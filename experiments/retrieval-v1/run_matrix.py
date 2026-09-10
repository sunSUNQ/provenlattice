from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .harness.agent_adapter import CommandAgentAdapter
from .harness.audit import audit_run, quarantine
from .harness.models import TaskDefinition
from .harness.provenance_tools import utc_now
from .harness.qualify import qualify
from .harness.reporting import generate_reports
from .harness.runner import run_task


ARM_ORDER = {
    1: ("native", "codegraph", "knowledge"),
    2: ("codegraph", "knowledge", "native"),
    3: ("knowledge", "native", "codegraph"),
}
ALIASES = {"sonnet", "opus", "default", "latest", "haiku", "fable"}


def _log(path: Path, event: str, **values) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"timestamp": utc_now(), "event": event, **values},
                                ensure_ascii=False) + "\n")


def _write_failure(results: Path, status: str, details: dict) -> None:
    value = {"status": status, **details}
    (results / "qualification-failure.json").write_text(
        json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [f"# {status}", ""] + [f"- **{key}**: `{item}`" for key, item in details.items()]
    (results / "qualification-failure.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_one(task: TaskDefinition, arm: str, repetition: int, args, adapter,
             log_path: Path) -> bool:
    run_dir = args.results / task.task_id / arm / f"r{repetition}"
    if run_dir.exists():
        existing = audit_run(run_dir, task, arm, repetition, args.model_id,
                             args.claude_version, args.provenlattice_commit)
        if existing["valid"]:
            _log(log_path, "skip_valid", run_key=f"{task.task_id}.{arm}.r{repetition}")
            return True
        destination = quarantine(run_dir)
        _log(log_path, "quarantine", run_key=f"{task.task_id}.{arm}.r{repetition}",
             destination=str(destination), errors=existing["errors"])
    for attempt in range(1, 4):
        _log(log_path, "run_start", run_key=f"{task.task_id}.{arm}.r{repetition}", attempt=attempt)
        result = run_task(task, arm, args.repo, args.results, adapter, args.timeout,
                          verify_commit=True, repetition=repetition, model_id=args.model_id,
                          claude_version=args.claude_version,
                          provenlattice_commit=args.provenlattice_commit,
                          database=args.database, attempt=attempt)
        audit = audit_run(result["run_dir"], task, arm, repetition, args.model_id,
                          args.claude_version, args.provenlattice_commit)
        if audit["valid"]:
            _log(log_path, "run_valid", run_key=f"{task.task_id}.{arm}.r{repetition}", attempt=attempt)
            return True
        run = result["run"]
        _log(log_path, "run_invalid", run_key=f"{task.task_id}.{arm}.r{repetition}",
             attempt=attempt, errors=audit["errors"], exit_reason=run.get("exit_reason"))
        if any("POLICY_VIOLATION" in item or "DIRTY_WORKTREE" in item for item in audit["errors"]):
            _write_failure(args.results, "R1 BLOCKED BY POLICY VIOLATION",
                           {"run_key": run.get("run_key"), "errors": audit["errors"]})
            return False
        infrastructure = (run.get("exit_reason") in {"adapter_error", "agent_nonzero_exit", "timeout"}
                          and not run.get("agent_output") and not run.get("tool_calls"))
        if not infrastructure or attempt == 3:
            _write_failure(args.results, "R1 BLOCKED BY INFRASTRUCTURE",
                           {"run_key": run.get("run_key"), "attempt": attempt,
                            "exit_reason": run.get("exit_reason"), "errors": audit["errors"]})
            return False
        destination = quarantine(result["run_dir"], "_attempts")
        _log(log_path, "attempt_archived", destination=str(destination))
        cooldown = args.cooldowns[min(attempt - 1, len(args.cooldowns) - 1)]
        _log(log_path, "cooldown", seconds=cooldown)
        time.sleep(cooldown)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and resume the frozen R1 experiment")
    parser.add_argument("--tasks", type=Path, default=Path("experiments/retrieval-v1/tasks"))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--agent-command", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--claude-version", required=True)
    parser.add_argument("--provenlattice-commit", required=True)
    parser.add_argument("--results", type=Path, default=Path("experiments/retrieval-v1/results"))
    parser.add_argument("--docs", type=Path, default=Path("docs/benchmarks"))
    parser.add_argument("--repetitions", type=int, choices=(1, 3), default=3)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--cooldowns", default="60,180,600")
    args = parser.parse_args()
    args.cooldowns = [int(value) for value in args.cooldowns.split(",")]
    if args.model_id.casefold() in ALIASES or not args.model_id.startswith("claude-"):
        raise ValueError("model-id must be a complete fixed Claude model ID, not an alias")
    args.results.mkdir(parents=True, exist_ok=True)
    log_path = args.results / "execution-log.ndjson"
    tasks = [TaskDefinition.load(path) for path in sorted(args.tasks.glob("T*.json"))]
    if [task.task_id for task in tasks] != [f"T{number:02d}" for number in range(1, 7)]:
        raise ValueError("frozen task set must be exactly T01..T06")
    adapter = CommandAgentAdapter(args.agent_command)
    qualification = [(tasks[0], "native", 1),
                     (tasks[0], "codegraph", 1), (tasks[0], "knowledge", 1)]
    qualification += [(task, arm, 1) for task in tasks[1:] for arm in ARM_ORDER[1]]
    for task, arm, repetition in qualification:
        if not _run_one(task, arm, repetition, args, adapter, log_path):
            return 2
    report = qualify(args.tasks, args.results)
    (args.results / "qualification.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _log(log_path, "qualification", status=report["qualification"], gates=report["gates"])
    if report["qualification"] != "PASS" or report["observed_runs"] != 18:
        _write_failure(args.results, "R1 QUALIFICATION FAILED",
                       {"observed_runs": report["observed_runs"],
                        "failed_gates": [g for g in report["gates"] if g["status"] != "PASS"]})
        return 3
    if args.repetitions == 1:
        print(json.dumps({"status": "QUALIFICATION PASS", "runs": 18}, indent=2))
        return 0
    for repetition in (2, 3):
        for task in tasks:
            for arm in ARM_ORDER[repetition]:
                if not _run_one(task, arm, repetition, args, adapter, log_path):
                    return 2
    final = generate_reports(args.tasks, args.results, args.docs, args.model_id,
                             args.claude_version, args.provenlattice_commit)
    _log(log_path, "complete", status=final["status"], runs=54)
    print(json.dumps(final, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

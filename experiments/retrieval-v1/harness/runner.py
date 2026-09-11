from __future__ import annotations

import argparse
import json
import re
import uuid
from pathlib import Path
from time import perf_counter

from .agent_adapter import CommandAgentAdapter
from .evaluator import evaluate, evaluate_r2
from .metrics import collect_metrics
from .models import ARM_TOOLS, WRITE_OPERATIONS, RunRequest, RunResult, TaskDefinition, ToolEvent
from .provenance_tools import repository_head, repository_status, sha256_text, utc_now, write_events


def run_task(task: TaskDefinition, arm: str, repo_path: str | Path, output_root: str | Path,
             adapter, timeout: float = 900, verify_commit: bool = True, repetition: int = 1,
             model_id: str = "unknown", claude_version: str = "unknown",
             provenlattice_commit: str | None = None, database: str | None = None,
             attempt: int = 1, protocol: str = "r1") -> dict:
    if arm not in ARM_TOOLS:
        raise ValueError(f"unknown arm: {arm}")
    run_key = f"{task.task_id}.{arm}.r{repetition}"
    run_id = f"{task.task_id}-{arm}-r{repetition}-{uuid.uuid4().hex[:8]}"
    run_dir = Path(output_root) / task.task_id / arm / f"r{repetition}"
    run_dir.mkdir(parents=True, exist_ok=True)
    start_time = utc_now()
    started = perf_counter()
    repo_path = str(Path(repo_path).resolve())
    actual_commit = repository_head(repo_path)
    status_before = repository_status(repo_path)
    errors: list[str] = []
    if verify_commit and actual_commit and actual_commit != task.commit:
        errors.append(f"REPO_COMMIT_MISMATCH expected={task.commit} actual={actual_commit}")
    if status_before:
        errors.append("DIRTY_WORKTREE_BEFORE_RUN")
    environment = {"PL_R1_ARM": arm, "PL_MODEL_ID": model_id,
                   "PL_CLAUDE_VERSION": claude_version}
    if protocol == "r2":
        environment["PL_R2_EVIDENCE_CONTRACT"] = "1"
    if database:
        environment["PL_R1_DATABASE"] = str(Path(database).resolve())
    request = RunRequest(run_id, task.task_id, repo_path, task.commit, arm, task.prompt,
                         sorted(ARM_TOOLS[arm]), environment, timeout)
    if errors:
        adapter_result = type("AdapterResult", (), {"output": "", "events": [],
                                                     "exit_reason": "preflight_failed",
                                                     "error": "; ".join(errors)})()
    else:
        adapter_result = adapter.run(request)
    events: list[ToolEvent] = adapter_result.events
    violations = list(errors)
    actual_model = getattr(adapter_result, "actual_model", None)
    actual_version = getattr(adapter_result, "actual_version", None)
    permission_denials = list(getattr(adapter_result, "permission_denials", None) or [])
    critical_permission_denials = [item for item in permission_denials
                                   if item.get("operation") not in {"shell", "unknown"}]
    if actual_model is not None and actual_model != model_id:
        violations.append(f"MODEL_MISMATCH expected={model_id} actual={actual_model}")
    if actual_version is not None and actual_version != claude_version:
        violations.append(f"CLAUDE_VERSION_MISMATCH expected={claude_version} actual={actual_version}")
    if critical_permission_denials:
        violations.append(f"RETRIEVAL_PERMISSION_DENIED:{len(critical_permission_denials)}")
    for event in events:
        if event.operation in WRITE_OPERATIONS:
            violations.append(f"WRITE_OPERATION:{event.operation}")
        if event.operation not in ARM_TOOLS[arm]:
            violations.append(f"DISALLOWED_OPERATION:{event.operation}")
        if event.operation == "shell" and re.search(
            r"\b(rm|del|remove-item|move-item|copy-item|git\s+(commit|reset|checkout|push))\b",
            str(event.query or event.target or ""), re.I,
        ):
            violations.append("DESTRUCTIVE_SHELL")
        command_text = str(event.query or event.target or "")
        if "provenlattice" in command_text.casefold() or "python -m provenlattice" in command_text.casefold():
            if arm == "native":
                violations.append("PROVENLATTICE_ACCESS_IN_NATIVE")
            elif arm == "codegraph" and event.operation in {
                "document", "evidence", "related-code", "cross-layer", "implemented", "requirements",
            }:
                violations.append(f"KNOWLEDGE_ACCESS_IN_CODEGRAPH:{event.operation}")
    status_after = repository_status(repo_path)
    if status_after != status_before:
        violations.append("POLICY_VIOLATION:WORKTREE_MODIFIED")
    ended = utc_now()
    duration_ms = (perf_counter() - started) * 1000
    usable_timeout = adapter_result.exit_reason == "timeout" and bool(events or adapter_result.output)
    status = ("failed" if violations or (adapter_result.exit_reason not in {"completed"} and not usable_timeout)
              else "completed")
    metrics = collect_metrics(task, events, duration_ms, adapter_result.output)
    evaluation = (evaluate_r2(task, adapter_result.output, events, metrics,
                              arm=arm, repo_path=repo_path)
                  if protocol == "r2" else evaluate(task, adapter_result.output, events, metrics))
    result = RunResult(run_id, task.task_id, arm, status,
                       evaluation["task_success"] if status == "completed" else None,
                       start_time, ended, duration_ms, len(events), adapter_result.output,
                       adapter_result.exit_reason, adapter_result.error, sorted(ARM_TOOLS[arm]), violations)
    run_record = result.to_dict()
    run_record.update({"run_key": run_key, "repetition": repetition,
                       "repo_path": repo_path, "repo_commit": task.commit,
                       "prompt": task.prompt, "environment": request.environment,
                       "agent_actual_commit": actual_commit,
                       "prompt_hash": sha256_text(task.prompt),
                       "model_id": model_id, "claude_version": claude_version,
                       "actual_model_id": actual_model, "actual_claude_version": actual_version,
                       "permission_denials": permission_denials,
                       "critical_permission_denials": critical_permission_denials,
                       "provenlattice_commit": provenlattice_commit,
                       "ground_truth_version": ("r2-evidence-v1" if protocol == "r2"
                                                else "r1-frozen-v1"), "attempt": attempt,
                       "protocol": protocol,
                       "git_status_before": status_before, "git_status_after": status_after,
                       "adapter": type(adapter).__name__})
    (run_dir / "run.json").write_text(json.dumps(run_record, indent=2, ensure_ascii=False), encoding="utf-8")
    write_events(run_dir / "events.ndjson", events)
    (run_dir / "agent-output.txt").write_text(adapter_result.output, encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "evaluation.json").write_text(json.dumps(evaluation, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"run_dir": str(run_dir), "run": run_record, "metrics": metrics, "evaluation": evaluation}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one read-only R1 qualification cell")
    parser.add_argument("task", type=Path)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--arm", choices=sorted(ARM_TOOLS), required=True)
    parser.add_argument("--agent-command", required=True)
    parser.add_argument("--results", type=Path, default=Path("experiments/retrieval-v1/results"))
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--repetition", type=int, default=1)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--claude-version", required=True)
    parser.add_argument("--provenlattice-commit", required=True)
    parser.add_argument("--database")
    parser.add_argument("--protocol", choices=("r1", "r2"), default="r1")
    parser.add_argument("--skip-commit-check", action="store_true")
    args = parser.parse_args()
    result = run_task(TaskDefinition.load(args.task), args.arm, args.repo, args.results,
                      CommandAgentAdapter(args.agent_command), args.timeout,
                      verify_commit=not args.skip_commit_check, repetition=args.repetition,
                      model_id=args.model_id, claude_version=args.claude_version,
                      provenlattice_commit=args.provenlattice_commit, database=args.database,
                      protocol=args.protocol)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["run"]["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

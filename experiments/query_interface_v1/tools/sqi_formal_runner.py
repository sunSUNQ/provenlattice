"""SQI-V1 formal qualification runner (Stage 3B execution wiring).

Arm wiring per frozen `SQI_FORMAL_QUALIFICATION_PROTOCOL_V1`:
  * native: Read/Grep/Glob only; neutral read-only system prompt; no SQI tool.
  * sqi: identical base tools + exactly one extra tool - the frozen CLI bridge
    (`python -m experiments.query_interface_v1.tools.sqi_cli`), whose stdout is
    the raw SQI envelope; per-session call log via PL_SQI_CALL_LOG.

The two arms share everything except SQI tool availability and the SQI citation
requirement - no other condition differs (protocol §2).

Modes:
  --check     preflight only (seals, config, runtime, fixtures); no agent run
  --run-cell  execute ONE formal cell (task, arm, repetition)
  --batch     execute all 36 cells sequentially after preflight
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINE_ROOT = HERE.parent
REPO_ROOT = LINE_ROOT.parents[1]
WORKSPACE = REPO_ROOT.parent
sys.path.insert(0, str(HERE))

from sqi_adapter import SQIAdapter  # noqa: E402
from sqi_cli import CANONICAL_CALLS  # noqa: E402
from sqi_evaluator import evaluate_cell  # noqa: E402
from sqi_isolation import leakage_events  # noqa: E402

models = importlib.import_module("experiments.retrieval-v1.harness.models")
agent_adapter = importlib.import_module("experiments.retrieval-v1.harness.agent_adapter")
provenance_tools = importlib.import_module("experiments.retrieval-v1.harness.provenance_tools")

TASKS_DIR = LINE_ROOT / "tasks"
RESULTS_DIR = LINE_ROOT / "results"
CONFIG_PATH = LINE_ROOT / "contract" / "formal-protocol-config.json"
SEALS = {
    "contract": LINE_ROOT / "contract" / "structured-query-interface-contract-v1.freeze.sha256",
    "implementation": LINE_ROOT / "contract" / "structured-query-interface-contract-v1.implementation-seal.sha256",
    "protocol": LINE_ROOT / "contract" / "sqi-formal-qualification-protocol-v1.seal.sha256",
    "amendment": LINE_ROOT / "contract" / "sqi-v1.1-amendments.sha256",
    "secondary": LINE_ROOT / "contract" / "structured-query-interface-contract-v1.secondary-seal.sha256",
}
# V1.1 amendment: SQI-T05.json was superseded after the V1 freeze (evidence-
# source declaration repair); its V1 seal entry is expected to mismatch.
AMENDMENT_SUPERSEDED = {"experiments/query_interface_v1/tasks/SQI-T05.json"}
REPOS = {
    "B1-aria2": WORKSPACE / "benchmark-repos" / "aria2",
    "B2-brpc": WORKSPACE / "benchmark-repos" / "brpc",
    "B3-rocksdb": WORKSPACE / "benchmark-repos" / "rocksdb",
}

def sqi_allowed_tools(task: dict) -> str:
    return ("Read(./**),Grep(./**),Glob,"
            "Bash(python -m experiments.query_interface_v1.tools.sqi_cli *)")


NATIVE_ALLOWED_TOOLS = "Read(./**),Grep(./**),Glob"

SQI_ARM_PROMPT_TEMPLATE = (
    "This is a read-only retrieval experiment. Never edit, create, delete, move, or commit files. "
    "Do not change git state. Answer the frozen user task using only permitted retrieval capabilities. "
    "You have the Structured Query Interface V1. Run exactly this bridge command (run it from any "
    "directory; the PYTHONPATH is preconfigured): "
    "python -m experiments.query_interface_v1.tools.sqi_cli --database \"{database}\" "
    "{code_database_arg}--commit \"{commit}\" --call <call> --arg key=value [--arg ...] "
    "with call one of symbol.lookup, symbol.callers, symbol.callees, symbol.references, "
    "impact.frontier, code.related, bundle.explain; use one --arg per parameter "
    "(e.g. --arg name=DownloadEngine, --arg symbol=<qualified_name or id>, "
    "--arg document=<document anchor>, --arg changed_shard_paths=db,file, "
    "--arg budget=max_evidence,max_symbols,max_edges,max_sections). "
    "Each invocation returns one JSON envelope; treat its data as structural facts, cite only "
    "evidence ids actually returned, and end the answer with 'Evidence Used:' followed by one "
    "'- E-...' line per used Evidence ID. You MUST perform at least one bridge invocation for "
    "this task: answers based only on file reading are invalid for this arm. Structural facts "
    "(identity, existence, frontier membership) may be cited directly; semantic claims "
    "(definition meaning, call-site meaning, reference purpose, downstream impact, "
    "document-code equivalence) must be verified by reading the source files before you assert "
    "them. Never repeat an identical bridge invocation (same call, parameters, database, and "
    "commit): it returns the byte-identical envelope, and a truncated result will not expand "
    "on retry — if you need more or different information, issue a more targeted query instead. "
    "Before finishing, verify that every distinct source domain the task requires has "
    "contributed cited evidence (for example, a task spanning both code and knowledge must "
    "show evidence from each domain); an answer missing a required domain is incomplete. "
    "An empty envelope is definitive for the anchor form you used: anchors resolve by exact "
    "node id, qualified_name, or node name only — path fragments and natural-language "
    "variants do not resolve. On an empty result, first check resolution with symbol.lookup "
    "or bundle.explain on the anchor alone; if it does not resolve, vary the identifier form "
    "or discover stored names with a broader query (for example bundle.explain on the "
    "enclosing document or symbol) instead of retrying semantically equivalent forms. "
    "Never bypass, chain, pipe, or truncate the CLI's JSON output. Stay inside the "
    "repository working directory; do not read or probe paths outside it."
)
NATIVE_ARM_PROMPT = (
    "This is a read-only retrieval experiment. Never edit, create, delete, move, or commit files. "
    "Do not change git state. Answer the frozen user task using only your file tools "
    "(read/grep/glob). Do not invoke ProvenLattice, SQI, or access any ProvenLattice database. "
    "Stay inside the repository working directory; do not read or probe paths outside it."
)


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def verify_seal(path: Path, skip: set[str] | None = None) -> tuple[bool, int, int, list[str]]:
    """Round-trip a seal file. Entries named in `skip` are treated as
    superseded-by-amendment (skipped, not counted as mismatches)."""
    skip = skip or set()
    pattern = re.compile(r"^([a-f0-9]{64})\s+\*?(.+?)\s*$")
    total = bad = 0
    mismatched: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        expected, rel = match.group(1), match.group(2).replace("\\", "/")
        if rel in skip:
            continue
        target = REPO_ROOT / rel
        total += 1
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            bad += 1
            mismatched.append(rel)
    return bad == 0, total - bad, total, mismatched


def load_tasks() -> list[dict]:
    tasks = []
    for index in range(1, 7):
        task = json.loads((TASKS_DIR / f"SQI-T0{index}.json").read_text(encoding="utf-8"))
        tasks.append(task)
    return tasks


def to_task_definition(task: dict) -> "models.TaskDefinition":
    return models.TaskDefinition(
        task_id=task["task_id"], repository=task["repository"], commit=task["commit"],
        category=task["category"], prompt=task["prompt"],
        ground_truth=task["ground_truth"], expected_files=task["expected_files"],
        expected_symbols=task["expected_symbols"],
        expected_documents=task.get("expected_documents", []),
        expected_relationships=task.get("expected_relationships", []),
        success_criteria=task["success_criteria"], difficulty=task.get("difficulty", "Medium"))


def resolve_database(path_value: str) -> str:
    path = Path(path_value)
    if path.is_absolute() and path.exists():
        return str(path)
    for base in (WORKSPACE, REPO_ROOT):
        candidate = base / path
        if candidate.exists():
            return str(candidate)
    raise RuntimeError(f"frozen database not found: {path_value}")


def build_arm_prompt(arm: str, task: dict) -> str:
    """V1.3 A1: per-session arm prompt with absolute bridge/database paths
    injected for the sqi arm (no bootstrap discovery needed)."""
    if arm != "sqi":
        return NATIVE_ARM_PROMPT
    database = resolve_database(task["database"])
    bridge = str(REPO_ROOT / "experiments" / "query_interface_v1" / "tools" / "sqi_cli.py")
    code_arg = ""
    if task.get("code_database"):
        code_arg = '--code-database "{}" '.format(resolve_database(task["code_database"]))
    return SQI_ARM_PROMPT_TEMPLATE.format(
        bridge=bridge.replace("\\", "/"), database=database.replace("\\", "/"),
        code_database_arg=code_arg, commit=task["commit"])


def build_command(arm: str, config: dict, task: dict | None = None) -> list[str]:
    """The two arms share the base command; they differ ONLY in the system
    prompt and allowed tools (protocol §2 arm parity). V1.3 (A1): the SQI
    prompt injects the absolute bridge/database paths per session."""
    claude = shutil.which("claude") or "claude"
    command = [claude, "-p", "--verbose", "--output-format", "stream-json"]
    # V1.3 A4: `default` permission mode = tools outside allowedTools are
    # denied BEFORE execution (dontAsk auto-approved everything, which let a
    # T04.sqi session delete 330 tracked files in the V1.1 batch).
    command.extend(["--permission-mode", "default"])
    if arm == "sqi" and task is not None:
        command.extend(["--append-system-prompt", build_arm_prompt(arm, task)])
        command.extend(["--allowedTools", sqi_allowed_tools(task)])
    else:
        command.extend(["--append-system-prompt", NATIVE_ARM_PROMPT])
        command.extend(["--allowedTools", NATIVE_ALLOWED_TOOLS])
    command.extend(["--model", config["model_id"]])
    return command


def preflight() -> dict:
    config = load_config()
    checks: dict[str, object] = {}
    for name, path in SEALS.items():
        skip = AMENDMENT_SUPERSEDED if name == "contract" else None
        ok, passed, total, mismatched = verify_seal(path, skip=skip)
        checks[f"seal_{name}"] = {"pass": ok, "verified": passed,
                                  "total": total,
                                  "superseded_skipped": sorted(mismatched)}
    checks["claude_cli"] = bool(shutil.which("claude"))
    for repo, path in REPOS.items():
        checks[f"repo_{repo}"] = path.exists()
    tasks = load_tasks()
    checks["tasks_loaded"] = len(tasks)
    for task in tasks:
        checks[f"database_{task['task_id']}"] = Path(
            resolve_database(task["database"])).exists()
    ok = all(value.get("pass", value) if isinstance(value, dict) else value
             for value in checks.values())
    return {"preflight": "PASS" if ok else "FAIL", "checks": checks,
            "config": {"model_id": config["model_id"],
                       "claude_cli_version": config["claude_cli_version"],
                       "repetitions_per_cell": config["repetitions_per_cell"]}}


def run_cell(task: dict, arm: str, repetition: int, config: dict,
             batch_id: str) -> dict:
    assert arm in ("native", "sqi")
    database = resolve_database(task["database"])
    repo_path = str(REPOS[task["repository"]].resolve())
    run_id = f"{task['task_id']}-{arm}-r{repetition}-{uuid.uuid4().hex[:8]}"
    run_dir = RESULTS_DIR / "formal" / batch_id / task["task_id"] / arm / f"r{repetition}"
    run_dir.mkdir(parents=True, exist_ok=True)
    call_log_path = run_dir / "sqi-call-log.ndjson"
    if call_log_path.exists():
        call_log_path.unlink()
    environment = {
        "PL_SQI_PROTOCOL": "1",
        "PL_SQI_CALL_LOG": str(call_log_path),
        "PL_SQI_DATABASE": database,
        "PL_SQI_COMMIT": task["commit"],
        "PL_MODEL_ID": config["model_id"],
        "PL_CLAUDE_VERSION": config["claude_cli_version"],
        # The agent session runs with cwd = benchmark repo, so the bridge
        # command `python -m experiments...` needs the provenlattice checkout
        # (experiments package + src) on PYTHONPATH; claude's Bash children
        # inherit this env (protocol §2: identical for both arms, unused by
        # native).
        "PYTHONPATH": str(REPO_ROOT / "src") + os.pathsep + str(REPO_ROOT),
    }
    if task.get("code_database"):
        environment["PL_SQI_CODE_DATABASE"] = resolve_database(
            task["code_database"])
    request = models.RunRequest(
        run_id=run_id, task_id=task["task_id"], repo_path=repo_path,
        repo_commit=task["commit"], arm=arm, prompt=task["prompt"],
        allowed_tools=sorted({"read", "search", "grep", "glob", "shell"}
                             if arm == "sqi" else {"read", "grep", "glob"}),
        environment=environment, timeout=float(config["timeout_s"]))
    adapter = agent_adapter.CommandAgentAdapter(build_command(arm, config, task))
    started = time.perf_counter()
    result = adapter.run(request)
    duration_ms = (time.perf_counter() - started) * 1000
    call_log = []
    if call_log_path.exists():
        for line in call_log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                call_log.append(json.loads(line))
    events = [event.to_dict() for event in result.events]
    violations: list[str] = []
    leaks = leakage_events(events, repo_path)
    for leak in leaks:
        violations.append("CHECKOUT_LEAKAGE:%s:%s" % (leak["operation"],
                                                      leak["target"][:120]))
    evaluation = evaluate_cell(task, arm, result.output, events, call_log, database)
    for flag in evaluation["capability_failure_flags"]:
        if flag == "SQI_ACCESS_IN_NATIVE":
            violations.append(flag)
    status = ("completed" if result.exit_reason == "completed" and not violations
              else "failed")
    record = {
        "schema": "SQI_FORMAL_RUN_RECORD_V1",
        "run_id": run_id, "batch_id": batch_id,
        "run_kind": "formal-qualification",
        "task_id": task["task_id"], "arm": arm, "repetition": repetition,
        "repository": task["repository"], "commit": task["commit"],
        "database": task["database"],
        "model_id": config["model_id"],
        "requested_claude_version": config["claude_cli_version"],
        "actual_model": result.actual_model, "actual_claude_version": result.actual_version,
        "status": status, "exit_reason": result.exit_reason, "error": result.error,
        "task_success": evaluation["task_success"] if status == "completed" else None,
        "duration_ms": round(duration_ms, 3),
        "tool_calls": len(events),
        "sqi_calls": len(call_log),
        "policy_violations": violations,
        "checkout_leakage_events": len(leaks),
        "prompt_hash": hashlib.sha256(task["prompt"].encode("utf-8")).hexdigest(),
        "arm_prompt_sha256": hashlib.sha256(
            (build_arm_prompt(arm, task) if arm == "sqi" else NATIVE_ARM_PROMPT)
            .encode("utf-8")).hexdigest(),
        "allowed_tools": sqi_allowed_tools(task) if arm == "sqi" else NATIVE_ALLOWED_TOOLS,
        "canonical_calls_available": list(CANONICAL_CALLS) if arm == "sqi" else [],
        "protocol": "SQI_FORMAL_QUALIFICATION_PROTOCOL_V1",
        "infrastructure_attribution": None if result.exit_reason in ("completed",)
        else ("timeout" if result.exit_reason == "timeout" else "adapter/runtime"),
    }
    (run_dir / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (run_dir / "events.ndjson").write_text(
        "\n".join(json.dumps(event, ensure_ascii=False, sort_keys=True)
                  for event in events) + "\n", encoding="utf-8")
    (run_dir / "agent-output.txt").write_text(result.output or "", encoding="utf-8")
    (run_dir / "evaluation.json").write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"run_dir": str(run_dir), "record": record, "evaluation": evaluation}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("check", "run-cell", "batch"),
                        default="check")
    parser.add_argument("--task", choices=[f"SQI-T0{i}" for i in range(1, 7)])
    parser.add_argument("--arm", choices=("native", "sqi"))
    parser.add_argument("--repetition", type=int, default=1)
    parser.add_argument("--batch-id", default=None)
    args = parser.parse_args()

    if args.mode == "check":
        report = preflight()
        print(json.dumps(report, indent=1))
        return 0 if report["preflight"] == "PASS" else 1

    preflight_report = preflight()
    if preflight_report["preflight"] != "PASS":
        print(json.dumps(preflight_report, indent=1))
        return 1
    config = load_config()
    tasks = {task["task_id"]: task for task in load_tasks()}
    batch_id = args.batch_id or time.strftime(
        "SQI-FORMAL-%Y%m%dT%H%M%SZ", time.gmtime())

    if args.mode == "run-cell":
        if not (args.task and args.arm):
            parser.error("--run-cell requires --task and --arm")
        result = run_cell(tasks[args.task], args.arm, args.repetition, config, batch_id)
        print(json.dumps({"run_dir": result["run_dir"],
                          "task_id": args.task, "arm": args.arm,
                          "status": result["record"]["status"],
                          "task_success": result["record"]["task_success"],
                          "capability_failure_flags":
                              result["evaluation"]["capability_failure_flags"]},
                         indent=1))
        return 0 if result["record"]["status"] == "completed" else 1

    # batch: 36 cells, frozen order (tasks ascending, arms native then sqi,
    # repetitions ascending - protocol §3)
    results = []
    for task in load_tasks():
        for arm in ("native", "sqi"):
            for repetition in range(1, int(config["repetitions_per_cell"]) + 1):
                outcome = run_cell(task, arm, repetition, config, batch_id)
                results.append({"task_id": task["task_id"], "arm": arm,
                                "repetition": repetition,
                                "status": outcome["record"]["status"],
                                "task_success": outcome["record"]["task_success"]})
                print(json.dumps(results[-1]))
    completed = sum(1 for item in results if item["status"] == "completed")
    print(json.dumps({"batch_id": batch_id, "cells_total": len(results),
                      "cells_completed": completed}, indent=1))
    return 0 if completed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

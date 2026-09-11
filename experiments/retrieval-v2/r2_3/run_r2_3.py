from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path

adapter_module = importlib.import_module("experiments.retrieval-v1.harness.agent_adapter")
models_module = importlib.import_module("experiments.retrieval-v1.harness.models")
runner_module = importlib.import_module("experiments.retrieval-v1.harness.runner")
v2 = importlib.import_module("experiments.retrieval-v2.evaluator-v2.evaluator")

TASK_IDS = ("T01", "T03", "T05")
ARM_ORDER = {1: ("native", "codegraph", "knowledge"),
             2: ("codegraph", "knowledge", "native"),
             3: ("knowledge", "native", "codegraph")}
ROOT = Path(__file__).parent
V2_PATH = ROOT.parent / "evaluator-v2" / "ground-truth-v2" / "ground-truth-v2.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tasks():
    return {task_id: models_module.TaskDefinition.load(ROOT.parent / "r2_1" / "tasks" / f"{task_id}.json")
            for task_id in TASK_IDS}


def ground_truth():
    return {item["task_id"]: item for item in json.loads(V2_PATH.read_text(encoding="utf-8"))["tasks"]}


def audit(path: Path, task, arm: str, repetition: int, args) -> dict:
    errors = []
    required = ("run.json", "events.ndjson", "agent-output.txt", "metrics.json", "evaluation.json", "evaluation-v2.json")
    missing = [name for name in required if not (path / name).is_file()]
    if missing:
        return {"valid": False, "errors": [f"MISSING:{name}" for name in missing]}
    run = json.loads((path / "run.json").read_text(encoding="utf-8"))
    metrics = json.loads((path / "metrics.json").read_text(encoding="utf-8"))
    v2_eval = json.loads((path / "evaluation-v2.json").read_text(encoding="utf-8"))
    if run.get("run_key") != f"{task.task_id}.{arm}.r{repetition}": errors.append("RUN_KEY")
    if run.get("prompt_hash") != hashlib.sha256(task.prompt.encode()).hexdigest(): errors.append("PROMPT_HASH")
    if run.get("agent_actual_commit") != task.commit: errors.append("REPO_SHA")
    if run.get("provenlattice_commit") != args.provenlattice_commit: errors.append("PROVENLATTICE_COMMIT")
    if run.get("protocol_revision") != "r2.3": errors.append("PROTOCOL_REVISION")
    if run.get("model_id") != args.model_id or run.get("actual_model_id") != args.model_id: errors.append("MODEL")
    if run.get("claude_version") != args.claude_version or run.get("actual_claude_version") != args.claude_version: errors.append("CLAUDE_VERSION")
    if run.get("ground_truth_v2_hash") != digest(V2_PATH): errors.append("GROUNDTRUTH_V2_HASH")
    if run.get("evaluator_v2_version") != "r2.2-groundtruth-v2": errors.append("EVALUATOR_V2_VERSION")
    if run.get("status") != "completed": errors.append(f"RUN_STATUS:{run.get('status')}")
    if run.get("policy_violations") or run.get("git_status_before") or run.get("git_status_after"): errors.append("ISOLATION")
    values = [json.loads(line) for line in (path / "events.ndjson").read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(values) != run.get("tool_calls") or len(values) != metrics.get("tool_turns"): errors.append("EVENT_COUNT")
    expected = ground_truth()[task.task_id]
    replay = v2.evaluate_v2(expected, (path / "agent-output.txt").read_text(encoding="utf-8"), values,
                             repo_root=args.repo, known_evidence_ids={"E-CODE-C2F8A2E93CB05E73B643FBBE", "E-CODE-4374CC9A74236B67C11F3479"})
    if replay != v2_eval: errors.append("EVALUATOR_V2_REPLAY")
    for key in ("returned_evidence_ids", "exposed_evidence_ids", "used_evidence_ids"):
        if key not in v2_eval: errors.append(f"LIFECYCLE:{key}")
    return {"valid": not errors, "errors": errors, "evaluation": v2_eval, "run": run}


def run_cell(task, arm: str, repetition: int, database: str | None, args, adapter) -> dict:
    path = args.results / task.task_id / arm / f"r{repetition}"
    if path.exists():
        if not args.resume:
            raise FileExistsError(f"refusing to replace existing R2.3 cell: {path}")
        checked = audit(path, task, arm, repetition, args)
        if checked["valid"]:
            return {"run_key": f"{task.task_id}.{arm}.r{repetition}", "valid": True, "skipped": True,
                    "task_success": checked["evaluation"]["task_success"]}
        raise ValueError(f"existing cell invalid: {path}: {checked['errors']}")
    result = runner_module.run_task(task, arm, args.repo, args.results, adapter, args.timeout,
                                    repetition=repetition, model_id=args.model_id,
                                    claude_version=args.claude_version,
                                    provenlattice_commit=args.provenlattice_commit,
                                    database=database, protocol="r2")
    path = Path(result["run_dir"])
    values = [json.loads(line) for line in (path / "events.ndjson").read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = ground_truth()[task.task_id]
    evaluation = v2.evaluate_v2(expected, (path / "agent-output.txt").read_text(encoding="utf-8"), values,
                                 repo_root=args.repo, known_evidence_ids={"E-CODE-C2F8A2E93CB05E73B643FBBE", "E-CODE-4374CC9A74236B67C11F3479"})
    (path / "evaluation-v2.json").write_text(json.dumps(evaluation, indent=2, ensure_ascii=False), encoding="utf-8")
    run = json.loads((path / "run.json").read_text(encoding="utf-8"))
    run.update({"protocol_revision": "r2.3", "ground_truth_v2_version": "groundtruth-v2",
                "ground_truth_v2_hash": digest(V2_PATH), "evaluator_v2_version": "r2.2-groundtruth-v2"})
    (path / "run.json").write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
    checked = audit(path, task, arm, repetition, args)
    return {"run_key": f"{task.task_id}.{arm}.r{repetition}", "valid": checked["valid"],
            "errors": checked["errors"], "task_success": evaluation["task_success"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen GroundTruthV2 R2.3 Agent revalidation")
    parser.add_argument("--phase", choices=("qualification", "stability", "all"), default="all")
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--codegraph-database", required=True)
    parser.add_argument("--knowledge-database", required=True)
    parser.add_argument("--agent-command", default="claude -p --verbose --output-format stream-json")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--claude-version", required=True)
    parser.add_argument("--provenlattice-commit", required=True)
    parser.add_argument("--results", type=Path, default=Path("experiments/retrieval-v2/r2_3/results"))
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    task_map = tasks()
    adapter = adapter_module.CommandAgentAdapter(args.agent_command)
    cells = []
    phases = (1,) if args.phase == "qualification" else (2, 3) if args.phase == "stability" else (1, 2, 3)
    for repetition in phases:
        for task_id in TASK_IDS:
            for arm in ARM_ORDER[repetition]:
                database = None if arm == "native" else args.codegraph_database if arm == "codegraph" else args.knowledge_database
                cell = run_cell(task_map[task_id], arm, repetition, database, args, adapter)
                cells.append(cell); print(json.dumps(cell, ensure_ascii=False), flush=True)
                if not cell["valid"]: return 2
    summary = {"protocol": "r2.3", "phase": args.phase, "model_id": args.model_id,
               "claude_version": args.claude_version, "provenlattice_commit": args.provenlattice_commit,
               "ground_truth_v2_hash": digest(V2_PATH), "cells": cells}
    (args.results / f"{args.phase}-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

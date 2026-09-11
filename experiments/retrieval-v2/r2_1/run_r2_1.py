from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path


adapter_module = importlib.import_module("experiments.retrieval-v1.harness.agent_adapter")
audit_module = importlib.import_module("experiments.retrieval-v1.harness.audit")
models_module = importlib.import_module("experiments.retrieval-v1.harness.models")
runner_module = importlib.import_module("experiments.retrieval-v1.harness.runner")

TASK_IDS = ("T01", "T03", "T05")
ARM_ORDER = {
    1: ("native", "codegraph"),
    2: ("codegraph", "native"),
    3: ("native", "codegraph"),
}


def _load_tasks() -> list:
    task_dir = Path(__file__).parent / "tasks"
    tasks = [models_module.TaskDefinition.load(task_dir / f"{task_id}.json")
             for task_id in TASK_IDS]
    frozen_sources = {
        "T01": Path("experiments/retrieval-v1/tasks/T01.json"),
        "T03": Path("experiments/retrieval-v1/tasks/T03.json"),
        "T05": Path("experiments/retrieval-v2/tasks/T05.json"),
    }
    for task in tasks:
        source = models_module.TaskDefinition.load(frozen_sources[task.task_id])
        if task.prompt != source.prompt:
            raise ValueError(f"frozen prompt changed for {task.task_id}")
    return tasks


def _run_cell(task, arm: str, repetition: int, database: str | None, args, adapter) -> dict:
    run_dir = args.results / task.task_id / arm / f"r{repetition}"
    if run_dir.exists():
        raise FileExistsError(f"refusing to replace frozen cell: {run_dir}")
    result = runner_module.run_task(
        task, arm, args.repo, args.results, adapter, args.timeout,
        repetition=repetition, model_id=args.model_id,
        claude_version=args.claude_version,
        provenlattice_commit=args.provenlattice_commit, database=database,
        protocol="r2",
    )
    audit = audit_module.audit_run(
        result["run_dir"], task, arm, repetition, args.model_id,
        args.claude_version, args.provenlattice_commit, protocol="r2",
    )
    return {
        "run_key": f"{task.task_id}.{arm}.r{repetition}",
        "valid": audit["valid"], "errors": audit["errors"],
        "status": result["run"]["status"],
        "task_success": result["evaluation"]["task_success"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen ProvenLattice V1.0-R2.1")
    parser.add_argument("--track", choices=("codegraph", "knowledge", "all"), default="all")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--codegraph-database", required=True)
    parser.add_argument("--knowledge-database", required=True)
    parser.add_argument("--agent-command", default="claude -p --verbose --output-format stream-json")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--claude-version", required=True)
    parser.add_argument("--provenlattice-commit", required=True)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--results", type=Path,
                        default=Path("experiments/retrieval-v2/r2_1/results"))
    args = parser.parse_args()
    tasks = _load_tasks()
    adapter = adapter_module.CommandAgentAdapter(args.agent_command)
    cells = []
    if args.track in {"codegraph", "all"}:
        for repetition in (1, 2, 3):
            for task in tasks:
                for arm in ARM_ORDER[repetition]:
                    database = None if arm == "native" else args.codegraph_database
                    cell = _run_cell(task, arm, repetition, database, args, adapter)
                    cells.append(cell)
                    print(json.dumps(cell, ensure_ascii=False), flush=True)
                    if not cell["valid"]:
                        return 2
    if args.track in {"knowledge", "all"}:
        task = next(item for item in tasks if item.task_id == "T05")
        for repetition in (1, 2, 3):
            cell = _run_cell(task, "knowledge", repetition, args.knowledge_database, args, adapter)
            cells.append(cell)
            print(json.dumps(cell, ensure_ascii=False), flush=True)
            if not cell["valid"]:
                return 2
    args.results.mkdir(parents=True, exist_ok=True)
    summary = {"protocol": "r2.1", "model_id": args.model_id,
               "claude_version": args.claude_version,
               "provenlattice_commit": args.provenlattice_commit,
               "cells": cells}
    (args.results / f"{args.track}-execution-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

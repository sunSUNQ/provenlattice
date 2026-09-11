from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path


adapter_module = importlib.import_module("experiments.retrieval-v1.harness.agent_adapter")
audit_module = importlib.import_module("experiments.retrieval-v1.harness.audit")
models_module = importlib.import_module("experiments.retrieval-v1.harness.models")
runner_module = importlib.import_module("experiments.retrieval-v1.harness.runner")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen R2 T05 three-arm qualification")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--codegraph-database", required=True)
    parser.add_argument("--knowledge-database", required=True)
    parser.add_argument("--agent-command", default="claude -p --verbose --output-format stream-json")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--claude-version", required=True)
    parser.add_argument("--provenlattice-commit", required=True)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--results", type=Path,
                        default=Path("experiments/retrieval-v2/results"))
    args = parser.parse_args()
    task = models_module.TaskDefinition.load(Path(__file__).parent / "tasks" / "T05.json")
    adapter = adapter_module.CommandAgentAdapter(args.agent_command)
    summary = []
    for arm in ("native", "codegraph", "knowledge"):
        database = (None if arm == "native" else args.codegraph_database
                    if arm == "codegraph" else args.knowledge_database)
        result = runner_module.run_task(
            task, arm, args.repo, args.results, adapter, args.timeout,
            model_id=args.model_id, claude_version=args.claude_version,
            provenlattice_commit=args.provenlattice_commit, database=database,
            protocol="r2",
        )
        audit = audit_module.audit_run(
            result["run_dir"], task, arm, 1, args.model_id, args.claude_version,
            args.provenlattice_commit, protocol="r2",
        )
        summary.append({"arm": arm, "valid": audit["valid"], "errors": audit["errors"],
                        "status": result["run"]["status"],
                        "task_success": result["evaluation"]["task_success"]})
        if not audit["valid"]:
            break
    args.results.mkdir(parents=True, exist_ok=True)
    output = {"protocol": "r2", "task": "T05", "cells": summary,
              "qualification": "PASS" if len(summary) == 3 and all(
                  item["valid"] for item in summary) else "FAIL"}
    (args.results / "t05-qualification.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output["qualification"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

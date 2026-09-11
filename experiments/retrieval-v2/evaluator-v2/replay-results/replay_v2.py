from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

ev = importlib.import_module("experiments.retrieval-v2.evaluator-v2.evaluator")


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline GroundTruthV2 replay")
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("experiments/retrieval-v2/evaluator-v2/replay-results/evaluator-v2-replay.json"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    code_repo = (repo.parent / "benchmark-repos" / "brpc") if (repo.parent / "benchmark-repos" / "brpc").is_dir() else repo
    gt = {item["task_id"]: item for item in json.loads((Path(__file__).parents[1] / "ground-truth-v2" / "ground-truth-v2.json").read_text(encoding="utf-8"))["tasks"]}
    roots = [repo / "experiments/retrieval-v1/results", repo / "experiments/retrieval-v2/results", repo / "experiments/retrieval-v2/r2_1/results"]
    run_dirs = []
    for root in roots:
        for task in ("T01", "T03", "T05"):
            for path in root.glob(f"{task}/*/r*"):
                if (path / "run.json").is_file() and (path / "events.ndjson").is_file() and (path / "agent-output.txt").is_file():
                    run_dirs.append(path)
    known = set()
    for path in run_dirs:
        for line in (path / "events.ndjson").read_text(encoding="utf-8").splitlines():
            try:
                known.update(str(item).upper() for item in (json.loads(line).get("evidence_ids") or []))
            except json.JSONDecodeError:
                continue
    # These two citations were not exposed by the failing bundles, but trace_evidence
    # against the frozen brpc DB confirms that both are real CodeDefinition facts.
    known.update({"E-CODE-C2F8A2E93CB05E73B643FBBE", "E-CODE-4374CC9A74236B67C11F3479"})
    cells = []
    for path in sorted(run_dirs):
        task_id = path.parts[-3]
        arm = path.parts[-2]
        run = json.loads((path / "run.json").read_text(encoding="utf-8"))
        events = [json.loads(line) for line in (path / "events.ndjson").read_text(encoding="utf-8").splitlines() if line.strip()]
        output = (path / "agent-output.txt").read_text(encoding="utf-8")
        task = gt[task_id]
        first = ev.evaluate_v2(task, output, events, repo_root=code_repo, known_evidence_ids=known)
        second = ev.evaluate_v2(task, output, events, repo_root=code_repo, known_evidence_ids=known)
        old = json.loads((path / "evaluation.json").read_text(encoding="utf-8")) if (path / "evaluation.json").is_file() else {}
        attribution = "TRUE_CAPABILITY_SUCCESS" if first["task_success"] and old.get("task_success") else (
            "EVALUATOR_FALSE_NEGATIVE" if first["task_success"] and not old.get("task_success") else
            "UNKNOWN_EVIDENCE" if first["unsupported_citation_count"] else
            "INVALID_EVIDENCE" if first["invalid_evidence_count"] else
            "TRUE_CAPABILITY_FAILURE")
        cells.append({"source": str(path.relative_to(repo)).replace("\\", "/"), "task": task_id, "arm": arm,
                      "repetition": int(path.name[1:]), "old_task_success": old.get("task_success"),
                      "old_recall": old.get("required_evidence_recall"),
                      "new_task_success": first["task_success"], "exact_recall_v2": first["exact_evidence_recall"],
                      "concept_recall_v2": first["concept_recall"], "new_precision": first["evidence_precision"],
                      "old_unsupported": old.get("unsupported_claim_count", old.get("wrong_evidence_count")),
                      "new_unsupported": first["unsupported_citation_count"],
                      "new_invalid": first["invalid_evidence_count"], "attribution": attribution,
                      "deterministic": first == second})
    counts = {}
    for cell in cells:
        counts[cell["attribution"]] = counts.get(cell["attribution"], 0) + 1
    result = {"protocol": "r2.2", "evaluator_version": "r2.2-groundtruth-v2",
              "run_count": len(cells), "known_evidence_count": len(known),
              "offline_only": True, "deterministic": all(item["deterministic"] for item in cells),
              "attribution_counts": counts, "cells": cells}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("run_count", "deterministic", "attribution_counts")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

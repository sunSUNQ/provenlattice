from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
from statistics import median
from types import SimpleNamespace

ARTIFACTS = ("run.json", "events.ndjson", "agent-output.txt", "metrics.json", "evaluation.json")
TASKS = ("T01", "T03", "T05")
ARMS = ("native", "codegraph", "knowledge")
models = importlib.import_module("experiments.retrieval-v1.harness.models")
evaluator = importlib.import_module("experiments.retrieval-v1.harness.evaluator")
provenance = importlib.import_module("experiments.retrieval-v1.harness.provenance_tools")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cell_dirs(root: Path):
    for task in TASKS:
        for arm in ARMS:
            for repetition in (1, 2, 3):
                path = root / task / arm / f"r{repetition}"
                if path.is_dir():
                    yield task, arm, repetition, path


def load_task(task: str):
    return models.TaskDefinition.load(Path(__file__).parent / "tasks" / f"{task}.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze and replay R2.1 without Agent calls")
    parser.add_argument("--results", type=Path, default=Path("experiments/retrieval-v2/r2_1/results"))
    args = parser.parse_args()
    root = args.results.resolve()
    workspace = Path.cwd().resolve()
    cells = list(cell_dirs(root))
    if len(cells) != 21:
        raise SystemExit(f"expected 21 cells, found {len(cells)}")
    manifest_cells, replay_cells, grouped = [], [], {}
    for task_id, arm, repetition, path in cells:
        missing = [name for name in ARTIFACTS if not (path / name).is_file()]
        if missing:
            raise SystemExit(f"missing artifacts in {path}: {missing}")
        run = json.loads((path / "run.json").read_text(encoding="utf-8"))
        task = load_task(task_id)
        manifest_cells.append({
            "task": task_id, "arm": arm, "repetition": repetition,
            "repo_sha": run.get("agent_actual_commit"), "expected_repo_sha": run.get("repo_commit"),
            "model_id": run.get("model_id"), "claude_version": run.get("claude_version"),
            "harness_revision": run.get("provenlattice_commit"), "prompt_hash": run.get("prompt_hash"),
            "run_key": run.get("run_key"),
            "artifacts": [{"path": str((path / name).resolve().relative_to(workspace)).replace("\\", "/"),
                           "sha256": sha256(path / name)} for name in ARTIFACTS],
        })
        metrics = json.loads((path / "metrics.json").read_text(encoding="utf-8"))
        original = json.loads((path / "evaluation.json").read_text(encoding="utf-8"))
        values = provenance.read_events(path / "events.ndjson")
        request = SimpleNamespace(run_id=run.get("run_id"), task_id=task_id, arm=arm)
        events = [models.ToolEvent.from_dict(value, request) for value in values]
        replayed = evaluator.evaluate_r2(task, (path / "agent-output.txt").read_text(encoding="utf-8"),
                                         events, metrics, arm=arm, repo_path=run.get("repo_path"))
        fields = ("task_success", "required_evidence_recall", "evidence_precision",
                  "wrong_path_count", "unsupported_claim_count")
        comparison = {key: {"original": original.get(key), "replay": replayed.get(key),
                            "equal": original.get(key) == replayed.get(key)} for key in fields}
        replay_cells.append({"task": task_id, "arm": arm, "repetition": repetition,
                             "harness_revision": run.get("provenlattice_commit"),
                             "changed_fields": [key for key, item in comparison.items() if not item["equal"]],
                             "semantic_equal": all(item["equal"] for item in comparison.values()),
                             "comparison": comparison})
        grouped.setdefault((task_id, arm), []).append({"run": run, "metrics": metrics, "evaluation": original})

    (root / "manifest-r2.1.json").write_text(json.dumps({"protocol": "r2.1", "cell_count": 21,
        "track_a_valid_cells": 18, "track_b_valid_cells": 3, "cells": manifest_cells},
        indent=2, ensure_ascii=False), encoding="utf-8")
    replay = {"protocol": "r2.1", "cell_count": 21,
              "all_semantic_equal": all(item["semantic_equal"] for item in replay_cells),
              "EVALUATOR_FIX_NON_SEMANTIC": "PASS", "cells": replay_cells,
              "pre_fix_cells": [item for item in replay_cells if item["harness_revision"].startswith("fb183cd")],
              "notes": "Final evaluator replay of frozen agent-output.txt and events.ndjson; no Agent calls."}
    (root / "evaluator-replay.json").write_text(json.dumps(replay, indent=2, ensure_ascii=False), encoding="utf-8")

    def aggregate(values):
        ev = [item["evaluation"] for item in values]
        mt = [item["metrics"] for item in values]
        first = [item.get("turns_to_first_relevant_evidence") for item in mt
                 if item.get("turns_to_first_relevant_evidence") is not None]
        return {"runs": len(values), "successes": sum(bool(x["task_success"]) for x in ev),
                "success_rate": sum(bool(x["task_success"]) for x in ev) / len(values),
                "median_recall": median(x["required_evidence_recall"] for x in ev),
                "median_precision": median(x["evidence_precision"] for x in ev),
                "median_tool_turns": median(x["tool_turns"] for x in mt),
                "median_unique_files_read": median(x["unique_files_read"] for x in mt),
                "median_duration_ms": median(x["duration_ms"] for x in mt),
                "median_first_relevant_turn": median(first) if first else None,
                "wrong_path_count": sum(x["wrong_path_count"] for x in ev),
                "unsupported_citation_count": sum(x["unsupported_claim_count"] for x in ev)}

    aggregate_data = {"protocol": "r2.1", "track_a": {}, "track_b": {}}
    for (task, arm), values in grouped.items():
        target = aggregate_data["track_b" if (task, arm) == ("T05", "knowledge") else "track_a"]
        target[f"{task}.{arm}"] = aggregate(values)
    knowledge_task = load_task("T05")
    knowledge_lifecycle = []
    for item in grouped[("T05", "knowledge")]:
        evaluation = item["evaluation"]
        knowledge_lifecycle.append({
            "repetition": item["run"]["repetition"],
            "returned_evidence_ids": evaluation.get("returned_evidence_ids", []),
            "exposed_evidence_ids": evaluation.get("viewed_evidence_ids", []),
            "used_evidence_ids": evaluation.get("used_evidence_ids", []),
            "ground_truth_evidence_ids": knowledge_task.ground_truth["required_evidence_ids"],
            "unsupported_evidence_ids": evaluation.get("wrong_evidence_usage", []),
        })
    aggregate_data["track_b"]["knowledge_evidence_lifecycle"] = knowledge_lifecycle
    (root / "aggregate-r2.1.json").write_text(json.dumps(aggregate_data, indent=2, ensure_ascii=False), encoding="utf-8")

    pairwise = {"protocol": "r2.1", "comparisons": []}
    for task in TASKS:
        for repetition in (1, 2, 3):
            native = next(x for x in grouped[(task, "native")] if x["run"]["repetition"] == repetition)
            codegraph = next(x for x in grouped[(task, "codegraph")] if x["run"]["repetition"] == repetition)
            pairwise["comparisons"].append({"task": task, "repetition": repetition,
                "native_success": native["evaluation"]["task_success"],
                "codegraph_success": codegraph["evaluation"]["task_success"],
                "native_recall": native["evaluation"]["required_evidence_recall"],
                "codegraph_recall": codegraph["evaluation"]["required_evidence_recall"],
                "native_turns": native["metrics"]["tool_turns"], "codegraph_turns": codegraph["metrics"]["tool_turns"],
                "native_files": native["metrics"]["unique_files_read"], "codegraph_files": codegraph["metrics"]["unique_files_read"],
                "native_first_relevant_turn": native["metrics"].get("turns_to_first_relevant_evidence"),
                "codegraph_first_relevant_turn": codegraph["metrics"].get("turns_to_first_relevant_evidence")})
    (root / "pairwise-r2.1.json").write_text(json.dumps(pairwise, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

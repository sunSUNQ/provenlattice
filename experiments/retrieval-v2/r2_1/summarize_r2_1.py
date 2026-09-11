from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


TASK_IDS = ("T01", "T03", "T05")


def _median(values: list[float | int | None]) -> float | None:
    usable = [value for value in values if value is not None]
    return statistics.median(usable) if usable else None


def _cell(root: Path, task: str, arm: str, repetition: int) -> dict:
    path = root / task / arm / f"r{repetition}"
    run = json.loads((path / "run.json").read_text(encoding="utf-8"))
    metrics = json.loads((path / "metrics.json").read_text(encoding="utf-8"))
    evaluation = json.loads((path / "evaluation.json").read_text(encoding="utf-8"))
    return {"run": run, "metrics": metrics, "evaluation": evaluation}


def _aggregate(cells: list[dict]) -> dict:
    evaluations = [cell["evaluation"] for cell in cells]
    metrics = [cell["metrics"] for cell in cells]
    return {
        "runs": len(cells),
        "successes": sum(bool(item["task_success"]) for item in evaluations),
        "success_rate": sum(bool(item["task_success"]) for item in evaluations) / len(cells),
        "median_recall": _median([item["required_evidence_recall"] for item in evaluations]),
        "median_precision": _median([item["evidence_precision"] for item in evaluations]),
        "median_tool_turns": _median([item["tool_turns"] for item in metrics]),
        "median_unique_files_read": _median([item["unique_files_read"] for item in metrics]),
        "median_time_to_first_relevant_evidence_ms": _median([
            item.get("time_to_first_relevant_evidence_ms") for item in metrics]),
        "median_turns_to_first_relevant_evidence": _median([
            item.get("turns_to_first_relevant_evidence") for item in metrics]),
        "wrong_path_count": sum(item["wrong_path_count"] for item in evaluations),
        "unsupported_citation_count": sum(item["unsupported_claim_count"] for item in evaluations),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize frozen R2.1 cells")
    parser.add_argument("--results", type=Path,
                        default=Path("experiments/retrieval-v2/r2_1/results"))
    parser.add_argument("--output", type=Path,
                        default=Path("experiments/retrieval-v2/r2_1/r2.1-results.json"))
    args = parser.parse_args()
    track_a = {}
    category_improvements = 0
    task_gate_values = []
    for task in TASK_IDS:
        native = _aggregate([_cell(args.results, task, "native", run) for run in (1, 2, 3)])
        codegraph = _aggregate([_cell(args.results, task, "codegraph", run) for run in (1, 2, 3)])
        efficiency_improved = (
            codegraph["median_tool_turns"] < native["median_tool_turns"]
            or codegraph["median_unique_files_read"] < native["median_unique_files_read"]
        )
        category_improvements += int(efficiency_improved)
        gate = (codegraph["success_rate"] >= native["success_rate"]
                and codegraph["median_recall"] >= native["median_recall"]
                and codegraph["wrong_path_count"] <= native["wrong_path_count"]
                and codegraph["unsupported_citation_count"] == 0)
        task_gate_values.append(gate)
        track_a[task] = {"native": native, "codegraph": codegraph,
                         "efficiency_improved": efficiency_improved,
                         "correctness_gate": gate}
    codegraph_gate = all(task_gate_values) and category_improvements >= 2

    knowledge_cells = [_cell(args.results, "T05", "knowledge", run) for run in (1, 2, 3)]
    knowledge = _aggregate(knowledge_cells)
    knowledge_gate = (knowledge["successes"] == 3 and knowledge["median_recall"] == 1.0
                      and knowledge["unsupported_citation_count"] == 0
                      and sum(cell["evaluation"]["wrong_evidence_count"]
                              for cell in knowledge_cells) == 0)
    result = {
        "protocol": "r2.1",
        "track_a": {"candidate_status": "POSITIVE CANDIDATE", "tasks": track_a,
                    "improved_task_categories": category_improvements,
                    "progression": "PASS" if codegraph_gate else "HOLD"},
        "track_b": {"audit_classification": "A. Query Bundle Gap",
                    "T05_knowledge": knowledge,
                    "wrong_evidence_count": sum(cell["evaluation"]["wrong_evidence_count"]
                                                for cell in knowledge_cells),
                    "progression": "PASS" if knowledge_gate else "HOLD"},
    }
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

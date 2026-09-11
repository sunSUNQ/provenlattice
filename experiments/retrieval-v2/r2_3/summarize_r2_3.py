from __future__ import annotations

"""Offline audit / aggregation / attribution for the frozen R2.3 experiment.

Read-only with respect to the frozen harness: it never calls an Agent, never
re-runs a cell, never re-scores an answer and never rewrites a raw cell. It only
reads the 27 frozen cells and emits the reviewed artifacts that the R2.3
protocol versions (manifest / aggregate / pairwise).

Mirrors the R2.1 precedent (summarize_r2_1.py + close_r2_1.py): raw Agent cells
stay local, reviewed manifests, aggregates and reports are versioned.

Statistics follow section 23 of the frozen protocol: n = 3 per Task x Arm, so
only median / min / max and task-level direction consistency are reported. No
p-value is computed and no significance is claimed.
"""

import argparse
import hashlib
import json
import statistics
from pathlib import Path

TASK_IDS = ("T01", "T03", "T05")
ARMS = ("native", "codegraph", "knowledge")
REPETITIONS = (1, 2, 3)
REQUIRED_ARTIFACTS = ("run.json", "events.ndjson", "agent-output.txt",
                      "metrics.json", "evaluation.json", "evaluation-v2.json")

EXPECTED_PROTOCOL = "r2.3"
EXPECTED_EVALUATOR = "r2.2-groundtruth-v2"
EXPECTED_REPO_SHA = "ae09e960c7291605dda52356cc0c2d45567fb53e"
EXPECTED_MODEL = "claude-sonnet-4-5-20250929"
EXPECTED_CLAUDE_VERSION = "2.1.268"

PROVENANCE_FIELDS = ("brpc_sha", "model_id", "claude_version", "ground_truth_v2_hash",
                     "evaluator_v2_version", "protocol_revision")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def median(values):
    usable = [value for value in values if value is not None]
    return statistics.median(usable) if usable else None


def spread(values) -> dict:
    usable = [value for value in values if value is not None]
    if not usable:
        return {"median": None, "min": None, "max": None, "values": list(values)}
    return {"median": statistics.median(usable), "min": min(usable),
            "max": max(usable), "values": list(values)}


def delta(a, b):
    """a - b with None propagation."""
    if a is None or b is None:
        return None
    return a - b


def direction(values) -> str:
    usable = [value for value in values if value is not None]
    if not usable:
        return "NO_DATA"
    if all(value > 0 for value in usable):
        return "INCREASE_CONSISTENT"
    if all(value < 0 for value in usable):
        return "DECREASE_CONSISTENT"
    if all(value == 0 for value in usable):
        return "NO_CHANGE"
    return "MIXED"


def cell_dir(results: Path, task: str, arm: str, repetition: int) -> Path:
    return results / task / arm / f"r{repetition}"


def load_cell(results: Path, task: str, arm: str, repetition: int, repo_root: Path) -> dict:
    path = cell_dir(results, task, arm, repetition)
    missing = [name for name in REQUIRED_ARTIFACTS if not (path / name).is_file()]
    if missing:
        raise SystemExit(f"missing artifacts in {path}: {missing}")
    run = read_json(path / "run.json")
    return {
        "task": task, "arm": arm, "repetition": repetition, "path": path,
        "run": run,
        "metrics": read_json(path / "metrics.json"),
        "evaluation": read_json(path / "evaluation-v2.json"),
        "evaluation_r1": read_json(path / "evaluation.json"),
    }


GRAPH_OPERATIONS = frozenset({
    "symbol", "definition", "callers", "callees", "references", "dependencies",
    "dependents", "subgraph", "shard", "impact", "explain-symbol", "explain-module",
    "trace-evidence",
})
KNOWLEDGE_OPERATIONS = frozenset({
    "document", "evidence", "related-code", "cross-layer", "implemented",
    "requirements", "find-related-code", "find-related-documents",
})
LOCAL_OPERATIONS = frozenset({"read", "search", "grep", "glob", "shell"})
ARM_OPERATIONS = {
    "native": LOCAL_OPERATIONS,
    "codegraph": LOCAL_OPERATIONS | GRAPH_OPERATIONS,
    "knowledge": LOCAL_OPERATIONS | GRAPH_OPERATIONS | KNOWLEDGE_OPERATIONS,
}


def arm_isolation(cell: dict) -> dict:
    """Section 10 arm-isolation gate, recomputed from the frozen raw events."""
    operations: list[str] = []
    evidence_ids: set[str] = set()
    text = (cell["path"] / "events.ndjson").read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        operations.append(str(value.get("operation", "unknown")).casefold())
        for item in value.get("evidence_ids") or []:
            evidence_ids.add(str(item).upper())
    arm = cell["arm"]
    allowed = ARM_OPERATIONS[arm]
    disallowed = sorted({item for item in operations if item not in allowed})
    knowledge_used = sorted({item for item in operations if item in KNOWLEDGE_OPERATIONS})
    graph_used = sorted({item for item in operations if item in GRAPH_OPERATIONS})
    cross_layer = sorted(item for item in evidence_ids if item.startswith("E-XLINK-"))
    if arm == "native":
        isolated = not knowledge_used and not graph_used and not evidence_ids
    elif arm == "codegraph":
        isolated = not knowledge_used and not cross_layer
    else:
        isolated = True
    return {
        "arm": arm,
        "operations": sorted(set(operations)),
        "disallowed_operations": disallowed,
        "knowledge_operations": knowledge_used,
        "graph_operations": graph_used,
        "cross_layer_evidence_used": cross_layer,
        "evidence_id_count": len(evidence_ids),
        "isolated": bool(isolated and not disallowed),
    }


def build_manifest(cells: list[dict], results: Path, repo_root: Path,
                   ground_truth_path: Path) -> dict:
    gt_hash = sha256_file(ground_truth_path)
    entries = []
    for cell in cells:
        run = cell["run"]
        path = cell["path"]
        artifacts = []
        for name in REQUIRED_ARTIFACTS:
            artifact = path / name
            artifacts.append({
                "path": str(artifact.relative_to(repo_root)).replace("\\", "/"),
                "sha256": sha256_file(artifact),
                "bytes": artifact.stat().st_size,
            })
        entries.append({
            "run_key": run.get("run_key"),
            "task": cell["task"], "arm": cell["arm"], "repetition": cell["repetition"],
            "status": run.get("status"),
            "task_success": cell["evaluation"].get("task_success"),
            "repo_sha": run.get("agent_actual_commit"),
            "expected_repo_sha": run.get("repo_commit"),
            "prompt_hash": run.get("prompt_hash"),
            "model_id": run.get("model_id"),
            "actual_model_id": run.get("actual_model_id"),
            "claude_version": run.get("claude_version"),
            "actual_claude_version": run.get("actual_claude_version"),
            "harness_revision": run.get("provenlattice_commit"),
            "protocol_revision": run.get("protocol_revision"),
            "ground_truth_v2_hash": run.get("ground_truth_v2_hash"),
            "evaluator_v2_version": run.get("evaluator_v2_version"),
            "git_status_before": run.get("git_status_before"),
            "git_status_after": run.get("git_status_after"),
            "policy_violations": run.get("policy_violations"),
            "tool_turns": run.get("tool_calls"),
            "duration_ms": run.get("duration_ms"),
            "environment": run.get("environment"),
            "artifacts": artifacts,
            "arm_isolation": arm_isolation(cell),
        })

    def distinct(field):
        values = {entry.get(field) for entry in entries}
        return sorted(value for value in values if value is not None)

    consistency = {
        "cell_count": len(entries),
        "expected_cell_count": len(TASK_IDS) * len(ARMS) * len(REPETITIONS),
        "brpc_sha": distinct("repo_sha"),
        "model_id": distinct("model_id"),
        "actual_model_id": distinct("actual_model_id"),
        "claude_version": distinct("claude_version"),
        "actual_claude_version": distinct("actual_claude_version"),
        "harness_revision": distinct("harness_revision"),
        "protocol_revision": distinct("protocol_revision"),
        "evaluator_v2_version": distinct("evaluator_v2_version"),
        "ground_truth_v2_hash": distinct("ground_truth_v2_hash"),
        "ground_truth_v2_hash_recomputed": gt_hash,
        "prompt_hashes": sorted({entry.get("prompt_hash") for entry in entries}),
        "all_status_completed": all(entry.get("status") == "completed" for entry in entries),
        "all_policy_violations_empty": all(not entry.get("policy_violations") for entry in entries),
        "all_repo_clean": all(not entry.get("git_status_before")
                              and not entry.get("git_status_after") for entry in entries),
        "arm_isolation_all": all(entry["arm_isolation"]["isolated"] for entry in entries),
    }
    checks = {
        "single_brpc_sha": len(consistency["brpc_sha"]) == 1
                           and consistency["brpc_sha"][0] == EXPECTED_REPO_SHA,
        "single_model": consistency["model_id"] == [EXPECTED_MODEL]
                        and consistency["actual_model_id"] == [EXPECTED_MODEL],
        "single_claude_version": consistency["claude_version"] == [EXPECTED_CLAUDE_VERSION]
                                 and consistency["actual_claude_version"] == [EXPECTED_CLAUDE_VERSION],
        "single_harness_revision": len(consistency["harness_revision"]) == 1,
        "single_protocol_revision": consistency["protocol_revision"] == [EXPECTED_PROTOCOL],
        "single_evaluator": consistency["evaluator_v2_version"] == [EXPECTED_EVALUATOR],
        "single_ground_truth": len(consistency["ground_truth_v2_hash"]) == 1
                               and consistency["ground_truth_v2_hash"][0] == gt_hash,
        "one_prompt_hash_per_task": len(consistency["prompt_hashes"]) == len(TASK_IDS),
        "all_completed": consistency["all_status_completed"],
        "all_repo_clean": consistency["all_repo_clean"],
        "no_policy_violations": consistency["all_policy_violations_empty"],
        "arm_isolation": consistency["arm_isolation_all"],
        "complete_grid": consistency["cell_count"] == consistency["expected_cell_count"],
    }
    return {
        "protocol": EXPECTED_PROTOCOL,
        "generated_from": "frozen raw cells (local, not versioned)",
        "results_dir": str(results),
        "cell_count": len(entries),
        "consistency": consistency,
        "integrity_checks": checks,
        "integrity_pass": all(checks.values()),
        "cells": entries,
    }


def evidence_utility(cell: dict, task_meta: dict) -> dict:
    evaluation = cell["evaluation"]
    metrics = cell["metrics"]
    returned = set(evaluation.get("returned_evidence_ids") or [])
    exposed = set(evaluation.get("exposed_evidence_ids") or [])
    used = set(evaluation.get("used_evidence_ids") or [])
    exact = {str(item).upper() for item in task_meta.get("required_evidence_ids") or []}
    alternatives = {str(item).upper() for item in task_meta.get("acceptable_alternative_ids") or []}
    supporting = {str(item).upper() for item in task_meta.get("supporting_evidence_ids") or []}
    invalid = {str(item).upper() for item in task_meta.get("invalid_evidence_ids") or []}
    accepted = exact | alternatives | supporting
    useful_used = used & accepted
    return {
        "returned_evidence": len(returned),
        "exposed_evidence": len(exposed),
        "used_evidence": len(used),
        "ground_truth_evidence": len(exact),
        "acceptable_alternative_evidence": len(alternatives),
        "supporting_evidence": len(supporting),
        "invalid_evidence": len(invalid),
        "ground_truth_used": len(used & exact),
        "acceptable_alternative_used": len(used & alternatives),
        "invalid_citation_count": int(evaluation.get("invalid_evidence_count") or 0),
        "unsupported_citation_count": int(evaluation.get("unsupported_citation_count") or 0),
        "returned_but_unused_evidence": int(metrics.get("returned_but_unused_evidence") or 0),
        "evidence_usage_rate": metrics.get("evidence_usage_rate"),
        "useful_evidence_density": (len(useful_used) / len(used)) if used else None,
        "used_but_not_returned": len(used - returned),
    }


def correctness(cell: dict) -> dict:
    evaluation = cell["evaluation"]
    return {
        "task_success": bool(evaluation.get("task_success")),
        "concept_recall": evaluation.get("concept_recall"),
        "exact_evidence_recall": evaluation.get("exact_evidence_recall"),
        "evidence_precision": evaluation.get("evidence_precision"),
        "wrong_path_count": int(evaluation.get("wrong_path_count") or 0),
        "invalid_evidence_count": int(evaluation.get("invalid_evidence_count") or 0),
        "unsupported_citation_count": int(evaluation.get("unsupported_citation_count") or 0),
        "exact_evidence_hits": len(evaluation.get("exact_evidence_hits") or []),
        "exact_evidence_misses": len(evaluation.get("exact_evidence_misses") or []),
        "concepts": evaluation.get("concepts") or [],
    }


def efficiency(cell: dict) -> dict:
    metrics = cell["metrics"]
    return {
        "tool_turns": metrics.get("tool_turns"),
        "read_calls": metrics.get("read_calls"),
        "grep_calls": metrics.get("grep_calls"),
        "glob_calls": metrics.get("glob_calls"),
        "shell_calls": metrics.get("shell_calls"),
        "graph_queries": metrics.get("graph_queries"),
        "knowledge_queries": metrics.get("knowledge_queries"),
        "unique_files_read": metrics.get("unique_files_read"),
        "total_file_chars_read": metrics.get("total_file_chars_read"),
        "total_tool_output_chars": metrics.get("total_tool_output_chars"),
        "time_to_first_relevant_evidence_ms": metrics.get("time_to_first_relevant_evidence_ms"),
        "turns_to_first_relevant_evidence": metrics.get("turns_to_first_relevant_evidence"),
        "duration_ms": metrics.get("duration_ms"),
        "input_tokens": metrics.get("input_tokens"),
        "output_tokens": metrics.get("output_tokens"),
        "cache_tokens": metrics.get("cache_tokens"),
        "total_tokens": metrics.get("total_tokens"),
    }


def build_aggregate(cells: list[dict], task_meta: dict) -> dict:
    aggregate = {"protocol": EXPECTED_PROTOCOL, "n_per_task_arm": len(REPETITIONS),
                 "statistics": "median/min/max only (n=3, no p-value, no significance claim)",
                 "task_arm": {}, "per_cell": {}}
    for task in TASK_IDS:
        for arm in ARMS:
            group = [cell for cell in cells if cell["task"] == task and cell["arm"] == arm]
            group.sort(key=lambda item: item["repetition"])
            correctness_rows = [correctness(cell) for cell in group]
            efficiency_rows = [efficiency(cell) for cell in group]
            utility_rows = [evidence_utility(cell, task_meta[task]) for cell in group]
            key = f"{task}.{arm}"
            aggregate["task_arm"][key] = {
                "task": task,
                "arm": arm,
                "runs": len(group),
                "successes": sum(row["task_success"] for row in correctness_rows),
                "success_rate": sum(row["task_success"] for row in correctness_rows) / len(group),
                "success_by_repetition": {cell["repetition"]: row["task_success"]
                                          for cell, row in zip(group, correctness_rows)},
                "correctness": {
                    field: spread([row[field] for row in correctness_rows])
                    for field in ("concept_recall", "exact_evidence_recall", "evidence_precision")
                },
                "correctness_sums": {
                    field: sum(row[field] for row in correctness_rows)
                    for field in ("wrong_path_count", "invalid_evidence_count",
                                  "unsupported_citation_count", "exact_evidence_hits",
                                  "exact_evidence_misses")
                },
                "efficiency": {
                    field: spread([row[field] for row in efficiency_rows])
                    for field in efficiency_rows[0]
                },
                "evidence_utility": {
                    field: (spread([row[field] for row in utility_rows])
                            if isinstance(utility_rows[0][field], (int, float, type(None)))
                            else None)
                    for field in utility_rows[0]
                },
            }
            for cell in group:
                aggregate["per_cell"][f"{task}.{arm}.r{cell['repetition']}"] = {
                    "correctness": correctness(cell),
                    "efficiency": efficiency(cell),
                    "evidence_utility": evidence_utility(cell, task_meta[task]),
                }
    return aggregate


COMPARISON_SECTIONS = (
    ("codegraph_vs_native", "codegraph", "native"),
    ("knowledge_vs_native", "knowledge", "native"),
    ("knowledge_vs_codegraph", "knowledge", "codegraph"),
)

SCALAR_METRICS = (
    ("task_success", "correctness", "task_success"),
    ("concept_recall", "correctness", "concept_recall"),
    ("exact_evidence_recall", "correctness", "exact_evidence_recall"),
    ("evidence_precision", "correctness", "evidence_precision"),
    ("wrong_path_count", "correctness", "wrong_path_count"),
    ("invalid_evidence_count", "correctness", "invalid_evidence_count"),
    ("unsupported_citation_count", "correctness", "unsupported_citation_count"),
    ("tool_turns", "efficiency", "tool_turns"),
    ("graph_queries", "efficiency", "graph_queries"),
    ("knowledge_queries", "efficiency", "knowledge_queries"),
    ("unique_files_read", "efficiency", "unique_files_read"),
    ("total_file_chars_read", "efficiency", "total_file_chars_read"),
    ("time_to_first_relevant_evidence_ms", "efficiency", "time_to_first_relevant_evidence_ms"),
    ("turns_to_first_relevant_evidence", "efficiency", "turns_to_first_relevant_evidence"),
    ("duration_ms", "efficiency", "duration_ms"),
    ("returned_but_unused_evidence", "evidence_utility", "returned_but_unused_evidence"),
    ("evidence_usage_rate", "evidence_utility", "evidence_usage_rate"),
    ("useful_evidence_density", "evidence_utility", "useful_evidence_density"),
)


def build_pairwise(cells: list[dict], task_meta: dict) -> dict:
    index = {(cell["task"], cell["arm"], cell["repetition"]): cell for cell in cells}

    def values(cell):
        return {
            "correctness": correctness(cell),
            "efficiency": efficiency(cell),
            "evidence_utility": evidence_utility(cell, task_meta[cell["task"]]),
        }

    pairwise = {"protocol": EXPECTED_PROTOCOL, "unit": "per task x repetition, plus medians",
                "note": "delta = treatment - reference; n=3, direction consistency reported, "
                        "no significance claimed",
                "comparisons": {}}
    for task in TASK_IDS:
        pairwise["comparisons"][task] = {}
        for label, treatment, reference in COMPARISON_SECTIONS:
            per_repetition = []
            for repetition in REPETITIONS:
                left = index[(task, treatment, repetition)]
                right = index[(task, reference, repetition)]
                left_values, right_values = values(left), values(right)
                row = {"repetition": repetition}
                for name, section, field in SCALAR_METRICS:
                    a = left_values[section].get(field)
                    b = right_values[section].get(field)
                    if isinstance(a, bool):
                        a = int(a)
                    if isinstance(b, bool):
                        b = int(b)
                    row[name] = delta(a, b)
                per_repetition.append(row)
            summary = {}
            for name, _section, _field in SCALAR_METRICS:
                series = [row[name] for row in per_repetition]
                summary[name] = {
                    "median_delta": median(series),
                    "values": series,
                    "direction": direction(series),
                }
            pairwise["comparisons"][task][label] = {
                "treatment": treatment, "reference": reference,
                "per_repetition": per_repetition, "summary": summary,
            }
    return pairwise


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit, aggregate and attribute frozen R2.3 cells")
    parser.add_argument("--results", type=Path, default=Path("experiments/retrieval-v2/r2_3/results"))
    parser.add_argument("--tasks", type=Path, default=Path("experiments/retrieval-v2/r2_1/tasks"))
    parser.add_argument("--ground-truth", type=Path,
                        default=Path("experiments/retrieval-v2/evaluator-v2/ground-truth-v2/ground-truth-v2.json"))
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    results = args.results
    if not results.is_absolute():
        results = (repo_root / results).resolve()
    task_meta = {task_id: read_json(args.tasks / f"{task_id}.json")["ground_truth"]
                 for task_id in TASK_IDS}
    ground_truth_tasks = {item["task_id"]: item
                          for item in read_json(args.ground_truth)["tasks"]}
    for task_id, item in ground_truth_tasks.items():
        task_meta.setdefault(task_id, {}).update(item)

    cells = [load_cell(results, task, arm, repetition, repo_root)
             for task in TASK_IDS for arm in ARMS for repetition in REPETITIONS]

    manifest = build_manifest(cells, results, repo_root, args.ground_truth)
    aggregate = build_aggregate(cells, task_meta)
    pairwise = build_pairwise(cells, task_meta)

    (results / "manifest-r2.3.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (results / "aggregate-r2.3.json").write_text(
        json.dumps(aggregate, indent=2, ensure_ascii=False), encoding="utf-8")
    (results / "pairwise-r2.3.json").write_text(
        json.dumps(pairwise, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"cells": len(cells),
                      "integrity_pass": manifest["integrity_pass"],
                      "failed_checks": [name for name, ok in manifest["integrity_checks"].items() if not ok],
                      "success_matrix": {key: value["successes"]
                                         for key, value in aggregate["task_arm"].items()}},
                     indent=2, ensure_ascii=False))
    return 0 if manifest["integrity_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

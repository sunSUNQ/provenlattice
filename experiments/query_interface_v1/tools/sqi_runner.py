"""SQI-V1 qualification runner.

Current phase: IMPLEMENTATION SMOKE ONLY.

  * reads the frozen task set SQI-T01..T06 (task freeze seal applies);
  * executes each task's frozen sqi_chain through the SQI adapter on the
    task's frozen database;
  * records per call: raw envelope, schema validation, semantic validation,
    budget accounting, truncation, evidence ids, and a double-execution
    determinism check;
  * arm support: --arm sqi executes the interface; --arm native is accepted
    for protocol completeness but is NOT executed in implementation-smoke
    (a native arm run is part of formal qualification, not of this phase);
  * emits run_kind=implementation-smoke records only. This runner refuses to
    emit qualification verdicts; formal Native-vs-SQI runs are a later phase
    with their own frozen protocol extension.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINE_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from sqi_adapter import SQIAdapter  # noqa: E402
from sqi_validator import validate_envelope  # noqa: E402

TASKS_DIR = LINE_ROOT / "tasks"
RESULTS_DIR = LINE_ROOT / "results"
# frozen databases live beside the provenlattice checkout (workspace root)
WORKSPACE_ROOT = LINE_ROOT.parents[2]
RUN_KIND = "implementation-smoke"
RUNNER_VERSION = "sqi-runner-v1-implementation-smoke"


def resolve_database(path_value: str) -> str:
    path = Path(path_value)
    if path.is_absolute() and path.exists():
        return str(path)
    for base in (WORKSPACE_ROOT, LINE_ROOT.parents[1], Path.cwd()):
        candidate = base / path
        if candidate.exists():
            return str(candidate)
    raise RuntimeError(f"frozen database not found: {path_value}")


def canonical(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def determinism_view(envelope: dict) -> str:
    """Canonical bytes for the double-execution check. Contract R2 allows
    exactly one non-deterministic envelope field: query_time_ms."""
    view = {key: value for key, value in envelope.items() if key != "query_time_ms"}
    return canonical(view)


def load_tasks() -> list[dict]:
    tasks = []
    for index in range(1, 7):
        path = TASKS_DIR / f"SQI-T0{index}.json"
        task = json.loads(path.read_text(encoding="utf-8"))
        if task.get("task_id") != f"SQI-T0{index}":
            raise RuntimeError(f"task id mismatch in {path}")
        tasks.append(task)
    return tasks


def build_steps(task: dict) -> list[dict]:
    """Frozen per-task step plans. Params come from the task's frozen ground
    truth or from earlier step outputs (deterministic chaining)."""
    tid = task["task_id"]
    gt = task["ground_truth"]
    if tid == "SQI-T01":
        return [{"call": "symbol.lookup",
                 "params": {"name": gt["qualified_name"], "kind": gt["kind"],
                            "path_prefix": gt["file"]}}]
    if tid == "SQI-T02":
        return [{"call": "symbol.lookup", "params": {"name": gt["qualified_name"]}},
                {"call": "symbol.callers",
                 "params": {"symbol": {"from": 0, "pick": gt["symbol_id"]}}}]
    if tid == "SQI-T03":
        return [{"call": "symbol.lookup", "params": {"name": "NumUnsetBytes"}},
                {"call": "symbol.references",
                 "params": {"symbol": {"from": 0, "pick": gt["symbol_id"]}}}]
    if tid == "SQI-T04":
        return [{"call": "impact.frontier",
                 "params": {"changed_shard_paths": gt["changed_shard_paths"],
                            "threshold": gt["threshold"]}}]
    if tid == "SQI-T05":
        document = next(item["value"] for item in gt["required_evidence"]
                        if item["type"] == "document_section")
        return [{"call": "code.related", "params": {"document": document}}]
    if tid == "SQI-T06":
        return [{"call": "bundle.explain",
                 "params": {"symbol": gt["symbol_query"], "budget": gt["budget"]}}]
    raise RuntimeError(f"no frozen step plan for {tid}")


def resolve_param(value: object, outputs: list[dict]) -> object:
    if isinstance(value, dict) and "from" in value:
        step = outputs[value["from"]]
        pick = value.get("pick")
        for row in step["envelope"]["data"]:
            if row.get("id") == pick:
                return pick
        matches = [row for row in step["envelope"]["data"]
                   if row.get("qualified_name") == pick]
        if matches:
            return matches[0]["id"]
        raise RuntimeError(f"chained param {pick!r} not found in step output")
    if isinstance(value, dict):
        return {key: resolve_param(item, outputs) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_param(item, outputs) for item in value]
    return value


def execute_call(adapter: SQIAdapter, call: str, params: dict) -> dict:
    if call == "symbol.lookup":
        return adapter.symbol_lookup(params["name"], kind=params.get("kind"),
                                     path_prefix=params.get("path_prefix"),
                                     budget=params.get("budget"))
    if call == "symbol.callers":
        return adapter.symbol_callers(params["symbol"], budget=params.get("budget"))
    if call == "symbol.callees":
        return adapter.symbol_callees(params["symbol"], budget=params.get("budget"))
    if call == "symbol.references":
        return adapter.symbol_references(params["symbol"],
                                         status=params.get("status"),
                                         budget=params.get("budget"))
    if call == "impact.frontier":
        return adapter.impact_frontier(params["changed_shard_paths"],
                                       threshold=params.get("threshold", 8),
                                       budget=params.get("budget"))
    if call == "code.related":
        return adapter.code_related(params["document"], budget=params.get("budget"))
    if call == "bundle.explain":
        return adapter.bundle_explain(params["symbol"], budget=params.get("budget"))
    raise RuntimeError(f"unknown canonical call {call}")


def evidence_fact_ids(envelope: dict) -> list[str]:
    """Deterministic fact identities backing the returned evidence
    (edge ids, reference row ids, ...) used for frozen-anchor crosschecks."""
    out = []
    for item in envelope.get("evidence") or []:
        fact_id = (item.get("metadata") or {}).get("fact_id")
        if fact_id:
            out.append(fact_id)
    return sorted(out)


def verify_anchors(task: dict, outputs: list[dict]) -> dict:
    """Stage-2 smoke anchor verification against the frozen task ground truth.
    Machinery-level correctness only - no task-effectiveness verdict."""
    tid = task["task_id"]
    gt = task["ground_truth"]
    checks: dict[str, object] = {}
    if tid == "SQI-T01":
        lookup = outputs[0]["envelope"]
        hit = [row for row in lookup["data"] if row.get("id") == gt["symbol_id"]]
        checks["symbol_id_returned"] = bool(hit)
        checks["declaration_line"] = hit[0]["start_line"] if hit else None
        row_file = (hit[0].get("file_path")
                    if hit and hit[0].get("file_path")
                    else (hit[0].get("metadata") or {}).get("relative_path")
                    if hit else None)
        checks["file_matches"] = row_file == gt["file"]
        checks["definition_evidence_kind"] = bool(lookup["evidence"]) and \
            lookup["evidence"][0]["kind"] == "CODE_DEFINITION"
    elif tid == "SQI-T02":
        callers = outputs[1]["envelope"]
        fact_ids = evidence_fact_ids(callers)
        frozen_edges = [c["edge_id"] for c in gt["callers"]]
        checks["frozen_edge_ids_returned"] = sorted(set(fact_ids) & set(frozen_edges))
        checks["frozen_edge_count_met"] = len(set(fact_ids) & set(frozen_edges)) == len(frozen_edges)
        names = {row.get("qualified_name") for row in callers["data"]}
        checks["production_callers_covered"] = sorted(
            name for name in gt["required_production_callers"] if name in names)
    elif tid == "SQI-T03":
        refs = outputs[1]["envelope"]
        frozen_pairs = {(r["file_id"], r["line"]) for r in gt["resolved_references"]}
        returned_pairs = {(r.get("file_id"), r.get("start_line"))
                          for r in refs["data"]
                          if r.get("resolved_symbol_id") == gt["symbol_id"]}
        checks["frozen_ref_locations_returned"] = len(frozen_pairs & returned_pairs)
        checks["frozen_ref_count_exact"] = returned_pairs == frozen_pairs
        checks["frozen_e_ref_ids_returned"] = sorted(
            set(gt["returned_evidence_ids"]) & set(refs["returned_evidence_ids"]))
    elif tid == "SQI-T04":
        frontier = outputs[0]["envelope"]
        meta = frontier["result_meta"]
        checks["frontier_size"] = meta["frontier_size"]
        checks["frontier_size_matches"] = meta["frontier_size"] == gt["directly_affected_count"]
        checks["boundary_edges_total"] = meta["boundary_edges_total"]
        checks["boundary_edges_total_matches"] = \
            meta["boundary_edges_total"] == gt["boundary_edge_count"]
        checks["wide_impact"] = meta["wide_impact"]
        checks["truncation_declared"] = frontier["truncation"]["truncated"]
    elif tid == "SQI-T05":
        related = outputs[0]["envelope"]
        target = gt["required_evidence"][1]["value"]
        checks["target_symbol_returned"] = any(
            row.get("qualified_name") == target for row in related["data"])
        checks["cross_layer_evidence"] = [e["evidence_id"] for e in related["evidence"]
                                          if e["kind"] == "CROSS_LAYER_LINK"]
    elif tid == "SQI-T06":
        bundle = outputs[0]["envelope"]
        checks["evidence_within_budget"] = \
            bundle["returned_evidence_count"] <= gt["budget"]["max_evidence"]
        checks["symbols_within_budget"] = \
            len(bundle["data"].get("related_entities", [])) <= gt["budget"]["max_symbols"]
        checks["truncation_declared"] = bundle["truncation"]["truncated"]
        checks["omitted_counts_present"] = bundle["truncation"]["omitted_counts"]
    return checks


def run_task(task: dict, arm: str) -> dict:
    started = time.perf_counter()
    record: dict = {
        "task_id": task["task_id"],
        "run_kind": RUN_KIND,
        "arm": arm,
        "repository": task["repository"],
        "commit": task["commit"],
        "database": task["database"],
        "sqi_version": "SQI-V1",
        "runner_version": RUNNER_VERSION,
        "native_arm_note": ("native arm is defined by the frozen contract but is "
                            "not executed in implementation-smoke; it requires the "
                            "frozen formal-phase agent protocol"),
        "steps": [],
    }
    if arm == "native":
        record["status"] = "NOT_EXECUTED_IN_IMPLEMENTATION_SMOKE"
        return record
    code_database = resolve_database(task["code_database"]) \
        if task.get("code_database") else None
    with SQIAdapter(resolve_database(task["database"]), task["commit"],
                    code_database=code_database) as adapter:
        outputs: list[dict] = []
        for index, step in enumerate(build_steps(task)):
            params = resolve_param(step["params"], outputs)
            envelope = execute_call(adapter, step["call"], params)
            replay = execute_call(adapter, step["call"], params)
            deterministic = determinism_view(envelope) == determinism_view(replay)
            ok, errors = validate_envelope(envelope, expected_commit=task["commit"])
            record["steps"].append({
                "step": index,
                "call": step["call"],
                "params": params,
                "envelope": envelope,
                "response_bytes": len(json.dumps(envelope, ensure_ascii=False)),
                "query_latency_ms": envelope.get("query_time_ms"),
                "schema_valid": ok,
                "semantic_errors": errors,
                "budget": envelope.get("budget"),
                "truncation": envelope.get("truncation"),
                "returned_evidence_ids": envelope.get("returned_evidence_ids"),
                "evidence_fact_ids": evidence_fact_ids(envelope),
                "source_verification_actions": (
                    "no live agent in implementation-smoke; policy block in "
                    "envelope marks the assertion classes that require source "
                    "verification (contract S8)"),
                "deterministic_double_execution": deterministic,
            })
            outputs.append({"call": step["call"], "envelope": envelope})
    record["anchor_verification"] = verify_anchors(task, outputs)
    anchors_ok = all(bool(value) for value in record["anchor_verification"].values())
    record["anchor_verification_pass"] = bool(anchors_ok)
    machinery_ok = all(
        step["schema_valid"] and not step["semantic_errors"]
        and step["deterministic_double_execution"] for step in record["steps"])
    record["machinery_pass"] = machinery_ok
    record["status"] = "PASS" if (machinery_ok and anchors_ok) else "FAIL"
    if record["status"] == "FAIL":
        record["failure_attribution"] = {
            "machinery": None if machinery_ok
            else "schema/semantic/determinism failure (SQI implementation)",
            "anchors": None if anchors_ok
            else "frozen anchor verification mismatch (fixture, adapter, or data)",
        }
    record["duration_s"] = round(time.perf_counter() - started, 3)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("sqi", "native"), default="sqi")
    parser.add_argument("--mode", choices=("implementation-smoke", "formal"),
                        default="implementation-smoke")
    parser.add_argument("--output", default=None,
                        help="summary output path (default results/implementation-smoke/)")
    args = parser.parse_args()
    if args.mode != "implementation-smoke":
        parser.error("formal qualification is not authorized from this runner; "
                     "formal Native-vs-SQI runs require the frozen formal protocol")
    tasks = load_tasks()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_id = f"SQI-SMOKE-{stamp}-{uuid.uuid4().hex[:6]}"
    out_dir = Path(args.output) if args.output else RESULTS_DIR / "implementation-smoke" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    records = [run_task(task, args.arm) for task in tasks]
    passed = sum(1 for record in records if record["status"] == "PASS")
    summary = {
        "schema": "SQI_IMPLEMENTATION_SMOKE_SUMMARY_V1",
        "schema_version": 1,
        "run_id": run_id,
        "run_kind": RUN_KIND,
        "arm": args.arm,
        "sqi_version": "SQI-V1",
        "runner_version": RUNNER_VERSION,
        "task_freeze_seal": "../tasks referenced via contract freeze seal",
        "qualification_verdict": None,
        "no_qualification_verdict_reason": (
            "implementation-smoke validates interface machinery only "
            "(schema validity, determinism, budget compliance, evidence binding, "
            "truncation honesty); Native-vs-SQI task effectiveness is a later "
            "frozen phase"),
        "tasks_total": len(tasks),
        "tasks_passed": passed,
        "tasks_failed": len(tasks) - passed,
        "status": "PASS" if passed == len(tasks) else "FAIL",
        "records": [],
    }
    for task, record in zip(tasks, records):
        record_path = out_dir / f"{task['task_id']}.json"
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n",
                               encoding="utf-8")
        summary["records"].append({
            "task_id": task["task_id"], "status": record["status"],
            "record": record_path.name,
            "sha256": hashlib.sha256(record_path.read_bytes()).hexdigest()})
    summary_path = out_dir / "implementation-smoke-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("run_id", "run_kind", "arm", "tasks_total", "tasks_passed",
                       "tasks_failed", "status")}, indent=1))
    print("summary:", summary_path)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

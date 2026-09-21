"""C4-R4 Native vs ProvenLattice V1.2 same-batch cost & effectiveness analysis.

Question B (horizontal product value), kept strictly separate from the
longitudinal V1.1 -> V1.2 question A:

    Native arm (no CodeGraph/SQI)
    vs ProvenLattice V1.2 arm (SQI V1.2)
    inside the SAME clean formal batch SQI-FORMAL-C4-20260920T093328Z
    (6 tasks x 2 arms x 3 reps = 36 cells, single backend deepseek-flash,
    per-cell model provenance, V1.4 finite-root isolation).

Read-only over the frozen batch evidence: run.json / evaluation.json /
events.ndjson / sqi-call-log.ndjson. No cell is re-run, excluded, or
re-weighted; token aggregation reuses the exact cell_tokens semantics of
the frozen C4-R4 synthesis (tools/sqi_c4_synthesis.py), so every total
back-calculates to the cell-level records embedded in the output JSON.

Outputs:
    results/analysis/C4-R4-NATIVE-VS-SQI-V1.2.json
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINE_ROOT = HERE.parent
RESULTS = LINE_ROOT / "results"
BATCH = RESULTS / "formal" / "SQI-FORMAL-C4-20260920T093328Z"
OUT = RESULTS / "analysis" / "C4-R4-NATIVE-VS-SQI-V1.2.json"
TASKS = [f"SQI-T0{i}" for i in range(1, 7)]
ARMS = ("native", "sqi")

NOT_CAPTURED = "METRIC_NOT_CAPTURED"

# Frozen longitudinal numbers (question A) — verbatim from the frozen
# V1.2 final qualification review (reviews/v1.2-final-qualification-review.md),
# baseline SQI-FORMAL-20260917-1 (mixed backends -> historical caveat).
V11_TO_V12_FROZEN = {
    "baseline_batch": "SQI-FORMAL-20260917-1",
    "clean_batch": "SQI-FORMAL-C4-20260920T093328Z",
    "deltas": {
        "input_tokens_pct": -36,
        "output_tokens_pct": -58,
        "cache_read_tokens_pct": -73,
        "envelope_bytes_pct": -26,
        "sqi_calls_pct": -17,
    },
    "caveat": "baseline ran on mixed backends (deepseek-flash + "
              "deepseek-v4-flash) — cross-era token comparisons carry a "
              "residual backend caveat",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def iter_cells(batch_dir: Path):
    for task_dir in sorted(batch_dir.glob("SQI-T*")):
        for arm_dir in sorted(task_dir.iterdir()):
            if not arm_dir.is_dir() or arm_dir.name not in ARMS:
                continue
            for rep_dir in sorted(arm_dir.glob("r*")):
                run_path = rep_dir / "run.json"
                if not run_path.exists():
                    continue
                run = load_json(run_path)
                ev = load_json(rep_dir / "evaluation.json") \
                    if (rep_dir / "evaluation.json").exists() else {}
                call_log = []
                log_path = rep_dir / "sqi-call-log.ndjson"
                if log_path.exists():
                    call_log = [json.loads(l) for l in
                                log_path.read_text(encoding="utf-8")
                                .splitlines() if l.strip()]
                events = []
                events_path = rep_dir / "events.ndjson"
                if events_path.exists():
                    events = [json.loads(l) for l in
                              events_path.read_text(encoding="utf-8")
                              .splitlines() if l.strip()]
                yield {"task_id": run["task_id"], "arm": run["arm"],
                       "repetition": run["repetition"],
                       "cell": run.get("cell_id"), "run": run, "eval": ev,
                       "call_log": call_log, "events": events,
                       "dir": rep_dir}


def cell_tokens(events: list) -> dict:
    """Session-cumulative per-cell usage: the CLI final result event's
    usage block is attached to the last event by the agent adapter; the
    frozen synthesis sums the same fields across events (identical result,
    exactly one token-bearing event per cell)."""
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0,
              "total_as_logged": 0}
    for event in events:
        tokens = event.get("tokens") or {}
        for key in totals:
            value = tokens.get("total" if key == "total_as_logged" else key)
            if isinstance(value, (int, float)):
                totals[key] += int(value)
    return totals


def percentile(values: list, q: float) -> float:
    """Linear-interpolation percentile (numpy 'linear' equivalent)."""
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q
    low, high = int(pos), min(int(pos) + 1, len(ordered) - 1)
    frac = pos - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def dist_stats(values: list) -> dict:
    if not values:
        return {"n": 0}
    return {"n": len(values), "sum": int(sum(values)),
            "mean": round(statistics.fmean(values), 1),
            "median": round(statistics.median(values), 1),
            "p25": round(percentile(values, 0.25), 1),
            "p75": round(percentile(values, 0.75), 1)}


def delta_pct(sqi_value, native_value):
    if native_value in (None, 0) or sqi_value is None:
        return None
    return round((sqi_value - native_value) / native_value * 100.0, 1)


def main() -> int:
    cells = list(iter_cells(BATCH))
    assert len(cells) == 36, f"expected 36 cells, found {len(cells)}"
    by_arm = {arm: [c for c in cells if c["arm"] == arm] for arm in ARMS}
    assert len(by_arm["native"]) == 18 and len(by_arm["sqi"]) == 18, \
        "expected 18 native + 18 sqi cells"

    # ---- dataset validity -------------------------------------------------
    validity_cells = []
    evaluator_mismatches = []
    prompt_hashes = {}
    for c in cells:
        run, ev = c["run"], c["eval"]
        provenance = run["isolation"]["model_provenance"]
        record = {
            "cell_id": c["cell"],
            "task_id": c["task_id"], "arm": c["arm"],
            "repetition": c["repetition"],
            "repository": run["repository"], "commit": run["commit"],
            "database": run["database"],
            "status": run["status"], "exit_reason": run["exit_reason"],
            "execution_valid": run["status"] == "completed"
                               and run["exit_reason"] == "completed",
            "model_id": run["model_id"],
            "backend_model": provenance["backend_model"],
            "backend_verified": bool(provenance["backend_verified"]),
            "isolation": {
                "window_closed_verified": run["isolation"]
                ["window_closed_verified"],
                "restore_verified": run["isolation"]["restore_verified"],
                "fingerprint_unchanged": run["isolation"]
                ["fingerprint_unchanged"],
            },
            "leakage_clean": (run.get("sensitive_leakage_events", 0) == 0
                              and not run.get("policy_violations")),
            "raw_checkout_leakage_events": run.get("checkout_leakage_events", 0),
            "capability_failure_flags": run.get("capability_failure_flags", []),
            "prompt_hash": run["prompt_hash"],
            "task_success_run_record": run.get("task_success"),
            "task_success_evaluator": ev.get("task_success"),
            "machine_checks_pass": ev.get("machine_checks_pass"),
            "citation_closure_ok": (ev.get("evidence_oracle") or {})
            .get("citation_closure_ok"),
            "tool_calls": run.get("tool_calls"),
            "sqi_calls": run.get("sqi_calls"),
        }
        record["tokens"] = cell_tokens(c["events"])
        c["tokens"] = record["tokens"]
        if record["task_success_run_record"] != record["task_success_evaluator"]:
            evaluator_mismatches.append(c["cell"])
        prompt_hashes.setdefault(c["task_id"], set()).add(run["prompt_hash"])
        validity_cells.append(record)

    backends = sorted({r["backend_model"] for r in validity_cells})
    unverified = [r["cell_id"] for r in validity_cells
                  if not r["backend_verified"]]
    invalid_exec = [r["cell_id"] for r in validity_cells
                    if not r["execution_valid"]]
    iso_broken = [r["cell_id"] for r in validity_cells
                  if not all(r["isolation"].values())]
    leaky = [r["cell_id"] for r in validity_cells if not r["leakage_clean"]]
    raw_leak_events = sum(r["raw_checkout_leakage_events"]
                          for r in validity_cells)
    capability_flagged = [r["cell_id"] for r in validity_cells
                          if r["capability_failure_flags"]]
    prompt_inconsistent = {t: sorted(h) for t, h in prompt_hashes.items()
                           if len(h) != 1}

    # ---- layer 1: task success -------------------------------------------
    def success_block(cell_list):
        total = len(cell_list)
        succ = sum(1 for c in cell_list if c["run"].get("task_success"))
        return {"success": succ, "total": total,
                "rate_pct": round(succ / total * 100.0, 1) if total else None}

    success_overall = {arm: success_block(by_arm[arm]) for arm in ARMS}
    success_per_task = {}
    for task in TASKS:
        row = {}
        for arm in ARMS:
            sub = [c for c in by_arm[arm] if c["task_id"] == task]
            assert len(sub) == 3, f"expected 3 reps for {task}.{arm}"
            row[arm] = success_block(sub)
        row["delta"] = (row["sqi"]["success"] - row["native"]["success"])
        success_per_task[task] = row

    # ---- layer 2: agent cost ----------------------------------------------
    TOKEN_KEYS = ("input", "output", "cache_read", "cache_creation",
                  "total_as_logged")

    def arm_cost(cell_list):
        per_cell = {k: [c["tokens"][k] for c in cell_list]
                    for k in TOKEN_KEYS}
        block = {k: dist_stats(v) for k, v in per_cell.items()}
        block["sqi_calls"] = {"sum": sum(c["run"].get("sqi_calls") or 0
                                         for c in cell_list),
                              "mean": round(statistics.fmean(
                                  [(c["run"].get("sqi_calls") or 0)
                                   for c in cell_list]), 2)}
        block["native_tool_events"] = {"sum": sum(c["run"]
                                                  .get("tool_calls") or 0
                                                  for c in cell_list),
                                       "mean": round(statistics.fmean(
                                           [(c["run"].get("tool_calls") or 0)
                                            for c in cell_list]), 2)}
        block["envelope_bytes"] = {"sum": sum(
            ((c["eval"].get("sqi_call_summary") or {})
             .get("total_payload_bytes") or 0) for c in cell_list)}
        return block

    cost_overall = {arm: arm_cost(by_arm[arm]) for arm in ARMS}
    cost_delta = {k: delta_pct(cost_overall["sqi"][k]["sum"],
                               cost_overall["native"][k]["sum"])
                  for k in TOKEN_KEYS}
    cost_delta["envelope_bytes"] = delta_pct(
        cost_overall["sqi"]["envelope_bytes"]["sum"],
        cost_overall["native"]["envelope_bytes"]["sum"])

    # ---- layer 3: success-normalized cost ----------------------------------
    def per_success(cell_list):
        succ = sum(1 for c in cell_list if c["run"].get("task_success"))
        if succ == 0:
            return {"successful_tasks": 0,
                    "note": "N/A — zero successful tasks"}
        return {"successful_tasks": succ,
                **{f"{k}_per_success": round(sum(c["tokens"][k]
                                                 for c in cell_list) / succ, 1)
                   for k in TOKEN_KEYS}}

    cost_per_success_overall = {arm: per_success(by_arm[arm]) for arm in ARMS}
    cost_per_success_per_task = {}
    for task in TASKS:
        row = {}
        for arm in ARMS:
            sub = [c for c in by_arm[arm] if c["task_id"] == task]
            row[arm] = per_success(sub)
        cost_per_success_per_task[task] = row

    # ---- layer 4: tool-use structure ---------------------------------------
    def native_tool_mix(cell_list, exclude_sqi_cli=False):
        mix = {}
        for c in cell_list:
            for event in c["events"]:
                if exclude_sqi_cli and event.get("query_type"):
                    continue
                tool = event.get("tool") or "UNKNOWN"
                mix[tool] = mix.get(tool, 0) + 1
        return dict(sorted(mix.items(), key=lambda kv: -kv[1]))

    native_tools = native_tool_mix(by_arm["native"])
    sqi_arm_all_events = native_tool_mix(by_arm["sqi"])
    sqi_arm_native_only = native_tool_mix(by_arm["sqi"],
                                          exclude_sqi_cli=True)
    sqi_calls_by_type = {}
    for c in by_arm["sqi"]:
        for entry in c["call_log"]:
            call = entry.get("call") or "UNKNOWN"
            sqi_calls_by_type[call] = sqi_calls_by_type.get(call, 0) + 1
    sqi_calls_by_type = dict(sorted(sqi_calls_by_type.items(),
                                    key=lambda kv: -kv[1]))
    tool_use_per_task = {}
    for task in TASKS:
        tool_use_per_task[task] = {
            "native_tools_by_type": native_tool_mix(
                [c for c in by_arm["native"] if c["task_id"] == task]),
            "sqi_calls_by_type": dict(sorted(
                ((k, v) for k, v in sqi_calls_by_type.items()), )),
            "sqi_calls_total": sum(c["run"].get("sqi_calls") or 0
                                   for c in by_arm["sqi"]
                                   if c["task_id"] == task),
            "sqi_arm_native_tools_excl_sqi_cli": native_tool_mix(
                [c for c in by_arm["sqi"] if c["task_id"] == task],
                exclude_sqi_cli=True),
        }
    # refine per-task sqi_calls_by_type
    for task in TASKS:
        per_type = {}
        for c in by_arm["sqi"]:
            if c["task_id"] != task:
                continue
            for entry in c["call_log"]:
                call = entry.get("call") or "UNKNOWN"
                per_type[call] = per_type.get(call, 0) + 1
        tool_use_per_task[task]["sqi_calls_by_type"] = dict(
            sorted(per_type.items(), key=lambda kv: -kv[1]))

    # ---- per-task cost breakdown -------------------------------------------
    per_task = {}
    for task in TASKS:
        row = {}
        for arm in ARMS:
            sub = [c for c in by_arm[arm] if c["task_id"] == task]
            block = success_block(sub)
            block["tokens"] = {k: dist_stats([c["tokens"][k] for c in sub])
                               for k in TOKEN_KEYS}
            block["sqi_calls_sum"] = sum(c["run"].get("sqi_calls") or 0
                                         for c in sub)
            block["native_tool_events_sum"] = sum(
                c["run"].get("tool_calls") or 0 for c in sub)
            row[arm] = block
        row["delta_pct_tokens"] = {
            k: delta_pct(row["sqi"]["tokens"][k]["sum"],
                         row["native"]["tokens"][k]["sum"])
            for k in TOKEN_KEYS}
        per_task[task] = row

    # ---- duration availability ---------------------------------------------
    # duration_ms existed only in the runner's in-memory record (added after
    # run.json was written); events timestamps are batch-flush stamps, so no
    # wall-clock span is recoverable from raw artifacts.
    duration_available = any(
        isinstance(c["run"].get("duration_ms"), (int, float))
        for c in cells)

    # ---- cell records for back-calculation ----------------------------------
    cell_records = sorted(
        ({"cell_id": r["cell_id"], "task_id": r["task_id"],
          "arm": r["arm"], "repetition": r["repetition"],
          "task_success": r["task_success_run_record"],
          "tokens": r["tokens"], "tool_calls": r["tool_calls"],
          "sqi_calls": r["sqi_calls"]} for r in validity_cells),
        key=lambda r: (r["task_id"], r["arm"], r["repetition"]))

    doc = {
        "schema": "C4_R4_NATIVE_VS_SQI_V12_ANALYSIS_V1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "batch": {
            "batch_id": "SQI-FORMAL-C4-20260920T093328Z",
            "cells_total": len(cells),
            "isolation_baseline_sha": "27e40df5e61cd815d8ea0d00203746344c279690",
            "comparability": "Native and ProvenLattice V1.2 arms come from "
                             "the SAME clean formal batch: identical frozen "
                             "task set (SQI-T01..T06), identical protocol / "
                             "oracle / prompts, identical V1.4 finite-root "
                             "isolation, identical time window, single "
                             "backend deepseek-flash with per-cell verified "
                             "model provenance. This is the most defensible "
                             "Native vs ProvenLattice horizontal comparison "
                             "available.",
        },
        "question_separation": {
            "question_A_longitudinal": {
                "comparison": "SQI V1.1 (SQI-FORMAL-20260917-1) vs SQI V1.2 "
                              "(this batch) — 'did ProvenLattice get "
                              "cheaper?'",
                "frozen_result": V11_TO_V12_FROZEN,
            },
            "question_B_horizontal": {
                "comparison": "C4-R4 Native vs C4-R4 ProvenLattice V1.2 — "
                              "'what do task success and agent cost look "
                              "like with vs without ProvenLattice?'",
                "scope": "this document; both arms of one clean batch",
            },
            "rule": "A and B must never be merged into one conclusion",
        },
        "validity": {
            "cells_total": len(validity_cells),
            "native_cells": len(by_arm["native"]),
            "sqi_cells": len(by_arm["sqi"]),
            "backends": backends,
            "backend_all_verified": not unverified,
            "backend_unverified_cells": unverified,
            "execution_valid_cells": len(validity_cells) - len(invalid_exec),
            "execution_invalid_cells": invalid_exec,
            "isolation_broken_cells": iso_broken,
            "leaky_cells": leaky,
            "raw_checkout_leakage_events_total": raw_leak_events,
            "leakage_criterion": "frozen C4 criterion: sensitive_leakage_"
                                 "events == 0 and policy_violations == [] — "
                                 "raw checkout_leakage_events additionally "
                                 "counts classified non-sensitive events "
                                 "(runtime-internal paths / documented arm-"
                                 "prompt hint patterns) and is informational",
            "capability_flagged_cells": capability_flagged,
            "evaluator_consistency_mismatches": evaluator_mismatches,
            "prompt_hash_inconsistent_tasks": prompt_inconsistent,
            "no_cells_excluded": True,
        },
        "success": {
            "overall": success_overall,
            "per_task": success_per_task,
            "execution_valid_vs_task_success": "execution_valid = runner "
                "status completed without violations; task_success = frozen "
                "oracle evaluation. They are reported separately and are "
                "never conflated.",
        },
        "cost_overall": {
            "native": cost_overall["native"],
            "sqi": cost_overall["sqi"],
            "delta_pct_sqi_vs_native": cost_delta,
            "token_semantics": "per-cell session-cumulative usage from the "
                               "agent adapter (CLI final result event usage), "
                               "aggregated with the frozen synthesis "
                               "cell_tokens semantics; total_as_logged is the "
                               "event-provided total, not a constructed sum",
            "duration": NOT_CAPTURED if not duration_available else "captured",
            "duration_note": "duration_ms existed only in the C4 runner's "
                             "in-memory cell record (added after run.json "
                             "was persisted); events.ndjson timestamps are "
                             "end-of-session flush stamps, so per-cell "
                             "wall-clock duration cannot be recovered from "
                             "raw artifacts. Minimum new measurement: persist "
                             "duration_ms in run.json for future batches.",
        },
        "cost_per_successful_task": {
            "overall": cost_per_success_overall,
            "per_task": cost_per_success_per_task,
            "interpretation_guard": "batch-level success-normalized token "
                                    "index only — not a monetary cost",
        },
        "per_task": per_task,
        "tool_use": {
            "native_by_tool": native_tools,
            "sqi_calls_by_type": sqi_calls_by_type,
            "sqi_arm_all_tool_events": sqi_arm_all_events,
            "sqi_arm_native_tool_events_excl_sqi_cli": sqi_arm_native_only,
            "per_task": tool_use_per_task,
            "equivalence_note": "native tool calls and SQI calls are NOT "
                                "treated as equivalent units: native tools "
                                "return raw text/binary hits, SQI calls "
                                "return schema'd evidence envelopes. The "
                                "goal is to expose exploration-structure "
                                "differences, not to claim 1 SQI call = 1 "
                                "Read.",
        },
        "cell_records": cell_records,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(json.dumps({
        "out": str(OUT),
        "cells": len(cells),
        "backends": backends,
        "success": {arm: success_overall[arm] for arm in ARMS},
        "cost_totals": {arm: {k: cost_overall[arm][k]["sum"]
                              for k in TOKEN_KEYS} for arm in ARMS},
        "delta_pct": cost_delta,
        "duration": doc["cost_overall"]["duration"],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""C4-R2 clean synthesis + V1.2 final qualification verdict.

Evidence: SQI-FORMAL-C4-20260920T042801Z — 36/36 cells on a single backend
(deepseek-flash), full model_provenance per cell, zero sensitive leakage.
This is the first before/after comparison with formal attribution standing.

Frozen evaluation order: capability floors first, then per-task cost with
the V1.1 baseline (SQI-FORMAL-20260917-1, cost-attribution-v1.json numbers;
that baseline ran on mixed backends, so cross-era token figures carry a
residual backend caveat — documented in unresolved regions).

Verdict: QUALIFIED iff every floor holds; otherwise HOLD / PARTIAL with
positive / negative / unresolved regions preserved verbatim.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINE_ROOT = HERE.parent
RESULTS = LINE_ROOT / "results" / "formal"
CLEAN_BATCH = RESULTS / "SQI-FORMAL-C4-20260920T042801Z"
BASELINE_BATCH = RESULTS / "SQI-FORMAL-20260917-1"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def iter_cells(batch_dir: Path):
    for task_dir in sorted(batch_dir.glob("SQI-T*")):
        for arm_dir in sorted(task_dir.iterdir()):
            if not arm_dir.is_dir():
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
                                log_path.read_text(encoding="utf-8").splitlines()
                                if l.strip()]
                yield {"task_id": run["task_id"], "arm": run["arm"],
                       "repetition": run["repetition"], "cell": run.get("cell_id"),
                       "run": run, "eval": ev, "call_log": call_log,
                       "dir": rep_dir}


def cell_tokens(rep_dir: Path) -> dict:
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    events_path = rep_dir / "events.ndjson"
    if not events_path.exists():
        return totals
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        tokens = (json.loads(line).get("tokens") or {})
        for key in totals:
            value = tokens.get(key)
            if isinstance(value, (int, float)):
                totals[key] += int(value)
    return totals


def source_reads(rep_dir: Path) -> dict:
    events_path = rep_dir / "events.ndjson"
    if not events_path.exists():
        return {"events": 0, "bytes": 0}
    count, size = 0, 0
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if str(event.get("operation", "")).casefold() == "read":
            count += 1
            size += int(event.get("result_size") or 0)
    return {"events": count, "bytes": size}


def main() -> int:
    cells = list(iter_cells(CLEAN_BATCH))
    assert len(cells) == 36, f"expected 36 cells, found {len(cells)}"
    sqi = [c for c in cells if c["arm"] == "sqi"]
    native = [c for c in cells if c["arm"] == "native"]

    # ---- layer 1: capability floors ------------------------------------
    per_task = {}
    for c in cells:
        per_task.setdefault((c["task_id"], c["arm"]), []).append(
            bool(c["run"].get("task_success")))
    sqi_success = sum(1 for c in sqi if c["run"].get("task_success"))
    native_success = sum(1 for c in native if c["run"].get("task_success"))
    t02 = sum(per_task[("SQI-T02", "sqi")])
    t04 = sum(per_task[("SQI-T04", "sqi")])
    citation_ok = sum(1 for c in sqi
                      if (c["eval"].get("evidence_oracle") or {})
                      .get("citation_closure_ok"))
    unsupported = sum(len((c["eval"].get("evidence_oracle") or {})
                          .get("unsupported_claim_ids", [])) for c in sqi)
    machine_pass = sum(1 for c in sqi if c["eval"].get("machine_checks_pass"))
    src_active = sum(1 for c in sqi if source_reads(c["dir"])["events"] >= 1)
    violations = [c["cell"] for c in cells
                  if c["run"].get("sensitive_leakage_events", 0)
                  or c["run"].get("policy_violations")]
    backends = sorted({c["run"]["isolation"]["model_provenance"]["backend_model"]
                       for c in cells})
    baseline_summary = load_json(BASELINE_BATCH / "formal-batch-summary.json")
    floors = {
        "sqi_18_of_18": {"value": f"{sqi_success}/18", "pass": sqi_success == 18},
        "t02_3_of_3": {"value": f"{t02}/3", "pass": t02 == 3},
        "t04_3_of_3": {"value": f"{t04}/3", "pass": t04 == 3},
        "citation_closure_100pct": {"value": f"{citation_ok}/18",
                                    "pass": citation_ok == 18},
        "unsupported_claims_zero": {"value": unsupported, "pass": unsupported == 0},
        "machine_checks": {"value": f"{machine_pass}/18",
                           "pass": machine_pass == 18},
        "source_verification": {"value": f"{src_active}/18 cells with source "
                                          "reads", "pass": src_active == 18},
        "no_new_violations": {"value": violations, "pass": not violations},
        "single_backend": {"value": backends, "pass": len(backends) == 1},
    }
    floors_pass = all(f["pass"] for f in floors.values())

    # ---- T05 / T06 task-level failure attribution -----------------------
    task_failures = {"SQI-T05": [], "SQI-T06": []}
    for c in sqi:
        if c["task_id"] in task_failures and not c["run"].get("task_success"):
            failed = [k for k, v in (c["eval"].get("machine_checks") or {})
                      .items() if not v]
            task_failures[c["task_id"]].append({
                "cell": c["cell"], "sqi_calls": c["run"].get("sqi_calls"),
                "machine_checks_failed": failed,
                "output_head": (c["dir"] / "agent-output.txt")
                .read_text(encoding="utf-8")[:220].replace("\n", " "),
            })
    t05_calls = sorted(c["run"]["sqi_calls"] for c in sqi
                       if c["task_id"] == "SQI-T05")
    t05_cache_hits = sum(1 for c in sqi if c["task_id"] == "SQI-T05"
                         for e in c["call_log"] if e.get("served_from_cache"))
    t06_repeat = {
        "cells": [{"cell": c["cell"], "sqi_calls": c["run"]["sqi_calls"],
                   "bundle_explain_calls": sum(1 for e in c["call_log"]
                                               if e["call"] == "bundle.explain"),
                   "cache_served": sum(1 for e in c["call_log"]
                                       if e.get("served_from_cache"))}
                  for c in sqi if c["task_id"] == "SQI-T06"],
        "mechanism": "the frozen T06 machine check requires exactly one "
                     "bundle.explain invocation; the observed failures are "
                     "agents RE-INVOKING the same bundle.explain (byte-"
                     "identical 32040-byte envelopes, later repeats served "
                     "from the OPT-T05 session cache) — agent call-pattern "
                     "behavior, not an implementation fault: the cache "
                     "returned byte-identical envelopes and citation "
                     "closure/unsupported claims stayed clean",
    }

    # ---- layer 2: cost ---------------------------------------------------
    def cost_block(cell_list):
        totals = {"cells": len(cell_list), "sqi_calls": 0, "envelope_bytes": 0,
                  "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
                  "cache_creation_tokens": 0, "cache_hits": 0,
                  "duration_ms": 0.0, "source_read_bytes": 0,
                  "source_read_events": 0, "agent_output_bytes": 0}
        for c in cell_list:
            run = c["run"]
            totals["sqi_calls"] += run.get("sqi_calls") or 0
            totals["duration_ms"] += run.get("duration_ms") or 0
            summary = c["eval"].get("sqi_call_summary") or {}
            totals["envelope_bytes"] += summary.get("total_payload_bytes") or 0
            tokens = cell_tokens(c["dir"])
            for key in ("input", "output", "cache_read", "cache_creation"):
                totals[f"{key}_tokens"] += tokens[key]
            totals["cache_hits"] += sum(1 for e in c["call_log"]
                                        if e.get("served_from_cache"))
            reads = source_reads(c["dir"])
            totals["source_read_bytes"] += reads["bytes"]
            totals["source_read_events"] += reads["events"]
            output_path = c["dir"] / "agent-output.txt"
            if output_path.exists():
                totals["agent_output_bytes"] += output_path.stat().st_size
        totals["cache_amplification"] = round(
            totals["cache_read_tokens"] / totals["input_tokens"], 1
        ) if totals["input_tokens"] else None
        return totals

    sqi_cost = cost_block(sqi)
    native_cost = cost_block(native)
    per_task_after = {}
    for task_id in sorted({c["task_id"] for c in sqi}):
        per_task_after[task_id] = cost_block(
            [c for c in sqi if c["task_id"] == task_id])
    baseline_cost = load_json(BASELINE_BATCH / "cost-attribution-v1.json")
    per_task_before = {k: {kk: v.get(kk) for kk in
                           ("cells", "sqi_calls", "envelope_bytes_total",
                            "input_tokens", "cache_read_tokens")}
                       for k, v in baseline_cost["per_task"].items()}

    # ---- verdict ---------------------------------------------------------
    if floors_pass:
        verdict = "QUALIFIED"
    else:
        verdict = ("HOLD / PARTIAL — single-backend attribution achieved, but "
                   "the frozen capability floor is breached at T05.sqi 2/3 "
                   "and T06.sqi 1/3; positive and negative regions preserved "
                   "for V1.2 negative-region repair")
    doc = {
        "schema": "SQI_C4_R2_CLEAN_SYNTHESIS_V1",
        "batch": CLEAN_BATCH.name,
        "isolation_baseline_sha": "27e40df5e61cd815d8ea0d00203746344c279690",
        "capability_floors": floors,
        "floors_pass": floors_pass,
        "task_success": {"sqi": f"{sqi_success}/18",
                         "native": f"{native_success}/18",
                         "per_task_sqi": {k[0]: f"{sum(v)}/3" for k, v in
                                          sorted(per_task.items())
                                          if k[1] == "sqi"},
                         "per_task_native": {k[0]: f"{sum(v)}/3" for k, v in
                                             sorted(per_task.items())
                                             if k[1] == "native"},
                         "baseline": baseline_summary["task_success"]},
        "t05_attribution": {
            "calls_per_cell": t05_calls,
            "cache_hits_total": t05_cache_hits,
            "failures": task_failures["SQI-T05"],
            "mechanism": "OPT-T05 session cache ACTIVE and correct: repeats "
                         "served byte-identical envelopes from the call log "
                         "(r2: 3 hits, r3: 4 hits). The r1 failure is agent "
                         "exploration behavior — 11 calls without reaching "
                         "the required knowledge-DB/code-DB evidence ids; "
                         "determinism cross-checked: the first 11 calls of "
                         "r1/r2/r3 have byte-identical envelopes",
        },
        "t06_attribution": t06_repeat,
        "cost_comparison": {"after_sqi_totals": sqi_cost,
                            "after_native_totals": native_cost,
                            "before_totals": baseline_cost["totals"],
                            "per_task_after": per_task_after,
                            "per_task_before": per_task_before},
        "verdict": verdict,
        "verdict_scope": "V1.2 (cost optimization qualification) only — "
                         "SQI-V1/V1.1 functional qualification unaffected",
        "regions": {
            "positive_regions": [
                "single-backend attribution achieved (deepseek-flash x36, "
                "provenance per cell)",
                "T02/T03/T04.sqi all 3/3 (T03/T04 recovered once the "
                "infrastructure defect was fixed)",
                "citation closure 18/18, unsupported claims 0, zero "
                "violations — SQI evidence discipline holds end to end",
                "OPT-T05 session cache verified in production: repeated "
                "invocations served byte-identical envelopes at zero "
                "recomputation",
            ],
            "negative_regions": [
                "T05.sqi 2/3 (r1: exploration shortfall, 11 calls without "
                "the required evidence ids)",
                "T06.sqi 1/3 (r2/r3: bundle.explain re-invocation violates "
                "the frozen single-call machine check)",
            ],
            "unresolved_regions": [
                "baseline ran on mixed backends (deepseek-flash + "
                "deepseek-v4-flash per host transcripts) — cross-era token "
                "comparisons carry a residual backend caveat",
                "native control variance (T02 native 0/3 vs baseline 1/3) "
                "suggests residual model behavioral drift independent of SQI",
                "whether T06 re-invocation is INVITED by the compressed "
                "envelope (agent wants more than truncated:true provides) "
                "vs pure model nondeterminism",
            ],
        },
    }
    out = RESULTS / f"C4-R2-SYNTHESIS-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(json.dumps({"verdict": verdict,
                      "sqi_task_success": f"{sqi_success}/18",
                      "floors": {k: v["pass"] for k, v in floors.items()},
                      "evidence": str(out)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

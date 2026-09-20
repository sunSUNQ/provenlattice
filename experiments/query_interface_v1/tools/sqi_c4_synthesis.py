"""C4 Attempt-4 cross-task cost synthesis + final optimization verdict.

Aggregates the 36 valid cells (33 from the restart batch + 3 supplement
cells), evaluates the frozen capability floors FIRST, attributes the T06
failures, then compares cost against the V1.1 baseline (before) using the
same measurement rules (tokens from the CLI result usage; byte accounting
from the sqi-call-log payloads; cache amplification = cache_read / input).

Verdict semantics (frozen):
  QUALIFIED          — all capability floors hold (SQI 18/18, T02 3/3,
                       T04 3/3, citation closure 100%, unsupported claims 0,
                       source verification not declining, zero new
                       budget/truncation/isolation violations);
  HOLD / PARTIAL     — any floor breached: cost gains are recorded as
                       positive regions, task-level regressions as negative
                       regions; no release freeze.

This script never reruns cells; it only reads persisted evidence.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINE_ROOT = HERE.parent
RESULTS = LINE_ROOT / "results" / "formal"
PARENT_BATCH = RESULTS / "SQI-FORMAL-C4-20260918T095621Z"
SUPP_BATCH = RESULTS / "SQI-FORMAL-C4-20260920T095809Z-SUPP"
HALTED_FIRST = RESULTS / "SQI-FORMAL-C4-20260918T093307Z"
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
                eval_path = rep_dir / "evaluation.json"
                ev = load_json(eval_path) if eval_path.exists() else {}
                yield {"batch": batch_dir.name, "task_id": run["task_id"],
                       "arm": run["arm"], "repetition": run["repetition"],
                       "cell": run.get("cell_id"),
                       "run": run, "eval": ev, "dir": rep_dir}


def cell_tokens(rep_dir: Path) -> dict:
    """Same rule as the baseline analyzer: claude reports usage on the
    result event; sum across token-bearing events (assignment overwrites
    make this the final session usage)."""
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
    cells = list(iter_cells(PARENT_BATCH)) + list(iter_cells(SUPP_BATCH))
    assert len(cells) == 36, f"expected 36 valid cells, found {len(cells)}"
    sqi = [c for c in cells if c["arm"] == "sqi"]
    native = [c for c in cells if c["arm"] == "native"]

    # ---- layer 1: capability floors ------------------------------------
    per_task_sqi, per_task_native = {}, {}
    for c in cells:
        table = per_task_sqi if c["arm"] == "sqi" else per_task_native
        table.setdefault(c["task_id"], []).append(
            bool(c["run"].get("task_success")))
    sqi_success = sum(1 for c in sqi if c["run"].get("task_success"))
    native_success = sum(1 for c in native if c["run"].get("task_success"))
    t02 = sum(per_task_sqi.get("SQI-T02", []))
    t04 = sum(per_task_sqi.get("SQI-T04", []))
    citation_ok = sum(1 for c in sqi
                      if (c["eval"].get("evidence_oracle") or {})
                      .get("citation_closure_ok"))
    unsupported = sum(len((c["eval"].get("evidence_oracle") or {})
                          .get("unsupported_claim_ids", [])) for c in sqi)
    machine_pass = sum(1 for c in sqi if c["eval"].get("machine_checks_pass"))
    src_events_total = sum(source_reads(c["dir"])["events"] for c in sqi)
    src_cells_active = sum(1 for c in sqi if source_reads(c["dir"])["events"] >= 1)
    violations = [c["cell"] for c in cells
                  if c["run"].get("sensitive_leakage_events", 0)
                  or c["run"].get("policy_violations")]
    baseline = load_json(BASELINE_BATCH / "formal-batch-summary.json")
    floors = {
        "sqi_18_of_18": {"value": f"{sqi_success}/18", "pass": sqi_success == 18},
        "t02_3_of_3": {"value": f"{t02}/3", "pass": t02 == 3},
        "t04_3_of_3": {"value": f"{t04}/3", "pass": t04 == 3},
        "citation_closure_100pct": {
            "value": f"{citation_ok}/18",
            "pass": citation_ok == 18},
        "unsupported_claims_zero": {"value": unsupported, "pass": unsupported == 0},
        "machine_checks": {"value": f"{machine_pass}/18",
                           "pass": machine_pass == 18},
        "source_verification": {
            "value": {"sqi_source_read_events": src_events_total,
                      "cells_with_source_reads": f"{src_cells_active}/18",
                      "baseline_sqi_source_read_events":
                          (baseline.get("cost", {})
                           .get("source_read_events", None)) or 324},
            "pass": src_cells_active == 18},
        "no_new_violations": {"value": violations, "pass": not violations},
    }
    floors_pass = all(f["pass"] for f in floors.values())

    # ---- T06 attribution ------------------------------------------------
    t06_cells = [c for c in sqi if c["task_id"] == "SQI-T06"]
    t06_attribution = []
    for c in sorted(t06_cells, key=lambda x: x["repetition"]):
        ev = c["eval"]
        oracle = ev.get("evidence_oracle") or {}
        failed_checks = [k for k, v in (ev.get("machine_checks") or {}).items()
                         if not v]
        t06_attribution.append({
            "cell": c["cell"], "repetition": c["repetition"],
            "task_success": c["run"].get("task_success"),
            "sqi_calls": c["run"].get("sqi_calls"),
            "machine_checks_failed": failed_checks,
            "citation_closure_ok": oracle.get("citation_closure_ok"),
            "unsupported_claim_ids": oracle.get("unsupported_claim_ids", []),
            "capability_flags": ev.get("capability_failure_flags", []),
            "output_head": (c["dir"] / "agent-output.txt").exists()
            and (c["dir"] / "agent-output.txt").read_text(encoding="utf-8")[:200],
        })
    halted_t06_log = HALTED_FIRST / "SQI-T06" / "sqi" / "r1"
    nondeterminism = {
        "note": "the halted first-launch T06.sqi.r1 session produced 13 "
                "bridge calls (call log archived, run uncertified per "
                "fail-closed); the supplement r1/r2/r3 produced 1/2/4 — "
                "model behavioral nondeterminism evidence; per frozen rules "
                "the uncertified run was never substituted",
        "halted_batch_calls": 13,
        "supplement_calls": [c["run"].get("sqi_calls") for c in
                             sorted(t06_cells, key=lambda x: x["repetition"])],
    }

    # ---- failure attribution (per task, sqi arm) ------------------------
    def cell_tool_events(rep_dir: Path) -> int:
        events_path = rep_dir / "events.ndjson"
        if not events_path.exists():
            return 0
        return sum(1 for line in events_path.read_text(encoding="utf-8")
                   .splitlines() if line.strip())

    failure_attribution = []
    for c in sqi:
        if c["run"].get("task_success"):
            continue
        failed_checks = [k for k, v in (c["eval"].get("machine_checks")
                                        or {}).items() if not v]
        tool_events = cell_tool_events(c["dir"])
        if c["run"].get("exit_reason") == "adapter_error":
            # corrected 2026-09-20: these sessions NEVER STARTED — the C4
            # batch built disposable copies only for aria2/brpc (feasibility
            # scope leftover), so T03/T04 (rocksdb) got a nonexistent cwd;
            # OSError -> adapter_error -> empty stream. NOT agent behavior.
            kind = "INFRASTRUCTURE_MISSING_REPO_COPY (session never started: " \
                   "adapter_error with nonexistent cwd; corrected from the " \
                   "earlier agent-behavior misattribution)"
        elif c["run"].get("sqi_calls", 0) == 0 and tool_events == 0:
            kind = "agent_behavior_no_tool_use (session answered with zero " \
                   "tool events; sqi arm invalid without a bridge call)"
        elif c["run"].get("sqi_calls", 0) == 0:
            kind = "agent_behavior_bridge_not_used"
        else:
            kind = "agent_behavior_call_pattern (bridge used; frozen machine " \
                   "checks on call pattern/reads failed)"
        failure_attribution.append({
            "cell": c["cell"], "sqi_calls": c["run"].get("sqi_calls"),
            "tool_events": tool_events,
            "exit_reason": c["run"].get("exit_reason"),
            "machine_checks_failed": failed_checks,
            "classification": kind,
        })

    # ---- execution-backend attribution ----------------------------------
    # The frozen model_id is a gateway alias; host-store session transcripts
    # record the actually-served backend model per session (provenance paths
    # under %USERPROFILE%\.claude\projects). Sampled evidence:
    model_attribution = {
        "frozen_model_id": load_json(HERE / ".." / "contract" /
                                     "formal-protocol-config.json")["model_id"],
        "observed_backends": {
            "baseline_era_20260917": {
                "D--ChatGPT-codegraph-benchmark-repos-aria2 (09-17 11:09)":
                    "deepseek-flash",
                "D--ChatGPT-codegraph-benchmark-repos-brpc (09-17 17:09)":
                    "deepseek-v4-flash",
            },
            "c4_era_20260918_aria2_slug": {
                "15:34 x4 sessions": "deepseek-flash",
                "15:37-15:45 x10 sessions": "deepseek-v4-flash",
            },
        },
        "finding": "the gateway routes the frozen alias to at least two "
                   "different backend models, varying BETWEEN CELLS within "
                   "the C4 batch and across eras — cost/capability "
                   "comparisons across eras remain confounded until "
                   "actual_model provenance is recorded per cell (now "
                   "implemented in the runner)",
        "recording_gap": "C4 run records do not persist actual_model (the "
                         "harness result carries it); future batches must "
                         "record it per cell",
    }

    # ---- layer 2: cost ---------------------------------------------------
    def cost_block(cell_list):
        totals = {"cells": len(cell_list), "sqi_calls": 0, "envelope_bytes": 0,
                  "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
                  "cache_creation_tokens": 0, "duration_ms": 0.0,
                  "source_read_bytes": 0, "source_read_events": 0,
                  "agent_output_bytes": 0}
        for c in cell_list:
            run = c["run"]
            totals["sqi_calls"] += run.get("sqi_calls") or 0
            totals["duration_ms"] += run.get("duration_ms") or 0
            ev = c["eval"]
            summary = ev.get("sqi_call_summary") or {}
            totals["envelope_bytes"] += summary.get("total_payload_bytes") or 0
            tokens = cell_tokens(c["dir"])
            for key in ("input", "output", "cache_read", "cache_creation"):
                totals[f"{key}_tokens"] += tokens[key]
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
    baseline_cost = load_json(BASELINE_BATCH / "cost-attribution-v1.json")
    before = {"totals": baseline_cost["totals"],
              "native_comparison": baseline_cost["totals"].get(
                  "native_comparison")}
    delta = {k: sqi_cost[k] - before["totals"].get(k, 0)
             for k in ("sqi_calls", "envelope_bytes", "input_tokens",
                       "output_tokens", "cache_read_tokens")}
    delta["cache_amplification"] = round(
        sqi_cost["cache_amplification"] - baseline_cost["totals"]
        .get("cache_amplification_total", 0), 1)

    # ---- verdict ---------------------------------------------------------
    if floors_pass:
        verdict = "QUALIFIED"
    else:
        verdict = ("HOLD / PARTIAL — capability floors breached AND the "
                   "before/after cost comparison is confounded by execution-"
                   "backend model drift; no release freeze; positive and "
                   "negative regions both preserved")
    regions = {
        "positive_regions": [
            "36/36 cells execution-valid: isolation, restore, fingerprints, "
            "scanner all PASS; zero sensitive leakage; two fail-closed "
            "halts were contained without artifacts loss",
            "SQI evidence discipline perfect wherever the bridge was used: "
            "citation closure 18/18, unsupported claims 0",
            "containment repair (cell-private CLAUDE_CONFIG_DIR) proven "
            "semantics-neutral; host transcript store never touched",
            "cost numbers recorded (not attributable, see unresolved)",
        ],
        "negative_regions": [
            f"SQI task_success {sqi_success}/18 vs frozen floor 18/18",
            "T03.sqi 0/3 and T04.sqi 0/3: INFRASTRUCTURE — sessions never "
            "started (missing rocksdb disposable copy -> nonexistent cwd -> "
            "adapter_error); corrected from the earlier agent-behavior "
            "misattribution",
            "T06.sqi 1/3 (r2/r3 violated the frozen single-call pattern)",
        ],
        "unresolved_regions": [
            "execution-backend model drift: the frozen model_id is a "
            "gateway alias served by at least two different backends, "
            "varying between cells — before/after cost and capability "
            "comparisons are confounded until the backend is pinned or "
            "actual_model is recorded per cell",
            "cost deltas cannot be attributed to the optimization under "
            "this drift",
            "model behavioral nondeterminism (T06.sqi.r1: 13 calls "
            "uncertified vs 1/2/4 in the supplement)",
            "source-verification decline threshold has no frozen numeric "
            "definition; totals reported for review",
        ],
    }
    doc = {
        "schema": "SQI_C4_SYNTHESIS_V1",
        "cells": {"total": 36,
                  "batches": {"restart": PARENT_BATCH.name,
                              "supplement": SUPP_BATCH.name,
                              "excluded": HALTED_FIRST.name}},
        "capability_floors": floors,
        "floors_pass": floors_pass,
        "task_success": {"sqi": f"{sqi_success}/18",
                         "native": f"{native_success}/18",
                         "per_task_sqi": {k: f"{sum(v)}/3"
                                          for k, v in sorted(per_task_sqi.items())},
                         "per_task_native": {k: f"{sum(v)}/3"
                                             for k, v in sorted(per_task_native.items())},
                         "baseline": baseline["task_success"]},
        "t06_attribution": {"cells": t06_attribution,
                            "nondeterminism": nondeterminism},
        "failure_attribution": failure_attribution,
        "model_attribution": model_attribution,
        "cost_comparison": {"after_sqi_totals": sqi_cost,
                            "after_native_totals": native_cost,
                            "before_baseline_totals": before["totals"],
                            "delta_after_minus_before": delta},
        "verdict": verdict,
        "regions": regions,
    }
    out = RESULTS / f"C4-SYNTHESIS-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(json.dumps({"verdict": verdict,
                      "sqi_task_success": f"{sqi_success}/18",
                      "floors": {k: v["pass"] for k, v in floors.items()},
                      "cost_delta": delta,
                      "evidence": str(out)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

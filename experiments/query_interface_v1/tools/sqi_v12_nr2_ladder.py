"""V1.2-NR2 qualification ladder — targeted T05 stability validation.

Stage plan (mirrors the NR1 ladder; the NR2 repair surface is the generic
empty-result guidance, so the ladder re-validates the two sensitive tasks
first, then the smoke set):

  T06   SQI-T06.sqi r1-r3   gate: task_success + exactly ONE bundle.explain
                            per cell + zero policy violations (repeat-call
                            discipline regression gate)
  T05   SQI-T05.sqi r1-r3   gate: task_success + citation closure + both
                            frozen required-database ids returned (the
                            C4-R3 negative region)
  SMOKE SQI-T01..T04 r1     gate: task_success (single-rep model noise is
                            tolerated on recheck, as in the NR1 ladder)

Every cell runs through the UNCHANGED frozen C4 lifecycle (CellWindow,
leakage classification, backend drift gate, per-repetition call logs).
NR2 telemetry: per cell, the number of empty envelopes that carried the
generic empty_result_guidance (mechanism exposure, no task specifics).

Verdict: GREEN iff all gates pass; HALTED on fail-closed batch halt;
FAIL otherwise. Evidence: results/formal/LADDER-V12NR2-<stamp>/
ladder-evidence.json + per-cell artifacts (run.json, evaluation.json,
call logs, window states).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINE_ROOT = HERE.parent
RESULTS = LINE_ROOT / "results" / "formal"

from sqi_c4_runner import (  # noqa: E402
    C4BatchHalted, C4BatchRunner, build_runtime, load_config, load_tasks,
    run_preflight)
from v14_feasibility_noreboot import task_db_rels  # noqa: E402

STAGES = [
    {"name": "T06", "tasks": ("SQI-T06",), "reps": (1, 2, 3)},
    {"name": "T05", "tasks": ("SQI-T05",), "reps": (1, 2, 3)},
    {"name": "SMOKE", "tasks": ("SQI-T01", "SQI-T02", "SQI-T03", "SQI-T04"),
     "reps": (1,)},
]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def call_log(run_dir: Path) -> list[dict]:
    path = run_dir / "sqi-call-log.ndjson"
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def hint_exposures(entries: list[dict]) -> int:
    """NR2 telemetry: empty envelopes that carried the generic guidance."""
    return sum(1 for e in entries
               if ((e.get("envelope") or {}).get("result_meta") or {})
               .get("empty_result_guidance"))


def stage_cells(stage: dict) -> list[dict]:
    return [{"task_id": task_id, "arm": "sqi", "repetition": rep}
            for task_id in stage["tasks"] for rep in stage["reps"]]


def summarize_stage(stage: dict, stage_dir: Path, records: list[dict]) -> dict:
    cells = []
    for record in records:
        run_dir = stage_dir / record["task_id"] / record["arm"] / \
            f"r{record['repetition']}"
        entries = call_log(run_dir)
        evaluation = read_json(run_dir / "evaluation.json")
        machine = evaluation.get("machine_checks") or {}
        failed = sorted(k for k, v in machine.items() if v is False)
        if record["task_id"] == "SQI-T06":
            explain = sum(1 for e in entries if e.get("call") == "bundle.explain")
            detail = (f"task_success={record['task_success']} "
                      f"bundle.explain={explain}")
            gate = bool(record["task_success"]) and explain == 1 \
                and not record["policy_violations"]
        elif record["task_id"] == "SQI-T05":
            ok_ids = bool(machine.get("knowledge_db_id_returned")) and \
                bool(machine.get("code_db_id_returned"))
            detail = (f"task_success={record['task_success']} "
                      f"required_db_ids={ok_ids} "
                      f"mc_failed={','.join(failed) or '-'}")
            gate = bool(record["task_success"]) and ok_ids \
                and not record["policy_violations"]
        else:
            detail = (f"task_success={record['task_success']} "
                      f"mc_failed={','.join(failed) or '-'}")
            gate = bool(record["task_success"])
        cells.append({
            "cell": record["cell_id"], "task_id": record["task_id"],
            "status": record["status"],
            "task_success": record["task_success"],
            "sqi_calls": record["sqi_calls"],
            "cache_hits": sum(1 for e in entries if e.get("served_from_cache")),
            "empty_guidance_exposures": hint_exposures(entries),
            "sensitive_leakage": record["sensitive_leakage_events"],
            "citation_closure_ok": (evaluation.get("evidence_oracle") or {})
            .get("citation_closure_ok"),
            "machine_checks_failed": failed,
            "backend": (record["isolation"]["model_provenance"]
                        .get("backend_model")),
            "gate": gate, "gate_detail": detail,
        })
    gate_pass = all(c["gate"] for c in cells) and \
        all(c["status"] == "completed" for c in cells)
    return {"stage": stage["name"], "halted": None, "cells": cells,
            "gate_pass": gate_pass,
            "gate_detail": "; ".join(c["gate_detail"] for c in cells)}


def main() -> int:
    preflight_doc = run_preflight()
    if preflight_doc["verdict"] != "PASS":
        print(json.dumps(preflight_doc["checks"], indent=1)[:2000])
        print("LADDER preflight FAIL — not started")
        return 1
    config = load_config()
    tasks = {t["task_id"]: t for t in load_tasks()}
    ladder_id = time.strftime("LADDER-V12NR2-%Y%m%d-%H%M%S",
                              time.localtime())
    ladder_root = RESULTS / ladder_id
    ladder_root.mkdir(parents=True, exist_ok=True)
    build_runtime(
        {tid: task_db_rels(t) for tid, t in tasks.items()},
        repos=sorted({t["repository"].split("-", 1)[1].lower()
                      for t in tasks.values()}))
    stages, halted = [], None
    try:
        for stage in STAGES:
            stage_dir = ladder_root / stage["name"]
            stage_dir.mkdir(parents=True, exist_ok=True)
            runner = C4BatchRunner(
                config, list(tasks.values()),
                f"{ladder_id}-{stage['name']}", stage_dir,
                expected_backend=preflight_doc.get("backend_reference"))
            records = runner.run_batch(stage_cells(stage))
            stages.append(summarize_stage(stage, stage_dir, records))
            if not stages[-1]["gate_pass"]:
                break
    except C4BatchHalted as halt:
        halted = {"cell": halt.cell_id, "reason": halt.reason,
                  "detail": halt.detail[:200]}
    verdict = ("HALTED" if halted else
               "GREEN" if all(s["gate_pass"] for s in stages) else "FAIL")
    doc = {
        "schema": "SQI_V12NR2_LADDER_EVIDENCE_V1",
        "ladder_id": ladder_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runner_commit": _head(),
        "preflight_backend": preflight_doc.get("backend_reference"),
        "stages": stages,
        "halted": halted,
        "verdict": verdict,
    }
    evidence = ladder_root / "ladder-evidence.json"
    evidence.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(json.dumps({"verdict": verdict,
                      "stages": {s["stage"]: s["gate_pass"] for s in stages},
                      "halted": halted, "evidence": str(evidence)},
                     ensure_ascii=False, indent=1))
    return 0 if verdict == "GREEN" else 1


def _head() -> str:
    import subprocess
    return subprocess.run(
        ["git", "-C", str(HERE.parents[2]), "rev-parse", "HEAD"],
        capture_output=True, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()


if __name__ == "__main__":
    sys.exit(main())

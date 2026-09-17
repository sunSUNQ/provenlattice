# SQI-V1 Six-Task Smoke Qualification Review — PASS

Smoke date: 2026-09-16

## Verdict

**SQI Six-Task Smoke = PASS.** All six frozen tasks executed through the sealed
SQI implementation on their frozen databases with schema-valid, deterministic,
budget-compliant, evidence-bound responses and verified frozen anchors.
This is smoke evidence only — it validates fixtures, anchors, routing, binding,
budgets and truncation. It is **not** a Native-vs-SQI effectiveness verdict.

## Run

- run_id: `SQI-SMOKE-20260916T101828Z-5bb591`
- run_kind: `implementation-smoke` (qualification verdict explicitly `null`)
- arm: `sqi` (native arm recorded as `NOT_EXECUTED_IN_IMPLEMENTATION_SMOKE`)
- per-task records + raw envelopes retained under
  `results/implementation-smoke/SQI-SMOKE-20260916T101828Z-5bb591/`
- superseded pre-freeze smoke runs retained and marked in
  `results/implementation-smoke/SUPERSEDED-smoke-runs.json`

## Per-task anchor verification (frozen ground truth)

| Task | Anchors checked | Result |
| --- | --- | --- |
| SQI-T01 | `aria2.DownloadEngine` symbol id returned; `src/DownloadEngine.h`; declaration line 84; CODE_DEFINITION evidence | PASS |
| SQI-T02 | all 7 frozen CALLS edge ids returned as evidence fact ids; 5 production callers covered; deterministic order | PASS |
| SQI-T03 | all 6 frozen resolved raw-reference locations returned exactly; all 6 frozen `E-REF-*` ids returned | PASS |
| SQI-T04 | frontier_size=49; boundary_edges_total=1031; wide_impact=true; budgeted edge-id listing with explicit truncation | PASS |
| SQI-T05 | `brpc.policy.AddServersInBatch.replicas` returned via `code.related`; CROSS_LAYER_LINK evidence `E-XLINK-3284c4dde04ede3b45992a17` | PASS |
| SQI-T06 | bundle within declared budget (12/6/10); truncation declared with honest omitted counts (43 symbols / 39 edges); deterministic repeat | PASS |

## Gate checks

- schema valid: 8/8 calls (across 6 tasks) PASS
- contract validation (C1–C4 + budget + expected-commit): PASS, zero semantic errors
- frozen anchors: 6/6 tasks verified
- provenance: repository/commit/generation present in every envelope; commit
  equals the frozen task commit (mismatch rejection tested)
- determinism: double-execution identical for every call (only `query_time_ms`
  varies, per Contract R2)
- budget/truncation: within hard caps; every cut explicitly reported
- no infrastructure blocker; no frozen asset modified

## task_failure vs capability failure

The smoke executes the interface machinery directly (no live agent), so no
task-level failures exist at this stage; the runner nevertheless records
`failure_attribution` fields separating machinery failures (schema/semantic/
determinism — SQI implementation) from anchor mismatches (fixture/adapter/
data), and never derives an SQI capability failure from a future task failure.

## SHA-256 manifest

`results/implementation-smoke/SQI-SMOKE-20260916T101828Z-5bb591/manifest.sha256`
covers this review's evidence set (summary + 6 task records + supersession
marker).

# RQ2 Formal B1 Qualification Review — PASS

Review date: 2026-09-16

## Scope and disposition

**B1-aria2 formal qualification: PASS.** This is a benchmark-scoped result,
not an RQ2 verdict. Contract V1 remains frozen and no runner, schema, manifest,
oracle, or parity rule was changed during the run.

All seven formal records are valid; none is silently omitted. There are zero
`INVALID_EXECUTION` records and zero infrastructure/environment-attributed
failures. The formal records are distinct from the `RESMOKE-C-V1-*` evidence
set.

## Contract cells and evidence

| Workload | Frozen minimum | Observed | Result |
| --- | --- | --- | --- |
| A full build | 5 measured reps | 5; median 4494.126 ms; scale counts within the v0.2 anomaly band | PASS |
| B warm repeated build | 5 measured reps | 5; median 4561.364 ms; scale counts within the v0.2 anomaly band | PASS |
| C incremental | 3 reps for each M1–M4 | 12/12 reps: hard gate, freshness, facts parity, strict digest parity, and all state-layer parity PASS | PASS |
| D online query | 30 warm rounds | 30 rounds; 150 samples per query type; frozen manifest order and exact qualified-name anchors | PASS |

The A/B v0.2 comparison remains the contract's anomaly detector only; it is
not a substitute for C exact-state parity. All query, correctness, freshness,
scale, and performance measurements are retained in the underlying formal
records and summarized in `qualification-v1-b1-aria2-summary.json`.

## Evidence governance

The exact record names, run ids, and SHA-256 values are machine-readable in
`../results/qualification-v1-b1-aria2-summary.json`. The load note correctly
states that host load was not independently measured. No capability failure or
contract-level defect was observed, so there is no failure attribution to
perform and no basis to reopen Contract V1.

## Next phase

Proceed unchanged to **RQ2 Formal B2 Qualification — brpc**. B3 and the
cross-system RQ2 verdict remain out of scope until B2 has its own formal
evidence review.

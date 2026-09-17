# C1 Optimization Target Freeze Review — PASS

Freeze date: 2026-09-17
Baseline: `results/formal/SQI-FORMAL-20260917-1/cost-attribution-v1.json` (C0)
Deliverable: `contract/cost-optimization-targets-v1.json` (sealed, see §4)

## Verdict

**C1 target freeze: PASS.** Three optimization targets are frozen with C0
evidence attached; the non-regression floor is frozen; the implementation
boundary (what changes, what never changes) is explicit. No implementation
was touched, no experiment was run.

## 1. Frozen targets (summary)

| Target | Change (one line) | Expected effect (C0-derived estimate) | Contract amendment |
| --- | --- | --- | --- |
| OPT-T01-PROJECTION | lookup returns compact candidate rows (identity fields only) | ~40–50% of lookup row bytes; T01 productive ratio was 18.1% | no |
| OPT-T05-COMPRESSION | `code.related` resolves the code-database definition evidence in the same call (composite within the frozen surface) + same-session repeat short-circuit | T05 calls 13/10/3 → ≤4 per cell; directional cache-read reduction ≥30% for T05; measured only in C4 | no |
| OPT-IDENTITY-DEDUP | per-evidence repository/commit and per-call policy hoisted to session level | ~49 KB (~9.5%) zero-information-loss reduction | **yes — V1.2 amendment required before C4** |

## 2. Why these three (C0 evidence recap)

- T01 productive ratio 18.1%: unfiltered lookups ship up to 20 full candidate
  rows while the task consumes one declaration — projection is the lever.
- T05 cache amplification 22.6× (13/10 calls): cross-database round trips are
  the call-count hotspot; compression attacks the 15.3× replay multiplier
  directly.
- Identity/policy duplication is byte-identical repetition (34 KB + 15 KB +
  ~16 KB ids echo): pure information-preserving hoisting, but it rewrites
  frozen envelope semantics, so it is fenced behind a sealed V1.2 amendment.

## 3. Non-regression floor (frozen, binding for C4)

18/18 overall · T02 3/3 · T04 3/3 · citation closure 100% · unsupported 0 ·
source-verification compliance not lower · no new budget/truncation violations
· the T02/T04 productive evidence sets unchanged (7 CALLS edges + caller rows;
result_meta aggregates + 49 SHARD_RELATION ids + budgeted boundary_edge_ids)
· tests 48/48 keep passing · seals re-verified. Any breach → stop, attribute,
revert to the sealed V1.1 secondary state; the V1.1 baseline batch remains the
standing evidence.

## 4. Explicitly rejected (frozen)

- stripping uncited-but-returned evidence (80.2% of evidence bytes are
  productive — wholesale stripping risks the floor);
- hard %-reduction targets for C1 (cache amplification dominates; measurable
  only in C4);
- a 7th canonical call for composites (T05 compression stays inside
  `code.related`);
- cross-session caching (determinism boundary).

## 5. Measurement plan (C4, frozen)

Same 36 cells, same order, same model/config under protocol V1.1; comparison
against the V1.1 baseline batch per task on success / closure / source-
verification / sqi_calls / envelope bytes / tokens / duration. The V1.2
contract amendment must be sealed before the batch, and the updated evaluator
must be re-verified offline against all 36 baseline cells (information-
preserving rewrite proof) before any formal cell runs.

## 6. Seal

`contract/cost-optimization-targets-v1.seal.sha256` fixes this JSON. The C2
implementation commit must re-verify: contract seals, amendment seal, secondary
seal (re-created for the C2 implementation), and the 48-test floor.

# Systems Benchmark Contract V1 — Delta Review

## Decision

**HOLD**

| Question | Answer |
|---|---|
| Contract V1 ready to freeze? | **NO** |
| Formal B1/B2/B3 qualification ready? | **NO** |

The implementation closes most of the original review requirements, and no formal qualification record has been started. However, the C-workload execution order contains one `NEW_BLOCKING_DEFECT` that invalidates the claimed incremental A→B experiment. This prevents approval even though the schema accepts the smoke record.

## New Blocking Defect: C1 — Mutation Applied Before the Initial Index

The frozen contract requires `Full(A) → Mutation → Incremental(A→B) → Full(B) parity`. The runner currently executes, per C rep:

```text
copy frozen repository
→ apply_mutations(copy_dir, family)
→ initial full build into incremental.db
→ incremental_update(copy_dir, incremental.db)
→ fresh full build into full.db
→ parity comparison
```

The initial index is thus already built from mutated state B. `incremental_update()` observes no A→B change. The final B1 M4 smoke record confirms this: its incremental rep has `changed=false`, `files_changed_reported=0`, and `files_reparsed=0`, while parity passes only because both databases represent B.

Consequences:

- C does not measure incremental maintenance of the frozen mutation.
- The exact parity gate compares B-versus-B, not Incremental(A→B)-versus-Full(B).
- The freshness probe observes a state already present in the initial index; it does not establish query-visible propagation of the mutation through incremental processing.
- C's SUT clock measures a no-change incremental invocation and cannot be used for an Incremental-versus-Full comparison.

Minimum correction: build `incremental.db` from unmodified A, apply the frozen mutation only after that build returns, then invoke `incremental_update()` and compare its resulting B state with a fresh full build of B. Re-run the affected C smoke coverage after the correction. No benchmark redesign is needed.

## 13-Item Closure Matrix

| Item | Delta status | Evidence / finding |
|---|---|---|
| R1 cache terminology | CLOSED | Contract and runner use `db-fresh`, `process-cold`, `first-query`, and `warm-repeat`; `eviction_attempted=not_attempted`; OS cache is not called controlled cold. |
| R2 fresh output/configuration | CLOSED | Build child asserts fresh DB, effective configuration is canonicalized/hashed, and shard strategy is passed to measured child calls. |
| R3 measurement boundary | CLOSED | Contract/schema records RSS and CPU as `main_measured_child_only`, with Windows/POSIX semantics and no process-tree claim. |
| R4 schema enforcement | CLOSED | V2 schema validation runs before standard artifact write; final A/B/C/D smoke artifacts validate successfully. |
| R5 repetition/statistics/order | CLOSED | A warm-up is excluded; qualification minima and load note are enforced; schedule has 21 unique frozen entries; median/min/max and descriptive tail rules are recorded. |
| R6 mutation representativeness | NOT_CLOSED operationally | All three manifests contain M1–M4 and deferred limitations are explicit, but C1 means M4 is not actually applied after the A baseline and therefore does not test cross-file incremental invalidation. |
| R7 B2/B3 mutation manifests | CLOSED | B2/B3 manifests exist with four families and frozen source hashes; static hash checks pass. |
| R8 exact parity | NOT_CLOSED operationally | Six fact digests plus three strict diagnostics correctly state coverage and preserve ±10% as anomaly-only, but C1 makes the comparison B-versus-B rather than A→B-versus-Full(B). |
| R9 query-visible freshness | NOT_CLOSED operationally | The two fields and actual probe are separately implemented, but the probe runs after an initial B index and cannot demonstrate that incremental processing made mutation B query-visible. |
| R10 dual clocks | CLOSED instrumentally | All required clocks are separately recorded and SUT/harness boundaries are explicit. Under C1, the C SUT value remains unsuitable for incremental-performance interpretation. |
| R11 query workload | CLOSED | Three portable 20-query manifests cover all four query types; B1/B2/B3 smoke D records pass exact qualified-name anchor validation. |
| R12 non-LOC normalization | CLOSED | Final A smoke record contains the promised KLOC, symbol, node, and raw-reference denominators/ratios; zero denominators map to null. |
| R13 environment provenance | CLOSED | Required environment fields are emitted with `UNKNOWN` fallback; qualification CLI rejects empty `load_note`. |

## Verification Performed

- The final six cited smoke artifacts each pass `run-systems-workload-v1.py --validate`.
- All 20 stored results have `run_kind=smoke`; no formal qualification run was found.
- Schedule V1 has 21 unique entries, covering B1–B3 × A/B/C(M1–M4)/D.
- B1/B2/B3 query manifests each contain 20 queries spanning symbol, callers, callees, and subgraph.
- Mutation manifests each contain M1/M2/M3/M4 with local, file-level, and cross-file scopes; deferred rename/move, file-addition, high-fanout-header, and overlay/branch cases are explicitly retained as deferred.
- The final B1 C M4 smoke record is schema-valid but shows the C1 no-change evidence above. Schema validity therefore does not establish workload semantic validity.

## Remaining Deferred Items

These remain correctly deferred and are not grounds for this HOLD: concurrent query, external same-machine baselines, B4/B5 and 11M scale qualification, performance optimization, causal explanation of the aria2 anomaly, and agent/token amortization claims.

## Freeze Recommendation

Do not freeze the Contract V1 bundle and do not begin formal B1/B2/B3 qualification until C1 is corrected and the affected Workload C smoke regression is re-run successfully with demonstrable A→B change detection, A→B incremental parity, and an A→B freshness probe.

Once this single execution-order defect is closed, the reviewer should recheck the corrected C path only. If it passes without a new defect, freeze the contract, runner/schema identity, benchmark manifests, mutation manifests, query manifests, and Schedule V1 together. After freezing, workload membership, run order, metric definitions, and normalization rules must not be changed based on observed formal results; any correction requires a versioned amendment or supersession.

Review discipline: no formal qualification was started, no runtime was modified, no performance optimization was performed, and no causal explanation of the aria2 smoke anomaly was attempted.

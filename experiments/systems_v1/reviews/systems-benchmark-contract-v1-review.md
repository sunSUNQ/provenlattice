# Systems Benchmark Contract V1 — Methodology Review

## Decision

**APPROVE_WITH_REQUIRED_CHANGES**

The design has a sound qualification shape: frozen B1–B3 repositories, fresh-output builds, raw per-rep retention, deterministic mutation inputs, separate incremental/full-rebuild parity, and a bounded no-scale-extrapolation claim. It is not ready to freeze or to begin B1/B2/B3 formal qualification because several claimed semantics are not yet operationally enforced by the contract, schema, and runner together.

| Freeze question | Answer |
|---|---|
| Contract V1 ready to freeze? | **NO** |
| Formal B1/B2/B3 qualification ready? | **NO** |

Only the required-before-formal-run items below block those answers. Concurrent query stress, external baselines, B4/B5, and true watcher-based freshness are correctly outside V1 and must remain deferred.

## 1. Cold / Warm Cache Semantics

### Finding: process isolation is defined; filesystem coldness is not

Workload A creates a fresh DB path and a new Python child process for each rep. This reliably establishes a **fresh-output, process-isolated full build**. It does not establish a cold filesystem/page cache, and it does not reset OS cache state. Workload B uses fresh processes and fresh DBs as well, so application/database caches are not warm across measured reps; only caches outside that process, such as OS file cache and Python bytecode cache, may be warm.

The current wording—“Cold Full Build” and “OS file cache ... warm”—overstates what the runner can guarantee. No administrator action is attempted or recorded to evict page cache. Such action is platform-specific, privileged on many systems, and has no Windows/Linux-equivalent meaning under the present implementation.

**REQUIRED_BEFORE_FORMAL_RUN R1:** Rename and record cache state precisely:

- A: `fresh_output + new_process + OS_page_cache_uncontrolled`; do not call it filesystem-cold.
- B: `fresh_output + new_process + prior-run OS-cache-eligible`; do not call application/DB cache warm.
- D cold: `new_query_process + first query + OS_page_cache_uncontrolled`.
- D warm: `same query process after three warm-up rounds`; application query cache is warm only if GraphQuery actually has one and this is documented.

Record the cache-operation policy, platform, privilege requirement, and whether any cache-clearing action was performed. If no privileged OS eviction is used, record `not_attempted` rather than inferring coldness. This makes the policy reproducible on Windows and Linux without claiming equivalence where none exists.

## 2. Full Build and Resource Measurements

### Strengths

- The runner allocates an otherwise unique DB path under a new temporary work directory per build rep.
- A/B child timing surrounds `full_index`; DB size and graph counts are read after the build.
- The benchmark manifest freezes source commit, C/C++ LOC, and observed baseline scale facts.
- The required graph facts are substantially better than LOC-only reporting.

### Required corrections

**REQUIRED_BEFORE_FORMAL_RUN R2:** Enforce fresh-output and configuration identity in the run record, rather than relying on convention. The run record must record the effective parser, resolver, shard, and thread configuration (or hashes of a canonical effective configuration) and assert that the DB/output path did not exist before the rep. Current `shard_strategy` is recorded, but parser/resolver configuration hashes are absent.

**REQUIRED_BEFORE_FORMAL_RUN R3:** Define peak RSS and CPU time as metrics of the measured child process only. On Windows the code reads that process's `PeakWorkingSetSize`; on POSIX it reads `RUSAGE_SELF`. Neither is process-tree memory nor process-tree CPU time, and neither accounts for parser children/grandchildren. Either add process-tree accounting or retain the present mechanism with the explicit label `main measured child only`; do not call it total system memory consumption.

**REQUIRED_BEFORE_FORMAL_RUN R4:** Make the schema and runner enforce, rather than merely describe, workload-specific raw fields. `validate_record()` currently performs a small custom top-level check instead of validating against the stated JSON Schema; `raw_reps` permits arbitrary fields; and the schema does not require build counters, build timings, derived aggregates, parity digests, or workload-specific query/incremental data. A structurally valid-looking record can therefore omit required qualification evidence. Use the frozen schema for actual validation and add workload-specific requirements (or separate schemas) before formal runs.

## 3. Repetition and Statistics

The contract's intended policy is appropriate: retain all raw samples, report median/min/max, avoid trimming, and avoid tiny-sample significance claims. It needs enforcement and a reporting boundary.

**REQUIRED_BEFORE_FORMAL_RUN R5:**

- Fix Workload A: `workload_build()` labels all A runs as `measured`, so its configured warm-up is currently included in derived aggregates. The A warm-up must be either removed from the A protocol or labelled `warmup` and excluded, matching the contract.
- Reject qualification invocations below the frozen minima: A/B measured reps >= 5; C reps >= 3 for every frozen mutation family; D warm measured rounds >= 30. Current CLI values can be lowered without qualification rejection.
- Freeze and record the full repository/workload/cache/mutation schedule, either as one deterministic sequence or a pre-frozen rotation. Per-invocation execution leaves order effects unconstrained.
- State that P95 for build n=5 is descriptive only. P99 must be reported only with its raw sample count and as a descriptive empirical quantile; no tail-reliability or inferential significance conclusion is allowed from these small or correlated samples.

## 4. Workload C — Incremental Update

### Mutation coverage

M1 is a local function-body edit; M2 appends a new symbol to an existing file; M3 deletes one source file. They cover a local edit, a symbol addition, and tombstone/delete handling. They do not cover a public signature/header change, file addition, rename/move, cross-module relation change, high-fanout header change, or overlay/branch mutation. The three current families are therefore biased toward easy/local and deletion cases; they are not enough to support a general incremental-engineering claim.

**REQUIRED_BEFORE_FORMAL_RUN R6:** Add one minimal frozen cross-file interface mutation family (for example, a public declaration/signature change plus its necessary in-repository call-site update). This is the smallest addition that tests invalidation propagation beyond M1/M2/M3. Do not expand V1 into a comprehensive mutation suite; rename/move, overlay/branch, and high-fanout stress can remain deferred and must be stated as untested.

**REQUIRED_BEFORE_FORMAL_RUN R7:** Provide frozen C manifests for B2 and B3, not only `mutations-aria2-v1.json`. The contract requires C for all B1–B3, and no formal three-repository qualification can be run without them.

### Parity

The runner correctly compares an incremental DB against a fresh full rebuild rather than comparing approximate counts. Its current gating digest, however, does not fully substantiate the stated parity claim:

- `nodes_facts` and `edges_facts` are useful canonical graph identity checks.
- `raw_references_facts` includes only id and resolution-state fields; it excludes source-reference identity/location, raw relation/name, and candidates.
- shard state is not part of the gate.
- API fingerprint and relevant query outputs are not checked.
- strict digest mismatches are only diagnostic, despite including relevant raw-reference candidate data.

`±10%` count drift is appropriately an anomaly detector and must not replace parity.

**REQUIRED_BEFORE_FORMAL_RUN R8:** Expand the parity gate to canonical, order-independent digests covering the intended state: nodes, edges, raw-reference identity and resolution state, shard state, and a frozen API/query-visible fingerprint; alternatively reduce the documented parity scope to exactly what is gated. A strict-digest mismatch needs an explicit disposition rule before it can be ignored. Exact parity must remain incremental-versus-fresh-full-rebuild.

### Time-to-freshness and anomaly isolation

The runner currently sets `time_to_freshness_ms == update_latency_ms`, measuring only the `incremental_update()` child. It neither includes mutation completion as a measured boundary nor probes that a subsequent query observes the new graph. It is valid as an incremental command latency, but not yet as a query-visible Time-to-Freshness metric.

**REQUIRED_BEFORE_FORMAL_RUN R9:** Rename this V1 value to `incremental_command_latency_ms`, or add an explicitly timed post-update query-visibility probe before retaining the `time_to_freshness_ms` name. True watcher/agent freshness may remain deferred, but V1 must not use the stronger name without the stronger observation.

The observed aria2 `incremental > full` smoke result must remain unexplained. The current child timing excludes repository-copy, mutation-application, and parity-full-build time from the incremental child's wall time, which is good for system-under-test latency, but the contract does not separately measure harness/validation time. It also cannot decompose startup, DB open/close, shard recomputation, snapshot verification, and graph-update costs.

**REQUIRED_BEFORE_FORMAL_RUN R10:** Define and record two clocks: `system_under_test_latency` (the existing child operation timing) and `benchmark_harness_validation_overhead` (copy, mutation application, parity build/digest, and orchestration, if reported). Do not compare C and A as architectural cost unless they use the same declared clock. Preserve component counters as diagnostic evidence, but make no causal attribution from the smoke observation.

## 5. Workload D — Queries

The aria2 query manifest has 20 frozen queries: five anchors × symbol/callers/callees/subgraph. It covers the requested four query shapes and uses a transparent anchor-selection policy. It is a reasonable V1 seed, not a sufficient three-repository query qualification by itself.

**REQUIRED_BEFORE_FORMAL_RUN R11:**

- Supply frozen B2 and B3 query manifests.
- Remove or replace the machine-local `source_database` provenance field. It is not portable or replayable.
- Freeze qualified anchor identity and validate that resolved anchors match it. The runner currently resolves by `name` and selects the lexicographically minimum result, while the manifest's `anchor` string is not validated; same-name ambiguity could silently benchmark another symbol.
- Freeze query execution order or a pre-frozen rotation and record it. The current loop uses manifest order for every round.
- Report P50/P95/P99 with per-type sample count and label P99 descriptive. A warm session with 30 rounds yields multiple samples per type, but they are ordered repetitions in one process, not independent tail samples.

Cold versus warm semantics must follow R1. The current “warm” query session is a new process after a previous cold child, so it reliably has three same-process query warm-up rounds but does not retain the preceding process's application/DB cache.

## 6. Normalization, Amortization, and Environment

The contract correctly rejects LOC as the only cost denominator and retains files, nodes, raw references, and edges. The runner's `normalized_block()` only produces LOC-normalized cost plus `edges_per_node`; it does not emit the promised operational cost normalizers (`sec/1K symbols`, `MiB/1K symbols`, `DB bytes/node` or `DB bytes/reference`). It also records nodes but not a separately defined symbol count.

**REQUIRED_BEFORE_FORMAL_RUN R12:** Add the promised per-symbol/per-node and DB-per-node/reference cost fields, define whether `symbols` means all nodes or a frozen node-kind subset, and retain the raw denominators. Do not fit or claim a single LOC slope.

**REQUIRED_BEFORE_FORMAL_RUN R13:** Align environment provenance with contract §4. The runner presently records OS, OS version, a processor string, Python version, ProvenLattice head, SQLite version, and an empty `load_note`; it does not record logical/physical core counts, RAM, filesystem/storage type where available, thread configuration, compiler/tool versions, or effective configuration hashes. Record `unknown` when unavailable rather than guessing, and make `load_note` a required operator-supplied field for formal runs.

The amortization equation is a sound measurement framework. V1 retains initial-index, mutation, and query quantities, and correctly defers same-machine grep/ripgrep, BM25, and SCIP comparison. It must not claim lower total agent-token cost or lower total agent cost from system-only timings. This is **NON_BLOCKING** once raw component distributions remain retained.

## 7. Deferred Scope Is Correct

| Item | Review classification | Decision |
|---|---|---|
| Concurrent query | FUTURE | Keep `DEFERRED`; no frozen concurrency/worker/cache/error instrumentation exists. |
| External same-machine baselines | FUTURE | Keep comparative amortization claims deferred. |
| B4 >=1M LOC, B5 multi-million, ~11M | FUTURE | Keep deferred; RocksDB at 622,772 C/C++ LOC is the present scale ceiling. |
| Parser/resolver/incremental optimization | NON_BLOCKING | Do not optimize before the frozen Before series is measured. |
| Explaining aria2 incremental > full smoke | NON_BLOCKING | Record as OBSERVED only; do not infer cause. |
| RQ1 graph-fidelity repair | FUTURE | Out of scope for RQ2 contract review. |

## 8. Minimal Required Change Set and Freeze Recommendation

The minimum changes before freezing and before B1/B2/B3 formal runs are R1–R13 above. They do not redesign the benchmark: they make its existing intended semantics executable and auditable, add exactly one cross-file incremental family, and complete the already-required B2/B3 workload manifests.

After these changes, freeze the contract, schema, runner, benchmark/mutation/query manifests, and the schedule together by hash. Then run the qualification. Do not reinterpret the current aria2 smoke as a qualification result and do not make million-line or 10M-scale claims.

Review scope: methodology only. No qualification was run, no runtime was modified, and no explanation or optimization of the aria2 anomaly was attempted.

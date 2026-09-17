# C0 Cost Attribution Baseline Review — SQI Cost Optimization V1

Attribution date: 2026-09-17
Baseline: `SQI-FORMAL-20260917-1` — 18 SQI formal cells (analysis only; no new
experiments, no frozen asset modified)
Artifact: `results/formal/SQI-FORMAL-20260917-1/cost-attribution-v1.json`
(SHA-256 `b9d0c05bd21a977833bfd3dfea1e50c9318ef54d88bf81f57402d4386dae2106`)

## 1. Where the cost actually is (18 cells, 59 SQI calls)

| Source | Bytes | Share |
| --- | ---: | ---: |
| envelope total (stdout to agent) | 517,226 | 100% |
| — data (fact rows / bundle) | 190,120 | 36.8% |
| — evidence total | 247,745 | 47.9% |
| —— identity (id/kind/src/rel/tgt/**repository/commit**) | 128,799 | 24.9% |
| —— extras (provenance/confidence/**metadata**) | 73,433 | 14.2% |
| —— location (source_path/source_range) | 23,694 | 4.6% |
| —— narrative (summary) | 22,381 | 4.3% |
| — overhead (constant blocks incl. policy/budget/ids-echo) | 79,361 | 15.3% |
| source-verification reads (324 events) | 1,215,437 | — |
| tokens: input 962,640 · output 230,508 · **cache-read 14,738,944** | | |

**Cache amplification = cache_read / input = 15.3×** (native 6.5×). Every tool
turn replays the accumulated context; sessions with many calls (T05: 13 calls,
22.6×) pay O(n²)-style replay. This — not envelope bytes alone — is the
dominant cost mechanism, consistent with the working hypothesis.

## 2. Productive vs redundant payload (per task)

"Productive" = evidence bytes the agent actually cited (Evaluation Used
closure). Ratios of used / total evidence bytes:

| Task | env bytes | used ev bytes | used ratio | reading |
| --- | ---: | ---: | ---: | --- |
| T01 | 46,417 | 4,008 | 18.1% | lookup returns 44 candidates; only the definition evidence is cited → per-call projection candidate |
| T02 | 56,583 | 23,670 | **91.3%** | success is carried by the 7 frozen CALLS-edge evidences (fact_ids crosschecked) — MUST KEEP |
| T03 | 58,823 | 18,725 | 79.1% | 6 resolved refs + owner-axis rows; mostly cited |
| T04 | 170,810 | 97,869 | **88.2%** | aggregates (result_meta) + all 49 SHARD_RELATION ids cited; boundary_edge_ids listing is the budgeted remainder |
| T05 | 80,409 | 15,186 | 62.2% | 13/10/3 calls — agents re-queried across DBs; call-count reduction is the lever |
| T06 | 104,184 | 38,896 | **96.6%** | bundle is nearly fully consumed; truncation honesty adds no waste |

Cross-call duplicate evidence: only **7.4%** (18.4 KB) — pure dedup has a low
ceiling. Identity duplication inside evidence (repository+commit repeated per
entry, 105 B × 320 ≈ 34 KB, 13.7%) plus per-call constant blocks
(source_verification_policy 249 B × 59, returned_evidence_ids echo ~16 KB)
are the structural redundancies.

## 3. What drove T02/T04 success (attribution to graph facts)

- **T02**: the 7 frozen CALLS edges — returned as CALL_RELATION evidence with
  `metadata.fact_id = edge_id` and cited 6–8 ids per cell (91.3% productive).
  Without the edge-backed enumeration the native arm dropped to 1/3.
- **T04**: `result_meta` aggregates (49 / 1031 / wide_impact — judged against
  frozen ground truth) plus the 49 SHARD_RELATION evidences, cited in full
  (88.2% productive). The boundary_edge_ids listing stays budgeted/truncated.
- **T01/T03/T05/T06**: payload that did not add correctness is concentrated in
  (a) T01's 44-row candidate list (18.1% productive), (b) T05's repeated
  cross-DB querying (13/10 calls in r1/r2 — a call-count problem, not a
  payload problem), (c) evidence narrative/extras present in all tasks.

## 4. Classification (frozen rules for C1/C2/C3)

- **MUST_KEEP**: fact rows; evidence identity core; source_path/source_range;
  returned_evidence_ids(+count); budget/truncation; envelope-level
  repository/commit/generation; result_meta; params echo; metadata.fact_id.
- **SAFE_TO_DEDUP**: per-evidence repository+commit (≈34 KB, requires contract
  amendment); per-call source_verification_policy (≈15 KB, session-level,
  requires amendment); cross-call duplicate evidence (18.4 KB, no amendment).
- **ON_DEMAND**: evidence narrative summary (22 KB); evidence extras
  (provenance/confidence/metadata-minus-fact_id ≈ 60 KB); full evidence
  objects for non-cited ids (C3 progressive disclosure).
- **SAFE_TO_REMOVE**: none at field level in V1.1 — every field is consumed by
  an oracle, required by the frozen contract, or measured productive. Removals
  require the contract amendments flagged above.

## 5. Implications for C1–C3 (targets to be fixed AFTER this baseline)

- C1 (dedup) alone: ceiling ≈ 12.5% of payload (identity/policy dedup) +
  7.4% (cross-call) — real but modest.
- C2 (per-call projection): T01-style candidate lists and per-call constant
  blocks are the levers; projection must keep the task-decisive fields.
- C3 (evidence-on-demand / fewer turns): highest-leverage because cache
  amplification multiplies every saved byte by the remaining turn count;
  T05's 13-call session is the canonical target.
- Correctness floor (frozen for C4): T01–T06 ≥ 18/18, T02 3/3, T04 3/3,
  citation closure 100%, unsupported 0, budget/truncation violations 0,
  source-verification compliance not lower than baseline.

## 6. Measurement limits (disclosed)

Claude reports usage per result event, not per cost source: the token split
between system prompt / tool schema / conversation history is **measurement
unavailable**. Byte-level accounting above is exact (recomputed from
sqi-call-log envelopes and events); cache amplification is reported as a
ratio, not a byte-exact decomposition.

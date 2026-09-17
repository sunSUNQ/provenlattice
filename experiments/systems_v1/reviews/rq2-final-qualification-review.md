# RQ2 Final Qualification Review — Cross-System Evidence Synthesis — QUALIFIED

Review date: 2026-09-16

## Verdict

**RQ2 = QUALIFIED** (previously `HOLD`), limited to the SYSTEMS_BENCHMARK_CONTRACT_V1
claim scope: Windows 11, frozen benchmark commits, single machine, B1–B3 three
scale bands (118.9k / 227.2k / 622.8k C/C++ LOC), ProvenLattice V0.2
implementation, Contract V1 protocol. No concurrency, no S3+ scale bands, no
scale extrapolation. No contract-level rollback was required at any point.

This is exactly the qualification criterion frozen in Contract V1 §6:
three repos × A/B/C/D all valid runs, repetition minimums met (gates PASS),
and all gates passed.

## 1. Scope of this synthesis

No new experiments were run. This review only synthesizes and re-verifies the
existing formal evidence:

- `qualification-v1-b1-aria2-summary.json` (B1 aria2 = PASS, 7 records)
- `qualification-v1-b2-brpc-summary.json` (B2 brpc = PASS, 7 records)
- `qualification-v1-b3-rocksdb-summary.json` (B3 rocksdb = PASS, 7 records)
- 21 formal run records in total, all `run_kind=qualification`

## 2. Cross-system summary

### Workload A (cold full build) and B (warm repeated build)

| System | Role | LOC | A median | B median | Measured reps (A/B) | Scale counts vs frozen v0.2 band |
| --- | --- | ---: | ---: | ---: | --- | --- |
| B1-aria2 | Small Regression | 118,926 | 4494.126 ms | 4561.364 ms | 5 / 5 | exact on anchors (nodes 29117, raw_refs 49109, edges 37074) |
| B2-brpc | Target-like Primary | 227,154 | 8337.305 ms | 9819.849 ms | 5 / 5 | exact on anchors (nodes 48929, raw_refs 84941, edges 59614) |
| B3-rocksdb | Scale | 622,772 | 28238.675 ms | 29669.906 ms | 5 / 5 | exact on anchors (nodes 118655, raw_refs 311111, edges 143585) |

All 6 build records sit exactly on the frozen v0.2 OBSERVED anchors — the
tightest possible position inside the ±10% anomaly guard — across a 5.2× LOC
range. No silent behavioral drift.

### Workload C (incremental A→B)

36 formal incremental reps (3 repos × 4 frozen mutation families × 3 reps):

- 36/36 hard gate PASS (`changed=true`, mutation targets match frozen manifests,
  input DB verified as frozen state A before mutation)
- 36/36 freshness PASS (frozen probes observed changed state B, same sequential
  child process)
- 36/36 exact parity PASS: incremental state digests equal clean `Full(B)`
  rebuild digests for all six state layers (nodes, edges, raw_references,
  shards, files, shard_edges facts)
- 36/36 strict digest parity PASS
- Mutation coverage spans body edits, symbol additions, file deletion
  (M3, including the previously fixed cache-invalidation defect path), and
  cross-file signature changes (M4, interface-sensitive)

### Workload D (online query)

| System | Warm measured rounds | Samples/query type | Query order | Anchor validation |
| --- | ---: | ---: | --- | --- |
| B1-aria2 | 30 | 150 (×4 types) | manifest_file_order, frozen | qualified_name_exact_match |
| B2-brpc | 30 | 150 (×4 types) | manifest_file_order, frozen | qualified_name_exact_match |
| B3-rocksdb | 30 | 150 (×4 types) | manifest_file_order, frozen | qualified_name_exact_match |

1800 warm query samples total; per-system frozen query manifests
(SHA-256 seal-verified); raw per-sample latencies retained in all records.

## 3. Generality review

One frozen Contract V1, one runner, one schema, and the same gate semantics
held without modification across three heterogeneous codebases:

1. **Incremental freshness — PASS**: every freshness probe (36/36) observed the
   expected post-mutation graph state, over three different repos with
   repo-specific frozen mutation manifests.
2. **Exact parity — PASS**: 36/36 incremental results are byte-digest-equal to
   clean Full(B) rebuilds at three scales, for all six query-visible state
   layers. This is the core RQ2 correctness-of-maintenance result.
3. **Raw-reference correctness — PASS**: raw_references_facts parity 36/36;
   raw-reference scale counts exactly on frozen anchors at all three scales.
4. **Shard/file/edge state consistency — PASS**: shards_facts, files_facts,
   shard_edges_facts, edges_facts digests equal 36/36.
5. **Query ordering/anchor correctness — PASS**: identical frozen semantics
   (manifest order, exact qualified-name anchors) enforced and recorded in all
   three D records.
6. **Scale measurement stability — PASS**: counts identical to anchors across a
   5.2× LOC range; warm query medians scale smoothly with repo size
   (e.g. callees 20.8 → 32.2 → 74.1 ms; symbol 19.8 → 26.8 → 62.3 ms).

**No cross-system contradiction was found.** The three evidence sets are
mutually consistent under the same frozen protocol.

## 4. Evidence integrity review

- **Contract seal unchanged**: all 25 entries of
  `contract-v1-freeze-2026-09-16.sha256` re-hashed during this synthesis and
  matching (contract, schema, runner, resolver, integration test, all
  benchmark/mutation/query/schedule manifests). Every formal record embeds the
  sealed contract digest.
- **Record digests re-verified**: all 21 formal record SHA-256 values were
  recomputed from file bytes and match the citations in all three
  qualification summaries and in `rq2-cross-system-synthesis-v1.json`.
- **No contamination**: formal evidence references exactly the 21
  `QUALIFICATION-V1-*` records. The 12 `RESMOKE-*` smoke records, 34 superseded
  pre-freeze `SYSV1-*` records, and the 2 `.invalid` artifacts are all excluded
  from qualification evidence and none is cited as evidence anywhere.
- **No silently dropped runs**: rep counts complete and contiguous in all 21
  records (A/B: 5 measured each; C: 3 reps × 3 roles per family; D: 31 rounds
  each). `silently_dropped = 0` everywhere.
- **Run accounting**: 21 valid records; 0 `INVALID_EXECUTION`; 1
  infrastructure-attributed artifact
  (`QUALIFICATION-V1-B3-ROCKSDB-D.invalid.json` — operator launch-environment
  defect during session takeover, failed before any measurement, full D
  re-executed with identical frozen parameters; does not affect the B3
  verdict); 0 silently dropped.

## 5. Scoped observations (non-gating, carried forward)

1. **Incremental update latency exceeds cold full-build latency at all three
   scales** (B1 ~5.6–6.0 s vs 4.5 s; B2 ~10.9–14.3 s vs 8.3 s; B3 ~37.7–47.5 s
   vs 28.2 s). Per Contract V1 §6 this remains OBSERVED_ONLY — an architecture
  /attribution question for the future Before/After optimization line, not a
   qualification gate. Correctness (freshness + exact parity) is unaffected.
2. **B3 D launch-environment event** — attributed, excluded, re-executed (see
   §4). No contract, runner, schema, or manifest change was involved.

Neither observation blocks qualification; both are recorded in the synthesis
JSON for the next mainline's attention.

## 6. Conclusion

All Contract V1 qualification criteria are met across B1 aria2, B2 brpc, and
B3 rocksdb with zero contract-level blockers, zero capability failures, and no
cross-system contradictions. RQ2 formally transitions:

`RQ2 = HOLD` → **`RQ2 = QUALIFIED`**

(limited to Contract V1 scope). The Systems + Scale Qualification V1 line is
closed. The next mainline decision — Agent task qualification, structured
query interface, or another capability — is outside the scope of this
synthesis and requires no further benchmark runs under this contract.

Synthesis artifact: `results/rq2-cross-system-synthesis-v1.json`
(SHA-256 `65e81754624cdcbd09e3b510f0e279eaabdc0e4109664d4c45cd1f06f92bde67`).

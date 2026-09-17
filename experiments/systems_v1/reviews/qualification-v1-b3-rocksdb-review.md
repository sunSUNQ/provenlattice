# RQ2 Formal B3 Qualification Review — PASS

Review date: 2026-09-16

## Disposition

**B3-rocksdb formal qualification: PASS.** Contract V1 stayed frozen throughout;
no runner, schema, manifest, anomaly band, oracle, or parity rule changed.
This result is scoped to B3 and completes the three-system formal evidence set
(B1 aria2, B2 brpc, B3 rocksdb); no RQ2 cross-system verdict is claimed here.

## Formal review questions

1. **Was Contract V1 kept unmodified?** Yes. All 25 entries of the freeze seal
   (`contract-v1-freeze-2026-09-16.sha256`) were re-hashed during this review
   and match: contract, schema, runner, resolver, test integration file, and
   all benchmark/mutation/query/schedule manifests. Every formal record carries
   `contract_sha256` equal to the sealed contract digest
   (`9d7531d8840647e9…`).
2. **Are all seven formal records valid?** Yes. A, B, C-M1…C-M4, and D validate
   against the frozen `SYSTEMS_RUN_SCHEMA_V1` with zero schema errors; each is
   `run_kind=qualification` for `B3-rocksdb`.
3. **Are A/B scale counts inside the frozen anomaly band?** Yes. Both workloads
   produced 5 measured reps (+1 warmup each) with nodes=118655,
   raw_references=311111, edges=143585 — exactly the frozen v0.2 observed
   anchors, inside the ±10% band. Medians: A 28238.675 ms, B 29669.906 ms.
4. **Did C pass 12/12 hard gates, freshness, and exact parity?** Yes. M1–M4 ×
   3 reps = 12 formal incremental reps; 12/12 `workload_c_gate` PASS with
   `changed=true` and mutation targets matching the frozen manifests; 12/12
   freshness probes PASS; 12/12 strict digest parity PASS across all six state
   layers (nodes, edges, raw_references, shards, files, shard_edges facts),
   verified per-rep against the clean `Full(B)` rebuild. M3's delete-file path
   and M4's cross-file signature change behaved per frozen expectations.
5. **Did D execute the frozen workload completely?** Yes. Frozen query manifest
   `queries-rocksdb-v1.json` (SHA `51cf0408c8a26e36…`, seal-verified), 1 cold
   round, then 30 warm measured rounds in the same process after 3 in-process
   warmup rounds; 150 samples per query type (symbol/callers/callees/subgraph);
   `execution_order=manifest_file_order`, `order_frozen=true`,
   `anchor_validation=qualified_name_exact_match`; raw per-sample latencies
   retained.
6. **Any invalid execution?** Zero `INVALID_EXECUTION` inside formal evidence.
   One infrastructure-attributed artifact exists
   (`QUALIFICATION-V1-B3-ROCKSDB-D.invalid.json`): the first D launch, made by
   the taking-over operator from a shell lacking `PYTHONPATH`, failed at the
   first child build task before any measurement; the frozen runner itself
   recorded it with `infrastructure_failure` attribution. Full D was
   re-executed from scratch with identical frozen parameters; the artifact is
   retained and excluded from formal evidence.
7. **Any infrastructure/environment failure?** None affecting formal evidence;
   see item 6 for the one launch-environment event, attributed to operator
   shell setup, not to Contract V1, runner, schema, manifests, or benchmark
   capability.
8. **Any silently dropped run?** No. Rep counts are complete and contiguous in
   every record (A/B: 5 measured; C: 3 reps × 3 roles per family; D: 31 query
   rounds), and `record_classification.silently_dropped = 0`.
9. **Do summary SHA-256 values match the records?** Yes. Every digest cited in
   `qualification-v1-b3-rocksdb-summary.json` was recomputed from the record
   bytes during this review and matches exactly.
10. **Any contract-level blocker?** None. No capability failure; no evidence
    provenance gap. B1/B2 results are unaffected: the only anomaly was operator
    launch environment, after all B1/B2 records were already sealed.

## Evidence and next phase

`qualification-v1-b3-rocksdb-summary.json` lists the seven formal records, run
identifiers, SHA-256 values, verdicts, and the D infrastructure attribution.
Smoke records (`RESMOKE-*`), the superseded pre-freeze `SYSV1-*` Workload C/D
records, and the D `.invalid` artifact remain separate and are excluded from
formal qualification evidence.

Proceed to **RQ2 Cross-System Evidence Synthesis + Final Qualification Review**
over B1 aria2, B2 brpc, and B3 rocksdb. No fourth benchmark, no workload
changes, no additional performance experiments.

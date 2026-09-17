# CLOSED — Workload C M3 Delete Invalidation / Raw-Reference Candidate Cache

Status date: 2026-09-16

## Scope and root cause

The B2-brpc/M3 and B3-rocksdb/M3 exact-parity failures are closed as one
engine defect: a raw-reference cache entry could be reused after symbol
removal even though its cached `candidate_symbols` still named a removed
symbol. The defect was confined to cache validity; no parity-oracle expansion
or re-review is required.

The enforced reuse invariant is now:

1. a cached `resolved_symbol_id`, when present, must still exist; and
2. every id in cached `candidate_symbols` must still exist.

Failure of either condition forces resolution from the current symbol set.

## Repair and regression evidence

- `src/provenlattice/resolver.py` applies the invariant to both direct cache
  reuse and the post-resolution record reuse path.
- `tests/test_integration.py::IntegrationTests.test_candidate_disappearance_rebuilds_ambiguous_reference`
  indexes a repository with two candidates, deletes one candidate file, and
  requires the incremental snapshot to equal a clean rebuild. The surviving
  reference becomes a single-candidate resolved reference.
- Targeted smoke records, each one rep and `run_kind=smoke`:
  - `SYSV1-B2BRPC-C-20260916T061945Z.json` — B2-brpc/M3: valid record,
    hard gate PASS, `raw_references_facts` parity PASS, strict digest PASS.
  - `SYSV1-B3ROCKSDB-C-20260916T062127Z.json` — B3-rocksdb/M3: valid record,
    hard gate PASS, `raw_references_facts` parity PASS, strict digest PASS.

For both records, nodes, edges, files, shards, and shard-edges facts digests
also match the clean Full(B) rebuild.

## Disposition

This root-cause review is **CLOSED**. It does not qualify the system: the
formal B1/B2/B3 × M1–M4 Workload C regression has not been started and remains
the required next gate before Contract V1 freeze review.

# SUPERSEDED — Workload C records produced before the corrected execution order

Status date: 2026-09-15
Blocker ID: `WORKLOAD_C_MUTATION_ORDER` (delta review finding C1)

## Disposition

Every Workload C run record listed in section 1 is **INVALID / SUPERSEDED** and
must not be cited as evidence of incremental-update capability. The original
files are retained verbatim in `results/` (not deleted) so the audit chain
stays complete.

Reason: in the runner revisions that produced these records, the frozen
mutation was applied to the repository copy **before** the initial index was
built. The initial DB therefore already represented state B, the incremental
call observed no A→B change (`changed=false`, `files_changed_reported=0`), the
exact-parity comparison was B-vs-B, and the freshness probe observed a state
already present in the initial index. Any C record produced without the
`workload_c_gate` hard gate (added to `SYSTEMS_RUN_SCHEMA_V1`, `const true`
conditions) lacks the per-run proof that

1. the frozen mutation verifiably happened (`mutation_pre_sha256 !=
   mutation_post_sha256`, expected anchor changed),
2. the incremental input DB was built from unmodified frozen A before the
   mutation,
3. the incremental run reported `changed=true`,
4. file-touching mutations reported `files_changed_reported >= 1`.

## 1. Superseded records (retained, do not delete)

| run_id | family | sha256 | defect observed |
|---|---|---|---|
| SYSV1-B1ARIA2-C-20260915T100056Z | n/a (infra failure) | df818af68d738991d7e6b68d6de7be53c450511320894d41caae133b71917a10 | INFRASTRUCTURE_FAILURE, non-final runner identity |
| SYSV1-B1ARIA2-C-20260915T100123Z | M1 | 024caf519f2e37e69aefd533932e1860b43903de7416bd89b938989581e17728 | non-final runner identity, no gate evidence |
| SYSV1-B1ARIA2-C-20260915T100200Z | M2 | 4999bd295e3f36e8c401d4e5b0c29b78020f615cf5be1955f7d3a58930203b3f | non-final runner identity, no gate evidence |
| SYSV1-B1ARIA2-C-20260915T100216Z | M3 | 456fa72f0b90b03629270188552ad237fcd9232a554a03dad3257d0a43adcf85 | non-final runner identity, no gate evidence |
| SYSV1-B1ARIA2-C-20260915T114220Z | M4 | e86695c40d5a2b9143b24b21e5a6f0b13729935c152c7d2cd3573e4d18c17797 | changed=false, files_changed_reported=0 (B-vs-B) |
| SYSV1-B1ARIA2-C-20260915T114353Z | M3 | c1292ee338f7d9d05058aa1f616e143825116a4494b021d374df321e72d4f430 | changed=false, files_changed_reported=0 (B-vs-B) |
| SYSV1-B1ARIA2-C-20260915T114415Z | M2 | 9073f6a89fa727ae46dd364949986fe69f4de9b18d98893d721318a739204b4b | changed=false, files_changed_reported=0 (B-vs-B) |
| SYSV1-B1ARIA2-C-20260915T114924Z | M4 | 4eaf12dead5511ea29c399dc3654c03c76210f0df159098f1942898cf9d3cc69 | changed=false, files_changed_reported=0 (B-vs-B) |

Also retained as failure evidence (produced under the corrected runner, failed
on transient disk exhaustion, superseded by the M3 re-run below):
`SYSV1-B1ARIA2-C-20260915T121605Z.invalid.json`.

## 2. Superseding records (corrected execution order + hard gate)

Runner identity: `tools/run-systems-workload-v1.py` with per-rep order
`copy frozen A → Full(A) initial index → baseline-A verification against
frozen file hashes → frozen mutation → Incremental(A→B) → freshness probe →
Full(B) → exact parity`. All twelve records are schema-valid under the amended
schema with `workload_c_gate` present and all conditions true.

| benchmark | family | run_id | changed | files_changed | files_reparsed | parity | probe |
|---|---|---|---|---|---|---|---|
| B1-aria2 | M1 | SYSV1-B1ARIA2-C-20260915T121420Z | true | 1 | 1 | PASS | PASS |
| B1-aria2 | M2 | SYSV1-B1ARIA2-C-20260915T121532Z | true | 1 | 1 | PASS | PASS |
| B1-aria2 | M3 | SYSV1-B1ARIA2-C-20260915T122057Z | true | 1 | 0 | PASS | PASS |
| B1-aria2 | M4 | SYSV1-B1ARIA2-C-20260915T121622Z | true | 3 | 3 | PASS | PASS |
| B2-brpc | M1 | SYSV1-B2BRPC-C-20260915T122133Z | true | 1 | 1 | PASS | PASS |
| B2-brpc | M2 | SYSV1-B2BRPC-C-20260915T122231Z | true | 1 | 1 | PASS | PASS |
| B2-brpc | M3 | SYSV1-B2BRPC-C-20260915T122328Z | true | 1 | 0 | **FAIL** (raw_references) | PASS |
| B2-brpc | M4 | SYSV1-B2BRPC-C-20260915T122420Z | true | 3 | 3 | PASS | PASS |
| B3-rocksdb | M1 | SYSV1-B3ROCKSDB-C-20260915T122538Z | true | 1 | 1 | PASS | PASS |
| B3-rocksdb | M2 | SYSV1-B3ROCKSDB-C-20260915T122840Z | true | 1 | 1 | PASS | PASS |
| B3-rocksdb | M3 | SYSV1-B3ROCKSDB-C-20260915T123200Z | true | 1 | 0 | **FAIL** (raw_references) | PASS |
| B3-rocksdb | M4 | SYSV1-B3ROCKSDB-C-20260915T123710Z | true | 3 | 3 | PASS | PASS |

`files_reparsed=0` for M3 is by design (file deletion reparses nothing);
`files_changed_reported=1` confirms the deletion was detected. The hard gate
intentionally does not require `files_reparsed > 0`.

## 3. New finding recorded by the corrected harness (not fixed here)

The M3 delete-file family now fails exact parity on B2-brpc and B3-rocksdb,
and the corrected harness exposes this honestly instead of masking it with a
B-vs-B comparison. Divergence is confined to `raw_references`
(`raw_references_facts` / `raw_references_strict`); nodes, edges, shards,
files, and shard_edges digests all match.

Mechanism (reproduced for B2 M3, deleted file
`src/brpc/policy/esp_protocol.cpp`): 16 `list.head` CALLS references in the
surviving `test/linked_list_unittest.cc` keep `candidate_symbols` entries
pointing at symbol ids that no longer exist in `nodes` after the incremental
delete. A fresh Full(B) drops those candidates. Row identity, status, and
resolved ids are otherwise identical (84,884 rows on both sides). B1-aria2 M3
passes because the deleted file's symbols are not retained as candidates
anywhere.

Per governance, the V0.2 engine stays frozen (Before-state measurement); this
divergence is recorded as an engine-level finding for the qualification
decision, separate from the now-closed harness blocker.

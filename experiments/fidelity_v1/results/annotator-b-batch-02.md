# Annotator B — Full Annotation Batch 02

## Execution metadata

```text
annotator_id: B
agent/model: glm-5.3-flash (endpoint: 火山AI网关/glm-5.3-flash)
runtime: opencode CLI
protocol_commit: 12f405c677582a2982d035433bf6837126772716
addenda_in_force: protocol-addendum-calls-v1-macro-semantics.md (FROZEN),
                  protocol-addendum-evidence-scope-v1.md (FROZEN)
batch_manifest: full-annotation-execution-plan-v1.json, batch_02 (RATIFIED A-view order, positions 26-85)
annotation_view_sha256: 5373fdae7c99a8c1518574758819b84eb68d00dd859aee0994526c4625cea602
repository commits: aria2 9e727358, brpc ae09e960, rocksdb 37234200 (all clean, unchanged)
date: 2026-09-14
cases: 60
```

Blindness: Annotator A's records, agreement audits, adjudication products, system status /
strategy / confidence / selected targets were not consulted. Candidate identities were recovered by
read-only lookups of the blinded `candidate_symbol_ids`; four candidate-less targets were recovered
by Evidence-Scope-V1 navigation (below). No repository mutation.

## Verdict summary

| verdict | n | C/C++ in-scope | Python (audit-only) |
| --- | ---: | ---: | ---: |
| ONE_VALID_TARGET | 31 | 28 | 3 |
| NO_VALID_TARGET | 29 | 10 | 19 |
| total | 60 | 38 | 22 |

All 60 records: `build_context_status = SOURCE_SUFFICIENT`, `confidence = HIGH`, `protocol_issue`
set only for the two declaration/definition-twin cases (below). Macro references (2) judged under
the frozen CALLS_V1 rule: relation exists, no repository symbol target.

## Verdicts

| case_id | repo | rel | verdict | gold target | tags |
| --- | --- | --- | --- | --- | --- |
| FQV1-brpc-3dd084e43286f5fe | brpc | CALLS | ONE_VALID_TARGET | butil/bit_array.h:56 | — |
| FQV1-aria2-1aefa5f3f46f94f6 | aria2 | IMPORTS | ONE_VALID_TARGET | src/array_fun.h:1 | — |
| FQV1-aria2-3145cfe72c552bd9 | aria2 | REFERENCES | NO_VALID_TARGET | none (local) | — |
| FQV1-brpc-289d004dec9594de | brpc | IMPORTS | ONE_VALID_TARGET | src/bvar/detail/is_atomical.h:1 | — |
| FQV1-rocksdb-cd53a135c0fdb46a | rocksdb | IMPORTS | NO_VALID_TARGET | none (std) | — |
| FQV1-brpc-7d1c68b08b689686 | brpc | IMPORTS | ONE_VALID_TARGET | src/bvar/window.h:1 | — |
| FQV1-aria2-42189fc8a97eb196 | aria2 | CALLS | ONE_VALID_TARGET | src/DHTPingTask.cc:59 | — |
| FQV1-rocksdb-8e526ba5ac0d956a | rocksdb | CALLS | NO_VALID_TARGET | none (STL) | same_name |
| FQV1-aria2-5ce7af038ff64537 | aria2 | CALLS | ONE_VALID_TARGET | src/a2functional.h:119 | same_name |
| FQV1-rocksdb-ede7a9c26d8e7eb7 | rocksdb | IMPORTS | NO_VALID_TARGET | none (std) | conditional_compilation |
| FQV1-rocksdb-a5e3f2693abf0ca0 | rocksdb | IMPORTS | ONE_VALID_TARGET | include/rocksdb/status.h:1 | — |
| FQV1-aria2-4d8e045122db45b8 | aria2 | IMPORTS | ONE_VALID_TARGET | src/PieceStorage.h:1 | — |
| FQV1-rocksdb-db52da4576e9fbc6 | rocksdb | CALLS | ONE_VALID_TARGET | options/options_test.cc:3816 | — |
| FQV1-rocksdb-6171ade471166b66 | rocksdb | IMPORTS | NO_VALID_TARGET | none (stdlib) | — |
| FQV1-brpc-c9fe122406a9bd9d | brpc | REFERENCES | NO_VALID_TARGET | none (builtin) | same_name, cross_module_homonym |
| FQV1-rocksdb-3e14d26f5ea90348 | rocksdb | REFERENCES | NO_VALID_TARGET | none (param) | same_name, cross_module_homonym |
| FQV1-aria2-34ef1c35da5cabaf | aria2 | CALLS | ONE_VALID_TARGET | src/crypto_hash.cc:23 | — |
| FQV1-rocksdb-082b468c2a347ecc | rocksdb | IMPORTS | ONE_VALID_TARGET | util/random.h:1 | — |
| FQV1-rocksdb-98fed327423513a1 | rocksdb | IMPORTS | NO_VALID_TARGET | none (std) | — |
| FQV1-brpc-4fc2ecf5e4f15730 | brpc | CALLS | NO_VALID_TARGET | none (macro, CALLS_V1) | macro |
| FQV1-brpc-a125d96bbb5279c8 | brpc | CALLS | ONE_VALID_TARGET | src/bvar/recorder.h:427 | — |
| FQV1-rocksdb-d53fd59a6ee6cce8 | rocksdb | CALLS | ONE_VALID_TARGET | include/rocksdb/table.h:1175 | — |
| FQV1-brpc-e50f9dad96b20880 | brpc | REFERENCES | NO_VALID_TARGET | none (local) | — |
| FQV1-aria2-f57b2e43a585b7c5 | aria2 | REFERENCES | NO_VALID_TARGET | none (stdlib) | — |
| FQV1-brpc-0a0b22aaf75a2795 | brpc | IMPORTS | ONE_VALID_TARGET | src/bvar/variable.h:1 | — |
| FQV1-aria2-7e6028952b2e2c4d | aria2 | REFERENCES | NO_VALID_TARGET | none (builtin) | — |
| FQV1-brpc-d12b7bdc3ecd5bbc | brpc | CALLS | ONE_VALID_TARGET | src/bthread/bthread.cpp:335 | — |
| FQV1-rocksdb-50cde67d26537c7c | rocksdb | CALLS | ONE_VALID_TARGET | include/rocksdb/status.h:379 | — |
| FQV1-rocksdb-7d3ed2f39a8ee359 | rocksdb | REFERENCES | NO_VALID_TARGET | none (module global) | — |
| FQV1-brpc-925bccaa1f6af572 | brpc | CALLS | ONE_VALID_TARGET | src/brpc/policy/thrift_protocol.cpp:126 | — |
| FQV1-aria2-6fd1cc6573ec1b32 | aria2 | REFERENCES | NO_VALID_TARGET | none (local) | same_name, cross_module_homonym |
| FQV1-brpc-afcb7bece5fbf84d | brpc | REFERENCES | NO_VALID_TARGET | none (shadowed local) | same_name |
| FQV1-rocksdb-b24d43d6f6748681 | rocksdb | IMPORTS | ONE_VALID_TARGET | include/rocksdb/file_system.h:1 | — |
| FQV1-aria2-3417e1e85c14dc2b | aria2 | REFERENCES | NO_VALID_TARGET | none (param) | same_name, cross_module_homonym |
| FQV1-brpc-b13db4df2ae67499 | brpc | REFERENCES | NO_VALID_TARGET | none (local) | — |
| FQV1-aria2-ecbfe395c8ae229d | aria2 | IMPORTS | ONE_VALID_TARGET | src/Command.h:1 | — |
| FQV1-aria2-52bdba205b5ce686 | aria2 | CALLS | ONE_VALID_TARGET | src/HttpHeader.cc:180 | — |
| FQV1-aria2-0f84707a755b6d84 | aria2 | CALLS | NO_VALID_TARGET | none (STL) | same_name |
| FQV1-rocksdb-db9854fe698976a2 | rocksdb | CALLS | ONE_VALID_TARGET | db/blob/db_blob_direct_write_test.cc:323 | — |
| FQV1-brpc-d96f900465b7aaa4 | brpc | REFERENCES | NO_VALID_TARGET | none (builtin) | same_name, cross_module_homonym |
| FQV1-brpc-1ad645405e3e9695 | brpc | IMPORTS | ONE_VALID_TARGET | src/butil/basictypes.h:1 | — |
| FQV1-aria2-f1abdaa5d081ee7e | aria2 | REFERENCES | ONE_VALID_TARGET | doc/sphinx_themes/.../__init__.py:35 | — |
| FQV1-rocksdb-342f7be2ac886595 | rocksdb | REFERENCES | NO_VALID_TARGET | none (local) | — |
| FQV1-rocksdb-f3dbb757e4ce0c89 | rocksdb | REFERENCES | NO_VALID_TARGET | none (local) | same_name, cross_module_homonym |
| FQV1-brpc-2bf1c7b1a8381218 | brpc | REFERENCES | NO_VALID_TARGET | none (local) | same_name, cross_module_homonym |
| FQV1-rocksdb-2b8ca346737ed076 | rocksdb | IMPORTS | ONE_VALID_TARGET | table/block_based/block_builder.h:1 | — |
| FQV1-brpc-a57b6fcb67fac1a7 | brpc | IMPORTS | ONE_VALID_TARGET | src/brpc/policy/hasher.h:1 | — |
| FQV1-aria2-fae8ea276b34fa91 | aria2 | REFERENCES | NO_VALID_TARGET | none (module global) | same_name, cross_module_homonym |
| FQV1-brpc-8a70796e56274535 | brpc | CALLS | NO_VALID_TARGET | none (macro, CALLS_V1) | macro |
| FQV1-aria2-c900f72d67f383ae | aria2 | CALLS | ONE_VALID_TARGET | src/ServerStat.h:59 | — |
| FQV1-aria2-be43e19b68a9a8e9 | aria2 | IMPORTS | NO_VALID_TARGET | none (POSIX) | — |
| FQV1-brpc-847434aeda664ac6 | brpc | REFERENCES | ONE_VALID_TARGET | tools/lldb_bthread_stack.py:61 | — |
| FQV1-aria2-2a7fdb7f3a53e49a | aria2 | IMPORTS | ONE_VALID_TARGET | src/File.h:1 | — |
| FQV1-brpc-5a19585afcd8a6d6 | brpc | CALLS | ONE_VALID_TARGET | src/butil/big_endian.cc:77 | — |
| FQV1-aria2-011b30e223df40af | aria2 | IMPORTS | NO_VALID_TARGET | none (std) | — |
| FQV1-aria2-186715e883536c6f | aria2 | REFERENCES | NO_VALID_TARGET | none (param) | same_name, cross_module_homonym |
| FQV1-rocksdb-080cc91dd1133d44 | rocksdb | REFERENCES | ONE_VALID_TARGET | tools/db_crashtest_test.py:104 | — |
| FQV1-aria2-5a4f0360db806a83 | aria2 | REFERENCES | NO_VALID_TARGET | none (attr) | same_name, cross_module_homonym |
| FQV1-aria2-dc272fbb1023afed | aria2 | IMPORTS | ONE_VALID_TARGET | src/a2functional.h:1 | — |
| FQV1-aria2-a4092dc76a6af8a7 | aria2 | IMPORTS | NO_VALID_TARGET | none (external) | — |

Per-case source evidence (file:line citations, navigation chains, and candidate disqualifications)
is recorded verbatim in `annotator-b-batch-02.json` (`evidence_notes`, `evidence_locations`,
`navigation_files`).

## Notable findings (for the agreement audit / drift check)

1. **CALLS_V1 applied prospectively (2 cases).** `ASSERT_FALSE` (brpc_redis_unittest.cpp:211) and
   `EXPECT_GT` (brpc_http_rpc_protocol_unittest.cpp:2956): macro invocations count as CALLS with
   `gold_relation_exists=true` and no repository symbol target — exactly per the frozen addendum,
   with no per-sample exception. Note the contrast with the pre-freeze calibration treatment of
   `ASSERT_EQ` (B: `RELATION_NOT_PRESENT`) — the rule is doing its job.
2. **Evidence Scope V1 recovered 4 candidate-less targets (all ONE_VALID_TARGET).**
   - `in` (cookie_helper.cc:53) → `aria2.in` template at src/a2functional.h:119-122; the system
     candidate was the union FIELD `sockaddr_in in;` (a2netcompat.h:118), misclassified as Function.
   - `setStatusCode` (HttpResponseTest.cc:252) → HttpHeader::setStatusCode, definition
     src/HttpHeader.cc:180 (declaration twin src/HttpHeader.h:116).
   - `getHostname` (ServerStatManTest.cc:53) → ServerStat::getHostname at src/ServerStat.h:59.
   - `default_params` (db_crashtest_test.py:187) → navigated `load_db_crashtest` → module object →
     module-level variable at tools/db_crashtest.py:208 — a genuine referent that is NOT a graph
     symbol, hence NO_VALID_TARGET with the chain documented.
3. **Same-file shadowing (1 case).** `bthread_num` at lldb_bthread_stack.py:265 refers to the
   function-LOCAL int bound at line 264, shadowing the module-level function that the candidate
   denotes — the candidate is a real symbol but is NOT the referent. NO_VALID_TARGET, tag same_name.
4. **Candidate-quality observations (data for the audit, not protocol issues):** in 3 cases the
   system candidate was definitively not the referent (`8e526ba5` wrong-class `erase`, `0f84707a`
   same-file class method vs local `std::string` receiver, `5ce7af03` misclassified field); in 2
   cases a real Python symbol candidate existed and matched (`847434ae`, `080cc91d`, `f1abdaa5` —
   3 with candidates matched). Python genuine-target cases confirm the graph does model some
   Python functions/methods, so Python OUT_OF_SCOPE exclusion is a scope decision, not a modeling gap.
5. **OBS-DECL-DEFN-TWIN — resolved by Declaration–Definition Equivalence V1 (5 groups).** The
   owner froze `protocol-addendum-decl-def-equivalence-v1.md`: for provable same-entity
   declaration/definition twins, `acceptable_targets = [decl, defn]`, `canonical_target =
   definition`, and scoring is two-layered (Semantic Target Correctness vs Canonical Node
   Correctness) so node duplication cannot depress Precision. A systematic same-qualified-name
   query over the frozen graphs found **5** twin groups in this batch — the 2 flagged at
   annotation time (`d12b7bdc`, `52bdba20`) plus 3 found by the audit query (`42189fc8`
   DHTPingTask.h:57, `925bccaa` thrift_message.h:120, `5a19585a` big_endian.h:91). All 5 batch-02
   golds are definitions (canonical). Records were enriched additively with
   `target_equivalence_group` / `canonical_target` / `acceptable_targets[]` /
   `equivalence_reason`; no verdicts changed.
6. **Navigation-depth signal (per the plan's analysis goal):** navigation beyond the sample file
   was required in 11/60 cases; 9/10 C/C++ NO_VALID_TARGET verdicts were external-target
   (stdlib/POSIX/macro) or STL-receiver cases decidable without navigation, while ALL 4 recovered
   targets came from CALLS/REFERENCES with empty candidate lists — for the full run, candidate-less
   CALLS/REFERENCES cases are where cross-file navigation most affects target determination.

## Completion checklist

```text
60 / 60 batch-02 samples accounted for:      YES (manifest positions 26-85, set-verified)
Blindness violations:                        0
Schema violations:                           0 (full-phase schema, plan JSON)
Case alignment:                              100% (manifest == annotated ids)
Build-context completeness:                  60/60 SOURCE_SUFFICIENT (no BUILD_CONTEXT_DEPENDENT)
Repositories mutated:                        0
Protocol issues blocking:                    0 (OBS-DECL-DEFN-TWIN is a non-blocking join convention)
```

Structured records: `experiments/fidelity_v1/results/annotator-b-batch-02.json`.

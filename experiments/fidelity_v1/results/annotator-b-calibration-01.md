# ProvenLattice Graph Fidelity V1 — Annotator B Calibration Batch 01

## Execution metadata

```text
annotator_id: B
agent/model: glm-5.3-flash (endpoint: 火山AI网关/glm-5.3-flash)
agent/runtime version: opencode CLI (runtime build number not exposed in this environment)
protocol_commit: 12f405c677582a2982d035433bf6837126772716
annotation_view: experiments/fidelity_v1/results/annotator-b.json (view=BLINDED_ANNOTATION, annotator=B)
annotation_view_sha256: 5373fdae7c99a8c1518574758819b84eb68d00dd859aee0994526c4625cea602
repository commits:
  provenlattice working repo (main): 0c27e011f91a324b327751fb5859193f64b4a719
  aria2  = 9e7273583f83e881e3ec067b523ba88724088d2f  (clean)
  brpc   = ae09e960c7291605dda52356cc0c2d45567fb53e  (clean)
  rocksdb= 37234200b57d8d0a6a5c41f2d9811bbd2e293544  (clean)
start_time: 2026-09-14T16:18:31+08:00 (batch-derivation work; repo inspection began minutes earlier)
end_time:   2026-09-14T16:37:35+08:00
calibration sample count: 25
```

The frozen commit SHAs for the three benchmark repositories were cross-checked against
`benchmark-analysis/v0.2-{aria2,brpc,rocksdb}.json` and each repository's actual `git rev-parse HEAD`;
all three working trees are clean.

## Batch definition and derivation (auditable)

No artifact available to Annotator B lists the 25 calibration case IDs (the frozen README defines the
pilot but not the batch delimiter; Annotator A's files were not opened, searched, or inferred from).
Batch 01 was therefore derived deterministically and verifiably as follows:

1. The frozen `build_pilot.py` selection logic was re-executed read-only against the three frozen
   v0.2 graph databases (`benchmark-analysis/v0.2-db/*.db`), reconstructing the 269-case canonical
   package order (repos aria2/brpc/rocksdb × relations CALLS/IMPORTS/REFERENCES × strata
   RESOLVED(20)/NONRESOLVED(10), seeded per stratum). Only `raw_references.id` was read from the
   databases; no system status, strategy, confidence, provenance, or resolved-target field of any
   case was queried or displayed.
2. `random.Random("provenlattice-fidelity-v1-blind:B").shuffle` over that reconstruction reproduced
   `annotator-b.json`'s 269-case id set and case order **byte-for-byte** (`set_match=True`,
   `b_order_replication_match=True`). This proves the reconstruction of the package and of the
   per-annotator shuffle is exact.
3. Batch 01 = the first 25 case IDs of the Annotator-A seeded order
   (`random.Random("provenlattice-fidelity-v1-blind:A")`), because `calibration-execution-log.md`
   describes Batch 01 as "25 blinded cases from Annotator A". The alternative rule (first 25 of
   canonical order) would be 25× aria2 CALLS — clearly not a designed calibration batch; the derived
   batch is balanced (below). This derivation, and its risk, is recorded as Protocol Issue PI-B-1.

Batch composition: repositories aria2=11, brpc=7, rocksdb=7; relations CALLS=9, IMPORTS=8,
REFERENCES=8.

## Blindness statement

The following were never opened, searched, or inferred from: `annotator-a-calibration-01.md`,
`annotator-a.json`, any Annotator A verdict, `pilot-candidates.json`, any `system.status`,
`resolution_strategy`, `provenance`, `confidence`, system-selected target, adjudication or agreement
material. Candidate definitions were recovered via read-only lookups of the blinded
`candidate_symbol_ids` in the frozen graph databases (sanctioned by
`calibration-execution-log.md` ANNOTATION_PROTOCOL_ISSUE-001). For two ONE_VALID_TARGET cases whose
candidate lists were empty, the gold target symbol id was likewise recovered by read-only
`nodes/files` lookups driven purely by source evidence (qualified name + location); this is what
makes the "UNDER_RESOLUTION opportunity" join possible. Source repos were only read; no file in
aria2/brpc/rocksdb or in the provenlattice package was modified.

## Verdict vocabulary used (blind world-fact mapping)

The frozen protocol defines stratum-dependent verdict sets, but the blinded view hides the stratum
and the system's selected target, so `CORRECT_RESOLUTION`/`WRONG_TARGET` cannot be assessed blind.
Each verdict below is therefore recorded as a world-fact using the protocol's own enums, from which
the post-blind join can map to the stratum-specific verdicts:

- `ONE_VALID_TARGET` — a genuine relation exists and exactly one valid target is determinable from source.
- `NO_VALID_TARGET` — a genuine relation exists but no valid target exists among the candidates
  (includes: target is external to the repository, is a local binding, or candidates are homonyms).
- `RELATION_NOT_PRESENT` — the source does not perform the claimed semantic relation at that location.
- `MULTIPLE_VALID_TARGETS`, `BUILD_CONTEXT_DEPENDENT`, `INSUFFICIENT_EVIDENCE` — none applied in this batch.

`gold_relation_exists=true` means the source genuinely performs the semantic action (call / import /
reference), regardless of whether the referent is a repository symbol; `false` means it does not.

`build_context_status` uses two states: `SOURCE_SUFFICIENT` (the frozen source tree alone determines
the verdict; stable under every compilation/macro/include-path state) and `BUILD_CONTEXT_DEPENDENT`
(unused — no verdict in this batch depends on unavailable compile definitions, include paths, or
generated headers; for every include case the target header is unique in the frozen tree, and none
of the basenames collides with a plausible generated header such as `config.h`).
`difficulty_tags` use only the frozen vocabulary: same_name, overload, namespace_collision, macro,
conditional_compilation, header_definition, ambiguous_include, cross_module_homonym.

## Verdicts (25 / 25)

| # | case_id | repo | relation | verdict | gold target | tags |
|---|---------|------|----------|---------|-------------|------|
| 1 | FQV1-aria2-0b3012e7241735bd | aria2 | IMPORTS | ONE_VALID_TARGET | src/Peer.h:1 | — |
| 2 | FQV1-rocksdb-1273fbd969565cef | rocksdb | CALLS | RELATION_NOT_PRESENT | none | macro |
| 3 | FQV1-aria2-713b641e93cc620c | aria2 | CALLS | ONE_VALID_TARGET | src/ValueBase.cc:123 | overload |
| 4 | FQV1-brpc-68baef18ae4bd3ee | brpc | CALLS | ONE_VALID_TARGET | src/brpc/couchbase.h:461 | same_name |
| 5 | FQV1-rocksdb-ee83baa17e82ced3 | rocksdb | REFERENCES | NO_VALID_TARGET | none | same_name, cross_module_homonym |
| 6 | FQV1-aria2-e057f6d338d4b31b | aria2 | CALLS | ONE_VALID_TARGET | src/IOFile.cc:104 | — |
| 7 | FQV1-aria2-4fd41bb9bb827c2a | aria2 | REFERENCES | NO_VALID_TARGET | none | — |
| 8 | FQV1-brpc-edbe4d00ad31625b | brpc | IMPORTS | ONE_VALID_TARGET | src/brpc/policy/baidu_rpc_protocol.h:1 | — |
| 9 | FQV1-rocksdb-dedc59a11f94c3e6 | rocksdb | IMPORTS | ONE_VALID_TARGET | db/wide/wide_columns_helper.h:1 | — |
| 10 | FQV1-aria2-156558abc75568d8 | aria2 | CALLS | NO_VALID_TARGET | none | same_name, cross_module_homonym |
| 11 | FQV1-aria2-3ea5b21309de76eb | aria2 | REFERENCES | NO_VALID_TARGET | none | — |
| 12 | FQV1-aria2-44c700a2083beb2e | aria2 | IMPORTS | ONE_VALID_TARGET | src/SocketCore.h:1 | — |
| 13 | FQV1-brpc-a4c0999defbf0e7b | brpc | CALLS | NO_VALID_TARGET | none | — |
| 14 | FQV1-aria2-91b984d6e6d0a7ee | aria2 | CALLS | NO_VALID_TARGET | none | same_name, cross_module_homonym |
| 15 | FQV1-rocksdb-b42469d800d8d7e1 | rocksdb | IMPORTS | NO_VALID_TARGET | none | conditional_compilation |
| 16 | FQV1-aria2-5d9c6122ac7c4cd4 | aria2 | REFERENCES | NO_VALID_TARGET | none | — |
| 17 | FQV1-brpc-734b24f434825a0f | brpc | REFERENCES | NO_VALID_TARGET | none | same_name, cross_module_homonym |
| 18 | FQV1-rocksdb-042e70a2abbb97a5 | rocksdb | REFERENCES | NO_VALID_TARGET | none | same_name, cross_module_homonym |
| 19 | FQV1-brpc-b210f3349b031961 | brpc | CALLS | ONE_VALID_TARGET | src/brpc/redis_reply.h:261 | same_name |
| 20 | FQV1-aria2-9eca3ec96d005bfe | aria2 | IMPORTS | ONE_VALID_TARGET | src/FileEntry.h:1 | — |
| 21 | FQV1-brpc-2a3acc02ebb20bb4 | brpc | IMPORTS | ONE_VALID_TARGET | src/butil/threading/thread_local.h:1 | — |
| 22 | FQV1-rocksdb-6adbad5ec0ab376e | rocksdb | CALLS | ONE_VALID_TARGET | include/rocksdb/io_status.h:52 | — |
| 23 | FQV1-rocksdb-ff7dddd235f6cd6a | rocksdb | REFERENCES | NO_VALID_TARGET | none | same_name, cross_module_homonym |
| 24 | FQV1-brpc-3fe7d970be9bff2a | brpc | REFERENCES | NO_VALID_TARGET | none | same_name, cross_module_homonym |
| 25 | FQV1-aria2-4ad524eeab0b941a | aria2 | IMPORTS | ONE_VALID_TARGET | src/Segment.h:1 | — |

Totals: ONE_VALID_TARGET 12, NO_VALID_TARGET 12, RELATION_NOT_PRESENT 1; all 25
`build_context_status=SOURCE_SUFFICIENT`.

## Source verification evidence (per sample)

Each record below was verified by reading the actual source at the frozen commits; gold target
symbol/file ids are the frozen graph identities of the candidates (or, for #3, of the target
recovered by read-only lookup).

1. **FQV1-aria2-0b3012e7241735bd** (IMPORTS, src/PeerListenCommand.cc:41-42, raw_name `Peer.h`).
   Line 41 is `#include "Peer.h"`. Quoted include from `src/` resolves to `src/Peer.h`; `Peer.h` is
   the only file of that basename in the frozen tree, so no include-path state can change the
   target. Candidate `file:e18d5fe7…` = `src/Peer.h`. Unique target.
2. **FQV1-rocksdb-1273fbd969565cef** (CALLS, db/memtable_list_test.cc:749, raw_name `ASSERT_EQ`).
   Line 749 is `ASSERT_EQ(3, list.NumNotFlushed());`. `ASSERT_EQ` is a GoogleTest preprocessing
   macro (gtest/gtest.h), not a function symbol; no in-repo callable target exists for this name and
   the candidate list is empty. The real call inside the statement (`list.NumNotFlushed()`) is a
   separate reference, not this one. gold_relation_exists=false.
3. **FQV1-aria2-713b641e93cc620c** (CALLS, test/RpcMethodTest.cc:294, raw_name `req1.params->append`).
   Line 294: `req1.params->append(std::move(urisParam1));`. `RpcRequest::params` is
   `std::unique_ptr<List>` (src/RpcRequest.h:50) and `urisParam1 = List::g()` (line 292), so the
   callee is `List::append(std::unique_ptr<ValueBase>)` — defined at src/ValueBase.cc:123
   (declaration src/ValueBase.h:186); the `String::ValueType` overload (ValueBase.h:189) is not
   viable for a `unique_ptr` argument. Candidates were empty; gold target recovered read-only:
   `symbol:8588c275…` (definition; the h:186 declaration denotes the same function).
4. **FQV1-brpc-68baef18ae4bd3ee** (CALLS, src/brpc/couchbase.h:390, raw_name `MergeFrom`).
   Line 390: `MergeFrom(from);` inside the `CouchbaseResponse` copy constructor where `from` is
   `const CouchbaseResponse&`; member lookup resolves to `CouchbaseResponse::MergeFrom(const
   CouchbaseResponse&)` declared at couchbase.h:461. Candidate `CouchbaseRequest::MergeFrom`
   (couchbase.h:359) is a different class, unreachable in this scope. Gold =
   `symbol:84b06e72…`.
5. **FQV1-rocksdb-ee83baa17e82ced3** (REFERENCES, build_tools/gtest_parallel.py:920, raw_name
   `logger`). Line 920: `logger.log_tasks(len(tasks))` — refers to the function-local
   `logger = FilterFormat(options.output_dir)` (line 914) inside `main()`. All 25 candidates are
   unrelated `logger` functions/members/types in other files (C++ and Python); local variables are
   not graph nodes. No valid target.
6. **FQV1-aria2-e057f6d338d4b31b** (CALLS, src/IOFile.cc:83, raw_name `eof`).
   Line 83: `if (eof())` inside `IOFile::getLine()`; implicit-this member call resolves to
   `IOFile::eof()` defined at src/IOFile.cc:104. Candidate `symbol:0f3dfdfa…` matches. (Blind
   record's owner_kind is `File` — a parser owner-attribution quirk; enclosing method is getLine.)
7. **FQV1-aria2-4fd41bb9bb827c2a** (REFERENCES, doc/manual-src/en/mkapiref.py:256, raw_name `re`).
   Line 256: `typedef = re.sub(...)` — refers to the module object `re` imported at line 36
   (`import re, sys, argparse`); the referent is the Python standard-library module, not a
   repository symbol; candidates empty. No valid target.
8. **FQV1-brpc-edbe4d00ad31625b** (IMPORTS, src/brpc/stream.cpp:31-32, raw_name
   `brpc/policy/baidu_rpc_protocol.h`). Line 31 is the include; resolves via the `src/` include
   root; header unique in the frozen tree. Candidate `file:1f322372…` matches. Unique target.
9. **FQV1-rocksdb-dedc59a11f94c3e6** (IMPORTS, db/wide/wide_columns_helper.cc:6-7, raw_name
   `db/wide/wide_columns_helper.h`). Line 6 is the include; repo-root-relative path; header unique
   in the frozen tree. Candidate `file:0aa05803…` matches. Unique target.
10. **FQV1-aria2-156558abc75568d8** (CALLS, test/Base64Test.cc:54, raw_name `s.begin`).
    Line 54: `... base64::encode(s.begin(), s.end())` with `std::string s` (line 27); `s.begin()`
    is `std::string::begin()`, an STL member outside the repository. All 15 candidates are
    aria2-class `begin` methods (Dict/List/IndexedList/etc.); none is std::string::begin.
    No valid target.
11. **FQV1-aria2-3ea5b21309de76eb** (REFERENCES, mkapiref.py:128, raw_name `infile`).
    Line 128: `line = infile.readline()` — the loop variable from `for infile in infiles:` (line
    122); a function-local binding, not a repository-level symbol; candidates empty. No valid target.
12. **FQV1-aria2-44c700a2083beb2e** (IMPORTS, src/util.cc:86-87, raw_name `SocketCore.h`).
    Line 86: `#include "SocketCore.h"`; quoted include from `src/` resolves to src/SocketCore.h;
    unique basename. Candidate `file:ce7a7881…` matches. Unique target.
13. **FQV1-brpc-a4c0999defbf0e7b** (CALLS, test/brpc_rdma_unittest.cpp:1844, raw_name `htons`).
    Line 1844: `addr.sin_port = htons(PORT);` — POSIX `htons` (arpa/inet.h), a platform API outside
    the repository; candidates empty; no in-repo target exists under any platform configuration.
    Relation exists; no valid target.
14. **FQV1-aria2-91b984d6e6d0a7ee** (CALLS, mkapiref.py:48, raw_name `print`).
    Line 48: `print('    {}'.format(line))` inside `FunctionDoc.write` — the Python builtin `print`
    (no shadowing definition in the file). Sole candidate `aria2.bittorrent.print`
    (src/bittorrent_helper.h:342, C++ function) is a cross-language homonym, not the callee.
    No valid target.
15. **FQV1-rocksdb-b42469d800d8d7e1** (IMPORTS, db/forward_iterator_bench.cc:21-22, raw_name
    `climits`). Line 21: `#include <climits>` — C++ standard header, external to the repository;
    candidates empty. The directive sits in the final `#else` branch after `#if !defined(GFLAGS)`
    (line 6) and `#elif defined(OS_MACOSX) || defined(OS_WIN)` (line 12): compiled only with
    GFLAGS on non-macOS/non-Windows. Under every macro state the header is never a repository file,
    so the verdict is stable (tag conditional_compilation records the conditional context).
    Relation exists; no valid target.
16. **FQV1-aria2-5d9c6122ac7c4cd4** (REFERENCES, mkapiref.py:237, raw_name `func_proto`).
    Line 237: `func_proto.append(line)` — the function-local list bound at line 229 inside
    `process_function`; local binding; candidates empty. No valid target.
17. **FQV1-brpc-734b24f434825a0f** (REFERENCES, tools/gdb_bthread_stack.py:192, raw_name
    `bthreads`). Line 192: `len(bthreads)` — the module-level Python global `bthreads = []`
    (line 54; `global bthreads` in `invoke`). The three candidates are unrelated C++ TEST helper
    functions named `bthreads` (test/bthread_semaphore_unittest.cpp:171,
    test/bthread_rwlock_unittest.cpp:255, test/bthread_mutex_unittest.cpp:259). No valid target.
18. **FQV1-rocksdb-042e70a2abbb97a5** (REFERENCES, build_tools/getdeps_fallback_mirror.py:103,
    raw_name `chunk`). Line 103: `if not chunk:` — the local variable bound at line 102 inside
    `download_url`. Sole candidate `TEST_F.chunk` is the C++ local `Slice chunk;`
    (table/sst_file_reader_test.cc:729) — cross-module homonym. No valid target.
19. **FQV1-brpc-b210f3349b031961** (CALLS, test/brpc_redis_unittest.cpp:1217, raw_name
    `response.reply(0).c_str`). Line 1217: `ASSERT_STREQ("OK", response.reply(0).c_str());` with
    `brpc::RedisResponse response;` (line 1174) and `const RedisReply& reply(int index) const`
    (src/brpc/redis.h:151); the callee is `RedisReply::c_str() const`, inline-defined at
    src/brpc/redis_reply.h:261-272. Other c_str candidates (`butil::IPStr::c_str`,
    `butil::EndPointStr::c_str`) belong to types not involved. Gold = `symbol:3d377a7e…`.
    Unique target.
20. **FQV1-aria2-9eca3ec96d005bfe** (IMPORTS, src/Context.cc:62-63, raw_name `FileEntry.h`).
    Line 62: `#include "FileEntry.h"`; quoted include from `src/`; unique basename. Candidate
    `file:261e1e6a…` matches. Unique target.
21. **FQV1-brpc-2a3acc02ebb20bb4** (IMPORTS, test/thread_local_unittest.cc:7-8, raw_name
    `butil/threading/thread_local.h`). Line 7 is the include; resolves via the `src/` include root;
    the written relative path uniquely selects src/butil/threading/thread_local.h (sibling
    src/butil/thread_local.h does not match the written path). Candidate `file:161224b8…` matches.
    Unique target.
22. **FQV1-rocksdb-6adbad5ec0ab376e** (CALLS, db/error_handler_fs_test.cc:2844, raw_name
    `st.SetRetryable`). Line 2844: `st.SetRetryable(true);` with `IOStatus st = IOStatus::IOError();`
    (line 2843); callee `IOStatus::SetRetryable(bool)`, inline-defined at
    include/rocksdb/io_status.h:52 — the only `SetRetryable` declaration in repository headers.
    Candidate `symbol:71b23f03…` matches. Unique target.
23. **FQV1-rocksdb-ff7dddd235f6cd6a** (REFERENCES, tools/advisor/advisor/db_stats_fetcher.py:197,
    raw_name `entities`). Line 197: `self.entities = entities` — the `__init__` parameter `entities`
    (line 194). Sole candidate is the C++ member `LazyWideColumnsBatch::Rep::entities`
    (db/wide/lazy_wide_columns.cc:262) — cross-module homonym. No valid target.
24. **FQV1-brpc-3fe7d970be9bff2a** (REFERENCES, tools/lldb_bthread_stack.py:224, raw_name
    `started`). Line 224: `if not global_state.started:` — the instance attribute `started` of
    `GlobalState` (bound at lines 57/62; `global_state = GlobalState()` at line 84). Sole candidate
    is a C++ function `started` (src/bthread/fd.cpp:310-312) — cross-language, cross-module homonym.
    No valid target.
25. **FQV1-aria2-4ad524eeab0b941a** (IMPORTS, test/BtDependencyTest.cc:13-14, raw_name
    `Segment.h`). Line 13: `#include "Segment.h"`; not present in `test/`, so it resolves via the
    project include path to src/Segment.h — the only `Segment.h` in the frozen tree (uniqueness
    makes include-path specifics irrelevant). Candidate `file:fa222219…` matches. Unique target.

## Build Context assessment

No verdict in this batch required compile definitions, include-path disambiguation, generated
headers, or platform state:

- All 6 same-directory/quoted includes (#1, #8, #9, #12, #20, #25) target headers that are unique
  in the frozen tree; #21 is disambiguated by its written relative path.
- The one conditional-compilation context (#15) is macro-state-independent for its verdict
  (`<climits>` is never a repository file); the condition is recorded as a difficulty tag.
- The macro case (#2) is identifiable as a macro from the visible source and its include of
  gtest; no expansion context was needed for the verdict.
- `BUILD_CONTEXT_DEPENDENT` was therefore not used; all 25 records use `SOURCE_SUFFICIENT`.

## Protocol issues

- **PI-B-1 (batch delimitation gap).** The frozen protocol (README at 12f405c) does not define how
  the 25 calibration sample IDs are delimited, and no batch manifest is available to Annotator B;
  Annotator A's files could not be consulted. Batch 01 was derived as the first 25 case IDs of the
  deterministic Annotator-A blinded view order, with full verification that the package/shuffle
  reconstruction is exact (269/269 set match; B-order byte-exact match). Risk: if Annotator A's
  actual batch was delimited by a different rule, adjudication will observe a sample mismatch; the
  derivation above is reproducible for that review. No verdict in this record depends on this
  choice beyond sample membership.
- **PI-B-2 (carries over ANNOTATION_PROTOCOL_ISSUE-001).** The blinded package supplies only
  `candidate_symbol_ids` without candidate definitions. As sanctioned in
  `calibration-execution-log.md`, candidate definitions were recovered by read-only lookups in the
  frozen graph databases; for two candidate-less ONE_VALID_TARGET cases (#3, and generally where
  candidates were empty) the gold target id was recovered by read-only `nodes/files` lookups driven
  by source evidence, enabling the UNDER_RESOLUTION join. No system status/strategy/confidence/
  selected-target field was ever read.
- **PI-B-3 (blind verdict vocabulary).** The frozen protocol defines stratum-dependent verdict sets,
  but the blinded view hides the stratum and the system's selected target, so
  `CORRECT_RESOLUTION`/`WRONG_TARGET` are not assessable blind. Verdicts are recorded as blind
  world-facts from the protocol's own enum set (see mapping above); the join to system status can
  map them to the stratum-specific verdicts without changing their semantics. No new verdict
  category was introduced.
- **PI-B-4 (language scope observation).** The pilot README scopes the pilot to C/C++, but the
  frozen V0.2 graph databases also yielded Python-source cases (doc tooling, build tools, debugger
  helpers) in this batch (#5, #7, #11, #14, #16, #17, #18, #23, #24). Each was judged by the
  language-appropriate semantics of IMPORTS (import statement), CALLS (call expression) and
  REFERENCES (name/attribute reference). No verdict-semantics change; noted for the stratum report.

## Completion checklist

```text
25 / 25 calibration samples accounted for:        YES
Annotator A results read:                          NO (files not opened/searched/inferred)
System status / strategy / confidence read:        NO
Target source repositories modified:               NO (read-only navigation only)
Verdicts conform to frozen schema enums:           YES (world-fact mapping documented, PI-B-3)
Source verification traceable per sample:          YES (file:line evidence per record)
Repository mutation:                               0 (aria2/brpc/rocksdb clean at frozen commits)
```

Structured records: `experiments/fidelity_v1/results/annotator-b-calibration-01.json`
(annotator-b blind-view schema, 25 annotated cases, batch-derivation metadata included).

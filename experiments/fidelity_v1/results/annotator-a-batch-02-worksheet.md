# Annotator A — batch_02 Worksheet

## Execution boundary

```text
annotator_id: A
batch: batch_02 (60 cases, A-view order)
source: blinded annotation view only (no system status, strategy, confidence,
        selected target, stratum, other annotator records, or audit results)
evidence: Evidence Scope V1 - read-only navigation inside the frozen repository
          commits + frozen Build Context fields; no network source retrieval
formal_verdict vocabulary (blind world-fact space; stratum join post-hoc):
  ONE_VALID_TARGET | NO_VALID_TARGET | MULTIPLE_VALID_TARGETS | RELATION_NOT_PRESENT | BUILD_CONTEXT_DEPENDENT | INSUFFICIENT_EVIDENCE
difficulty_tags vocabulary (frozen):
  same_name | overload | namespace_collision | macro | conditional_compilation | header_definition | ambiguous_include | cross_module_homonym
decl/def twins (Decl/Def Equivalence V1, FROZEN): record the target your source
  evidence establishes; equivalence groups are joined at scoring time
navigation: list every file read beyond the sample's own file (navigation_files)
  and path:line anchors for the deciding evidence (evidence_locations)
INSUFFICIENT_EVIDENCE only when undeterminable under the full Evidence Scope V1;
EVIDENCE_SCOPE_TOO_NARROW is never a verdict
```

## 1. FQV1-brpc-3dd084e43286f5fe

- repository: brpc   relation: CALLS
- source: `src/brpc/policy/couchbase_protocol.cpp:60-60`
- owner: Function `brpc.policy.InitSupportedCommandMap`
- raw_name: `butil.bit_array_set`
- candidates: 1
  - `symbol:2120f70de2d20dea843db10deb8f1b34594b85d901d245770e82c8369e5449ed`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 2. FQV1-aria2-1aefa5f3f46f94f6

- repository: aria2   relation: IMPORTS
- source: `test/SessionSerializerTest.cc:10-11`
- owner: File `test.SessionSerializerTest`
- raw_name: `array_fun.h`   target_module: `array_fun.h`
- candidates: 1
  - `file:3c7d4956d7f9a24049f4490bbbfe62d27ba32de816b442a30403910850d7b736`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 3. FQV1-aria2-3145cfe72c552bd9

- repository: aria2   relation: REFERENCES
- source: `doc/bash_completion/make_bash_completion.py:78-78`
- owner: Function `doc.bash_completion.make_bash_completion.output_case`
- raw_name: `bool_opts`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 4. FQV1-brpc-289d004dec9594de

- repository: brpc   relation: IMPORTS
- source: `src/bvar/detail/combiner.h:32-33`
- owner: File `src.bvar.detail.combiner`
- raw_name: `bvar/detail/is_atomical.h`   target_module: `bvar/detail/is_atomical.h`
- candidates: 1
  - `file:e683770d7b1e7ab1c02b1375fb15653eb3ce38a5baef8db0ee2304a931b135cc`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 5. FQV1-rocksdb-cd53a135c0fdb46a

- repository: rocksdb   relation: IMPORTS
- source: `utilities/backup/backup_engine.cc:13-14`
- owner: File `utilities.backup.backup_engine`
- raw_name: `cstdlib`   target_module: `cstdlib`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 6. FQV1-brpc-7d1c68b08b689686

- repository: brpc   relation: IMPORTS
- source: `src/brpc/backup_request_policy.cpp:22-23`
- owner: File `src.brpc.backup_request_policy`
- raw_name: `bvar/window.h`   target_module: `bvar/window.h`
- candidates: 1
  - `file:9bfdc0e6637519f3eb66fbf037e8d7d4cc2dd13878cb86b34005691e1f838e1f`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 7. FQV1-aria2-42189fc8a97eb196

- repository: aria2   relation: CALLS
- source: `src/DHTPingTask.cc:82-82`
- owner: File `src.DHTPingTask`
- raw_name: `addMessage`
- candidates: 1
  - `symbol:1d11e23277061fca299b5f8ade3f56e8f89d636f227aa80616e1040d30257d6f`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 8. FQV1-rocksdb-8e526ba5ac0d956a

- repository: rocksdb   relation: CALLS
- source: `utilities/blob_db/blob_db_impl.cc:1631-1631`
- owner: File `utilities.blob_db.blob_db_impl`
- raw_name: `open_ttl_files_.erase`
- candidates: 1
  - `symbol:6a35a63b78c638c0bbe768f2482f6b0857eb89406f8e09c0df6b0d26298af053`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 9. FQV1-aria2-5ce7af038ff64537

- repository: aria2   relation: CALLS
- source: `src/cookie_helper.cc:53-53`
- owner: Function `aria2.cookie.anonymous.isDelimiter`
- raw_name: `in`
- candidates: 1
  - `symbol:e19297531ee5fab31d81e5e0ac59396d114a74bdb947027273f512c0f8ab22fd`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 10. FQV1-rocksdb-ede7a9c26d8e7eb7

- repository: rocksdb   relation: IMPORTS
- source: `db_stress_tool/db_stress_listener.h:10-11`
- owner: File `db_stress_tool.db_stress_listener`
- raw_name: `mutex`   target_module: `mutex`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 11. FQV1-rocksdb-a5e3f2693abf0ca0

- repository: rocksdb   relation: IMPORTS
- source: `options/customizable.cc:13-14`
- owner: File `options.customizable`
- raw_name: `rocksdb/status.h`   target_module: `rocksdb/status.h`
- candidates: 1
  - `file:887db6db839168314ccee6fccc7350c92367c52f804f39d2da2cbf2ef6e6658f`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 12. FQV1-aria2-4d8e045122db45b8

- repository: aria2   relation: IMPORTS
- source: `src/BtRegistry.cc:39-40`
- owner: File `src.BtRegistry`
- raw_name: `PieceStorage.h`   target_module: `PieceStorage.h`
- candidates: 1
  - `file:64ab4a80f7bf1ca48903f30fadea77c5590e85a156e5100af48f6ff4776014e3`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 13. FQV1-rocksdb-db52da4576e9fbc6

- repository: rocksdb   relation: CALLS
- source: `options/options_test.cc:3861-3861`
- owner: Function `ROCKSDB_NAMESPACE.TEST_F`
- raw_name: `testCase`
- candidates: 1
  - `symbol:d5170e1674f30f1b663c712eb32a2ddb4403935361f2b4f3f8a6cda58d27f7da`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 14. FQV1-rocksdb-6171ade471166b66

- repository: rocksdb   relation: IMPORTS
- source: `tools/advisor/advisor/db_log_parser.py:11-11`
- owner: File `tools.advisor.advisor.db_log_parser`
- raw_name: `Enum`   target_module: `enum`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 15. FQV1-brpc-c9fe122406a9bd9d

- repository: brpc   relation: REFERENCES
- source: `tools/gdb_bthread_stack.py:171-171`
- owner: Method `tools.gdb_bthread_stack.BthreadAllCmd.invoke`
- raw_name: `format`
- candidates: 1
  - `symbol:d5fa05eec334493162a7da4aa4c6db84ea9cd626ba927e7ac325ff9846540d1b`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 16. FQV1-rocksdb-3e14d26f5ea90348

- repository: rocksdb   relation: REFERENCES
- source: `tools/fault_injection_log_parser.py:158-158`
- owner: Function `tools.fault_injection_log_parser.decode_fault_injection_log`
- raw_name: `raw_path`
- candidates: 1
  - `symbol:5ba74801add67a52df59f4431b10fabe6a57ad647448d4ea15d4dee1d7e52408`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 17. FQV1-aria2-34ef1c35da5cabaf

- repository: aria2   relation: CALLS
- source: `src/crypto_hash.cc:464-464`
- owner: Method `SHA1.transform`
- raw_name: `rol`
- candidates: 1
  - `symbol:501a588b71d1a34ec7fcb64a0fac62331f35555c729df0b84bb0743c53c16f1d`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 18. FQV1-rocksdb-082b468c2a347ecc

- repository: rocksdb   relation: IMPORTS
- source: `db/db_compaction_test.cc:35-36`
- owner: File `db.db_compaction_test`
- raw_name: `util/random.h`   target_module: `util/random.h`
- candidates: 1
  - `file:7ddec5b715631f57881516d7e3deca7420147302752a531e9e1299be7375112a`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 19. FQV1-rocksdb-98fed327423513a1

- repository: rocksdb   relation: IMPORTS
- source: `file/writable_file_writer.cc:13-14`
- owner: File `file.writable_file_writer`
- raw_name: `cstdio`   target_module: `cstdio`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 20. FQV1-brpc-4fc2ecf5e4f15730

- repository: brpc   relation: CALLS
- source: `test/brpc_redis_unittest.cpp:211-211`
- owner: Function `anonymous.TEST_F`
- raw_name: `ASSERT_FALSE`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 21. FQV1-brpc-a125d96bbb5279c8

- repository: brpc   relation: CALLS
- source: `src/bvar/recorder.h:193-193`
- owner: Method `bvar.IntRecorder.set_debug_name`
- raw_name: `diagnostic_name`
- candidates: 1
  - `symbol:0f4c9a02797cfe969b154e95d7d155be79ff9b7a0225ca68d117a033e7d5c20a`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 22. FQV1-rocksdb-d53fd59a6ee6cce8

- repository: rocksdb   relation: CALLS
- source: `table/block_based/block_based_table_factory.h:58-58`
- owner: Method `ROCKSDB_NAMESPACE.BlockBasedTableFactory.kClassName`
- raw_name: `kBlockBasedTableName`
- candidates: 1
  - `symbol:50bf01b6c74deec9f9c5a3dd50692be061189a5b26d74dbaa7cd82df9b58e253`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 23. FQV1-brpc-e50f9dad96b20880

- repository: brpc   relation: REFERENCES
- source: `tools/lldb_bthread_stack.py:91-91`
- owner: Function `tools.lldb_bthread_stack.get_child`
- raw_name: `childs_value_list`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 24. FQV1-aria2-f57b2e43a585b7c5

- repository: aria2   relation: REFERENCES
- source: `doc/manual-src/en/mkapiref.py:82-82`
- owner: Method `doc.manual-src.en.mkapiref.StructDoc.write`
- raw_name: `re`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 25. FQV1-brpc-0a0b22aaf75a2795

- repository: brpc   relation: IMPORTS
- source: `src/bvar/passive_status.h:23-24`
- owner: File `src.bvar.passive_status`
- raw_name: `bvar/variable.h`   target_module: `bvar/variable.h`
- candidates: 1
  - `file:a64c2c576e9a6f5420ed47c4aba6dc9dd5a620fa9edf0543e343f44dd2d36deb`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 26. FQV1-aria2-7e6028952b2e2c4d

- repository: aria2   relation: REFERENCES
- source: `doc/manual-src/en/mkapiref.py:90-90`
- owner: Method `doc.manual-src.en.mkapiref.StructDoc.write`
- raw_name: `endswith`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 27. FQV1-brpc-d12b7bdc3ecd5bbc

- repository: brpc   relation: CALLS
- source: `test/bthread_unittest.cpp:184-184`
- owner: Function `anonymous.misc`
- raw_name: `bthread_start_urgent`
- candidates: 2
  - `symbol:82120524ca00e8c9d25fe43f384959c0fc33f42a3abfd9f6a914232b8541d488`
  - `symbol:f33946fda2e5c4f4f7d3314a6d9677fa94b8e8cab2c983f15d7ba8674f5d0fd4`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 28. FQV1-rocksdb-50cde67d26537c7c

- repository: rocksdb   relation: CALLS
- source: `utilities/transactions/write_committed_transaction_ts_test.cc:944-946`
- owner: Function `ROCKSDB_NAMESPACE.TEST_P`
- raw_name: `txn3->GetForUpdate(ReadOptions(), handles_[1], "key", &value, /*exclusive=*/true, /*do_validate=*/false) .IsInvalidArgument`
- candidates: 1
  - `symbol:e3914a04fe233add7ea49eeb9cb512edddbbb00fbac1bca1aa72dedcf9d12c8c`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 29. FQV1-rocksdb-7d3ed2f39a8ee359

- repository: rocksdb   relation: REFERENCES
- source: `tools/db_crashtest_test.py:187-187`
- owner: Method `tools.db_crashtest_test.DBCrashTestTest.test_cache_and_write_buffer_size_multiplier_respects_write_buffer_minimum`
- raw_name: `default_params`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 30. FQV1-brpc-925bccaa1f6af572

- repository: brpc   relation: CALLS
- source: `src/brpc/policy/thrift_protocol.cpp:645-646`
- owner: Function `brpc.policy.ProcessThriftResponse`
- raw_name: `ReadThriftStruct`
- candidates: 1
  - `symbol:df8342fb962201cc97efb91bc2901003646af5f990e2209bb43e46a908b84a0e`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 31. FQV1-aria2-6fd1cc6573ec1b32

- repository: aria2   relation: REFERENCES
- source: `doc/bash_completion/make_bash_completion.py:36-36`
- owner: Function `doc.bash_completion.make_bash_completion.get_all_options`
- raw_name: `opts`
- candidates: 1
  - `symbol:827f6468eadb4d3dea44f00993819f61a937811e0b153df68c58af71200a7d65`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 32. FQV1-brpc-afcb7bece5fbf84d

- repository: brpc   relation: REFERENCES
- source: `tools/lldb_bthread_stack.py:265-265`
- owner: Function `tools.lldb_bthread_stack.bthread_all`
- raw_name: `bthread_num`
- candidates: 1
  - `symbol:e954e36d5a22bdc85cd39e4213b078175a33e70ef6d51b3ed343f6daeb9869cf`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 33. FQV1-rocksdb-b24d43d6f6748681

- repository: rocksdb   relation: IMPORTS
- source: `logging/auto_roll_logger.cc:13-14`
- owner: File `logging.auto_roll_logger`
- raw_name: `rocksdb/file_system.h`   target_module: `rocksdb/file_system.h`
- candidates: 1
  - `file:4a13cc5105443e7dac136092aa4fc851a01b11eacb37597da27a8ce949aa842f`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 34. FQV1-aria2-3417e1e85c14dc2b

- repository: aria2   relation: REFERENCES
- source: `doc/bash_completion/make_bash_completion.py:126-126`
- owner: Function `doc.bash_completion.make_bash_completion.output_case`
- raw_name: `opts`
- candidates: 1
  - `symbol:827f6468eadb4d3dea44f00993819f61a937811e0b153df68c58af71200a7d65`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 35. FQV1-brpc-b13db4df2ae67499

- repository: brpc   relation: REFERENCES
- source: `tools/lldb_bthread_stack.py:140-140`
- owner: Function `tools.lldb_bthread_stack.get_all_bthreads`
- raw_name: `long_type`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 36. FQV1-aria2-ecbfe395c8ae229d

- repository: aria2   relation: IMPORTS
- source: `src/DHTEntryPointNameResolveCommand.h:38-39`
- owner: File `src.DHTEntryPointNameResolveCommand`
- raw_name: `Command.h`   target_module: `Command.h`
- candidates: 1
  - `file:8ea1c2d1e68c65dcacbe20bbe8692bfbbe98ca3e66bca708677a07098cd95854`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 37. FQV1-aria2-52bdba205b5ce686

- repository: aria2   relation: CALLS
- source: `test/HttpResponseTest.cc:252-252`
- owner: File `test.HttpResponseTest`
- raw_name: `httpResponse.getHttpHeader()->setStatusCode`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 38. FQV1-aria2-0f84707a755b6d84

- repository: aria2   relation: CALLS
- source: `src/CookieStorage.cc:159-159`
- owner: File `src.CookieStorage`
- raw_name: `data.size`
- candidates: 1
  - `symbol:09276028ee2eb90c14b4bb3cb04035b818d1419fca335ca7284be69ec847572c`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 39. FQV1-rocksdb-db9854fe698976a2

- repository: rocksdb   relation: CALLS
- source: `db/blob/db_blob_direct_write_test.cc:687-687`
- owner: Function `ROCKSDB_NAMESPACE.TEST_F`
- raw_name: `CountBlobFiles`
- candidates: 1
  - `symbol:a270cc1c657d60e23819c531d77190a6ad93841769c35562a0e0548d00d1f2ac`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 40. FQV1-brpc-d96f900465b7aaa4

- repository: brpc   relation: REFERENCES
- source: `tools/gdb_bthread_stack.py:144-144`
- owner: Method `tools.gdb_bthread_stack.BthreadFrameCmd.invoke`
- raw_name: `format`
- candidates: 1
  - `symbol:d5fa05eec334493162a7da4aa4c6db84ea9cd626ba927e7ac325ff9846540d1b`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 41. FQV1-brpc-1ad645405e3e9695

- repository: brpc   relation: IMPORTS
- source: `src/butil/debug/stack_trace.cc:7-8`
- owner: File `src.butil.debug.stack_trace`
- raw_name: `butil/basictypes.h`   target_module: `butil/basictypes.h`
- candidates: 1
  - `file:e648967fee36d71ea4533f1e619c6a14f8be1824df3a12cc00e58cd91f3c8852`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 42. FQV1-aria2-f1abdaa5d081ee7e

- repository: aria2   relation: REFERENCES
- source: `doc/sphinx_themes/sphinx_rtd_theme/__init__.py:75-75`
- owner: Function `doc.sphinx_themes.sphinx_rtd_theme.setup`
- raw_name: `extend_html_context`
- candidates: 1
  - `symbol:141d0477ddcc5263cca41d93af610f9467400ac1fdcee867634b27ae4ea71f22`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 43. FQV1-rocksdb-342f7be2ac886595

- repository: rocksdb   relation: REFERENCES
- source: `tools/c_api_gen/gen_roundtrip_tests.py:167-167`
- owner: Function `tools.c_api_gen.gen_roundtrip_tests.emit`
- raw_name: `test_fns`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 44. FQV1-rocksdb-f3dbb757e4ce0c89

- repository: rocksdb   relation: REFERENCES
- source: `tools/advisor/advisor/db_config_optimizer.py:130-130`
- owner: Method `tools.advisor.advisor.db_config_optimizer.ConfigOptimizer.improve_db_config`
- raw_name: `current_config`
- candidates: 1
  - `symbol:7e3d7cbfd4f34258e5363800c7c65b6e3e48acd0bdcc2d6598eb79ad0826278d`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 45. FQV1-brpc-2bf1c7b1a8381218

- repository: brpc   relation: REFERENCES
- source: `tools/lldb_bthread_stack.py:156-156`
- owner: Function `tools.lldb_bthread_stack.get_all_bthreads`
- raw_name: `task_meta`
- candidates: 1
  - `symbol:8c7073821c6d7704f1d85a6c69b79af77782e934e575336f593c6d884e9f6578`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 46. FQV1-rocksdb-2b8ca346737ed076

- repository: rocksdb   relation: IMPORTS
- source: `table/block_based/flush_block_policy.cc:15-16`
- owner: File `table.block_based.flush_block_policy`
- raw_name: `table/block_based/block_builder.h`   target_module: `table/block_based/block_builder.h`
- candidates: 1
  - `file:d82a01662ff16e90169a3df5b925a2a13275a91f830f2edc50a550411267a5b8`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 47. FQV1-brpc-a57b6fcb67fac1a7

- repository: brpc   relation: IMPORTS
- source: `src/brpc/trackme.cpp:30-31`
- owner: File `src.brpc.trackme`
- raw_name: `brpc/policy/hasher.h`   target_module: `brpc/policy/hasher.h`
- candidates: 1
  - `file:27e4d376b0dc9d833351c487e7b5bd03b68f10b740816f6ffc6c7bff6ac8e865`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 48. FQV1-aria2-fae8ea276b34fa91

- repository: aria2   relation: REFERENCES
- source: `doc/bash_completion/make_bash_completion.py:166-166`
- owner: File `doc.bash_completion.make_bash_completion`
- raw_name: `opts`
- candidates: 1
  - `symbol:827f6468eadb4d3dea44f00993819f61a937811e0b153df68c58af71200a7d65`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 49. FQV1-brpc-8a70796e56274535

- repository: brpc   relation: CALLS
- source: `test/brpc_http_rpc_protocol_unittest.cpp:2956-2956`
- owner: Function `anonymous.TEST_F`
- raw_name: `EXPECT_GT`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 50. FQV1-aria2-c900f72d67f383ae

- repository: aria2   relation: CALLS
- source: `test/ServerStatManTest.cc:53-53`
- owner: File `test.ServerStatManTest`
- raw_name: `r->getHostname`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 51. FQV1-aria2-be43e19b68a9a8e9

- repository: aria2   relation: IMPORTS
- source: `src/SimpleRandomizer.cc:38-39`
- owner: File `src.SimpleRandomizer`
- raw_name: `unistd.h`   target_module: `unistd.h`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 52. FQV1-brpc-847434aeda664ac6

- repository: brpc   relation: REFERENCES
- source: `tools/lldb_bthread_stack.py:324-324`
- owner: Function `tools.lldb_bthread_stack.bthread_end`
- raw_name: `reset`
- candidates: 1
  - `symbol:ccceb740f15ec062cb11474b7f171badac069981627b7e0c38c27bd37aee8e3d`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 53. FQV1-aria2-2a7fdb7f3a53e49a

- repository: aria2   relation: IMPORTS
- source: `src/RequestGroupMan.cc:63-64`
- owner: File `src.RequestGroupMan`
- raw_name: `File.h`   target_module: `File.h`
- candidates: 1
  - `file:70aac1b7f04aa04a1e3a7fd3f61a5eb622d2f8aa4c1003e41f317bd6576eb2ee`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 54. FQV1-brpc-5a19585afcd8a6d6

- repository: brpc   relation: CALLS
- source: `src/butil/big_endian.cc:86-86`
- owner: File `src.butil.big_endian`
- raw_name: `Write`
- candidates: 1
  - `symbol:7a03a45ecac8804af5754b0b682def1416ce59238609eaf9ec1876c2ea72e1a3`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 55. FQV1-aria2-011b30e223df40af

- repository: aria2   relation: IMPORTS
- source: `src/DiskAdaptor.h:40-41`
- owner: File `src.DiskAdaptor`
- raw_name: `string`   target_module: `string`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 56. FQV1-aria2-186715e883536c6f

- repository: aria2   relation: REFERENCES
- source: `doc/bash_completion/make_bash_completion.py:80-80`
- owner: Function `doc.bash_completion.make_bash_completion.output_case`
- raw_name: `opts`
- candidates: 1
  - `symbol:827f6468eadb4d3dea44f00993819f61a937811e0b153df68c58af71200a7d65`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 57. FQV1-rocksdb-080cc91dd1133d44

- repository: rocksdb   relation: REFERENCES
- source: `tools/db_crashtest_test.py:595-595`
- owner: Method `tools.db_crashtest_test.DBCrashTestTest.test_liveness_params_keep_mixed_workload_and_enable_watchdog`
- raw_name: `build_mode_args`
- candidates: 1
  - `symbol:44eef1de3306c8da4c60cab41b32893b24e7dea47fdb246c9b6df59367a68c43`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 58. FQV1-aria2-5a4f0360db806a83

- repository: aria2   relation: REFERENCES
- source: `doc/manual-src/en/mkapiref.py:290-290`
- owner: File `doc.manual-src.en.mkapiref`
- raw_name: `header`
- candidates: 1
  - `symbol:9628e95873bc3f5abc46f119f1425a41d4ea0c6c9d510b47c8973c3dfc57c38c`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 59. FQV1-aria2-dc272fbb1023afed

- repository: aria2   relation: IMPORTS
- source: `src/AbstractAuthResolver.cc:37-38`
- owner: File `src.AbstractAuthResolver`
- raw_name: `a2functional.h`   target_module: `a2functional.h`
- candidates: 1
  - `file:90fdefd318a22a34e2a6e18763e82609f9d9a2e8f584a4f34a79d5521c31d6d2`

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

## 60. FQV1-aria2-a4092dc76a6af8a7

- repository: aria2   relation: IMPORTS
- source: `test/BtRegistryTest.cc:3-4`
- owner: File `test.BtRegistryTest`
- raw_name: `cppunit/extensions/HelperMacros.h`   target_module: `cppunit/extensions/HelperMacros.h`
- candidates: 0

| field | record |
| --- | --- |
| gold_relation_exists | |
| formal_verdict | |
| valid_target_count | |
| selected target (path:start, symbol_id) | |
| build_context_status | |
| navigation_files | |
| evidence_locations | |
| difficulty_tags | |
| confidence | |
| protocol_issue | |
| notes | |

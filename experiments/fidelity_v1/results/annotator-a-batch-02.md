# Annotator A — Batch 02

- Status: COMPLETE
- Samples: 60 / 60
- Blind Package Preflight: PASS
- Source Verification: COMPLETE
- Blindness violations: 0
- Repository mutation: 0

## Verdict distribution

| Verdict | Count |
|---|---:|
| ONE_VALID_TARGET | 42 |
| NO_VALID_TARGET | 18 |

## Annotations

| Case ID | Relation | Verdict | Candidate IDs | Source evidence |
|---|---|---|---|---|
| FQV1-brpc-3dd084e43286f5fe | CALLS | ONE_VALID_TARGET | symbol:2120f70de2d20dea843db10deb8f1b34594b85d901d245770e82c8369e5449ed | `src/brpc/policy/couchbase_protocol.cpp:60-60` |
| FQV1-aria2-1aefa5f3f46f94f6 | IMPORTS | ONE_VALID_TARGET | file:3c7d4956d7f9a24049f4490bbbfe62d27ba32de816b442a30403910850d7b736 | `test/SessionSerializerTest.cc:10-11` |
| FQV1-aria2-3145cfe72c552bd9 | REFERENCES | NO_VALID_TARGET | — | `doc/bash_completion/make_bash_completion.py:78-78` |
| FQV1-brpc-289d004dec9594de | IMPORTS | ONE_VALID_TARGET | file:e683770d7b1e7ab1c02b1375fb15653eb3ce38a5baef8db0ee2304a931b135cc | `src/bvar/detail/combiner.h:32-33` |
| FQV1-rocksdb-cd53a135c0fdb46a | IMPORTS | NO_VALID_TARGET | — | `utilities/backup/backup_engine.cc:13-14` |
| FQV1-brpc-7d1c68b08b689686 | IMPORTS | ONE_VALID_TARGET | file:9bfdc0e6637519f3eb66fbf037e8d7d4cc2dd13878cb86b34005691e1f838e1f | `src/brpc/backup_request_policy.cpp:22-23` |
| FQV1-aria2-42189fc8a97eb196 | CALLS | ONE_VALID_TARGET | symbol:1d11e23277061fca299b5f8ade3f56e8f89d636f227aa80616e1040d30257d6f | `src/DHTPingTask.cc:82-82` |
| FQV1-rocksdb-8e526ba5ac0d956a | CALLS | ONE_VALID_TARGET | symbol:6a35a63b78c638c0bbe768f2482f6b0857eb89406f8e09c0df6b0d26298af053 | `utilities/blob_db/blob_db_impl.cc:1631-1631` |
| FQV1-aria2-5ce7af038ff64537 | CALLS | ONE_VALID_TARGET | symbol:e19297531ee5fab31d81e5e0ac59396d114a74bdb947027273f512c0f8ab22fd | `src/cookie_helper.cc:53-53` |
| FQV1-rocksdb-ede7a9c26d8e7eb7 | IMPORTS | NO_VALID_TARGET | — | `db_stress_tool/db_stress_listener.h:10-11` |
| FQV1-rocksdb-a5e3f2693abf0ca0 | IMPORTS | ONE_VALID_TARGET | file:887db6db839168314ccee6fccc7350c92367c52f804f39d2da2cbf2ef6e6658f | `options/customizable.cc:13-14` |
| FQV1-aria2-4d8e045122db45b8 | IMPORTS | ONE_VALID_TARGET | file:64ab4a80f7bf1ca48903f30fadea77c5590e85a156e5100af48f6ff4776014e3 | `src/BtRegistry.cc:39-40` |
| FQV1-rocksdb-db52da4576e9fbc6 | CALLS | ONE_VALID_TARGET | symbol:d5170e1674f30f1b663c712eb32a2ddb4403935361f2b4f3f8a6cda58d27f7da | `options/options_test.cc:3861-3861` |
| FQV1-rocksdb-6171ade471166b66 | IMPORTS | NO_VALID_TARGET | — | `tools/advisor/advisor/db_log_parser.py:11-11` |
| FQV1-brpc-c9fe122406a9bd9d | REFERENCES | ONE_VALID_TARGET | symbol:d5fa05eec334493162a7da4aa4c6db84ea9cd626ba927e7ac325ff9846540d1b | `tools/gdb_bthread_stack.py:171-171` |
| FQV1-rocksdb-3e14d26f5ea90348 | REFERENCES | ONE_VALID_TARGET | symbol:5ba74801add67a52df59f4431b10fabe6a57ad647448d4ea15d4dee1d7e52408 | `tools/fault_injection_log_parser.py:158-158` |
| FQV1-aria2-34ef1c35da5cabaf | CALLS | ONE_VALID_TARGET | symbol:501a588b71d1a34ec7fcb64a0fac62331f35555c729df0b84bb0743c53c16f1d | `src/crypto_hash.cc:464-464` |
| FQV1-rocksdb-082b468c2a347ecc | IMPORTS | ONE_VALID_TARGET | file:7ddec5b715631f57881516d7e3deca7420147302752a531e9e1299be7375112a | `db/db_compaction_test.cc:35-36` |
| FQV1-rocksdb-98fed327423513a1 | IMPORTS | NO_VALID_TARGET | — | `file/writable_file_writer.cc:13-14` |
| FQV1-brpc-4fc2ecf5e4f15730 | CALLS | NO_VALID_TARGET | — | `test/brpc_redis_unittest.cpp:211-211` |
| FQV1-brpc-a125d96bbb5279c8 | CALLS | ONE_VALID_TARGET | symbol:0f4c9a02797cfe969b154e95d7d155be79ff9b7a0225ca68d117a033e7d5c20a | `src/bvar/recorder.h:193-193` |
| FQV1-rocksdb-d53fd59a6ee6cce8 | CALLS | ONE_VALID_TARGET | symbol:50bf01b6c74deec9f9c5a3dd50692be061189a5b26d74dbaa7cd82df9b58e253 | `table/block_based/block_based_table_factory.h:58-58` |
| FQV1-brpc-e50f9dad96b20880 | REFERENCES | NO_VALID_TARGET | — | `tools/lldb_bthread_stack.py:91-91` |
| FQV1-aria2-f57b2e43a585b7c5 | REFERENCES | NO_VALID_TARGET | — | `doc/manual-src/en/mkapiref.py:82-82` |
| FQV1-brpc-0a0b22aaf75a2795 | IMPORTS | ONE_VALID_TARGET | file:a64c2c576e9a6f5420ed47c4aba6dc9dd5a620fa9edf0543e343f44dd2d36deb | `src/bvar/passive_status.h:23-24` |
| FQV1-aria2-7e6028952b2e2c4d | REFERENCES | NO_VALID_TARGET | — | `doc/manual-src/en/mkapiref.py:90-90` |
| FQV1-brpc-d12b7bdc3ecd5bbc | CALLS | ONE_VALID_TARGET | symbol:82120524ca00e8c9d25fe43f384959c0fc33f42a3abfd9f6a914232b8541d488<br>symbol:f33946fda2e5c4f4f7d3314a6d9677fa94b8e8cab2c983f15d7ba8674f5d0fd4 | `test/bthread_unittest.cpp:184-184` |
| FQV1-rocksdb-50cde67d26537c7c | CALLS | ONE_VALID_TARGET | symbol:e3914a04fe233add7ea49eeb9cb512edddbbb00fbac1bca1aa72dedcf9d12c8c | `utilities/transactions/write_committed_transaction_ts_test.cc:944-946` |
| FQV1-rocksdb-7d3ed2f39a8ee359 | REFERENCES | NO_VALID_TARGET | — | `tools/db_crashtest_test.py:187-187` |
| FQV1-brpc-925bccaa1f6af572 | CALLS | ONE_VALID_TARGET | symbol:df8342fb962201cc97efb91bc2901003646af5f990e2209bb43e46a908b84a0e | `src/brpc/policy/thrift_protocol.cpp:645-646` |
| FQV1-aria2-6fd1cc6573ec1b32 | REFERENCES | ONE_VALID_TARGET | symbol:827f6468eadb4d3dea44f00993819f61a937811e0b153df68c58af71200a7d65 | `doc/bash_completion/make_bash_completion.py:36-36` |
| FQV1-brpc-afcb7bece5fbf84d | REFERENCES | ONE_VALID_TARGET | symbol:e954e36d5a22bdc85cd39e4213b078175a33e70ef6d51b3ed343f6daeb9869cf | `tools/lldb_bthread_stack.py:265-265` |
| FQV1-rocksdb-b24d43d6f6748681 | IMPORTS | ONE_VALID_TARGET | file:4a13cc5105443e7dac136092aa4fc851a01b11eacb37597da27a8ce949aa842f | `logging/auto_roll_logger.cc:13-14` |
| FQV1-aria2-3417e1e85c14dc2b | REFERENCES | ONE_VALID_TARGET | symbol:827f6468eadb4d3dea44f00993819f61a937811e0b153df68c58af71200a7d65 | `doc/bash_completion/make_bash_completion.py:126-126` |
| FQV1-brpc-b13db4df2ae67499 | REFERENCES | NO_VALID_TARGET | — | `tools/lldb_bthread_stack.py:140-140` |
| FQV1-aria2-ecbfe395c8ae229d | IMPORTS | ONE_VALID_TARGET | file:8ea1c2d1e68c65dcacbe20bbe8692bfbbe98ca3e66bca708677a07098cd95854 | `src/DHTEntryPointNameResolveCommand.h:38-39` |
| FQV1-aria2-52bdba205b5ce686 | CALLS | NO_VALID_TARGET | — | `test/HttpResponseTest.cc:252-252` |
| FQV1-aria2-0f84707a755b6d84 | CALLS | ONE_VALID_TARGET | symbol:09276028ee2eb90c14b4bb3cb04035b818d1419fca335ca7284be69ec847572c | `src/CookieStorage.cc:159-159` |
| FQV1-rocksdb-db9854fe698976a2 | CALLS | ONE_VALID_TARGET | symbol:a270cc1c657d60e23819c531d77190a6ad93841769c35562a0e0548d00d1f2ac | `db/blob/db_blob_direct_write_test.cc:687-687` |
| FQV1-brpc-d96f900465b7aaa4 | REFERENCES | ONE_VALID_TARGET | symbol:d5fa05eec334493162a7da4aa4c6db84ea9cd626ba927e7ac325ff9846540d1b | `tools/gdb_bthread_stack.py:144-144` |
| FQV1-brpc-1ad645405e3e9695 | IMPORTS | ONE_VALID_TARGET | file:e648967fee36d71ea4533f1e619c6a14f8be1824df3a12cc00e58cd91f3c8852 | `src/butil/debug/stack_trace.cc:7-8` |
| FQV1-aria2-f1abdaa5d081ee7e | REFERENCES | ONE_VALID_TARGET | symbol:141d0477ddcc5263cca41d93af610f9467400ac1fdcee867634b27ae4ea71f22 | `doc/sphinx_themes/sphinx_rtd_theme/__init__.py:75-75` |
| FQV1-rocksdb-342f7be2ac886595 | REFERENCES | NO_VALID_TARGET | — | `tools/c_api_gen/gen_roundtrip_tests.py:167-167` |
| FQV1-rocksdb-f3dbb757e4ce0c89 | REFERENCES | ONE_VALID_TARGET | symbol:7e3d7cbfd4f34258e5363800c7c65b6e3e48acd0bdcc2d6598eb79ad0826278d | `tools/advisor/advisor/db_config_optimizer.py:130-130` |
| FQV1-brpc-2bf1c7b1a8381218 | REFERENCES | ONE_VALID_TARGET | symbol:8c7073821c6d7704f1d85a6c69b79af77782e934e575336f593c6d884e9f6578 | `tools/lldb_bthread_stack.py:156-156` |
| FQV1-rocksdb-2b8ca346737ed076 | IMPORTS | ONE_VALID_TARGET | file:d82a01662ff16e90169a3df5b925a2a13275a91f830f2edc50a550411267a5b8 | `table/block_based/flush_block_policy.cc:15-16` |
| FQV1-brpc-a57b6fcb67fac1a7 | IMPORTS | ONE_VALID_TARGET | file:27e4d376b0dc9d833351c487e7b5bd03b68f10b740816f6ffc6c7bff6ac8e865 | `src/brpc/trackme.cpp:30-31` |
| FQV1-aria2-fae8ea276b34fa91 | REFERENCES | ONE_VALID_TARGET | symbol:827f6468eadb4d3dea44f00993819f61a937811e0b153df68c58af71200a7d65 | `doc/bash_completion/make_bash_completion.py:166-166` |
| FQV1-brpc-8a70796e56274535 | CALLS | NO_VALID_TARGET | — | `test/brpc_http_rpc_protocol_unittest.cpp:2956-2956` |
| FQV1-aria2-c900f72d67f383ae | CALLS | NO_VALID_TARGET | — | `test/ServerStatManTest.cc:53-53` |
| FQV1-aria2-be43e19b68a9a8e9 | IMPORTS | NO_VALID_TARGET | — | `src/SimpleRandomizer.cc:38-39` |
| FQV1-brpc-847434aeda664ac6 | REFERENCES | ONE_VALID_TARGET | symbol:ccceb740f15ec062cb11474b7f171badac069981627b7e0c38c27bd37aee8e3d | `tools/lldb_bthread_stack.py:324-324` |
| FQV1-aria2-2a7fdb7f3a53e49a | IMPORTS | ONE_VALID_TARGET | file:70aac1b7f04aa04a1e3a7fd3f61a5eb622d2f8aa4c1003e41f317bd6576eb2ee | `src/RequestGroupMan.cc:63-64` |
| FQV1-brpc-5a19585afcd8a6d6 | CALLS | ONE_VALID_TARGET | symbol:7a03a45ecac8804af5754b0b682def1416ce59238609eaf9ec1876c2ea72e1a3 | `src/butil/big_endian.cc:86-86` |
| FQV1-aria2-011b30e223df40af | IMPORTS | NO_VALID_TARGET | — | `src/DiskAdaptor.h:40-41` |
| FQV1-aria2-186715e883536c6f | REFERENCES | ONE_VALID_TARGET | symbol:827f6468eadb4d3dea44f00993819f61a937811e0b153df68c58af71200a7d65 | `doc/bash_completion/make_bash_completion.py:80-80` |
| FQV1-rocksdb-080cc91dd1133d44 | REFERENCES | ONE_VALID_TARGET | symbol:44eef1de3306c8da4c60cab41b32893b24e7dea47fdb246c9b6df59367a68c43 | `tools/db_crashtest_test.py:595-595` |
| FQV1-aria2-5a4f0360db806a83 | REFERENCES | ONE_VALID_TARGET | symbol:9628e95873bc3f5abc46f119f1425a41d4ea0c6c9d510b47c8973c3dfc57c38c | `doc/manual-src/en/mkapiref.py:290-290` |
| FQV1-aria2-dc272fbb1023afed | IMPORTS | ONE_VALID_TARGET | file:90fdefd318a22a34e2a6e18763e82609f9d9a2e8f584a4f34a79d5521c31d6d2 | `src/AbstractAuthResolver.cc:37-38` |
| FQV1-aria2-a4092dc76a6af8a7 | IMPORTS | NO_VALID_TARGET | — | `test/BtRegistryTest.cc:3-4` |

## Navigation telemetry

- Same-file source checks: 60
- Cross-file verification: 42
- Declaration/definition lookups: 28
- Include tracing: 21
- Candidate-source verification: 42


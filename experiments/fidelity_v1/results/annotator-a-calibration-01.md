# Graph Fidelity V1 — Annotator A Calibration 01

## Execution boundary

- Source package: `annotator-a.json`, first 25 cases in its blinded order.
- System status, strategy, confidence, and selected target: not consulted.
- This is an independent source-level annotation record, not a score or an adjudication.
- Every row records a semantic relation observed in source. `target evidence` records the source-level target when it can be established without the hidden system decision.
- The frozen `relation_verdict` vocabulary is intentionally not assigned here: its two permitted vocabularies depend on the hidden system status. It must be derived only after the blinded annotations are joined during the prescribed audit.

| # | Case ID | 关系 | 源码语义关系 | 目标证据 | 构建上下文 | 难点 / 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | FQV1-aria2-0b3012e7241735bd | IMPORTS | 存在 | `src/Peer.h` | 未使用额外构建上下文 | 直接双引号 include |
| 2 | FQV1-rocksdb-1273fbd969565cef | CALLS | 存在 | GoogleTest `ASSERT_EQ` 宏；仓内无候选目标 | 未使用额外构建上下文 | `macro`、外部依赖 |
| 3 | FQV1-aria2-713b641e93cc620c | CALLS | 存在 | `req1.params` 对象的 `append` 调用；本包不足以确定仓内定义 | 未使用额外构建上下文 | 无候选；需要类型传播 |
| 4 | FQV1-brpc-68baef18ae4bd3ee | CALLS | 存在 | `brpc.CouchbaseOperations.CouchbaseResponse.MergeFrom` | 未使用额外构建上下文 | 同名 `MergeFrom` 候选，接收者类型消歧 |
| 5 | FQV1-rocksdb-ee83baa17e82ced3 | REFERENCES | 存在 | Python 局部 `logger` 对象；`logger.log_tasks` | 未使用额外构建上下文 | 候选均非该 Python 对象；跨语言同名干扰 |
| 6 | FQV1-aria2-e057f6d338d4b31b | CALLS | 存在 | `aria2.IOFile.eof` | 未使用额外构建上下文 | 直接成员调用 |
| 7 | FQV1-aria2-4fd41bb9bb827c2a | REFERENCES | 存在 | Python 标准库模块 `re` | 未使用额外构建上下文 | 外部模块 |
| 8 | FQV1-brpc-edbe4d00ad31625b | IMPORTS | 存在 | `src/brpc/policy/baidu_rpc_protocol.h` | 未使用额外构建上下文 | 直接双引号 include |
| 9 | FQV1-rocksdb-dedc59a11f94c3e6 | IMPORTS | 存在 | `db/wide/wide_columns_helper.h` | 未使用额外构建上下文 | 直接双引号 include |
| 10 | FQV1-aria2-156558abc75568d8 | CALLS | 存在 | `std::string::begin` | 未使用额外构建上下文 | 标准库目标；仓内同名候选均不匹配 |
| 11 | FQV1-aria2-3ea5b21309de76eb | REFERENCES | 存在 | Python 局部 `infile` 文件对象 | 未使用额外构建上下文 | 局部变量引用 |
| 12 | FQV1-aria2-44c700a2083beb2e | IMPORTS | 存在 | `src/SocketCore.h` | 未使用额外构建上下文 | 直接双引号 include |
| 13 | FQV1-brpc-a4c0999defbf0e7b | CALLS | 存在 | 系统网络函数 `htons` | 未使用额外构建上下文 | 外部系统库 |
| 14 | FQV1-aria2-91b984d6e6d0a7ee | CALLS | 存在 | Python 内建 `print` | 未使用额外构建上下文 | 跨语言同名候选不匹配 |
| 15 | FQV1-rocksdb-b42469d800d8d7e1 | IMPORTS | 存在 | 系统头文件 `<climits>` | 未使用额外构建上下文 | 外部系统头 |
| 16 | FQV1-aria2-5d9c6122ac7c4cd4 | REFERENCES | 存在 | Python 局部列表 `func_proto` | 未使用额外构建上下文 | 局部变量引用 |
| 17 | FQV1-brpc-734b24f434825a0f | REFERENCES | 存在 | Python 局部列表 `bthreads` | 未使用额外构建上下文 | 候选均为 C++ 测试变量；跨语言同名干扰 |
| 18 | FQV1-rocksdb-042e70a2abbb97a5 | REFERENCES | 存在 | Python 局部 `chunk` | 未使用额外构建上下文 | 候选为无关 C++ 测试变量 |
| 19 | FQV1-brpc-b210f3349b031961 | CALLS | 存在 | `brpc.RedisReply.c_str` | 未使用额外构建上下文 | 同名候选，接收者 `response.reply(0)` 消歧 |
| 20 | FQV1-aria2-9eca3ec96d005bfe | IMPORTS | 存在 | `src/FileEntry.h` | 未使用额外构建上下文 | 直接双引号 include |
| 21 | FQV1-brpc-2a3acc02ebb20bb4 | IMPORTS | 存在 | `src/butil/threading/thread_local.h` | 未使用额外构建上下文 | 直接双引号 include |
| 22 | FQV1-rocksdb-6adbad5ec0ab376e | CALLS | 存在 | `ROCKSDB_NAMESPACE.IOStatus.SetRetryable` | 未使用额外构建上下文 | 直接成员调用 |
| 23 | FQV1-rocksdb-ff7dddd235f6cd6a | REFERENCES | 存在 | Python 构造函数参数 `entities` | 未使用额外构建上下文 | 候选为无关 C++ 成员；跨语言同名干扰 |
| 24 | FQV1-brpc-3fe7d970be9bff2a | REFERENCES | 存在 | Python `global_state.started` 属性 | 未使用额外构建上下文 | 候选为无关 C++ 函数；跨语言同名干扰 |
| 25 | FQV1-aria2-4ad524eeab0b941a | IMPORTS | 存在 | `src/Segment.h` | 未使用额外构建上下文 | 直接双引号 include |

## Calibration observations

1. 25/25 source locations contain the sampled semantic relation; this is a source-observation fact only and is not system precision.
2. Twelve cases have an unambiguous repository-local target from source and candidate metadata (six imports and six calls).
3. Thirteen cases reference an external dependency, a Python local/builtin/module, or a target that cannot be assigned a repository symbol ID from the blinded package alone. They remain valid evidence of a source-level relation, but require the post-join rules to distinguish valid non-repository targets from resolver misses.
4. `ANNOTATION_PROTOCOL_ISSUE-001` remains open: target-definition metadata needs to be available to annotators without exposing the system-selected target. The lookup used in this calibration was candidate-by-candidate and did not inspect `raw_references.status`, `resolved_symbol_id`, strategy, or confidence.

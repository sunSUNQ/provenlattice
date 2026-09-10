# ProvenLattice Core V0.2 — C/C++ Benchmark Baseline

日期：2026-09-10。三个 benchmark 均使用冻结的 shallow-clone commit，数据库写在 `benchmark-analysis/v0.2-db/`，未修改 benchmark repository。

## 环境与口径

- Windows 11 `10.0.26200`，Python 3.12.10。
- Tree-sitter 0.26.0、Python grammar 0.25.0、C grammar 0.24.2、C++ grammar 0.23.4。
- `files_scanned` 只统计 ProvenLattice 当前支持的 Python/C/C++ 源文件；忽略 build/out/dist/target/cache/third_party/deps/vendor 等目录。
- `parse_failures` 表示 parser 抛出异常、未产生 ParsedFile；`syntax_error_files` 表示 Tree-sitter 产生了可恢复的 `ERROR` 节点。两者不能混为一谈。
- Full Index 时间包含 scan、parse、graph/resolution/shard 和 SQLite snapshot 写入。
- Peak Memory 是单独 Python 进程的 Peak Working Set。
- 查询先预热 3 次，再采样 30 次；subgraph 使用 `max_hops=2`、`max_nodes=100`。

原始数据：[provenlattice-v0.2-baseline.json](C:/Users/sunqinghw/Documents/ChatGPT/codegraph/benchmark-analysis/provenlattice-v0.2-baseline.json)。可重复运行脚本：[run_baseline.py](C:/Users/sunqinghw/Documents/ChatGPT/codegraph/provenlattice/benchmarks/run_baseline.py) 与 [analyze_baseline.py](C:/Users/sunqinghw/Documents/ChatGPT/codegraph/provenlattice/benchmarks/analyze_baseline.py)。

## 规模与解析结果

| Metric | B1 aria2 | B2 brpc | B3 RocksDB |
| --- | ---: | ---: | ---: |
| Commit | `9e727358` | `ae09e960` | `37234200` |
| C/C++ LOC | 118,926 | 227,154 | 622,772 |
| Files scanned / parsed | 1,168 / 1,168 | 1,168 / 1,168 | 1,478 / 1,478 |
| Hard parse failures | 0 | 0 | 0 |
| Parse coverage | 100% | 100% | 100% |
| Syntax-error files | 388 | 305 | 248 |
| Syntax-clean rate | 66.78% | 73.89% | 83.22% |
| Nodes | 29,117 | 48,929 | 118,655 |
| RawReferences | 49,109 | 84,941 | 311,111 |
| Resolved | 10,804 (22.0%) | 17,210 (20.3%) | 54,481 (17.5%) |
| Ambiguous | 13,966 (28.4%) | 28,421 (33.5%) | 101,090 (32.5%) |
| Unresolved | 24,339 (49.6%) | 39,310 (46.3%) | 155,540 (50.0%) |
| Edges | 37,074 | 59,614 | 143,585 |
| Shards | 8 | 46 | 64 |
| Boundary edges | 1,356 (3.66%) | 4,291 (7.20%) | 11,692 (8.14%) |

## 性能结果

| Metric | B1 aria2 | B2 brpc | B3 RocksDB |
| --- | ---: | ---: | ---: |
| Full Index | 3,954 ms | 7,591 ms | 26,190 ms |
| Peak Memory | 186.5 MiB | 308.9 MiB | 1,069.5 MiB |
| SQLite DB | 125.9 MiB | 226.2 MiB | 835.5 MiB |
| Symbol P50 / P95 | 87.4 / 93.0 ms | 159.8 / 171.1 ms | 420.3 / 449.0 ms |
| Caller P50 / P95 | 50.7 / 54.1 ms | 39.6 / 40.9 ms | 154.5 / 165.1 ms |
| Callee P50 / P95 | 15.9 / 16.6 ms | 30.2 / 32.3 ms | 69.8 / 72.4 ms |
| Subgraph P50 / P95 | 25.9 / 28.0 ms | 27.4 / 28.9 ms | 66.3 / 68.1 ms |

## 结果分析

### 1. Tree-sitter 覆盖率

三档仓库 hard parse coverage 均为 100%，没有文件因 parser 异常丢失。syntax-clean rate 为 66.78%–83.22%；ERROR 节点主要出现在宏密集、条件编译、平台声明和 `.h` 文件，但 Tree-sitter 仍能恢复并产生结构事实。后续不应把 syntax-error file 误报为 parse failure。

### 2. unresolved/ambiguous 的主要来源

unresolved 主要来自本阶段明确不强制解决的语义：macro-like call、template/cast 形态、成员或 qualified call，以及找不到本仓目标的系统/生成 include。三仓 unresolved 中，宏形态分别约 7.3K、21.0K、61.3K；模板/转换形态约 10.3K、8.8K、55.7K。ambiguous 主要是成员调用与同名/重载函数；Resolver 没有为了提高 resolved rate 强行选边。

include suffix 解析已产生 5,961 / 4,408 / 8,666 个 resolved IMPORTS；无法唯一匹配的 include 保持 ambiguous/unresolved。

### 3. Node / Edge / RawReference 与 LOC

从 B1 到 B3，LOC 增长约 5.24 倍，Nodes 增长 4.08 倍，Edges 增长 3.87 倍，RawReferences 增长 6.34 倍。Nodes/Edges 总体随 LOC 单调增长，但不是固定线性系数：RocksDB 的测试、宏和模板调用密度使 RawReference 增速更高。

每 KLOC 的 Nodes 为 244.8 / 215.4 / 190.5，Edges 为 311.7 / 262.4 / 230.6，RawReferences 为 412.9 / 373.9 / 499.6。这说明 LOC 只能用于规模归一化，不能代替工程结构和语法密度。

### 4. Shard / Boundary Edge

brpc 与 RocksDB 得到 46/64 个 shard、7.2%/8.1% boundary edge，能够体现多模块工程的跨目录关系。aria2 只有 8 个 shard，说明当前“两级目录”策略会把扁平的 `src/` 工程聚成过大的单 shard。边界事实可信，但 B1 的 shard 粒度不够适合精细增量比例测量。

### 5. 时间与 DB Size 增长

Full Index 从 3.95s → 7.59s → 26.19s，随着 LOC 和 RawReference 单调增长；B3 比 B2 略呈超线性，和 3.66 倍 RawReference、SQLite 写入量相符。DB 从 125.9 MiB → 226.2 MiB → 835.5 MiB，趋势合理，但 RocksDB 的 835.5 MiB 已表明 parser cache 与 graph facts 的重复存储需要后续压缩。

### 6. Resolver 是否足够进入 Shard Incremental 实验

足够进行“保守 correctness”实验：resolved/ambiguous/unresolved contract 在真实仓库成立；只有 resolved fact 形成语义 Edge；include、same-file、qualified 和 unique-symbol resolution 都有真实命中；Full/Incremental parity fixture 已覆盖 C/C++ reference target 与 cross-shard edge 变化。

它还不适合宣称完整 C++ call graph。17.5%–22.0% resolved rate 是当前最小语义模型的基线，不应通过猜测类型、宏或重载来人为抬高。

### 7. 进入 V0.3 前的 blocker

必须优先解决的是 shard qualification：为扁平 `src/` 仓库提供可配置或模块感知的 shard 策略，否则 aria2 的增量实验会退化为“大 shard 重建”。

另外两项是明确的性能债务，不阻塞 correctness 实验，但会影响规模结论：

- File node metadata 内嵌完整 ParsedFile cache，导致 RocksDB DB 达 835.5 MiB；应拆分/压缩 parser cache。
- Symbol 查询 P95 从 93 ms 增至 449 ms，当前 `name OR qualified_name OR LIKE` 查询需要专用索引或分步查询。

宏展开、模板实例化、函数指针、virtual dispatch 与复杂 overload resolution 仍按阶段约束保留 ambiguous/unresolved，不是 V0.3 blocker。

## Stable Symbol Identity 结论

现有 `repository + path + kind + qualified name + signature` contract 可以继续使用，无需重设计：

- C++ qualified name 使用 namespace/class 语义范围，不把文件 module 前缀混入符号名；
- nested class/method 由 scope 组合；
- overload 由 signature 区分；
- header declaration 与 source definition 保持相同 qualified name/signature，但因 path 不同拥有不同稳定 ID；
- 同一文件内完全相同 identity 的重复 declaration/definition 合并，并记录 duplicate site。

这是一项最小适配，没有改变 Node、Edge、RawReference 或 Shard 的 Core contract。

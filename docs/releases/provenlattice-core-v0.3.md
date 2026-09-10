# ProvenLattice Core V0.3

> Reference Resolution、C/C++ Graph Support、Shard Qualification 与 Incremental Foundation 的版本记录

## 版本范围

V0.3 延续 Core V0.1/V0.2 的 CodeGraph 主线，只处理源码结构、引用关系、分片和局部增量更新。本版本不引入 Spec、Log、Commit Graph、Embedding、MCP、UI、TASCO 或 Branch Overlay。

## 已完成能力

### 统一解析与图模型

- 基于 Tree-sitter 的 Python、C、C++ Parser Adapter。
- 支持 `.h/.hpp/.c/.cc/.cpp`。
- C/C++ 提取 namespace、class/struct、function、method、declaration/definition、include、call expression、typedef/using 与 type。
- Parser 输出统一的 `ParsedSymbol`、`ParsedReference`、`ParsedImport`，Graph Core contract 保持不变。
- 复杂宏展开、模板实例化、函数指针、虚调用和复杂重载保持 ambiguous/unresolved，不强行生成错误 Edge。

### Reference Resolution 与 Provenance

每个 RawReference 明确记录：

```text
raw_name
candidate_symbols
resolved_symbol_id
resolution_strategy
provenance
confidence
status = resolved | ambiguous | unresolved
```

解析优先级为 same-file、qualified name、explicit import/include、unique imported symbol、unique repository symbol。只有 resolved reference 才形成语义 Edge；`tree_sitter_syntax`、`same_file_resolution`、`qualified_name_resolution`、`import_resolution` 和 `unique_symbol_resolution` 等 provenance 保留在图中。

RawReference 建立了以下反向索引：

```text
raw_name → reference sites
file → references
owner symbol → references
resolved symbol → references
```

### Stable Symbol Identity 与 API Fingerprint

Symbol identity 继续使用：

```text
repository + relative path + kind + qualified name + signature
```

已覆盖 namespace、nested class、method、overload，以及 header declaration/source definition。Shard API fingerprint 只依赖公开 symbol 的 kind、qualified name 和 signature，因此函数体变化不会改变 fingerprint，公开签名变化会设置 `boundary_dirty`。

### 可插拔 Shard

实现三种策略：

| Strategy | 作用 |
|---|---|
| `directory` | 按目录层级建立可解释的 baseline shard |
| `build-aware` | 识别 Bazel/CMake/Make/Meson 文件形成边界候选 |
| `structural` | 对 oversized directory 按确定性的 syntax-density bucket 拆分 |

Shard 统计包括 shard 数量、文件/节点 min/median/p95/max、internal/boundary edges、boundary ratio、isolated shard 和 giant shard ratio。

新增 `shard_edges` 表持久化跨 shard 边，`GraphQuery.get_boundary_references()` 可反向查询 symbol 相关 boundary reference。

### Incremental Foundation

`compute_impact_frontier()` 采用保守的一跳策略：

1. 0-hop：changed shards；
2. 1-hop：直接 dependent shards；
3. 记录受影响 boundary edges、frontier size 和 `wide_impact`；
4. 暂不递归重建 Dependency Frontier。

增量指标新增：

```text
files_reparsed / files_reused
references_reprocessed / references_reused
shards_updated / shards_reused
boundary_edges_reprocessed / boundary_edges_reused
impact_frontier_size / wide_impact
```

## 验证结果

### 自动化测试

```text
20 tests passed
```

覆盖 Python/C/C++ fixture、stable identity、RawReference resolution contract、三种 Shard strategy、API fingerprint、reverse boundary index、文件增删改和 Full/Incremental parity。

### Benchmark Set V1

| ID | Repository | 用途 | C/C++ LOC | Nodes | RawReferences | Edges | Full index | DB |
|---|---|---|---:|---:|---:|---:|---:|---:|
| B1 | aria2/aria2 | Small Regression | 118,926 | 29,117 | 49,109 | 37,074 | 3.95 s | 132 MB |
| B2 | apache/brpc | Target-like Primary | 227,154 | 48,929 | 84,941 | 59,614 | 7.59 s | 237 MB |
| B3 | facebook/rocksdb | Scale | 622,772 | 118,655 | 311,111 | 143,585 | 26.19 s | 876 MB |

三个 benchmark 均以固定 commit、shallow clone、clean working tree 记录；本地只保留 aria2、brpc、rocksdb。

### Shard 结论

- B1：Structural 将 giant shard ratio 从 74.083% 降至 8.738%，适合增量压力测试；Directory 保留为低 boundary ratio baseline。
- B2：Directory 在 giant ratio 37.803%、boundary ratio 7.198% 之间最均衡，作为 Primary。
- B3：Build-aware 的 boundary ratio 为 8.056%，适合作为 Scale baseline；Structural 的 giant ratio 为 10.242%，作为对照。

### Mutation parity

B1 的 M1–M5 全部通过：

| Case | 结果 |
|---|---|
| M1 local body | API fingerprint unchanged；1 file、1 shard 更新 |
| M2 internal relation | 仅当前 shard 更新；API fingerprint unchanged |
| M3 public signature | fingerprint changed；boundary dirty=true |
| M4 cross-shard add | boundary edge +1 |
| M5 cross-shard remove | boundary edge -1 |

B2 和 B3 另各执行一次 body-only representative mutation，均只重解析 1 个文件、只更新 1 个 shard，并通过 parity。

## 主要发现与限制

1. 三个真实仓库的扫描/解析尝试覆盖率均为 100%；syntax-clean 比例受宏、模板、平台条件代码和不完整片段影响。
2. unresolved/ambiguous 主要来自宏样式调用、template/cast、成员/限定名调用和条件 include；这是保守 resolver 的预期行为。
3. Nodes、RawReferences、Edges 随 B1→B3 合理增长；RawReference 增长快于 LOC，反映 C++ 调用和宏密度。
4. 当前 Resolver、RawReference cache、shard_edges 和一跳 frontier 已足够进入下一阶段 Shard Incremental 实验。
5. 下一阶段前没有必须阻断的架构问题；复杂 overload/template/function-pointer/virtual dispatch 仍应允许 unresolved/ambiguous。

## 可重复产物

- [`design-v0.md`](../design-v0.md)：Core contract 与架构设计。
- [`open-source-survey.md`](../open-source-survey.md)：开源方案调研与技术选择。
- [`provenlattice-v0.3-shard.md`](../benchmarks/provenlattice-v0.3-shard.md)：完整 strategy、baseline、mutation 与 query 结果。
- [`provenlattice-v0.3-shard.json`](../benchmarks/provenlattice-v0.3-shard.json)：结构化结果和固定 commit 校验。
- `benchmarks/qualify_shards.py`、`benchmarks/run_mutations.py`、`benchmarks/run_representative.py`：可重复脚本。

## 后续建议

固定 B1/B2/B3，继续测 Full Index Time、DB Size、Nodes、Edges、RawReferences、Shards、Boundary Edges，以及 mutation 的重解析文件数、引用复用数、更新 shard 数、frontier 和 Symbol/Caller/Callee/Subgraph P50/P95。暂不扩展到 Spec、Log、Commit、Embedding、MCP、UI 或 TASCO。

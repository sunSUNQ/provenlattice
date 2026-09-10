# ProvenLattice Core V0.3 — Shard Qualification and Incremental Foundation

生成日期：2026-09-10。此报告只覆盖 CodeGraph、可插拔 Shard、API fingerprint、reverse boundary index、one-hop impact frontier 和增量 parity；不包含 Spec、Log、Commit、Embedding、MCP、UI、TASCO 或 Branch Overlay。

## 1. 固定 Benchmark Set

| ID | Repository | Commit | 用途 |
|---|---|---|---|
| B1 | [aria2/aria2](https://github.com/aria2/aria2) | `9e7273583f83e881e3ec067b523ba88724088d2f` | Small Regression |
| B2 | [apache/brpc](https://github.com/apache/brpc) | `ae09e960c7291605dda52356cc0c2d45567fb53e` | Target-like Primary |
| B3 | [facebook/rocksdb](https://github.com/facebook/rocksdb) | `37234200b57d8d0a6a5c41f2d9811bbd2e293544` | Scale |

三个目录都已验证为 shallow clone、working tree clean，且当前 SHA 与基线记录一致。候选筛选的完整 9 仓库记录仍保存在 `benchmark-results.json`；本地只保留上述三个副本。

## 2. 目标画像与统一口径

目标约 16.4 MB、1301 文件、340K total LOC、307K C/C++ LOC、约 1100 个 C/C++ 文件、src 797/test 359、Bazel、多模块和大量跨模块关系。统计使用 `git ls-files`，排除 `.git/build/out/dist/target/node_modules/.cache/third_party/third-party/deps/vendor`；LOC 为去除空白与注释后的物理行；解析覆盖率以扫描文件数为分母；boundary edge 由 source/target shard 不同判定。完整口径在 [`measure.ps1`](measure.ps1)。

## 3. V0.2 Full Index 基线

| Benchmark | C/C++ LOC | files scanned/parsed | syntax-clean | nodes | RawReference | resolved / ambiguous / unresolved | edges | shards | boundary edges | Full ms | DB size | query P95 symbol/caller/callee/subgraph (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| B1 aria2 | 118,926 | 1168/1168 | 66.781% | 29,117 | 49,109 | 10,804 / 13,966 / 24,339 | 37,074 | 8 | 1,356 | 3,953.6 | 132,034,560 B | 93.0 / 54.1 / 16.6 / 28.0 |
| B2 brpc | 227,154 | 1168/1168 | 73.887% | 48,929 | 84,941 | 17,210 / 28,421 / 39,310 | 59,614 | 46 | 4,291 | 7,590.8 | 237,162,496 B | 171.1 / 40.9 / 32.3 / 28.9 |
| B3 RocksDB | 622,772 | 1478/1478 | 83.221% | 118,655 | 311,111 | 54,481 / 101,090 / 155,540 | 143,585 | 64 | 11,692 | 26,190.2 | 876,105,728 B | 449.0 / 165.1 / 72.4 / 68.1 |

解析覆盖率为 100%；syntax-clean 较低主要是大型仓库中预处理器、平台条件代码、宏和不完整片段产生的 Tree-sitter error nodes，不等于文件未扫描。

## 4. Shard Strategy Qualification

实现了统一 `ShardStrategy` 接口：`directory`（目录基线）、`build-aware`（识别 Bazel/CMake/Make/Meson 边界）、`structural`（按确定性的 syntax-density bucket 拆分 oversized directory）。所有结果均为临时 DB，运行后清理。

| Benchmark / strategy | shards | files min/med/p95/max | nodes min/med/p95/max | internal | boundary | boundary ratio | isolated | giant shard ratio |
|---|---:|---|---|---:|---:|---:|---:|---:|
| B1 / directory | 8 | 1/1/947/947 | 2/24/21,570/21,570 | 35,718 | 1,356 | 3.658% | 0 | 74.083% |
| B1 / build-aware | 8 | 1/1/947/947 | 2/24/21,570/21,570 | 35,718 | 1,356 | 3.658% | 0 | 74.083% |
| B1 / structural | 21 | 1/79/79/79 | 2/1,719/2,393/2,544 | 29,694 | 7,380 | 19.906% | 0 | 8.738% |
| B2 / directory | 46 | 1/2/216/421 | 5/53/9,989/18,496 | 55,323 | 4,291 | 7.198% | 0 | 37.803% |
| B2 / build-aware | 40 | 1/2/10/842 | 5/38/228/33,892 | 56,858 | 2,756 | 4.623% | 0 | 69.269% |
| B2 / structural | 56 | 1/2/78/78 | 5/67/3,761/4,884 | 52,365 | 7,249 | 12.160% | 0 | 9.982% |
| B3 / directory | 64 | 1/11/101/209 | 3/461/5,867/28,960 | 131,893 | 11,692 | 8.143% | 0 | 24.407% |
| B3 / build-aware | 59 | 1/12/124/209 | 3/610/8,459/28,960 | 132,018 | 11,567 | 8.056% | 0 | 24.407% |
| B3 / structural | 70 | 1/14/65/70 | 3/732/5,234/12,153 | 130,266 | 13,319 | 9.276% | 0 | 10.242% |

结论：directory 是可解释的 baseline；structural 显著抑制 giant shard，但会增加 boundary ratio；build-aware 在 RocksDB 只略微降低 boundary ratio，在 brpc 则形成 69.269% 的 giant shard。因此不要静默替换 baseline，应按仓库/profile 选择策略。推荐 B1 使用 structural 做局部增量压力测试，B2 保留 directory 作为主要基准，B3 使用 build-aware 做规模基线，并以 structural 作为 giant-shard 对照。

## 5. API Fingerprint、Reverse Index 与 Impact Frontier

- fingerprint 只由公开 Namespace/Class/Struct/Function/Method/Type 的 qualified name、kind、signature 构成，函数体变化不会改变 fingerprint。
- `shard_edges` 持久化 boundary edge 的 source/destination shard 和 raw reference；`get_boundary_references(symbol)` 可反向回答 symbol 所在 shard 的依赖、被依赖 shard 及 boundary reference sites。
- `compute_impact_frontier` 只计算 changed shards、直接 dependent shards（一跳）和受影响 boundary edge；超过阈值标记 `wide_impact`，暂不递归 rebuild。

## 6. B1 固定 M1–M5 Mutation 结果

每个 case 都在临时 aria2 副本中执行：Full(A)、修改、Incremental(A→B)、Full(B)，比较 nodes/edges/raw references/shards/shard_edges 快照，并确认临时目录自动清理。

| Mutation | 预期 | parity | API fingerprint changed | boundary add/remove | files reparsed/reused | refs reprocessed/reused | shards updated/reused | boundary edges processed/reused | frontier / wide | incremental ms |
|---|---|---|---|---|---|---|---|---|---|---:|
| M1 local body | fingerprint unchanged, boundary_dirty=false | PASS | No | 0 / 0 | 1 / 1167 | 442 / 48,667 | 1 / 20 | 0 / 7,380 | 0 / false | 4,664.4 |
| M2 internal relation | current shard only | PASS | No | 0 / 0 | 1 / 1167 | 443 / 48,667 | 1 / 20 | 0 / 7,380 | 0 / false | 4,694.2 |
| M3 public signature | fingerprint changed, boundary_dirty=true | PASS | Yes | 0 / 0 | 1 / 1167 | 443 / 48,666 | 1 / 20 | 0 / 7,380 | 0 / false | 4,707.5 |
| M4 cross-shard add | boundary edge added | PASS | No | 1 / 0 | 1 / 1167 | 26 / 49,084 | 1 / 20 | 1 / 7,380 | 0 / false | 4,568.3 |
| M5 cross-shard remove | boundary edge removed | PASS | No | 0 / 1 | 1 / 1167 | 25 / 49,084 | 1 / 20 | 1 / 7,379 | 0 / false | 4,625.2 |

M1–M5 五项均 `parity=true`、`clean_restored=true`。M4/M5 的跨 shard edge 变化被准确记录；M3 触发 API fingerprint 变化并把受影响 shard 标记为 dirty。当前 fixture 的一跳 frontier 为 0，说明这些 mutation 没有命中一个额外 dependent shard；frontier 算法本身由单元测试覆盖。

另外对 B2/B3 做了代表性的 body-only mutation（均为单文件注释变更，Structural strategy）：

| Benchmark | file | parity | files reparsed/reused | refs reprocessed/reused | shards updated/reused | incremental ms |
|---|---|---|---|---|---|---:|
| B2 brpc | `src/brpc/builtin/common.cpp` | PASS | 1 / 1167 | 71 / 84,870 | 1 / 55 | 8,558.3 |
| B3 RocksDB | `db/db_impl/db_impl.cc` | PASS | 1 / 1477 | 2,266 / 308,845 | 1 / 69 | 30,590.3 |

两项代表性 mutation 同样保持 fingerprint/boundary 不变，且临时副本已清理。

## 7. ProvenLattice 适配性与主要发现

1. Tree-sitter 对三个真实仓库均扫描并尝试解析全部文件（100% coverage）。主要失败形态不是 IO/parser crash，而是宏/模板/平台条件代码导致的 syntax error nodes。
2. unresolved/ambiguous 主要来自宏样式调用、template/cast、成员/限定名调用以及外部/条件 include；B3 的 unresolved CALLS 数量随规模明显增长。Resolver 保持 conservative，不为提高 resolved rate 强行绑定。
3. Nodes、RawReference 和 Edges 从 B1→B2→B3 增长（29k/49k/37k → 49k/85k/60k → 119k/311k/144k），与 LOC 增长方向一致；RawReference 增长快于 LOC，反映真实 C++ 调用和宏密度。
4. Shard 结构能区分目录、build 文件和结构拆分的 trade-off。所有策略 isolated shard 均为 0；structural 将 giant ratio 压到约 8.7%–10.2%，代价是 12.2%–19.9% boundary ratio。
5. Full index 时间和 DB size 从 B1→B3 合理增长：约 4.0s/132MB、7.6s/237MB、26.2s/876MB。Symbol query P95 随图规模上升，caller/callee/subgraph 仍在可重复基线范围内。
6. 当前 Resolver、raw-reference cache、shard_edges 和一跳 frontier 已足以进入下一阶段 Shard Incremental 实验。M1–M5 的局部重算和 parity 是证据。
7. 进入下一阶段前没有必须阻断的架构问题。应记录的已知限制是复杂 C++ overload/template/function-pointer/virtual dispatch 仍可能 ambiguous/unresolved，以及 syntax-error 文件需要后续增量诊断改进；这些不应通过错误 Edge “修复”。

## 8. 后续 Benchmark Baseline 建议

对 B1/B2/B3 固定记录：`Full Index Time`、DB size、Nodes、Edges、RawReferences、Shards、Boundary Edges；每个 mutation 记录 `Files Reparsed/Reused`、`References Reprocessed/Reused`、`Shards Updated/Reused`、`Boundary Edges Processed/Reused`、Impact Frontier Size/WIDE_IMPACT、Incremental Time。查询侧继续记录 Symbol/Caller/Callee/Subgraph P50/P95。B1 用于每次回归，B2 用于主要效果验证，B3 用于规模、存储和查询延迟趋势；不修改 benchmark 仓库本身。

## 9. 可重复产物

- [`provenlattice-v0.3-shard.json`](provenlattice-v0.3-shard.json)：完整结构化报告（含三仓库 SHA/clean/shallow 校验、三种策略、V0.2 baseline、M1–M5 结果）。
- [`provenlattice-v0.3-mutations.json`](provenlattice-v0.3-mutations.json)：M1–M5 原始结果。
- [`measure.ps1`](measure.ps1)：统一 benchmark 统计口径。
- [`../../benchmarks/qualify_shards.py`](../../benchmarks/qualify_shards.py)、[`../../benchmarks/run_mutations.py`](../../benchmarks/run_mutations.py)、[`../../benchmarks/assemble_v03_report.py`](../../benchmarks/assemble_v03_report.py)：可重复执行的 qualification、mutation、报告汇总脚本。

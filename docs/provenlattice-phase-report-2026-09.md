# ProvenLattice

> 面向 Code Agent 的工程证据图谱基础设施：阶段进展、已验证能力与真实仓基线。

ProvenLattice 将代码结构、依赖关系、工程知识与可追溯证据建模为可查询图谱。它不是上下文压缩组件，也不依赖 TASCO；当前以独立的 CodeGraph 和 Knowledge Layer 演进、验证和发布。

本文档记录截至 **2026-09-14** 的阶段成果。所有数据仅来自冻结的真实仓 benchmark、确定性 fixture 与 Agent 对照实验；未实测的规模和延迟不会被表述为已验证能力。

## 当前状态

ProvenLattice 已完成从 C/C++ CodeGraph、可分片增量更新、多人/多分支 Overlay，到 CodeGraph + Knowledge 跨层证据的连续验证。当前最大的真实 C/C++ 仓库为 RocksDB（**622,772 LOC**）：全量构图 **26.19 s**、峰值内存 **1,069.5 MiB**、V0.2 图数据库 **835.5 MiB**；Caller、Callee、Subgraph 查询 P95 分别为 **165.1 / 72.4 / 68.1 ms**，Symbol 查询 P95 为 **449.0 ms**。

局部变更不再触发整仓重建：已在真实仓验证单文件重解析、单 Shard 更新、Boundary 影响检测和 Full/Incremental parity。aria2 的五个固定 mutation 样本为 **4.57–4.71 s**；brpc 与 RocksDB 的代表性单文件更新为 **8.56 s / 30.59 s**。这些是单次样本，不应作为稳定 P50/P95 延迟承诺。Overlay 已证明为 Delta 存储而非完整图复制，实际 Symbol 查询 P95 额外开销低于 **6%**。

当前可准确描述为：**10–30 万 LOC 是舒适验证区，62 万 LOC 已真实跑通并暴露出存储和 Symbol 查询性能债务；百万级与千万级仍是下一阶段专项验证目标。**

## 版本能力演进

| 阶段 | 已验证能力 | 关键证据 | 尚未宣称的能力 |
|---|---|---|---|
| **Core V0.2** | C/C++ 全量扫描、Tree-sitter 结构解析、保守符号/引用解析、稳定 Symbol Identity、SQLite 图快照与基础图查询 | aria2、brpc、RocksDB 均 100% 文件扫描/解析完成，无 hard parse failure；三档真实仓基线完整冻结 | 完整 C++ 语义调用图；宏、模板、函数指针、虚调用和复杂重载的强行解析 |
| **Core V0.3** | Shard 策略可插拔；API fingerprint；反向 Boundary 索引；一跳 Impact Frontier；Full/Incremental parity | M1–M5 均 PASS；局部 body、内部关系、公开签名、跨 Shard 边新增/删除均得到预期影响范围 | 局部更新的稳定 P50/P95；递归 dependency frontier 重建；所有仓库的一套通用最优分片策略 |
| **Core V0.4** | 共享 Base + Branch Overlay + Session Overlay；确定性优先级；tombstone；局部 graph reconciliation；冲突/重放控制 | 真实三仓 Overlay 均与 Full 物化结果 parity PASS；不同 Shard、同 identity、Boundary/API 三类冲突可识别；兼容 rebase 只重算一个 Shard | 自动解决源码 merge 冲突；跨大范围依赖链的自动重建；多分支、大规模并发压测 |
| **V1.0 Knowledge** | 文档、章节、需求（Requirement）、证据（Evidence）与 CodeGraph 的跨层建模；可追溯的证据契约；知识/代码增量更新与 Overlay parity | brpc 真实仓新增 1,404 个知识节点、736 条原始证据链接、80 条跨层边；31 项单元测试通过；fixture Full/Incremental/Overlay parity 通过 | LLM linker、Embedding/Vector DB、Runtime/Log、Commit History、MCP 或 UI |
| **V1.0-R1 检索验证** | 建立 Native、CodeGraph、Knowledge 三组 Agent 对照实验的可审计执行与隔离基线 | 18/18 qualification 通过、54/54 数据集审计完成；但旧 evaluator 的 `wrong_path` 规则使 task success 饱和为 0 | CodeGraph/Knowledge 的效果优于 Native；首证据时间与跨层边利用率 |
| **V1.0-R2 接口验证** | 收紧 Agent 查询、返回 bundle 和证据引用的接口观测 | T05 的 CodeGraph required recall 恢复至 1.0；R2 interface/artifact gate 通过 | Knowledge 的可重复收益；紧凑证据 bundle |
| **V1.0-R2.1 实验收口** | 复现并拆分 CodeGraph 与 Knowledge 的问题归因 | 21/21 有效产物；Knowledge 的必需证据召回达到 1.0，但 citation/evaluator contract 仍不稳定 | 跨任务的稳定正向区；仅凭一次 T05 优化就宣称收益 |
| **V1.0-R2.2 评估契约验证** | 将概念召回、精确证据、路径/fragment 与无效引用分开评估 | 51 个冻结 cell 离线重放确定；E1–E10 fixture 通过；识别 8 个 evaluator false negative | CodeGraph/Knowledge 已有效；R2.2 只证明测量有效性 |
| **V1.0-R2.3 Agent 再验证** | 在修正后的冻结协议下验证 CodeGraph / Knowledge 的任务效用边界 | 3 任务 × 3 条件 × 3 次重复共 27/27 VALID；Knowledge 在 T03 有稳定效率收益，T05 为积极候选区 | “Knowledge 对所有任务都更好”；当前证据 bundle 已达到最优精度 |
| **V1.0-R2.4 离线 bundle 资格验证** | 在不运行 Agent 的前提下评估 bundle 裁剪策略 | Loose 是唯一同时保留 T01/T03/T05 全部必需证据的策略；T01/T03 bundle 从 39/24 缩至 4 项 | Agent 端收益已经复现；路径精度语义已完成验证 |

### V0.2：从“可建图”到“真实 C/C++ 基线”

这一阶段证明的是最小而保守的 CodeGraph 能落在真实工程上：文件、节点、RawReference、解析成功的语义边和 Shard 均被持久化；无法可靠解析的 C++ 语义保持 ambiguous 或 unresolved，而不是伪造边。三个冻结仓均没有 parser 异常导致的文件丢失。Tree-sitter `ERROR` 节点存在于宏和条件编译密集文件中，但不等于 parse failure。

### V0.3：从“整图可用”到“局部变更可控”

这一阶段证明更新路径与变更影响相关，而非直接与仓库总规模相关。单文件改动时仅重解析该文件、重算相关引用并更新当前 Shard；公开签名变化会使 API fingerprint 变化并标记 Boundary 影响；跨 Shard 引用的新增和删除会被分别记录。所有 mutation 均与修改后 Full Index 快照一致（parity PASS）。

Shard 策略的结论也已明确：目录分片是可解释基线；structural 可降低 giant shard，但会抬升跨边比例；build-aware 的收益随仓库结构而变。因此当前是“按仓库画像选择策略”，不是“一个策略通吃”。

### V0.4：从“单工作副本”到“多分支共享图”

有效视图为 `Base + Branch Overlay + Session Overlay`，优先级为 `Session > Branch > Base`。Overlay 只保存 Node、Edge、RawReference、Shard 和 BoundaryEdge 的 ADD/UPDATE/DELETE Delta；DELETE 使用 tombstone，绝不改写 Base。真实小改动的 Branch Overlay 占 Base 的 0.0563%–0.2664%，证明分支数增长不会线性复制完整图。

### V1.0：从代码关系到工程证据关系

V1.0 为 Markdown 文档、章节、需求、约束和验收条件建立稳定 identity，并通过 RawEvidenceLink 与跨层 Edge 连接到代码。brpc 实验显示 Knowledge 层只增加约 5.14 MB（2.14%）数据库；当前存储瓶颈仍是 CodeGraph 中的 parser cache、RawReference 与索引，不是 Knowledge 层。

### V1.0-R1：先验证实验是否可信

R1 建立了 Native、CodeGraph、Knowledge 三个对照组的完整实验框架：18/18 qualification gate 通过，54/54 运行可审计，并严格隔离不同组可使用的能力。它首先证明的是**实验数据可复核**，而不是 ProvenLattice 已优于 Native。旧 evaluator 对 `wrong_path` 的定义过窄，使全部 54 次运行的任务成功率饱和为 0；因此 R1 明确冻结为基础设施与观测基线，并暴露了首证据时间、跨层边使用 ID 未被记录的问题。

### V1.0-R2 与 R2.1：收紧接口，定位问题边界

R2 以 T05 为接口资格实验，验证了 Agent 可以从 CodeGraph 的结构化返回中恢复必需证据召回（CodeGraph-R2 为 1.0），但 Knowledge-R2 只达到 0.667，且两个结构化组都返回了过多未使用证据。R2.1 将实验扩展并复现：Knowledge-R2.1 的三次必需证据召回均为 1.0，表明缺口不在知识覆盖或 Cross-Layer Link 是否存在；但引用与 evaluator 的契约仍不稳定。因此两阶段的结论是 **接口和可观测性已有进展，跨任务效果仍 HOLD**。

### V1.0-R2.2：让“实验失败”可以被正确解释

R2.2 不重新运行 Agent，而是对 R1、R2、R2.1 的 51 个冻结 cell 离线重放。它引入 GroundTruthV2，将概念召回、精确证据召回、可接受替代证据、上下文支持、未知证据和无效证据分开判定；路径和 document fragment 也被标准化。结果识别出 8 个 evaluator false negative 与 4 个真实的 invalid evidence。此阶段只说明**评估契约可靠**，不能单独证明产品效果。

### V1.0-R2.3：从“数据结构正确”到“对 Agent 是否有帮助”

该阶段不是图性能 benchmark，而是 Agent 任务效果验证。27 个冻结执行均有效；Knowledge 在 T03 上以更少工具轮次、文件和读取量完成任务，在 T05 上相对 Native 为 3/3 对 1/3 的积极候选结果。与此同时，T01 出现 evidence bundle 干扰项，说明下一优先级是 Query / bundle precision，而不是盲目扩展新的 Evidence Layer。

### V1.0-R2.4：在上线前压缩证据 bundle

R2.4 是离线 bundle 资格实验，没有运行新的 Agent。它在 R2.3 的冻结返回集上评估裁剪策略：Loose 是唯一能对 T01、T03、T05 同时保留全部必需证据的策略；T01/T03 的返回规模可从 39/24 项压缩至 4 项。T05 的 Balanced 与 Aggressive 会丢失必需证据，因而不合格。下一步应把 Loose 策略接入新的 Agent 实验，并再次测量任务成功、证据精度和路径精度语义。

## 真实仓 CodeGraph 基线

**统一口径：**C/C++ LOC 为去除空白和注释后的物理行；全量构图包含扫描、解析、建图、解析/消歧、分片和 SQLite 写入；查询预热 3 次后采样 30 次；Subgraph 参数为 `max_hops=2`、`max_nodes=100`。

| 指标 | aria2（11.9 万 LOC） | brpc（22.7 万 LOC） | RocksDB（62.3 万 LOC） |
|---|---:|---:|---:|
| C/C++ LOC | 118,926 | 227,154 | 622,772 |
| 文件扫描 / 解析 | 1,168 / 1,168 | 1,168 / 1,168 | 1,478 / 1,478 |
| 硬解析失败（Hard Parse Failures） | 0 | 0 | 0 |
| 文件解析覆盖率（Parse Coverage） | 100% | 100% | 100% |
| Nodes | 29,117 | 48,929 | 118,655 |
| RawReferences | 49,109 | 84,941 | 311,111 |
| 已解析引用（Resolved References） | 10,804 | 17,210 | 54,481 |
| 歧义引用（Ambiguous References） | 13,966 | 28,421 | 101,090 |
| 未解析引用（Unresolved References） | 24,339 | 39,310 | 155,540 |
| Edges | 37,074 | 59,614 | 143,585 |
| Shards | 8 | 46 | 64 |
| Boundary Edges | 1,356 | 4,291 | 11,692 |
| 全量构图 | 3.95 s | 7.59 s | 26.19 s |
| 峰值内存 | 186.5 MiB | 308.9 MiB | 1,069.5 MiB |
| V0.2 SQLite 图数据库 | 125.9 MiB | 226.2 MiB | 835.5 MiB |

### 规模趋势与存储说明

- LOC 从 aria2 到 RocksDB 增长 5.24 倍；Nodes、Edges 分别增长 4.08、3.87 倍，而 RawReferences 增长 6.34 倍。
- RawReference 密度，而不仅是 LOC，是当前构图时间、SQLite 写入与内存增长的关键解释变量；RocksDB 因宏、模板和调用密度呈现轻微超线性增长。
- V0.2 的 DB 尺寸包含完整 ParsedFile cache。因而当前的 835.5 MiB 是“现状实测”，不是最终稳态存储成本；parser cache 拆分/压缩是明确性能债务。

## 图查询性能（P50 / P95）

| 查询 | aria2 | brpc | RocksDB |
|---|---:|---:|---:|
| Symbol | 87.4 / 93.0 ms | 159.8 / 171.1 ms | 420.3 / 449.0 ms |
| Caller | 50.7 / 54.1 ms | 39.6 / 40.9 ms | 154.5 / 165.1 ms |
| Callee | 15.9 / 16.6 ms | 30.2 / 32.3 ms | 69.8 / 72.4 ms |
| Subgraph | 25.9 / 28.0 ms | 27.4 / 28.9 ms | 66.3 / 68.1 ms |

关系查询在当前最大真实仓保持数十至一百余毫秒；最明显瓶颈是 Symbol 查询，RocksDB P95 已到 449.0 ms。根因已定位为当前 `name OR qualified_name OR LIKE` 路径，需要专用索引或分步查询；在百万级之前应优先处理。

## 增量更新与 Overlay

### 单文件增量构图：已证明的范围与现有时间样本

| 仓库 / 场景 | 文件重解析 / 复用 | 引用重算 / 复用 | Shard 更新 / 复用 | 结果 | 单次耗时 |
|---|---:|---:|---:|---|---:|
| aria2 M1：局部函数体 | 1 / 1,167 | 442 / 48,667 | 1 / 20 | parity PASS；fingerprint 不变 | 4,664.4 ms |
| aria2 M2：内部关系 | 1 / 1,167 | 443 / 48,667 | 1 / 20 | parity PASS；仅当前 Shard | 4,694.2 ms |
| aria2 M3：公开签名 | 1 / 1,167 | 443 / 48,666 | 1 / 20 | parity PASS；Boundary 标脏 | 4,707.5 ms |
| aria2 M4/M5：跨 Shard 边增/删 | 1 / 1,167 | 26 / 49,084 或 25 / 49,084 | 1 / 20 | parity PASS；仅对应 Boundary Edge 改变 | 4,568.3 / 4,625.2 ms |
| brpc：body-only | 1 / 1,167 | 71 / 84,870 | 1 / 55 | parity PASS | 8,558.3 ms |
| RocksDB：body-only | 1 / 1,477 | 2,266 / 308,845 | 1 / 69 | parity PASS | 30,590.3 ms |

以上是指定 mutation 的单次实测，不是 P50/P95。它们证明**更新范围**已经局部化，但尚不足以发布“单文件更新延迟”的稳定服务指标。下一轮应固定 1 / 5 / 20 文件变更集，记录 P50、P95、峰值内存及 Boundary/Frontier 分布。

### Branch / Session Overlay：存储、应用与查询代价

| 仓库 | Base DB | Branch Overlay | Overlay / Base | Session Overlay | 触及 Shard | Apply | Symbol 查询 P95 开销（Branch / Branch+Session） |
|---|---:|---:|---:|---:|---:|---:|---:|
| aria2 | 126.8 MiB | 240 KiB | 0.1848% | 28 KiB | 1 | 2,312 ms | 0.56% / 5.22% |
| brpc | 229.0 MiB | 132 KiB | 0.0563% | 28 KiB | 1 | 3,953 ms | 5.96% / 2.17% |
| RocksDB | 843.1 MiB | 2.25 MiB | 0.2664% | 28 KiB | 1 | 15,014 ms | 1.91% / 5.89% |

注：此表使用 V0.4 schema migration 后的 Base DB 字节数，故与 V0.2 基线表略有差异；两者不应混作同一构建产物。三仓 Overlay 查询 P95 开销均低于 6%，这是本机测试结果，不是跨环境性能承诺。

## Knowledge Layer 基线（brpc）

| 指标 | 实测值 |
|---|---:|
| 文档数（Documents） | 149 |
| 章节数（Sections） | 1,255 |
| 知识节点数（Knowledge Nodes） | 1,404 |
| 原始证据链接数（Raw Evidence Links） | 736 |
| 跨层边数（Cross-Layer Edges） | 80 |
| 知识索引时间（Knowledge Index Time） | 26,641.66 ms |
| 峰值工作集（Peak Working Set） | 155.6 MiB |
| 合并数据库增长（Combined DB Growth） | 5.14 MiB（2.14%） |
| 已解析证据查询 P50 / P95（Resolved Evidence Lookup） | 0.5578 / 1.2693 ms |
| 文档/章节 → 代码查询 P50 / P95（Document/Section → Code） | 24.4154 / 27.2017 ms |
| 跨层子图查询 P50 / P95（Cross-Layer Subgraph） | 23.1982 / 26.2102 ms |

## 当前适用规模与后续计划

| 规模层级 | 当前判断 |
|---|---|
| 10 万 LOC | 已实测，适合快速开发和回归 |
| 20–30 万 LOC | 已实测，当前的主验证区 |
| 60 万 LOC | 已实测跑通，已能观察到 DB、RawReference 和 Symbol Query 压力 |
| 100 万 LOC | 值得作为下一档正式 qualification，但尚未实测 |
| 1,000 万+ LOC | 目标规模；现阶段不可宣称已支持 |

下一条 Graph Core 规模实验是 **Million-line Scale Qualification**：以 100 万、200 万、500 万、1,000 万+ LOC 分档，固定记录 Full Index Time、Peak RSS、DB Size、Nodes/Edges/RawReferences per LOC、1/5/20 文件增量 P50/P95、四类查询 P50/P95 与 Overlay Query Overhead。优先优化 parser cache 存储和 Symbol 查询索引，再用新数据决定是否需要更深层的 resolver、writer 或分片策略改造。

## 参考实验报告

- [V0.2 C/C++ baseline](benchmarks/provenlattice-v0.2-baseline.md)
- [V0.3 Shard qualification & incremental foundation](benchmarks/provenlattice-v0.3-shard.md)
- [V0.4 Branch & Session Overlay](benchmarks/provenlattice-v0.4-overlay.md)
- [V1.0 Knowledge baseline](benchmarks/provenlattice-v1.0-knowledge.md)
- [V1.0-R1 Retrieval qualification](benchmarks/provenlattice-v1.0-r1-retrieval.md)
- [V1.0-R2 T05 interface qualification](benchmarks/provenlattice-v1.0-r2-t05.md)
- [V1.0-R2.1 Experiment closure](benchmarks/provenlattice-v1.0-r2.1.md)
- [V1.0-R2.2 Evaluation contract qualification](benchmarks/provenlattice-v1.0-r2.2-evaluator.md)
- [V1.0-R2.3 Agent revalidation](benchmarks/provenlattice-v1.0-r2.3.md)
- [V1.0-R2.4 Offline bundle qualification](../experiments/retrieval-v2/r2_4/results/qualification-r2.4.md)

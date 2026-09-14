# ProvenLattice Research & Validation Framework V1

> 将 ProvenLattice 从“按版本自然生长的工程原型”组织为一套可复现、可归因、可扩展的工程证据图研究与验证体系。

**状态：FRAMEWORK READY FOR FREEZE**
**适用范围：**后续 Graph Core、Knowledge、Retrieval、Agent Integration 和规模实验。
**不替代：**现有版本报告、冻结 benchmark、实现设计或发布说明。已有实测数据见 [阶段进展与真实仓基线](provenlattice-phase-report-2026-09.md)。

当前证据映射、等级和实验 backlog 见 [Evidence Inventory & Gap Matrix V1](provenlattice-evidence-inventory-gap-matrix-v1.md)。

正式冻结时须在发布记录中写入 `framework_version`、`git_commit`、`sha256` 与 `freeze_date`；本文术语、RQ、Track、Failure Taxonomy、Evidence Level 与 Benchmark Metadata 在冻结后只能以版本化扩展方式变更，不能随单轮实验结果改写。

## 1. 目标与原则

ProvenLattice 的目标不是只证明“能更快建一个图”，也不是只比较某一组 Agent 的任务成功率。它要回答的是：是否可以将真实软件工程中的代码、文档、需求和其他证据稳定地映射为可增量维护、可追溯、可被 Agent 消费的工程证据图；以及这套能力在检索和最终任务上何时有效、何时失效、为什么失效。

因此，项目以分层资格验证为原则：下层正确性是上层实验的前提，但任何上层结果都不能反向替代下层证据。

```text
图基础层正确
      ↓
图服务可用且高效
      ↓
证据检索少而准
      ↓
Agent 实际采用并正确消费
      ↓
最终工程任务改善
```

这意味着：

- Agent 表现不好，不能直接归因于“图没用”；需要区分图缺失、解析失败、检索漏失、bundle 过滤、Agent 未采用、推理失败和评估误判。
- 图构建正确，也不能推出 Agent 必然受益；Agent 可能没有调用、没有理解或没有正确引用服务返回的证据。
- 外部论文的公开数字仅是参照，不能与不同仓库、硬件、语言和图 schema 下的本机结果直接比较。

## 2. 系统模型：三个相互依赖的层

```text
                 ProvenLattice
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   Graph Fabric    Graph Services   Agent Integration
     图基础层          图服务层          Agent 集成层
```

| 层级 | 核心问题 | 输入 → 输出 | 当前/规划能力 |
|---|---|---|---|
| 图基础层（Graph Fabric） | 工程信息是否被准确、稳定、增量地映射为图？ | 源代码、文档、需求 → Nodes、Edges、Raw Evidence、Overlay | 解析、稳定 identity、引用解析、分片、增量、Overlay、Knowledge 节点与跨层边 |
| 图服务层（Graph Services） | 原始图能否转化为稳定、精确、可消费的工程能力？ | 图与任务意图 → 查询结果、导航路径、Evidence Bundle | 符号查询、调用关系、子图、影响分析、文档 ↔ 代码、证据追溯、任务感知检索 |
| Agent 集成层（Agent Integration） | Agent 是否实际采用并正确使用图服务？ | Agent + Tool/API → 证据使用、引用、最终任务结果 | 工具契约、能力隔离、查询策略、citation contract、会话证据控制 |

## 3. 资格体系：四个 Qualification Level 与六条 Benchmark Track

四个 Qualification Level 规定“先证明什么”，六条 Track 规定“具体测什么”。

| Qualification Level | 回答的问题 | 对应 Benchmark Track |
|---|---|---|
| L1 图正确性资格验证 | 图建得对不对？ | A. 图保真度 |
| L2 图系统资格验证 | 大仓中能否稳定、低成本运行？ | B. 图系统与规模；增量工程维度 |
| L3 检索与证据资格验证 | 图服务能否返回正确且紧凑的工程证据？ | C. 检索与导航；D. 证据质量 |
| L4 Agent 效果资格验证 | Agent 是否采用图并改善真实任务？ | E. Agent 采用与导航；F. 最终任务效果 |

| Track | 要回答的问题 | 必测指标 | 通过后可作出的结论 |
|---|---|---|---|
| A. 图保真度（Graph Fidelity） | 图是否正确表达代码与工程证据？ | Hard Parse Coverage、Syntax-clean Rate、Recovered-with-error Rate、边 Precision/Recall/F1、已解析/歧义/未解析分布、稳定 ID 正确性、provenance 正确性、Full/Incremental/Overlay parity | 在定义的语言、关系类型和仓库范围内，图的表示可信 |
| B. 图系统与规模（Graph Systems & Scale） | 图能否工程化构建、维护与查询？ | 全量构图时间、LOC/s、峰值 RSS、DB 大小、Bytes/LOC、更新 P50/P95、查询 P50/P95/P99、Overlay 放大率 | 在测得的规模和工作负载下，系统成本可接受 |
| C. 检索与导航（Retrieval & Navigation） | 图查询能否找到正确文件、函数、行和路径？ | File/Function/Line Recall@k、Precision@k、F1、MRR、NDCG、IoU、Coverage@Budget | 图服务对定位和导航有独立可测的检索效用 |
| D. 证据质量（Evidence Quality） | 返回给上层的 Evidence Bundle 是否少而准？ | Required Retention、干扰项抑制率、Bundle Precision、有效证据密度、会话唯一证据暴露、重复暴露 | 在指定任务和预算下，bundle 能保留必要证据并控制上下文负担 |
| E. Agent 采用与导航（Agent Utilization） | Agent 是否真的调用、理解和采用图服务？ | Graph/Knowledge Adoption、首相关证据调用、首正确文件调用、查询数、returned-but-unused、used/returned、citation hygiene | 可区分“服务无效”和“Agent 未采用/误用” |
| F. 最终任务效果（End-task Effectiveness） | 最终软件工程任务是否更正确或更低成本？ | Task Success、Concept Recall、Evidence Precision、Pass@1、Patch Apply、测试通过率、Token、轮次、文件、时延 | 在受控对照下，ProvenLattice 对目标任务有端到端收益或无收益 |

## 4. Research Questions

| RQ | 问题 | 主要 Track | 需要避免的错误推论 |
|---|---|---|---|
| RQ1 图保真度 | ProvenLattice 能否准确表达真实仓库中的结构关系和工程证据？ | A | `resolved rate` 不是图准确率；必须按边类型报告 Precision/Recall |
| RQ2 可扩展性 | 能否以可接受的存储、更新和查询成本扩展到百万/千万行？ | B | 不能由 62 万 LOC 线性外推至千万行 |
| RQ3 检索质量 | 图检索是否比文本检索更容易找到正确证据？ | C | Agent 成功率不能代替独立检索质量 |
| RQ4 证据效率 | 能否以更少干扰、受控预算返回所需上下文？ | D | 单查询合格不代表多轮会话不会证据过载 |
| RQ5 Agent 采用 | Agent 是否实际调用并正确消费图服务？ | E | “工具可用”不等于“工具被采用” |
| RQ6 最终任务效果 | Agent 使用 ProvenLattice 后是否更正确、更低成本？ | F | 端到端提升不等于图本身必然更准确 |
| RQ7 泛化性 | 规律是否跨仓库、任务、语言和模型成立？ | A–F | 单仓、单模型、单任务不能宣称泛化 |
| RQ8 增量工程 | 持续修改、多分支、多会话下是否仍保持一致与低成本？ | A、B | 单文件 body-only mutation 不能代表真实协作负载 |

### Graph Fidelity Gold Set Protocol

边类型级 Precision/Recall/F1 必须基于可审计的 Gold Set，而不能仅由 `resolved` 数量推导。对千万行级仓库，不要求人工检查全部关系；Gold Set 应按下列维度分层抽样，并冻结为长期 benchmark asset：

| 分层维度 | 建议类别 |
|---|---|
| 语言 | C/C++ 起步，后续扩展 Python、Java、Go、Rust、TypeScript |
| 关系类型 | CALL、REFERENCE、IMPORT、INHERIT、CONTAIN、DEFINE、DOC→CODE、REQUIREMENT→CODE |
| 难度 | 同文件、跨文件、跨模块、跨 Shard、宏密集、重载、歧义名称、生成代码 |
| 仓库结构 | 多模块、扁平目录、header-heavy、macro-heavy、generated-code-heavy |

Gold Set 同时包含正例与负例/混淆例。正例验证真实应存在的关系；负例专门覆盖同名干扰、重载、namespace collision、宏展开、条件编译、header declaration vs definition、ambiguous include 与跨模块同名符号，验证系统能正确 abstain 而非误连边。

每个抽样单元由两位标注者独立确认来源、目标和关系类型；分歧经复核后形成冻结 Gold Set。正式研究可报告标注者一致性。Gold Set 的变更必须增加版本，而不能回写既有实验的 Ground Truth。

对于 C/C++，每个 Gold Set judgement 还记录 Build Context，避免将编译上下文缺失误归因于 Graph 或 Resolver：

```text
build_context_available
compile_commands_available
build_target
platform
preprocessor_context
generated_source_policy
```

若所需编译上下文不可用，应标注 `BUILD_CONTEXT_UNAVAILABLE` 并从该上下文下的 Resolver 能力分母中单独报告。

ProvenLattice 的 Resolver 允许“保守弃权”，因此除常规边 Precision/Recall/F1 外，必须按关系类型报告：

| 指标 | 定义 | 解释 |
|---|---|---|
| 已解析精度（Resolution Precision） | 被标为 resolved 的关系中，正确关系的比例 | 系统说“确定”时有多可靠 |
| 已解析覆盖率（Resolution Coverage） | Gold Set 中被正确 resolved 的关系比例 | 保守策略覆盖了多少真实关系 |
| 弃权率（Abstention Rate） | ambiguous + unresolved 占候选关系的比例 | 为了避免误连放弃了多少关系 |
| 选择性风险（Selective Risk） | resolved 子集上的错误率 | 在主动选择回答的前提下残留多少风险 |

## 5. 证据链与失败归因

每个 Agent 实验 Cell 必须保留从结果到原始工程事实的链路：

```text
Task Result
    ↓
Evidence Used by Agent
    ↓
Evidence Returned by Service
    ↓
Evidence Available in Graph
    ↓
Source Code / Document Origin
```

失败不应被强制压缩为单一标签。每个 Cell 应记录 `primary_failure`、`contributing_failures[]` 和 `first_broken_stage`；例如一次任务可将 `CITATION_FAILURE` 标为主因，同时记录 `SESSION_EVIDENCE_OVERLOAD` 与 `EXCESSIVE_QUERYING` 为次因。

最低限度的记录字段为：任务、Required Concepts、Required Evidence、可接受替代项、来源是否存在、图中是否存在、Candidate Set 是否包含、Bundle 是否保留、Agent 是否暴露、Agent 是否使用、Citation 是否 resolve、最终答案是否正确、evaluator 判定、运行是否有效、实际模型/Agent/环境及原始引用 ID。

| Failure Code | 定义 | 应优先检查的层 |
|---|---|---|
| `GRAPH_ABSENCE` | Required Evidence 未进入图 | Graph Fabric |
| `SOURCE_ABSENCE` | Required Evidence 在冻结仓库或文档来源中不存在 | Source / Benchmark Asset |
| `RESOLUTION_FAILURE` | 原始信息存在，但未形成正确或可用关系 | Graph Fabric |
| `RETRIEVAL_MISS` | 图中存在证据，查询服务没有返回 | Graph Services |
| `BUNDLE_SUPPRESSION` | 候选集中存在证据，但被过滤/预算策略丢弃 | Graph Services |
| `SESSION_EVIDENCE_OVERLOAD` | 多轮查询导致唯一或重复证据暴露超出任务消费能力 | Graph Services / Agent Integration |
| `EXCESSIVE_QUERYING` | Required Evidence 已齐备后仍进行无增益查询 | Agent Integration |
| `AGENT_NON_USE` | Agent 收到证据，却没有采用 | Agent Integration |
| `CITATION_FAILURE` | Agent 采用线索但引用对象、ID 或路径不符合契约 | Agent Integration |
| `TASK_REASONING_FAILURE` | 证据充分但最终推理/结论错误 | Agent Integration |
| `EVALUATION_FAILURE` | 可接受答案被 evaluator 错判 | Evaluation |
| `INFRASTRUCTURE_FAILURE` | 网络、Sandbox、工具、运行环境或产物链路异常，使该运行无效 | Infrastructure |

归因应允许统计为分布，而非只报告总成功率。例如，一批失败可被拆解为 Graph Fabric、Retrieval、Agent Usage、Reasoning 和 Evaluator 等类别，为下一轮实验提供明确的修复优先级。

## 6. 长期 Benchmark 资产

### 6.1 Engineering Task Benchmark

每个任务不是单纯 Prompt，而是长期可复用的 benchmark asset：

```text
Task Prompt
Required Concepts
Required Evidence
Acceptable Alternatives
Distractors
Graph Oracle
Retrieval Oracle
Agent Evaluation Contract
```

每个 Retrieval Task 还应分别报告 Graph Oracle Coverage、Conditional Retrieval Recall 与 End-to-end Recall，隔离 Graph Fabric 和 Graph Services 的责任：

```text
Graph Oracle Coverage = Graph 中存在的 Required Evidence / Required Evidence 总数
Conditional Retrieval Recall = Retriever 返回的 Required Evidence / Graph 中存在的 Required Evidence
End-to-end Recall = Retriever 返回的 Required Evidence / Required Evidence 总数
```

| Task Family | 主要验证层 | 典型输出 |
|---|---|---|
| Symbol Lookup | 图保真度 / 检索 | 正确符号定义 |
| Caller / Callee | 图保真度 / 检索 | 关系路径与调用方/被调用方 |
| Dependency Trace | 图保真度 / 检索 | 跨模块依赖链 |
| Document → Code | Knowledge / 检索 | 需求或设计对应实现 |
| Code → Document | Knowledge / 检索 | 实现的设计依据与约束 |
| Module Understanding | 检索 / Agent | 模块职责、边界和关键路径 |
| Impact Analysis | 增量图 / 检索 | 改动影响范围与证据 |
| Bug Localization | Agent | 文件、函数或行级候选 |
| Change Planning | Agent | 变更点、依赖和验证计划 |
| Cross-module Diagnosis | 图 + Agent | 跨模块问题定位与因果链 |
| Historical Change Reasoning | Future History Layer | 变更动机与版本证据 |
| Runtime-to-Code Diagnosis | Future Runtime Layer | 日志/运行时现象到代码映射 |

### 6.2 Graph Build Benchmark

图系统实验按语言、规模和工程结构三轴组织；每个格子冻结仓库提交、排除规则、机器环境和运行参数。

| 维度 | 建议分档 |
|---|---|
| 语言 | C/C++、Python、Java、Go、Rust、TypeScript |
| 规模 | 100K、500K、1M、5M、10M+ LOC |
| 工程结构 | monorepo、多模块、扁平项目、header-heavy、generated-code-heavy、macro-heavy |

Scale 不是单一的“10M+ PASS/FAIL gate”，而是逐档资格状态。建议规模 band 为 S1 `[0.08M, 0.2M)`、S2 `[0.4M, 0.8M)`、S3 `[0.8M, 1.5M)`、S4 `[4M, 7M)`、S5 `≥8M LOC`；每个 band 单独标记 `QUALIFIED`、`HOLD` 或 `BLOCKED`，并记录阻塞资源与协议版本。

每档统一记录：LOC、文件数、Nodes、Edges、RawReferences、全量构图时间、峰值 RSS、DB Size、Bytes/LOC、Bytes/Node、Bytes/Edge、Nodes/KLOC、Edges/KLOC、RawReferences/KLOC、Edges/Node、RawReferences/Node、四类查询 P50/P95/P99、1/5/20 文件更新 P50/P95、Shards touched、Boundary Edges 重算量以及 Full/Incremental parity。Scale Model 应同时以 `Files / Symbols / References / Edges` 解释成本，不能只依赖 LOC。

Scale Benchmark 必须区分三种负载，不能用单次单查询数据替代在线系统结论：

| 负载 | 额外必测指标 | 目的 |
|---|---|---|
| 首次构建（Cold Build） | files/s、symbols/s、references/s、峰值临时磁盘、最终磁盘、CPU 利用率 | 描述首次部署成本与资源上限 |
| 稳态更新（Steady-state Update） | 更新 P50/P95、Time-to-Freshness、影响范围、parity | 描述源码变化到查询可见新状态的端到端时间 |
| 在线查询（Online Query） | QPS、并发 1/4/16/32 下的 P50/P95/P99、缓存状态 | 描述多 Agent/多开发者并发使用成本 |

### Incremental Mutation Benchmark

更新实验除“改动文件数”外，必须固定修改类型。每种 Mutation 在临时副本中运行 `Full(A) → Mutation → Incremental(A→B) → Full(B)`，并验证快照 parity。

| Mutation Family | 主要验证目标 |
|---|---|
| Function body edit | API 不变时的局部更新 |
| Public signature change | API fingerprint 与 impact frontier |
| Add / Delete symbol | 节点、引用、新增与 tombstone |
| Rename symbol | Stable identity 与 remove-add 行为 |
| Move file | path/shard/identity 迁移 |
| Add / Remove cross-module call | Boundary Edge 新增与清理 |
| Header change | C/C++ 高 fan-out 场景 |
| Branch / Session overlay edit | Delta 持久化与视图合成 |
| Merge / Rebase | Overlay reconcile 与冲突归因 |

每个 Mutation 至少记录：files reparsed/reused、symbols recomputed、references reprocessed/reused、shards touched、boundary edges recomputed、update latency、Time-to-Freshness、Full/Incremental parity、primary/contributing failure（如失败）。由此检验更新复杂度是否主要由 **change + impact** 而非 repository size 决定。

### 索引成本摊销（Amortized Cost）

图系统与文本搜索的成本模型不同，不能只比较单次 Query Latency。对每种 workload，报告：

```text
Total Cost(N tasks)
= Initial Index Cost
+ Incremental Maintenance Cost
+ Σ Query Cost
```

在 `N = 1 / 10 / 100 / 1,000` 个任务下分别测量时间、机器成本与上下文成本，并报告 break-even 区间。这样可以区分“一次性临时任务中 grep 更便宜”与“高频工程任务中索引成本已被检索收益摊平”的场景。

### 6.3 Agent 与模型矩阵

Agent 实验至少包含 Native、Agent + CodeGraph、Agent + CodeGraph + Knowledge 三组。所有组应使用相同任务、相同仓库提交、相同模型配置和同一 evaluator；仅能力边界不同。随后增加多个模型 cohort，测试收益是否依赖单一模型。

| 维度 | 最小要求 | 后续扩展 |
|---|---|---|
| 对照组 | Native / CodeGraph / Knowledge | 文本检索 Agent、外部图工具 Agent |
| 模型 | 一个冻结模型 | 多模型 cohort |
| 仓库 | 一个受控真实仓 | 多仓、多语言 |
| 任务 | 理解与证据任务 | 定位、规划、修复与公开 benchmark |
| 重复 | 每个 cell 多次重复 | 随机种子、提示模板和工具策略消融 |

Agent 实验还必须记录 Session 级证据指标；单查询 Bundle Precision 合格不代表多轮 Agent 会话不会过载。

| 指标 | 定义 |
|---|---|
| Queries per Task | 完成一个任务实际发起的服务查询数 |
| Unique Evidence Exposed per Session | 会话中首次暴露的唯一 Evidence 数 |
| Repeated Evidence Exposure | 已暴露 Evidence 被重复返回的次数/比例 |
| New / Useful New Evidence per Query | 每次查询带来的新增证据及其中实际使用的比例 |
| Evidence Saturation Point | 所有 Required Evidence 首次齐备的查询序号 |
| Queries after Last Required Evidence Found | 饱和点之后仍继续发起的查询数 |
| Returned-but-unused | 返回但未被 Agent 使用的证据数 |
| Citation Fan-out | 最终答案引用的不同 Evidence 数 |
| Invalid / Unknown Citation Rate | 不符合契约或不存在的引用比例 |
| Marginal Evidence Utility(q) | 第 q 次查询新增的有效证据数 / 该次返回证据数 |

## 7. 外部参照与复现策略

外部系统分属不同问题域，应作为按 Track 选择的参照，而不是单一排行榜：

| 参照方向 | 候选项目 / 工作 | 用途 |
|---|---|---|
| 大图系统与存储 | [Joern / flatgraph](https://flatgraph.joern.io/benchmarks/index.html)、[SCIP](https://github.com/sourcegraph/scip)、[Kythe](https://github.com/kythe/kythe) | Graph build、存储、精确导航与系统设计参照 |
| 图辅助代码 Agent | [RepoGraph](https://arxiv.org/abs/2410.14684)、CodexGraph、[GraphCoder](https://arxiv.org/abs/2406.07003) | 跨模型、检索和端到端任务指标参照 |
| 定位与修复 | LocAgent、[ARISE](https://github.com/FARD-Lab/ARISE) | 文件/函数/行级定位、修复和预算指标参照 |
| Agent 图工具采用 | [CodeCompass](https://github.com/tpaip607/research-codecompass) | Tool Adoption 与导航路径指标参照 |
| 工程化开源工具 | [CodeGraphContext](https://github.com/codegraphcontext/codegraphcontext) | 同机可复现的 CLI/MCP 基线候选 |

外部数字只能在 related work 或 external reference 中引用。要宣布强横向结论，必须完成同机复现：相同仓库、相同 commit、相同硬件、相同资源限制、相同任务、相同指标定义。

同机对比必须同时给出两种视图：**Common Capability Comparison** 仅比较各系统共同提供的能力（例如 symbol、definition、reference、call）；**Full System Comparison** 则说明各系统完整保存的图事实、证据层和协作能力。DB Size、构图时间或查询时间不能脱离 capability scope 裸比。

| 比较方向 | 最小同机对照 |
|---|---|
| C/C++ 图构建 | ProvenLattice / Joern / CodeGraphContext（Tree-sitter 或 SCIP） |
| 基础导航 | ripgrep / SCIP / ProvenLattice 图查询 |
| 检索与证据 | 文本检索（如 BM25）/ CodeGraph / CodeGraph + Knowledge |
| Agent 任务 | Native Agent / 文本检索 Agent / ProvenLattice CodeGraph / ProvenLattice Knowledge |

## 8. 当前证据盘点

| 领域 | 已有冻结证据 | 当前缺口 |
|---|---|---|
| 图基础层 | V0.2 真实 C/C++ 解析与图基线；V0.3 增量 parity；V0.4 Overlay parity；V1.0 Knowledge parity | 边类型级 Precision/Recall/F1，更多语言与工程结构 |
| 图系统与规模 | aria2、brpc、RocksDB 三档构图、存储、内存、查询；Overlay 比例与开销 | 百万/千万 LOC、更新 P50/P95、查询 P99、并发与多分支压力 |
| 检索与证据 | R2.4 Offline Bundle Qualification；R2.3 干扰项与引用归因 | 多粒度定位指标、文本检索对照、Session Evidence Aggregation |
| Agent 集成 | R1–R2.3 的能力隔离、评估契约和受控对照 | 统一 adoption 指标、跨仓/跨模型复验、修复类任务 |
| 评估治理 | R2.2 GroundTruthV2 与 51 cell 确定性重放 | 更大任务集、公开 benchmark 映射、长期 evaluator 版本治理 |

## 9. 执行顺序与近期交付物

后续工作不应仅按 `R2.x` 编号驱动；每个新实验先声明它服务的 RQ、Track、冻结输入、成功门槛和失败归因方式。严格沿着 Representation → Systems → Retrieval → Agent 推进：如果图关系本身错误，后续检索或 Agent 失败无法被正确解释。

| 阶段 | 交付物 | 决策门槛 |
|---|---|---|
| Phase 0：Framework Freeze | 本文档、指标词典、结果 schema、失败归因 schema | 后续实验必须能映射到 RQ、Track 和版本化 Benchmark Asset |
| Phase 1：Evidence Inventory | V0–R2.4 的实验—RQ—Track 证据清单 | 明确哪些是实测、哪些是缺口、哪些只属外部参照 |
| Phase 2：Graph Fidelity | Gold Set、边类型 Precision/Recall/F1、选择性解析指标 | 未完成 L1 前，不对 Retrieval/Agent 失败作图服务优劣结论 |
| Phase 3：Graph Systems / Scale | 当前实现的冻结 Scale Baseline、瓶颈归因、优化后同协议复测 | 先得到 Before，再优化，再以同协议获得 After；不先优化后测 |
| Phase 4：Retrieval / Evidence | 多粒度 Retrieval Benchmark、文本检索对照、Session Evidence 指标 | 证明服务独立质量后，才进入端到端 Agent 比较 |
| Phase 5：Agent Adoption / Effectiveness | 多轮 Agent 对照、采用率、归因链、最终任务指标 | 区分服务不足、Agent 未采用和任务推理失败 |
| Phase 6：Generalization / External Baseline | 跨仓、跨模型与同机外部工具复现 | 仅在受控复现后发布横向强结论 |

## 10. 实验统计与 Benchmark Governance

系统 Benchmark 与 Agent Experiment 采用不同统计协议，不能混用。

| 实验类型 | 最低运行规范 | 报告规范 |
|---|---|---|
| 确定性系统 Benchmark（构图、更新、查询） | 明确 cold/warm cache；warm-up 后至少 5 次重复；冻结 CPU、RAM、OS、文件系统、runtime、数据库版本、线程数与缓存状态 | median、P95、min、max；并保留每次原始测量 |
| 早期 Agent Qualification | 可 `n = 1`，仅用于接口、产物和协议 gate | 不作稳定性、显著性或泛化结论 |
| Agent Stability / Effectiveness | 每个 cell 至少 `n ≥ 3`；随机化或轮换 arm order；固定模型、提示和工具策略 | task-level paired comparison、median、min/max；样本量足够时报告 effect size 与置信区间 |

小样本不能宣称统计显著。模型版本、Agent 版本、环境、网络/Sandbox 状态和无效运行都必须记录；`INFRASTRUCTURE_FAILURE` 运行不得混入能力指标。

每个 Benchmark Asset 使用以下最小元数据，防止 Ground Truth、Evaluator 或 schema 更新污染历史结论：

```text
benchmark_id
version
repository
commit
task_version
oracle_version
evaluator_version
schema_version
created_at
supersedes
sha256
```

同时维护 task leakage audit、Ground Truth change history 和 evaluator change history。Ground Truth、Acceptable Alternatives、Distractors 与 Evaluator Contract 必须在查看目标实验 Arm 结果前冻结；Agent 成绩不得反向修改这些评价资产。若出现 GroundTruthV3 或 evaluator 更新，旧数据保持原样；新版本以新的 benchmark/evaluator version 运行，并可进行 offline replay，而不回写既有结果。

每一项结论还必须随结果报告以下 Claim Scope，防止将受限资格验证写成项目级能力：

```text
claim
evidence_level
scope
  language
  repository / commit
  task or mutation family
  build context
  protocol version
```

## 11. 版本与文档治理

- **版本报告**记录某一版本已经实现和实际测得的结果，例如 V0.2、V0.4、V1.0-R2.4。
- **本 Framework**定义长期问题、层次、指标、对照与归因，不用未来目标伪装成当前能力。
- **Benchmark Protocol**为每个 Track 固定输入、环境、运行步骤、结果 schema 和 acceptance criteria。
- **Result Report**只回答协议中预先冻结的问题，并将所有失败归入第 5 节的分类之一或明确标为未归因。

如此，ProvenLattice 的核心主张可以被严格表述为：

> ProvenLattice 是一套面向 Code Agent 的、可增量维护且带 provenance 的工程证据基础设施；其价值通过图保真度、图系统规模、证据检索质量、Agent 采用与最终工程任务效果的独立且串联验证来建立。

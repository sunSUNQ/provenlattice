# ProvenLattice Evidence Inventory & Gap Matrix V1

> V0–R2.4 现有实验成果的总账：它们回答了哪些 Research Question、证据强度到什么程度、还缺什么，以及下一条实验线的优先级。

**状态：Evidence Inventory V1 — READY FOR FREEZE**
**Framework 依据：**[ProvenLattice Research & Validation Framework V1](provenlattice-research-validation-framework-v1.md)
**数据原则：**本文件只盘点既有冻结报告、可复现产物和明确标注的观察性结果；不把未来计划或不同协议的外部数字写成当前能力。

## 1. 使用方式

这不是新的 benchmark 结果，而是研究治理文档。每项新实验开始前，应更新对应行的“已有证据”“缺口”和“下一实验”；完成后，只能提升相应 RQ 的证据等级，不能借由其他 RQ 的结果连带提升。

```text
版本 / 实验
      ↓
RQ1–RQ8 + Track A–F
      ↓
证据等级
      ↓
明确缺口
      ↓
P0 / P1 / P2 backlog
```

## 2. 证据等级定义

| 等级 | 定义 | 可以作出的结论 | 不可作出的结论 |
|---|---|---|---|
| `NONE` | 没有可审计实验或产物 | 尚无证据 | 任何能力或趋势 |
| `OBSERVED` | 有测试、单次运行、smoke test 或工程观察 | 现象出现过，值得进一步验证 | 稳定性、因果性或泛化 |
| `PARTIAL` | 在受控范围内有真实仓/冻结协议证据，但维度或样本不完整 | 该受限条件下存在初步支持 | 全边类型、全规模、跨仓/跨模型结论 |
| `QUALIFIED` | 协议、输入、门槛和产物冻结，且资格 gate 通过 | 被限定的能力已经通过资格验证 | 跨环境或跨任务泛化 |
| `REPLICATED` | 在相同协议下跨重复、第二个任务/仓库/条件复现 | 结论在已复现条件下稳定 | 广泛泛化 |
| `GENERALIZED` | 跨仓库、任务、语言或模型的受控重复支持同一结论 | 在已覆盖总体中具有泛化支持 | 未覆盖总体的绝对结论 |

证据等级针对**具体 RQ 和明确范围**，不是项目的总分。例如 V0.4 的 Overlay parity 可以是 `QUALIFIED`，并不使 RQ2（千万行 Scale）达到 `QUALIFIED`。

## 3. 版本与实验资产清单

| 资产 | 主要内容 | 映射 RQ / Track | 当前盘点定位 |
|---|---|---|---|
| V0.1 Core Foundation | RawReference、`resolved/ambiguous/unresolved`、仅 resolved 形成 Edge、provenance | RQ1 / A | Resolver 保守性与图事实模型的基础证据 |
| V0.2 C/C++ Baseline | aria2、brpc、RocksDB 的真实仓构图、存储、内存和关系查询 | RQ1、RQ2 / A、B | 三档真实 C/C++ 工程基线 |
| V0.3 Shard Qualification | Shard strategy、API fingerprint、Boundary reverse index、M1–M5、incremental parity | RQ1、RQ8 / A、B | 局部更新与影响范围基础 |
| V0.4 Overlay | Branch/Session Overlay、冲突、rebase、Delta 大小与查询开销 | RQ8、RQ2 / A、B | 多分支/多会话图维护基础 |
| V1.0 Knowledge | Knowledge Nodes、Evidence Links、Cross-layer Edges、知识增量与 parity | RQ1、RQ3、RQ4 / A、C、D | 跨层证据表达基础 |
| R1 Retrieval Qualification | Native/CodeGraph/Knowledge 隔离、54 run 审计与指标采集 | RQ5、RQ6 / E、F | 受控 Agent 实验基础；旧 evaluator 结论受限 |
| R2 / R2.1 Interface & Closure | T05 接口、bundle 暴露、citation/evaluator 问题归因 | RQ3、RQ4、RQ5、RQ6 / C–F | Graph Service 与 Agent 边界的定位证据 |
| R2.2 Evaluation Contract | GroundTruthV2、51 cell 确定性重放、false negative 归因 | RQ5、RQ6 / E、F | 测量有效性资格验证，不是产品效果结论 |
| R2.3 Agent Revalidation | 3 任务 × 3 条件 × 3 次重复、27/27 VALID | RQ4、RQ5、RQ6 / D、E、F | 任务受限的 Agent 效用证据 |
| R2.4 Offline Bundle | T01/T03/T05 bundle 裁剪、Loose 策略资格验证 | RQ3、RQ4 / C、D | 单查询证据选择质量 |
| R2.4-DS Phase A / transport smoke | DeepSeek 传输与阶段性 Agent 产物 | RQ5、RQ7 / E | `OBSERVED`；尚不是稳定或跨模型效果结论 |

## 4. RQ / Track 总账

| RQ / Track | 已有证据 | 当前等级 | 现阶段可陈述的结论 | 明确缺口 | 下一实验 | 优先级 |
|---|---|---|---|---|---|---|
| **RQ1 图保真度 / A** | V0.1 Resolver contract；V0.2 三个真实 C/C++ 仓 Hard Parse Coverage=100%，Syntax-clean Rate=66.78%/73.89%/83.22%，并保留 recovery error；V0.3/V0.4/V1.0 parity | `PARTIAL` | 目标文件均可产出解析结果；语法恢复状态与硬解析失败独立报告；保守解析和 parity 已在定义范围内成立 | 无正/负例 Gold Set；缺 CALL/IMPORT/REFERENCE/跨层关系 P/R/F1、False Resolution Rate、选择性风险及 Build Context | Graph Fidelity Gold Set Protocol + Build Context metadata | **P0** |
| **RQ2 可扩展性 / B** | aria2、brpc、RocksDB（11.9 万/22.7 万/62.3 万 LOC）的构图、DB、内存、查询；V0.4 Overlay 成本 | `PARTIAL` | 62.3 万 LOC C/C++ 已实测跑通；可观察 RawReference、存储和 Symbol Query 压力 | 无 S3/S4/S5（1M/5M/10M+ band）；无并发 QPS、TTF、稳定 P95/P99 更新、图规模归一化 | Current Implementation Scale Baseline（先不优化） | **P0** |
| **RQ3 检索质量 / C** | Symbol/Caller/Callee/Subgraph 查询基线；R2/R2.1 接口观察；R2.4 Offline bundle | `PARTIAL` | 冻结任务上可离线验证 required evidence retention 与 bundle 策略 | 无 Graph Oracle Coverage / Conditional Recall；无 File/Function/Line Recall@k、MRR、NDCG、文本检索（BM25）对照；任务族不足 | Retrieval Benchmark Suite | **P0** |
| **RQ4 证据效率 / D** | V1.0 跨层证据；R2.3 bundle 干扰与 returned-unused；R2.4 Loose 在 T01/T03/T05 保留全部必需证据 | `QUALIFIED`（仅 R2.4 三任务、单查询） | 在该冻结候选集与协议下，Loose 是唯一三任务均保留 required evidence 的策略 | 无多查询 Session Exposure、预算曲线、饱和点、重复暴露或 Marginal Evidence Utility | Session Evidence Metrics + Aggregation benchmark | **P1** |
| **RQ5 Agent 采用 / E** | R1 的能力隔离和调用记录；R2/R2.1 接口归因；R2.3 27/27 valid；R2.4-DS Phase A 产物 | `PARTIAL` | Agent 使用图服务与引用契约可以被观测；“工具可用 ≠ Agent 正确采用”已被实验证明是实际问题 | 缺统一 Adoption/FCTC/首相关证据/饱和后查询 telemetry；DS 尚未稳定复验 | Agent telemetry replay / schema upgrade | **P1** |
| **RQ6 最终任务效果 / F** | R1 受 evaluator 限制的 54 runs；R2.2 修正测量；R2.3 三任务对照与 task-scoped positive candidate | `PARTIAL` | 对少量受控工程理解任务已有可审计证据；Knowledge 在特定任务有正向候选信号，并非普适提升 | 任务族过少；缺 bug 定位、变更规划、修复；缺公共 benchmark 与稳定复现 | Expanded Task Benchmark | **P1** |
| **RQ7 泛化性 / A–F** | 多仓 C/C++ 构图；Claude 系列受控实验；DeepSeek transport/Phase A 观察 | `OBSERVED` | 已有跨仓构图和第二模型的初步工程资产 | 缺相同协议下的跨仓、跨模型、跨语言任务矩阵；无同机外部 baseline | Generalization Matrix | **P2** |
| **RQ8 增量工程 / A、B** | V0.3 M1–M5 与 B2/B3 单文件 parity；V0.4 Branch/Session、冲突、兼容 rebase | `QUALIFIED`（受限 Mutation/Overlay contract） | 单文件局部修改、Boundary 变化、Overlay 物化与冲突识别已经资格验证 | Mutation 类型不足；无 rename/move/header/high fan-out、多文件、并发与 Time-to-Freshness 分布 | Incremental Mutation Suite | **P0 / P1** |

### 4.1 现有结论的 Scope Ledger

每项等级只能在下列 scope 内理解；该 scope 随每次新结果一同发布。

| RQ | 当前 Claim Scope |
|---|---|
| RQ1 | C/C++；aria2、brpc、RocksDB；V0.1–V1.0 的 Resolver / parity 协议；无 compiler-aware build context 资格结论 |
| RQ2 | Windows 11、冻结 benchmark commit、单机；11.9 万–62.3 万 C/C++ LOC；V0.2/V0.4 协议；不含并发与 S3+ Scale band |
| RQ3 | 当前 Query API 与 T01/T03/T05 任务证据；R2–R2.4 协议；非文件/函数/行级通用 retrieval claim |
| RQ4 | R2.4 冻结候选池、T01/T03/T05、单查询、Loose 策略；不含会话级聚合 |
| RQ5 | R1–R2.3 的 Claude 受控 cell 与 R2.4-DS Phase A 观察；不含跨模型稳定性结论 |
| RQ6 | brpc 受控理解/证据任务；不含缺陷修复、测试通过或公开 benchmark 结论 |
| RQ7 | 多仓 C/C++ 构图与有限第二模型产物；不含共享协议下的模型/语言泛化 |
| RQ8 | V0.3 M1–M5、B2/B3 单文件 mutation，V0.4 Branch/Session/Conflict/Rebase；不含 rename/move/header/high fan-out 与多文件并发 |

### 4.2 当前状态摘要

```text
已形成受限资格验证：
  - V0.3/V0.4/V1.0 的 parity 与 Overlay contract
  - R2.4 三任务单查询 bundle 策略

已有真实仓基础但仍属 Partial：
  - C/C++ 图构建与规模
  - 图保真度
  - Retrieval
  - Agent Adoption / End-task Effectiveness

仅有观察性跨条件线索：
  - 跨模型、跨语言和跨仓 Agent 泛化
```

因此，当前最高优先级不是扩大 Agent 任务数量，而是先补齐 RQ1、RQ2、RQ3 的下层证据：**图是否正确、能否规模化运行、图服务是否独立有效。**

## 5. P0 / P1 / P2 实验 Backlog

| 优先级 | 实验线 | 服务 RQ / Track | 最小交付物 | 完成门槛 |
|---|---|---|---|---|
| **P0** | Fidelity Gold Set | RQ1 / A | 分层样本、双人标注协议、冻结 Gold Set、边类型 P/R/F1、Resolution Precision/Coverage/Abstention/Selective Risk | 至少覆盖 CALL、REFERENCE、IMPORT、DEFINE、CONTAIN、DOC→CODE 与难例分层；所有标注和争议可追溯 |
| **P0** | Current Scale Baseline | RQ2 / B | 在当前实现上执行 100K→500K→1M→5M→10M+ 分档协议；Cold Build、单查询、并发查询、磁盘/内存/TTF | 先输出 Before baseline 与瓶颈归因；不得先优化后首次测量 |
| **P0** | Retrieval Benchmark Suite | RQ3 / C | 任务族、Graph/Retrieval Oracle、文本检索基线、File/Function/Line 指标 | 冻结任务、替代答案与干扰项；可复现比较文本/图/图+知识 |
| **P0/P1** | Incremental Mutation Suite | RQ8 / A、B | 固定 Mutation Family、parity runner、影响范围和 TTF 报告 | 覆盖 body/signature/add/delete/rename/move/cross-module/header/overlay/rebase |
| **P1** | Session Evidence Benchmark | RQ4 / D | Session Unique/Repeated Evidence、Saturation、Post-saturation Query、预算曲线 | 证明 Loose 的单查询优势在多轮会话中是否保留 |
| **P1** | Agent Telemetry Replay | RQ5 / E | 统一事件 schema、Adoption、FCTC、Used/Returned、Citation 指标、primary/contributing failure | 可将每个失败定位到 Source→Graph→Service→Agent→Evaluator 链路 |
| **P1** | Expanded Agent Tasks | RQ6 / F | 理解、定位、影响分析、变更规划等任务族与重复策略 | 每个 cell 至少 3 次稳定性运行；不以小样本宣称显著 |
| **P2** | Generalization Matrix | RQ7 / A–F | 第二仓、第二模型、后续第二语言；共享协议的重复实验 | 同一核心结论在至少两个受控条件下复现 |
| **P2** | External Same-machine Baselines | RQ2、RQ3、RQ6 / B、C、F | 固定仓库/commit/硬件下的工具对照 | 仅用统一 schema 发布横向结论 |

## 6. 现有 Agent 线的处置

当前 Framework 下，R2.4 的定位应冻结为：

```text
R2.4 Offline
= Evidence Quality evidence

R2.4-DS Phase A
= Agent Adoption / Session Exposure evidence（观察性）

R2.4 Stability
= DEFERRED
```

`DEFERRED` 不是失败或取消，而是顺序调整：在 Graph Fidelity、Scale 和 Retrieval 的解释力不足前，继续扩展 Agent Stability 无法可靠区分图、服务、Agent 或 evaluator 的责任。待 P0 证据完善后，R2.4 的 Loose 策略应以完整 Session telemetry 和失败归因链重新进入 Agent 验证。

## 7. Framework 冻结清单

Framework V1 在正式冻结时应生成一个不可变发布记录，至少包含：

```text
framework_version: V1
git_commit: <commit at freeze>
sha256: <artifact hash at freeze>
freeze_date: <ISO-8601 date>
```

冻结对象包括：

- RQ1–RQ8 与 Track A–F 的定义；
- Evidence Level 词典；
- Failure Taxonomy、`primary_failure`、`contributing_failures[]`、`first_broken_stage` 的语义；
- Benchmark Metadata 最小 schema；
- 当前实现的 Scale Baseline 协议。

冻结后，新增能力或指标采用版本化扩展；不得因某轮实验失败或成功而改写旧术语、历史 Ground Truth、Evaluator 或既有结果。

## 8. 当前主线

```text
Evidence Inventory
      ↓
Graph Fidelity
      ↓
Systems / Scale
      ↓
Retrieval
      ↓
Agent
      ↓
Generalization
```

这条主线将 ProvenLattice 的研究对象明确为：先证明工程证据图的表示可信，再证明系统可运行、检索可用、Agent 可采用，最后才讨论端到端收益与泛化。每一阶段的输出都成为下一阶段可追溯的输入。

## 9. 盘点来源

- [V0.2 C/C++ baseline](benchmarks/provenlattice-v0.2-baseline.md)
- [V0.3 Shard qualification](benchmarks/provenlattice-v0.3-shard.md)
- [V0.4 Branch & Session Overlay](benchmarks/provenlattice-v0.4-overlay.md)
- [V1.0 Knowledge baseline](benchmarks/provenlattice-v1.0-knowledge.md)
- [V1.0-R1 Retrieval qualification](benchmarks/provenlattice-v1.0-r1-retrieval.md)
- [V1.0-R2 T05 interface qualification](benchmarks/provenlattice-v1.0-r2-t05.md)
- [V1.0-R2.1 Experiment closure](benchmarks/provenlattice-v1.0-r2.1.md)
- [V1.0-R2.2 Evaluation contract qualification](benchmarks/provenlattice-v1.0-r2.2-evaluator.md)
- [V1.0-R2.3 Agent revalidation](benchmarks/provenlattice-v1.0-r2.3.md)
- [V1.0-R2.4 Offline bundle qualification](../experiments/retrieval-v2/r2_4/results/qualification-r2.4.md)
- [V0 design](design-v0.md) and [V1 design](design-v1.md)

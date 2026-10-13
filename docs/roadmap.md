# ProvenLattice Standalone Roadmap

## Product boundary

ProvenLattice 是面向 Code Agent 的独立工程证据基础设施，不是 TASCO 的上下文压缩组件。两个项目分别维护版本、接口、数据模型和实验结论；在两者各自成熟前，不安排组合实验，也不让 ProvenLattice 的研发依赖 TASCO。

ProvenLattice 的核心问题是：代码在哪里、谁依赖谁、为什么这样设计、哪个需求对应哪段代码、谁修改过它、哪个版本包含它、以及运行时错误可能指向哪里。

## Gold Target V2（长期产品化目标，canonical planning entry）

> 定位：本节是 ProvenLattice 长期产品化目标的**权威规划入口**（V2，2026-10-12
> 冻结；V1 版（2026-10-10，单能力域定位）由本版取代，变化摘要见 G0）。
> 设计原则同步于 [docs/design-optional-analysis-layer-vision.md](design-optional-analysis-layer-vision.md)；
> main 与 PR #1 两条开发线的实现差异审计、能力映射、语义差异矩阵、三臂对照
> 实验设计与渐进整合路线见
> [docs/design-dual-capability-integration.md](design-dual-capability-integration.md)。
> 注意：vision 文档 §3 的 L0–L4 是分析能力阶梯的**历史命名**，与本节 L1–L5
> pipeline 分层编号不同（映射见其文档头注记）。
> 本节是**规划与架构原则**，不是当前实现状态声明（对照见 G7）。

### G0. V1 → V2 主要变化（摘要）

| 项 | V1（2026-10-10） | V2（2026-10-12） |
| --- | --- | --- |
| 产品定位 | 面向 Code Agent 的工程证据基础设施 | **统一程序知识和语义分析平台**：Agent Development（默认核心）+ Code Inspection（可选高级）双能力域 |
| L2 | Optional Analysis（Agent 侧可选分析） | **Unified Optional Analysis**：双能力域共享的可插拔分析引擎（Normalized IR / Canonical CFG、Full/Sparse CFG 视图、Semantic Events、DFG、Alias/Ownership、Taint、Defect/Security Analyzers） |
| L3 | Task Context | **Task Services / Orchestration**：Agent Development 与 Code Inspection 两类任务服务共用编排（能力选择、scope 规划、结果组装）；分析算法仍归 L2 |
| 架构形状 | Always-on foundation + on-demand capabilities + task-scoped context | **Shared Foundation + Unified Analysis Engine + Dual Task Domains**（V1 形状作为其子集保留） |
| 新增输入 | — | PR #1（缺陷导向稀疏语义程序图，未合并）纳入统一架构：能力映射与语义差异见 design-dual-capability-integration.md §4/§5 |
| Profiles | basic / development / deep / security（概念） | 同名四档保留；`security` 明确对应 Code Inspection 能力域（仍未实现，见 G5） |
| 不变 | L1 默认开启、Capability × Scope 双维按需、不规划 L6、Layer ≠ Maturity Level | 全部保留并强化 |

### G1. 核心目标

ProvenLattice V2 的长期定位是：

> **一个面向 AI Agent 与代码检测的统一程序知识和语义分析平台。**

系统以轻量、确定性、可增量的代码知识图谱为基础，支持两大能力域：

**能力域 A：Agent Development（日常开发辅助，默认核心）**

1. 代码理解、符号和引用查询；
2. 函数定位、调用关系、依赖关系和影响分析；
3. Agent 编码、Bug 定位、代码修改和重构辅助；
4. 需求与代码、文档和工程知识关联；
5. 面向任务的相关上下文生成；
6. 在需要时使用 AST、CFG、Data Flow 等更深层分析事实；
7. 修改后的验证结果与证据引用。

要求：基础代码图谱默认开启；默认建图尽可能低成本；**不因引入代码检测能力
而明显增加普通用户的资源消耗**；高级分析按任务、范围和能力按需触发。

**能力域 B：Code Inspection（深度代码检测，可选高级）**

1. 资源生命周期与内存管理缺陷候选检测；
2. 空指针、Use-After-Free、Double Free 等缺陷分析；
3. 锁、并发、竞态相关分析；
4. Def-use、Data Flow、Alias、Ownership 等程序语义分析；
5. 污点传播与安全分析；
6. Typed Defect Query；
7. Evidence Bundle、Missing Evidence 和缺陷候选复核；
8. 后续扩展的静态分析与安全检测规则。

要求：默认不启用高成本检测；支持按项目、文件、函数和缺陷类别选择；高级分析
结果可被 Agent Development 复用；严格区分 **Candidate / Uncertain / Verified
Finding**；不将不确定的推断自动提升为已确认事实；所有缺陷结论必须携带来源、
证据、缺失证据和可信性状态。

两大能力域**共享底层事实、分析引擎和证据体系**，不能发展成两套彼此独立的
CodeGraph。

核心原则（保留自 V1）：

```text
L1 = 默认开启（默认基础服务）
L2+ = 按需增强
```

准确解释（防止误读）：

- 不是把 L2–L5 作为一个整体开关；
- 每层内部能力**独立启用**；
- 高成本能力同时受 **capability** 与 **scope** 两个维度控制（见 G3）。

### G2. 五层运行模型

| 层 | 运行模型 | 内容与要求 |
| --- | --- | --- |
| **L1 Foundation / Knowledge** | **默认开启，Always-on** | Repository/File/Symbol、Definition/Reference/Call、Dependency/Impact、Knowledge/Requirement/Document、基础 provenance。即使不启用任何高级分析，ProvenLattice 仍是可用的基础代码/工程知识服务（symbol / definition / callers / callees / references / related code / impact / knowledge）。必须保持：stable、deterministic、相对低成本、可增量维护、适合默认部署。**两大能力域共享同一份基础事实，不因检测能力重复建图。** |
| **L2 Unified Optional Analysis** | **按需；Analyzer Capability Registry（非单开关）** | 双能力域共享的统一可插拔分析引擎。规划支持：Normalized AST/IR、Canonical CFG、**Full CFG View 与 Sparse CFG View 双视图**、Semantic Events、Def-use / Data Flow、Alias / Points-to、Ownership / Resource Semantics、Taint Analysis、Defect / Security Analyzers。已有 analyzer（main）：Python AST、Python CFG、C AST、C CFG、C 短路 CFG、C 调用语义；PR #1 分支已有（未集成）：Semantic Events、Sparse CFG/DFG、Ownership Contracts、8 类 Typed Defect Query（整合状态见 G7 与 design-dual-capability-integration.md）。必须清楚标记**已实现 / 部分实现 / 未来目标**及 formal / diagnostic 证据等级。**新增 analyzer 不新增 architecture layer。**Full 与 Sparse 是同一控制流语义的不同用途**视图**，不设计为两套长期独立的事实来源；语言专属语义由独立 frontend / 语言适配器承载；不强制每次生成 Sparse CFG 先完整持久化 Full CFG。 |
| **L3 Task Services / Orchestration** | **request-time / task-time；统一编排、双业务入口** | 由 Task Context 扩展为统一任务服务层，内含 **Agent Development Task Services**（task-context 事实包）与 **Code Inspection Task Services**（defect 查询入口、候选复核组织）。负责分析能力选择、执行范围规划、分析结果组合、任务上下文生成和检测结果组织。**实际分析算法仍归 L2。**检测入口默认不隐式触发高成本分析；普通 task-context 不无限制触发昂贵 analyzer。 |
| **L4 Evidence / Results** | **Core Provenance = baseline；Advanced Evidence = optional；统一证据契约** | 统一管理代码分析证据和结果表示：基础代码证据、分析路径、Evidence Bundle、Missing Evidence、**Candidate Finding 与 Verified Finding 区分**、Agent 任务引用与验证证据。统一契约要素：stable identity、source span、provenance、resolved/ambiguous/unresolved、analyzer version、freshness/staleness、missing evidence、truncation/coverage。Core provenance 默认保留、不关闭；Advanced evidence（Agent trace normalization-v2、runtime/validation evidence、formal experiment telemetry）可选。**不把 Finding 直接变成新的架构层**（见 G4 Finding 特别说明）。 |
| **L5 Exposure** | **Adapter 层；CLI = baseline** | 至少保留一个基础访问面（CLI 已实现），长期统一提供 Agent Query 与 Code Inspection 的访问能力。已有：CLI（baseline）、native MCP（可按配置启用）；Plugin / SDK 尚未实现；REST/API 为候选。**Plugin、SDK、REST 等属未来扩展，不因新能力域而额外增加一层。**"L5 optional" ≠ 系统可以没有任何访问入口。 |

### G3. 双重按需原则（Capability × Scope）

高级能力成本控制必须同时具备：

```text
Capability selection  ×  Scope selection
（selected analyzer）     （selected function / file / module / task scope）
```

而不是 `enable CFG → 为整个仓库构建 CFG`。目标成本模型：

```text
Total Cost ≈ Foundation Cost + Σ( Selected Capability × Selected Scope )
```

> **whole-repository deep analysis 不应成为默认行为。**

能力的选择、依赖、语言支持、分析成本、构建状态、缓存与失效由
**Analyzer Capability Registry** 统一管理（PR #1 的检测能力与 main 的
AST/CFG analyzers 在 Registry 中同层注册，只是成本与默认开关不同；
Registry 本身尚未实现，见 G7）。

### G4. Layer ≠ Maturity Level（不规划 L6）

五层表示**数据生命周期 / pipeline stages**（repository state → derived
analysis → task selection → provenance governance → consumption interface），
不是功能复杂度等级：

```text
AST → CFG → Def-use → Points-to → Taint   能力递进，仍全部属于 L2 Analysis
CLI → MCP → Plugin → SDK                  形态递进，仍全部属于 L5 Exposure
```

**L6 判定标准**（未来必须同时满足，才考虑新增层）：

1. 出现现有五层无法自然容纳的新数据处理阶段；
2. 有独立输入/输出；
3. 有独立持久状态；
4. 有独立生命周期；
5. 有自己的失效/更新规则；
6. 有独立消费契约；
7. 已有真实需求证据证明需要该阶段。

仅新增 analyzer、新数据类型、新 CLI、新索引、新安全规则，均不足以建立 L6。

**Finding 特别说明**：Security/Detection Finding 当前表示为
`L2 analysis artifact → L4 evidence → L3 task context`，**不创建 Finding
Layer**。所有 Finding 必须显式携带 **Candidate / Uncertain / Verified**
可信性状态与来源、证据、缺失证据；不确定的推断**不得自动升级为已确认
事实**；检测结论（人工/工具判定）不得与事实状态混淆。只有当 Finding
未来成为真正一等长期对象并拥有独立生命周期
（identity / deduplication / suppression / severity / triage / ownership /
validation / remediation state / regression tracking）时，才重新评估是否
需要新阶段。**当前：NO L6 PLANNED。**

### G5. Capability Profiles（future productization candidate，未实现）

> 明确：这是**规划**，不是当前已实现功能。不实现任何 profile 代码。
> 这些是长期产品组合目标，不得把尚未实现的 Profile 写成正式功能。

未来产品化候选：`Unified Capability / Profile Configuration`，概念映射：

| Profile | 能力组合 | 服务域 |
| --- | --- | --- |
| basic | L1 基础代码图谱与日常查询 | 默认（双域共用） |
| development | basic + 按需 AST/CFG + Agent task-context | Agent Development |
| deep（未来） | basic + 选定的深度数据流分析（AST + CFG + def-use 等，按 scope） | Agent Development（高级） |
| security（未来） | basic + Semantic Events + Sparse CFG/DFG + Defect Queries（按项目/文件/函数/缺陷类别选择） | Code Inspection |

> profiles 是能力组合的 UX shortcut，**不改变五层架构**；高级用户未来仍应
> 能够单独选择 capability。

### G6. 推荐架构图

```text
             ProvenLattice Gold Target V2
        （Shared Foundation + Unified Analysis Engine
                + Dual Task Domains）

   ┌───────────────────────────────────────────────────────┐
   │ L5 Exposure：CLI（baseline）· MCP · future Plugin/SDK  │
   │        Agent Query 入口   |   Inspection 入口          │
   └───────────────────────────┬───────────────────────────┘
                               │
   ┌───────────────────────────┴───────────────────────────┐
   │ L3 Task Services / Orchestration（统一编排，算法归 L2） │
   │  Agent Development TS      |      Code Inspection TS   │
   │  task-context 事实包        |      defect 查询/复核组织 │
   └───────────────────────────┬───────────────────────────┘
                               │
   ┌───────────────────────────┴───────────────────────────┐
   │ L2 Unified Optional Analysis（按需，Capability × Scope）│
   │        Analyzer Capability Registry                    │
   │  Normalized IR · Canonical CFG · Full/Sparse CFG Views │
   │  Semantic Events · Def-use/DFG · Alias/Ownership       │
   │  Taint · Defect/Security Analyzers                     │
   └───────────────────────────┬───────────────────────────┘
                               │
   ┌───────────────────────────┴───────────────────────────┐
   │ L4 Evidence / Results（统一证据契约）                   │
   │  identity · span · provenance · 三态 · missing evidence│
   │  truncation/coverage · Candidate ≠ Verified Finding    │
   └───────────────────────────┬───────────────────────────┘
                               │
   ┌───────────────────────────┴───────────────────────────┐
   │ L1 Foundation / Knowledge（默认，Always-on，低成本）    │
   │  graph + knowledge + core provenance（双域共享唯一事实）│
   └───────────────────────────────────────────────────────┘
```

> 逐层实现状态见 G7；PR #1 能力映射、语义差异矩阵与整合路线见
> [docs/design-dual-capability-integration.md](design-dual-capability-integration.md)。

### G7. 当前实现 vs Gold Target V2

**Already implemented（main 已集成）**：

- L1 Foundation Graph 默认基础能力
- optional AST / CFG materialization（Python AST/CFG；C normalized AST + 函数内
  CFG + 短路 + 调用语义分类）
- scoped analysis（`analyze --scope`）
- analysis cache / freshness
- Python / C analyzer dispatch
- task-context request-time 入口
- core provenance
- normalization-v2
- CLI
- native MCP

**Partially implemented**：

- 整体 optional capability model 已存在，但尚未形成统一配置模型
- L3 已按调用使用，但尚无完整 profile-driven policy
- Analyzer Capability Registry 仅有雏形（`ANALYZER_VERSIONS` 注册表 +
  feature/scope 校验），尚无依赖/成本/语言覆盖的统一管理面

**Available on PR #1 branch（未集成 main，整合状态见
[design-dual-capability-integration.md](design-dual-capability-integration.md) §9）**：

- Semantic Events（15 类，词汇表驱动）+ Sparse CFG / Sparse DFG
- Ownership Contracts + 8 类 Typed Defect Query（`defect` CLI 入口）+
  Evidence Bundle / Missing Evidence
- cold/hot 存储分离（`codegraph.cold.db`）与流式 update、缺陷查询性能优化
- 语言边界：CFG/DFG 仅 C/C++ 语料验证；输出全部为 Candidate（PR 自报
  stage-6 precision 基线 1/32，stage-9 后部分收敛，逐条归因在案）

**Not implemented（统一架构目标，当前无实现）**：

- 统一 Normalized Program IR / Canonical Control-Flow Model（Full/Sparse
  双视图收敛）
- Analyzer Capability Registry 完整版（依赖/成本/语言/失效统一管理）
- unified capability config / profile system / automatic capability planning
- def-use / points-to / taint / Clang（main 侧均未启动；PR 分支的 taint_path
  属检测链组成部分，随 PR 整合决策走）
- Plugin / SDK
- distributed / cross-repo infrastructure
- Code Inspection 的正式 qualification（三臂实验未执行，见
  design-dual-capability-integration.md §8）

> Gold Target 是方向声明，**不等于当前已全部实现**；实现状态以 §1–§2 的
> 冻结证据、§3 的 pending 项与 PR #1 整合决策为准。PR #1 的任何能力在
> 合并并取得对应证据之前，一律不得在对外文档中表述为已交付能力。

## Version line（2026-10-10 reconciliation）

| 分区 | 内容 | 状态 |
| --- | --- | --- |
| Gold Target | 长期产品化目标（canonical planning entry，V2 双能力域） | 见下节 |
| Dual-capability integration | main × PR #1 统一架构（审计/能力映射/语义差异/三臂实验/整合路线） | 规划冻结（2026-10-12）；Phase 1 未启动；见 design-dual-capability-integration.md |
| Qualified releases | 正式资格与发布（有冻结 artifact） | 见 §1 |
| Post-V1.2 implemented development | 已集成 main 的开发态能力 | 见 §2 |
| Pending validation | 进行中 / 待收敛的验证 | 见 §3 |
| Future capability candidates | 候选能力（未排期、不承诺） | 见 §4 |

> 旧版 roadmap 中的 V1.0-R1 "Next" 与 V1.1/V1.2/V1.3/V1.4/V2.0 "Planned" 路线
> 已失效删除：实际演进路径为 RQ1/RQ2 → SQI-V1/V1.1/V1.2 → Analysis Layer →
> Context Bundle/MCP → C10 → zstd 16-case → C 分析链（见 §1–§2）。

## 1. Qualified releases（正式资格）

| 里程碑 | 范围 | 结论 |
| --- | --- | --- |
| Core V0.3 / Core V0.4 | Shard / Incremental；Branch / Session Overlay（工程级 parity） | Complete |
| V1.0 | Knowledge Layer / Cross-Layer Evidence | Complete |
| RQ1 | Graph Fidelity Qualification V1 | QUALIFIED（2026-09-15） |
| RQ2 | Systems + Scale Qualification V1 | QUALIFIED（2026-09-16） |
| SQI-V1 / SQI-V1.1 | Structured Query Interface + Hardening | QUALIFIED / PASS（2026-09-17） |
| SQI-V1.2 | Cost Optimization Qualification | QUALIFIED / RELEASE READY（2026-09-20） |

**SQI-V1.2 = 最新正式发布**（tag `provenlattice-sqi-v1.2`）。

诚实边界：Overlay V1.1 正式资格 NOT STARTED（工程级 parity/conflict 证据已在案）；
S3+ scale bands / concurrency、第四个 benchmark 仓库 NOT STARTED。

## 2. Post-V1.2 implemented development（已集成 main，development checkpoint）

以下能力均已集成 main。这是**开发进展记录，不是正式 V1.3 qualification**；
V1.3 尚未打 tag、尚未举行正式 qualification 汇总。

| 项 | 状态 |
| --- | --- |
| Analysis Layer D0–D8（Python AST/CFG，可选派生层） | ✅ QUALIFIED（Python-only，2026-09-22；Base Graph 零影响回归 137/137） |
| D8-RV1 历史 ADOPTION_GAP case 重验 | ✅ 已闭合：CASE_SOLVED_WITHOUT_PROVENLATTICE ×2（如实在案，不计能力 win） |
| Context Bundle / `task-context`（D9-C1/C2） | ✅ implemented（task-context-v0 事实包，fact_id + evidence_ids 可追溯） |
| Native MCP 暴露（D9-C7/C8） | ✅ implemented（单工具透明桥接，C8-A 冻结合约 byte-identical） |
| normalization-v2（D9-C9） | ✅ implemented（Agent trace → 事实级观测，raw≡normalized 校验） |
| D9-C10 P2 受控能力稳定性 | ✅ PASS（2026-10-09；12/12 cells、6/6 pairs VALID、0 leakage） |
| ContextBench zstd 16-case 重验 | ✅ 14/16 resolved、0 真实失败、2 infra-excluded（≠16/16；对比历史 13/16 无回归） |
| C 分析链 A1/A2/A2.1/A3/A3.5/A3.6 | ✅ 已集成 main（C normalized AST、function-local CFG V1 + `&&`/`||`/`?:` 短路、调用语义分类 direct/indirect/unresolved、definition-preference 紧凑上下文；全量回归 254/254） |
| R1 revalidation 包 / manifest / colleague guide | ✅ 冻结（wheel sha256 在案；结果不预写） |

## 3. Pending validation

- **Colleague 16-case rerun（R1 revalidation）= current next experiment**：
  环境受控重跑全部 16 个 ContextBench-zstd case，与 2026-10-09 本地批
  （14/16 resolved、2 infra-limited、0 真实失败）对比。入口：
  `revalidation/c-contextbench-zstd-r1-manifest.json` +
  `docs/c-analysis-colleague-revalidation-guide.md`。结果不预写。
- V1.3 正式 qualification 汇总 + tag：待上述 revalidation 之后再收敛；
  在此之前不宣称正式 V1.3 qualification。

## 4. Future capability candidates（按五层映射；候选，未排期、不承诺）

> **范围说明**：本表只描述 **main 已集成范围**的未来候选。PR #1 分支已实现的
> 检测类能力（Semantic Events / Sparse CFG/DFG / Defect Queries 等）不在
> "future candidate" 之列，其整合状态以 Gold Target V2 节 G7 与
> [design-dual-capability-integration.md](design-dual-capability-integration.md)
> 为准。
>
> **Vector/semantic index = implementation-dependent**：若实现为
> repository-level canonical semantic index 属 **L1**；若仅作为 task-context
> candidate retrieval accelerator 属 **L3**。最终归属由其数据生命周期决定，
> 不预绑定单一层。
> Runtime Log / Commit History / Validation Result ingestion 同时对应
> **L1 ingestion/knowledge + L4 provenance/evidence**。

| 层 | 候选 | 状态备注 |
| --- | --- | --- |
| L1 | S3+ scale bands / concurrency；cross-repository indexing；distributed indexing；canonical vector index（仅当未来作为 repository-level index）；Runtime Log ingestion；Commit History ingestion；Validation Result ingestion | not started |
| L2 | Def-Use / Local Data Flow；Points-to / precise function-pointer resolution；Taint / Security Analysis；C++ deep analysis；Clang semantic enrichment；compile_commands-aware analysis；Interprocedural CFG | **def-use not justified yet**——真实 case 未证明必要（`A4_DEFUSE_NOT_YET_JUSTIFIED`），出现真实需求信号再启动，非已规划必做；其余 future candidate（当前 C indirect 调用仅如实分类、永不 name-bind，不做 target 解析） |
| L3 | semantic/vector retrieval accelerator（仅当 vector index 服务 task-context relevance 而非 canonical index）；smarter context selection；context budgeting / profile selection | future candidate |
| L4 | Runtime evidence provenance；Validation evidence；richer normalization；audit/verification extensions | future candidate |
| L5 | Plugin；SDK；REST/API service；additional Agent adapters | evidence-driven decision（MCP 已落地，CLI = baseline） |
| 跨层 | Overlay V1.1 正式资格（candidate，工程级证据已在案）；第四个 benchmark 仓库（not started） | 见 §1 诚实边界 |

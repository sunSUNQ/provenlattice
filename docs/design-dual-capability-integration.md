# Dual-Capability Integration Design：main 与 PR #1 的统一架构与整合规划

> 版本：V1（2026-10-12）
> 文档地位：Gold Target V2 的**整合设计附件**。权威规划入口仍是
> [docs/roadmap.md](roadmap.md) 的 Gold Target V2 节；本文记录两条开发线的
> 实现差异审计、能力映射、语义差异矩阵、三臂对照实验设计与渐进整合路线。
>
> **边界声明**：
> - 本轮为文档与架构规划更新，未修改任何生产代码、测试基线或冻结实验数据；
> - **PR #1 未合并**。文中所有 PR #1 能力均标注为「PR 分支可用、未集成 main」，
>   其能力是否、何时、以何种形态进入 main，由 Phase 1–2 的实验证据决定；
> - 不预先认定 main 或 PR 任一实现全面优于对方（见 §6）。

## 目录

1. 背景
2. 路线 A 审计：当前 main
3. 路线 B 审计：PR #1
4. 能力映射表
5. 语义差异矩阵
6. 互补性评估
7. 统一架构：Shared Foundation + Unified Analysis Engine + Dual Task Domains
8. 三臂对照实验设计（待执行）
9. 渐进整合路线（Phase 1–5）
10. 风险与开放问题

---

## 1. 背景

ProvenLattice 当前存在两条并行开发路线：

- **路线 A（main）**：面向 Agent 日常编码辅助的工程证据基础设施——基础代码
  图谱、可选 AST/CFG 分析层（D0–D8 + C 分析链 A1–A3.6）、task-context 事实包、
  统一证据与规范化、CLI/MCP 暴露。五层 Gold Target（L1–L5）已冻结于 roadmap。
- **路线 B（PR #1，branch `fork/main` = `fcd363c`，未合并）**：面向代码检测的
  缺陷导向稀疏语义程序图——Semantic Events、Sparse CFG、Sparse DFG、
  Ownership Contracts、8 类 Typed Defect Query、Evidence Bundle，以及支撑它们
  的冷存储分离与查询性能优化。

两条路线共享同一 Foundation Graph 与 identity 体系（PR #1 直接构建在 main 的
storage/resolver/graph 之上，且其最后一个提交 `fcd363c` 已显式适配 main 的
C call-kind 语义与流式 resolver），但分析目标、抽象粒度与实现路径不同。
Gold Target V2 决定将其统一为**一个平台的两个能力域**（Agent Development =
默认核心；Code Inspection = 可选高级），而不是长期维护两套系统。

---

## 2. 路线 A 审计：当前 main

> 证据基础：`docs/design-optional-analysis-layer-vision.md` §10（D0–D8 冻结
> 契约）、README 五层文字版、roadmap §2。以下全部为 **main 已集成能力**。

### 2.1 L1 Foundation（默认启用）

- Python + C/C++ 基础解析；Repository/File/Symbol、Definition/Reference/Call、
  Dependency/Impact、Knowledge（Spec/Requirement/Document）。
- `resolved / ambiguous / unresolved` 三态引用；只有 resolved 生成 Edge。
- RQ1 图保真度、RQ2 系统与规模、SQI-V1/V1.1/V1.2 正式资格；Overlay V0.4
  工程级 parity（正式资格 NOT STARTED）。

### 2.2 L2 Optional Analysis（可选派生层，`analysis_*` 表族）

| Analyzer | id / contract | 粒度与要点 |
| --- | --- | --- |
| Python AST | `ast:python` / `python-ast-v1` | 真实 CST 全量节点（含函数体），parent 链、structural_path、span |
| Python CFG | `cfg:python` / `python-cfg-v1` | statement 级、intraprocedural；entry/exit/condition/callsite/merge/return/break/continue；next/true/false/back 等边；**无异常边、无 async** |
| C normalized AST | `ast:c` / `c-ast-v2` | `.c/.h`，normalized AST（tree-sitter kinds 仅存 `parser_kind`） |
| C CFG | `cfg:c` / `c-cfg-v2` | sequence/if/else/while/do/for/break/continue/return/**switch/case/default/fallthrough/goto**/implicit exit |
| C 短路 CFG | A2.1（同 `cfg:c`） | 表达式级 `&&`/`\|\|`/`?:` lowering，operand 复用 normalized AST identity |
| C 调用语义 | A3（foundation metadata） | `call_kind = direct/indirect/unresolved`；**indirect 永不 name-bind** |

- 存储：单 `codegraph.db` 内 `analysis_*` 表族；`file × analyzer` 原子替换；
  失效键 = file_id + analyzer + source_hash + feature_version（fail-closed）；
  payload 硬上限。
- 编排：`analyze <repo> --scope <dir> --features ast,cfg`（feature/scope 校验
  先于 mutation，cfg→ast 依赖编排）；查询六态
  available/not_built/stale/unsupported/not_available/corrupt（查询永不隐式
  analyze）；`explain-symbol --analysis` 附带分析事实。
- 明确不做（D4/D8 边界）：whole-program CFG、interprocedural taint、def-use
  （`A4_DEFUSE_NOT_YET_JUSTIFIED`）、points-to / 精确 function-pointer target。

### 2.3 L3/L4/L5

- L3：`task-context <symbols>` → task-context-v0 事实包（fact_id +
  evidence_ids 可追溯）；D9-C10 受控稳定性 PASS。
- L4：core provenance（E-CALL-*/E-REF-*、source span、三态）、SQI citation
  closure、normalization-v2（raw≡normalized 校验）。
- L5：CLI（baseline 全命令面）+ native MCP（单工具透明桥接，C8-A 冻结合约）。

---

## 3. 路线 B 审计：PR #1

> 证据基础：PR #1 描述与 12 个提交、PR 分支源码（`sparsecfg.py` / `sparsedfg.py`
> / `defect.py` / `contracts.py` / `semantics/`）、PR 自带知识库（`知识库/01–08`）。
> 以下能力**均属 PR 分支，未集成 main**；性能与精度数字来自 PR 冻结实验，
> 其语料与口径与 main 历史实验不同，不可直接比较（见 §8 前提）。

### 3.1 三层图模型（PR 的核心抽象）

```text
第三层  Defect Semantic Relations   CONTROL_REACHES · DATA_FLOW_TO · CONSUMES
                                    ——缺陷推理真正消费的关系
第二层  Semantic Event Layer        CALL · DEREFERENCE · READ · BRANCH · RETURN ·
                                    WRITE · CHECK · THROW · ALLOC · RELEASE ·
                                    LOCK · UNLOCK · ATOMIC · THREAD_SPAWN ·
                                    THREAD_JOIN（15 类）
                                    ——缺陷分析的粒度：不是语句，是「操作」
第一层  Structural Code KG          Repository · Directory · File · Symbol
                                    ——与 main L1 同源的全局骨架
```

- 事件由 TOML 词汇表驱动（`semantics/vocabularies/cpp.toml`、`python.toml`），
  刻意保守（ALLOC/RELEASE 白名单；`qualified_exclude`、`out_param` 等轴），
  词汇表以 package-data 随 wheel 分发。
- 关系层实测规模：redis-50 上 CONTROL_REACHES 162,268 条 vs DATA_FLOW_TO
  6,055 条（≈27:1）；`CONSUMES` 三仓合计 2 条（PR 自己如实登记为
  「交付了但基本不产出」）。

### 3.2 Sparse CFG / Sparse DFG

- `sparsecfg.py`（~2,650 行）：方法内语句坍缩为「词汇表事件 + CHECK/BRANCH/
  DEREFERENCE 结构点 + 每方法一个合成 exit」；边带 `branch=true/false`、
  `fallthrough`（switch 链）等 flag；声明同一性标注（STORAGE_LOCAL/PARAMETER/
  FUNCTION_STATIC/FIELD/FILE_STATIC/GLOBAL/UNKNOWN 七类）；点身份经
  `PointKey` 由 graph.py 解析；模块不依赖 tree-sitter C grammar 即可 import。
  **goto 跳转目标不建模**（链直接结束，登记为 stage-3 不精确项）；catch 子句
  fall-through 已处理；`try` 有处理入口。
- `sparsedfg.py`：DATA_FLOW_TO / CONSUMES，via 链元数据；四类流；查询期
  参数绑定。DFG 只保留五类缺陷相关的 value flow。
- READ/WRITE 访问事件（stage 5A）携带声明同一性——这是 PR 对 READ/WRITE
  identity 的回答，main 当前无对应持久事实。

### 3.3 Contracts 与 Defect Typed Queries

- `contracts.py`：declared/inferred ownership contracts（TOML 配置），被
  `resource_lifetime` 与 `race_condition` 消费。
- 8 类查询：`double_free`、`use_after_free`、`null_flow`、`lock_order`、
  `race_condition`、`resource_lifetime`、`error_handling`、`taint_path`，
  外加 `defect all`；CLI `provenlattice defect <query>` 支持 `--subject`、
  `--max-hops/--max-paths/--max-candidates`、`--list`、`--no-contracts`。
- 每个候选携带**证据路径 + resolution status**；`MAY_ALIAS` 仅作候选元数据，
  不是别名分析；taint 为 TOML 注册的 4 source/3 sink 最小集，无 sanitizer 模型。
- **精度基线（PR 如实登记）**：stage-6 人工裁定 32 候选 = 1 TP / 31 FP
  （precision 1/32）；stage-9 修复后 `lock_order` llama 25→16、redis 1→0，
  `error_handling` llama −2,009 / redis −32（全部逐条归因为 FP）；残量 FP
  以 API-contract / execution-model 知识缺失为主（26 例裁定中 24 例
  `needs_dfg=false`）。

### 3.4 存储与性能（PR 附带交付）

- 冷/热存储分离：`raw_references` 与 parse cache 移入 `codegraph.cold.db`
  （TEMP VIEW 保持旧读取兼容；legacy 布局自动识别、不迁移；split 前旧库
  update 显式 raise——**无迁移路径**，PR 登记）。主库 −12.7%（redis）/
  −20.9%（llama）；update 峰值内存 −13.9% / −23.4%。
- 缺陷图每次 `all` 只物化一次（19.2s→11.0s，−43%）；`find_paths` 改读可达性
  扫描自身 BFS 树（use_after_free 121.8s→4.4s，27.7×）；证据路径优化
  （五跳 −26% / −28%，输出字节级一致）。
- 顺带修复交付级缺陷：缺失 parse cache 不再被当作「文件解析为空」静默清空。

### 3.5 PR 自我登记的边界（来自 `知识库/07`）

1. **它不确认缺陷**——全部输出是 candidate，不是 verified finding。
2. **语言边界：CFG/DFG 只有 C/C++**（事件词汇表含 Python 基础轴，但未在
   Python 语料上做缺陷验证）。
3. 覆盖边界：缺陷矩阵 38 类，仅展开 9 类。
4. DFG 四种不产边情形（判据边界）。
5. 已知残量：局部变量不产生 WRITE 事件、别名两侧盲区、循环变量/lambda 捕获
   无作用域身份、`arguments` 被压缩、次序敏感窗口。
6. `E-DEFECT-` 证据 ID 查找仍重跑全部 8 个查询；`get_control_paths` /
   `_pattern_result` 在 `all` 路径外各物化一次。
7. 测试：PR 分支 17 个测试文件 +7,678 行；PR 报告 HEAD 333 通过（main 起点 322）。

---

## 4. 能力映射表

> 「状态」列指统一架构下的整合状态，全部为**规划**，未实现。

| 当前 main | PR #1 | 目标（统一架构） | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| Normalized C AST（`analysis_c_frontend` + `analysis_c_ast`，c-ast-v2） | Tree-sitter semantic extraction（`parsing/events.py` + 词汇表） | 统一 Normalized Program IR 契约 + 语言适配器（frontend 可插拔，事件/IR 从契约派生） | 规划 | main 的 normalized AST 与 PR 的 vocabulary axis 描述同一代码的两个切面；统一 IR 需同时容纳 structural 节点与语义事件 |
| Function-local CFG（`cfg:c` / `cfg:python`，statement 级） | Sparse CFG（`sparsecfg.py`，事件点级 CONTROL_REACHES） | 统一 Canonical Control-Flow Model，提供 **Full CFG View**（完整控制流，Agent reasoning）与 **Sparse CFG View**（缺陷相关事件压缩）双视图 | 规划（过渡期 adapter 共存） | 两者粒度与用途不同；目标是**一个事实来源、两个视图**，不是两套长期并存的 walker（见 §5 投影保真行） |
| Call semantics（`call_kind` direct/indirect/unresolved；indirect 永不 name-bind） | Semantic CALL events（词汇表驱动） | 共用稳定调用身份（call site identity + call_kind + callee shape），事件层引用而非重复判定 | 规划 | PR `fcd363c` 已按 main 的 call_kind 语义校准，方向一致 |
| AnalysisStore（`analysis_*` 表族；file×analyzer；fail-closed freshness） | Semantic persistence（`semantic_edges` / 事件表 + cold store 布局） | 统一派生数据缓存、analyzer version 与 freshness 契约（含冷/热布局策略） | 规划 | PR 的 cold store 是布局级改进，对 L1 也有效；需统一「哪些表冷存」的 registry 决策 |
| Optional analyzers（orchestrator `--features ast,cfg`） | Semantic/Defect pipeline（`defect` 命令 + 语义抽取链） | 全部纳入统一 **Analyzer Capability Registry**（能力依赖、语言支持、成本、构建状态、缓存失效） | 规划 | Registry 是 Capability Profiles（§7）的实现基础 |
| L4 provenance（E-CALL-*/E-REF-*、fact_id、三态引用） | Evidence Bundle（`E-DEFECT-` 证据 id、bundle、resolution status、missing evidence 分类） | 统一证据契约：stable identity、source span、provenance、三态、analyzer version、freshness、missing evidence、truncation/coverage、**Candidate ≠ Verified Finding** | 规划 | PR 的 missing-evidence 分类器（`_MISSING_*` 描述符）是可复用资产 |
| L3 Task Context（task-context-v0） | Defect Query（`defect` 命令） | L3 统一任务编排：Agent Development Task Services 与 Code Inspection Task Services 双业务入口，共用能力选择/范围规划/结果组装 | 规划 | 两个入口、一个编排层；检测入口不得隐式触发高成本分析（L1 默认成本不变） |

---

## 5. 语义差异矩阵

> 逐项对比双方对同一语言语义的处理。统一方向为长期目标，允许过渡期
> 两套实现经 adapter 共存（Gold Target V2 原则 4）。

| 语义点 | main（analysis_c_cfg / analysis_cfg） | PR #1（sparsecfg / defect） | 统一方向 |
| --- | --- | --- | --- |
| **goto / label** | 完整建模（c-cfg-v2 显式 goto/label 节点与边） | **跳转目标不建模**：goto 后链直接结束（PR 登记的不精确项） | 统一 IR 中 goto 是 Full View 一等事实；Sparse View 可保守近似，但必须携带「此处 goto 未解析」的 missing-evidence 标注，禁止静默截断 |
| **switch / fallthrough** | case/default/fallthrough 显式节点与边 | `fallthrough` 边 flag（switch 链 pending 机制） | flag 词表统一；两边语义一致，合并成本低 |
| **short-circuit（&&/\|\|/?:）** | 表达式级 lowering（A2.1，operand 复用 AST identity） | conditional_expression 有处理入口；BRANCH 事件粒度记录分支 | Full View 保有表达式级精度；Sparse View 以 CHECK/BRANCH 点承接；投影 oracle 需验证短路语义在两个视图一致 |
| **function pointers / indirect calls** | `call_kind = indirect` 分类，**indirect 永不 name-bind**（A3 边界） | 未发现专门建模（无 indirect/function-pointer 语义轴） | 调用身份统一走 `call_kind`；间接调用的资源语义（如通过 fp 释放）登记为 missing evidence，不得冒充 resolved |
| **C++ exception / RAII** | 无异常边（D4 明确 CFG_EXCEPTION 属后续扩展） | catch 子句 fall-through 已处理；THROW 事件（含 noreturn 建模：GGML_ABORT/GGML_ASSERT）；`SUBJECT_FROM_RAII` 所有权来源 | 异常边进统一 IR（Full View 可选边）；RAII 所有权来源被 contracts 体系采纳；`assert` 双方一致不建模为 noreturn |
| **control-flow reachability** | CFG 邻接查询（函数内） | CONTROL_REACHES 持久化 + `_Reachability` BFS（route 复用，防 find_paths 悬崖；`truncated` 仅在全结果集时置位） | 统一 reachability 服务：Full 邻接与 Sparse CONTROL_REACHES 共享 BFS 基础设施与 truncation 语义 |
| **READ/WRITE identity** | 无对应持久事实（analysis 表族不含访问事件） | READ/WRITE 访问事件（stage 5A）+ 声明同一性七类（STORAGE_*） | **PR 的贡献应被统一 IR 采纳**；声明同一性（parameter/field/global…）是 ownership 与 race 分析的前提 |
| **ownership / alias** | 无 | 所有权契约表（declared + inferred）；`MAY_ALIAS` 仅候选元数据；别名两侧盲区、锁别名精度缺失如实登记 | 契约表纳入统一 Registry（数据文件，非代码）；alias 长期方向是 points-to（main future candidate），短期以 missing-evidence 标注 |
| **CFG → Sparse 投影保真** | 不适用（main 无 sparse 层） | Sparse CFG 独立构建（事件驱动），**非**从 Full CFG 投影 | 允许继续直接构建 Sparse（Gold Target V2 明确不强制先持久化 Full CFG），但三臂实验必须含 projection-oracle：同一函数上 Full/Sparse 的可达性结论冲突需可解释（见 §8 T2） |

---

## 6. 互补性评估

> 按要求不做整体优劣裁决；逐维度记录双方更强的一面。

**main 更强的一面：**

1. **语义精度与语言覆盖的完整性**：goto/label 完整建模、表达式级短路、
   indirect call 严格不 name-bind——这些是 Agent reasoning 依赖的「不撒谎」
   事实；PR 在 goto 与 indirect 上有登记的不精确。
2. **资格治理成熟度**：RQ1/RQ2/SQI 三代正式资格、D0–D8 每阶段零影响回归、
   freeze-contract 方法论；PR 的验证是 diagnostic 级（冻结语料上的自查实验），
   尚无跨团队正式 qualification。
3. **Python 支持**：main 的 AST/CFG 在 Python 上已正式资格；PR 的缺陷链只有
   C/C++ 语料验证。
4. **增量与多版本**：overlay/session/branch 体系与增量 parity 证据在 main。

**PR #1 更强的一面：**

1. **缺陷语义的事件模型**：15 类语义事件 + 词汇表驱动是比 statement CFG 更
   贴近缺陷推理的粒度；READ/WRITE identity 与声明同一性是 main 缺失的事实层。
2. **typed query + evidence bundle 的完整闭环**：8 类查询、每候选证据路径 +
   resolution status + missing-evidence 分类，正是 Gold Target V2 L4 想要的
   Candidate Finding 形态。
3. **存储与查询工程**：冷/热分离、流式 update、共享图物化、BFS route 复用——
   这些对 L1 同样有价值的布局与性能改进已在真实大仓（redis-50 / llama.cpp-69）
   上验证。
4. **诚实的精度基线**：1/32 precision 基线不掩盖、逐条归因 FP，并给出
   「残量 FP 是 API-contract 知识问题而非解析问题」的明确归因——为 Phase 4
   的质量工作提供了可测量起点。

**结论**：main 是更严格的「事实基础设施」，PR 是更完整的「检测应用层」；
统一架构（§7）正是让两者各归其位：事实与治理来自 main 的方法论，检测能力
经 Registry 进入 L2，两类任务经 L3 编排共享。

---

## 7. 统一架构

**Shared Foundation + Unified Analysis Engine + Dual Task Domains**

```text
                ┌──────────────────────────────────────────────┐
                │  L5 Exposure：CLI（baseline）· MCP · future  │
                │     Agent Query 入口  |  Inspection 入口      │
                └───────────────────┬──────────────────────────┘
                                    │
          ┌─────────────────────────┴─────────────────────────┐
          │   L3 Task Services / Orchestration（统一编排）      │
          │   Agent Development TS   |   Code Inspection TS    │
          │   （capability 选择 · scope 规划 · 结果组装/打包）   │
          └─────────────────────────┬─────────────────────────┘
                                    │
          ┌─────────────────────────┴─────────────────────────┐
          │   L2 Unified Optional Analysis（统一可插拔引擎）     │
          │   Analyzer Capability Registry                     │
          │   ┌───────────────┬─────────────────────────────┐ │
          │   │ Normalized IR │ Canonical Control-Flow Model │ │
          │   │  Full CFG View · Sparse CFG View · Sparse DFG │ │
          │   │  Semantic Events · Def-use · Alias/Ownership  │ │
          │   │  Taint · Defect/Security Analyzers            │ │
          │   └───────────────┴─────────────────────────────┘ │
          └─────────────────────────┬─────────────────────────┘
                                    │
          ┌─────────────────────────┴─────────────────────────┐
          │   L4 Evidence / Results（统一证据契约）             │
          │   fact/evidence id · span · provenance · 三态      │
          │   missing evidence · truncation · Candidate≠Verified│
          └─────────────────────────┬─────────────────────────┘
                                    │
          ┌─────────────────────────┴─────────────────────────┐
          │   L1 Foundation / Knowledge（默认 Always-on）       │
          │   graph + knowledge + core provenance（低成本）     │
          └──────────────────────────────────────────────────┘
```

七条架构原则（Gold Target V2 冻结版，详见 roadmap Gold Target V2 节）：

1. **共享基础图谱**：Repository/File/Symbol/Definition/Reference/Call/
   Dependency/Impact/Knowledge/Identity/Provenance 只有一份事实来源。
2. **统一分析引擎**：AST/CFG/Events/DFG/Sparse Graph/Defect Analyzer 归属
   同一可插拔体系；两个能力域按任务复用分析事实，不各自养 walker。
3. **能力按需启用**：`Capability Selection × Scope Selection`；Analyzer
   Capability Registry 管理依赖、语言支持、成本、构建状态、缓存与失效。
4. **统一语义来源**：长期目标是统一 Normalized Program IR 与 Canonical
   Control-Flow Model；Full/Sparse 是同一事实的不同**视图**，不是两套事实
   来源；语言专属语义由独立 frontend/adapter 承载。**不强制**每次生成
   Sparse CFG 先完整持久化 Full CFG。
5. **低成本默认服务**：L1 默认路径不得因检测能力承担额外成本；高级分析按
   capability × scope 触发。
6. **统一证据契约**：见 §4 最后一行；Candidate / Uncertain / Verified
   Finding 严格区分，不确定的推断不自动升级为已确认事实。
7. **过渡期共存规则**：两套 CFG/IR 实现允许经 adapter 共存，但必须
   （a）登记差异矩阵（§5）；（b）逐步收敛到统一 Registry 注册的契约；
   （c）禁止在同一查询内混用两套实现而不标注来源。

**Capability Profiles（长期产品组合目标，未实现）**：

| Profile | 组合 | 服务域 |
| --- | --- | --- |
| `basic` | L1 基础图谱与日常查询 | 默认 |
| `development` | basic + 按需 AST/CFG + Agent task-context | Agent Development |
| `deep` | basic + 选定的深度数据流分析 | Agent Development（高级） |
| `security` | basic + Semantic Events + Sparse CFG/DFG + Defect Queries | Code Inspection |

> profiles 是能力组合的 UX shortcut，不改变五层架构；不得把未实现的
> profile 写成已交付功能。

---

## 8. 三臂对照实验设计（待执行）

> **状态：PLANNED，未执行。** 本节是实验设计，不是结果记录；任何数字在
> 冻结 artifact 产生之前不得写入任何文档。

### 8.1 三臂定义

| 臂 | 内容 | 版本锚点 |
| --- | --- | --- |
| A | 当前 main | `main`（冻结 commit，Phase 1 确定） |
| B | PR #1 | `fork/main` = `fcd363c`（已含 main 集成适配） |
| C | 统一架构原型 | Phase 3 产物（统一 IR/CFG 后的第一个原型 tag） |

### 8.2 测试四类

1. **Semantic Correctness**：语言与控制流语义正确性——§5 语义差异矩阵逐项
   出 gold case（goto/label、switch/fallthrough、短路、indirect、exception/
   RAII、READ/WRITE identity、ownership/alias）；以人工裁定 gold 为 oracle。
2. **Capability Coverage**：AST / CFG / Event / DFG / Defect Query /
   Evidence 各能力的可用矩阵（语言 × 能力 × scope）。
3. **Engineering Cost**：索引时间、增量时间、峰值 RSS、DB 大小（主库+冷库
   分列）、查询耗时（含 `defect all` 与 task-context 两类）。
4. **Real Utility**：Agent 编码任务结果（复用 ContextBench-zstd 协议）与
   真实缺陷候选检测效果（precision / recall + 人工复核）。

### 8.3 复用与隔离

- 优先复用现有夹具（`tests/fixture_*`）、zstd ContextBench 16-case 协议、
  PR 的 defect benchmark 语料（redis-50 / llama.cpp-69 冻结库）。
- **不直接比较两套历史结果**：main 的 ContextBench/SQI 数字与 PR 的
  defect 数字来自不同任务集合与验证环境。三臂实验必须：
  - 冻结测试代码与仓库版本（arm anchor + 语料 sha256）；
  - 统一执行环境（同机、同依赖、同 Python 版本）；
  - 相同输入与测试预算（token / 时间 / 迭代上限）；
  - 候选 precision / recall 均经人工复核并登记裁定者与分歧。

### 8.4 必测专项

- **Sparse projection 路径正确性**（T2）：同一函数上 Full View 与 Sparse View
  的可达性/流结论逐 case 对照；冲突必须可归因（登记为投影语义或缺陷）。
- **默认 L1-only 成本回归**（T3）：三臂在「不启用任何 L2 能力」下的 index /
  update / 查询成本与存储布局对比；验收线：统一架构原型相对 main 的 L1
  默认成本无可感知回归（具体预算见 §9 Phase 2/3 门槛）。
- **分析缓存 freshness 与增量失效**（T3）：编辑后 stale 检测、增量后
  analysis/semantic 表失效一致性、cold store 布局下的 update 正确性
  （PR 已有部分证据，需在统一架构上重验）。

---

## 9. 渐进整合路线（Phase 1–5）

> 每阶段八要素：目标 / 涉及模块 / 保留能力 / 实验门槛 / 性能预算 / 交付物 /
> 停止条件 / 回退策略。**当前只规划，未启动；Phase 1 之前需人工验收本设计。**

### Phase 1 — Architecture and Baseline Audit

- **目标**：冻结双方基线，形成可对照的能力与成本基线档案。
- **涉及模块**：无代码改动；`docs/`（本文件 + roadmap）；`revalidation/` 清单机制复用。
- **保留能力**：main 与 PR 各自独立可运行、可测试。
- **实验门槛**：§8 的 T1/T3 基线跑通（A、B 两臂），gold case 集冻结。
- **性能预算**：记录型（建立基线，无门槛）。
- **交付物**：基线审计报告 + 三臂实验 harness（A/B 先行）+ 冻结语料清单。
- **停止条件**：A/B 任一臂在统一环境无法复现其关键数字（差异 >10% 且不可归因）。
- **回退策略**：回到各自文档记录的冻结结果，标注环境差异，重设预算。

### Phase 2 — Optional Inspection Integration

- **目标**：PR 的检测能力以**可选配置**接入 main，经 Analyzer Capability
  Registry 注册；L1 默认成本与行为稳定。
- **涉及模块**：`cli.py`（defect 命令接入）、`orchestrator.py`（features 扩展）、
  `semantics/`、`sparsecfg/sparsedfg/defect/contracts`、`storage.py`（cold store
  决策）、`pyproject.toml`（package-data）。
- **保留能力**：main L1/D0–D8 全部契约与测试不改动语义；PR 的 8 类查询与
  evidence bundle 形态不变。
- **实验门槛**：PR 全部测试在合并树上通过；L1-only 成本回归（T3）通过；
  defect 语义正确性抽检（T1 子集）通过。
- **性能预算**：不启用 defect 时，index/update/查询性能偏差 ≤ 噪声带
  （以 A 臂基线 ±N% 定义，Phase 1 冻结具体数字）；启用时按 §3.4 记录。
- **交付物**：merge PR（若 Phase 1 门槛通过）或等价 rebase 分支；registry
  注册表 v1；`security` profile 的最小可行配置示例。
- **停止条件**：cold store 与 main 增量路径出现无法就地修复的语义冲突；
  或 L1 回归超预算且无低成本修复。
- **回退策略**：feature flag 关闭 defect 入口；cold store 保留 legacy 布局
  分支（PR 已内建 legacy 检测）。

### Phase 3 — Shared IR / CFG Convergence

- **目标**：统一 Normalized Program IR 与 Canonical Control-Flow Model；
  Full/Sparse 成为双视图；消除重复 CFG walker。
- **涉及模块**：`analysis_c_frontend/analysis_c_ast`（IR 候选基础）、
  `parsing/events.py` + `semantics/vocabulary.py`（事件契约）、
  `analysis_cfg/analysis_c_cfg` 与 `sparsecfg`（walker 收敛）、`models.py`、
  `identity.py`（PointKey 与 symbol identity 对齐）。
- **保留能力**：C/C++ 语言语义（§5 全部行）；PR 缺陷能力覆盖不回退。
- **实验门槛**：T1 全量 gold case 双视图通过；T2 projection oracle 通过
  （冲突全部可归因）；C 分析链与 defect 查询的既有回归测试通过。
- **性能预算**：统一 IR 后 `defect all` 不慢于 B 臂基线的 +10%；Full View
  构建成本按 scope 计入 registry 定价。
- **交付物**：统一 IR 契约冻结文档；C 臂原型 tag；语义差异矩阵收敛版。
- **停止条件**：统一 IR 无法在不丢失任一侧行语义的前提下表达 §5 某关键行
  （如 goto 或 READ/WRITE identity），且无 adapter 方案。
- **回退策略**：维持 Phase 2 的 adapter 共存形态，差异矩阵作为长期登记。

### Phase 4 — Data Flow and Defect Quality

- **目标**：优化 DFG、Identity、Ownership、API Contract、Alias、路径查询
  性能与误报。
- **涉及模块**：`sparsedfg.py`、`contracts.py`、`defect.py`、词汇表 TOML、
  `resolver.py`（call_kind 深化）。
- **保留能力**：T1/T2 全部通过项不回退。
- **实验门槛**：以 stage-6 基线（1/32）与 stage-9 后状态为参照，precision
  提升可复现且 FP 逐条归因；残量 FP 的 `needs_dfg=false` 主因（API-contract
  知识缺失）有对应改进项落地或明确豁免。
- **性能预算**：`defect all` 与单查询成本不劣化超过 Phase 3 冻结带。
- **交付物**：precision/recall 报告（人工复核）；契约/注解层设计文档。
- **停止条件**：精度提升依赖需要 whole-program 分析且成本超预算。
- **回退策略**：保留规则级开关（如 `error_handling` 的 builtin 过滤可独立启停）。

### Phase 5 — Agent + Inspection Productization

- **目标**：统一 CLI/MCP、Capability Profiles、Evidence API、文档与真实
  Agent / Inspection 测试。
- **涉及模块**：`cli.py`、MCP 桥、`analysis_query.py`（六态契约扩展到
  inspection 能力）、文档面。
- **保留能力**：全部前序阶段交付。
- **实验门槛**：ContextBench 协议下 Agent Development 无回归；Inspection
  任务集（defect 复核工作流）形成首个 controlled 证据。
- **性能预算**：profile 切换零额外常驻成本；L1-only 仍是默认。
- **交付物**：profile 配置面；Evidence API 文档；双域任务报告。
- **停止条件**：profile 化导致查询契约破坏性变更且无迁移方案。
- **回退策略**：profile 退化为文档化的 capability 组合建议，不做代码开关。

---

## 10. 风险与开放问题

1. **两套 walker 的收敛深度**：Full（statement 级）与 Sparse（事件点级）
   的统一 IR 表达力是 Phase 3 最大技术风险；goto 与 READ/WRITE identity
   是先行探针语义。
2. **精度叙事**：PR 的 1/32 precision 基线必须作为公开参照随能力一起进入
   main 的文档与 registry 定价，避免「检测能力 = 已验证发现」的误读。
3. **cold store 布局决策**：若 Phase 2 接入，需要决定 raw_references /
   parse_cache 冷存是否默认启用（对 L1 用户是布局变更，涉及 `status`
   输出与备份流程）。
4. **Python 侧检测能力空缺**：事件词汇表有 Python 基础轴，但缺陷链未在
   Python 语料验证；`security` profile 对 Python 项目的能力边界须明示。
5. **实验预算与人力**：三臂实验的人工复核（precision/recall、gold case
   裁定）是主要成本；建议沿用 D8/D9 的受控协议与裁定留痕机制。
6. **术语漂移**：本文件、roadmap、vision、README 四处对 L2/L3 的命名已
   统一为 V2 口径（Unified Optional Analysis / Task Services）；后续新增
   文档必须沿用，出现冲突以 roadmap Gold Target V2 节为准。

# PR #1 Capability Reconciliation R1（能力对账与技术选择）

> 任务：PL-PR1-CAPABILITY-RECONCILIATION-R1（2026-10-12）
> 文档地位：对账主报告。全部实测数据见
> [docs/pr1-comparison-test-results.md](pr1-comparison-test-results.md)；
> 集成实施步骤见 [docs/pr1-selective-integration-plan.md](pr1-selective-integration-plan.md)。
> **边界**：未合并 PR；未修改 main / PR 源码；未启动正式代码整合；
> 测试数据全部为本轮实测（环境与基线见对照报告 §1）。

## 1. 冻结基线（Step 1）

| 项 | main | PR #1 |
| --- | --- | --- |
| commit SHA | `14499f840dde177517a3521a8eb735e1a27fb48f` | `fcd363c5fbda7d3f8c818d8b3223525fb001ea05`（PR head，已含对 main 的集成适配提交） |
| 检出位置（隔离 worktree，只读使用） | `%TEMP%\opencode\pl-r1\main` | `%TEMP%\opencode\pl-r1\pr` |
| 测试套件（本轮实测） | **254 / 254 通过**（66.3s） | **530 / 531 通过，1 error**（110.5s；error 根因已定位，见对照报告 §3.1） |
| 环境 | Windows / Python 3.12.10 / tree-sitter 0.26.0（与 requirements.txt 一致） | 同左 |

PR head 与 main 的关系：PR 分支已 rebase 到 main 最新提交之上
（merge-base = main HEAD），且其最后一个提交 `fcd363c` 专门适配了 main 的
C call-kind 语义与流式 resolver——PR 不是从旧分叉点独立演化。

### 1.1 重叠实现与新增能力盘点

**重叠区（双方都有实现）**：

| 能力 | main 实现 | PR #1 实现 |
| --- | --- | --- |
| C/C++ 基础图抽取 | `parsing/cpp.py`（symbol/definition/reference/call，含宏/常量/变量声明为 `definition:false` 符号） | 同文件被 PR 重构（语义事件钩子 + declarations 重构），**基础图产出不同**（见 §4.1，本轮最重要发现） |
| C 调用语义分类（A3） | `parsing/cpp.py` call_kind + `query.get_call_semantics` | 同一 call_kind 机制（PR 经 `fcd363c` 集成，存于 reference metadata；`get_call_semantics` 双方同名同源） |
| CFG | `analysis_c_cfg.py`（statement 级 Full CFG，`cfg:c`） | `sparsecfg.py`（事件点级 Sparse CFG，CONTROL_REACHES） |
| C normalized AST | `analysis_c_frontend.py` + `analysis_c_ast.py`（`ast:c`） | 无对应层（PR 直接从 tree-sitter 树抽事件，不经 normalized AST 持久层） |
| 存储层 | `storage.py`（单库 `codegraph.db`，raw_references 在主库） | `storage.py` 重构：raw_references/parse cache 移入 `codegraph.cold.db`（冷/热分离），流式 update |
| resolver / incremental | main 基线 | PR 改动（7A-2 流式携带引用行 + `fcd363c` call_kind 适配） |

**仅 PR 存在的能力**：`semantics/`（15 类语义事件词汇表 + taint/contract/defect 模式 TOML）、`parsing/events.py`（事件抽取）、`sparsecfg.py` 的 Sparse CFG、`sparsedfg.py`（DATA_FLOW_TO/CONSUMES）、`contracts.py`（所有权契约）、`defect.py`（8 类 Typed Defect Query + Evidence Bundle + Missing Evidence）、CLI `defect` 命令、冷存储分离、缺陷链性能优化（共享图物化 / BFS route / 证据路径）。

**仅 main 存在的能力**：Python AST/CFG（`ast:python`/`cfg:python`）、C normalized AST 层（`ast:c`）、`task-context` 事实包、normalization-v2、MCP、knowledge layer、overlay/session、formal qualification 体系（RQ1/RQ2/SQI）。

### 1.2 语言覆盖与边界（双方自述 + 本轮验证）

| 语言 | main | PR #1 |
| --- | --- | --- |
| Python | L1 完整 + L2 AST/CFG（formal QUALIFIED） | L1 完整；语义事件词汇表有 python.toml，但**无 CFG/DFG/缺陷验证** |
| C（.c/.h） | L1 完整 + L2 normalized AST/CFG/短路/调用语义 | L1 + 语义事件 + Sparse CFG/DFG + 缺陷查询（主验证语料） |
| C++（.cc/.cpp） | L1 完整；L2 deep analysis 不支持（明确边界） | L1 + 语义事件/Sparse CFG/DFG/缺陷查询可运行（本轮 aria2 实测），但词汇表为 C-API 中心，A3 call_kind 仅 stamp 到 .c 文件（aria2 实测：direct 46,678 / indirect 1 / null 8,466——null 即 C++ 文件未分类） |

---

## 2. 对照测试结论摘要（Step 2，详细数据见对照报告）

1. **CFG 语义结构**：if/else、while、do-while、switch+fallthrough、短路、三目——两侧都能给出正确形状，但**粒度与精度不同**（main 表达式级短路 lowering vs PR 单 BRANCH 坍缩；main goto 完整建模 vs PR 真分支断链）。PR 独有 CHECK/DEREFERENCE/READ/WRITE 事件粒度。
2. **main 侧新发现的健壮性缺口**：for 循环写在单个物理行时 C CFG 整文件跳过（`cfg:no_functions_built`，诚实登记不崩溃）；多行同代码正常。PR 侧同一文件 Sparse CFG 正确。
3. **call semantics**：双方同源一致（direct/indirect/语法 direct+解析 unresolved 三分类都能区分）。
4. **PR 专属能力独立验证**：缺陷链在夹具上正确发现植入的 double_free（证据链 + 3 条 missing_evidence）；aria2 上 8 查询全链可运行（null_flow population 381、error_handling resolved 3,975 等），13.9s 完成 `all`。
5. **性能**（aria2，1,393 文件 / 165k LOC）：PR 索引 +157%（17.27s vs 6.71s）、索引峰值 RSS +88%，但**查询延迟反而快约 2×**（冷存储缩小主库的副产品）；增量更新 PR 12.16s vs main 6.26s；单函数追加增量下 PR 总库 308.1MB vs main 278.4MB。
6. **PR 侧新发现（本轮最重要）**：同一 aria2 语料上 PR 基础图 **Function 节点 9,284→1,268（-86%）、Method 15,307→12,521（-18%）**，缺失的均为常量/宏/成员变量声明（main 标记 `definition:false` 的粗粒度符号）。PR 的 declarations 重构让基础图语义更干净，但**破坏 L1 符号兼容并使 RQ1 资格口径失效**。

---

## 3. 逐模块技术选择（Step 3）

> 判据：实测证据优先；测试数量与代码量不作依据。每项给出代码位置、证据、依据、风险与依赖。

### 3.1 基础图抽取（`parsing/cpp.py` 符号抽取路径）——KEEP_MAIN（附移植门槛）

- **证据**：missing_symbols.json——main-only Function 名 2,469 个（样本 `A2_DELTA_MILLIS`=constexpr 变量、`KEY_GID`=常量、成员变量 `btAnnounce_`）；Method 名 1,393 个（`SocketCore.h` 的 `bindAddrs_` 等，全部 `signature="()"`、`definition:false`）。PR 全部不再产出（aria2：Function 1,268 vs 9,284；DEFINES 17,192 vs 27,941）。
- **依据**：RQ1 图保真度资格（precision 0.931/0.899）是在 main 的抽取行为上取得并冻结的；PR 的 declarations 重构改变了 L1 事实集合本身（外部使用者 `find_symbol('KEY_GID')` 之类查询行为改变）。语义上 PR 更"干净"（常量不是函数），但这属于 **L1 契约变更**，必须走重新资格化，不能随检测能力一起悄悄进入。
- **风险**：若直接采用 PR 的 cpp.py，Agent 日常查询（L1 默认能力）在宏/常量/成员变量上出现静默行为变化。
- **依赖**：PR 的 `parsing/events.py` 事件钩子挂在重构后的 cpp.py 上——选择性移植必须把"事件钩子"与"声明重构"解耦（见集成计划 I1 的阻塞条件 B1）。
- **伴随事实**：PR 的 CALLS 边 2,336 vs main 2,244（+92）、resolved 引用 11,634 vs 11,437——PR 的解析器在调用边上有小幅改进，可在 L1 parity 门下单独评估回 ports。

### 3.2 C normalized AST（`ast:c`）——KEEP_MAIN

- **证据**：main `analysis_c_frontend/analysis_c_ast`（c-ast-v2 契约，D2/A1 冻结，golden 测试在案）；PR 无对应层。
- **依据**：这是 main L2 的既有正式资产，是 Full CFG 与 `get_analysis_summary` 的基础；PR 不提供等价物。
- **风险/依赖**：无。与 §3.3 的 COMBINE 共存（两者输入不同层）。

### 3.3 CFG：main Full CFG vs PR Sparse CFG——COMBINE（分阶段，目标双视图）

- **证据**（构造级实测，见对照报告 §4）：
  - main：goto/label 完整建模（goto 节点 + goto→label 边）；switch 的 case/default/fallthrough/break 全显式；短路 && 表达式级 lowering（两个 condition 节点串联）；do-while 回边正确；**单行 for 缺陷**（§2.2）。
  - PR：BRANCH true/false、loop_back、switch fallthrough flag、do-while true+loop_back 全正确；短路坍缩为单 BRANCH（条件内副作用调用的求值门控丢失，保守但更粗）；goto 跳转目标不建模（真分支从图上断开，PR 自我登记）；独有 CHECK/DEREFERENCE/READ/WRITE 事件点。
- **依据**：两者粒度与用途不同（Agent reasoning 的完整控制流 vs 缺陷推理的事件可达性），Gold Target V2 已定义为同一控制流语义的 Full/Sparse 双视图。**当前证据支持"双视图并存、事实来源逐步收敛"，不支持用一方替换另一方。**
- **风险**：两套 walker 长期并存造成语义漂移（goto 与短路是先行探针——两侧结论已可证不同）。
- **依赖**：PR sparse CFG 依赖 `parsing/events.py` 与 `models.py` 的 PointKey/ParsedEvent/ParsedEdge。

### 3.4 调用语义（A3 call_kind）——KEEP_MAIN（PR 已对齐，无需动作）

- **证据**：main `get_call_semantics`：caller_cs01=direct(target)/run_cs04=indirect/caller_cs09=direct+class unresolved；PR reference metadata 同样携带 call_kind（foo_cs01=direct、fp_cs05=indirect、callee_shape/argument_identifiers 齐全）。
- **依据**：`fcd363c` 之后双方同一机制；main 侧多一个 SQI 查询面（get_call_semantics），保留。
- **风险**：C++ 文件 call_kind 为 null（双方同源边界，非 PR 回归）。

### 3.5 语义事件层（`semantics/` + `parsing/events.py`）——ADOPT_PR（作为可选 L2 analyzer）

- **证据**：aria2 实测 103,042 事件（CALL 48,542 / READ 22,971 / DEREFERENCE 16,165 / CHECK 807 / ALLOC 442 / RELEASE 46 …）；夹具级验证事件形状正确（res01：ALLOC→CHECK→RELEASE×2）。
- **依据**：main 无任何等价物；这是缺陷链的必要基础；词汇表 TOML 是数据非代码，保守白名单可控。
- **风险**：抽取成本进入索引（+157%）——**必须以可选 analyzer 触发，不得进 L1 默认路径**（见 §4.2 与集成计划 I1 门）。
- **依赖**：cpp.py 事件钩子（需解耦移植，B1）；`semantic_events/semantic_edges/semantic_fingerprint` 表。

### 3.6 Sparse DFG（`sparsedfg.py`）——ADOPT_PR（随事件层）

- **证据**：aria2 上 DATA_FLOW_TO 3,089 / CONSUMES 2（CONSUMES 近零产出，PR 自己如实登记）；夹具上 ALLOC→CALL/CHECK→CALL 流边正确。
- **依据**：PR-only；五类缺陷相关 value flow 是 null_flow/UAF/double_free 的输入。
- **风险**：DFG 保守判据的四种不产边情形（PR 登记的召回上限）需进入 registry 的能力说明。
- **依赖**：事件层 + PointKey。

### 3.7 所有权契约（`contracts.py` + `semantics/contracts.toml`）——ADOPT_PR（随事件层）

- **证据**：`race_condition`/`resource_lifetime` 消费契约的候选裁定路径在夹具上可运行；契约是 TOML 数据。
- **依据**：PR-only；Gold Target V2 L2 的 Ownership/Resource Semantics 归属项。
- **依赖**：无独立阻塞；随 defect 链整体进入。

### 3.8 8 类 Typed Defect Query + Evidence Bundle（`defect.py` + CLI `defect`）——ADOPT_PR（作为可选 L2/L3 能力）

- **证据**：植入 double_free 的夹具上按查询名/矩阵键/`all` 三条路径均返回同一候选（E-DEFECT-*、facts、paths、source_evidence、3 条 missing_evidence、confidence 0.5）；aria2 实测：null_flow population 381（resolved 356/ambiguous 16，max_candidates 截断 20）、error_handling stored-call-result 8,121（resolved 3,975）、double_free 2、use_after_free 1、taint_path 0（input_to_sink population 954 被判据过滤）、`all` 13.93s。
- **依据**：PR-only 且质量可独立验证；Evidence Bundle/Missing Evidence 契约形态正是 Gold Target V2 L4 要求的 Candidate Finding 形态；输出全部为 candidate，与"不确认缺陷"的边界一致。
- **风险**：aria2 上候选集中于 test/ 文件（需 scope 选择支持）；`max_candidates=20` 默认截断对大仓的覆盖表达需在 registry 定价时说明；残量 FP 以 API-contract 知识缺失为主（PR stage-6 基线 1/32，stage-9 后部分收敛）。
- **依赖**：事件层、DFG、契约；1 个已知失败测试需先修（对照报告 §3.1）。

### 3.9 存储布局：冷/热分离（7A-1/7A-3）——DEFER（收益真实，门槛未过）

- **证据**：aria2 上 PR 主库 224.8MB + 冷库 82.8MB；**查询延迟反而比 main 快约 2×**（6.5–11.2ms vs 12–17ms / 10 次调用）；索引 RSS 409.6 vs 217.8MB。
- **依据**：查询性能收益真实且对 L1 有价值；但它是**默认存储布局变更**——`status` 输出、备份流程、旧库兼容（split 前旧库 update 显式 raise，PR 登记无迁移路径）都受影响。Gold Target V2 的 L1 稳定性原则要求布局变更单独走门槛，不随检测能力捆绑。
- **风险**：无迁移路径；跨布局对比口径复杂（PR 自己也登记了 free page 不可比问题）。
- **依赖**：I4（集成计划）；若 I3（流式 update）先行落地，update 峰值内存收益可先行获得而不动布局。

### 3.10 流式 update（7A-2）——COMBINE（值得单独移植到 main 布局）

- **证据**：PR update 不再物化 raw_references（llama -23.4% 峰值内存，PR 冻结实验）；本轮 aria2 实测 PR 增量 12.16s vs main 6.26s（总量含语义层重建，未单独隔离 7A-2 收益——诚实标注：本轮未做 7A-2 的隔离 A/B）。
- **依据**：L1 update 路径的内存/行为改进，与冷存储决策解耦可先行。
- **风险**：`replace_snapshot` 只重写变更行的语义需在 main 布局上重验 parity。
- **依赖**：resolver/storage 的移植评审；**本轮 NOT_TESTED：7A-2 在 legacy 布局上的隔离收益**。

### 3.11 缺陷链性能优化（7B-1 共享物化、stage-8 证据路径、stage-9 规则修复）——ADOPT_PR（随 defect 链整体）

- **依据**：均为 defect.py/query.py 内部的正确性保持型优化（输出字节级一致由 PR 冻结实验 + 本轮夹具/aria2 复测支持）；stage-9 两项规则修复直接消已归因 FP。
- **依赖**：随 §3.8 进入。

### 3.12 Python 侧事件/缺陷（`semantics/vocabularies/python.toml`）——DEFER

- **证据**：PR 词汇表含 Python 基础轴，但本轮未在 Python 语料上运行缺陷链（无验证证据）。
- **依据**：无证据不集成；`security` profile 对 Python 的能力边界维持 Gold Target V2 的明示空缺。
- **依赖**：Python 语料上的独立验证批次。

### 3.13 PR 已知失败测试与文档修正——REJECT（原样并入）→ 修复后 ADOPT

- **证据**：`test_defect.CliTests.test_a_bad_type_is_a_usage_error_and_an_unexpanded_one_is_not` 在 PR head 报 `RuntimeError: base graph is empty`（cli.run 在 `--type` 校验前打开空库；traceback 在案）。
- **依据**：测试自身缺陷（期望 usage error 先于 DB 打开），非产品逻辑错误；集成时必须先修，不得带病并入。

---

## 4. 选择性集成方案要点（Step 4，实施细节见集成计划文档）

1. **以 main 为基础创建 `integration/pr1-selective`**，按依赖序迁移：I1 语义事件层（可选 analyzer，L1 parity 门）→ I2 缺陷查询 + CLI（先修失败测试）→ I3 流式 update（legacy 布局）→ I4 冷存储（opt-in 布局，单独门槛）→ I5 Registry/Profile 接线。
2. **L1 保护门**：默认路径 index/update/查询行为与成本相对 main 基线无可感知回归（本轮已冻结基线数字：索引 6.71s / 峰值 217.8MB / 查询 12–17ms / 库 152.9MB，aria2）。
3. **禁止事项**：不接受"先整体合并再删重复"；不接受把 PR 的 declarations 重构（§3.1）混在事件层移植里带入；不在 I1–I2 阶段动默认存储布局。
4. **阻塞条件与解决方向**（详见集成计划 §4）：B1 事件钩子与声明重构在 cpp.py 中纠缠；B2 L1 parity 门失败；B3 双 walker 语义收敛（goto/短路先行探针）。

## 5. 与 Gold Target V2 的关系

本轮选择矩阵是 Gold Target V2（docs/roadmap.md）"Unified Optional Analysis + 统一证据契约"路线的第一步实证：ADOPT_PR 各项全部落入 L2 可选引擎与 L4 统一证据契约的既定位置；KEEP_MAIN 项保护 L1 默认服务与已冻结资格；DEFER 项（冷存储、Python 侧）按 evidence-driven 原则等待独立证据。

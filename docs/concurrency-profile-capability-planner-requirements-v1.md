# 并发 Profile 与 Capability Planner：Requirements V1

> 状态：**requirements-only，待 Review/CI 与 Owner 后续合并授权**。
> 范围：`PL-CONCURRENCY-ARCH-REQUIREMENTS-REVISION-V1` / issue-pilot #22。
> 本文冻结架构和接口需求；不实现 Planner、分析器、查询、CLI 或 MCP 行为。

## 1. 决策与边界

Owner 已批准本轮仅冻结下列五类并发需求：

1. 非原子 `++` / `--` 并发竞态；
2. `bool` 标志变量并发竞态；
3. 共享变量并发竞态；
4. 锁未配对；
5. 锁顺序不一致／锁内阻塞。

`atomicity_violation`、`order_violation`、`toctou` 不是本轮检测类型或 query
contract；除非未来证明为上述五类的必要底层依赖，不得以它们扩大 V1 范围。

本需求不改变 ProvenLattice 的 L1--L5：

| 层 | V1 要求 |
| --- | --- |
| L1 Foundation / Knowledge | 保持既有 Foundation Graph、默认 index、实体、关系与成本不变。 |
| L2 Unified Optional Analysis | 承载可选、可复用的底层分析 Capability；新增 analyzer 不是新架构层。 |
| L3 Task Services / Orchestration | 承载 Profile Registry、Capability Planner 和按场景组织；算法仍归 L2。 |
| L4 Evidence / Results | 输出 Candidate、resolved/ambiguous/unresolved、coverage、freshness、missing evidence；`resolved` 不是 Verified Finding。 |
| L5 Exposure | 将来仅提供显式 CLI/MCP Profile 或 query-set 入口；无 Profile 时保持旧语义。 |

不规划 L6、不复制第二套图、不复制第二套 capability registry。Profile 是 Capability
组合的 UX shortcut，不是分析实现，也不是漏洞事实来源。

## 2. 两类 Capability 的分工

**底层 Analysis Capability** 是 L2 可跨场景复用的事实生产者，例如
`events`、`sparse_cfg`、`sparse_dfg`、未来的 `concurrency_context`。它们按
Capability × Scope 构建、缓存、失效并报告语言支持与成熟度。

**Scenario / Detection Capability** 是面向一个漏洞类型的 L3/L4 组织契约：它声明
所需的 L2 facts、选择规则、排除条件、输出候选及证据。它不复制事件提取、CFG、DFG
或基础图实现。既有 `race_condition` 与 `lock_order` 是这一类的现有查询入口。

| 类别 | 责任 | 示例 | 不得承担 |
| --- | --- | --- | --- |
| Analysis Capability | 产生版本化派生事实 | READ/WRITE、LOCK/UNLOCK、控制可达、数据流 | 判定某一漏洞是否真实 |
| Scenario / Detection Capability | 组合事实、应用规则、生成 Candidate/Evidence Bundle | 非原子自增、flag race、lock pairing | 重新建图或隐式扩大 scope |
| Profile | 声明一组 scenario 与参数 | `concurrency-v1` | 绕开 Registry 或默认启用昂贵能力 |

## 3. V1 并发需求矩阵

所有 `concurrency.*` ID 在本文件中是**需求 ID**，不是已实现的 CLI feature 或已注册
query 名称。首期语言范围为 C/C++；Python 与 Java 必须明确报告 `unsupported`，不得
伪称覆盖。

| V1 需求 / Scenario ID | 当前状态 | 必需底层依赖 | 可选依赖 | 实体与关系 | 未来查询接口 / L4 输出 | 排除条件与不确定性 | 复用关系 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `concurrency.non_atomic_incdec` | 未实现 | `events`、`sparse_cfg`、READ/WRITE、变量身份 | `sparse_dfg`、lockset、线程上下文 | Access、变量；`READS`、`WRITES`、`SAME_OBJECT`、`MAY_PARALLEL` | 显式 query-set 中的 Candidate，含读改写 span、同步事实、missing evidence | 原子 API、双方同锁保护、局部/线程局部对象、无法确定同一对象；无 `MAY_PARALLEL` 时至少 ambiguous | 复用 shared-state race 的对象/同步事实 |
| `concurrency.bool_flag_race` | 未实现 | `events`、`sparse_cfg`、READ/WRITE、变量身份 | `sparse_dfg`、线程上下文 | bool Access、flag；`READS`、`WRITES`、`SAME_OBJECT`、`MAY_PARALLEL` | Candidate 含 flag 读写、控制分支和来源 span | atomic/受锁 flag、局部/线程局部、只读、无法确定同一 flag；无并发证据为 ambiguous | 复用 shared-state race，增加 bool/type 和控制用途规则 |
| `concurrency.shared_state_race` | 部分已有：`race_condition` 为 FUNCTIONAL + DIAGNOSTIC | `events`、`sparse_cfg`、READ/WRITE、变量身份 | `sparse_dfg`、lockset、`concurrency_context` | 共享对象、Access、Lock、Thread Context；`READS/WRITES`、`GUARDED_BY`、`MAY_PARALLEL`、`HAPPENS_BEFORE` | 保持 `race_condition` 旧名称；结果增加可选事实/coverage，不改变默认 envelope | read/read、双方原子、可证明同锁保护、局部/线程局部；未建 `MAY_PARALLEL`、锁保护或别名时须列 missing evidence | 前两类共享同一 access/object/synchronization capability |
| `concurrency.lock_pairing` | 未实现 | `events`、`sparse_cfg`、LOCK/UNLOCK、锁身份 | `sparse_dfg`、RAII/guard binding、异常/退出语义 | Lock、Acquire、Release、Guard；`ACQUIRES`、`RELEASES`、`CONTROL_REACHES`、`SAME_LOCK` | 新 scenario 输出未配对 acquire/release Candidate；不是改写既有 `lock_order` | RAII、callee release、try-lock、goto/异常、不确定 lock alias、路径截断必须如实表达 | 复用 lock identity、控制可达和 L4 evidence bundle |
| `concurrency.lock_discipline` | 部分已有：`lock_order` 覆盖反向锁序与自死锁形状，诊断级 | `events`、`sparse_cfg`、LOCK/UNLOCK、锁身份 | `concurrency_context`、wait/signal、callee/blocking API contract | Lock、Acquire、Release、Blocking Call、Thread Context；`HOLDS`、`LOCK_ORDER`、`WAITS_FOR`、`MAY_PARALLEL` | 保持 `lock_order` 旧名称；锁内阻塞作为同一 V1 scenario 的独立 rule/coverage 子项 | recursive mutex、try-lock、RAII、锁别名、线程是否并发、阻塞 API contract 不足时不能提升结论 | 与 lock pairing 共用锁事件/identity；与 race 共用线程上下文 |

`lock_order` 的“锁内阻塞”规则可在同一 scenario 下独立注册和报告；不得为了拆分
规则而把 Owner 的第五类需求改成第六个 taxonomy 项。

## 4. 复用的 L2 Capability 合同

Planner 必须以现有 `CAPABILITY_CONTRACT` 为唯一注册事实来源。V1 requirements
保留其既有 `status`、`languages`、`depends_on`、`cost_class`、analyzer ID、版本及
freshness 语义；Profile 只引用 Capability ID，不复制这些字段。

| Capability | 当前状态 | V1 中的复用方式 |
| --- | --- | --- |
| `events` | 部分实现；C/C++ 语义事件 | LOCK/UNLOCK/ATOMIC、THREAD_SPAWN/JOIN 及一般事件来源 |
| `sparse_cfg` | 已实现；C/C++/Java | 路径、持锁区间、控制分支、结构/访问点 |
| `sparse_dfg` | 已实现；诊断级 | 对象身份、别名链、def-use；仅在场景需要时请求 |
| `defect` | 已实现；查询时能力 | 既有 `race_condition`、`lock_order` 的兼容入口与 Evidence Bundle |
| `concurrency_context` | 未来 capability，尚未注册 | 仅当实现需要可复用的 `MAY_PARALLEL`/HB/thread lifecycle facts 时新增；不能把它假写为已交付 |

## 5. Profile Registry 合同

`concurrency-v1` 是未来的可选 Profile 名称，不代表本 PR 实现了该配置面。其声明至少
包含：

```text
profile_id, profile_version, scenario_ids, requested_scope,
language_policy,
minimum_maturity, budgets, required_capabilities, optional_capabilities,
evidence_policy, query_set_version
```

要求：

- Profile 版本独立于 analyzer version，并在 L4 结果中可追溯。
- Profile 可请求五个 scenario；Planner 可因语言、成熟度、依赖或预算跳过其中一项。
- `partial`、`unsupported`、`stale`、`not_built` 必须逐 capability 与逐 scenario
  表达，不能用空候选伪装成功。
- 无 Profile 时，`analyze`、`defect`、CLI 和 MCP 保持现有参数、默认行为、query 名称
  与输出 envelope。
- 不得静默扩大既有 `defect --type all` 的集合或成本；未来 Profile 必须有显式
  query-set/version 语义。

## 6. Capability Planner V1 最小合同

Planner 是 L3 的确定性纯规划步骤；它不执行分析，也不改变 L1。输入为 Profile 或
显式 scenario/capability 请求、scope、语言、预算、现有缓存/freshness 和调用方允许的
成熟度。输出是稳定排序的执行计划。

每个 plan item 至少包含：

```text
capability_id, scenario_ids, analyzer_ids, scope, language, maturity,
dependencies, decision(build|reuse|query_only|skip), reason,
status(current|partial|unsupported|stale|not_built), cost_class
```

Planner V1 必须：

1. 递归展开 `depends_on`；
2. 按 `(capability, language, scope, analyzer version)` 去重；
3. 在计划前检查语言支持、成熟度和可选运行时；
4. 根据缓存版本、source/freshness 和依赖 freshness 选择 build/reuse/skip；
5. 对 registered-but-unimplemented、partial、unsupported、stale 和预算不足给出
   明确原因；
6. 对同一输入产生确定性 plan、稳定排序和可审计 plan ID；
7. 不因普通 task-context 或未指定 Profile 隐式请求高成本 capability；
8. 将 Profile/Scenario 选择与 L2 analyzer registration 分离，禁止第二套 registry。

## 7. L4 证据与成熟度

每个 Scenario Candidate 必须保留现有 Evidence Bundle 基础字段，并增加或复用：

- profile/version、scenario ID、实际执行的 capability/analyzer/version；
- source span、stable identity、resolved/ambiguous/unresolved；
- coverage（分析文件、访问/锁/路径、规则排除、截断）；
- freshness/staleness、build/reuse/skip 决策；
- `missing_evidence`：并行性、别名、锁保护、RAII、递归锁、try-lock、阻塞 API
  contract、路径/预算等；
- grade/level/provenance。

Candidate、证据解析状态和人工/运行时 Verified Finding 严格分离。V1 不授权自动确认
漏洞、自动修复或改变查询等级。

## 8. 兼容性与 Non-goals

兼容性约束：L1 默认 index 零新增检测成本；既有 L1 ID/edge 语义、CLI/MCP 默认语义、
`race_condition`、`lock_order` 及现有 query contract 全部保留。新能力只能通过显式
Profile 或显式 query-set 请求进入，且必须 fail closed。

Non-goals：

- 不实现 Planner、Profile registry、并发 analyzer、query 或 CLI/MCP 参数；
- 不修改 ProvenLattice 产品代码、schema、默认扫描范围、发布或版本；
- 不新增 atomicity/order/TOCTOU 作为本轮漏洞类别；
- 不运行大规模实验、不作性能或正式资格声明；
- 不建立第二套 Graph、Registry 或架构层。

## 9. 最小开发路线（后续独立 Issue）

1. Planner V1：仅实现 registry 驱动的确定性规划、状态表达与单元测试，默认无行为变化；
2. 并发共享事实：按证据需要决定是否引入 `concurrency_context`；
3. 在保持旧入口的前提下加强 `race_condition` 与 `lock_order`；
4. 分别实现非原子增减、bool flag、共享变量、锁未配对、锁顺序／锁内阻塞 scenario；
5. 最后才实现显式 `concurrency-v1` Profile 的 CLI/MCP 接入和端到端校验。

每一步都需单独的 Owner 授权、Issue、实现 PR、独立 Review 和相应正反例；本需求 PR
不构成上述实现授权。

# ProvenLattice V1.4 Capability Matrix

> 当前能力状态统一入口(2026-10-13,V1.4)
> 资格等级:FUNCTIONAL_VALIDATED > FUNCTIONAL + DIAGNOSTIC > SMOKE + DIAGNOSTIC
> 全部缺陷查询输出为 Candidate,受 `local-only, diagnostic` 分析范围约束。

## L1 Foundation / Knowledge

| 能力 | 来源 | 语言 | 默认 | 状态 | 验证 | 典型任务 | 限制 |
|---|---|---|---|---|---|---|---|
| Foundation Graph | V1.3 | Python/C/C++ | 默认 | ✅ implemented | RQ1/RQ2/SQI formal | 代码理解/定位/影响 | S3+ 未测 |
| Three-state References | V1.3 | Python/C/C++ | 默认 | ✅ | RQ1 | 引用追溯 | — |
| Impact Analysis | V1.3 | Python/C/C++ | 默认 | ✅ | RQ2 | 影响面分析 | — |
| Knowledge Layer | V1.3 | Markdown | 默认 | ✅ | SQI | 需求→代码 | — |

## L2 Agent Analysis (V1.3)

| 能力 | 来源 | 语言 | 默认 | 状态 | 验证 | 典型任务 | 限制 |
|---|---|---|---|---|---|---|---|
| Python AST | V1.3 | Python | 按需 | ✅ QUALIFIED | D2 | 结构理解 | — |
| Python CFG | V1.3 | Python | 按需 | ✅ QUALIFIED | D4 | 控制流分析 | 无异常边 |
| C normalized AST | V1.3 | C (.c/.h) | 按需 | ✅ diagnostic | A1 | 结构理解 | C++ unsupported |
| C CFG + 短路 | V1.3 | C (.c/.h) | 按需 | ✅ diagnostic | A2/A2.1 | 控制流/短路 | 单行 for 已修复 |
| C 调用语义 | V1.3 | C (.c/.h) | 默认 | ✅ diagnostic | A3 | direct/indirect 分类 | 仅 .c 文件 |

## L2 Inspection Analysis (PR1 → V1.4)

| 能力 | 来源 | 语言 | 默认 | 状态 | 验证 | 典型任务 | 限制 |
|---|---|---|---|---|---|---|---|
| Semantic Events (15 类) | PR1 | C/C++ | 按需 | ✅ diagnostic | I1-A | 操作粒度事实 | Python 未验证 |
| Sparse CFG | PR1 | C/C++ | 按需 | ✅ diagnostic | I1-B | 事件可达性 | goto 不建模 |
| Sparse DFG | PR1 | C/C++ | 按需 | ✅ diagnostic | I1-C | def→use 链 | 无 SSA |
| Ownership Contracts | PR1 | C/C++ | 按需 | ✅ diagnostic | I2-A | 所有权规则 | TOML 数据待填充 |
| double_free | PR1 | C/C++ | 按需 | ✅ **FUNCTIONAL_VALIDATED** | I2-A | 连续释放检测 | — |
| use_after_free | PR1 | C/C++ | 按需 | ✅ **FUNCTIONAL_VALIDATED** | I2-B1 | 释放后使用 | 别名精度有限 |
| null_flow | PR1 | C/C++ | 按需 | ✅ FUNCTIONAL + DIAGNOSTIC | I2-A | NULL→deref | `if(p){*p=1}` FP |
| resource_lifetime | PR1 | C/C++ | 按需 | ✅ FUNCTIONAL + DIAGNOSTIC | overnight | 泄漏检测 | 释放包装器不可见 |
| lock_order | PR1 | C/C++ | 按需 | ✅ FUNCTIONAL + DIAGNOSTIC | overnight | 锁序反转 | 无法证明并发 |
| race_condition | PR1 | C/C++ | 按需 | ✅ FUNCTIONAL + DIAGNOSTIC | overnight | 共享变量竞态 | ambiguous-only |
| error_handling | PR1 | C/C++ | 按需 | ◐ SMOKE + DIAGNOSTIC | overnight | 未检查返回值 | 精度受 API contract 限制 |
| taint_path | PR1 | C/C++ | 按需 | ◐ SMOKE + DIAGNOSTIC | overnight | source→sink | 4 source/3 sink 仅 |

## L3 Task Services

| 能力 | 来源 | 语言 | 默认 | 状态 | 验证 | 典型任务 | 限制 |
|---|---|---|---|---|---|---|---|
| task-context-v0 | V1.3 | All | 按需 | ✅ | D9-C10 | Agent 上下文 | — |
| Defect Query 入口 | V1.4 | C/C++ | 按需 | ✅ diagnostic | I2-A | 缺陷候选查询 | 需上游链 |

## L4 Evidence & Results

| 能力 | 来源 | 默认 | 状态 | 验证 | 说明 |
|---|---|---|---|---|---|
| Core Provenance | V1.3 | 默认 | ✅ | SQI | fact_id/evidence_ids/span |
| Evidence Bundle | PR1 | 按需 | ✅ diagnostic | I2-A | Candidate ≠ Verified |
| Three-state Reachability | V1.4 | 按需 | ✅ | I1C-R1 | true/false/unknown |

## L5 Exposure

| 能力 | 来源 | 状态 | 说明 |
|---|---|---|---|
| CLI | V1.3 | ✅ | 全命令面含 defect |
| MCP | V1.3 | ✅ | 透传桥(含 defect) |
| Plugin/SDK/REST | — | ⬜ | future candidate |

## Integration Engineering (V1.4)

| 能力 | 来源 | 状态 | 说明 |
|---|---|---|---|
| Capability Contract | V1.4 | ✅ | 8 查询 + 3 analyzer 统一注册 |
| Dependency Freshness | V1.4 | ✅ | `dependency_staleness()` 统一规则 |
| Composite PK Migration | V1.4 | ✅ | 旧库自动迁移,8 项测试 |
| Three-state Evidence | V1.4 | ✅ | unknown 不当作 false |
| Query Budget | V1.4 | ✅ | max_candidates/max_paths/max_hops + truncated |
| Grade/Level Provenance | V1.4 | ✅ | 每结果标注 `local-only, diagnostic` |

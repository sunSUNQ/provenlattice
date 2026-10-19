# ProvenLattice 1.5.0 Capability Matrix

> 当前能力状态统一入口(2026-10-19,1.5.0 — Java Public Beta)
> 资格等级:FUNCTIONAL_VALIDATED > FUNCTIONAL + DIAGNOSTIC > SMOKE + DIAGNOSTIC
> 全部缺陷查询输出为 Candidate,受 `local-only, diagnostic` 分析范围约束。

## L1 Foundation / Knowledge

| 能力 | 来源 | 语言 | 默认 | 状态 | 验证 | 典型任务 | 限制 |
|---|---|---|---|---|---|---|---|
| Foundation Graph | V1.3 | Python/C/C++ | 默认 | ✅ implemented | RQ1/RQ2/SQI formal | 代码理解/定位/影响 | S3+ 未测 |
| Foundation Graph (Java) | PL-JAVA-P0-P1 (T1–T3) | Java (.java) | 默认 | ✅ implemented (FUNCTIONAL + DIAGNOSTIC) | 21 用例 + 479 全量回归 + py/cpp 四表金样（2026-10-15，1.5.0）；RQ1 formal 未执行 | Java 代码理解/定位（tree-sitter 语法事实） | 三态精度边界见下；性能基准未测 |
| Three-state References | V1.3 | Python/C/C++/Java | 默认 | ✅ | RQ1 | 引用追溯 | Java 侧 R1 收紧语义见下 |
| Impact Analysis | V1.3 | Python/C/C++ | 默认 | ✅ | RQ2 | 影响面分析 | — |
| Knowledge Layer | V1.3 | Markdown | 默认 | ✅ | SQI | 需求→代码 | — |

> **Java（P0，Foundation Graph 阶段）能力边界（2026-10-15）**：
>
> - **节点**（全部复用冻结 kind，metadata 判别）：`Class`（class/enum/record）、`Interface`（interface/annotation）、`Method`（method/constructor/field/enum_constant）；包声明不建节点（存于 File `metadata["java_package"]`）。
> - **边**：`DEFINES`、`CONTAINS`、`IMPORTS`、`CALLS`、`REFERENCES`、`IMPLEMENTS`（extends/implements/throws，`metadata["java_relation"]` 区分）。
> - **resolved**（确定性绑定）：单类型/静态 import 路径（confidence 1.0）、限定名（0.99）、同文件符号（0.98）、import 别名（0.95）、全局唯一名（0.75）。
> - **ambiguous**（如实保留候选）：方法重载调用、跨包同名、通配 import 下的同名类型、`this(...)` 显式构造调用。
> - **unresolved**（不猜测）：间接形状（`super.x()` / `super()` / 复杂 receiver / `Type::method`，strategy=`indirect_call_shape`）、外部类型（JDK/第三方，如 `java.io.Serializable`）、通配 import 本身、隐式默认构造。
> - **提取 gap（已记录限制，非错误映射）**：record 组件、注解元素（annotation_type_element）、匿名类体内容、隐式默认构造不产出符号；局部变量/参数/lambda 参数/模式变量不产出引用（消除错误绑定面）。
> - **明确不等同于（L1 语法层）**：方法重载判定、继承层级解析由**可选 JDT Analyzer** 提供（见 L2 表 Semantic Java 行）；完整 CFG/DFG、任何缺陷查询不属于 L1。默认 index 零高级分析产物。
> - **已知精度边界（T8 评审发现 → PL-JAVA-P1 已修复，2026-10-15）**：~~same-file 阶梯按名绑定不区分 Java 类型/值命名空间~~ **已修复**：resolver 对 `type_usage`/`object_creation` 引用（metadata 门控，仅 Java 发射）在 same-file 与全局唯一阶梯排除可调用 kind（Function/Method）；同文件方法不再捕获类型目标（回归用例 java22/23/24）。Python 侧共享机制经 CALLS 显形（注解引用不发射），行为已用 pin 测试固化、修复需独立决策；C/C++ 不发射 type_usage，守卫零触发。`CALL_KIND_VERSION` 当前 = **3**（1→2：type-target 守卫；2→3：R1 demote；旧库在下次实际重建时全量重解析收敛——既有缓存机制边界）。

## L2 Agent Analysis (V1.3)

| 能力 | 来源 | 语言 | 默认 | 状态 | 验证 | 典型任务 | 限制 |
|---|---|---|---|---|---|---|---|
| Python AST | V1.3 | Python | 按需 | ✅ QUALIFIED | D2 | 结构理解 | — |
| Python CFG | V1.3 | Python | 按需 | ✅ QUALIFIED | D4 | 控制流分析 | 无异常边 |
| C normalized AST | V1.3 | C (.c/.h) | 按需 | ✅ diagnostic | A1 | 结构理解 | C++ unsupported |
| C CFG + 短路 | V1.3 | C (.c/.h) | 按需 | ✅ diagnostic | A2/A2.1 | 控制流/短路 | 单行 for 已修复 |
| C 调用语义 | V1.3 | C (.c/.h) | 默认 | ✅ diagnostic | A3 | direct/indirect 分类 | 仅 .c 文件 |
| **Semantic Java (Optional JDT)** | PL-JAVA-P2-D | Java (.java) | 按需（CLI `java-semantic`） | ✅ implemented (diagnostic) | P2-B/P2-D/P2-E：21 gold 20+1 CORRECT、8/8 历史错误样本修正、168 冲突抽样 0 JDT 错误、479 全量回归（1.5.0） | 跨文件精确绑定/重载消歧/继承层级（query-time 审计视图） | 需用户自备 JDK 21 + JDT classpath（Windows/JDK21 已验证，**Linux JDT NOT_VERIFIED**）；recovered 绑定过滤；query-time 不持久化；JDK 其他组合未测 |

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

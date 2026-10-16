# P2-A 设计评审：L1 错误绑定安全收紧（Demote）— 仅供人工批准，未实施

**状态：`P2A_DESIGN_READY_FOR_APPROVAL`** · 日期 2026-10-15 · 输入 HEAD f713ec2
**性质**：设计文档；本任务未修改任何 L1 绑定逻辑（约束遵守）。

---

## 1. 问题陈述（实测证据）

真实仓库人工审计（60 样本）：**8/60 错误确定性绑定**，全部集中于启发式阶梯，
根因单一——**receiver 声明类型不被语法阶梯追踪**：

| # | 形态 | L1 阶梯 | 错绑目标 | 真实目标 |
|---|---|---|---|---|
| 1 | `MINUTES.toMillis`（静态导入枚举常量） | unique 0.75 | ClockSource.toMillis | TimeUnit.toMillis |
| 2 | `current.getPassword`（lambda 参数） | same-file 0.98 | HikariConfig.getPassword | Credentials.getPassword |
| 3 | `sharedList.stream` | unique 0.75 | StringAppender.stream | List.stream |
| 4 | `field.get` | unique 0.75 | FastList.get | Field.get |
| 5 | `members.get` | same-file 0.98 | JsonObject.get | LinkedTreeMap.get |
| 6 | `map.put` | same-file 0.98 | 嵌套测试类.put | Map.put |
| 7 | `"1".repeat` | unique 0.75 | JsonReaderTest.repeat | String.repeat |
| 8 | `target.add` | same-file 0.98 | 嵌套测试类.add | List.add |

影响面（readiness-ladder-measurement.json）：启发层占 resolved CALLS 的
**79.0%（hikaricp）/ 75.0%（gson）**。JDT 独立解析对 8/8 样本全部 CORRECT
（P2-B phase4-historical-sites.json），故收紧后的召回损失可由 P2-D 精确层承接。

## 2. CALLS 阶梯现状盘点

| 阶梯 | 置信 | receiver 语义 | 现状判定 |
|---|---|---|---|
| import/qualified/module | 1.0/0.99/1.0 | 类型/FQN 显式 | **保持不变**（0 实测错误） |
| same-file | 0.98 | 隐式 `this` 或 receiver 未知 | **按 receiver_shape 分流**（见 §3） |
| unique 全局 | 0.75 | receiver 未知（实例调用）或静态 FQN 已改写 | identifier-receiver 实例调用 → **demote** |
| indirect veto | — | 复杂 receiver / `super` / 方法引用 | 保持不变 |
| P1 type-target 守卫 | — | 类型目标 | 保持不变 |

## 3. 安全规则设计（Demote 规则矩阵）

**Demote 规则 R1**：`CALLS` 引用满足以下全部条件时，绑定结果由 resolved 降为
**ambiguous（候选完整保留）**：
- `metadata["receiver_shape"] == "identifier"`（receiver 为普通标识符：局部/参数/字段
  变量名——类型未知）；
- 且绑定来源 ∈ {unique_symbol_resolution(0.75), same_file_resolution(0.98)}。

**R2（保持 resolved）**：`receiver_shape ∈ {"this", "fqn", "class_static"}` 的调用
（`this.foo()`、FQN 静态调用、经 import 别名改写的静态调用）——T9-B/审计中此类
零错误；裸调用（无 receiver，即隐式 this）同样保持（Java 名字解析中同类方法优先，
审计无反例）。

**R3（保持不变）**：REFERENCES/IMPLEMENTS 类、type-target P1 守卫、间接 veto、
所有精确层（≥0.99）。

**为什么 ambiguous 而非 unresolved**：候选确实存在（同名方法集合），三态语义中
"有候选未选中"= ambiguous；unresolved 表示无候选，会丢失证据。候选集与原
strategy/confidence 完整保留在 raw_references 中，来源信息不损失。

**错误区分保障**：同名方法间不互相错绑——demote 后不再有"选中"，只暴露候选集；
唯一保留的精确层要求显式证据（import/限定名/this/静态改写）。

### receiver_shape 元数据（提取器侧，最小增量）
`parsing/java.py` 的 `_call` 已识别 receiver 形状（this/super/标识符链/复杂表达式/
无 receiver），新增输出：
- `"identifier"`：object 为普通标识符（含 field_access 链首段为标识符）；
- `"this"` / `"fqn"`（object 为 scoped/qualified 链）/ `"complex"`（含 `(`、`[` 或 super）；
- 无 receiver → `"implicit_this"`。
提取器改动为**纯标注**（不改变任何现有 emit 行为），Python/C/C++ 提取器零改动。

## 4. 八个决策点

1. **哪些规则 demote**：仅 R1（identifier-receiver × {0.75, 0.98}）。
2. **哪些保持**：R2/R3（见 §3）；`this`/隐式 this/精确层/全部 veto 逻辑。
3. **避免同名错绑**：demote 后无"选中"即无错绑；精确层仅由显式证据触发（import/
   限定名/this），与 receiver 类型推断无关。
4. **ambiguous 候选表达**：RawReference.candidate_symbols 保留原候选集；status=
   ambiguous；resolution_strategy 保留原阶梯名 + metadata 增加
   `{"demoted": true, "demote_reason": "receiver_type_unknown"}`；无 resolved 边
   （调用图边消失，查询面经 raw_references 仍可见候选）。
5. **与 JDT 精确结果合并**（P2-D，独立 feature）：JDT 行以
   provenance=`semantic:jdt-v1` 独立存在，不写 raw_references 主表（analysis 表）；
   查询面按 provenance 分层：L1 ambiguous 行 + JDT CORRECT 绑定并列呈现；
   recovered=true 的 JDT 行不得覆盖任何 L1 行。
6. **JDT 缺失/失败/禁用**：L1 demote 结果独立成立（ambiguous 如实呈现）；
   fail-closed 无降级污染——这要求接受"过渡期 CALLS resolved 下降"为**契约内
   如实状态**而非缺陷（决策点 10 的联动前提）。
7. **影响量化**：demote 直接影响启发层（hikaricp 79.0% / gson 75.0% 的 resolved
   CALLS）；identifier-receiver 子集需实施时以 receiver_shape 元数据精确测量
   （本设计阶段禁止把启发式命中数当作正确召回数——影响面 = 上界）。参考：审计
   CALLS 样本错误率 8/60=13.3%，若样本代表性成立，demote 消除约数百条错误边/
   库，代价是同名候选边的显式化。
8. **Python/C/C++ 与 MCP/CLI 影响**：demote 由 `receiver_shape` 门控——仅 Java
   提取器发射该值，旧语言零变化（P1 同模式）；CLI/MCP 查询面语言无关，ambiguous
   行为与既有三态展示一致，无 schema 变化。
9. **回退**：单 commit revert + `CALL_KIND_VERSION` 3→2（既有机制自动恢复 v2 结果）。
10. **联动交付保障**：P2-A 与 P2-D 的 capability 登记合并为一个发布单元；
    P2-A 的 commit 不得独立于 P2-D 进入 release 分支（发布注记绑定）；
    过渡期文档（capability-matrix）先行标注。

## 5. 替代方案与取舍

| 方案 | 内容 | 取舍 |
|---|---|---|
| **A1（推荐，收窄版）** | 仅 identifier-receiver 实例调用 demote（§3 R1） | 错误消除最彻底（8/8 样本覆盖）；召回损失由 P2-D 承接；过渡期 resolved 下降需接受 |
| A2 | 仅 demote 0.75 unique 层，保留 0.98 same-file | 召回损失较小，但审计 4/8 错误来自 0.98（#2/5/6/8）——错误残留一半，不满足 Wrong-Resolution 目标 |
| A3 | 状态不变，仅消费契约收紧（0.75/0.98=Candidate） | 零代码风险，但审计证明错误边仍流入 callers/callees 图查询，用户仍会采信 |

A2/A3 均无法达成"已覆盖场景 Wrong-Resolution=0"，故推荐 A1。A1 风险 = 过渡期
resolved 指标下降——这是**如实状态**（错误边本不应为 resolved）。

## 6. 实施清单（获批后）
1. parsing/java.py：receiver_shape 标注（~10 行）；
2. resolver.py：R1 规则（~8 行）+ CALL_KIND_VERSION 3；
3. 测试：8 真实错误样本最小 fixture 化 + java01–31 回归 + 金样 + 影响面测量入库；
4. capability-matrix 过渡期标注。

## 7. 人工决策清单
- [ ] 是否批准 demote（A1 收窄版）？
- [ ] 是否接受 P2-A/P2-D 联动交付（单 commit 发布单元 + 过渡期 resolved 下降）？
- [ ] JDT 禁用/失败时行为确认：L1 ambiguous 如实呈现，不回退到启发式 resolved？
- [ ] P2-B 内存预算（Xmx1g / RSS≤1.6GB / jgit≤15s）是否批准？

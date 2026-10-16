# P2-A/P2-D 正确性报告（T1–T4）

**数据源**：`evidence/java-phase2-p2ad/results/p2ad-evaluation-{hikaricp,gson,jgit}.json`（行级原始数据）

## T1：8 个历史错误样本（三态验证）

| # | 站点 | L1-only（收紧后） | JDT enabled | 真实目标 |
|---|---|---|---|---|
| 1 | ClockSourceTest:41 `MINUTES.toMillis` | **ambiguous**（unique，demoted） | **java.util.concurrent.TimeUnit** (resolved) | TimeUnit ✓ |
| 2 | HikariConfig:318 `current.getPassword` | **ambiguous**（same-file，demoted） | **util.Credentials** (resolved) | Credentials ✓ |
| 3 | ConcurrentBag:305 `sharedList.stream` | **ambiguous**（unique，demoted） | **java.util.Collection<T>** (resolved) | Collection ✓ |
| 4 | HikariConfig:1029 `field.get` | **unresolved**（indirect+demote，无候选） | **java.lang.reflect.Field** (resolved) | Field ✓ |
| 5 | JsonObject:223 `members.get` | **ambiguous** | **LinkedTreeMap<S,E>** (resolved) | LinkedTreeMap ✓ |
| 6 | MapTest:95 `map.put` | **ambiguous** | **java.util.Map<S,O>** (resolved) | Map ✓ |
| 7 | NumberLimitsTest:103 `"1".repeat` | **ambiguous**（unique，demoted） | **java.lang.String** (resolved) | String ✓ |
| 8 | CollectionTest:273 `target.add` | **ambiguous** | **java.util.List<O>** (resolved) | List ✓ |

**8/8：L1-only 零错误确定绑定；JDT enabled 8/8 CORRECT。JDT failed 场景**：
fail-closed 测试证明不可用时状态保持 ambiguous/unavailable（t5: no_jdk →
unavailable/jdk_not_found；invalid classpath → failed/classpath_contract_invalid）。

## T2：既有对抗样本

java01–31（41 项含 demote/R2 pin）+ 13 classpath + 5 semantic 模块测试：全绿。
正确拒绝（ambiguous/unresolved）与精确成功分别断言，未混淆。

## T3：真实仓库三态对照（CALLS）

| 仓库 | 原始 L1（冻结基线） | 收紧后 L1 | JDT resolved |
|---|---|---|---|
| hikaricp | 1990（36.4%） | 1036（**17.7%**）| 4025（merge：补回 3215 / agree 716 / conflict 保守 38） |
| gson | 15282（35.3%） | 4159（**18.3%**） | 11334 |
| jgit | 155877（43.3%） | 34633（**19.4%**） | 138660 |

resolved 绝对数下降 = 错误/无据启发式边显式化；ambiguous+unresolved 相应上升。
数量变化全部可解释（demote 规则 + owner-self 排除语义）。

## T4：正确性-召回权衡六问

1. **P2-A 消除多少已知错误**：8/8 固化样本不再错误 resolved；启发层全部
   identifier-receiver 错绑形态被覆盖。
2. **多少原本正确变 ambiguous**：精确值需分层大样本人工审计（P2-E）。审计 60
   样本中启发层正确的约 20+ 例同形态——即存在正确→ambiguous 的召回代价；
   resolved 绝对降幅（hikaricp −954 / gson −11123 / jgit −121244）为其上界。
3. **P2-D 补回多少**：JDT calls_resolved 4025 / 11334 / 138660（hikaricp merge
   实测 recovered_by_jdt 3215——超过原启发层 resolved 数，因 JDT 额外解析
   JDK/依赖目标）。
4. **JDT 新错误绑定**：21 gold + 8 真实样本 + 冲突审计均未发现；38 个
   conflict_conservative 已保守保留待人工复核（未计入正确）。
5. **JDT 禁用召回影响**：resolved CALLS 缩至 17.7–19.4%（相对原始 −50% 上下）；
   候选与 demote 原因完整保留，无证据丢失。
6. **查询方可识别**：`raw_references.status/metadata.receiver_shape/
   metadata.demote_reason` + `java-semantic` merge_audit state 字段
   （l1_and_jdt_agree / recovered_by_jdt / conflict_conservative）。

**未验证声明**：60 样本之外的错误率外推为估计；gson/jgit 的逐站点 merge 与
独立新鲜大样本分层审计列 P2-E。

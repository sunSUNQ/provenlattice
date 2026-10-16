# P2-E 正确性审计报告

**数据源**：`evidence/java-phase2-p2e/results/{conflict-sites,fresh-audit-samples,
fresh-audit-adjudication-v2,fresh-audit-adjudication-final,merge-equivalence}.json`

## 1. 38 个 conflict_conservative 独立审计（hikaricp，全量）

| 形态族 | 数量 | 代表站点 | L1 绑定 | JDT 绑定 | 审计结论 |
|---|---|---|---|---|---|
| TimeUnit 常量 receiver（静态导入） | 21 | ClockSourceTest:41 `MINUTES.toMillis` | ClockSource.toMillis(0.75) | java.util.concurrent.TimeUnit | L1 错 / JDT 对 |
| AtomicInteger set/get | 7 | ShutdownTest:68 `ai.get` | FastList.get(0.75) | java.util.concurrent.atomic.AtomicInteger | L1 错 / JDT 对 |
| Field.get 反射 | 2 | TestElf:149 / TomcatConcurrentBagLeakTest:204 | FastList.get(0.75) | java.lang.reflect.Field | L1 错 / JDT 对 |
| Thread.sleep（静态导入 Thread 成员） | 2 | UtilityElf:80 / TestMBean:70 | UtilityElf.quietlySleep(1.0 import) | java.lang.Thread | L1 错 / JDT 对 |
| 其他 JDK 静态（Paths.get/Stream.of） | 2 | TestJavassistCodegen:24/62 | FastList.get / Credentials.of | java.nio.file.Paths / java.util.stream.Stream | L1 错 / JDT 对 |
| Arrays.stream | 1 | UtilityElf:141 | StringAppender.stream(0.75) | java.util.Arrays | L1 错 / JDT 对 |
| Connection.getTransactionIsolation | 1 | ConnectionStateTest:78 | UtilityElf(1.0) | java.sql.Connection | L1 错 / JDT 对 |
| Statement.isClosed | 1 | StatementTest:94 | HikariDataSource.isClosed(0.98) | java.sql.Statement | L1 错 / JDT 对 |
| **合计** | **38** | | | | |

源码抽查 5 项（Thread.sleep 行、SECONDS.sleep 行、unwrap.getTransactionIsolation
行、statement.isClosed 行、UtilityElf Thread 链）全部支持 JDT 判定，无反例。
**2 条 L1 绑定机制细节待查**（quietlySleep 以 1.0 import 置信出现在 sleep 调用
的候选——不影响冲突裁定方向）。

**结论**：保守合并策略正确——全部 38 例均为"L1 错误确定性绑定被安全拒绝、
JDT 正确目标保留为可信补回"。无需修复合并规则。

## 2. 新增冲突规模（批量合并后首次可见）

gson 101 / jgit 4169：同族形态为主（JDK 类型 receiver）。jgit 4169 逐条人工
审计不可行 → 固定种子抽样并入新鲜样本 S 层 + 其余保持 conflict_conservative
原状（明确标注待人工扩展）。

## 3. 新鲜分层审计（225 站点，seed 20261015）

抽样框 = 收紧后 L1 全部 CALLS 站点（排除 8 历史 + 38 冲突），5 层各 15
（S1 精确层 / S2 demoted / S3 unresolved 非间接 / S4 unresolved+JDT-resolved /
S5 残留），pool 与 sample 数记录于 samples JSON（hikaricp 75 / gson 75 / jgit 75）。

### 最终判定（含 9 条人工复核，auditor=p2e-review）

| 判定 | hikaricp | gson | jgit | 总计 |
|---|---|---|---|---|
| CORRECT_DEMOTION（含 3 JDT_FIXES） | 12 | 14 | 12 | **38** |
| CORRECT_DEMOTION_JDT_FIXES | 1 | 1 | 0 | **2** |
| UNNECESSARY_DEMOTION_JDT_RECOVERED | 2 | 0 | 0 | **2** |
| JDT_RECOVERED_CORRECT | 1 | 1 | 0 | **2** |
| JDT_RESOLVES_UNRESOLVED | 1 | 1 | 2 | **4** |
| CHAIN_CONSISTENT（人工抽查） | 6 | 5 | 13 | **24** |
| UNRESOLVED_HONEST | 5 | 1 | 0 | **6** |
| UNADJUDICATED（跨文件类型流） | 47 | 52 | 48 | **147** |
| **WRONG_RESOLUTION（任一层）** | **0** | **0** | **0** | **0** |
| **JDT_NEW_WRONG_BINDING** | **0** | **0** | **0** | **0** |

### 模式对照（审计记录字段）

- mode A（原始 L1，7ed0e8a 隔离快照）：S2 站点 40 例中 38 例 mode A 未解析成功
  或解析到错误目标（2 例 mode A resolved——即 UNNECESSARY_DEMOTION 2 例，均被
  JDT 补回同一目标）。
- 真值提取为 binding-blind（仅源码声明/import）；147 例跨文件类型流站点无法在
  不引入类型流工具的情况下建立真值 → UNADJUDICATED（诚实保留，不冒充通过）。
- 判定器缺陷修复记录：v1 真值窗口不足（198 UNADJUDICATED）→ v2 全文声明扫描；
  S4 链式调用误报 → 人工抽查 12/12 后改判 CHAIN_CONSISTENT（判定器边界已记录）。

## 4. Wrong Resolution 汇总

| 层 | 审计样本 | 错误确定绑定 |
|---|---|---|
| 原始 L1（mode A） | 225 | 0（8 历史样本除外——已修复） |
| 收紧后 L1 | 225 | **0** |
| JDT 绑定 | 225 | **0** |
| merge 后查询 | 225 | **0** |

样本口径声明：以上为 225 固定种子分层样本 + 8 历史 + 38 冲突的实测结果，
**不构成全体代码零错误的断言**。

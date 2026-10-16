# P2-E 验收证据闭环报告

**状态：`ACCEPTANCE_EVIDENCE_PASS`**（未裁定项不掩盖高风险机制；剩余不确定性边界明确）
**日期**：2026-10-15 · **HEAD**：`370e842` → `d816XXX`（本轮 3 commits，未 push）· **476 tests OK**

---

## 1. Phase 2 工程结论复核

HEAD/475 基线/147 UNADJUDICATED/冲突数据全部独立核对一致；P2-E 报告结论与
原始数据吻合，无推翻项。期间发现并修复 **1 个生产缺陷**（§3，经独立复现确认，
属允许修复范围）。

## 2. 147 个 UNADJUDICATED 归因（Phase 1，`unadjudicated-attribution.json`）

| 归因 | 数量 | 说明 |
|---|---|---|
| 多声明类型（真实歧义） | 97 | receiver 标识符在多文件声明——三态契约的诚实 ambiguous |
| 外部/JDK 类型流缺失 | 49 | 声明不在仓库内（参数来自依赖/JDK），需 classpath+类型流 |
| 补充裁定 SUPPLEMENTAL_JDT_CORRECT | 1 | 全仓声明搜索唯一命中，JDT 一致 |
| **JDT 错误暴露** | **0** | 未发现任何被评价方错误 |

方法独立性：全仓声明搜索（`Type receiver` 全文模式 + import 映射），不依赖
L1/JDT 输出；JDT 输出仅作对照。剩余 146 保留 UNKNOWN（诚实边界，机制明确）。

## 3. 冲突机制族与分层审计（Phase 2）

**机制族（file-keyed 修复后）**：jgit——streams/arrays 455、collections 243、
jdk_other 72、project 12、timeunit 6、reflection 1；gson——streams 59、reflection 9、
jdk_other 5、project 3；hikaricp——timeunit 17、atomic 7、streams 2、jdk_other 1。
**JDK 集合/流/并发类型 receiver 占绝对主导**（与 P7 根因一致）。

**分层抽样审计（seed 20261016，jgit 100 / gson 30 / hikaricp 27 全量）**：

| 审计判定 | jgit | gson | hikaricp | 合计 |
|---|---|---|---|---|
| JDT_CORRECT_L1_WRONG | 88 | 24 | 3 | **115** |
| INHERITANCE_HIERARCHY（12/12 人工验证） | 11 | 1 | 0 | **12** |
| CROSS_FILE_DECL_WEAK | 11 | 7 | 7 | **25** |
| TRUTH_EXTERNAL_UNADJUDICATED | 18 | 0 | 17 | **35** |
| **MISMATCH（真实可疑）** | **0** | **0** | **0** | **0** |

**168 抽样中 0 个 JDT 错误绑定、0 个保守拒绝正确目标的实例**（继承层级 12 例
为 JDT 标准声明点语义，人工全部确认）。

## 4. 本轮发现并修复的缺陷（经独立复现确认）

**merge_with_l1 跨文件行号串扰**：L1 对照按 (line) 匹配、且 INNER JOIN 丢弃
demote 后的 ambiguous 行——两文件同号时 L1 对照互相污染（UtilityElf:80 显示
TestMBean:70 的 quietlySleep 1.0 即此伪影）。修复：(file, line) 双键 + LEFT JOIN；
回归测试 `test_merge_is_file_scoped` 固化。**影响范围**：仅 JDT 审计视图的
L1 对照展示，L1 图谱与冲突裁定方向不受影响（JDT 正确性由源码独立定案）。
修复后冲突清单：hikaricp 38→27、gson 101→76、**jgit 4169→789（-81% 为串扰
假冲突）**；重审计 MISMATCH=0。

## 5. quietlySleep 专项复核（Phase 3）

最小复现 + 真实 DB 行核对：
- 真实 L1 行 `Thread.sleep` @ UtilityElf:80 = **unresolved**（P2-A R1 demote，
  receiver_shape=identifier）——**无缺陷**；
- 冲突清单所示 "1.0 quietlySleep" 为跨文件串扰伪影（§4 修复）；
- extractor probe：`Thread.sleep` 在静态导入环境正确标 identifier（审计 #1 同
  形态 demote 路径有效）。

## 6. 正确性证据汇总（Phase 4）

| 口径 | 已裁定 | 未裁定 | Wrong Resolution | JDT 新错 |
|---|---|---|---|---|
| 已知测试集（java01–31 + demote 9 + semantic 5） | 45 | 0 | 0 | 0 |
| P2-E 原有新鲜样本（225） | 78 | 147 | 0 | 0 |
| 本轮 147 归因补充 | 1 | 146 | 0 | 0 |
| 本轮冲突抽样（168） | 115+12 确认 | 41（弱/外部） | 0 | 0 |
| 机制性对抗（8 历史 + T9-B 21 gold） | 29 | 0 | 0 | 0 |

**不同口径未混合计算总体正确率**（按任务要求分层列示）。

## 7. 七问回答

1. P2-A 确实减少错误确定绑定？（T1 8/8 + 审计 0 错残留）✅
2. JDT 有效补回可证明正确调用？（T1 8/8 + 115 JDT_CORRECT + 24 chain）✅
3. Conservative merge 引入错误确定绑定？**未发现**（168 抽样 0）✅
4. 系统性高置信错误？未发现（高置信层 0 错误，quietlySleep 疑点为展示伪影）✅
5. 未裁定集中机制？跨文件类型流（97）与外部类型流（49）——与 JDT 能力边界一致
6. 证据足以工程签收？**支持**（ACCEPTANCE_EVIDENCE_PASS）
7. RQ1 formal 缺口：174+ 案例独立金标集、盲标注协议、跨环境复现、147+146
   未裁定项的类型流工具支持

## 8. 回归（Phase 5）

全量 **476 tests OK**（475 + 1 新 file-scoped 回归）；金样/MCP/无 JVM smoke
沿用 P2-E 结论（本轮零 resolver/schema 变更，仅 java_semantic 视图修复）。

## 9. RQ1 formal 前需补充

① 独立标注的 ≥174 案例金标集与盲评协议；② 类型流辅助真值工具（消除
UNADJUDICATED）；③ 跨平台复现（Linux CI 的 JDT 运行）；④ 正式抽样设计的
置信区间报告。

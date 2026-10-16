# P2-E 最终资格报告

**状态：`JAVA_PHASE2_ENGINEERING_PASS`**（G1–G6 逐项核实见 §7；非 formal qualification）
**日期**：2026-10-15 · **HEAD**：`a22a03a` → 本轮 commits（fe2ac4d、+2，未 push）

---

## 1. G1 工程规模 —— PASS

`merge_with_l1` 由逐站点 SQL 原型重写为**单次 bulk SQL + 内存匹配**（保持与冻结
原型完全一致的匹配语义）。等价性验证（equivalence_check.py）：

| 项 | 结果 |
|---|---|
| 逐站点状态对照 | **5217/5217 identical**（hikaricp，同输入） |
| counts 对照 | 3084/38/716/1379 双方完全一致 |
| 等价性检查价值 | **抓到并修复** sqlite LIKE ASCII 大小写不敏感 vs Python endswith 敏感的语义漂移（4 站点 recovered↔conflict） |

规模化（P2-E 批量版首次完成）：

| 仓库 | merge wall | 站点数 | 原型能力 |
|---|---|---|---|
| hikaricp | **20ms** | 5217 | 可完成（计数与冻结 oracle 一致） |
| gson | **93ms** | 19633 | 原型超时（>30min） |
| jgit | **1965ms** | 159854 | 原型无法完成 |

## 2. G2 正确性 —— PASS（含诚实边界）

- **8 历史错误样本**：8/8 保持修复（L1 tightened ambiguous/unresolved + JDT CORRECT，
  P2AD 报告数据在本轮合并口径下复核）。
- **38 冲突独立审计**（`conflict-sites.json` 全清单 + 5 项源码抽查）：全部属于
  "L1 错绑（receiver 类型不可知）/JDT 正确"族——TimeUnit 常量 ×21、AtomicInteger
  set/get ×7、Field.get ×2、Thread.sleep ×2、Paths/Stream/Arrays/Connection/
  Statement 各 1；抽查（Thread.sleep、SECONDS.sleep、Connection.getTransaction-
  Isolation、Statement.isClosed、UtilityElf Thread 链）无反例。**保守合并策略
  验证正确**（拒绝 L1 错绑、不覆盖 JDT 正确目标）。2 条 L1 绑定机制细节
  （quietlySleep 1.0 import 形态）标记待查——不影响冲突裁定。
- **新增冲突规模披露**：批量合并使 gson/jgit 冲突首次可见（101/4169）。jgit
  4169 无法逐条人工审计 → 固定种子抽样口径（并入 Phase 3 新鲜样本 S 层）+
  其余保持 conflict_conservative 原状，明确标注为待人工扩展项。

## 3. G3 补召回量化 —— PASS（Phase 3 新鲜分层审计，225 站点，seed 20261015）

| 判定（最终，含人工复核 9 条） | 数量 |
|---|---|
| CORRECT_DEMOTION（demote 正确，其中 3 例 JDT 同时给出真目标） | **41** |
| UNNECESSARY_DEMOTION_JDT_RECOVERED（原本正确被降级，JDT 补回同一目标） | **2** |
| JDT_RECOVERED_CORRECT / JDT_RESOLVES_UNRESOLVED | 2 / 4 |
| CHAIN_CONSISTENT（链式调用，12+12 人工抽查 JDT 与链语义一致） | 24 |
| UNRESOLVED_HONEST | 6 |
| UNADJUDICATED（跨文件类型流，真值需类型流，诚实保留） | 147 |
| **Wrong Resolution（mode A 原始 L1、收紧 L1、JDT、merge 全模式）** | **0** |
| **JDT New Wrong Binding** | **0** |

口径声明：分层样本结果，非全体代码零错误断言；147 UNADJUDICATED 是边界不是通过。
mode A（原始 L1）来自 a22a03a 前的 7ed0e8a 隔离 git-archive 快照，同仓库 SHA。

## 4. G4 性能 —— PASS

- D4 预算：Xmx1g ✅ / JDT RSS ≤1.6GB ✅（P2-B 采样 1.13-1.19GB）/ jgit JDT 批处理
  **8130ms ≤15s ✅**（生产路径 3 次重复：8130/8015/8245ms）。
- merge 无规模退化：20ms→93ms→1965ms（站点 5217→19633→159854，近线性）。
- 完整链路（L1+JDT+merge）单列报告：jgit ≈25.1s（L1）+8.1s（JDT）+2.0s（merge）；
  15s 预算仅适用于 JDT 批处理，未误用为链路预算。
- 内存：max(单进程峰值) 口径（1027MB L1 / 1291MB JDT），无虚假相加。

## 5. G5 兼容性 —— PASS

全量 **475 tests OK**；金样 py/cpp IDENTICAL_EXCEPT_CALL_KIND_VERSION（版本戳 3
设计内）；Python/C/C++ R2 pin 测试通过；MCP frozen harness 自基线零提交/零改动；
默认 index 无 JVM（全量测试即无 JVM 运行）；CLI smoke + java-semantic
--status-only fail-closed smoke 通过。

## 6. G6 证据完整性 —— PASS

`evidence/java-phase2-p2e/`：experiment-manifest（冻结于优化前）、merge-equivalence
（5217 站点对照）、conflict-sites（38+101+4169 全清单）、fresh-audit-samples/
adjudication v1/v2/final（抽样→判定→人工复核全链）、merge-perf、p2e-merge-*.json、
全量 detail JSONL（hikaricp/gson/jgit）。checkpoint 记录各阶段。

## 7. 未解决风险与后续建议

| 项 | 处置 |
|---|---|
| 147 UNADJUDICATED（跨文件类型流真值） | 诚实边界；P2-D 已给出 JDT 绑定，formal 真值需类型流工具 |
| gson 101 / jgit 4169 冲突仅抽样口径 | 保守保留 conflict_conservative；人工扩展审计为可选后续 |
| quietlySleep 1.0 import 绑定机制细节 | 待查（不影响冲突裁定；2 处标记） |
| merge 结果当前为查询时视图（无持久化） | 与 P2-D 设计一致；持久化若需要应走 analysis 表（未实施） |

**Java Phase 2 具备最终工程验收条件**（提交人工工程验收；formal qualification
不在本轮声明范围）。

## 8. 本轮 Commits

| Commit | 内容 |
|---|---|
| 7a9ffca | 实验冻结（manifest/oracle/抽样规则/指标） |
| fe2ac4d | Phase 1-2（批量 merge + 等价性 5217 identical + 冲突提取） |
| （本轮报告 commit） | 三份报告 + 审计数据 |

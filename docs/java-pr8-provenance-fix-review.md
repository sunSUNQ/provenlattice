# PR #8 Provenance Fix and Final Review Report

**状态：`PR8_REVIEW_PASS_READY_FOR_MERGE`**
**日期**：2026-10-15 · **PR HEAD（评审时点）**：`82c9bde`（远程，双平台 CI PASS）
**修复 commit**：`82c9bde`（docs(1.5.0): provenance corrections and unreleased marker）

---

## 1. 独立 GitHub 审查发现核验（Step 1）

| 发现 | 核验结果 |
|---|---|
| 492baba→3956c8c 存在 java_semantic.py 修改 | **属实**：+66/−4（driver 缓存指纹修复，PR #7 内容）+ tests/test_driver_cache.py +44 |
| 44b8960→3956c8c 无文件差异 | **属实**（0 文件，merge commit 树等价） |
| provenance 文件错误归属 | **属实**：v1 声称"492baba 产品代码与 3956c8c 逐文件一致"——错误，已撤回 |
| CHANGELOG 日期语义 | **属实**：2026-10-15 为撰写日；Release 未发生 → 已改 UNRELEASED 标记 |

## 2. 修复内容（commit `82c9bde`，仅 docs，2 文件 +24/−17）

1. **provenance v2**：逐报告区分验证对象与轮次——
   - pr-submission：PR #6 提交轮（合并前），对象 = d933c7c，CI run 38878761976；
   - postmerge：PR #6 合并后，对象 = 492baba，CI run 38887260856（**不含** PR #7 修复——其 Phase 4 实验正是该 blocker 的发现过程）；
   - 44b8960→3956c8c 树等价确认；v1 错误表述显式撤回。
2. **CHANGELOG**：1.5.0 条目标记 **UNRELEASED / 待发布**（正式发布日期由 Release 任务填写）。
3. 两份历史报告**字节不变**（SHA256 复核一致，见 §3）。

## 3. 定向验证（Step 3）

- 迁移报告 SHA256：18aa86f1ead686b5 / e35dbb4991ef68e3 —— **unchanged: True**（×2）
- 44b8960..3956c8c 文件差异 = **0** ✅；492baba..3956c8c = **2**（PR #7 内容，证实修正）✅
- 文档一致性：CHANGELOG UNRELEASED + 四项 Beta 边界 + RQ1 表述；provenance v2 关系表述；B1 版本 1.5.0（pyproject/`__init__`）——全部一致 ✅
- PR diff 范围：仅 CHANGELOG.md + release-docs-provenance.md（无无关变更，无产品代码变更）✅

## 4. 远程 CI（Step 4，run 39192255802 @ 82c9bde）

| Job | 结论 |
|---|---|
| test-linux | **PASS**（50s） |
| test-windows | **PASS**（6m40s） |
| JDT 可选步骤 | CI_SKIPPED（依赖策略，未计入 JDT 通过） |

CI 与 PR HEAD 82c9bde 严格对应 ✅。

## 5. B1/B2/B3 复核

- B1 ✅（1.5.0 四源一致，干净 venv 验证沿用 + 断言未回退）
- B2 ✅（UNRELEASED 标记 + 边界四项 + 升级注记保留）
- B3 ✅（两报告 SHA256 不变 + provenance v2 修正归属与验证对象）

## 6. 证据边界声明（诚实口径）

- 两份迁移报告**各自**验证 d933c7c（PR 分支）与 492baba（合并树），**均不构成
  对 3956c8c 的完整独立验证**；3956c8c 的增量正确性由 PR #7 自身 CI（双平台
  PASS）+ 3 项回归测试 + 本轮 44b8960/3956c8c 树等价核验独立证明。
- Linux JDT 仍 NOT_VERIFIED；146 UNKNOWN 保守保留；RQ1 formal 未取得。

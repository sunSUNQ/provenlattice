# Release Documentation Provenance — 1.5.0

本文件记录 1.5.0 发布准备 PR 中两份验收报告的来源、验证对象与完整性。
（v2：修正 v1 对 492baba/3956c8c 代码关系的错误表述，并区分两份报告各自
的验证对象与轮次。）

## 报告来源与验证对象（逐报告区分）

| 报告 | 产出轮次 | 验证对象（产品代码） | 关联 CI / 运行 | 迁入 SHA256（前 16 位） |
|---|---|---|---|---|
| `docs/java-beta-pr-submission-report.md` | **PR #6 提交轮（合并前）**，本地 commit `16f6ed6` | PR 分支 `feat/java-public-beta` @ `d933c7c`（含 6 个重组提交；**不含** PR #7 修复） | run 38878761976（Linux 44s PASS / Windows 7m14s PASS，476 tests） | `e35dbb4991ef68e3` |
| `docs/java-beta-postmerge-validation-report.md` | **PR #6 合并后验证轮**，本地 commit `157dff0` | 合并 commit `492baba`（= PR #6 树）+ 本地 main 索引运行；**不含** PR #7 修复（其 Phase 4 实验正是该 blocker 的发现过程） | run 38887260856（main 双平台 success，476 tests） | `18aa86f1ead686b5` |

## 历史背景区分

- **本地研发 HEAD `157dff0`**：Java 研发与验收的完整工作链（30 commits，
  未 push），包含两份报告与 6 个大型原始明细文件。
- **远程发布基线 `3956c8c`**：PR #6（干净重组 121 文件）+ PR #7（driver 缓存
  指纹修复 `44b8960`）合入后的 main——**1.5.0 发布候选基线**。
- **代码关系核验（本文件 v2 修正）**：
  - `44b8960 → 3956c8c`：树完全等价（0 文件差异，merge commit）。
  - `492baba → 3956c8c`：**存在产品代码差异**——`java_semantic.py`
    （+22/−4）与 `tests/test_driver_cache.py`（+44），合计 +66/−4（driver
    缓存指纹修复与回归测试），即 PR #7 内容。v1 中"492baba 产品代码与
    3956c8c 逐文件一致"的表述**错误，已撤回**。（统计按 `git diff
    492baba..3956c8c --numstat` 实测修正。）
- 因此：postmerge 报告的验证对象（492baba）**不含** PR #7 修复；PR #7 的
  正确性由其自身的 CI（run 38886089785，双平台 PASS）与 3 项回归测试独立
  证明；两份报告均不构成对 3956c8c 的完整独立验证。
- 本地研发链中 6 个大型原始明细文件（gson/hikaricp full-detail JSONL、
  merge-old/new-sites）**刻意未随迁**：远程以 `.gitignore` 排除大型明细，其
  判定与计数已由提交的审计摘要文件承载。

## 完整性

- 两份报告以 `157dff0` 版本原样迁入（字节级 SHA256 见上表，迁入前后未改动
  任何测试结论、数字或措辞）。
- 报告正文中"本地 HEAD 157dff0"等历史指称按原始记录保留——它们描述的是
  产生证据时的研发状态，不是本发布分支的状态。

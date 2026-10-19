# Release Documentation Provenance — 1.5.0

本文件记录 1.5.0 发布准备 PR 中两份验收报告的来源与完整性，保证历史事实
不被改写。

## 报告来源

| 报告 | 原始产出位置 | 原始 commit（本地研发链） | 迁入 SHA256（前 16 位） |
|---|---|---|---|
| `docs/java-beta-postmerge-validation-report.md` | 本地 main 研发链（PR #6/#7 合并后验证轮） | `157dff0` | `18aa86f1ead686b5` |
| `docs/java-beta-pr-submission-report.md` | 本地 main 研发链（PR 提交轮） | `16f6ed6` | `e35dbb4991ef68e3` |

## 历史背景区分

- **本地研发 HEAD `157dff0`**：Java 研发与验收的完整工作链（30 commits，
  未 push），包含本报告迁移前的研究历史与 6 个大型原始明细文件。
- **远程发布基线 `3956c8c`**：经 PR #6（干净重组 121 文件）与 PR #7（driver
  缓存指纹修复）合入的已批准 Java 能力——**1.5.0 发布候选基线**。
- 两报告的验证运行均在 **PR #6 合并 commit `492baba` 的产品代码**上执行；
  该代码与 `3956c8c` 的产品代码逐文件一致（差异仅为 docs/evidence 文件），
  因此报告结论适用于本发布基线。
- 本地研发链中另有的 6 个大型原始明细文件（gson/hikaricp full-detail JSONL、
  merge-old/new-sites）**刻意未随迁**：远程以 `.gitignore` 排除大型明细，其
  判定与计数已由提交的审计摘要文件承载。

## 完整性

- 两份报告以 `157dff0` 版本原样迁入（字节级 SHA256 见上表），未修改任何测试
  结论、数字或措辞。
- 报告正文中"本地 HEAD 157dff0"等历史指称按原始记录保留——它们描述的是
  产生证据时的研发状态，不是本发布分支的状态。

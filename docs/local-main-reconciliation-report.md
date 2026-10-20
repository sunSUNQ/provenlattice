# 本地 main 平行历史对账报告（Issue Pilot #9 / Owner 决策 R3 §3 RECONCILE_PR）

状态：只读审计交付物 · 审计基线：`origin/main = f4aa118`（PR #21 合并后），
`main = b10b27d`（本地未推送线） · 审计时间：2026-10-20
· 合同：Owner Agent 恢复派发评论（缩小范围版）——只读审计共享对象库，
不触碰用户工作区，不改任何产品代码/既有文档，不 force push / 不重写
本地 main / 不 push 37 提交本体。

## 1. 目的

本地 main 与 origin/main 自 v1.4 时代（merge-base `42c6d89`）分叉为平行
历史：本地独有 37 个提交（原始开发史），origin 独有 46+ 个提交（经
PR #2–#21 重落地并继续演进）。本报告逐提交对账 37 个未推送提交与
origin/main 的内容关系，给出"哪些缺失项值得走正式 PR"的决策输入。

## 2. 方法与判定标准

- 枚举：`git rev-list origin/main..main`（37 commits）；
- 逐提交文件清单：`git show --name-only`；
- 存在性核对：`git cat-file -e origin/main:<file>`（逐文件）；
- 演进核对：`git diff <commit> origin/main -- <files>`（方向：本地 commit
  → origin 终态；`+`=origin 侧新增演进，`-`=被后续演进取代的行）；
- `git cherry`（patch-id）全 37 为 `+`：因各 PR 以 squash/rebase 形态
  重落地，patch-id 不可能匹配，故本报告全部采用**内容级核对**为准；
- 分类：
  - **A 等价合入（字节一致）**：该提交全部文件在 origin/main 存在且
    终态与该提交版本完全一致；
  - **B 等价合入（演进包含）**：全部文件存在于 origin，origin 侧在其
    基础上有后续演进（origin 为唯一活跃主线且 CI 门控）；
  - **C 部分缺失**：提交的 docs/evidence 文件在 origin/main 缺失
    （生产面文件无一缺失，见 §4）；
  - **D 过期/被取代**：提交内容被 origin 上以不同文件名/结构的重落地
    版本取代。

## 3. 总体结论

1. **生产面（src/、tests/、pyproject.toml、MANIFEST.in、ci.yml、
   requirements.txt、README、CHANGELOG）：0 个文件缺失**。37 个提交
   触碰的全部生产面文件均存在于 origin/main——本地 Java 线的全部
   生产内容已经以演进形态经 PR 重落地，无需任何代码回收。
2. **缺失仅限 docs/evidence：7 个提交、12 个文件**（§5 清单）。
3. origin/main 相对本地 main 的**净新增能力**（本地线没有的内容，
   不存在回收问题，仅作对账完整性记录）：PR #13 的 ast:java/cfg:java
   分析器（`analysis_java_ast.py`/`analysis_java_cfg.py` + 注册 +
   测试）、PR #10–#12 的 callers 最终修正态、PR #14 的
   `revalidation/linux-jdt-verify/`、PR #17/#19/#20/#21 的调查与验证
   交付物、1.6.0-dev0 版本预备（PR #18 未合并，hold 中）。
4. 本地 main 的 pyproject 版本为 `1.5.0`，origin/main 为
   `1.6.0-dev0`（PR #18 分支上，未合并）——两线版本号已不可直接
   fast-forward。

## 4. 逐提交分类表（37 项）

### A. 等价合入——字节一致（9 项）

| commit | 主题 | 证据 |
|---|---|---|
| 3f6f415 | longrun final report | 该提交文件与 origin/main 终态 diff 为空 |
| aa86487 | design/evidence-chain 文档 | 同上 |
| ed8ac90 | Phase 2 readiness review | 同上 |
| f713ec2 | P2-B memory qualification 报告 | 同上 |
| d2d053d | P2-A/P2-D 评估与性能报告 | 同上 |
| f7405af | P2-E final qualification | 同上 |
| c65cc28 | driver package marker | 同上 |
| 16f6ed6 | PR #6 提交报告 | 同上 |
| 157dff0 | post-merge validation 报告 | 同上 |

### B. 等价合入——演进包含（12 项，origin 在其内容之上有后续演进）

| commit | 主题 | 对 origin 终态 delta（本地 commit → origin/main） | 重落地载体（lineage） |
|---|---|---|---|
| d36e088 | T1-T3 foundation graph | 5 文件 +500/-16 | PR #6 及后续 |
| d5aa6e7 | P1 resolver type-target guard | 2 文件 +195/-6 | PR #6 及后续 |
| dec0272 | T6 capability registration | 3 文件 +70/-19 | PR #6（capability-matrix/roadmap 均在） |
| bf8a13e | P6 adversarial hardening | 1 文件 +9/-3 | PR #6 |
| 7ed0e8a | P2-C classpath contract | 2 文件 +31/-12 | PR #6/#7（origin 已含 8.3 短名 abspath 修正） |
| 1ef88f9 | P2-A demote + P2-D semantic_java | 6 文件 +97/-22 | PR #6/#7 |
| 370e842 | batch merge_with_l1 补交 | 1 文件 +29/-9 | PR #6 |
| 91ee76d | Phase 2 acceptance closure | 1 文件 +22/-4 | PR #6 |
| a4667c5 | public beta readiness (README) | 1 文件 +29/-19 | PR #6/#8 |
| edd24a9 | beta readiness artifacts (BOM fix 等) | 2 文件 +27/-10 | PR #6/#7 |
| 258d34b | PR packaging hygiene (MANIFEST.in) | 1 文件 +1/-1（生产面）；其 evidence 2 文件缺失 → 见 §5 | PR #6/#8 |
| 077810b | PR preflight（ci.yml Java steps + 材料） | 1 文件 +49/-2 | PR #6 |

delta 方向说明：以上为"本地提交 → origin 终态"的 diff，`+` 行是
origin 侧在其内容之上的演进（callers 修正、8.3 路径修正、AST/CFG
注册等），`-` 行是被演进取代的行——本地内容是 origin 终态的祖先形态。

### C. 部分缺失——docs/evidence 文件在 origin 缺失（6 项 + B 类中 1 项）

| commit | 主题 | 缺失文件 |
|---|---|---|
| 3f79181 | P2-B measurements | `evidence/java-phase2-p2b/results/p2b-gson-full-detail-0.jsonl`、`p2b-hikaricp-full-detail-0.jsonl` |
| fe2ac4d | P2-E Phase 1-2 | `evidence/java-phase2-p2e/results/merge-new-sites.json`、`merge-old-sites.json`、`p2e-{gson,hikaricp,jgit}-full-detail.jsonl`（5 文件） |
| 67a1fb5 | P2-E evidence update | `evidence/java-phase2-p2e/results/merge-new-sites.json`、`unadjudicated-attribution.json` |
| 258d34b | PR packaging hygiene | `evidence/java-phase2-p2e/results/p2e-jgit-full-detail.jsonl`、`unadjudicated-attribution.json` |
| 32611d7 | 1.5.0 merge + postmerge record | `docs/java-150-merge-postmerge-validation.md` |
| e7a7d2d | 1.5.0 release notes | `docs/releases/release-notes-1.5.0.md` |
| 582b022 | Stage-0 postrelease report | `docs/java-beta-stage0-report.md`（**Issue #9 状态行同步的阻塞物**） |

### D. 其余：checkpoint/evidence 追加型提交，全部文件已在 origin（10 项）

606fe6b（T9-A benchmark evidence，16 文件）、9847a39（T9-B + ADR +
prototype，6 文件）、258eeb3（P7 e2e audit，7 文件）、ac6ba5d /
15bef26 / f289f58 / 924c5fc / b10b27d（checkpoints.jsonl 追加）、
a22a03a（p2ad checkpoints）、7a9ffca（P2-E experiment manifest）——
逐文件 `cat-file -e origin/main:<f>` 全部 exit 0。checkpoint 类为
追加式 jsonl，origin 侧为超集。

## 5. 缺失文件处置建议（供 owner 决策；本报告不执行任何带入）

| 优先级建议 | 文件 | 理由与建议 |
|---|---|---|
| 高 | `docs/java-beta-stage0-report.md`（582b022） | Issue #9 合同目标的载体；不入 origin 则状态行同步永久阻塞。建议：以正式 PR 带入**原始内容**（582b022 版本），随后 #9 按既定范围更新两处状态行（PR #14/#17 之后的 VERIFIED 结论与 capability-matrix 措辞） |
| 中 | `docs/java-150-merge-postmerge-validation.md`（32611d7）、`docs/releases/release-notes-1.5.0.md`（e7a7d2d） | origin 已有 `docs/releases/v1.5.0.md`（PR #8 重落地版本）作为发布主记录；本两份为本地过程记录。建议：release notes 以 origin v1.5.0.md 为准（本地版本视为被取代）；postmerge 记录由 owner 裁量是否作为历史归档带入 |
| 中 | P2-B 2 份 `*-full-detail-0.jsonl`（3f79181）、P2-E 7 份 results/attribution（fe2ac4d/67a1fb5/258d34b） | 原始实验数据；origin 已有同族 detail/summary 文件，缺的是 full-detail 大文件与 attribution 数据。建议：若 owner 认为 T9-B/P2-B/P2-E 证据链需要 full-detail 原始数据（如后续 formal 抽样审计），以单独 evidence PR 带入；否则在决策记录中明确放弃，避免证据链悬空 |

## 6. 边界与局限声明

- 本报告为只读审计：未修改任何文件（含产品代码与既有文档）、未触碰
  `D:\ChatGPT\codegraph` 用户工作区与未提交修改、未执行任何 push。
- "等价合入（演进包含）"的判定依据是内容级 diff 与 lineage（PR 合并
  历史），非逐行补丁证明；origin/main 为唯一活跃主线且全量 CI 门控，
  以其终态为准绳。若 owner 需要逐提交补丁级核对，建议在决定"哪些
  缺失项走正式 PR"之后对选中项做专项审计。
- 37 个提交本体如何处置（保留本地 / push 到归档分支 / 逐步放弃）属
  Owner Gate（本地 main 历史处理），本报告不提出执行方案，仅提示：
  两线 pyproject 版本已分叉（1.5.0 vs 1.6.0-dev0），任何直接合并都
  需要显式决策。

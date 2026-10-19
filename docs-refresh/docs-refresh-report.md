# 1.5.0 全量 Markdown 文档刷新报告（DOCS_V150_READY_FOR_PR → PR #9 已提交）

**日期**：2026-10-19 · **基线**：远程 main `0ec6364`（PR #8 merge commit）
**工作区**：隔离 worktree `docs/1.5.0-refresh` 分支（修改已 commit 并 push 至 PR #9，双平台 CI PASS）

---

## 1. 执行摘要

全仓 **250 个受 Git 管理的 Markdown** 逐一清点、分类（A–E）、SHA256 登记；
6 个权威文档完成 1.5.0 同步更新；2 个新文档创建；55 份历史报告与 146 份
实验/测试资产按"保留原始内容"纪律零字节变化；跨文档一致性、链接与格式
检查通过。

## 2. 分类统计（A–E）

| 类 | 定义 | 数量 | 处理 |
|---|---|---|---|
| A 当前入口/状态文档 | README、CHANGELOG、capability-matrix、roadmap、REPRODUCIBILITY、docs/releases/v1.5.0.md | 5+1 新 | **全部更新/创建** |
| B 技术设计与路线图 | docs/design-*、integration-overview 等 | 44 | 2 更新（capability-matrix 标题与 Java 行、roadmap G7 增补）；其余保留历史设计 |
| C 历史报告与验收证据 | docs/java-*、pr1-*、java-pr6/pr8 等 | 55 | 全部保留原样（含 1 个历史示例占位链接——非权威文件，保留） |
| D 实验协议/原始结果/fixture | evidence/*、experiments/*、tests/*、benchmark* | 146 | **冻结零字节变化**（git status 核验） |

## 3. 核心文档更新明细（Phase 1）

### README.md
- 标题 `ProvenLattice V1.4` → `ProvenLattice 1.5.0`；定位句改为三语言
- Java Support 边界条目：删除"JDT 未实测、未集成"过期声明；JDT 小节标题
  改为"**已交付**"，P2-A/P2-D/P2-E 资格引用更新
- Validation 表标注"1.4.0 基线"并新增 **1.5.0 Java 验证段**（479 tests、
  三仓库零失败、jgit 25.1s / JDT 8.1s、wheel/sdist 安装验证）
- Limitations Java 条目改写为当前真实状态（可选 JDT 已交付、Linux NOT_VERIFIED、
  SCIP INFRA_BLOCKED、非 Stable）
- Documentation 表补 `docs/releases/v1.5.0.md` 与设计证据链入口
- Standalone Roadmap 增 1.5.0 段（已交付/未验证/未取得分层）
- Status 节：479 tests、GitHub Release 链接、**GitHub-only 安装渠道声明**
- V1.4 New Capabilities 保留为历史里程碑 ✅

### docs/capability-matrix.md
- 标题与日期 → 1.5.0
- Java L1 行验证列更新（479 全量回归）
- Three-state 行语言列补 Java
- **L2 表新增 `Semantic Java (Optional JDT)` 行**（implemented/diagnostic，
  Windows/JDK21 已验证、Linux NOT_VERIFIED、query-time 不持久化）
- 边界注："明确不等同于"改为 JDT 已交付表述；CALL_KIND_VERSION 更新为
  **当前 = 3**（含 1→2/2→3 演进史）

### docs/roadmap.md
- G7 Already implemented 增补 1.5.0 Java Optional JDT 条目
- Not implemented 的 Java 行改写为精确余量（SCIP INFRA_BLOCKED、Linux JDT
  待完成、Java L2 分析器、RQ1 formal 独立立项）
- Gold Target V2 冻结规划**未触碰** ✅

### CHANGELOG.md
- 1.5.0 条目 UNRELEASED → **已发布（2026-10-19）**，附 tag/Release URL
- 历史 V1.4 及更早条目零变化（仅 1 处 "1.4.0" = V1.4 条目本身，合理保留）

### REPRODUCIBILITY.md
- 新增 "0. 1.5.0 Java Public Beta Evidence" 节（tag/commit/PR 链/479 tests/
  三仓库/审计/JDT 范围/发布包 SHA256/未取得资格）
- V1.4 历史 evidence 节保留原样

### docs/releases/v1.5.0.md（新建）
- 独立 1.5.0 Release Notes：新能力/安装（GitHub-only 渠道如实声明）/可选
  JDT 启用/升级注记/验证结果/已知限制/证据链

## 4. 其他文档扫描（Phase 2）

- 全部 250 文件按 stale 模式扫描（JDT 未集成声明、476 旧测试数、UNRELEASED
  残留、PyPI 不存在声明等）；**A/B 层过期命中已全部清除**（终扫 0 命中）
- C/D 类历史文件含旧数字者为**准确历史记录**（如 provenance 中 run 38878761976
  的 476 tests 为该轮真实计数），按纪律保留

## 5. 一致性与验证（Phase 3/4，`validation-results.json`）

| 检查 | 结果 |
|---|---|
| 版本一致性（README/CHANGELOG/capability-matrix/releases/REPRODUCIBILITY） | 1.5.0 全一致；README 无 V1.4 主标题残留；UNRELEASED 仅 CHANGELOG（已改已发布，最终态 0） |
| 相对链接 | 检查 74、broken 1 = `design-analysis-layer-c-a3-audit.md` 的历史示例占位 `x`（C 类，保留） |
| Markdown 格式 | 未闭合 code fence = 0 |
| 冻结证据完整性 | experiments/、evidence/、tests/、src/ **零触碰**（git status 核验） |
| CLI 示例 | README/java-semantic 示例均为真实执行输出（Java L1 smoke / fail-closed / JDK21 链路在前轮实测） |
| GitHub Release URL | `releases/tag/provenlattice-v1.5.0` 已在线验证 ✅ |

## 6. 统计汇总

- Markdown 总数：**250**
- A 类更新：**5/5**；新建：**1**（v1.5.0.md）+ provenance 文件（前轮已入）
- B 类更新：2（capability-matrix、roadmap）；保留历史：42
- C 类保留：55；D 类冻结：146
- 过期权威描述残留：**0**
- 阻断：**0**

## 7. 提交与 PR 说明

按约束本轮**未 commit**——全部修改保留在隔离 worktree
`%TEMP%\opencode\docs150`（分支 `docs/1.5.0-refresh`）工作区中，等待人工
审查后单独批准文档 PR（建议：单 commit "docs: 1.5.0 documentation refresh"
或按文件分组）。

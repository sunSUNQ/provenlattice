# PR 提交报告 — Java Public Beta

**状态：`PR_READY_FOR_REVIEW`** · 日期 2026-10-15
**PR**：https://github.com/sunSUNQ/provenlattice/pull/6
**分支**：`feat/java-public-beta`（origin/main 42c6d89 → HEAD `d933c7c`，6 个可审查提交）
**原始研发 HEAD**：`c65cc28`（27 个本地研发 commit 保留在 main 工作历史，未 push）

---

## 1. 历史卫生审查与干净重组（Phase 1）

- 对象级审计（`history_audit.py`）发现 Java 研发历史含大型 blob：
  **57.2MB** jgit detail JSONL、**8.4MB** attribution JSON（已从 HEAD 移除但
  历史可达）及多个 >1MB 明细。
- **采用干净历史重组**：`feat/java-public-beta` 从 origin/main（42c6d89）创建，
  按 c65cc28 已批准的最终文件状态重组成 **6 个可审查提交**（core / docs /
  evidence / PR 打包 / driver marker / CI 步骤），**排除全部 >1MB 原始明细**
  （.gitignore 固化规则）。
- 树等价：121 文件 +47,312 行（原 691,525 行 → -93%）；排除清单之外的最终
  功能内容与已验收版本一致；重组分支上全量 **476 tests OK**。
- 原始 27 commit 链保留在本地 main 历史（HEAD c65cc28），未破坏；映射：
  c65cc28 树 → 集成分支 HEAD 树（排除 8 个大明细文件 + 新增 __init__.py/
  MANIFEST.in/CI 步骤/BOM 与 normalize 修复）。

## 2. 提交过程中修复的 CI 阻断（保留失败记录）

| # | Run | 平台 | 失败 | 修复 |
|---|---|---|---|---|
| 1 | 38872308809 | 双平台 | 干净分支漏提 tests/（417 基线 vs capability 扩展断言） | `test(java): add Java test suites` |
| 2 | 38873822242 | Windows | `Path.resolve()` 展开 8.3 短名（RUNNER~1）→ classpath 指纹环境相关 | **产品修复**：normalize 改 abspath（base_dir 先拼接）|
| 3 | 38875390467 | Windows | 测试期望值用 resolve() 与产品 abspath 不一致 | 测试断言环境可移植化 |
| 4 | 38877158153 | Windows | cp11 断言 `is_dir()` 对 jar 文件恒 False（断言笔误） | 改 `exists()` |
| — | 38878761976 | **双平台全绿** | — | — |

全部失败原因、修复前后证据保留于 GitHub Actions runs 与本地 commit 链。

## 3. 远程 CI 状态（Run 38878761976）

| 检查 | Windows | Linux |
|---|---|---|
| Python 全量测试（476） | **CI_PASS**（15m18s） | **CI_PASS**（42s） |
| Wheel 构建 + driver 打包断言 | **CI_PASS** | **CI_PASS** |
| Java L1 no-JVM smoke | **CI_PASS** | **CI_PASS** |
| java-semantic CLI smoke | **CI_PASS** | **CI_PASS** |
| JDT 可选步骤 | **CI_SKIPPED**（无 PL_JAVA_JDT_CLASSPATH，未计入 JDT 通过） | **CI_SKIPPED** |
| JDK 缺失 fail-closed | **CI_PASS**（unavailable 断言） | **CI_PASS** |

JDT 是否真正在远程运行：**否**（CI_SKIPPED——依赖策略要求经审查的 jar 集，
未配置 runner variable；Linux JDT 仍 NOT_VERIFIED）。

## 4. Merge 条件

- **具备人工 Review 条件**：✅（PR #6 OPEN、MERGEABLE、双平台 CI_PASS、
  diff 121 文件 +47k 行无异常大数据、无敏感信息）
- **具备 Merge 条件**：⏳ 待人工 Code Review + 仓库保护规则执行；
  merge 后建议在 main 复跑 CI 并执行一次全量 index 验证。

## 5. 发布阻断项

**无**。非阻断遗留：Linux JDT NOT_VERIFIED；JDK 组合矩阵未全测；146 UNKNOWN；
query-time 不持久化；Maven/Gradle 自动发现未实施。

## 6. 合并后建议验证任务

1. main 上复跑全量测试 + Java smoke（双平台）。
2. Linux 容器/runner 配置 PL_JAVA_JDT_CLASSPATH 执行 JDT 冒烟（升格 Linux JDT 验证）。
3. RQ1 formal qualification 立项评估（独立金标集 + 盲评协议）。
4. Stable Release 准备（按 Beta 反馈 + 上述补验）。

---

**本轮 commits（feat/java-public-beta 远程分支）**：
3d9110a feat(java) → baa83b7 docs → c103bd0 evidence → 258d34b packaging →
c65cc28 driver marker → 0e781cf tests → 5895daa normalize fix → 431ebfe
portable assertions → d933c7c cp11 exists → （PR #6）

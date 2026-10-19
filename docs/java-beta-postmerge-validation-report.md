# Java Public Beta 合并后验证与 Release 准备报告

**状态：`POSTMERGE_PASS`** · **`JAVA_BETA_READY_FOR_RELEASE: YES`**
**日期**：2026-10-15 · **最终 main HEAD**：`44b8960`（PR #7 合并后）

---

## 1. PR 合并与 main 状态

| PR | 内容 | 状态 | merge commit |
|---|---|---|---|
| #6 | Java L1 + optional JDT semantic analysis（121 文件） | **MERGED** | `492baba` |
| #7 | fix: driver compile cache keyed on source fingerprint（发布阻断修复） | **MERGED** | `3956c8c` |

最终 main HEAD：`44b8960`（远程）。合并前强制检查全过（OPEN/3c7a853/双 CI PASS/
MERGEABLE/base main）；未绕过分支保护；merge commit 方式（无 force push）。

## 2. 合并后独立验证（origin/main worktree）

- 全量 **476 tests OK**（合并后 main 首跑）
- Java 真实仓库（冻结 SHA）：HikariCP 112 文件（3918 resolved，0 失败）、
  gson 263（5468 节点 / 14364 resolved）、jgit 1895（37942 节点 / 142412 resolved）
  ——零解析失败
- MCP frozen contract：sha256 与基线一致（未触碰）
- 旧库升级：CALL_KIND_VERSION 3 机制（升级后全量 index 即收敛——本轮合并后
  三仓库索引即为全量重建验证）

## 3. 发布包与用户路径（真实 wheel/sdist，干净 venv）

| 用户步骤 | 结果 |
|---|---|
| wheel/sdist 构建（合并后 main） | ✅ 均含 driver 源码 |
| 干净 venv 安装 | ✅ |
| 无 JVM Java L1 索引 + symbol/callers 查询 | ✅（callers=0 为 P2-A 收紧后正确语义：相关调用为 ambiguous 候选） |
| 无 JDK 时 `java-semantic` | ✅ `unavailable / jdk_not_found` |
| JDK 21 + 手工 Classpath manifest + full 查询 | ✅ available，calls_resolved 4025，merge 口径 27/714/3228/1248 |
| provenance / fingerprint / L1-JDT 对照 | ✅ 用户可见 |

## 4. Driver 缓存升级风险专项（Phase 4，RELEASE_BLOCKER 确认并修复）

- **实验确认**：compiled.marker 仅查存在性 → 模拟 wheel 升级（替换 site-packages
  driver 源）后旧 class 被执行（run2：新源被忽略）；删除 marker 强制重编译时
  损坏源的编译失败被正确 fail-closed（run4：`failed / driver_compile_failed`）。
- **修复**：marker 改为 `sha256(driver 源码 + JDT classpath)` 指纹（PR #7，
  独立分支 → CI 双平台 PASS → 已合并）。
- **修复验证**：新 wheel 安装 + 旧缓存共存 → 指纹不匹配 → 重编译 → 新 driver
  执行（calls_resolved 4025）✅；回归测试 3 项（key 对源码/classpath 变化敏感、
  旧式 marker 不被复用）。
- **RELEASE_BLOCKER 解除** ✅

## 5. main CI（合并后）

| Job | 结论 |
|---|---|
| test-linux | **success**（含 476 全量 + Java smoke + driver 打包断言） |
| test-windows | **success**（同上） |
| JDT 可选步骤 | CI_SKIPPED（两平台；依赖策略，未计入 JDT 通过） |

## 6. 验证范围声明

Windows（Temurin 21）全链路已验证；**Linux：CI 全量测试 PASS，Linux JDT 运行
NOT_VERIFIED**（可选步骤依赖策略）；其他 JDK 组合未测；146 UNKNOWN 保守保留；
query-time 结果不持久化到 L1 图；RQ1 formal **未取得**。

## 7. Release Notes 材料（建议版本号：**1.5.0**）

依据：新增 Java L1 + optional JDT Analyzer（minor 级新能力，无 breaking change；
版本号最终由维护者决定，本项目未自动修改）。

**Release Notes 要点**（摘要，全文随 Release 生成）：
1. 新能力：Java L1（默认无 JVM）、三态引用 + P2-A 安全收紧、java-semantic
   可选 JDT 精确解析、classpath 手工契约
2. 安装：`pip install provenlattice`（含 tree-sitter-java）；JDT 可选能力需
   JDK 21（已验证）+ JDT classpath（用户自备）+ 两个环境变量
3. **升级必须**：执行一次完整 `provenlattice index`（CALL_KIND_VERSION 3）
4. 限制：146 UNKNOWN、Linux JDT NOT_VERIFIED、query-time 不持久化、SCIP
   INFRA_BLOCKED、Maven/Gradle 不自动执行
5. 已验证/未验证边界与 RQ1 formal 声明

## 8. Release Blocker 清单

**无**。（原 driver 缓存 blocker 已修复并验证。）

## 9. 下一条正式 Release Agent 任务建议

人工批准版本号 → 创建 tag/Release（附本报告与资格报告链）→ PyPI 发布流程
（独立授权）→ Stable 准备（Linux JDT 验证 + JDK 矩阵 + Beta 反馈收集）。

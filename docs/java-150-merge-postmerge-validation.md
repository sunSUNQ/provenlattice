# 1.5.0 合并与合并后验证记录（PL-JAVA-PR8-MERGE-AND-POSTMERGE-V1）

**状态：`POSTMERGE_PASS_RELEASE_READY`** · 日期 2026-10-16

## 合并与 main

- PR #8：**MERGED**，merge commit **`0ec6364`**
- 最终 main HEAD：**`77939e6`**（含 B1/B2/B3 全部内容）
- main 合并后 CI（run 39194630800 @ 0ec6364）：**test-linux success / test-windows success**

## 验证结果（合并后 main，干净 venv 安装 1.5.0 wheel）

| 项 | 结果 |
|---|---|
| 全量测试 | **479 tests OK**（repo 根 + PYTHONPATH 运行；476 + 3 driver-cache 回归） |
| 版本元数据 | pyproject = `__version__` = installed = **1.5.0** ✅（worktree 直跑出现的 1.4.0 为本机旧 editable 安装伪影，干净 venv 权威验证通过） |
| CHANGELOG | 1.5.0 **UNRELEASED** 标记 + 四项 Beta 边界 + 升级注记 ✅ |
| provenance | numstat 修正（+22/−4、+44）与 PR #7 实测一致 ✅ |
| 报告 SHA256 | 18aa86f1… / e35dbb49… 迁入版本未变 ✅ |
| Java L1 索引 | hikaricp 112 文件 / 3918 resolved / 0 失败 ✅ |
| 无 JDK fail-closed | `unavailable / jdk_not_found` ✅ |
| JDK21 JDT smoke | `available`，calls_resolved 4025，backend eclipse-jdt ✅ |
| CI JDT 步骤 | **CI_SKIPPED**（两平台；不宣称为 PASS） |

## 发布包（合并后 main 构建）

| 产物 | SHA256 |
|---|---|
| provenlattice-1.5.0-py3-none-any.whl | `7ce708a593b8a39bcd2bbab2e3788fcf315ed25683a722e51a8bb62ffe5c391c` |
| provenlattice-1.5.0.tar.gz | `8417a05eddf7af8d817ab5e0f96df2afd95ade9e1ebe267a2f37f7a7f4d9be46` |

## 遗留边界（Release Notes 必须保留）

Linux JDT NOT_VERIFIED（CI_SKIPPED）；146 UNKNOWN 保守保留；query-time 结果
不持久化；RQ1 formal 未取得；JDK 21 已验证、其他组合未测；Maven/Gradle 与
SCIP 边界同前。

## Release Blocker

**无。**

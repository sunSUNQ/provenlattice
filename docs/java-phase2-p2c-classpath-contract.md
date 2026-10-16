# P2-C：手工 Java Classpath 契约（正式实现 v1）

**状态：已实现并测试**（`src/provenlattice/classpath.py`，13 项契约测试 +
三仓库真实验证）· 日期 2026-10-15 · 输入 HEAD f713ec2

## 1. 定位与不变量

- 供 P2-D 可选 JDT Analyzer 消费的正式契约；**默认 L1 路径不 import 本模块**，
  不启动 JVM；Python/C/C++ 能力不受影响。
- 失败封闭：任何 NOT_FOUND / NOT_READABLE / BAD_KIND / CORRUPT_JAR 使契约整体
  `status="invalid"`、`usable=False`、`fingerprint=None`——消费方必须拒绝继续，
  不允许静默产出错误的精确解析结果。

## 2. 输入格式（无分隔符歧义设计）

1. API：`build_classpath(project_roots=[...], dependencies=[...], base_dir=...)`
   ——每项恰为**一个路径**；空格、`;`、`&` 均为字面字符（§cp09 测试）。
2. 清单文件：`load_classpath_file(path)` ——每行一条，`project:<path>` /
   `dep:<path>`，`#` 注释与空行忽略；相对路径按清单所在目录解析。
3. **刻意不提供**分号/冒号连接串输入（Windows 分隔符歧义源头）；含分隔符的
   字符串会按字面路径处理并得到 NOT_FOUND 诊断。

## 3. 规范化、顺序与去重

- `expanduser → 相对路径按 base_dir → resolve() → 正斜杠`。
- 去重键 = `os.path.normcase(正斜杠路径)`（Windows 大小写不敏感、POSIX 近恒等），
  **保留首次出现顺序**；重复项计入 `duplicates` 并报告。
- 顺序即 classpath 解析序，语义保留；指纹对顺序敏感。

## 4. 验证规则

| 类别 | 规则 |
|---|---|
| project_roots | 必须存在、为目录、可读 → 否则 NOT_FOUND/NOT_A_DIRECTORY/NOT_READABLE |
| dependencies | 存在 + 可读 + （目录=class dir 或 后缀 .jar/.zip 且 `zipfile.is_zipfile` 通过）→ 否则 NOT_FOUND/NOT_READABLE/BAD_KIND/CORRUPT_JAR |

## 5. 指纹与 freshness/invalidation

- `fingerprint = "cp:" + sha256(0x1f 连接的 normcase 条目序列)`；
  **顺序变化即变化**（cp10）；依赖集合变化即变化（cp13）；空契约 = `cp:empty`；
  invalid = None。
- freshness 契约：Analyzer 结果必须记录所用契约的 fingerprint；消费时与当前
  fingerprint 比对——不一致即结果过期（P2-D 接入 `dependency_staleness` 同风格）。
- 解析结果来源记录：JDT 行携带 `provenance=semantic:jdt-v<n>` +
  `classpath_fingerprint`（P2-D 落地项，本契约提供该字段）。

## 6. 错误报告

`ClasspathIssue(path, code, detail)` 结构化输出；codes：NOT_FOUND / NOT_READABLE /
BAD_KIND / CORRUPT_JAR / NOT_A_DIRECTORY。**可复现性**：相同输入（路径集合+顺序+平台）
→ 相同指纹；测量与验证脚本入库（`evidence/java-phase2-p2c/`）。

## 7. 优雅降级场景（已测）

| 场景 | 行为 |
|---|---|
| 无 classpath | `status="empty"`, `usable=True`, `cp:empty`（Analyzer 可无 classpath 运行，recovered 过滤兜底） |
| 路径不存在 / 不可读 / 非法种类 / 损坏 jar | 整体 invalid fail-closed（C/D 场景） |
| 重复 | 报告并去重（F 场景） |
| 配置更新 | 指纹变化 → invalidation（E 场景） |

## 8. 与 Maven/Gradle 自动发现的关系（Phase 5 设计调查，未实施）

**接入点**：`build_classpath()` 为纯函数——未来的发现器只需产出
`(project_roots, dependencies)` 序列即可接入，契约/指纹/freshness 不变。

| 场景 | 设计方向 |
|---|---|
| Maven 项目 | 优先读取**已生成**的 classpath 文件（如 `mvn dependency:build-classpath -Dmdep.outputFile=...` 的产物）；无产物时不自动执行 mvn |
| Gradle 项目 | 同上（Gradle `eclipse`/自定义任务产物）；不自动执行 gradle 脚本 |
| 多模块 | 每模块一份契约清单 + 模块间依赖 jar 的显式列举；发现器按模块产出多个 contract |
| 依赖缺失 | 清单声明的路径缺失 → invalid fail-closed（已有行为），报告缺失项 |
| 离线环境 | 仅消费本地已有制品；绝不联网下载 |
| Classpath 过期 | 指纹不匹配 → 结果过期（已有 freshness 契约）；制品 mtime 变化可作辅助信号 |
| 构建脚本副作用 | **永不自动执行**项目自带构建脚本（可执行任意代码）；如未来提供 opt-in 执行，必须显式声明、隔离进程、并默认拒绝网络 |
| 自动发现 vs 手工优先级 | 手工契约**始终覆盖**自动发现（显式输入优先）；自动发现仅建议、标记 provenance |
| 缓存 | 发现结果（contract JSON）按仓库 SHA + 配置哈希缓存；缓存不改变指纹算法 |
| 不可靠发现 | 发现器无法确证时输出 `usable=False` + 原因，绝不猜测路径补齐 |

## 9. 明确不做（本轮）

- 不接线 CLI flag（避免悬空命令；P2-D 的 analyze/独立命令接入时消费本契约）；
- 不实现 Maven/Gradle 自动发现（§8 为设计边界）；
- 不改变 Java L1 绑定语义（P2-A 独立评审：docs/java-phase2-p2a-demote-design-review.md）；
- 不启动 JVM（消费验证使用 P2-B 隔离原型 driver，结果标注为"独立原型已验证"）。

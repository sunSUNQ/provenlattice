# PR Preflight 报告 — Java Public Beta

**状态：`READY_FOR_PR`**（远程 CI 未执行——区分 CI_CONFIGURED / CI_EXECUTED / CI_PASS）
**日期**：2026-10-15 · **HEAD**：`edd24a9` → 本轮 commits（未 push）· **476 tests OK**

---

## 1. Phase 0：Git 与工作区

- 24 个本地 commit（42c6d89..edd24a9）逐项列出核验，全部 Java 相关、无无关修改。
- 历史审计：无二进制依赖（JDK/JAR 在仓库外）、无敏感信息；evidence 脚本中的
  当环境绝对路径为实验记录性质（报告已注明）。
- **PR 卫生处理**：276k 行 jgit detail JSONL 与 176k 行 attribution JSON 移出跟踪
  （本体存仓库外，判定/摘要数据保留在库）；本轮构建产物 `build/` 清理。
- 用户未跟踪 v1.4 文件：完好保留，未触碰。

## 2. Phase 1：功能一致性（六项全过）

无 JVM 默认索引 ✅（476 测试即无 JVM 运行）；JDT fail-closed ✅（status-only
smoke）；无已知错误确定绑定 ✅（R1 + P2-E 审计）；ambiguous/unresolved 语义一致 ✅；
query-time 与图谱分离 ✅（merge 为视图，零 L1 写入）；旧语言 pin ✅。

## 3. Phase 2：双平台 CI（CI_CONFIGURED——远程未执行）

`ci.yml` 两 job（windows/linux）各新增 4 步：

1. Verify package-data（TOML + **JDT driver 源码存在性**）
2. Java L1 no-JVM smoke（真实索引 + symbol 查询 + analyzer 状态断言）
3. Wheel build 断言 driver 打包
4. Optional JDT smoke（`if: env.PL_JAVA_JDT_CLASSPATH != ''`——仅在 runner 配置
   了经审查的 JDT jar 时执行）

YAML 语法已本地验证（yaml.safe_load，双 job 11 steps）。
**CI 状态口径**：CI_CONFIGURED ✅ / CI_EXECUTED ❌（需 push 后远程运行）/
CI_PASS ❌——不宣称远程通过。

## 4. Phase 3：发布包复核（真实产物）

| 项 | wheel | sdist |
|---|---|---|
| Java frontend | ✅ | ✅ |
| JDT driver 源码 | ✅（本轮 MANIFEST.in 修复） | ✅ |
| 干净环境 driver 编译缓存 | ✅（tempfile，无绝对路径） | — |
| BOM manifest 兼容 | ✅（utf-8-sig + 回归） | — |
| 无 JDK 状态 | ✅ unavailable/jdk_not_found | — |
| 完整 JDT 调用 + provenance + fingerprint | ✅（干净 venv 实测 4025 resolved） | — |

## 5. Phase 4：最终工程验收

全量 **476 tests OK**（含 13 classpath + 9 demote/R2 + 5 semantic）；Python/C/C++
回归含于全量；MCP frozen contract 零改动（git 核对）；旧库 = CALL_KIND_VERSION
机制（升级注记：全量 index 一次）。

## 6. README 更新摘要

Java Support 节新增 "可选精确解析：java-semantic" 小节——环境变量、status-only、
classpath manifest 示例、provenance/fingerprint、资源成本、限制、formal 边界——
**全部示例为真实 CLI 实测输出**。

## 7. PR 描述（建议正文）

> **feat: add Java support with optional JDT semantic analysis**
>
> ### 背景
> 在既有 ProvenLattice Foundation Graph（Python/C/C++）上新增 Java 支持：
> L1 默认轻量确定性解析 + 可选 Eclipse JDT 精确语义增强（query-time）。
>
> ### Java 新能力
> - L1：`.java` 扫描/解析/符号/引用/调用，复用冻结 schema 与三态契约
> - P2-A R1：receiver 类型不可知的 0.75/0.98 启发式绑定 demote（Wrong-Resolution=0）
> - P2-C：手工 Classpath 契约（校验/去重/指纹/fail-closed）
> - P2-D：`semantic_java` capability + `java-semantic` CLI（独立 JVM 进程、
>   recovered 过滤、merge 审计视图）
>
> ### 架构
> L1 与 JDT 严格分层：默认 index 零 JVM；JDT 按需独立进程，结果为查询时
> 增强视图（不写 L1 图），provenance=semantic:jdt-v1 + classpath fingerprint。
>
> ### 正确性证据
> 8/8 历史错误绑定修复；168 冲突抽样 0 JDT 错误；225 新鲜分层审计
> WRONG_RESOLUTION=0（原始/收紧/JDT/merge 四模式）；38 冲突全审计。
>
> ### 性能
> jgit（1891 文件）：L1 25.1s / JDT 8.1s / merge 2.0s；JDT RSS ~1.2GB（-Xmx1g）。
>
> ### 兼容性
> Python/C/C++ 行为不变（金样四表一致，除设计内版本戳）；MCP contract 不变；
> 旧库经 CALL_KIND_VERSION 自动重解析。
>
> ### 已知限制
> 146 UNKNOWN（跨文件/外部类型流）；query-time 不持久化；Linux 未验证；
> Maven/Gradle 不自动执行；SCIP INFRA_BLOCKED。
>
> ### 升级说明
> 升级后执行一次 `provenlattice index`（CALL_KIND_VERSION 3）。
>
> ### Reviewer 清单
> - [ ] resolver.py R1 门控（metadata 仅 Java 发射）
> - [ ] CALL_KIND_VERSION 3 与升级注记
> - [ ] classpath.py fail-closed 语义
> - [ ] java_semantic.py recovered 过滤与 merge 策略
> - [ ] capability 冻结集扩展
> - [ ] CI 双平台 Java 步骤

## 8. 裁定与后续人工顺序

**`READY_FOR_PR`**（Blocker：无。CI_EXECUTED/CI_PASS 与 Linux 验证为 PR 后事项）。

人工顺序：审核本地提交 → push feature 分支 → 创建 PR（标题/正文见 §7）→
远程 CI（Windows+Linux，JDT 步骤按需配置）→ Code Review → 合并 main →
main 复验 → 决定版本号 → Tag/Release。

建议下一条任务：远程 CI 通过后的 Linux JDT 补验 + RQ1 formal 立项评估。

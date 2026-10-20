# Java JDT 结果持久化到 analysis 表 — 设计文档 V1（research prototype）

Issue Pilot #5 · 状态：原型实测完成 · 证据等级：**prototype（Windows-only，T9-B jar 集）**，
不构成产品资格声明。

## 1. 问题

`semantic_java`（P2-D）是 query-time only：每次会话查询都要重跑 JDT 批处理
（jgit 1891 文件量级 19.4s 本轮实测），且结果不落任何派生层。Stage-0 建议
"analysis 表持久化（独立立项）"。

## 2. 设计

### 2.1 写入路径

- 复用现有 `AnalysisStore.replace_analysis_for_file` 守卫写路径
  （payload 上限、依赖记录、freshness 记账全部沿用，无旁路）。
- 持久化粒度 = (repo, commit, file, contract)：
  - 每文件一个或多个 `java_call_binding` 节点，按 (line, expr, state) 排序后
    自适应分块（单节点 payload ≤ ~2.8KB，上限 4096B）；
  - 节点 id = SHA256(file_id, "java-jdt-persist", chunk_index)，确定性；
  - edges 恒为空（调用点决定是派生事实，不建图）。
- 原型使用临时注册槽 `ast:java-jdt` v1（进程内 `register_analyzer`）。
  生产化需要真正的 `semantic:*` feature 契约（KNOWN_FEATURES 扩展 +
  ANALYZER_VERSIONS 注册 + orchestrator 分发），本原型不改 `src/`。

### 2.2 Freshness 规则

完全复用现有规则，无新机制：

| 失效源 | 机制 |
|---|---|
| 源文件变化 | `base_source_hash`（file_state）不匹配 → stale |
| L1/ast 依赖变化 | `metadata.dependencies = {"ast:java": ast:java-v1}`，由统一 `dependency_staleness` 判定 |
| JDT jar/驱动变化 | classpath 指纹（jar 名+大小 SHA256）编入契约串 `java-ast-jdt-persist-v1+<fp12>`；读路径比对 metadata.contract |
| 版本升级 | `feature_version` 1 → N（`is_analysis_fresh` 判定） |

读路径 = `read_current_analysis` + contract 比对，与 `analysis_java_cfg` 检查
其 ast 依赖的模式一致。

### 2.3 边界保持（合同反例逐条核对）

- **不污染 L1**：持久化仅写 `ast:java-jdt` feature 行；三仓实测
  `ast:java` 行数 before/after 相等（results/*.json
  `l1_non_pollution.pass=true`）。首轮实测基线为 0（标准 index 流程
  不产生 `ast:java` 行，0=0 无鉴别力，复审指出后已修复）：复审后的
  重跑在持久化前先以标准 analyze 流程物化非零 `ast:java` 基线
  （hikaricp 77,487 行 / gson 222,638 行 / jgit 749,855 行），
  持久化写前后行数不变（`baseline_nonzero=true`），该检查现具有
  鉴别力。
- **默认 index 不触发 JVM**：orchestrator 硬编码分发，不读运行时注册表；
  注册只存在于原型进程内。fail-closed 自检：无 classpath 环境时
  `unavailable / jdt_classpath_not_configured`，持久化 0 行。
- **freshness 规则与 `analysis_state` 一致**：全部走现有 API，无自定 SQL 写入。
- **字节一致**：同输入两次持久化到两个 DB，逐文件 SHA256 全等（三仓 100%）。

## 3. 实测结果（Windows / Temurin 21.0.12.1+1 / Xmx1g）

复审后重跑（含 `--ast-baseline` 非零基线；环境与首轮同：T9-B 20-jar
套件，contract 指纹一致 `+12d0a50064c3`，同 pinned commit）：

| 指标 | HikariCP a4d93f4 | gson e2292f9 | jgit 6e68739 |
|---|---:|---:|---:|
| 文件数（持久化） | 94 | 216 | 1637 |
| ast:java 基线（标准 analyze 流程） | 77,487 行 | 222,638 行 | 749,855 行 |
| JDT 批处理 | 2.65s | 2.43s | 9.33s |
| merge | 0.029s | 0.119s | 1.44s |
| 持久化写 | 0.33s / 1604 节点 / 3.6MB | 0.91s / 5141 节点 / 12.2MB | 17.4s / 45475 节点 / 107MB |
| **持久化读延迟 avg（p95）** | **0.278ms（0.62）** | **0.398ms（1.06）** | **0.616ms（1.93）** |
| query-time 基线（重跑 JDT+merge） | 2.67s | 2.55s | 10.8s |
| 字节稳定 | 94/94 | 216/216 | 1637/1637 |
| 失效重建（单文件探测） | 2.96s | 7.93s | 60.1s |
| 探测后还原字节一致 | ✅ | ✅ | ✅ |
| fail-closed（无 classpath） | unavailable / 0 行 | 同 | 同 |
| L1 非污染（非零基线） | 77,487 → 77,487 | 222,638 → 222,638 | 749,855 → 749,855 |

与 stage0 数字的关系：本轮 gson `recovered_by_jdt` 9513 ≠ stage0 3228——
本轮覆盖全仓（含 `extras/` 与测试树）且 CALL_KIND_VERSION 可能随 1.4.0→1.5.0
演进；测量口径不同，不构成矛盾。raw 结果见 `results/*.json`。

### 已知限制（如实）

1. **失效重建是全批量的**：原型在任何失效后重跑整仓 index+JDT+merge
   （上表"失效重建"行）。单文件增量 JDT 是后续工作；持久化读路径不受影响。
2. **payload 存储成本**：jgit 107MB（含全部站点明细行）。生产化若只需
   (site → target) 决议，可裁剪 `l1` 侧明细，存储可再降一个量级。
3. **临时注册槽**：`ast:java-jdt` 仅为原型通道；正式 feature 契约另行走
   PR 的 src 变更（本 Issue 禁止）。

## 4. 结论与证据等级

- 可行性：**原型级证实**。三仓全部满足 Issue #5 的反例门（不污染 L1、
  默认 index 不触发 JVM、freshness 与 analysis_state 一致、同输入字节一致）。
- 收益：查询路径把每次会话 2.6–10.8s 的 JDT 重跑摊销为一次构建 +
  0.28–0.62ms/文件 的读，收益 3–4 个数量级。
- 立项建议：值得进入 feature 契约阶段（正式 analyzer id、增量失效、
  payload 裁剪三项为契约要点）；是否立项由 owner 依本证据决定。

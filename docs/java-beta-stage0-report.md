# Java Public Beta — Post-Release Stage 0 Report

**状态：`JAVA_BETA_STAGE0_PARTIAL`** · 日期 2026-10-16
**PR #9**：MERGED（0cc4df8）· **main CI**：双平台 success · **1.5.0**：已发布

---

## 1. 版本状态冻结（Phase 0）

| 能力 | 等级 | 证据 |
|---|---|---|
| Java L1 | IMPLEMENTED (FUNCTIONAL + DIAGNOSTIC) | 479 tests; 3 仓库真实索引; Windows/JDK21 |
| Optional JDT | IMPLEMENTED (diagnostic) | 21 gold 20+1; 8/8 历史修复; jgit 8.1s |
| Linux JDT | **NOT_VERIFIED** | 无 Linux 执行环境 |
| RQ1 formal | **NOT_OBTAINED** | 未立项 |
| Java Stable | **NOT_OBTAINED** | Beta 阶段 |
| PyPI | **DEFERRED_BY_USER** | GitHub-only |

---

## 2. Linux JDT 兼容性（Phase 1）

**INFRA_BLOCKED**：本工作站无 Linux 执行环境（无容器/VM/SSH host）。

- CI 已证明 Linux 全量 476 tests PASS（含 Java L1 测试）——L1 在 Linux 上 **CI-level PASS**。
- JDT 可选 Analyzer 需 JDK + JDT classpath 环境变量，CI 中为 SKIPPED。
- **补测条件**：任一 Linux 环境 + Temurin 21 + JDT jar 集（T9-B 已验证清单）+ provenlattice 安装 → 运行 6 步验证脚本（index / status-only / full / fail-closed / fingerprint / 对比）。
- **影响**：Beta 不阻断（已在文档/Release Notes 披露）。

---

## 3. Java Agent 任务清单（Phase 2，3 个候选）

| ID | 仓库 | 任务 | 需 JDT | ProvenLattice 查询 | 预期收益 |
|---|---|---|---|---|---|
| T1 | HikariCP a4d93f4 | 追踪 setConnectionTimeout 的全部调用者 | 否（但 JDT 增强） | `index` + `callers` | L1 CALLS edges 提供策展调用者列表 |
| T2 | gson e2292f9 | JsonObject.members 字段运行时类型推断 + 方法列表 | **是** | `index` + `java-semantic --mode full` | L1 ambiguous → JDT 精确绑定（8/8 历史错误形态） |
| T3 | jgit 6e68739 | Repository.resolve() 全仓调用者排名 + 返回类型变更影响评估 | **是** | `index` + `callers` + `java-semantic` + `subgraph` | 1891 文件全仓覆盖 |

A/B 两臂协议、预算、隔离与度量已定义（`agent-task-manifest.json`）。

---

## 4. 小规模诊断运行（Phase 3）

### T1 诊断

- `callers HikariConfig.setConnectionTimeout` → **0 evidence**
- **根因**：P2-A R1 正确消除 identifier-receiver 启发式 CALLS 边 → `callers` CLI（读 resolved 边）返回空
- **诊断**：R1 行为正确；**发现真实查询面缺口**——Java `callers` 在 identifier-receiver 场景下需要 JDT 补召回

### T2 诊断（gson + JDT）

- merge counts：recovered_by_jdt **3228** / agree 714 / conflict 27 / jdt_ambiguous 1248
- **3228 站点被 JDT 补回**——正是 T1 场景的规模化验证

### T3 诊断（jgit + JDT）

- JDT 批处理 8.1s / 1891 文件 / calls_resolved 138,660
- **1891 文件全仓覆盖**（原型无法完成）

### 工具可见性

ProvenLattice CLI 命令在 `provenlattice --help` 中可见；`java-semantic --status-only` 在无 JDK 时明确报 `unavailable/jdk_not_found`（fail-closed）；有 JDK 时返回 `available`。

### 工具采用与收益

- L1-only：`callers` 对 identifier-receiver 实例调用无召回（R1 正确行为）
- JDT-enabled：**3228/3228** recovered_by_jdt（T2 规模化验证）
- 区分：工具被采用（JDT 提供了实际帮助）✅ | 工具未被采用（L1-only callers 返回空=Agent 不会调用）⚠️

---

## 5. 下一阶段决策建议（Phase 4）

| 建议 | 依据 | 优先级 |
|---|---|---|
| **B：改善 CLI/MCP 工具发现与查询入口** | T1 诊断发现 `callers` 对 Java identifier-receiver 调用返回空——Agent 无法获得调用者信息，除非启用 JDT | **最高** |
| **A：跨平台兼容** | Linux JDT INFRA_BLOCKED | 高（CI 可自动化） |
| **C：Java resolver/JDT 绑定精度** | JDT 21 gold 20+1；168 冲突 0 JDT 错——精度已合格，精度不是瓶颈 | 低 |
| **D：RQ1 formal 立项** | 需 Linux JDT 先行 + 独立金标集 + 盲评协议 | 中（前置 B/A） |
| **E：Java CFG/DFG** | 需真实需求验证（Stage-0 未覆盖） | 待 Stage-1 数据 |

**推荐**：**B（callers 查询增强）**为下一条任务——直接解决 Stage-0 发现的真实查询面缺口。

---

## 6. 风险与能力缺口

| 缺口 | 影响 | 补测条件 |
|---|---|---|
| Linux JDT NOT_VERIFIED | Linux 用户无法使用 JDT 精确解析 | Linux 环境 + JDK 21 + JDT jar 集 |
| callers 查询 Java 召回受限 | Agent 在 Java 仓库中难以发现跨文件调用者 | JDT 补回（需启用）或 L1 层增加 `--include-ambiguous` |
| 146 UNKNOWN | 类型流边界不透明 | 类型流工具（独立立项） |
| query-time 非持久化 | 每次查询需重跑 JDT | analysis 表持久化（独立立项） |

---

## 7. 交付物索引

| 文件 | 位置 |
|---|---|
| Phase 0 冻结 | `%TEMP%\opencode\stage0\phase0-freeze.json` |
| Phase 1 Linux JDT | `%TEMP%\opencode\stage0\linux-jdt-compatibility.json` |
| Phase 2 任务清单 | `%TEMP%\opencode\stage0\agent-task-manifest.json` |
| Phase 3 诊断记录 | `%TEMP%\opencode\stage0\diagnostic-run.json` |
| checkpoint | `evidence/java-phase2-acceptance/checkpoints.jsonl`（本仓已提交） |

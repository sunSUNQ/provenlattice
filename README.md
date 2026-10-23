# ProvenLattice 1.6.0

**A Provenance-aware Code Knowledge and Analysis Platform for AI Agents**

ProvenLattice 是一个面向 AI Agent 的统一代码知识和语义分析平台。以轻量、确定性、可增量的代码知识图谱为基础，支持三大语言（Python / C/C++ / Java）与两大能力域：

* **Agent Development（日常开发辅助，默认核心）**：代码理解、调用关系与影响分析、Agent 编码/修复辅助、需求-代码关联、任务上下文生成；
* **Code Inspection（深度代码检测，可选高级）**：Semantic Events、Sparse CFG/DFG、八类缺陷候选查询、Evidence Bundle。

两大能力域共享底层事实、分析引擎和证据体系。长期规划见 [docs/roadmap.md](docs/roadmap.md) Gold Target V2 节。

## Motivation

当前 Code Agent 主要通过文件读取、代码搜索和工具调用理解大型代码仓库。

随着代码规模和工程复杂度增加，这种方式容易带来：

* 大量重复搜索与文件读取
* 跨文件、跨模块关系定位成本较高
* 代码与需求、设计、历史信息相互割裂
* Agent 上下文快速膨胀
* 缺陷检测依赖独立工具，证据不可追溯

ProvenLattice 探索一种新的工程上下文组织方式：

> 将代码仓库的结构、语义和缺陷信息组织成可查询、可追溯的分层证据结构，为 AI Agent 提供任务相关的最小必要上下文和按需深度分析。

## Architecture

```text
L1 Foundation Graph（默认启用，零检测开销）
│   index/update → Repository/File/Symbol/Call/Reference/Impact/Knowledge
│   Python + C/C++ + Java 确定性解析，resolved/ambiguous/unresolved 三态引用
│
L2 Unified Optional Analysis（按 Capability × Scope 按需物化）
│
│   ┌─ Agent Analysis ─────────────────────────────────────────┐
│   │ Python AST/CFG · C normalized AST/CFG · 短路 · 调用语义   │
│   └──────────────────────────────────────────────────────────┘
│   ┌─ Inspection Analysis ────────────────────────────────────┐
│   │ Semantic Events (15 类) · Sparse CFG · Sparse DFG         │
│   │ 8 类 Typed Defect Query · Evidence Bundle                 │
│   └──────────────────────────────────────────────────────────┘
│
L3 Task Services（Agent task-context · Defect query）
L4 Evidence & Results（统一证据契约，Candidate ≠ Verified）
L5 Exposure（CLI baseline · MCP passthrough）
```

> Full CFG 和 Sparse CFG 当前为两种独立实现；Canonical Control-Flow Model 属于长期演进目标。

## Quick Start

```bash
pip install -e .

# 1. 构建基础图谱（L1，默认轻量）
provenlattice index /path/to/repo --json

# 2. 基础查询
provenlattice symbol <name> --database /path/to/repo/.provenlattice/codegraph.db --json
provenlattice callers <symbol> --database /path/to/repo/.provenlattice/codegraph.db --json

# 3. Agent 分析（AST/CFG）
provenlattice analyze /path/to/repo --scope src --features ast,cfg --json
provenlattice analysis /path/to/repo --feature cfg --file-path src/foo.c --json

# 4. 任务上下文
provenlattice task-context <symbol> --database /path/to/repo/.provenlattice/codegraph.db --json

# 5. Code Inspection（按需，触发上游链 + 缺陷查询）
provenlattice analyze /path/to/repo --scope src --features defect --json
provenlattice defect /path/to/repo --type double_free --database /path/to/repo/.provenlattice/codegraph.db --json
provenlattice defect /path/to/repo --type use_after_free --json
provenlattice defect /path/to/repo --type null_flow --json
provenlattice defect /path/to/repo --type all --json

# 6. MCP（透明桥接，需 MCP 客户端配置后使用；见 Limitations）
#    mcp__provenlattice__query 为 MCP 协议内工具名，
#    不是 CLI 子命令。MCP stdio 客户端端到端验证已完成（4/4 PASS，
#    见 docs/v1.4-mcp-e2e-report.md）。
```

## V1.4 New Capabilities

| 能力 | 来源 | 说明 |
|---|---|---|
| Semantic Events (15 类) | PR #1 | 词汇表驱动的操作事件（CALL/ALLOC/RELEASE/LOCK/…），按需物化 |
| Sparse CFG | PR #1 | 事件点级控制可达（CONTROL_REACHES），含 CHECK/BRANCH/DEREF 结构事件 |
| Sparse DFG | PR #1 | 方法内 def→use（DATA_FLOW_TO）+ 别名链 + via 中间体 |
| 8 类 Defect Query | PR #1 | double_free/use_after_free/null_flow/resource_lifetime/lock_order/race_condition/taint_path/error_handling |
| Evidence Bundle | PR #1 | E-DEFECT-* id、facts、uncertain_facts、source_evidence、missing_evidence |
| Ownership Contracts | PR #1 | ContractTable + inferred ownership rules；declared TOML 数据未迁入 |
| Capability Contract | V1.4 | 统一能力注册（8 查询 + 3 analyzer），按 Capability × Scope 控制 |
| Dependency Freshness | V1.4 | `dependency_staleness()` 统一规则，上游变化自动失效下游缓存 |
| Composite PK (id, feature) | V1.4 | 跨 analyzer 同 ID 共存，旧库自动迁移 |
| Three-state Reachability | V1C-R1 | true / false / unknown — unknown 不当作不可达 |

## Java Support (P0, Foundation Graph)

Java 以 **tree-sitter 语法事实**接入默认 Foundation Graph（T1–T3，2026-10-15）：

```bash
provenlattice index /path/to/java-repo --json   # .java 文件自动识别
provenlattice symbol Helper --database /path/to/java-repo/.provenlattice/codegraph.db --json
provenlattice callers com.example.core.Helper.build --database ... --json
```

* **节点**：`Class`（class/enum/record）、`Interface`（interface/annotation）、`Method`（method/constructor/field/enum_constant）——全部复用既有冻结 kind，metadata 判别（`java_kind` / `java_member`）；包不建节点。
* **边**：`DEFINES` / `CONTAINS` / `IMPORTS` / `CALLS` / `REFERENCES` / `IMPLEMENTS`（extends/implements/throws 以 `java_relation` 区分）。
* **三态边界**：import/限定名/同文件/全局唯一 → `resolved`（0.75–1.0）；重载调用、跨包同名、通配 import 同名 → `ambiguous`（候选完整保留）；间接形状（`super.x()`、复杂 receiver、`Type::method`）、JDK/第三方类型、隐式默认构造 → `unresolved`。**不做重载判定与继承层级绑定**。
* **已记录提取 gap**：record 组件、注解元素、匿名类体、隐式默认构造不产出符号；局部变量/参数/lambda/模式变量不产出引用。
* **边界**：L1 为 tree-sitter 语法事实层；方法重载判定、继承层级绑定与完整类型流由**可选的 JDT 精确解析**提供（见下节）；record 组件、注解元素、匿名类体、隐式默认构造不提取（已记录 gap）；分/局部/lambda/模式变量不产出引用。

### 可选精确解析：`java-semantic`（Eclipse JDT Analyzer，已交付）

在 L1 之上提供一个**可选的**查询时精确解析增强（Eclipse JDT，独立 JVM 进程，按需启动，用完即退；**默认 index 永不启动 JVM**）。已经 P2-A/P2-D 集成与 P2-E 工程资格验证（G1–G6，`docs/java-phase2-p2e-final-qualification-report.md`）。

```bat
# 1. 环境要求（可选能力，未配置时 L1 完全不受影响）
set PL_JAVA_JDK=C:\path\to\jdk-21            # 需要 JDK（javac + java）
set PL_JAVA_JDT_CLASSPATH=C:\jars\org.eclipse.jdt.core.jar;C:\jars\...  # JDT 及其依赖 jar

# 2. 查看能力状态（fail-closed：缺 JDK/JDT 时明确报告 unavailable 及原因）
provenlattice java-semantic <repo> --status-only --json

# 3. 手工 Classpath 清单（P2-C 契约；一行一条，project:/dep: 角色，# 注释）
#    classpath.txt:
#    project: C:\repos\my-app\src\main\java
#    dep: C:\libs\slf4j-api.jar
provenlattice java-semantic <repo> --classpath-manifest classpath.txt --json

# 4. 查询结果：每个调用站点给出 L1 状态与 JDT 精确绑定对照
#    provenance=semantic:jdt-v1 + classpath 指纹可追溯；
#    recovered（依赖缺失伪造）绑定被过滤，歧义不会被升级为确定。
```

* **资源**：JVM `-Xmx1g`（默认）；实测 1.9k 文件仓库批处理 ~8s / 进程 RSS ~1.2GB
  （预算：RSS ≤1.6GB、批处理 ≤15s——已验证，正式预算批准待人工）。
* **限制**：外部依赖 jar 未入 classpath 的类型绑定被过滤（不伪造）；跨文件类型流
  样本中 147/225 无法建立独立真值（诚实边界）；query-time 结果**不持久化到 L1 图谱**；
  Maven/Gradle 不会被执行（classpath 手工提供）。
* **已验证**：479 项测试（Windows/Linux CI 双绿）、三真实仓库端到端、8/8 历史错误绑定修正、168 冲突抽样 0 JDT 错误。**未取得** RQ1 formal qualification。

## Validation

以下结果基于 aria2 语料（1,393 文件 / 165k LOC）在 5 轮交错配对运行中测量（1.4.0 基线）：

| 检查项 | 结果 |
|---|---|
| 全量测试 | **408/408 PASS** |
| L1 parity | **PASS**（node/edge id 逐 ID 相等） |
| 八类 defect CLI | **8/8 available** |
| 旧库 PK 迁移 | **8/8 PASS** |
| 默认 index 零检测产物 | **CONFIRMED** |
| 默认 index 耗时 | **6.77s**（5 轮配对中位，aria2，冻结 main 基线 = 6.77s） |
| 默认 RSS | **218.0MB**（中位数；合并后单次验证 = 6.94s / 218.1MB） |

> 性能数据基于特定测试语料和环境，不代表所有仓库的通用表现。
>
> **1.5.0 新增验证**（Java Public Beta，见 `docs/releases/v1.5.0.md` 与 postmerge
> 报告）：479 项测试 OK（Windows/Linux CI 双绿）；Java 真实仓库 HikariCP/gson/
> jgit 索引零失败；JGit L1 索引 25.1s；JDT 批处理 8.1s / RSS ~1.2GB；wheel/
> sdist 干净安装验证通过。

## Limitations

- 全部输出为 **Candidate**（`resolved` ≠ Verified Finding；`confidence` 为 heuristic score）
- `error_handling` 和 `taint_path` 仅 SMOKE + DIAGNOSTIC 级
- CONSUMES 仅覆盖直接传递形状（`f(malloc(n))`）
- goto 目标不建模；短路坍缩为单 BRANCH
- 无 SSA / points-to / 跨函数数据流边
- Python 缺陷检测链未验证
- Cold Store / declarations 重构未纳入 V1.4（归档于 `archive/pr1-full-merge`）
- Streaming Incremental 可在 legacy 单库布局下独立移植（不依赖 Cold Store），待独立 A/B 验证
- MCP defect 查询已完成端到端客户端验证（stdio JSON-RPC 真实 server 子进程，initialize/tools/list/8 类 defect query/stale fail-closed 全链路 4/4 PASS，测试 `tests/test_mcp_defect_e2e.py`，见 `docs/v1.4-mcp-e2e-report.md`；`mcp__provenlattice__query` 为 MCP 协议内工具名，非 CLI 子命令）
- `semantics/contracts.toml`（declared 所有权规则数据）和 `semantics/vocabularies/python.toml`（Python 事件词汇表）未迁入
- Java：L1 已交付（Public Beta）；可选 JDT 精确解析已交付（Windows/JDK21 已验证；Linux JDT VERIFIED——CI ubuntu-latest / Temurin 21 / Maven 钉扎套件，PR #14 CI，fixture 级跨平台对比，见 docs/linux-jdt-verification-report.md）；record 组件、注解元素、匿名类体、隐式默认构造不提取；SCIP INFRA_BLOCKED；Java 不具备 Stable 资格，RQ1 formal 未取得

## Documentation

| 文档 | 说明 |
|---|---|
| [docs/v1.4-integration-overview.md](docs/v1.4-integration-overview.md) | V1.4 整合背景、能力对照与架构 |
| [docs/capability-matrix.md](docs/capability-matrix.md) | 当前能力状态统一入口 |
| [docs/defect-query-guide.md](docs/defect-query-guide.md) | 缺陷查询使用指南 |
| [docs/roadmap.md](docs/roadmap.md) | Gold Target V2 长期路线 |
| [REPRODUCIBILITY.md](REPRODUCIBILITY.md) | 资格验证证据链 |
| [docs/releases/v1.5.0.md](docs/releases/v1.5.0.md) | **1.5.0 发布说明（Java Public Beta）** |
| [docs/releases/v1.4.md](docs/releases/v1.4.md) | V1.4 发布说明 |
| [docs/java-support-implementation-plan.md](docs/java-support-implementation-plan.md) | Java 支持设计与证据链 |
| [docs/pr1-merge-and-final-close.md](docs/pr1-merge-and-final-close.md) | PR1 整合最终收口报告 |
| [docs/pr1-diverged-main-reconciliation-audit.md](docs/pr1-diverged-main-reconciliation-audit.md) | 分叉审计与恢复方案 |
| [CHANGELOG.md](CHANGELOG.md) | 变更日志 |

## Research Direction

* 大规模代码结构建模
* 分层工程信息组织
* 跨层工程证据关联
* 增量图更新
* 面向 Code Agent 的结构化检索
* Graph-guided Context Retrieval
* 按需缺陷检测的 Evidence 语义

## Standalone Roadmap

```text
Core V0.3–V1.0 / RQ1 / RQ2 / SQI-V1–V1.2                    ✅ 正式资格
Analysis Layer D0–D8 (Python AST/CFG)                        ✅ QUALIFIED
Context Bundle / task-context-v0 / MCP / normalization-v2     ✅
C Analysis Chain A1–A3.6                                     ✅ diagnostic
Gold Target V2 双能力域架构                                    ✅ 规划冻结
─── V1.4 ───
Semantic Events / Sparse CFG / Sparse DFG                     ✅ 按需已交付
8 类 Typed Defect Query + Evidence Bundle                     ✅ 按需已交付
Capability Contract + 统一 freshness                          ✅ 已交付
Composite PK (id, feature) + 旧库迁移                          ✅ 已交付
三态可达性证据 (true/false/unknown)                            ✅ 已交付
Java Foundation Graph (P0, T1–T3)                              ✅ L1 已交付（21 用例 + 金样回归；无 L2）
─── 1.5.0（Java Public Beta）───
Java L1 完整工程资格（P2-A/P2-C/P2-D/P2-E）                      ✅ Engineering PASS
Optional JDT Semantic Analyzer（java-semantic）                 ✅ 已交付（diagnostic；Windows/JDK21 已验证）
Classpath manifest + Driver fingerprint 缓存                     ✅ 已交付
Linux JDT 验证 / JDK 矩阵                                       ✅ VERIFIED (ubuntu CI, PR #14, fixture 级) / 其他 JDK 组合未测
Java RQ1 formal / Stable 资格                                   ⬜ 未取得（独立立项）
─── 未来 ───
Canonical CFG / Full-Sparse 双视图收敛                          规划（Gold Target V2 Phase 3）
精确 alias / points-to / 跨函数数据流                           future candidate
完整 Taint Analysis / sanitizer                                future candidate
Python 缺陷检测链                                              future candidate
Cold Store / Streaming Incremental                             deferred (opt-in candidate)
CI / Plugin / SDK / REST                                      future candidate
```

## Status

✅ **1.5.0 = Java Public Beta（Agent Development + Code Inspection 双能力域平台 + Java 支持）**

- 479 项测试通过（417 主基线回归 + 62 Java/文档轮新增），Windows/Linux CI 双绿
- L1 parity PASS（Python/C/C++ 基础图谱零变化）
- Java：L1 已交付 + 可选 JDT 精确解析已交付（diagnostic 级；Public Beta 限制见上）
- 八类缺陷查询按需可用（local-only, diagnostic 级）
- GitHub Release：[provenlattice-v1.5.0](https://github.com/sunSUNQ/provenlattice/releases/tag/provenlattice-v1.5.0)（wheel/sdist SHA256 已验证）
- **当前安装渠道为 GitHub Release**（PyPI 尚未发布）

详细能力矩阵见 [docs/capability-matrix.md](docs/capability-matrix.md)。

---

**ProvenLattice 1.5.0**

*A Provenance-aware Code Knowledge and Analysis Platform for AI Agents*

# PR1 Main Merge Review

> 任务:PL-PR1-MAIN-MERGE-REVIEW(2026-10-12)
> 审查 HEAD:`86cafae`(含 qualification report)
> 冻结 main 基线:`14499f8`
> 集成分支:`integration/pr1-selective`(9 commits)
> 独立运行测试:408/408 PASS + L1 parity PASS(审查者自行运行,非采信报告)

---

## 1. 审查范围

### 提交链

| SHA | 描述 | 变更 |
|---|---|---|
| `3d081fb` | I1C baseline freeze | I0–I1-C + R1/I0R1 文档 |
| `f985d36` | I2A: defect + evidence (2/8) | defect_query.py + evidence.py + schema |
| `581d221` | I2A-R1: PK migration + isolation | analysis.py migration + 8 tests |
| `69b401c` | I2B1: use_after_free (3/8) | defect.py UAF block + 16 tests |
| `5937794` | Phase 0: UAF assertion strengthening | test assertions |
| `28eda07` | Overnight: all 8 queries (8/8) | defect.py full + contracts.py + taint.toml |
| `6f374e4` | Overnight report | docs |
| `d9a2388` | Final qualification: 26 per-query tests | tests + defect_query grade |
| `86cafae` | Qualification report | docs |

### 变更文件(38 files, +17,025 / -25)

**src/provenlattice/**(23 files):
`analysis.py`, `analysis_c_ast.py`, `analysis_c_cfg.py`, `analysis_c_dfg.py`(新),
`analysis_c_events.py`(新), `analysis_c_scfg.py`(新), `analysis_cfg.py`,
`analysis_query.py`, `analysis_semantic_common.py`(新), `cli.py`,
`contracts.py`(新), `defect.py`(重写), `defect_query.py`(新), `evidence.py`,
`identity.py`, `models.py`, `orchestrator.py`, `parsing/declarations.py`(新),
`parsing/events.py`(新), `semantics/__init__.py`(新), `semantics/defect_patterns.toml`(新),
`semantics/events.py`(新), `semantics/taint.toml`(新), `semantics/vocabularies/cpp.toml`(新),
`semantics/vocabularies/python.toml`(新), `semantics/vocabulary.py`(新),
`sparsecfg.py`, `sparsedfg.py`

**tests/**(15 files):12 个新测试文件 + 3 个既有测试修改

**docs/**(5 files):研究报告 + 资格报告

**零 diff 的 L1 关键文件**:graph.py, scanner.py, resolver.py, shard.py, overlay.py, mcp_server.py

---

## 2. 审查项与判定

### 2.1 架构与实现 — **PASS**

**五层架构兼容**:全部 Code Inspection 能力归属 L2 Unified Optional Analysis(查询时间读取器)+ L4 Evidence。defect 是 query-time capability(analyze 仅物化上游链,候选由 CLI `defect` 命令查询),不新增架构层。八类查询均为 Candidate 输出,不升级为 Verified Finding。

**L1 默认行为**:graph.py / scanner.py / resolver.py / shard.py / overlay.py **零 diff**。基础 index 不触发 Events / Sparse CFG / DFG / Defect 分析(I0 测试锁定)。L1 Symbol / Reference / Call / call_kind 语义不变。

**按需执行**:`defect` 在 FEATURE_DEPENDENCIES 中声明三个上游依赖(events, sparse_cfg, sparse_dfg);`analyze --features defect` 物化上游链(按需)。CLI `defect` 命令是纯读取器,零写操作(审计确认)。

**重复/硬编码/耦合**:defect.py 中 redis/llama 语料名仅出现在注释(设计文档引用),非硬编码逻辑。无 `test_`/`fixture_` 命名泄漏到产品代码。`analysis_semantic_common.py` 消除了 events/scfg 之间的 owner 对齐重复。

### 2.2 API 与消费端兼容性 — **PASS**

**grade/level 字段**:
- `analysis_query` envelope:通过 `_coverage()` 从 state metadata 透传 `level`/`grade`,仅对 sparse_cfg/sparse_dfg/events/sparse_dfg feature 存在;对 ast/cfg 返回不含这些 key——**additive,不破坏现有消费者**
- `defect_query` envelope:顶层 `grade`/`level`/`provenance.grade` 为新增 key;`status`/`candidates`/`coverage` 等既有 key 结构不变——additive
- CLI JSON:`defect` 命令返回完整 envelope;`--json` 透传 json.dumps——additive key 不影响已有解析
- MCP:mcp_server.py 零 diff,CLI 透传桥——新增命令自动可用

**响应路径**:available / stale / not_built / unknown_defect_query / base_graph_required 五条路径均经测试验证。`AnalysisRequestError` 统一处理为 `{"status": "failed", "error": {...}}` 结构。

### 2.3 存储与旧库兼容性 — **PASS**(1 WARN)

**PK 迁移**:`_migrate_pk_schema` 检测 `PRAGMA table_info` 的 PK 列;旧单列 PK → RENAME → CREATE 复合 PK → INSERT OR IGNORE 复制 → DROP 旧表。在 `AnalysisStore.__init__` 中调用,先于 `executescript(ANALYSIS_SCHEMA)`。

实测:200 行旧库迁移后行数/PK 集合/payload 保留;幂等(重打开不重迁移);事务安全(SQLite journal)。

**WARN**:迁移 DDL 中 `analysis_edges` 的 CREATE TABLE 硬编码了 `src_id`/`dst_id` 列名,与 ANALYSIS_SCHEMA 中通用 SQL 略有差异。**触发条件**:仅当未来添加新分析节点表时可能遗漏。**非阻断**——当前仅两张表。

**INSERT OR IGNORE**:仅在 (id, feature) 完全相同时忽略。旧单列 PK 表中 id 天然唯一,复合 PK 是超集,不可能丢弃有效行。

**只读模式**:`AnalysisStore.__init__` 执行 schema 创建 + 迁移检查,均为写操作。但这是 I2A 前就有的行为(executescript 在 I0 就存在)。纯查询通过已初始化的 DB 打开时,migration 是 no-op(PK 已正确)。只读打开未初始化的 DB 会尝试建表——这是 **I2A 前已有行为**,非新增风险。

### 2.4 八类查询语义 — **PASS**(2 DIAGNOSTIC)

| Query | 判定 | 审查结论 |
|---|---|---|
| resource_lifetime | FUNCTIONAL + DIAGNOSTIC | 正例泄漏/反例正常/contract gap 如实标注;`contracts_available: False` 是 fixture 限制 |
| lock_order | FUNCTIONAL + DIAGNOSTIC | 正例反序/反例同序;并发证明不在范围;`MAY_PARALLEL` 缺失入 missing_evidence |
| race_condition | FUNCTIONAL + DIAGNOSTIC | 仅 ambiguous(设计选择);参数 join 窄化登记 |
| null_flow | FUNCTIONAL + DIAGNOSTIC | `if(p){*p=1}` 已知 FP 保留在测试中;check-based elimination 逻辑与 PR 一致 |
| use_after_free | FUNCTIONAL_VALIDATED | 12 场景全过;别名缺口登记 |
| double_free | FUNCTIONAL_VALIDATED | 正例/互斥分支排除/realloc 阻断/stale 全过 |
| error_handling | SMOKE + DIAGNOSTIC | 可运行;依赖 CALLS 引用层扫描;精度受 API contract 限制 |
| taint_path | SMOKE + DIAGNOSTIC | 可运行;仅 4 source/3 sink;无 sanitizer/跨函数 |

**resolved ≠ Verified Finding**:`defect.py` 中无任何 "verified"/"Verified" 字符串(审计确认)。`provenance.resolved_is_not_verified` 字段显式声明。

**FP/FN 台账**:已知 FP(`if(p){*p=1}`)和 FN(别名/CONSUMES/SSA 缺失)在测试注释与资格报告中登记,未掩盖。

### 2.5 测试与证据 — **PASS**

**测试数量**:独立运行确认 **408/408 PASS**(非采信报告)。

**为什么 overnight 前后均为 382**:overnight 通过调用图闭包一次性移植了全部 8 个查询函数(5,473 行),但**没有为 6 个新查询添加独立测试**——仅靠 smoke 验证。本轮(I2C-R1)补写了 26 项 per-query 资格测试,使总数从 382 增至 408。**这是 overnight 的一个实际缺口,本轮已修复。**

**测试覆盖**:
- 26 项 per-query 资格测试(每类至少 positive/negative/stale/traceability)
- 8 项 PK 迁移测试
- 16 项 UAF 专项测试(12 场景)
- 16 项 I2A 专项测试(null_flow/double_free)
- 34 项 sparse 层测试(I1-B/I1-C)
- 14 项 I0 capability contract 测试
- 223+ 项 main 既有回归(含 L1 parity/sparse CFG golden tests)

**无固定夹具特殊实现**:defect.py 中无 `test_`/`fixture_` 命名;语料名(redis/llama)仅出现在注释中。

**冻结数据**:experiments/ 和 docs/benchmarks/ 零 diff。

### 2.6 合并风险 — **PASS**(1 WARN)

**回归风险**:
- L1 关键文件零 diff(graph/scanner/resolver/shard/overlay/mcp_server)
- 全量测试 408/408 包含 main 既有 223+ 回归(零失败)
- `analysis_c_cfg.py` 的 diff 仅含 I0R1 对齐修复 + I1-A 依赖门 + I1-B 依赖证明——均为防御性增强

**非阻断改进建议**:
1. `_migrate_pk_schema` 的 CREATE TABLE 语句可提取为共享 DDL 字符串,消除 analysis_nodes/edges 两处的列名重复
2. defect.py 中 500+ 行注释引用 redis/llama 语料测量数字——这些是设计文档引用,非硬编码,但在 main 上读起来可能造成混淆;长期可归入 docs/
3. `defect_query.py` 的 `_upstream_state` 对每个文件做 3 次 SQL 查询(三个 feature 各一次),大仓时可能成为查询延迟瓶颈;I1-C 实测显示这不是当前瓶颈

**无阻断问题**。

---

## 3. 综合判定

| 审查项 | 判定 |
|---|---|
| 架构与实现 | **PASS** |
| API 兼容性 | **PASS** |
| 存储与旧库兼容 | **PASS**(1 WARN:迁移 DDL 列名硬编码) |
| 八类查询语义 | **PASS**(6 FUNCTIONAL + 2 SMOKE,均为 DIAGNOSTIC) |
| 测试与证据 | **PASS**(408/408 独立确认) |
| 合并风险 | **PASS**(1 WARN:迁移 DDL 列名硬编码) |

### 最终判定:**READY_TO_MERGE**

### 附:非阻断改进建议

| # | 类型 | 描述 | 触发条件 | 建议 |
|---|---|---|---|---|
| 1 | WARN | `_migrate_pk_schema` CREATE TABLE 中 `analysis_edges` 的列名(`src_id`/`dst_id`/`kind`/`payload`)硬编码而非从 ANALYSIS_SCHEMA 提取 | 未来添加新分析表时可能遗漏 | 提取共享 DDL 或用 schema 驱动生成 |
| 2 | WARN | defect.py 中大量注释引用 redis-50/llama.cpp-69 的测量数字——这些是设计上下文而非当前代码行为的断言 | 阅读 defect.py 的贡献者可能误以为这些数字是当前 main 上的行为 | 长期将语料特定注释归入 docs/ |
| 3 | WARN | `defect_query._upstream_state` 对每个 feature × 每个文件各执行一次 SQL 查询 | 大仓(万级文件)时查询延迟可能上升 | 批量查询或 JOIN 优化 |
| 4 | INFO | `defect_query` 的 `names` 表从 nodes 表全量加载 Function/Method 行 | 大仓内存开销 | 按需加载或缓存 |
| 5 | INFO | `test_cfg_analysis.py` 中硬编码的 `"python-cfg-v1"` 已替换为 `PYTHON_CFG_CONTRACT` 常量——这是一次测试修改(非断言弱化),使测试版本无关 | cfg:python 未来版本升级时测试不会误报 | 保持 |

---

## 4. 自动化测试未覆盖的风险

1. **大仓 CONSUMES/INPUT_TO_SINK 精度**——当前仅人工夹具验证(3-5 个函数),未在 redis/llama 级语料上与 PR 结果做行级对比。风险:低(defect_query 逻辑与 PR 验证通过)。
2. **MCP 透传 `defect` 命令**——MCP 桥透传 CLI,理论上可用,但未做端到端 MCP 客户端验证。风险:极低。
3. **并发分析写入同一 DB**——多个 `analyze` 进程同时写同一 database 的行为未测试。SQLite WAL 模式应处理,但未验证。风险:低(单用户场景)。
4. **`test_cfg_analysis.py` 中 `PYTHON_CFG_CONTRACT` 的导入来源**——`analysis_cfg.py` 的版本从 1→2(依赖证明),已有测试使用了导入常量,未来版本升级不会破坏此测试。

---

## 5. 审查者声明

- 独立运行 408/408 测试(非采信报告)
- 独立运行 L1 parity(非采信报告)
- 独立审查了 analysis.py/defect.py/defect_query.py/contracts.py/evidence.py/orchestrator.py/cli.py/analysis_query.py/analysis_c_dfg.py/analysis_c_events.py/analysis_c_scfg.py/analysis_semantic_common.py/evidence.py/parsing/events.py/parsing/declarations.py/semantics/vocabulary.py 的完整源码
- 独立确认 graph.py/scanner.py/resolver.py/shard.py/overlay.py/mcp_server.py 零 diff
- 独立确认 experiments/ 和 docs/benchmarks/ 零 diff(冻结数据)
- 审查过程中未修改任何源码、测试或文档

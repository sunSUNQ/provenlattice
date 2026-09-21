# ProvenLattice Foundation Evidence Review — CodeGraph 基座能力证明

> 生成：`experiments/foundation_analysis/foundation_evidence_synthesis.py`
> 机器证据：`experiments/foundation_analysis/results/PROVENLATTICE-FOUNDATION-EVIDENCE.json`
> 原则：只使用现有正式 evidence；不重跑 benchmark；缺失指标标 `NOT_CAPTURED / NOT_TESTED / NOT_IMPLEMENTED`。

---

## 1. Executive Summary

ProvenLattice 的基座能力（CodeGraph / Engineering Evidence Foundation）**不是先做 Agent demo 再补图**，而是按

```text
图构得出来 → 图事实正确 → 大仓可运行 → 增量仍正确 → Agent 可消费 → 成本可控
```

的顺序逐层取得正式资格：

1. **图事实正确性（RQ1）= QUALIFIED**（限 V0.2、C/C++、CALLS/IMPORTS、三仓、冻结 V1 采样框）：174 例双盲 Gold，resolved precision **0.931**（样本）/ **0.8992**（加权总体）；主要限制是覆盖（尤其 CALLS），不是错选目标（错选 1 例 vs 漏解析 20 例）。
2. **大仓构建与增量一致性（RQ2）= QUALIFIED**（SYSTEMS_BENCHMARK_CONTRACT_V1 冻结 scope）：aria2 118,926 / brpc 227,154 / RocksDB 622,772 C/C++ LOC；21 条正式记录；**36/36 增量 rep 在六个状态层与 Full(B) 逐字节一致**；A/B scale 计数精确落在冻结锚点；0 无效执行、0 静默丢弃。
3. **Agent 消费（SQI-V1 / V1.2）= QUALIFIED**：SQI 18/18（vs Native 13/18 与 12/18 对照），citation closure 18/18；V1.2 成本 input −36% / output −58% / cache-read −73%（纵向对比带历史 backend caveat）。
4. **诚实的边界**：Overlay 为 IMPLEMENTED + PARTIALLY QUALIFIED（V0.4 工程级 parity/conflict 证据，未进冻结正式资格，V1.1 NOT STARTED）；增量延迟**高于**全量构建（正式记录在案，非门禁）；Query p95/p99（核心图查询）、并发 QPS、10M+ LOC、跨仓统一索引、向量索引、分布式同步 = 未测/未实现。

## 2. RQ1 Fidelity — "图里的事实能不能信？"

**Verdict: QUALIFIED**（P0 Graph Fidelity Qualification V1，2026-09-15 CLOSED；evidence level QUALIFIED，未到 REPLICATED/GENERALIZED）。

| RQ1 指标 | 结果 | 说明 |
| --- | ---: | --- |
| Gold Set | 174 例 | CALLS 86 + IMPORTS 88（REFERENCES population = 0，`GRAPH_REPRESENTATION_GAP`，不可评） |
| Resolved Precision（样本） | **0.9310** | 174 例非加权样本视图 |
| Resolved Precision（加权总体） | **0.8992** | 按冻结 population 权重还原（RocksDB CALLS_NONRESOLVED 层权重 0.5503） |
| Scoring | 108 正确 / 1 错选 / 20 漏解析 / 7 absent 上误解析 / 37 合理弃权 / 1 排除 | 每例恰好归入一个状态 |
| 覆盖 | 加权 target-opportunity coverage **0.2436** | 覆盖（而非错选）是主要限制 |
| CALLS | resolved precision 0.8571 | 全部 28 个归因失败均为 CALLS |
| IMPORTS | resolved precision 1.0 | 限冻结 benchmark 内，不得外推为"永远完美" |
| 失败机制归因 | 10 candidate-generation miss / 11 resolver abstention / 7 over-resolution | 三种机制需不同修复手段 |
| Annotation | 双标注员 + 盲评 | 盲评包 batch-02..05、blindness provenance audit |
| Calibration gate | `CALIBRATION_QUALIFIED_WITH_DOCUMENTED_DEVIATIONS` | 25 例校准（协议 commit `12f405c6`）；9 个 Python 例划出 C/C++ 计分域 |
| 分歧裁决 | cohort reconciliation | calibration 14/16 agreed；batch_02 34/38；batch_03 38/40；batch_04 32/41；batch_05 见 gold freeze manifest；最终 `final-cpp-adjudication.json` |

**结论**：在该冻结 benchmark 内，"resolved 的可评 C/C++ CALLS/IMPORTS 关系语义目标通常正确"成立；同时不得压缩成单一准确率数字，不得声称 REFERENCES 可靠或泛化到任意语言/仓库。

来源：`experiments/fidelity_v1/results/rq1-graph-fidelity-evidence-synthesis-v1.{json,md}`、`gold/gold-freeze-manifest.json`（SEALED_FROZEN）、`results/calibration-gate-01.json`、`results/p0-graph-fidelity-qualification-v1-freeze.md`。

## 3. Repository Scale（正式 artifact 核验）

| Repo | Role | Frozen Commit | C/C++ LOC | Files* | Symbols* | Nodes | Raw References | Edges |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B1 aria2 | Small Regression | `9e727358` | 118,926 | 1,168 | 27,936 | 29,117 | 49,109 | 37,074 |
| B2 brpc | Target-like Primary | `ae09e960` | 227,154 | 1,168 | 47,688 | 48,929 | 84,941 | 59,614 |
| B3 RocksDB | Scale | `37234200` | 622,772 | 1,478 | 117,097 | 118,655 | 311,111 | 143,585 |

\* Files/Symbols 取自正式记录 `QUALIFICATION-V1-*-A.json` 的 `derived.normalized_median.cost_denominators`（formal runner 记录的归一化分母）。三条记录即如此记载（B1 与 B2 的 files 分母同为 1,168，按正式记录原样报告，未做任何"修正"）。

知识层规模（B2 brpc，V1.0 正式 baseline）：knowledge nodes 1,404 · document sections 1,255 · raw evidence links 736（resolved 80 / ambiguous 202 / unresolved 454）· cross-layer edges 80。

## 4. Full Build

Workload A（cold full build，5 measured reps/repo，warmup 1；正式记录含 p95/p99/min/max）：

| Repo | A median | A p95 | A min–max | Peak RSS median | DB size median |
| --- | ---: | ---: | --- | ---: | ---: |
| B1 aria2 | 4,494.126 ms | 4,812 ms | 4,372–4,812 ms | 191 MB | 126.8 MB |
| B2 brpc | 8,337.305 ms | 14,844 ms | 8,078–14,844 ms | 314 MB | 229.1 MB |
| B3 RocksDB | 28,238.675 ms | 28,921 ms | 27,556–28,921 ms | 1,075 MB | 843.2 MB |

Workload B（warm repeated build，5 reps/repo）：medians 4,561.364 / 9,819.849 / 29,669.906 ms。A/B 六条记录的 scale 计数全部**精确**落在冻结 v0.2 OBSERVED 锚点（±10% 异常带中心），5.2× LOC 范围内无漂移。v0.2 OBSERVED 锚点本身（单次运行 baseline，manifest 明示"NOT qualification results"）：full index 3.95/7.59/26.19 s，peak memory 195.6/323.9/1,121.5 MB，DB 132/237/876 MB。

## 5. Incremental A→B（资格链）

正式流程（与 runner `tools/run-systems-workload-v1.py` 及 superseded 文档记载一致）：

```text
Original Repository A (frozen commit)
        ↓  copy frozen A
Full Build(A) initial index
        ↓  baseline-A verification against frozen file hashes
Apply Frozen Mutation (M1–M4, sha256-pinned ops)
        ↓  workload_c_gate hard gate: mutation_pre_sha256 != mutation_post_sha256
Incremental Update A → B
        ↓  freshness probe（同一次 sequential child 内观测到 state B）
Fresh Full Build(B)
        ↓
Compare Incremental(B) vs Full(B)：六状态层 digest 全等 + strict digest
```

**历史缺陷如何被发现与修复（证据链完整，负结果未隐藏）**：

1. 早期 runner 把 mutation 应用在 initial index **之前** → 初始 DB 已是 B 态 → 增量观察到 `changed=false, files_changed_reported=0` → **B-vs-B 假 parity**。34 条 pre-freeze `SYSV1-*` 记录被标记 **SUPERSEDED**（保留不删除，`results/SUPERSEDED-workload-c-mutation-order.md`，blocker `WORKLOAD_C_MUTATION_ORDER` = contract delta review C1）。
2. 修正后 runner（copy A → Full(A) → baseline 验证 → mutation → Incremental A→B → freshness probe → Full(B) → exact parity，含 `workload_c_gate` 硬门）**诚实暴露**了真实引擎缺陷：M3 delete-file 在 B2/B3 上 `raw_references` parity FAIL（raw-reference cache 在符号删除后仍复用失效 candidate）。
3. 引擎修复：`src/provenlattice/resolver.py` 强制 cache 复用不变量（resolved id 与全部 candidate ids 必须仍存在）+ 集成回归测试；M3 B2/B3 定向 smoke PASS（`SYSV1-B2BRPC-C-20260916T061945Z` / `SYSV1-B3ROCKSDB-C-20260916T062127Z`）。
4. 正式资格：**36 条 formal incremental reps（3 repo × 4 mutation family × 3 reps）36/36 PASS**（`QUALIFICATION-V1-B*-C-M*.json`，2026-09-16）。M3 `files_reparsed=0` 为设计使然（删除文件无需重解析），`files_changed_reported=1` 证明删除被检测。

## 6. State Parity（多状态层）

正式记录中的**准确状态层名称**（`rq2-cross-system-synthesis-v1.json.generality_findings.exact_parity`）：

```text
nodes_facts
edges_facts
raw_references_facts
shards_facts
files_facts
shard_edges_facts
```

36/36 rep 中，Incremental(B) 与 clean Full(B) 在以上六层 digest 全等，且 `raw_references_strict` strict digest parity 36/36；A/B/D 的 anchor 计数与 qualified-name 锚点校验全部 PASS。

## 7. Graph Entity Scale

见 §3 表（formal records）；补充 Shard（V0.3 正式 shard benchmark，`docs/benchmarks/provenlattice-v0.3-shard.json`；RQ2 formal 协议统一使用 `directory` 策略）：

| Repo | Directory shards | Structural shards | Build-aware shards | Boundary ratio (dir) |
| --- | ---: | ---: | ---: | ---: |
| B1 aria2 | 8 | 21 | 8 | 3.66% |
| B2 brpc | 46 | 56 | 40 | 7.20% |
| B3 RocksDB | 64 | 70 | 59 | 8.14% |

Cross-layer links：80（B2 brpc，V1.0 knowledge baseline）。Knowledge sections：1,255（brpc）。Calls/call edges 未作为独立计数单独记录于 formal RQ2 记录（edges 为 resolved-edge 总数）→ 该细分列 **NOT_CAPTURED**（不另行拆算）。

## 8. Query Performance

**当前已测（RQ2 Workload D，正式）**：每 repo 30 warm measured rounds × 每查询类型 150 样本（callees/callers/subgraph/symbol），共 **1,800 warm 样本**；执行顺序 `manifest_file_order` 冻结、anchor 校验 `qualified_name_exact_match`、查询 manifest SHA-256 封存；正式汇总指标为 **warm median**（原始逐样本延迟保留在记录中）：

| Query type | B1 aria2 | B2 brpc | B3 RocksDB |
| --- | ---: | ---: | ---: |
| callees | 20.78 ms | 32.17 ms | 74.10 ms |
| callers | 47.86 ms | 33.64 ms | 166.31 ms |
| subgraph | 44.36 ms | 39.16 ms | 70.03 ms |
| symbol | 19.82 ms | 26.78 ms | 62.30 ms |

Medians 随 repo 规模单调增长（callees 20.8→32.2→74.1 ms；symbol 19.8→26.8→62.3 ms）。附：知识层查询（B2，30 样本）evidence_lookup p50 0.56 / p95 1.27 ms；document_to_code p50 24.4 / p95 27.2 ms；cross_layer_subgraph p50 23.2 / p95 26.2 ms。Overlay 符号查询（V0.4，20 样本本机基线）branch P95 开销 < 6%。

**边界（必须如实区分）**：

- 核心图查询的 **p95/p99 未在正式汇总中报告**（逐样本原始值在记录中可复核）→ `NOT_CAPTURED`（p99 全线）/ p95 仅知识层与 overlay 基线有正式值；
- 并发 QPS、毫秒级 SLA 负载测试：`NOT_TESTED`（Contract V1 明确排除并发）；
- "毫秒级查询"当前**只能**表述为：warm median 20–166 ms 区间的正式单机测量，是实测数据而非 SLA 承诺；领导长期目标（毫秒级查询 SLA）尚未成为已验证能力。

## 9. Overlay Status

**状态：IMPLEMENTED + PARTIALLY QUALIFIED**（不得写成完整正式资格）。

- **已实现**（`src/provenlattice/overlay.py`，23 KB）：Branch（持久）/ Session（临时）Overlay，`GraphView` 按 Session > Branch > Base 合成，DELETE tombstone，`REBASE_REQUIRED`，冲突体系（`NO_CONFLICT` / `ENTITY_CONFLICT` / `DELETE_UPDATE_CONFLICT` / `ADD_ADD_CONFLICT` / `BOUNDARY_CONFLICT`），session commit-to-branch / discard，兼容 rebase（B1/B2 分别 8.669/11.663 ms，只重算 1 个 shard）。
- **工程级验证**（`docs/benchmarks/provenlattice-v0.4-overlay.json` + `provenlattice-v0.4-conflicts.json` + `tests/test_overlay.py`）：真实 B1/B2/B3 单文件 body-only 修改 overlay **materialization parity PASS**；delta 大小仅占 Base 的 0.1848% / 0.0563% / 0.2664%；apply 2,312 / 3,953 / 15,014 ms；B1/B2 lifecycle/conflict matrix PASS；branch 查询 P95 开销 < 6%。
- **未做**：未纳入 SYSTEMS_BENCHMARK_CONTRACT_V1 冻结正式资格（baseline 仅单文件 body-only 一类修改）；Overlay V1.1 = **NOT STARTED**（REPRODUCIBILITY.md）；SQI-V1.2 发布明确未包含 Overlay V1.1。

## 10. Language Support

| Language | Parser | Formal Evidence | Status |
| --- | --- | --- | --- |
| C | tree-sitter `CppTreeSitterParser("c")` | RQ1 + RQ2 正式（aria2/brpc/RocksDB） | QUALIFIED（限冻结 scope） |
| C++ | tree-sitter `CppTreeSitterParser("cpp")` | RQ1 + RQ2 正式（aria2/brpc/RocksDB） | QUALIFIED（限冻结 scope） |
| Python | tree-sitter `TreeSitterParser` | parser 已实现；RQ2 formal runner 扫描 `['c','cpp','python']`；RQ1 校准门把 9 个 Python pilot 例划出 C/C++ 计分域（OUT_OF_SCOPE，保留在 audit 包） | IMPLEMENTED / NOT YET QUALIFIED |

复杂宏展开、模板实例化、函数指针、虚调用、复杂重载按 contract 保持 ambiguous/unresolved，不强行生成错误 Edge（保守 resolver 设计）。

## 11. Target Architecture Mapping（谨慎版，全部有 evidence 依据）

| Target Layer | Existing ProvenLattice Capability | Evidence | Gap |
| --- | --- | --- | --- |
| 应用接入层 | SQI 七类规范化 envelope（预算有界、可引用、citation closure）+ CLI | SQI-V1/V1.2 formal | IDE / CI / web 接入面未建 |
| 服务编排层 | 进程内 query API + 会话纪律 + per-session call log | SQI formal call logs、session tests | 多租户服务平台化 NOT_TESTED |
| 计算引擎层 | 解析/candidate/resolver/shard/incremental/impact frontier | RQ1 QUALIFIED、RQ2 QUALIFIED、V0.3 shard | CALLS 覆盖修复 deferred（≠fixed）；REFERENCES 表示缺口 |
| 存储引擎层 | 单机 SQLite、六状态层、反向 boundary 索引 | RQ2 36/36 parity；db_size/peak_rss 正式记录 | 非 SQLite backend abstraction NOT_STARTED |
| 同步协调层 | 增量 freshness/parity 链（36/36）+ V0.4 overlay delta | RQ2 workload C；V0.4 artifacts | CDC / replication / 分布式一致性 NOT_IMPLEMENTED |
| 图谱索引 | 六状态层 + shard/boundary edges + qualified-name 索引 | RQ2 锚点精确 + D 锚点校验 | S3+ 规模带 NOT_TESTED |
| 全局索引（多仓统一） | 无（各仓独立 DB） | — | NOT_TESTED / NOT_STARTED |
| 向量索引 | 无（V1.0 明确排除 Embedding/Vector DB） | release scope 声明 | NOT_IMPLEMENTED |

## 12. Current Gaps（当前缺口汇总）

| 指标 | 状态 |
| --- | --- |
| Peak Memory（formal reps） | AVAILABLE（191/314/1,075 MB medians） |
| DB Size | AVAILABLE（126.8/229.1/843.2 MB medians） |
| Cold Build / Warm Build | AVAILABLE（A/B workloads） |
| Incremental Latency | AVAILABLE（且正式记录：**高于** full build，非门禁观察） |
| Query p95（核心图查询） | NOT_CAPTURED（正式汇总仅 median；逐样本在档） |
| Query p99 | NOT_CAPTURED |
| Concurrent QPS | NOT_TESTED |
| 10M+ LOC | NOT_TESTED（最大正式带 622.8k） |
| Multi-Repo 统一索引 / Cross-Repo | NOT_TESTED |
| Vector Retrieval | NOT_IMPLEMENTED |
| Distributed Sync / CDC | NOT_IMPLEMENTED |
| C4 agent cell duration | NOT_CAPTURED |

**Incremental 性能的正确表述**：增量**正确性**已 QUALIFIED（36/36）；"增量是否比全量快"是独立的性能问题——正式数据显示当前 B1/B2/B3 全部出现 incremental latency > cold full build（例如 B3：37.7–47.5 s vs 28.2 s；B1：5.6–6.0 s vs 4.5 s），按 Contract V1 §6 记为 OBSERVED_ONLY 非门禁观察，归因到 Before/After 优化线。

## 13. Report-Ready Tables

### 基座能力总表

| 基座能力 | 验证方式 | 当前结果 | 状态 |
| --- | --- | --- | --- |
| 图事实正确性 | RQ1 Fidelity（174 例双盲 Gold） | resolved precision 0.931 / 0.899（加权）；覆盖是主要限制 | QUALIFIED（限冻结 scope） |
| 大仓图构建 | aria2/brpc/RocksDB A/B（5+5 reps） | 118.9k/227.2k/622.8k LOC；计数精确落锚点 | QUALIFIED（Contract V1） |
| Incremental correctness | A→B vs Full(B)（4 mutation × 3 repo × 3 reps） | 36/36 hard gate + freshness + parity | QUALIFIED（Contract V1） |
| Multi-state parity | 六状态层 digest 精确比较 | nodes/edges/raw_references/shards/files/shard_edges 36/36 | QUALIFIED（Contract V1） |
| Query correctness | SQI formal（36 cells ×2 代） | 18/18；citation closure 18/18 | QUALIFIED |
| Agent consumption | SQI-V1 + C4-R4 formal batches | SQI 18/18 vs Native 13/18 与 12/18 | QUALIFIED |
| Cost control | C0–C4 归因 + V1.2 优化 | input −36% / output −58% / cache-read −73% | QUALIFIED / RELEASE READY |
| Overlay | V0.4 工程 parity/conflict + unittests | parity PASS、delta 0.06–0.27%、冲突矩阵 PASS | IMPLEMENTED / PARTIALLY QUALIFIED |
| Knowledge layer | V1.0 unittests + B2 baseline + SQI T05/T06 | 1,404 nodes / 1,255 sections / 80 cross-layer edges | IMPLEMENTED；Agent 消费经 SQI QUALIFIED |
| Multi-Repo | 三仓同一冻结协议（独立 DB） | 无统一跨仓索引/查询 | PARTIAL；统一索引 NOT_TESTED |
| Vector Retrieval | — | 明确排除 | NOT_IMPLEMENTED |
| Distributed Sync | — | 单机 scope | NOT_IMPLEMENTED |

### 证据链图（汇报/PPT 用）

```text
Source / Docs
    ↓
Graph Build（tree-sitter C/C++/Python；六状态层；shard/boundary 索引）
    ↓
RQ1 Fidelity V1 ──── 图事实是否可信（QUALIFIED：0.931 / 0.899，覆盖受限）
    ↓
RQ2 Systems V1 ──── 大仓能否构建（118.9k / 227.2k / 622.8k LOC）
    │                 ├─ Incremental A→B（36/36 hard gate + freshness）
    │                 └─ Full(B) exact parity（六状态层逐字节一致）
    ↓
SQI ─────────────── 图能否被 Agent 稳定查询（有界 envelope + citation closure）
    ↓
Agent Formal Qualification ──── SQI 18/18（36-cell formal batches ×2 代）
    ↓
V1.2 Cost Optimization ──── input −36% / output −58% / cache-read −73%
    ↓
Code Agent / Code Detection / IDE / CI（接口边界已定义，见 §14）
```

## 14. Evidence Index（溯源）

| 结论 | 来源 artifact |
| --- | --- |
| RQ1 QUALIFIED、0.931/0.899、174 Gold、归因 10/11/7 | `experiments/fidelity_v1/results/rq1-graph-fidelity-evidence-synthesis-v1.{json,md}`（sha256 封存） |
| Gold 冻结与双盲裁决 | `experiments/fidelity_v1/gold/gold-freeze-manifest.json`（SEALED_FROZEN）、`final-cpp-adjudication.json`、`results/blind-agreement-audit-*.md` |
| 校准门 / Python 划域 | `experiments/fidelity_v1/results/calibration-gate-01.json`（协议 commit `12f405c6`） |
| RQ2 QUALIFIED、21 records、36/36、六状态层、latency inversion | `experiments/systems_v1/results/rq2-cross-system-synthesis-v1.json`、`reviews/rq2-final-qualification-review.md` |
| Repo/LOC/commit/DB/内存锚点 | `experiments/systems_v1/manifests/benchmarks-v1.json` |
| M1–M4 定义与 deferred 清单 | `experiments/systems_v1/manifests/mutations-{aria2,brpc,rocksdb}-v1.json` |
| B-vs-B 缺陷与 superseded 记录 | `experiments/systems_v1/results/SUPERSEDED-workload-c-mutation-order.md` |
| M3 引擎缺陷与修复 | `experiments/systems_v1/reviews/workload-c-m3-delete-invalidation-review.md` |
| formal build 统计（p95/p99/RSS/DB） | `experiments/systems_v1/results/QUALIFICATION-V1-B*-A.json` |
| Shard 统计 | `docs/benchmarks/provenlattice-v0.3-shard.json` |
| Overlay parity/冲突/延迟 | `docs/benchmarks/provenlattice-v0.4-overlay.json`、`provenlattice-v0.4-conflicts.json`、`provenlattice-v0.4-overlay.md` |
| Knowledge 规模与查询 | `docs/benchmarks/provenlattice-v1.0-knowledge.json` |
| SQI-V1 / V1.2 / C4-R4 横向 | `experiments/query_interface_v1/results/formal/SQI-FORMAL-20260917-1/`、`C4-R4-SYNTHESIS-20260920-175458.json`、`results/analysis/C4-R4-NATIVE-VS-SQI-V1.2.json` |
| 状态总账 | `REPRODUCIBILITY.md`、`CHANGELOG.md`、`docs/provenlattice-evidence-inventory-gap-matrix-v1.md` |

## 15. 三条团队方向的接口边界（共用同一 Evidence Graph / Identity / Provenance contract）

**A. Graph Storage**
输入：Frozen Graph Semantics（六状态层 + identity/provenance contract）、Frozen Query Workloads（RQ2 D manifests）。
研究面：Storage Backend（非 SQLite abstraction）、Build、Incremental、Traversal、Concurrency、Footprint。
已有基座：36/36 parity 语义 = 任何新 backend 的正确性 oracle。

**B. Code Detection**
输入：Finding（file/line/rule）→ 经 ProvenLattice：Symbol / Call / Reference / Impact / Requirement / Evidence → 输出：Evidence-Enriched Finding。
已有基座：`E-*` evidence id 契约 + citation closure + impact.frontier（T04 formal 3/3）。

**C. Agent**
输入：Engineering Task → 经 SQI / Evidence API → 输出：Answer / Fix / Review。
已有基座：SQI 7 类查询 + 预算/纪律/缓存 + 36-cell formal 资格 + V1.2 成本优化。

三条线共用同一套：**Stable Identity（repository+path+kind+qualified name+signature）、六状态层图语义、`E-*` 证据 id 与 provenance 契约**——这是"底座"的真正含义。

# Structured Query Interface Contract V1 (SQI-V1)

> **P2 / RQ3–RQ6 — Agent-Facing Structured Query Interface V1**
>
> serves: RQ3 (检索质量, Track C) / RQ4 (证据效率, Track D) / RQ5 (Agent 采用, Track E) / RQ6 (任务级效果, Track F)
> 前置: RQ1 = QUALIFIED (2026-09-15); RQ2 = QUALIFIED (2026-09-16, 限 Contract V1 scope)
> 状态: **CONTRACT FROZEN (V1)** — 本文件冻结接口语义与 qualification 用例;实现与 runner 在正式 run 前另行冻结。
> 日期: 2026-09-16

## 0. 本线定位

RQ2 已证明:同一冻结 Contract 下,ProvenLattice 在 aria2/brpc/RocksDB 三个异构仓库上
保持 incremental freshness、exact parity、查询语义与规模测量稳定。**RQ2 线已收口,
不再向其中加入新实验。**

本线把已资格化的底座查询能力产品化为 **Agent 可稳定消费的结构化只读查询接口**,
并以其为被测对象做任务级 qualification。R1(retrieval-v1)暴露底层图操作、
R2(retrieval-v2)引入预算化 EvidenceBundle 的经验教训是本 contract 的直接输入:
底层能力不缺,缺的是**有界、可引用、可验证、可审计**的 Agent 查询面。

## 1. 范围与非目标

**V1 范围(只读)**:

- 单仓、单快照(frozen commit-matched DB)上的 6 个 canonical 只读查询(§3)。
- 统一 JSON envelope(§4)、强制 provenance(§6)、强制预算与截断语义(§7)。
- Knowledge 层经锚点暴露(§5),Overlay **排除**(V1.1 deferred,§5.5)。

**V1 非目标**:

- 不做写入、不做索引构建/增量维护(那是 RQ2 线已资格化的能力,本线只消费其产物)。
- 不引入 embeddings、LLM reranker、MCP server、TASCO、history/log。
- 不做多仓联合查询;不做会话/分支 Overlay 读路径。
- 不声称任务级效果提升(RQ6 结论待本线 qualification 之后)。

## 2. 被测实现基线

- ProvenLattice V0.2/V1.0 实现(与 RQ2 qualification 所测同一实现,冻结 commit)。
- 输入 DB: `benchmark-analysis/v0.2-db/{aria2,brpc,rocksdb}.db` 与
  `benchmark-analysis/v1.0-db/brpc-knowledge.db`(均为 RQ1/RQ2 冻结 commit 匹配产物)。
- 三仓 frozen commits:
  B1-aria2 `9e7273583f83e881e3ec067b523ba88724088d2f`;
  B2-brpc `ae09e960c7291605dda52356cc0c2d45567fb53e`;
  B3-rocksdb `37234200b57d8d0a6a5c41f2d9811bbd2e293544`。

## 3. V1 查询面(冻结,共 6 个 canonical calls)

首批链路:`symbol lookup → callers/callees → reference evidence → impact frontier → requirement/code evidence`。

| # | call | 输入 | 语义 | 输出主体 |
| --- | --- | --- | --- | --- |
| Q1 | `symbol.lookup` | `name`(必填), `kind?`, `path_prefix?` | 按 name 匹配 symbol(fuzzy→exact 一致于实现),返回 symbol 身份行 | symbols[] + `CODE_DEFINITION` evidence |
| Q2 | `symbol.callers` / `symbol.callees` | `symbol_id` 或 `qualified_name`(必填) | 沿 `CALLS` 边的入/出邻居 | edges[] + 对端 symbols[] + `CALL_RELATION` evidence |
| Q3 | `symbol.references` | `symbol_id`(必填), `status?`(resolved/unresolved) | 该 symbol 的 raw references 及解析状态 | raw_refs[] + `REFERENCE` evidence |
| Q4 | `impact.frontier` | `changed_shard_paths[]`(必填), `threshold?=8` | 当前快照上,受 changed shards 的 boundary 边直接影响的 1-hop shard 集合(保守前沿) | affected_shards[] + boundary edge ids + `wide_impact` flag + `SHARD_RELATION` evidence |
| Q5 | `code.related` | `document`(path 或 section 锚点,必填) | 文档段落 → 已实现代码 symbol 的跨层关联 | code symbols[] + `DOCUMENT_SECTION` + `CROSS_LAYER_LINK` evidence |
| Q6 | `bundle.explain` | `symbol`(必填), budget(§7) | 上述链路的单次预算化组合(EvidenceBundle) | bundle: symbols/edges/raw_refs/sections + evidence |

规则:

- R1.查询只允许上述 6 类;未列出的底层方法(`get_subgraph`、`get_evidence_links`、
  `get_requirements` 等)在 V1 不对 Agent 暴露,仅作为内部实现或 evaluator 侧工具。
- R2.每个 call 必须幂等、只读、确定性:同一 DB + 同一输入 ⇒ 逐字节相同输出(除
  `query_id`、`query_time_ms` 两个显式标注的 non-deterministic 字段)。
- R3.错误一律结构化返回(`error.code` + `error.message`),错误也是 schema 校验的
  一部分;禁止把异常栈直接抛给 Agent。

## 4. 统一输入/输出 schema

**输出 envelope(每个 call 必填字段)**:

```json
{
  "query_id": "Q-<16hex>",
  "query_type": "symbol.lookup | symbol.callers | symbol.callees | symbol.references | impact.frontier | code.related | bundle.explain",
  "anchor": "<echo of primary input>",
  "params": { "<echo of all inputs>" },
  "repository": "repo:<id>",
  "commit": "<frozen commit sha>",
  "graph_generation": 1,
  "data": [ ... ],
  "evidence": [ { "evidence_id", "kind", "source_id", "relation", "target_id", "repository", "source_path", "source_range", "confidence", "provenance", "summary" } ],
  "returned_evidence_ids": ["E-*"],
  "returned_evidence_count": 0,
  "bundle_size": 0,
  "truncation": { "truncated": false, "omitted_counts": { "symbols": 0, "edges": 0, "raw_refs": 0, "sections": 0 } },
  "query_time_ms": 0.0
}
```

**约束**:

- C1.任何出现在 `data` 中的 fact(symbol/edge/raw_ref/section/shard relation)必须有
  对应 `evidence` 条目且其 `evidence_id` 出现在 `returned_evidence_ids` 中;反之
  evidence 不得引用未返回的 fact(允许 evidence 描述边界,见 §7 T1)。
- C2.evidence_id 确定性派生自 fact identity(kind, repository, source_id, relation,
  target),与查询顺序、graph generation、Agent session 无关(R2 既有规则,继承)。
- C3.`truncation.truncated=true` 时必须给出各类 `omitted_counts`;禁止静默截断。
- C4.schema(JSON Schema,`schema/sqi-envelope-v1.json`,实现阶段冻结)校验 PASS
  才算有效调用;校验失败按 `INVALID_CALL` 记录,不进入能力指标。

## 5. 各层暴露程度(V1 冻结)

### 5.1 Symbol 层 — 完整暴露(只读)

身份(`symbol_id`、`qualified_name`、`kind`、`language`)、位置(`file_id` +
`relative_path`、`start_line`/`end_line`)、`signature`、`shard_id`。不暴露:
source_hash 之外的源码正文、generation 计数器之外的构建历史。

### 5.2 Reference 层 — 证据绑定暴露

raw reference 行(名称、解析状态、位置、owner)仅以 evidence 绑定形式返回;
支持按 `status` 过滤;禁止无界批量导出(受 §7 预算约束)。解析状态必须原样暴露
(包括 `unresolved`),不得在接口层掩盖 RQ1 已知的 CALLS/REFERENCES 覆盖缺口。

### 5.3 Impact 层 — shard 级保守前沿

只返回 shard 粒度的 0-hop(声明变更)与 1-hop(boundary 依赖)前沿 + `wide_impact`
布尔。**接口不做 symbol 级 impact 断言**,Agent 不得把 frontier 解读为符号级语义
影响(见 §8 源码验证规则)。多快照 diff 模式 defer 到 V1.1。

### 5.4 Knowledge 层 — 锚点暴露

仅经 `code.related` 按文档锚点暴露:命中的 `DOCUMENT_SECTION`(id、heading_path、
file)与 `CROSS_LAYER_LINK` 到代码 symbol。禁止返回文档全文或语料统计。

### 5.5 Overlay 层 — V1 排除

分支/会话 Overlay(GraphView、conflict、commit/merge)defer 到 V1.1。V1 所有查询
运行在 base 快照上;`GraphQuery(overlay=...)` 参数在 V1 qualification 中必须为空。

## 6. Provenance 强制要求

- P1.每个 result 必带:repository id、frozen commit sha、graph_generation、
  DB identity(path + 尺寸 + 生成代数由 envelope 隐含)。
- P2.每个 fact 必带 evidence 条目:确定性 `evidence_id`、`kind`
  (CODE_DEFINITION/CALL_RELATION/REFERENCE/DEPENDENCY/SHARD_RELATION/
  DOCUMENT_SECTION/CROSS_LAYER_LINK,与 R2 冻结枚举一致)、`source_path`、
  `source_range`(file+line 锚点)、`relation`、`provenance`(解析器/规则来源)。
- P3.Agent 侧输出若引用图 fact,必须以 `Evidence Used:` 尾注列出所依赖的
  evidence_id(R2 既有 citation 协议,继承);evaluator 按引用闭包打分。
- P4.调用日志(每次 call 的 envelope 原文)全部保留,是 qualification 的第一手证据。

## 7. 返回规模限制(预算,冻结)

| 参数 | 默认 | 硬上限 |
| --- | ---: | ---: |
| `max_evidence` | 20 | 50 |
| `max_symbols` | 8 | 20 |
| `max_edges` | 20 | 50 |
| `max_sections` | 4 | 10 |
| `max_hops`(subgraph 类语义,仅 bundle 内部) | 2 | 2 |
| 单响应字节上限 | — | 256 KiB |

- B1.超出预算必须截断并置 `truncation.truncated=true` + `omitted_counts`;
  截断选择必须确定性(按 (file_id, start_line, id) 排序,继承既有规则)。
- B2.禁止全图导出、禁止无界遍历、禁止跨查询累积绕过预算的复合调用
  (qualification 的 adoption 审计会检查调用序列)。
- B3.预算由 Agent 在调用中声明(≤ 硬上限);未声明用默认值。

## 8. 源码验证规则(哪些结论必须回源码验证)

接口提供的是**可验证锚点**(`source_path` + `source_range`),不是结论。Agent 在
对外断言以下内容前,**必须**先用文件读取工具回到源码验证,interface 结果不得单独
作为最终依据:

- V1.`symbol.lookup` 返回的定义的**语义**(该类/函数做什么);
- V2.`symbol.callers`/`callees` 命中的**调用点语义**(调用条件、参数含义);
- V3.`symbol.references` 命中的引用处**用途**;
- V4.`impact.frontier` 的下游 shard 的**实际影响**(frontier 只是保守候选集);
- V5.`code.related` 命中代码与文档描述的**等价性**。

相反,以下内容允许直接采信 interface(仍须 citation):symbol 身份与位置、边的
存在性、raw reference 的存在性与解析状态、frontier 的成员资格本身。

## 9. Qualification 用例(冻结,6 个真实任务)

锚点均于 2026-09-16 用只读查询对 frozen DB 实测固定(非人工臆造);qualification
时 evaluator 从同一 frozen DB 确定性重算期望值。任务 JSON 见 `tasks/SQI-T0{1..6}.json`
(与 contract 一同 seal)。Arms: `Native`(无接口,可自由读仓)与 `SQI`(必须经本
接口查询,允许读源码验证)。每 cell ≥3 reps,固定 model/runtime。

| 任务 | 仓 | 链路 | 场景(锚点摘要) |
| --- | --- | --- | --- |
| SQI-T01 | B1-aria2 | lookup → definition evidence | 定位 `aria2.DownloadEngine` 类声明(src/DownloadEngine.h:84,symbol `e8a562a9…`),说明其职责 |
| SQI-T02 | B2-brpc | lookup → callers → call-site evidence | `butil.Status.error_cstr`(`89c0f47c…`)的调用方枚举:7 条 CALLS 边冻结,要求枚举 ≥4 个生产调用方并回源码验证至少 2 处 |
| SQI-T03 | B3-rocksdb | lookup → references → reference evidence | `ROCKSDB_NAMESPACE.NumUnsetBytes`(`0458f52e…`)的 6 条 resolved raw refs(file:line 冻结),要求逐条引用 E-REF 证据 |
| SQI-T04 | B3-rocksdb | change 声明 → impact frontier | 声明 changed shard paths `{db, file}`(对应 RQ2 M4 冻结变更所在 shard);期望 1-hop 前沿 = 49 shards、1031 条 boundary 边、`wide_impact=true`,且 Agent 不得越权做符号级断言 |
| SQI-T05 | B2-brpc | document → code.related → cross-layer evidence | 复用 R2 已资格化的 T01 ground truth:docs/cn/client.md 负载均衡节 → `brpc.policy.AddServersInBatch.replicas` → consistent_hashing_load_balancer.cpp(E-CODE-9cec5b84fb52b556c0c332c9) |
| SQI-T06 | B2-brpc | bundle.explain 预算合规 | 对 `brpc.IsAskedToQuit`(49 callers,天然超预算)以 budget(max_evidence=12, max_symbols=6, max_edges=10)调用;验证 envelope schema、截断诚实性与 citation 完整性 |

**Qualification gates(每 cell)**:

- G1.全部调用 schema-valid(§4 C4);无 `INVALID_CALL`。
- G2.预算合规(§7),截断显式。
- G3.citation 闭包覆盖:答案声称的每个图 fact 都有 evidence_id 支撑。
- G4.源码验证纪律:§8 所列断言在事件日志中有对应的源码读取行为。
- G5.任务正确性按 frozen ground truth 判定(复用 R2 evaluator 语义)。
- G6.采纳与效率指标(RQ5/RQ4):调用次数、返回字节数、命中证据数,与 Native arm
  的 token/时间成本对照;**本阶段只采集,不做跨 arm 因果宣称**。

## 10. 证据等级目标与 claim scope

- 通过全部 gates 后,本线可陈述:`SQI-V1` 在 3 仓 × 6 任务上 **QUALIFIED**
  (限 §10 scope)。claim scope:Windows 11、冻结 commits、单机、只读查询、
  指定 model/runtime;不含 Overlay、不含多仓、不含并发、不含规模外推。
- 与 R1/R2 结果比较时视为**相邻协议版本**,不合并为同一重复(R2 既有规则)。

## 11. 冻结与变更控制

- 本次冻结(`structured-query-interface-contract-v1.freeze.sha256`)覆盖:本文件 +
  `tasks/SQI-T01..T06.json`。
- 实现阶段随后冻结:`schema/sqi-envelope-v1.json`、runner/adapter、ground-truth
  重算脚本;冻结必须发生在任何正式 qualification run 之前,并将文件哈希并入 seal
  (V1.1 次级 seal),与 systems_v1 流程一致。
- 任何语义变更(查询面、envelope 字段、预算上限、gates、任务锚点)必须升版本
  (V1.1/V2),禁止原地修改本文件;修改后旧 evidence 不得并入新 qualification。

## 12. 与既有线的关系

- RQ2(systems_v1)的 21 份 formal records、3 份 summary、synthesis 与 freeze seal
  **原样不动**;本线只读消费其已资格化的实现与 DB 产物。
- retrieval-v1/v2 的任务与 evaluator 语义被继承(T01 ground truth 直接复用);
  其结果作为相邻协议基线,不与本线 pools。
- RQ1 deferred 的 CALLS/Resolver 覆盖缺口**不修复**:接口按冻结实现原样暴露
  `unresolved` 状态,这正是本线要在 Agent 消费语境下量化的输入之一。

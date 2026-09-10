# ProvenLattice V1.0 — Knowledge Layer & Cross-Layer Evidence

## Scope

V1.0 在 Core V0.4 的 CodeGraph、Shard、Incremental 与 Base/Branch/Session Overlay 上增加最小 Knowledge Layer。它不是第二套图系统：Knowledge 节点继续使用统一 `Node`，跨层事实继续使用统一 `Edge`，原始证据使用与 `RawReference` 对称的 `RawEvidenceLink`。

本阶段仅处理 `spec/`、`docs/`、`doc/` 下的 Markdown 文档。Runtime Log、Commit History、Validation Result、Embedding、Vector DB、LLM linker、MCP、UI 和 TASCO 不在范围内。

## Model

Knowledge kinds：

- `Document`, `DocumentSection`, `Spec`, `Requirement`
- `Constraint`, `AcceptanceCriterion`
- `ShardDocument`, `ArchitectureSection`

文档根节点和 Section 节点 metadata 保存：`document_id`, `document_type`, `path`, `heading_path`, `anchor`, `start_line`, `end_line`, `content_hash`, `document_version`。`document_version` 是 content-addressed integer，因此同一 Revision B 的 Full 与 Incremental 结果一致。

Section ID 基于仓库、文档路径、kind 和 heading hierarchy；显式 Requirement ID 优先作为 anchor。重复 heading 使用 Markdown 风格的 occurrence suffix，不依赖行号。正文和行号变化不会改变显式 Requirement ID。

## RawEvidenceLink contract

```text
id
repository_id
source_node_id
raw_anchor
anchor_type
candidate_targets
resolved_target_id
resolution_status
resolution_strategy
provenance
confidence
generation
metadata
```

`resolution_status` 严格区分 `resolved / ambiguous / unresolved`。原始证据始终持久化；只有唯一 `resolved` target 生成 Edge。ambiguous/unresolved 绝不为提高 resolved rate 而强绑。

确定性解析顺序为：

1. explicit Requirement ID；
2. exact file path / file:line；
3. exact qualified symbol（`.` 与 `::` 规范化）；
4. explicit module name；
5. unique simple symbol candidate。

当前不做语义相似度、Embedding 或 LLM 推断。跨层关系限制为 `DESCRIBES`, `CONSTRAINS`, `IMPLEMENTED_BY`, `VERIFIED_BY`, `BELONGS_TO`, `DOCUMENTS`。结构包含关系仍使用既有 `CONTAINS`。

## Incremental update

`document_state` 持久化每个文档的 content hash 和 content-addressed version。Knowledge update 只重新读取 hash 变化的文档，并以 Section hash 区分 reprocessed/reused。删除 Section 时同步删除其 RawEvidenceLink 和派生跨层 Edge。

代码 generation 变化时，不重新解析未变文档，而是通过持久化 RawEvidenceLink 重新验证候选和 target。V1.0 当前采用保守策略：代码 generation 变化时重新验证全部 Knowledge evidence；这是正确性优先的基线，后续可利用 raw anchor / resolved target 索引进一步缩小到 changed-symbol candidate set。

## Overlay

`RawEvidenceLink` 已加入 V0.4 `ENTITY_TABLES`。Knowledge Node、Cross-layer Edge 和 RawEvidenceLink 因而自然支持：

```text
Session Overlay > Branch Overlay > Base Graph
```

同一 Requirement/Section 的分支差异走既有 entity conflict；删除与更新走 tombstone/`DELETE_UPDATE_CONFLICT`；不引入独立 merge 机制。

## Query surface

- `get_evidence_links(...)`
- `get_implemented_code(requirement)`
- `get_requirements(symbol)`
- `get_document_targets(document_or_section)`
- 既有 `get_subgraph(...)` 可跨越 Knowledge 与 CodeGraph

CLI 对应提供 `knowledge`, `implemented`, `requirements`, `evidence`。

## Correctness gates

V1 fixture 同时包含 `spec/recovery.md`, `docs/architecture.md`, `src/recovery.cpp`, `test/recovery_test.cpp`，覆盖：

- C1：显式 symbol 生成 resolved `IMPLEMENTED_BY`；
- C2：同名多 symbol 保持 ambiguous 且无 Edge；
- C3：Requirement 正文改变但 ID 稳定；
- C4：Section 删除同步删除 evidence 与 Edge；
- C5：代码 signature 改变后未变文档 evidence 被重新解析；
- C6：两个 Overlay 修改同一 Knowledge entity 时报告 `ENTITY_CONFLICT`。

Hard Gate：`FullIndex(B) + FullKnowledge(B) == IncrementalIndex(A→B) + IncrementalKnowledge(A→B)`，并验证 Overlay materialization parity。

## Known limitations

- 文档 parser 当前只覆盖 Markdown heading；未接入 RST、AsciiDoc 或外部需求系统。
- ShardDocument 采用保守的文件命名识别，尚无 build-aware document ownership。
- 结构匹配仅覆盖显式 path/module anchor；没有自然语言实体链接。
- 代码 generation 改变后的 evidence candidate refresh 仍是全 evidence 级，而非最小候选集合。
- `document_state` 是索引状态，不作为 Overlay 图实体；Overlay parity 覆盖 Node、Edge、RawEvidenceLink。

## Next qualification

V1.0-R1 的独立检索实验定义见 [design-v1-r1.md](design-v1-r1.md)。它验证 ProvenLattice 自身能否改善真实工程证据定位，不把 Token 压缩、TASCO 或某种 Agent 接口作为前置假设。

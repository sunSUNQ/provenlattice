# ProvenLattice V1.0 — Knowledge Layer baseline

V1.0 是首个 CodeGraph 与工程知识层统一建模的阶段基线。

已完成：

- Markdown Document / Section / Spec / Requirement / Constraint / AcceptanceCriterion 建模；
- 稳定 Section 与显式 Requirement identity；
- RawEvidenceLink 的 resolved / ambiguous / unresolved contract；
- 独立确定性 CrossLayerResolver；
- provenance/confidence 跨层 Edge；
- Knowledge 文档增量更新和代码变更后的 evidence refresh；
- Knowledge Node / Edge / RawEvidenceLink Overlay；
- Full/Incremental/Overlay parity；
- C1–C6 fixture；
- B2 brpc 真实仓基线。

验证状态：标准库 `unittest` 共 31 项全部通过。详细设计和实测数据分别见 `docs/design-v1.md` 与 `docs/benchmarks/provenlattice-v1.0-knowledge.md`。

明确未包含：Runtime Log、Commit History、Validation Result、Embedding、Vector DB、LLM linker、MCP、UI、TASCO。

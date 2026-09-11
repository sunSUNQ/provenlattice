# ProvenLattice V1.0-R2 Structured Retrieval Qualification

R2 measures a different interface from R1. R1 exposed low-level graph operations; R2 adds
bounded, deterministic `EvidenceBundle` queries and explicit Evidence citations. Results are
therefore compared as adjacent protocol versions, not pooled as identical repetitions.

## Frozen scope

- Parser, ReferenceResolver, CrossLayerResolver, Knowledge Dataset, Shard and Overlay semantics
  remain unchanged.
- No resolver or coverage expansion, embeddings, LLM reranker, history/log, MCP or TASCO.
- Evidence kinds are limited to `CODE_DEFINITION`, `CALL_RELATION`, `REFERENCE`, `DEPENDENCY`,
  `SHARD_RELATION`, `DOCUMENT_SECTION` and `CROSS_LAYER_LINK`.
- IDs are derived from repository and underlying fact identity, not query order, graph generation
  or Agent session.

High-level CLI queries are `explain-symbol`, `explain-module`, `find-related-code`,
`find-related-documents` and `trace-evidence`. Each accepts `--max-evidence`, `--max-symbols`,
`--max-edges` and `--max-sections`.

## First qualification cell set

The first gate is the unchanged R1 T05 task at brpc commit
`ae09e960c7291605dda52356cc0c2d45567fb53e`:

```text
T05 × Native
T05 × CodeGraph-R2
T05 × Knowledge-R2
```

The R2 task adds frozen Evidence IDs generated from the existing brpc Knowledge DB; these IDs are
evaluator-only data and are never included in the Agent prompt. Graph and Knowledge answers must
end with `Evidence Used:` citations. Native remains ID-free and is evaluated with the frozen R1
natural-language evidence contract.

Arm isolation is physical as well as logical: CodeGraph uses the frozen Core-only brpc database,
while Knowledge uses the frozen Knowledge database. CodeGraph therefore cannot receive document or
cross-layer rows through a high-level bundle. Its required ID set contains code evidence; Knowledge's
set additionally contains the required document and resolved cross-layer link. Both non-Native arms
must still mention the original frozen natural-language evidence to satisfy task success.

Run the three cells with one fixed model/runtime:

```powershell
$env:PYTHONPATH = "src"
python -m experiments.retrieval-v2.run_t05 `
  --repo ..\benchmark-repos\brpc `
  --codegraph-database ..\benchmark-analysis\v0.2-db\brpc.db `
  --knowledge-database ..\benchmark-analysis\v1.0-db\brpc-knowledge.db `
  --model-id claude-sonnet-4-5-20250929 `
  --claude-version 2.1.268 `
  --provenlattice-commit R2_COMMIT
```

Raw cell artifacts remain local. The reviewed qualification summary and comparison report may be
committed after audit. A wider 3-task qualification is allowed only after all three T05 artifacts
are complete, reproducible, read-only and correctly isolated by Arm.

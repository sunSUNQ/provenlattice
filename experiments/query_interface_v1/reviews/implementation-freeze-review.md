# SQI-V1 Implementation Baseline Freeze Review — PASS

Freeze date: 2026-09-16

## Scope

Stage 1 (`SQI-V1 Implementation Baseline`) is complete and frozen. This review
records what was sealed, the completion gate evidence, and the explicit
boundary: **no formal Native-vs-SQI qualification has been run or claimed.**

## Frozen implementation files

`contract/structured-query-interface-contract-v1.implementation-seal.sha256`
(secondary seal per Contract V1 §11) — SHA-256 round-trip verified 5/5:

| File | Role |
| --- | --- |
| `schema/sqi-envelope-v1.json` | structural envelope schema (C4) |
| `tools/sqi_validator.py` | C1–C4 semantics, budget accounting, provenance binding (incl. expected-commit mismatch), truncation honesty |
| `tools/sqi_adapter.py` | the six frozen canonical calls, shared budget pool, deterministic ordering, bounded row projection, shard-level impact only |
| `tools/sqi_runner.py` | frozen task loader (SQI-T01..T06), sqi/native arm scaffold, per-call raw envelope + schema/contract validation + budget/truncation/bytes/latency + double-execution determinism + frozen-anchor verification; refuses `--mode formal` |
| `tests/test_sqi_v1.py` | 21 implementation tests |

The Contract freeze seal (contract + T01–T06, 7 files) is untouched.

## Completion gate evidence

1. **Six canonical calls implemented**: `symbol.lookup`, `symbol.callers`,
   `symbol.callees`, `symbol.references`, `impact.frontier`, `code.related`,
   `bundle.explain` — each a separate handler over the frozen ProvenLattice
   `GraphQuery`/evidence/shard primitives; no second data model, no Overlay
   path, no symbol-level impact derivation.
2. **T01–T06 loadable by the runner** with frozen per-task step plans.
3. **Schema + contract validation active**: the adapter self-validates every
   envelope (structural + C1–C4 + budget + expected-commit) before returning;
   the runner re-validates and records the result per call.
4. **Implementation tests: 21/21 PASS**
   (`PYTHONPATH=src python -m unittest experiments.query_interface_v1.tests.test_sqi_v1`),
   covering the ten required behaviors: deterministic output, evidence
   bidirectional binding, provenance mismatch, deterministic truncation,
   bundle shared budget, unresolved raw references verbatim, impact boundary,
   source-verification policy, response byte ceiling, evidence-ID stability.
5. **No frozen contract/task file modified**: both original seals re-verified
   (7/7 and 5/5) after all implementation work.
6. **No known implementation blocker.**

## Notes carried into Stage 2

- `impact.frontier` returns the exact aggregate (`boundary_edges_total`,
  `frontier_size`, `wide_impact`) plus a deterministic budgeted listing of
  boundary edge ids; the listing never masquerades as the full edge set.
- `bundle.explain` reports honest omitted counts recomputed from uncapped
  candidate facts (T06: 43 symbols / 39 edges omitted of 49 callers).
- Unresolved/ambiguous raw references are returned verbatim (owner and
  resolution-target axes merged under the frozen `symbol.references` input).
- Response byte ceiling (256 KiB) enforced before return.

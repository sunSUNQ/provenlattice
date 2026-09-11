# ProvenLattice V1.0-R2.1 — Experiment Closure

## Frozen protocol

Repository: `apache/brpc`, commit `ae09e960c7291605dda52356cc0c2d45567fb53e`.
Model: `claude-sonnet-4-5-20250929`; Claude Code `2.1.268`. Track A is T01/T03/T05 × Native and
CodeGraph-R2 × 3 = 18 valid cells. Track B is T05 × Knowledge-R2.1 × 3 = 3 valid cells. Every
cell has the five required artifacts; raw Agent artifacts remain local and are hashed in the
manifest.

## Final status

| Gate | Status | Evidence |
|---|---|---|
| Interface Qualification | PASS | 21/21 valid artifacts; offline replay identical |
| CodeGraph Progression | HOLD | cross-task benefit unstable; T01/T03 Ground Truth semantic mismatch |
| Knowledge Progression | HOLD | Query Bundle gap closed; citation/evaluator contract still unstable |

## Track A observed results

| Task / arm | Success | Median recall | Median precision | Median turns | Median files | First relevant turn |
|---|---:|---:|---:|---:|---:|---:|
| T01 Native | 3/3 | 1.00 | 1.00 | 10 | 5 | 1 |
| T01 CodeGraph | 0/3 | 0.00 | 0.00 | 19 | 3 | 13 |
| T03 Native | 2/3 | 1.00 | 1.00 | 12 | 5 | — |
| T03 CodeGraph | 0/3 | 1.00 | 1.00 | 9 | 4 | 1 |
| T05 Native | 2/3 | 1.00 | 1.00 | 22 | 9 | — |
| T05 CodeGraph | 1/3 | 1.00 | 0.043 | 48 | 11 | 4 |

T01 and T03 are attributed as `GROUND_TRUTH_SEMANTIC_MISMATCH` where the output satisfies the
natural task better than the frozen ID contract. T05 remains `Positive Signal / Not Stable Positive
Zone`; its R2 one-shot improvement (17 turns, 2 files) did not reproduce.

## Track B observed results

Knowledge R2.1 exact recall is `1.0 / 1.0 / 1.0`; the required DocumentSection Evidence is now
returned and exposed with the Cross-Layer Link. Aggregate medians are 18 turns, 4 files and 0.167
precision. One run has a fragment-path classification and one has an unsupported citation, so the
gate remains HOLD. This is an Evidence/Evaluator Contract issue, not a Coverage Gap.

## Reproducibility artifacts

- [manifest-r2.1.json](../../experiments/retrieval-v2/r2_1/results/manifest-r2.1.json)
- [aggregate-r2.1.json](../../experiments/retrieval-v2/r2_1/results/aggregate-r2.1.json)
- [pairwise-r2.1.json](../../experiments/retrieval-v2/r2_1/results/pairwise-r2.1.json)
- [evaluator-replay.json](../../experiments/retrieval-v2/r2_1/results/evaluator-replay.json)
- [failure-attribution-r2.1.md](../../experiments/retrieval-v2/r2_1/failure-attribution-r2.1.md)
- [protocol-deviations.md](../../experiments/retrieval-v2/r2_1/protocol-deviations.md)

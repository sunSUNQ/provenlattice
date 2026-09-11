# ProvenLattice V1.0-R2.2 — Evaluation Contract Qualification

R2.2 is an offline measurement qualification. No Agent Cell was rerun. The replay set contains 51
frozen cells from R1, R2 and R2.1, covering T01, T03 and T05 across Native, CodeGraph and Knowledge.

## Contract changes

GroundTruthV2 supports required concepts, `ANY_OF` / `ALL_OF` / `OPTIONAL` evidence groups,
acceptable alternatives, supporting evidence, distractors and invalid evidence. Identity is
canonicalized by Evidence ID, stable symbol/document-section ID and repository-relative path.
Document fragments are split from paths and normalized as anchors; Windows and POSIX paths are
equivalent. Citations are classified as `SUPPORTED_EXACT`, `SUPPORTED_ALTERNATIVE`,
`SUPPORTED_CONTEXTUAL`, `UNKNOWN_EVIDENCE` or `INVALID_EVIDENCE`. Concept Recall is reported
separately from Exact Evidence Recall.

The deterministic E1–E10 fixture suite passes. Offline replay is deterministic for all 51 cells.

## Attribution

| Attribution | Cells |
|---|---:|
| TRUE_CAPABILITY_SUCCESS | 10 |
| TRUE_CAPABILITY_FAILURE | 29 |
| EVALUATOR_FALSE_NEGATIVE | 8 |
| INVALID_EVIDENCE | 4 |
| UNKNOWN_EVIDENCE | 0 |

For T01/T03 specifically, 7 historical failures are evaluator false negatives after accepting the
audited bounded-load implementation and authoritative virtual-node document; 18 remain true
capability failures, and 5 are true successes. Original evaluation files and scores are unchanged.

The four invalid citations are real CodeDefinition IDs confirmed by `trace_evidence`, but were not
exposed by the current bundle. They are not hallucinations (`UNKNOWN_EVIDENCE = 0`); they remain
contract violations (`INVALID_EVIDENCE`).

## Answers to the qualification questions

1. T01/T03 contain 18 true capability failures and 7 evaluator false negatives among historical
   failures.
2. GroundTruthV2 exposes 7 T01/T03 false negatives; it does not convert the remaining failures.
3. Yes. `ANY_OF` accepts multiple independently audited engineering paths without requiring every
   alternative.
4. Yes for path/fragment handling: fragments no longer enter filesystem glob validation; the E6–E7
   regression fixtures pass.
5. The Knowledge unsupported citations are valid IDs but not bundle-exposed, so they are
   `INVALID_EVIDENCE`, not hallucinated unknown IDs.
6. T01, T03 and T05 are candidates for a future R2.3 Agent experiment. T01/T03 should use the
   frozen GroundTruthV2; T05 should retain the stricter no-invalid-citation gate.

R2.2 qualifies measurement validity only. It does not declare CodeGraph or Knowledge effective;
that requires a new R2.3 Agent experiment.

# R2.3 failure attribution

Five of the 27 frozen cells are non-success. Attribution below is mechanical: it is read from the
frozen `evaluation-v2.json` and `metrics.json` of each cell, and the GroundTruthV2 role of every
cited Evidence ID is resolved from
`experiments/retrieval-v2/evaluator-v2/ground-truth-v2/ground-truth-v2.json`.
No cell was re-run or re-scored.

| Cell | Concept recall | Trigger | Classification |
|---|---:|---|---|
| `T01.knowledge.r1` | 1.000 | cited `E-CODE-9CEC5B84FB52B556C0C332C9` -> `INVALID_EVIDENCE` | `INVALID_EVIDENCE` (bundle precision) |
| `T05.codegraph.r1` | 1.000 | cited `E-CODE-C2F8A2E93CB05E73B643FBBE` -> `INVALID_EVIDENCE` | `INVALID_EVIDENCE` (agent-side) |
| `T03.codegraph.r2` | 1.000 | cited `E-CODE-9CEC` -> `UNKNOWN_EVIDENCE` | `UNKNOWN_EVIDENCE` (truncated ID) |
| `T05.native.r2` | 1.000 | `wrong_path_count = 1`, path `src/brpc/*.cpp` | `PATH_PRECISION` |
| `T05.native.r3` | 1.000 | `wrong_path_count = 1`, path `src/brpc/*.cpp` | `PATH_PRECISION` |

## Counts

| Class | Count |
|---|---:|
| TRUE_CAPABILITY_SUCCESS | 22 |
| TRUE_CAPABILITY_FAILURE | 0 |
| INVALID_EVIDENCE | 2 |
| UNKNOWN_EVIDENCE | 1 |
| PATH_PRECISION | 2 |
| EVALUATOR_FALSE_NEGATIVE | 0 |

## Detail

### `T01.knowledge.r1` — INVALID_EVIDENCE via bundle exposure

- Concept recall 1.000, no unmet concept, 0 wrong paths, 0 unsupported citations.
- Exact required evidence `E-CODE-1726CDC7C9938223C1D04362` was **not** cited.
- Bundle returned 10 items; the agent used all 10 (`returned = used = 10`, unused = 0).
- GroundTruthV2 for T01 declares `E-CODE-9CEC5B84FB52B556C0C332C9` in `invalid_evidence_ids`.
- The Knowledge bundle surfaced that item, so the agent had no way to know it was a distractor.

This is a bundle-precision / distractor-exposure event, not a citation hallucination.

### `T05.codegraph.r1` — INVALID_EVIDENCE cited without exposure

- Concept recall 1.000; exact recall 0.333 (only the code evidence, missing the DOC and XLINK rows).
- Bundle returned 38 items and the agent used 20; `E-CODE-C2F8A2E93CB05E73B643FBBE` was **not**
  among the returned items, so the citation is agent-side fabrication of an Evidence ID.

### `T03.codegraph.r2` — UNKNOWN_EVIDENCE from a truncated ID

- Concept recall 1.000; exact recall 1.000 (the required ID was correctly cited in full elsewhere in
  the answer); precision 0.667.
- The answer additionally cited the literal fragment `E-CODE-9CEC`, which does not resolve to an
  Evidence ID and is classified `UNKNOWN_EVIDENCE`.
- Pure citation hygiene: the substance of the answer was complete.

### `T05.native.r2` / `T05.native.r3` — PATH_PRECISION

- Concept recall 1.000; all three T05 concepts satisfied in both cells; no invalid or unsupported
  citations.
- The only failure trigger is a single `wrong_path_count` from the phrase `src/brpc/*.cpp`, which the
  EvaluatorV2 path regex extracts and then rejects because no such file exists.
- T05 `expected_paths` is empty in GroundTruthV2, so there is no expected path to match against.
- Reported as a real answer-precision defect (a wildcard is not a specific file) **and** as the first
  measurement-contract item for a later round. It is not reclassified here: section 16 of the frozen
  protocol forbids changing the evaluator during this round.

## Structural finding: one Evidence ID, two GroundTruthV2 roles

`E-CODE-9CEC5B84FB52B556C0C332C9`

- T03: `required_evidence_ids` -> citing it is required and correct.
- T01: `invalid_evidence_ids` -> citing it fails the task.

`T01.codegraph` never used it and scored 3/3; `T01.knowledge` returned and used it and scored 2/3.
Any future bundle-precision work must therefore treat per-task distractor sets as first-class bundle
selection input rather than a global evidence property.

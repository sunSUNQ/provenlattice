# Graph Fidelity V1 — Calibration Execution Log

## Batch 01

- Status: `A_COMPLETE_B_PENDING`
- Intended scope: 25 blinded cases from Annotator A and the same 25 case IDs in Annotator B's blinded view.
- Scoring exposure: none.
- System-status exposure: none during Annotator A's calibration.
- Annotator A: 25 source-level records completed in `annotator-a-calibration-01.md`.
- Annotator B: independent calibration not yet received.

## ANNOTATION_PROTOCOL_ISSUE-001

**Observed during:** initial blinded-package inspection, before any case received a label.

**Issue:** The blinded package supplies `candidate_symbol_ids`, but it does not supply a candidate definition path, source range, qualified name, or other source-level target context. For `CALLS` and `REFERENCES`, an annotator therefore cannot independently determine whether a candidate is the gold target, nor can they populate `gold_target_symbol_id` from source evidence alone.

**Impact:** The current package supports recording whether a source-level relation appears to exist, but it does not support a defensible target-correctness judgement for candidate-dependent cases. Continuing would create annotations that cannot satisfy the frozen protocol's target-verification requirement.

**Action taken:** No candidate, label vocabulary, or scoring rule was changed. Annotator A used read-only candidate-ID lookups in the frozen graph databases to recover target definitions without consulting system status. The A record is complete; the batch remains open until an independent B record is available and the issue is reviewed at batch level.

**Out of scope:** This log does not alter the frozen protocol or make a graph-fidelity claim.

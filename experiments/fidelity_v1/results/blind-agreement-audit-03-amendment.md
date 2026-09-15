# ProvenLattice Fidelity V1 — Blind Agreement Audit 03 Amendment

## Purpose and authority

This amendment corrects only the Gate scope mapping in the original Batch 03
agreement audit. It does not alter either sealed Batch 03 annotation record,
the reported agreement measurements, frozen protocol semantics, or source
repositories.

The frozen qualification boundary treats Python `REFERENCES` as an audit-only
track. A reliability or semantic-ambiguity finding in that track must not gate
the primary C/C++ CALLS/IMPORTS Fidelity V1 universe.

## Corrected gate decision

| Track | Gate | Basis |
| --- | --- | --- |
| C/C++ primary Fidelity V1 | **PASS** | No `NEW_SYSTEMATIC_SEMANTIC_AMBIGUITY`, blindness violation, scope mismatch, or schema incompatibility was established in C/C++ CALLS/IMPORTS. |
| Python REFERENCES audit-only | **HOLD / separate protocol study** | 10 of 12 formal-verdict disagreements are Python REFERENCES and reveal an unaligned Python-specific relation/target interpretation. |
| Batch 04 C/C++ mainline | **UNBLOCKED** | The Python audit-only hold does not gate the C/C++ universe. |

The original single, global `HOLD` is therefore superseded by this partitioned
decision. Ordinary C/C++ disagreements remain in the adjudication queue; they
do not alter protocol semantics or independently trigger a Drift Gate hold.

## Preserved audit evidence

| C/C++ measure | Result |
| --- | ---: |
| Cases | 40 |
| Formal-verdict agreement | 38/40 (95.0%) |
| Cohen's kappa | 0.857 |
| CALLS formal-verdict agreement | 20/21 (95.2%) |
| IMPORTS formal-verdict agreement | 20/21 (95.2%) |

The original audit's Python audit-only observations remain preserved without
being pooled into the C/C++ gate: 10/20 Python formal-verdict agreement and
8/18 Python REFERENCES formal-verdict agreement.

## Handling

- Keep the original 18-case adjudication queue unchanged; it is evidence
  review, not a protocol rewrite.
- Route the Python REFERENCES cluster to the separate Python protocol study.
- Keep Batch 04 C/C++ annotators blind to Batch 03 results, this amendment,
  and every adjudication outcome.
- Do not compute or publish Graph Fidelity results until sealed Gold and
  system predictions are joined in the later scoring stage.

## Validation

The amendment uses only the structured and narrative Batch 03 agreement-audit
artifacts. It reads no system prediction, resolver status/strategy/confidence,
selected target, Graph Fidelity score, or later-batch outcome.

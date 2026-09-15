# Graph Fidelity V1 — Blind Agreement Audit 02 Amendment

## Status

| Item | Status |
| --- | --- |
| Batch 02 Drift Gate | **PASS** |
| Batch 03 | **UNBLOCKED** |
| C/C++ protocol | Stable enough to continue |
| C/C++ adjudication | 4 CALLS cases queued |
| Python REFERENCES | Audit-only reliability issue; separate protocol study required |
| Graph Fidelity verdict | Not yet available |

This amendment supersedes the prior Batch 02 conclusion that marked the
Drift Gate `HOLD`. That conclusion treated ordinary, unclassified annotation
disagreements as established protocol drift. Under the frozen policy, a hold
is warranted only for `NEW_SYSTEMATIC_SEMANTIC_AMBIGUITY`,
`BLINDNESS_VIOLATION`, `SCOPE_MISMATCH`, or `SCHEMA_INCOMPATIBILITY`.
None was established in this audit.

No sealed Annotator A or Annotator B annotation record was changed. No system
prediction, system status, resolver strategy, resolver confidence, selected
target, or Graph Fidelity score was used.

## C/C++ agreement basis

| Measure | Result |
| --- | ---: |
| C/C++ cases | 38 |
| Relation-presence agreement | 38/38 (100.00%) |
| Build-context agreement | 38/38 (100.00%) |
| Formal-verdict agreement | 34/38 (89.47%) |
| Formal-verdict Cohen's kappa | 0.729 |
| IMPORTS formal-verdict agreement | 20/20 (100.00%) |
| CALLS formal-verdict agreement | 14/18 (77.78%) |

The four C/C++ formal disagreements all preserve relation presence. They are
limited to cross-file CALLS target identification and are queued for
third-party, source-only adjudication. They are not a finding of a new CALLS
semantic ambiguity.

## Q3 — Navigation complexity

`LOCAL_ONLY` means neither record indicates cross-file navigation.
`CROSS_FILE` means A's cross-file flag is true or B records one or more
navigation files.

| C/C++ class | n | Formal verdict | Relation presence | Target-cardinality agreement |
| --- | ---: | ---: | ---: | ---: |
| LOCAL_ONLY | 8 | 8/8 | 8/8 | 8/8 |
| CROSS_FILE | 30 | 26/30 | 30/30 | 25/30 |

A recorded navigation booleans, not navigation-file counts or recovery
telemetry. B recorded 11 navigation files across 9 C/C++ cases and 4 recovered
targets. These fields are therefore not treated as directly comparable counts.

## Q4 — Declaration/definition equivalence

Five C/C++ cases contain a declaration/definition twin group.

| Measure | Result |
| --- | ---: |
| Semantic target agreement | 4/5 |
| Canonical-node agreement | 4/5 |
| Semantic disagreement | 1 |
| Canonicalization-only disagreement | 0 |

The single disagreement is a candidate-missing, cross-file recovery case; it
does not establish a declaration/definition semantic conflict.

## Scope isolation and next handling

Python REFERENCES has 10/21 formal-verdict agreement and remains an
audit-only reliability finding. It is excluded from the C/C++ Fidelity
universe and does not affect this gate.

The four C/C++ CALLS cases proceed to an independent, source-only adjudication
queue. Batch 03 annotators must remain blind to that queue and its outcomes.
Telemetry schema alignment for Batch 03 may be added without changing frozen
verdict semantics.

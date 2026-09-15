# ProvenLattice P0 Graph Fidelity V1 — Blind Agreement Audit 04

**Status: COMPLETE**

Auditor: independent root Agreement Auditor, current runtime model **GPT-5**.
This audit reads only the sealed Batch 04 A/B records, Batch 04 manifests,
package-local frozen protocols/telemetry schema, and Batch 04 seal
verification. No system prediction, resolver data, Graph Fidelity score,
future-batch result, or existing adjudication answer was read.

## Preflight

| Check | Result |
| --- | ---: |
| A sample count | 60 |
| B sample count | 60 |
| Case ID alignment | 60/60 |
| A sealed | YES |
| B sealed | YES |
| A/B blindness violations | 0 / 0 |
| A/B schema violations | 0 / 0 |
| A/B repository mutations | 0 / 0 |

The complete A sealed record is the package's
`output/annotator-a-batch-04-annotations.json`; the package's blank template
was not used as an annotation input. B's complete output is
`output/annotation-record-template.json`. Both records contain all eight
frozen telemetry fields.

## Overall agreement

Build context is normalized as follows: A `BUILD_CONTEXT_DEPENDENT` and B
`REQUIRED_UNAVAILABLE` map to `DEPENDENT`; A/B `NOT_REQUIRED` and B
`EXTERNAL_TARGET` map to `NOT_REQUIRED`.

| Measure | Agreement | 95% descriptive interval | κ |
| --- | ---: | ---: | ---: |
| Exact formal verdict / raw agreement | 49/60 (81.7%) | 70.1–89.4% | 0.535 |
| Relation presence | 60/60 (100.0%) | 94.0–100.0% | κ not informative (single-category marginals) |
| Build context, normalized | 58/60 (96.7%) | 88.6–99.1% | 0.000 |

The build-context κ is not substantively informative because the normalized
labels are overwhelmingly single-category; the observed agreement is the
reported measure.

## Scope and relation slices

The C/C++ primary universe is closed by relation denominator reconciliation:
`CALLS 23 + IMPORTS 18 = 41` C/C++ cases. The remaining 19 cases are Python
`REFERENCES` audit-only.

| Slice | n | Formal verdict | Relation presence | Build context | κ (formal) |
| --- | ---: | ---: | ---: | ---: | ---: |
| C/C++ primary | 41 | 32/41 (78.0%) | 41/41 (100.0%) | 39/41 (95.1%) | 0.457 |
| Python audit-only | 19 | 17/19 (89.5%) | 19/19 (100.0%) | 19/19 (100.0%) | 0.732 |
| CALLS | 23 | 16/23 (69.6%) | 23/23 (100.0%) | 21/23 (91.3%) | 0.000, not informative due marginal degeneracy |
| IMPORTS | 18 | 16/18 (88.9%) | 18/18 (100.0%) | 18/18 (100.0%) | 0.786 |
| REFERENCES — audit-only | 19 | 17/19 (89.5%) | 19/19 (100.0%) | 19/19 (100.0%) | 0.732 |

Python REFERENCES remains `HOLD / separate protocol study` and does not gate
the C/C++ primary universe.

## Navigation and verification depth

`CROSS_FILE` means either annotator recorded at least one navigation file.
Depth is the maximum of A/B's `verification_depth` for the case.

| Class / depth | n | Formal verdict | Target-cardinality | Relation presence |
| --- | ---: | ---: | ---: | ---: |
| LOCAL_ONLY / L0 | 49 | 38/49 (77.6%) | 40/49 (81.6%) | 49/49 (100.0%) |
| CROSS_FILE / L1 | 11 | 11/11 (100.0%) | 11/11 (100.0%) | 11/11 (100.0%) |
| L2 | 0 | N/A | N/A | N/A |
| L3 | 0 | N/A | N/A | N/A |
| L4 | 0 | N/A | N/A | N/A |

A recorded zero navigation files for all cases; B recorded 11 L1 cases. The
11 formal disagreements are all LOCAL_ONLY/L0, so disagreement is not
concentrated in deeper verification in this batch. Aggregate B telemetry:
11 navigation files, 11 navigation hops, and 11 recovered-target flags across
the CROSS_FILE class; A recorded 0 for each corresponding count/flag.

## Declaration/definition equivalence

No explicit declaration/definition twin-group field is present in either
sealed record schema, and no twin-case membership is encoded in the Batch 04
records. Therefore semantic-target agreement, canonical-node agreement,
semantic-disagreement count, and canonicalization-only-disagreement count are
**not computable from the permitted sealed inputs**. No equivalence was
invented.

## C/C++ disagreement attribution

There are **9** C/C++ formal disagreements: 7 CALLS and 2 IMPORTS. They are
ordinary adjudication cases, classified without deciding A/B correctness:

- 7 CALLS: `TARGET_CARDINALITY_DISAGREEMENT`; 5 also expose opaque-candidate
  or candidate-missing evidence limitations (`CANDIDATE_MISSING`/`OTHER`).
- 2 IMPORTS: `BUILD_CONTEXT_DIFFERENCE` with target-cardinality unavailable
  on B's `BUILD_CONTEXT_DEPENDENT` verdict.

No case is classified as a new systematic semantic ambiguity. All 9 enter the
adjudication queue. The 2 Python formal disagreements remain audit-only.

## Drift Gate

**C/C++ primary Drift Gate: PASS**

No `NEW_SYSTEMATIC_SEMANTIC_AMBIGUITY`, `BLINDNESS_VIOLATION`,
`SCOPE_MISMATCH`, or `SCHEMA_INCOMPATIBILITY` was established for the C/C++
primary universe. Ordinary disagreement and κ values do not independently
trigger HOLD.

**Batch 05 C/C++ mainline: UNBLOCKED.**

Graph Fidelity scoring remains unavailable until the later sealed-Gold/system
join stage.

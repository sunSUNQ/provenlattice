# ProvenLattice Fidelity V1 — Blind Agreement Audit, Batch 03

## Audit boundary

This audit compares only the completed Annotator A and Annotator B Batch 03 records in their clean packages, the two Batch 03 manifests, and the frozen package-local Annotation Instructions V1, CALLS_V1, Evidence Scope V1, and Declaration–Definition Equivalence V1 documents. It does not use Batch 02 results, any system prediction/status/resolver data, Graph Fidelity scores, later batches, or adjudication outcomes.

Audit date: 2026-09-15 (Asia/Shanghai). Batch: 03. Units: 60 paired cases.

## Preflight

| Check | Result |
|---|---:|
| Manifest / Annotator A / Annotator B count | 60 / 60 / 60 |
| Unique IDs, A / B | 60 / 60 |
| Manifest-aligned pairs | 60/60 |
| Extra or missing IDs | 0 |
| Schema violations, A / B | 0 / 0 |
| Blindness-field violations, A / B | 0 / 0 |
| Frozen repo commits match | 3/3 |
| Frozen repo dirty paths | 0 |

All frozen inputs and protocol payloads match their package-manifest SHA256 values. Each completed `output/annotation-record-template.json` differs from its original blank-template hash, as expected after annotation; these are the only payload hash differences. Frozen source repositories are at the pinned commits and clean: aria2 `9e7273583f83e881e3ec067b523ba88724088d2f`, brpc `ae09e960c7291605dda52356cc0c2d45567fb53e`, rocksdb `37234200b57d8d0a6a5c41f2d9811bbd2e293544`.

## Agreement results

Intervals are descriptive two-sided 95% Wilson score intervals. Cohen's kappa is reported where marginal variation permits it.

| Measure | Agreement | Percent (95% CI) | Kappa |
|---|---:|---:|---:|
| Formal verdict, raw exact | 48/60 | 80.0% (68.2–88.2%) | 0.516 |
| Relation presence | 56/60 | 93.3% (84.1–97.4%) | 0.000¹ |
| Build-context status, normalized | 60/60 | 100.0% (94.0–100.0%) | N/A² |
| Identical telemetry bundle | 52/60 | 86.7% (75.8–93.1%) | Not categorical |

¹ Presence kappa is zero despite high observed agreement because Annotator B used only one presence category; this is a prevalence/marginal degeneracy and should not be read as zero raw agreement.  
² Both annotators assigned the same single normalized status (`NOT_REQUIRED`) to every case, so expected agreement is 1 and kappa is undefined.

### Q1 — relation slices

| Relation | N | Formal-verdict exact | Percent (95% CI) | Kappa | Treatment |
|---|---:|---:|---:|---:|---|
| CALLS | 21 | 20/21 | 95.2% (77.3–99.2%) | 0.774 | Primary |
| IMPORTS | 21 | 20/21 | 95.2% (77.3–99.2%) | 0.889 | Primary |
| REFERENCES | 18 | 8/18 | 44.4% (24.6–66.3%) | 0.043 | Python audit-only |

Relation-presence agreement is 21/21 for CALLS, 21/21 for IMPORTS, and 14/18 for REFERENCES.

### Q2 — normalized language scope

Annotator A's `C` and `C++` labels and Annotator B's `C/C++` label were normalized to `C/C++`; `Python` was unchanged.

| Scope | N | Formal-verdict exact | Percent (95% CI) | Kappa |
|---|---:|---:|---:|---:|
| C/C++ | 40 | 38/40 | 95.0% (83.5–98.6%) | 0.857 |
| Python | 20 | 10/20 | 50.0% (29.9–70.1%) | 0.074 |

All 10 Python formal-verdict disagreements occur in `REFERENCES`. This is an audit-only slice, not part of primary CALLS/IMPORTS agreement.

### Q3 — navigation telemetry

Identical telemetry means equality of `navigation_files`, ordered `navigation_path`, `navigation_hop_count`, `verification_depth`, and `target_recovered_after_navigation` for the same case. The complete bundle agrees for 52/60 cases. Component agreement is 52/60 for navigation files, 52/60 for ordered path, and 53/60 each for hop count, verification depth, and recovery flag. This is a measurement comparison only and does not alter semantic verdicts.

### Q4 — declaration/definition equivalence

Both annotators selected `ONE_VALID_TARGET` in 38 cases. The raw target tuple (`symbol_id`, `path`, `start_line`) agrees in 22/38 cases (57.9%, 95% CI 42.2–72.2%). Applying frozen Declaration–Definition Equivalence V1 to the 10 differing tuples that share the same non-null semantic `symbol_id` raises equivalent-target agreement to 32/38 (84.2%, 95% CI 69.6–92.6%). The remaining six target disagreements require adjudication; no equivalence was inferred for different or absent symbol IDs.

## Disagreement classification and Drift Gate

Formal-verdict disagreements comprise eight `ONE_VALID_TARGET` versus `NO_VALID_TARGET` cases and four `RELATION_NOT_PRESENT` versus `ONE_VALID_TARGET` cases. Ten of the twelve are Python `REFERENCES`; this concentration spans multiple repositories and both disagreement forms. It is classified as `NEW_SYSTEMATIC_SEMANTIC_AMBIGUITY`: the frozen documents do not state a Python REFERENCES-specific rule sufficient to align whether a syntactic occurrence constitutes a relation and whether repository-local binding establishes its target.

**Drift Gate: HOLD — `NEW_SYSTEMATIC_SEMANTIC_AMBIGUITY`.**

No `BLINDNESS_VIOLATION`, `SCOPE_MISMATCH`, or `SCHEMA_INCOMPATIBILITY` was found. The normalized C/C++ label variation is representational only. The two primary-relation formal disagreements and six non-equivalent unique-target disagreements are ordinary case disagreements and are queued for adjudication, not independently treated as gate failures.

## Adjudication queue

Formal-verdict queue (12):

- `FQV1-rocksdb-eb22480ad0a9d65f` — REFERENCES, Python — A ONE_VALID_TARGET / B NO_VALID_TARGET
- `FQV1-brpc-639b4fbd4eb1a885` — REFERENCES, Python — A ONE_VALID_TARGET / B NO_VALID_TARGET
- `FQV1-brpc-3c112669c1d2a328` — REFERENCES, Python — A RELATION_NOT_PRESENT / B ONE_VALID_TARGET
- `FQV1-rocksdb-ec017de0157014f4` — CALLS, C/C++ — A ONE_VALID_TARGET / B NO_VALID_TARGET
- `FQV1-rocksdb-41db0050ca5b26f5` — REFERENCES, Python — A ONE_VALID_TARGET / B NO_VALID_TARGET
- `FQV1-aria2-3b7ff33941c6d59a` — REFERENCES, Python — A ONE_VALID_TARGET / B NO_VALID_TARGET
- `FQV1-aria2-ecdd1dedf78333a5` — IMPORTS, C/C++ — A ONE_VALID_TARGET / B NO_VALID_TARGET
- `FQV1-aria2-c9bbcfab82d72458` — REFERENCES, Python — A RELATION_NOT_PRESENT / B ONE_VALID_TARGET
- `FQV1-brpc-6ce1878baf26a770` — REFERENCES, Python — A ONE_VALID_TARGET / B NO_VALID_TARGET
- `FQV1-brpc-df438b2594cbeea6` — REFERENCES, Python — A RELATION_NOT_PRESENT / B ONE_VALID_TARGET
- `FQV1-brpc-683dfb396789c525` — REFERENCES, Python — A RELATION_NOT_PRESENT / B ONE_VALID_TARGET
- `FQV1-rocksdb-e4c4b582d8cc5646` — REFERENCES, Python — A ONE_VALID_TARGET / B NO_VALID_TARGET

Non-equivalent unique-target queue (6):

- `FQV1-rocksdb-657008a8ca392740` — CALLS
- `FQV1-aria2-c6525c9d8d155f3f` — CALLS
- `FQV1-rocksdb-85a27eca37b8f8c1` — CALLS
- `FQV1-rocksdb-bd1fd621f81874b8` — IMPORTS
- `FQV1-brpc-4f4f2346428539fb` — CALLS
- `FQV1-rocksdb-b968fe7da547e59e` — REFERENCES (Python audit-only)

These 18 distinct cases form the adjudication queue. This audit does not adjudicate them.

## Validation

The structured companion contains the same counts, metrics, gate decision, and case queue. Both artifacts parse/render as plain UTF-8 text, and their SHA256 digests are recorded in the companion checksum file.

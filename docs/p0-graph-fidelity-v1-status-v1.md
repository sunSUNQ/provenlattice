# P0 Graph Fidelity Qualification V1 — Status Report V1

Status snapshot of the P0 Graph Fidelity Qualification V1 pipeline: blind annotation, agreement audits,
source-only adjudication, Gold Set freeze, system prediction join, and deterministic fidelity scoring.
All numbers below are recomputed by versioned scripts from frozen, hash-anchored artifacts.

## 1. Status board

| Phase | Status |
| --- | --- |
| Protocol / sampling frame | FROZEN (protocol commit `12f405c677582a2982d035433bf6837126772716` + 3 frozen addenda) |
| Calibration (25 cases) | QUALIFIED (`calibration-gate-01`, documented deviations, addenda ratified) |
| Blind annotation batches 02–05 | COMPLETE (25 + 60 + 60 + 60 + 64 = 269-case protocol universe) |
| Agreement audits + drift gates | COMPLETE — audits 02/03/04/05 (+ sealed amendments); all C/C++ gates PASS |
| Batch 02 source-only adjudication | COMPLETE (4 CALLS cases, SEALED) |
| Final C/C++ adjudication (batches 03–05) | COMPLETE (queue 13/13 closed, confidence HIGH, SEALED) |
| Gold Set Freeze | SEALED / FROZEN (`cpp-structural-relation-gold-v1`, 174 cases) |
| System Prediction Join V1 | COMPLETE (174/174 matched, 0 duplicates, gold mutation 0) |
| Graph Fidelity Scoring V1 | COMPLETE (deterministic; no interpretation) |
| RQ1 verdict | NOT WRITTEN — failure attribution and claim-boundary review are later phases |

## 2. Universe and provenance

| Universe | n |
| --- | ---: |
| Protocol universe (all languages) | 269 |
| C/C++ Fidelity Universe (frozen) | 174 |
| CALLS gold | 86 |
| IMPORTS gold | 88 |
| Python out-of-scope (audit-only) | 95 |

C/C++ `REFERENCES` is a graph-representation gap (`CXX_REFERENCE_RELATION_NOT_MODELED`, SFC-1) and is
not evaluable for C/C++; it is excluded from the fidelity universe.

Frozen artifact hashes:

| Artifact | SHA256 |
| --- | --- |
| `experiments/fidelity_v1/results/pilot-candidates.json` | `558f78bfd69d5578b09bc9488739808b7e849d196659d1b82d91403453ba2484` |
| `experiments/fidelity_v1/results/sampling-frame-correction-v1.json` | `f4b338224b7928a0daa2e6bda429ce5ef0b196d8e082519adee7d379ba552771` |
| `experiments/fidelity_v1/final-cpp-adjudication.json` | `96ff9b98392c5b52274afdda7442c36670beb6589198686b3282dc021a95fc0e` |
| `experiments/fidelity_v1/gold/cpp-structural-relation-gold-v1.json` | `794751acaf5e0a1376619b41e236976b0c904415940cf97242910d759c5a6d93` |
| `experiments/fidelity_v1/results/system-gold-join-v1.json` | `a9fdd0a5b531e175703c64777c91bd6ba2578cf6db925e392ed1f39752099f6b` |
| `experiments/fidelity_v1/results/graph-fidelity-scoring-v1.json` | `336794b4af7f5d9cbd518f21f2f788789413e2499fce0d668439b459e6d0382a` |

Reproducible builders live in `experiments/fidelity_v1/tools/`:

- `build-final-adjudication-package.ps1` — source-only clean adjudication package (13 cases)
- `build-gold-freeze-v1.ps1` — Gold Set synthesis + freeze (155 agreed + 19 adjudicated)
- `build-system-gold-join-v1.ps1` — Gold LEFT JOIN system prediction on `sample_id`
- `score-graph-fidelity-v1.ps1` — deterministic scoring contract `GRAPH_FIDELITY_SCORING_V1`

## 3. Annotation and adjudication summary

| Cohort | n | CALLS | IMPORTS | Agreed | Adjudicated |
| --- | ---: | ---: | ---: | ---: | ---: |
| calibration_01 | 16 | 8 | 8 | 14 | 2 |
| batch_02 | 38 | 18 | 20 | 34 | 4 |
| batch_03 | 40 | 20 | 20 | 38 | 2 |
| batch_04 | 41 | 23 | 18 | 32 | 9 |
| batch_05 | 39 | 17 | 22 | 37 | 2 |
| total | 174 | 86 | 88 | 155 | 19 |

The 19 adjudicated gold records come from: the sealed Batch-02 adjudication (4), the sealed final C/C++
adjudication (13), and 2 calibration disagreements resolved by frozen protocol addenda (`CALLS_V1` macro
semantics; Evidence Scope V1 owner ratification). No sealed annotation record was modified at any point.

Gold target layer: `UNIQUE 123`, `DIVERGENT 6`, `ABSENT 44`, `INDETERMINATE 1`. The 6 `DIVERGENT` cases are
verdict-agreed cases where the two annotators recorded different (equally sealed) targets; the freeze freezes
the acceptable-target set and does not adjudicate them.

## 4. Deterministic scoring results

Scoring states (174/174 classified exactly once):

| State | n |
| --- | ---: |
| CORRECT_RESOLUTION | 108 |
| WRONG_TARGET_RESOLUTION | 1 |
| MISSED_RESOLUTION_OPPORTUNITY | 20 |
| FALSE_RESOLUTION_ON_ABSENT | 7 |
| JUSTIFIED_ABSTENTION | 37 |
| INDETERMINATE_EXCLUDED | 1 |

Reconciliation gates: target-present 129/129, ABSENT 44/44, INDETERMINATE 1/1.

| Metric | Unweighted sample | Weighted population |
| --- | ---: | ---: |
| Resolved Precision | 0.9310 | 0.8992 |
| Selective Risk = P(wrong \| resolved, evaluable) | 0.0690 | 0.1008 |
| Resolution Coverage (evaluable) | 0.6705 | 0.1866 |
| Operational resolution rate (117/174) | 0.6724 | reported in artifact |
| Target Opportunity Coverage | 0.8450 | 0.2436 |
| False Resolution on Absent Rate | 0.1591 | 0.0468 |
| Abstention Rate (evaluable) | 0.3295 | 0.8134 |
| Abstention Quality | 0.6491 | 0.3393 |
| Missed Resolution Opportunity Rate | 0.1550 | 0.7564 |

Resolved errors decompose as `WRONG_TARGET_RESOLUTION` = 1 and `FALSE_RESOLUTION_ON_ABSENT` = 7
(share among 8 resolved errors: 0.125 / 0.875).

Macro subgroup means (unweighted, subgroup values preserved in the artifact):

- By repository — Resolved Precision: aria2 0.8718, brpc 1.0000, rocksdb 0.9231 (macro 0.9316)
- By relation — Resolved Precision: CALLS 0.8571 (Target Opportunity Coverage 0.7101), IMPORTS 1.0000 (1.0000)

Population weighting uses the frozen stratum weights of `sampling-frame-correction-v1`. The RocksDB
`CALLS_NONRESOLVED` stratum alone carries weight 0.5503 (population 226,886; 9 sampled C/C++ cases:
6 target-present missed resolutions, 3 justified abstentions). This dominance is reported as fact; no
causal interpretation is attached in this report.

Canonical-node correctness is tracked separately from semantic acceptable-target membership:
105 canonical matches, 1 canonical mismatch, 3 not evaluable (resolved `DIVERGENT` cases carry no frozen
canonical target) over the 109 resolved target-present cases.

## 5. Governance notes

- The system prediction was first opened only after the Gold Set was sealed; the join is a raw LEFT JOIN on
  `sample_id` with no correctness rewriting.
- The single `INDETERMINATE` gold case (`FQV1-brpc-a7dd1a2db3530e09`) is excluded from every correctness,
  risk, and abstention denominator by contract.
- 28 `scoring_error_cases[]` (wrong-target, false-resolution-on-absent, missed-resolution) are prepared in the
  scoring artifact with full gold/system fields; failure-mechanism labels (`CANDIDATE_GENERATION_MISS`,
  `RESOLUTION_FAILURE`, ...) are deliberately deferred to the attribution phase.
- Out of scope until a later phase: failure attribution, RQ1 evidence update, paper-level claim boundary
  review, resolver/candidate-generation repair.

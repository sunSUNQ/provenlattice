# C/C++ Structural Relation Gold Set V1 - Freeze Report

```text
status: SEALED_FROZEN
scope:  CXX_PRIMARY (C/C++ CALLS + IMPORTS)
```

## Universe reconciliation

| Quantity | Value |
| --- | ---: |
| C/C++ Fidelity Universe (frozen sampling frame) | 174 |
| Gold records total | 174 |
| CALLS Gold | 86 |
| IMPORTS Gold | 88 |
| Unique sample_ids | 174 |
| Unresolved adjudications | 0 |
| Python records | 0 |
| REFERENCES records | 0 |

CALLS (86) + IMPORTS (88) = 174. Matches sampling-frame-correction-v1 (cpp_fidelity=174; stratum C/C++ sums CALLS=86, IMPORTS=88).

## Cohort reconciliation

| Cohort | Total | CALLS | IMPORTS | Agreed | Adjudicated |
| --- | ---: | ---: | ---: | ---: | ---: |
| calibration_01 | 16 | 8 | 8 | 14 | 2 |
| batch_02 | 38 | 18 | 20 | 34 | 4 |
| batch_03 | 40 | 20 | 20 | 38 | 2 |
| batch_04 | 41 | 23 | 18 | 32 | 9 |
| batch_05 | 39 | 17 | 22 | 37 | 2 |

## Verdict distribution

| final_gold_verdict | n |
| --- | ---: |
| BUILD_CONTEXT_DEPENDENT | 1 |
| NO_VALID_TARGET | 44 |
| ONE_VALID_TARGET | 129 |

## Target-layer status

| target_status | n |
| --- | ---: |
| ABSENT | 44 |
| DIVERGENT | 6 |
| INDETERMINATE | 1 |
| UNIQUE | 123 |

Target-divergent verdict-agreed cases (acceptable_targets frozen as a set; final_gold_target intentionally null; no adjudication performed at freeze): 6

- FQV1-aria2-5ce7af038ff64537 (batch_02, CALLS, acceptable: symbol:e19297531ee5fab31d81e5e0ac59396d114a74bdb947027273f512c0f8ab22fd | src/a2functional.h)
- FQV1-brpc-d12b7bdc3ecd5bbc (batch_02, CALLS, acceptable: symbol:82120524ca00e8c9d25fe43f384959c0fc33f42a3abfd9f6a914232b8541d488 | src/bthread/bthread.cpp)
- FQV1-aria2-c6525c9d8d155f3f (batch_03, CALLS, acceptable: src/util.h | test/UtilTest1.cc)
- FQV1-brpc-4f4f2346428539fb (batch_03, CALLS, acceptable: src/bthread/bthread.h | src/bthread/semaphore.cpp)
- FQV1-rocksdb-7c9c116938584ddb (batch_05, CALLS, acceptable: db/db_test_util.cc | db/db_test_util.h)
- FQV1-rocksdb-3b90b89381b8d13d (batch_05, CALLS, acceptable: include/rocksdb/utilities/stackable_db.h | include/rocksdb/db.h)

## Relation scope policy

```text
CALLS      INCLUDED
IMPORTS    INCLUDED
REFERENCES NOT EVALUABLE FOR C/C++ (CXX_REFERENCE_RELATION_NOT_MODELED, SFC-1)
Python     EXCLUDED (95 python_out_of_scope cases)
```

## Synthesis sources (all sealed)

| Input | Role | Verification |
| --- | --- | --- |
| results/batch-02-cpp-calls-adjudication.json | sealed Batch 02 adjudication (4 cases) | sha256-anchored |
| final-cpp-adjudication.json | sealed final C/C++ adjudication (13 cases) | sha256-anchored |
| results/annotator-a-calibration-01-normalized.json | sealed Annotator A calibration record (normalized) | sha256-anchored |
| results/annotator-b-calibration-01.json | sealed Annotator B calibration record + frozen calibration case metadata | sha256-anchored |
| results/calibration-gate-01.json | sealed calibration gate (python out-of-scope list; D1/D2/D3) | observed-at-freeze |
| results/protocol-addendum-calls-v1-macro-semantics.md | FROZEN addendum (macro semantics; resolves calibration case FQV1-rocksdb-1273fbd969565cef) | frozen-protocol |
| results/protocol-addendum-evidence-scope-v1.md | FROZEN owner-ratified addendum (supersedes OPEN-1; resolves calibration case FQV1-aria2-713b641e93cc620c) | frozen-protocol |
| blind_packages/batch-03/annotator-a/input/annotator-a-blind-view.json | frozen blind view batch_03 (case metadata + annotation candidate scope) | sha256-anchored |
| blind_packages/batch-03/annotator-a/input/batch-03-manifest.json | frozen batch manifest batch_03 (case order) | sha256-anchored |
| blind_packages/batch-04/annotator-a/input/annotator-a-blind-view.json | frozen blind view batch_04 (case metadata + annotation candidate scope) | sha256-anchored |
| blind_packages/batch-04/annotator-a/input/batch-04-manifest.json | frozen batch manifest batch_04 (case order) | sha256-anchored |
| blind_packages/batch-05/annotator-a/input/annotator-a-blind-view.json | frozen blind view batch_05 (case metadata + annotation candidate scope) | sha256-anchored |
| blind_packages/batch-05/annotator-a/input/batch-05-manifest.json | frozen batch manifest batch_05 (case order) | sha256-anchored |
| blind_packages/batch-03/annotator-a/output/annotation-record-template.json | sealed Annotator A batch-03 records | observed-at-freeze |
| blind_packages/batch-03/annotator-b/output/annotation-record-template.json | sealed Annotator B batch-03 records | observed-at-freeze |
| blind_packages/batch-04/annotator-a/output/annotator-a-batch-04-annotations.json | sealed Annotator A batch-04 records | observed-at-freeze |
| blind_packages/batch-04/annotator-b/output/annotation-record-template.json | sealed Annotator B batch-04 records | sha256-anchored |
| blind_packages/batch-05/annotator-a/output/annotator-a-batch-05-annotations.json | sealed Annotator A batch-05 records | sha256-anchored |
| blind_packages/batch-05/annotator-b/output/annotator-b-batch-05-annotation-records.json | sealed Annotator B batch-05 records | sha256-anchored |
| results/annotator-a-batch-02.json | sealed Annotator A batch-02 records | observed-at-freeze |
| results/annotator-b-batch-02.json | sealed Annotator B batch-02 records + frozen batch-02 case metadata | observed-at-freeze |
| results/sampling-frame-correction-v1.json | frozen sampling frame (universe cpp_fidelity=174; CALLS 86 / IMPORTS 88) | frozen-frame |

## Freeze discipline

- No system prediction, resolver output, or Graph Fidelity artifact was read; `results/pilot-candidates.json` was not opened.
- No sealed annotation record was modified; no new adjudication was performed; every final verdict originates from sealed A/B agreement or a sealed adjudication artifact.
- This gold set is read-only from this point. The next phase (system-gold join) must join system predictions ON sample_id without modifying any gold record.


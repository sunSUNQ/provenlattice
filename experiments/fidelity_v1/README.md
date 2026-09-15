# Graph Fidelity Qualification V1 — Pilot Gold Set

This pilot measures resolver correctness independently of Agent behavior. It uses frozen V0.2 C/C++ graph databases for aria2, brpc and RocksDB, and samples `RawReference` decisions rather than only generated edges.

## Scope

- Language: C/C++
- Repositories: aria2, brpc, RocksDB
- Relations: `CALLS`, `IMPORTS`, `REFERENCES` (C/C++ `REFERENCES` is not produced by the extractor — see the capability gap below)
- Strata: each relation is sampled as `RESOLVED` and `NONRESOLVED` (`ambiguous` or `unresolved`)
- Targets: 20 resolved cases and 10 nonresolved cases per repository/stratum, subject to source availability

The six strata are a pilot for resolver decisions, not a claim that all Graph Fabric relation families are covered. `DEFINES`, `CONTAINS`, and sparse `IMPLEMENTS` require a later structural-edge protocol.

### Known capability gap (SFC-1, formalized)

Classification `GRAPH_REPRESENTATION_GAP`, gap code `CXX_REFERENCE_RELATION_NOT_MODELED`: the C/C++ parser/extractor emits no `REFERENCES` RawReference, so no C/C++ REFERENCES universe exists for fidelity audit. C/C++ Fidelity V1 evaluates `CALLS` (86 sampled) and `IMPORTS` (88 sampled) only; the 89 sampled `REFERENCES` cases are Python-source and remain audit-only inside the 269-case Protocol Universe. Formal wording for any report:

> C/C++ REFERENCES relation is currently not represented by the evaluated extraction pipeline; therefore fidelity cannot be estimated for this relation in V1.

This is a graph-representation gap, not a `RETRIEVAL_MISS` and not sampling bias. See `milestone-freeze-p0-fidelity-v1.md` and §7 of `full-annotation-execution-plan-v1.md`.

## Generate the annotation package

```powershell
python experiments/fidelity_v1/build_pilot.py `
  --database aria2=../benchmark-analysis/v0.2-db/aria2.db `
  --database brpc=../benchmark-analysis/v0.2-db/brpc.db `
  --database rocksdb=../benchmark-analysis/v0.2-db/rocksdb.db `
  --output experiments/fidelity_v1/results/pilot-candidates.json
```

The script opens all graph databases read-only and emits deterministic candidates. Every case records `population_N` and `sample_n` for its stratum, source coordinates, system result, candidate symbols, build-context fields, and blank independent-annotation fields. It freezes the status `PILOT_GOLD_SET_READY_FOR_ANNOTATION` and the claim `NO_FIDELITY_VERDICT_YET`.

## Create blinded annotation views

```powershell
python experiments/fidelity_v1/prepare_annotation_views.py `
  --canonical experiments/fidelity_v1/results/pilot-candidates.json `
  --annotator-a experiments/fidelity_v1/results/annotator-a.json `
  --annotator-b experiments/fidelity_v1/results/annotator-b.json
```

The blinded views hide `system.status`, `resolution_strategy`, `confidence`, the selected target, and the sampling stratum. Annotators A and B must not see each other's files. The canonical package remains the audit asset and is joined only after annotation.

## Annotation protocol

Two annotators independently inspect each source relation and record whether a semantic relation exists, its gold target if applicable, and `build_context_status`. Hard-negative/confounder tags include `same_name`, `overload`, `namespace_collision`, `macro`, `conditional_compilation`, `header_definition`, `ambiguous_include`, and `cross_module_homonym`.

For a system `resolved` case, `relation_verdict` is one of `CORRECT_RESOLUTION`, `WRONG_TARGET`, `RELATION_NOT_PRESENT`, `BUILD_CONTEXT_DEPENDENT`, or `INSUFFICIENT_EVIDENCE`. For an `ambiguous` or `unresolved` case it is one of `NO_VALID_TARGET`, `ONE_VALID_TARGET`, `MULTIPLE_VALID_TARGETS`, `BUILD_CONTEXT_DEPENDENT`, or `INSUFFICIENT_EVIDENCE`. A unique target in a nonresolved case is an `UNDER_RESOLUTION` opportunity after the blind result is joined to system status.

The Gold Set is frozen only after disagreement review. The report separates population statistics from human audit: Resolution Coverage and Abstention Rate come from all frozen RawReferences; Resolved Precision, False Resolution Rate, Selective Risk (= `1 - Resolved Precision`), and abstention appropriateness come from annotated cases and are population-weighted by stratum. It reports raw agreement, Cohen's κ, disagreement and adjudication rates, plus results by relation, repository and resolver strategy. Relation Recall and Missing-Reference Recall are explicitly out of scope until an oracle-first recall set exists. A quota shortfall is reported rather than silently backfilled from another relation or repository.

---

## P0 pipeline status (all phases sealed)

```text
Protocol / Sampling            FROZEN     protocol commit 12f405c677582a2... + 3 frozen addenda
Calibration (25 cases)         QUALIFIED  calibration-gate-01 (C/C++ 16; kappa 0.8516 raw / 0.9228 normalized)
Annotation batches 02-05       COMPLETE   calibration 25 + 60 + 60 + 60 + 64 = 269 protocol universe
Agreement audits / drift gates COMPLETE   audits 02(amended), 03(amended), 04(amended), 05 - all C/C++ gates PASS
Adjudications                  COMPLETE   batch-02 (4 cases) + final C/C++ (13/13, HIGH) + 2 calibration
                                          disagreements resolved by frozen protocol addenda
Gold Set Freeze                SEALED     cpp-structural-relation-gold-v1: 174 = 86 CALLS + 88 IMPORTS
System Prediction Join V1      COMPLETE   LEFT JOIN on sample_id; 174/174 matched; 0 duplicates; gold mutation 0
Graph Fidelity Scoring V1      COMPLETE   deterministic 4-view scoring artifact (contract GRAPH_FIDELITY_SCORING_V1)
RQ1 verdict                    NOT WRITTEN  interpretation / failure attribution are later phases
```

Frozen provenance (SHA256):

| Artifact | SHA256 |
| --- | --- |
| `results/pilot-candidates.json` (canonical system prediction) | `558f78bfd69d5578b09bc9488739808b7e849d196659d1b82d91403453ba2484` |
| `results/sampling-frame-correction-v1.json` (frozen weights) | `f4b338224b7928a0daa2e6bda429ce5ef0b196d8e082519adee7d379ba552771` |
| `final-cpp-adjudication.json` (13-case final adjudication) | `96ff9b98392c5b52274afdda7442c36670beb6589198686b3282dc021a95fc0e` |
| `gold/cpp-structural-relation-gold-v1.json` | `794751acaf5e0a1376619b41e236976b0c904415940cf97242910d759c5a6d93` |
| `results/system-gold-join-v1.json` | `a9fdd0a5b531e175703c64777c91bd6ba2578cf6db925e392ed1f39752099f6b` |
| `results/graph-fidelity-scoring-v1.json` | `336794b4af7f5d9cbd518f21f2f788789413e2499fce0d668439b459e6d0382a` |

## Deterministic results snapshot (no interpretation)

Scoring states (174/174, classified exactly once): `CORRECT_RESOLUTION 108`, `WRONG_TARGET_RESOLUTION 1`,
`MISSED_RESOLUTION_OPPORTUNITY 20`, `FALSE_RESOLUTION_ON_ABSENT 7`, `JUSTIFIED_ABSTENTION 37`,
`INDETERMINATE_EXCLUDED 1`. Reconciliation: target-present 129/129, ABSENT 44/44, INDETERMINATE 1/1.

| Metric | Unweighted sample | Weighted population |
| --- | ---: | ---: |
| Resolved Precision | 0.9310 | 0.8992 |
| Selective Risk | 0.0690 | 0.1008 |
| Resolution Coverage (evaluable) | 0.6705 | 0.1866 |
| Operational resolution rate | 117/174 = 0.6724 | weighted equivalent in artifact |
| Target Opportunity Coverage | 0.8450 | 0.2436 |
| False Resolution on Absent Rate | 0.1591 | 0.0468 |
| Abstention Rate (evaluable) | 0.3295 | 0.8134 |
| Abstention Quality | 0.6491 | 0.3393 |
| Missed Resolution Opportunity Rate | 0.1550 | 0.7564 |

Macro subgroup values are preserved in `results/graph-fidelity-scoring-v1.{json,md}` (per repository, per relation,
per stratum) next to the macro means. Resolved errors decompose into `WRONG_TARGET_RESOLUTION` (1) and
`FALSE_RESOLUTION_ON_ABSENT` (7). Six verdict-agreed cases carry target-level divergence and are frozen as
acceptable-target sets (`DIVERGENT`); the single `INDETERMINATE` case (`FQV1-brpc-a7dd1a2db3530e09`) is excluded
from every correctness denominator. The population-weighted view is dominated by the frozen stratum weight of
RocksDB `CALLS_NONRESOLVED` (0.5503) - reported as fact; causal interpretation is out of scope here.

## Governance discipline

- `gold/`, `results/system-gold-join-v1.json`, sealed adjudication and audit artifacts are **read-only** from their
  seal points; every artifact carries SHA256 provenance and a reproducible builder under `tools/`.
- The system prediction (`results/pilot-candidates.json`) was only opened after the Gold Set was sealed.
- Failure-attribution inputs (`scoring_error_cases[]`, 28 cases) are prepared in the scoring artifact, but no
  `CANDIDATE_GENERATION_MISS` / `RESOLUTION_FAILURE` labels are asserted yet.
- Next phases (not started): failure attribution, RQ1 evidence update, and the paper-level claim boundary review.

A full status snapshot with the same numbers lives in `docs/p0-graph-fidelity-v1-status-v1.md`.

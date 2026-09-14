# Graph Fidelity Qualification V1 — Pilot Gold Set

This pilot measures resolver correctness independently of Agent behavior. It uses frozen V0.2 C/C++ graph databases for aria2, brpc and RocksDB, and samples `RawReference` decisions rather than only generated edges.

## Scope

- Language: C/C++
- Repositories: aria2, brpc, RocksDB
- Relations: `CALLS`, `IMPORTS`, `REFERENCES`
- Strata: each relation is sampled as `RESOLVED` and `NONRESOLVED` (`ambiguous` or `unresolved`)
- Targets: 20 resolved cases and 10 nonresolved cases per repository/stratum, subject to source availability

The six strata are a pilot for resolver decisions, not a claim that all Graph Fabric relation families are covered. `DEFINES`, `CONTAINS`, and sparse `IMPLEMENTS` require a later structural-edge protocol.

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

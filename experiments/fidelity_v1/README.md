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

The script opens all graph databases read-only and emits deterministic candidates. Every case records source coordinates, system result, candidate symbols, build-context fields, and blank independent-annotation fields.

## Annotation protocol

Two annotators independently inspect each source relation and record whether a semantic relation exists, its gold target if applicable, whether the system relation is correct, and whether abstention is correct. Hard-negative/confounder tags include `same_name`, `overload`, `namespace_collision`, `macro`, `conditional_compilation`, `header_definition`, `ambiguous_include`, and `cross_module_homonym`.

The Gold Set is frozen only after disagreement review. Precision, conditional coverage, abstention, and selective risk are then calculated by relation type and stratum. A quota shortfall is reported rather than silently backfilled from another relation or repository.

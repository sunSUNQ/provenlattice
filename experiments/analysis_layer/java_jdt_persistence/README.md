# JDT persistence prototype (Issue Pilot #5, research-only)

Prototype for persisting JDT-merged Java call bindings into the derived
analysis layer, replacing the query-time-only `semantic_java` behavior with a
cache that reuses the existing `base_hash` + contract freshness rules.

## What it does

`prototype.py <repo> --db <db> --jdk <jdk21> --jars <jdt-jar-dir> --out <json>`

1. `full_index` (default L1 index; never touches the JVM)
2. one batch `run_jdt_analysis` (optional JDT analyzer, query-time API as-is)
3. `merge_with_l1` audit merge (per-site states: `recovered_by_jdt`,
   `l1_and_jdt_agree`, `jdt_ambiguous`, `conflict_conservative`, ...)
4. per-file persistence into `AnalysisStore` under the provisional analyzer
   slot `ast:java-jdt` (runtime registration; see note below), chunked
   adaptive nodes (<= ~2.8KB payload each), metadata records the prototype
   contract `java-ast-jdt-persist-v1+<classpath-fingerprint[:12]>` and the
   `ast:java` dependency contract
5. measurements: persisted read latency, byte stability (second DB, SHA256
   per file), source-change invalidation + restore, fail-closed selfcheck
   (classpath env removed -> `unavailable`, 0 rows), L1 non-pollution assert

With `--ast-baseline <scope>` the standard analyze flow first materializes a
non-zero `ast:java` baseline (via `analyze_scope`), so the L1 non-pollution
check compares real row counts around the persistence write instead of an
empty 0=0 baseline (review fix, Issue Pilot #5).

Environment values in `results/*.json` are redacted to placeholders
(`jdk-21.0.12.1+1`, `<local-jars-dir>`, manifest basename): product
repositories must not contain local absolute paths. Reproduction uses your
own JDK 21 + stripped JDT jar dir with the same jar set.

## Registry note (prototype-only)

`KNOWN_FEATURES` does not include a `semantic` feature, so the prototype
registers `ast:java-jdt` v1 **in-process** via the public
`register_analyzer` API. The default index dispatches hardcoded analyzers
(not the registry), so unrelated `full_index` processes are unaffected; the
committed artifacts assert this (`l1_non_pollution`). Productionization
belongs to a future feature contract that owns a proper analyzer id.

## Evidence

- `results/gson-persist.json`, `results/hikaricp-persist.json`,
  `results/jgit-persist.json` — pinned commits matching Issue Pilot stage-0
  (gson e2292f9, HikariCP a4d93f4, jgit 6e68739)
- evidence level: **prototype measurement, Windows-only** (Temurin 21.0.12.1+1,
  T9-B JDT jar set); not a product claim
- design discussion: `docs/java-jdt-persistence-design-v1.md`

## Boundary honored (APPROVE_RESEARCH_ONLY)

- no changes under `src/`; no analyzer registration in shipped code
- no merge to main; default index behavior unchanged (JVM never invoked by
  `full_index`; fail-closed preserved)

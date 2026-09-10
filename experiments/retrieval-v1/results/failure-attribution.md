# R1 Failure Attribution

This is observational attribution over the frozen 54-run dataset. No implementation,
task, Ground Truth, metric, or evaluator semantics were changed.

## Dataset-wide

- **Ground Truth / evaluator contract:** all 54 runs were marked unsuccessful because the
  frozen `wrong_path` rule treats legitimate supporting files outside the narrow expected
  list as wrong. Evidence precision remained 1.0 in all runs.
- **Query Interface:** repeated broad symbol lookups, malformed path/CLI attempts, and no
  structured returned/used evidence IDs reduced both efficiency and auditability.
- **Agent Tool Selection:** Knowledge was available in 18 runs but used in only 9.
- **Instrumentation:** first-relevant-evidence latency and Cross-Layer Edge utilization are
  unavailable for every run.

## Task attribution

| Task | Observed zone | Primary attribution |
| --- | --- | --- |
| T01 | Neutral correctness, negative efficiency | Query Interface; Knowledge Usage Gap |
| T02 | Neutral, narrower file set but slower | Query Interface; mixed Agent Tool Selection |
| T03 | Neutral correctness, negative efficiency | Query Interface; Knowledge Usage Gap |
| T04 | Neutral correctness, negative efficiency | Query Interface; Knowledge Usage Gap |
| T05 | Negative/unstable correctness; CodeGraph efficiency gain | CodeGraph/Knowledge Coverage candidate plus Query Interface |
| T06 | Mixed/neutral | Query Interface; Knowledge used but no measured correctness gain |

## What cannot be attributed

Resolver Quality versus Knowledge/CodeGraph Coverage cannot be separated from this dataset,
because query-result entities and edge IDs were not retained in the event schema. The 80
trusted Cross-Layer Edges may have been returned by the observed Knowledge queries, but their
actual use is not auditable. No Resolver or Knowledge change is justified from this run alone.

# Graph Fidelity Scoring V1 - Deterministic Results

```text
status:   SCORING_COMPLETE_NO_INTERPRETATION
contract: GRAPH_FIDELITY_SCORING_V1
inputs:   gold(sealed) x system(canonical) via system-gold-join-v1 (sealed)
claims:   no RQ1 verdict, no paper claim, no attribution in this artifact
```

## Provenance

| Item | Value |
| --- | --- |
| Gold SHA256 | 794751acaf5e0a1376619b41e236976b0c904415940cf97242910d759c5a6d93 |
| System prediction SHA256 | 558f78bfd69d5578b09bc9488739808b7e849d196659d1b82d91403453ba2484 |
| Join SHA256 | a9fdd0a5b531e175703c64777c91bd6ba2578cf6db925e392ed1f39752099f6b |
| Sampling frame SHA256 | f4b338224b7928a0daa2e6bda429ce5ef0b196d8e082519adee7d379ba552771 |
| Scoring script SHA256 | 56124783df4e6616263efebdb00cd978a9dac43400a933449ac0ec20f96dbd54 |
| Created (UTC) / runtime | 2026-09-15T08:50:43Z / 0.70s |

## Scoring states (174/174 classified exactly once)

| State | n |
| --- | ---: |
| CORRECT_RESOLUTION | 108 |
| WRONG_TARGET_RESOLUTION | 1 |
| MISSED_RESOLUTION_OPPORTUNITY | 20 |
| FALSE_RESOLUTION_ON_ABSENT | 7 |
| JUSTIFIED_ABSTENTION | 37 |
| INDETERMINATE_EXCLUDED | 1 |

Reconciliation: target-present 129/129; ABSENT 44/44; INDETERMINATE 1/1.

## Unweighted sample view (descriptive)

N evaluable = 173 (173 evaluable; 1 INDETERMINATE excluded); N resolved (evaluable) = 116; N abstained (evaluable) = 57

| Metric | Value |
| --- | ---: |
| Resolved Precision | 0.9310 |
| Selective Risk = P(wrong | resolved, evaluable) | 0.0690 |
| Resolution Coverage (evaluable) | 0.6705 |
| Operational resolution rate (119/174, reported separately) | 0.6724 |
| Target Opportunity Coverage | 0.8450 |
| False Resolution on Absent Rate | 0.1591 |
| Abstention Rate (evaluable) | 0.3295 |
| Abstention Quality | 0.6491 |
| Missed Resolution Opportunity Rate | 0.1550 |

Resolved error decomposition: 8 resolved errors = WRONG_TARGET 1 (0.1250) + FALSE_RESOLUTION_ON_ABSENT 7 (0.8750)

## Weighted population view (frozen sampling-frame weights)

| Metric | Value |
| --- | ---: |
| Resolved Precision | 0.8992 |
| Selective Risk | 0.1008 |
| Resolution Coverage (evaluable) | 0.1866 |
| Operational resolution rate (weighted, all 174) | 0.1879 |
| Target Opportunity Coverage | 0.2436 |
| False Resolution on Absent Rate | 0.0468 |
| Abstention Rate (evaluable) | 0.8134 |
| Abstention Quality | 0.3393 |
| Missed Resolution Opportunity Rate | 0.7564 |

## Macro by repository (subgroup values preserved)

| Repository | Resolved Precision | Selective Risk | Res.Coverage | Target Opp.Coverage | False-Res/Absent | Abstention Rate | Abstention Quality | Missed Opp.Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| aria2 | 0.8718 | 0.1282 | 0.6610 | 0.8293 | 0.2778 | 0.3390 | 0.6500 | 0.1707 |
| brpc | 1.0000 | 0.0000 | 0.6552 | 0.8444 | 0.0000 | 0.3448 | 0.6500 | 0.1556 |
| rocksdb | 0.9231 | 0.0769 | 0.6964 | 0.8605 | 0.1538 | 0.3036 | 0.6471 | 0.1395 |
| macro mean (unweighted) | 0.9316 | 0.0684 | 0.6709 | 0.8447 | 0.1439 | 0.3291 | 0.6490 | 0.1553 |

## Macro by relation (subgroup values preserved)

| Relation | Resolved Precision | Selective Risk | Res.Coverage | Target Opp.Coverage | False-Res/Absent | Abstention Rate | Abstention Quality | Missed Opp.Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CALLS | 0.8571 | 0.1429 | 0.6588 | 0.7101 | 0.4375 | 0.3412 | 0.3103 | 0.2899 |
| IMPORTS | 1.0000 | 0.0000 | 0.6818 | 1.0000 | 0.0000 | 0.3182 | 1.0000 | 0.0000 |
| macro mean (unweighted) | 0.9286 | 0.0714 | 0.6703 | 0.8551 | 0.2188 | 0.3297 | 0.6552 | 0.1449 |

## Per-stratum view (frozen strata; facts only)

| Stratum | pop_N_cpp | n_cpp | weight | target-present | ABSENT | correct | wrong | missed | false-res/absent | justified-abst | Res.Prec | Abst.Qual |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CALLS_RESOLVED (aria2) | 4769 | 19 | 0.0116 | 14 | 5 | 14 | 0 | 0 | 5 | 0 | 0.7368 | n/a |
| CALLS_NONRESOLVED (aria2) | 35874 | 10 | 0.0870 | 7 | 3 | 0 | 0 | 7 | 0 | 3 | n/a | 0.3000 |
| IMPORTS_RESOLVED (aria2) | 5961 | 20 | 0.0145 | 20 | 0 | 20 | 0 | 0 | 0 | 0 | 1.0000 | n/a |
| IMPORTS_NONRESOLVED (aria2) | 1594 | 10 | 0.0039 | 0 | 10 | 0 | 0 | 0 | 0 | 10 | n/a | 1.0000 |
| CALLS_RESOLVED (brpc) | 12599 | 19 | 0.0306 | 18 | 0 | 18 | 0 | 0 | 0 | 0 | 1.0000 | n/a |
| CALLS_NONRESOLVED (brpc) | 64075 | 10 | 0.1554 | 7 | 3 | 0 | 0 | 7 | 0 | 3 | n/a | 0.3000 |
| IMPORTS_RESOLVED (brpc) | 4408 | 20 | 0.0107 | 20 | 0 | 20 | 0 | 0 | 0 | 0 | 1.0000 | n/a |
| IMPORTS_NONRESOLVED (brpc) | 2605 | 10 | 0.0063 | 0 | 10 | 0 | 0 | 0 | 0 | 10 | n/a | 1.0000 |
| CALLS_RESOLVED (rocksdb) | 41084 | 19 | 0.0996 | 17 | 2 | 16 | 1 | 0 | 2 | 0 | 0.8421 | n/a |
| CALLS_NONRESOLVED (rocksdb) | 226886 | 9 | 0.5503 | 6 | 3 | 0 | 0 | 6 | 0 | 3 | n/a | 0.3333 |
| IMPORTS_RESOLVED (rocksdb) | 8666 | 20 | 0.0210 | 20 | 0 | 20 | 0 | 0 | 0 | 0 | 1.0000 | n/a |
| IMPORTS_NONRESOLVED (rocksdb) | 3771 | 8 | 0.0091 | 0 | 8 | 0 | 0 | 0 | 0 | 8 | n/a | 1.0000 |

Highlighted stratum (fact only): RocksDB CALLS_NONRESOLVED carries population weight 0.5503 of the C/C++ universe - the largest of all strata. No causal interpretation is made here.

## INDETERMINATE observation (excluded from all correctness denominators)

- sample_id: FQV1-brpc-a7dd1a2db3530e09 (brpc, CALLS)
- system_resolved: True; system_status: resolved; strategy: same_file_resolution; confidence: 0.98
- predicted_target: {"symbol_id":"symbol:259c7c2656d9f4c76ac426574621db88e26cd7115529cae9ee092a2e1d145dbc","kind":"Function","qualified_name":"butil.anonymous.__cpuid","path":"src/butil/cpu.cc","start_line":70,"end_line":76}

## Canonical node correctness (separate metric)

evaluable resolved target-present cases: 109; canonical match: 105; canonical mismatch: 1; not evaluable (no frozen canonical, incl. all DIVERGENT): 3. Semantic acceptable-target membership remains the sole Resolved Precision input.

## Error cases prepared for later attribution (no mechanism labels here)

scoring_error_cases: 28 (WRONG_TARGET 1, FALSE_RESOLUTION_ON_ABSENT 7, MISSED_RESOLUTION_OPPORTUNITY 20) - full records in the JSON artifact.

## Discipline

- Gold, system prediction and join artifacts read-only; mutation = 0.
- No resolver/candidate-generation/parser repair; no new annotation or adjudication.
- All metrics recomputable from the frozen inputs by tools/score-graph-fidelity-v1.ps1.


# System Prediction Join V1 - Report

```text
status: JOIN_COMPLETE_NO_SCORING
join:   Gold LEFT JOIN SystemPrediction ON sample_id (gold authoritative)
claims: NO fidelity verdict, NO RQ1 claim in this artifact
```

## Provenance

| Item | Value |
| --- | --- |
| Gold file | gold/cpp-structural-relation-gold-v1.json |
| Gold SHA256 | 794751acaf5e0a1376619b41e236976b0c904415940cf97242910d759c5a6d93 |
| Gold hash verification | PASS (cpp-structural-relation-gold-v1.sha256 + gold-freeze-manifest.json) |
| System prediction file | results/pilot-candidates.json |
| System prediction SHA256 | 558f78bfd69d5578b09bc9488739808b7e849d196659d1b82d91403453ba2484 |
| Join script | tools/build-system-gold-join-v1.ps1 |
| Join script SHA256 | 73996b762dde6d8fefb31050ed5dc74d7a1a49bc4734c7f158d6f18d16a1670f |
| Join key | sample_id |
| Created (UTC) | 2026-09-15T08:35:44Z |
| Runtime | 0.27s |

## Join integrity

| Measure | Value |
| --- | ---: |
| Gold sample IDs | 174 |
| Unique Gold IDs | 174 |
| Matched system predictions | 174 |
| Missing system predictions | 0 |
| Matched + missing | 174 |
| Duplicate system sample IDs | 0 |
| System-only sample IDs | 95 |
| System records total | 269 |
| Resolved cases with empty predicted_target | 0 |
| raw_reference_id mismatches (gold vs system) | 0 |

System-only IDs are the scope-excluded Protocol Universe cases (Python REFERENCES plus Python-source CALLS/IMPORTS stratum leakage), consistent with sampling-frame-correction-v1 scope_excluded_n = 95.

## Derived scoring-ready fields (deterministic, no verdict)

| Field value | n |
| --- | ---: |
| system_resolved = true | 117 |
| system_resolved = false | 57 |
| predicted_target_in_acceptable_targets = true | 108 |
| predicted_target_in_acceptable_targets = false | 1 |
| predicted_target_in_acceptable_targets = null (not evaluable) | 65 |

null = join missing, system abstained, gold layer ABSENT/INDETERMINATE, or empty predicted target. ABSENT rows are never scored as false targets; INDETERMINATE rows are never auto-counted as system errors.

## Discipline

- Gold file read-only; re-hashed unchanged after the join (mutation = 0).
- System prediction read-only; raw fields preserved verbatim (no correct/wrong rewrite).
- No resolver/candidate-generation/parser repair; no re-annotation; no re-adjudication; anomalies are recorded, not fixed.


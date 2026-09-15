# R2.4 Offline Bundle Qualification

No Agent was run. Candidate pools are frozen R2.3 CodeGraph/Knowledge returns; GroundTruthV2 is used only for scoring.

## T01 — document_to_code

| Policy | Size | Required retention | Distractor suppression | Precision | Qualified |
|---|---:|---:|---:|---:|---|
| R2.3 Generic | 39 | 1.000 | 0.000 | 0.026 | baseline |
| Loose | 4 | 1.000 | 1.000 | 0.250 | YES |
| Balanced | 4 | 1.000 | 1.000 | 0.250 | YES |
| Aggressive | 4 | 1.000 | 1.000 | 0.250 | YES |

## T03 — code_to_document

| Policy | Size | Required retention | Distractor suppression | Precision | Qualified |
|---|---:|---:|---:|---:|---|
| R2.3 Generic | 24 | 1.000 | 1.000 | 0.083 | baseline |
| Loose | 4 | 1.000 | 1.000 | 0.500 | YES |
| Balanced | 4 | 1.000 | 1.000 | 0.500 | YES |
| Aggressive | 4 | 1.000 | 1.000 | 0.500 | YES |

## T05 — module_understanding

| Policy | Size | Required retention | Distractor suppression | Precision | Qualified |
|---|---:|---:|---:|---:|---|
| R2.3 Generic | 96 | 1.000 | 1.000 | 0.042 | baseline |
| Loose | 20 | 1.000 | 1.000 | 0.200 | YES |
| Balanced | 13 | 0.333 | 1.000 | 0.077 | NO |
| Aggressive | 8 | 0.333 | 1.000 | 0.125 | NO |

## Recommendation

Loose

## Qualification status

QUALIFIED: Loose is the only policy retaining every required Evidence ID for T01/T03/T05

## Measurement open item

Path Precision Semantics remains unchanged and is not evaluated here.

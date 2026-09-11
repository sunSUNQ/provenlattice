# ProvenLattice V1.0-R2 — T05 Interface Qualification

## Outcome

The R2 interface and artifact gate passed, but the progression gate is **HOLD**. All three
cells used the fixed brpc commit, exact Claude model, Claude Code 2.1.268, clean read-only
workspace, complete artifacts and reproducible evaluation. CodeGraph and Knowledge used physically
separate Core-only and Knowledge databases.

The wider 3-task qualification was not started because Knowledge-R2 reached only 0.667 required
Evidence recall and cited two Evidence IDs that were not observed in a returned bundle.

## T05 results

| Arm | Task success | Required recall | Precision | Turns | Graph / Knowledge queries | Files | Time | Usage | Returned unused | Wrong path |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Native | PASS | 1.000 | 1.000 | 25 | 0 / 0 | 9 | 31.5s | — | 0 | 0 |
| CodeGraph-R2 | PASS | 1.000 | 0.050 | 17 | 15 / 0 | 2 | 39.8s | 0.488 | 21 | 0 |
| Knowledge-R2 | FAIL | 0.667 | 0.125 | 22 | 14 / 2 | 6 | 45.4s | 0.400 | 21 | 0 |

Precision is intentionally strict: only frozen required/optional IDs count as correct used Evidence;
other cited IDs are not silently promoted after observing the run.

## R1 comparison

R1 T05 medians were Native `1.00 / 29 turns / 11 files / 37.0s`, CodeGraph
`0.50 / 20 / 7 / 31.2s`, and Knowledge `0.50 / 30 / 8 / 38.5s`.

- CodeGraph-R2 restored required recall from 0.50 to 1.00 and used 3 fewer turns and 5 fewer files
  than the R1 CodeGraph median. Compared with R2 Native it used 8 fewer turns and 7 fewer files,
  although wall time was 8.3 seconds slower.
- Knowledge-R2 improved recall from 0.50 to 0.667 and reduced turns/files versus R1, but did not
  use the exact required document-section Evidence. It used the required code definition and
  resolved cross-layer link, while citing the document-root Evidence instead.
- Both structured arms still over-queried and returned 21 unused Evidence items. R2 has therefore
  improved observability and CodeGraph recall, but has not yet demonstrated compact Evidence use.

## Frozen diagnosis

This run does not justify Resolver or Knowledge coverage expansion. The required cross-layer link
already exists and was used. The observed gap is at the Agent-facing retrieval/citation boundary:
`find-related-code docs/cn/backup_request.md` anchors the document root, while the Ground Truth
requires a specific child section Evidence ID. The next investigation should remain within the R2
interface contract and determine how a document-path query should expose its relevant child-section
Evidence under the existing budget.

Three invalid configuration attempts are retained locally under
`experiments/retrieval-v2/results/_invalid/`; they are excluded from reported results.

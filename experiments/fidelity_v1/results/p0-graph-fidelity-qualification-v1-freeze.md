# P0 Graph Fidelity Qualification V1 — Final Freeze

> **P0 is closed as a research qualification milestone; the identified Graph Fidelity gaps
> remain open engineering problems and are intentionally deferred until after lower-layer
> evaluation coverage is completed.**

```text
P0 Graph Fidelity Qualification V1
Status: CLOSED

RQ1 Evidence Level: QUALIFIED

freeze_date:     2026-09-15
freeze_git_head: ef1bc8e2b81fee6467db02c7ad34842582d32acf
protocol_commit: 12f405c677582a2982d035433bf6837126772716 (+ 3 frozen addenda)
supersedes:      milestone-freeze-p0-fidelity-v1.md (mid-execution snapshot, 2026-09-14,
                 Status = EXECUTION PHASE) — that snapshot is retained unmodified as history;
                 this document is the terminal state of P0.
```

## 1. Scope (frozen)

```text
Scope:
- ProvenLattice V0.2
- C/C++
- aria2 / brpc / RocksDB
- CALLS / IMPORTS
```

Every claim carried by this milestone keeps the same qualifiers: current V0.2, three
repositories, C/C++, CALLS/IMPORTS, frozen V1 sampling frame. No claim extends beyond this
scope; in particular nothing here supports C/C++ REFERENCES, other languages, other
repositories, or any other system.

## 2. Key findings (frozen)

```text
- Resolved Precision:      93.10% sample / 89.92% population-weighted
- Main limitation:         CALLS coverage
- IMPORTS:                 strong within the frozen benchmark
- C++ REFERENCES:          NOT REPRESENTED / NOT EVALUABLE
- Graph Fidelity problem:  NOT SOLVED
```

Supporting detail (from `rq1-graph-fidelity-evidence-synthesis-v1`):

- 174/174 Gold cases scored exactly once: 108 CORRECT_RESOLUTION, 1 WRONG_TARGET_RESOLUTION,
  20 MISSED_RESOLUTION_OPPORTUNITY, 7 FALSE_RESOLUTION_ON_ABSENT, 37 JUSTIFIED_ABSTENTION,
  1 INDETERMINATE_EXCLUDED.
- All 28 attributed scoring errors are CALLS: 10 CANDIDATE_GENERATION_MISS,
  11 RESOLVER_ABSTENTION, 7 RESOLVER_OVER_RESOLUTION.
- RocksDB `CALLS_NONRESOLVED` carries frozen weight 0.5503; weighted coverage conclusions are
  dominated by that stratum by design of the frozen sampling frame.

## 3. Core artifact hash chain (verified at freeze)

Each stage's SHA256 was recomputed from the files on disk at freeze time and matched the
previously recorded sidecar/provenance values. The chain is ordered; each stage consumes the
previous stage as read-only input.

| Stage | Artifact | SHA256 |
| --- | --- | --- |
| 1. Gold | `experiments/fidelity_v1/gold/cpp-structural-relation-gold-v1.json` | `794751acaf5e0a1376619b41e236976b0c904415940cf97242910d759c5a6d93` |
| 2. Join | `experiments/fidelity_v1/results/system-gold-join-v1.json` | `a9fdd0a5b531e175703c64777c91bd6ba2578cf6db925e392ed1f39752099f6b` |
| 3. Scoring | `experiments/fidelity_v1/results/graph-fidelity-scoring-v1.json` | `336794b4af7f5d9cbd518f21f2f788789413e2499fce0d668439b459e6d0382a` |
| 4. Failure Attribution | `experiments/fidelity_v1/results/graph-fidelity-failure-attribution-v1.json` | `3e864f437002328064d4954a15edff2e018d3e5cf8bedaa43d1c9cefec1683ec` |
| 5. RQ1 Evidence Synthesis | `experiments/fidelity_v1/results/rq1-graph-fidelity-evidence-synthesis-v1.json` | `51ef57ace36ad175061a5f2b2e0b5b7f45682bbf2643f493361f4bfa4878420d` |

Anchors reused from earlier frozen records:

| Anchor | SHA256 |
| --- | --- |
| System prediction (`pilot-candidates.json`) | `558f78bfd69d5578b09bc9488739808b7e849d196659d1b82d91403453ba2484` |
| Sampling frame (`sampling-frame-correction-v1.json`) | `f4b338224b7928a0daa2e6bda429ce5ef0b196d8e082519adee7d379ba552771` |
| Attribution script (`tools/attribute-failures-v1.ps1`) | `f80dceea78ddd6c7136e6495552e674f1e05da8250016311878dec34c87cc0fd` |

## 4. Deferred engineering gaps (open, intentionally not repaired)

These are recorded as standing engineering work items. They are **not** part of P0 and must not
be repaired as a side effect of another RQ's work; when the CALLS repair line starts, it starts
from the Before baseline in Section 5.

| # | Gap | Frozen evidence |
| --- | --- | --- |
| G1 | CALLS candidate coverage — correct repository target absent from the candidate set | 10 of 28 attributed errors: 9 of 20 missed opportunities plus the 1 wrong-target case had candidate-generation miss as primary mechanism |
| G2 | Resolver abstention — correct target present in candidate set but not resolved | 11 of 20 missed opportunities |
| G3 | Receiver/owner over-resolution — single-candidate resolution on external receivers | 7 FALSE_RESOLUTION_ON_ABSENT cases; receiver/owner mismatch in all 7; 6 used `unique_symbol_resolution` |
| G4 | C++ REFERENCES representation gap (`CXX_REFERENCE_RELATION_NOT_MODELED`) | Extraction population = 0; fidelity not evaluable in V1 |

### Deferred ≠ fixed, deferred ≠ failed

```text
deferred != fixed   : no gap above is repaired; no post-repair number exists.
deferred != failed  : each gap is a measured, attributed, sealed observation with a frozen
                      Before baseline; deferral is a sequencing decision, not a negative result.
```

Rationale for the sequencing decision: repairing Resolver / Candidate Generation now would
restart local capability iteration and convert ProvenLattice back into a continuous
feature-repair line. The research mainline instead proceeds to RQ2 while the P0 evidence chain
stays frozen as the comparison baseline.

## 5. Before baseline for the future CALLS repair line

Any future resolver / candidate-generation change MUST re-run the frozen scoring contract
(`GRAPH_FIDELITY_SCORING_V1`) against the same Gold Set (`cpp-structural-relation-gold-v1`,
hash above) before any improvement claim. The Before baseline to beat, per mechanism:

```text
Before (frozen, 28 attributed CALLS errors):
  CANDIDATE_GENERATION_MISS   10
  RESOLVER_ABSTENTION         11
  RESOLVER_OVER_RESOLUTION     7

Before (frozen, headline metrics):
  Resolved Precision           0.9310 sample / 0.8992 weighted
  Target Opportunity Coverage  0.8450 sample / 0.2436 weighted
  False Resolution on Absent   0.1591 sample / 0.0468 weighted
```

An After run that changes extractor, candidates, or resolver invalidates none of the above; it
only becomes a new versioned result joined against the same frozen Gold Set.

## 6. Handover

- RQ1 → **CLOSED** at `QUALIFIED`. Evidence Inventory updated accordingly
  (`docs/provenlattice-evidence-inventory-gap-matrix-v1.md`).
- Next mainline: **P1 / RQ2 — Graph Systems & Scale Qualification V1**
  (`experiments/systems_v1/`): Systems Benchmark Contract V1, run schema, deterministic
  instrumentation over the existing OBSERVED V0.2 baselines.
- Model division: Terra reviews the RQ2 benchmark design once the contract draft exists; Sol is
  not consumed until the RQ2 three-repository data is complete and ready for final evidence
  synthesis.

No Gold, join, scoring, attribution, or synthesis artifact was modified by this freeze; only
`.sha256` sidecars for the two synthesis files (absent before) were added, and this document
plus Evidence Inventory governance updates were written.

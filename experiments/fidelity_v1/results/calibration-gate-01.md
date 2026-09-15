# Calibration Gate 01 — Post-Join Adjudication Report

```text
date: 2026-09-14
phase: calibration-01 post-join adjudication (Annotator A + Annotator B records sealed)
protocol_commit: 12f405c677582a2982d035433bf6837126772716
gate_status: CALIBRATION_QUALIFIED_WITH_DOCUMENTED_DEVIATIONS
full_244_annotation: UNBLOCKED (not started; 269 pilot cases - 25 calibration = 244)
```

## Inputs

| artifact | sha256 |
| --- | --- |
| `annotator-a-calibration-01-normalized.json` | `6cb400447fe7ba6fbd27b19e35ea1e5c9ef3e8b9c46b5e2406756599a780ff8b` |
| `annotator-b-calibration-01.json` (sealed) | `bb85142770dc494f3d560bb702a77c69e3cae7e24c04ea31c67c53e2525b3ed5` |
| `protocol-addendum-calls-v1-macro-semantics.md` | see repo |

Case alignment verified programmatically: Annotator A's 25 case IDs == Annotator B's 25 case IDs.

## Adjudication decisions (applied in order, no parallel changes)

- **D1 — CALLS_V1 macro semantics frozen (option A).** Rule: CALLS_V1 recognizes only the observable
  call semantics at the layer the current Graph Fabric actually models (pre-preprocessing source
  layer). A macro invocation therefore **counts as CALLS**; expansion targets (B), exclusion of
  macros (C), and build-context insufficiency (D) are rejected as inconsistent with that anchor.
  Uniform for all future macro samples; no `ASSERT_EQ` exception. Artifact:
  `protocol-addendum-calls-v1-macro-semantics.md`. Sealed records are not edited; the rule is
  applied symmetrically at gate level.
- **D2 — Annotator A verdict normalization.** `annotator-a-calibration-01-normalized.json`:
  25/25 labels mapped uniquely from A's per-case table via explicit rules MR-1/MR-2/MR-3; **0**
  `UNMAPPABLE_WITHOUT_REANNOTATION`. One MEDIUM-confidence mapping (#3, `INSUFFICIENT_EVIDENCE`,
  target-scope-only reading) with the ambiguity documented in-line. A's original record untouched.
  Recorded observation: A's prose "12 repo-local targets (6 imports + 6 calls)" is inconsistent
  with A's own table (11: 7 imports + 4 calls); the table is authoritative.
- **D3 — Python scope isolated.** The 9 Python-source cases stay in the audit package and are
  excluded from the formal C/C++ fidelity scoring universe:

| field | value |
| --- | --- |
| scope_status | `OUT_OF_SCOPE` (9 cases) / `IN_SCOPE` (16 cases) |
| included_in_protocol_audit | `true` (all 25) |
| included_in_cpp_fidelity_score | `false` (9 Python) / `true` (16 C/C++) |

  Out-of-scope case IDs: `FQV1-rocksdb-ee83baa17e82ced3`, `FQV1-aria2-4fd41bb9bb827c2a`,
  `FQV1-aria2-3ea5b21309de76eb`, `FQV1-aria2-91b984d6e6d0a7ee`, `FQV1-aria2-5d9c6122ac7c4cd4`,
  `FQV1-brpc-734b24f434825a0f`, `FQV1-rocksdb-042e70a2abbb97a5`,
  `FQV1-rocksdb-ff7dddd235f6cd6a`, `FQV1-brpc-3fe7d970be9bff2a`.
  No case deleted; no replacement sampled. The candidate-generator scope leakage (V0.2 graph
  databases modeled Python files under a C/C++-scoped pilot) is preserved as a fact.

## Agreement metrics

Two universes, as required: **protocol-level** (all 25, including scope deviations — evaluates
protocol execution) and **C/C++ in-scope** (16 — the formal scoring universe).

| metric | protocol-level (25) | C/C++ in-scope (16) |
| --- | --- | --- |
| Exact formal-verdict agreement (raw) | 23/25 = 0.920 | 14/16 = 0.875 |
| Cohen's κ (raw) | 0.8516 | 0.7143 |
| Exact formal-verdict agreement (rule-normalized) | 24/25 = 0.960 | 15/16 = 0.938 |
| Cohen's κ (rule-normalized) | 0.9228 | 0.8519 |
| Relation-presence agreement (raw) | 24/25 = 0.960 | 14/16 = 0.875 |
| Relation-presence agreement (rule-normalized) | 25/25 = 1.000 | 15/16 = 0.938 |
| Build-context agreement | 25/25 = 1.000 | 16/16 = 1.000 |

Per-relation (protocol-level; C/C++ in-scope identical except n):

| relation | n | presence raw → normalized | verdict raw → normalized |
| --- | ---: | --- | --- |
| CALLS | 9 | 8/9 → 9/9 | 7/9 → 8/9 |
| IMPORTS | 8 | 8/8 → 8/8 | 8/8 → 8/8 |
| REFERENCES | 8 | 8/8 → 8/8 | 8/8 → 8/8 |

"Rule-normalized" = frozen CALLS_V1 macro rule applied symmetrically to both annotators' records
(affects only `FQV1-rocksdb-1273fbd969565cef`). κ terms: ALL-25 raw p0=0.920/pe=0.4608;
normalized p0=0.960/pe=0.4816; CPP-16 raw p0=0.875/pe=0.5625; normalized p0=0.9375/pe=0.59375.
Caveat: n is small; κ prevalence effects apply; metrics are calibration diagnostics, not fidelity
claims.

## Raw formal-verdict disagreements (both, with resolution status)

1. `FQV1-rocksdb-1273fbd969565cef` (CALLS): A `NO_VALID_TARGET` vs B `RELATION_NOT_PRESENT`
   (B had `gold_relation_exists=false`). **Resolved by D1**: under CALLS_V1 option A the macro
   invocation is a CALLS relation with no repository symbol target → `NO_VALID_TARGET`. Both
   records then agree; no annotator-error adjudication was made.
2. `FQV1-aria2-713b641e93cc620c` (CALLS): A `INSUFFICIENT_EVIDENCE` (package-bound: "needs type
   propagation") vs B `ONE_VALID_TARGET` (cross-file type propagation within the frozen tree:
   `List::append(std::unique_ptr<ValueBase>)` at `src/ValueBase.cc:123`). **OPEN (OPEN-1)**:
   evidence-scope divergence, not a source-fact disagreement — both affirm relation existence and
   the same callee object. Recommendation (NOT frozen by this gate): for the full run, annotator
   evidence scope = blinded package + read-only navigation of the frozen source tree (as the pilot
   README and annotation task already permit); a target determinable by cross-file type propagation
   within the frozen tree counts as determined. Requires owner ratification before the 244-case run.

## Gate rationale

The three HOLDs are closed: macro semantics frozen by a uniform rule that explains the `ASSERT_EQ`
divergence without a per-sample exception; A's labels normalized into the formal vocabulary with
zero unmappable cases; Python scope isolated with audit retention. κ is in the substantial-to-
almost-perfect band on both universes (0.85 raw / 0.92 normalized protocol-level; 0.71 raw / 0.85
normalized in-scope), relation-presence reaches 25/25 under the frozen rule, and IMPORTS/REFERENCES
agree fully. One documented open item (evidence-scope rule) is carried as a recommendation.

```text
gate_status: CALIBRATION_QUALIFIED_WITH_DOCUMENTED_DEVIATIONS
deviations: [D1 CALLS_V1 addendum, D2 A-label normalization product, D3 Python scope exclusion,
             OPEN-1 evidence-scope rule recommendation]
full_244_annotation: UNBLOCKED (not started)
```

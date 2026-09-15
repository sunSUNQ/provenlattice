# Milestone Freeze — P0 Graph Fidelity Qualification V1

```text
freeze_date: 2026-09-14
protocol_commit: 12f405c677582a2982d035433bf6837126772716
companion_artifacts:
  - full-annotation-execution-plan-v1.md / full-annotation-execution-plan-v1.json
  - sampling-frame-correction-v1.json
  - protocol-addendum-calls-v1-macro-semantics.md (FROZEN)
  - protocol-addendum-evidence-scope-v1.md (FROZEN)
  - protocol-addendum-decl-def-equivalence-v1.md (FROZEN)
```

## Frozen state snapshot

```text
P0 Graph Fidelity Qualification V1
Status = EXECUTION PHASE

Framework / Protocol             FROZEN
Sampling / Reweighting           FROZEN
Known Coverage Gap               RECORDED
Capability Repair                DEFERRED

C++ CALLS                        REPRESENTED
C++ IMPORTS                      REPRESENTED
C++ REFERENCES                   NOT REPRESENTED

Calibration                      QUALIFIED

A02                              NEXT
Audit 02                         AFTER A02
Batch 02 B                       COMPLETE
Batch 02 Agreement               PENDING
Batch 03                         BLOCKED BY DRIFT GATE

Graph Fidelity Verdict           NOT YET AVAILABLE
```

## P0 as four separated research questions

```text
1. Representation Coverage
      What does the C/C++ graph actually model?
      → CALLS / IMPORTS have population; REFERENCES = 0
      → CXX_REFERENCE_RELATION_NOT_MODELED

2. Resolution Fidelity
      For modeled relations, are resolved / abstention decisions correct?
      → waits on Gold annotation (A02 → Audit 02 → remaining batches)

3. Representation Canonicalization
      Is a decl/def twin a semantic error?
      → Semantic Target Correctness vs Canonical Node Correctness are separated

4. Verification Difficulty
      How deep must human source navigation go to confirm a relation?
      → L0–L4, analysis-only
```

This decomposition — not a single final "Precision = xx%" — is the deliverable structure of
Fidelity V1.

## SFC-1 elevated: Graph Coverage Gap (research-conclusion boundary)

SFC-1 is a formal representation boundary of the evaluated pipeline — not a sampling remark,
not `RETRIEVAL_MISS`, and not sampling bias:

```text
classification: GRAPH_REPRESENTATION_GAP
gap_code:       CXX_REFERENCE_RELATION_NOT_MODELED

mechanism:
  C/C++ parser/extractor
    → emits no REFERENCES RawReference
    → no C/C++ REFERENCES universe exists for Fidelity audit
```

Mandatory formal wording (replaces any "C/C++ REFERENCES fidelity 未测" phrasing):

> **C/C++ REFERENCES relation is currently not represented by the evaluated extraction
> pipeline; therefore fidelity cannot be estimated for this relation in V1.**

C/C++ Fidelity Universe relation status:

| Relation   | C/C++ population | Gold scoring | Status |
| --- | ---: | ---: | --- |
| CALLS      | 385,287 | 86 sampled | EVALUATED |
| IMPORTS    |  27,005 | 88 sampled | EVALUATED |
| REFERENCES |       0 |  0 | CAPABILITY GAP / NOT EVALUABLE |

Python REFERENCES (population 25,697 RawReferences; 89 sampled cases) remains in the 269-case
Protocol Universe as audit-only evidence and never enters C/C++ fidelity scoring.
(Arithmetic correction: the SFC-1 text originally wrote 26,697; the frozen strata sum to
19+662+109+773+2891+21243 = 25,697.)

### Repair deferral (standing)

The `CXX_REFERENCE_RELATION_NOT_MODELED` gap is **not** to be repaired during Fidelity V1.
The CALLS / IMPORTS baseline completes first. Deferring the repair preserves a clean
capability-addition evidence chain:

```text
Before:         C/C++ REFERENCES population = 0
Implementation: extractor adds REFERENCES emission (future, out of Fidelity V1 scope)
After:          C/C++ REFERENCES population > 0 + independent Fidelity Gold Set qualification
```

## Reporting rule (SFC-3 guard)

rocksdb CALLS_NONRESOLVED alone carries 0.5503 of the C/C++ population weight, so a single
"Population-weighted Fidelity = XX%" would largely report that one stratum and must never be the
main conclusion. Every headline metric — Resolved Precision, False Resolution Rate, and
Selective Risk — is reported in three views:

```text
1. Population-weighted           → reflects the real graph population
2. Macro by relation/repository  → prevents large strata from drowning others
3. Per-stratum                   → true bottleneck localization

breakdowns:
  overall weighted / CALLS macro / IMPORTS macro
  aria2 / brpc / rocksdb
  resolved / nonresolved
  each stratum
```

## Decl/Def Equivalence V1 — frozen at V1 scope

The two-layer rule (Semantic Target Correctness vs Canonical Node Correctness) stays frozen at
`DECLARATION_DEFINITION_TWIN` only. Extensions (forward declaration, interface/implementation,
generated wrapper/implementation, alias/canonical type) are future versioned addenda, not V1.

The `semantic = CORRECT / canonical = NON_CANONICAL_TWIN` split is deliberately retained: it
prevents the graph schema's canonicalization choice from being recorded as a semantic resolution
error.

## Verification Depth (analysis-only dimension)

Navigation evidence (`navigation_files_count` / `navigation_hops`, already recorded by the B02
enrichment) is retained for a future complexity axis, provisionally:

```text
L0 = same snippet      L1 = same file
L2 = cross file        L3 = cross module
L4 = build-context dependent
```

No schema change in V1; frozen verdicts are unaffected. The intended analysis is resolver
accuracy vs verification depth (e.g., L0/L1 vs L2/L3 precision deltas) to steer the next
resolver iteration.

## Sequencing (standing)

```text
A Batch 02 (PENDING)
  → B Batch 02 (COMPLETE)
  → Blind Agreement Audit 02 (incl. navigation-stratified agreement)
  → Drift Gate
  → PASS
  → Batch 03 A/B
```

B03 must not start before A02 completes. No new protocol work is needed before A02.

## Batch 02 agreement audit — mandatory questions

1. CALLS vs IMPORTS formal-verdict agreement, reported separately (not pooled).
2. C/C++ in-scope vs Python audit-only agreement — materially different or not.
3. Local-only (L0/L1) vs cross-file (L2+) navigation agreement — materially different or not.
4. On `DECLARATION_DEFINITION_TWIN` cases: Semantic Target Correctness agreement vs Canonical
   Node Correctness agreement, reported separately. Semantic agreement exceeding canonical
   agreement (e.g. 100% vs 80%) means humans agree on "who is referenced" while the graph node
   representation differs — stratified fidelity evidence, not annotator error.

Audit 02 is strictly limited to Q1–Q4 plus the standard checks (case alignment, blindness,
schema validity, relation-presence agreement, formal-verdict agreement, Cohen's κ,
build-context agreement, protocol issue categories). No new metrics, no new rules, no protocol
edits. Output is a single `Drift Gate: PASS / HOLD`; HOLD is reserved for a new systematic
semantic ambiguity, a blindness violation, a scope mismatch, or a schema incompatibility.
Ordinary fact divergences go to adjudication without blocking Batch 03.

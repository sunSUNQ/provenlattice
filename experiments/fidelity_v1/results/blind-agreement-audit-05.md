# Batch 05 Blind Agreement Audit (Audit 05)

Artifact: `blind-agreement-audit-05` | Date: 2026-09-15
Auditor role: independent Agreement Auditor (not Annotator A, not Annotator B).

Scope: consistency audit of the sealed A05 / B05 annotation records only.
No source-only adjudication was performed; no system prediction, resolver, or
Graph Fidelity material was read; no final Gold verdict or final target was
decided.

---

## Status

```
Batch 05 Blind Agreement Audit
Status: COMPLETE
```

Annotator inputs (allowed read set only):

| | Annotator A | Annotator B |
|---|---|---|
| Agent / model | opencode CLI agent / glm-5.3-flash | Codex / GPT-5 |
| Status | VALID + SEALED | COMPLETE + SEALED |
| Blindness violations | 0 (batch-05 case-specific exposure = 0 per provenance audit) | 0 |
| Opposite annotator access | 0 | 0 |
| System prediction access | 0 | 0 |

Cross-model diversity = YES; independent sessions = YES; independent
packages = YES. The disclosed A05 packaging/annotation role-separation
deviation is retained in methodology metadata; the independent provenance
audit already adjudicated it (RETAIN / VALID, batch-05 case-specific exposure
= 0), and this audit does not re-adjudicate it.

---

## Preflight

```
A sample count        = 64        B sample count        = 64
Case ID alignment     = 64/64     Case order alignment  = 64/64
(matches frozen manifest and both blind views; 0 relation-type mismatches)
C/C++ membership      = 39/39     Python membership     = 25/25
A sealed              = YES       B sealed              = YES
A usable              = YES       B usable              = YES
Schema violations     = 0         Telemetry consistency = 0 violations
Repository mutations  = 0         STOP condition        = not triggered
```

Sealed-hash verification (recomputed by this audit):

- Annotator A package: 9/9 `SHA256SUMS` entries OK.
- Annotator B package: 9/9 `SHA256SUMS` entries OK.
- A annotations `sha256 = 08915528c97394f9ee52453190ed7241a125a739e8c3995c222754b951dee622`
  — matches the hash recorded in A's execution note.
- B annotation records `sha256 = 560d08cc940bdfa6eb4416fd0298a98a441845d184bdcce5e93f5e212f2c220c`
  and B execution metadata `sha256 = f452c29c9987e4d50376b980bf22fce7903799caf9f2e1d0e456e2877380fb3e`
  — both match `annotator-b-batch-05-seal.json`.
- B05 first attempt in the A05 session was self-blocked (independence
  violation, 0/64 performed); B05 was completed in a fresh session, satisfying
  the provenance-audit prerequisite. The blocked-attempt note contains no
  annotation content.

Observed metadata nuance (recorded, non-blocking): A's execution note cites a
package manifest hash `5b53611f…` and B's blocked note cites `c7b17d0a…`,
neither of which equals the current frozen package manifests (`67ad27db…`,
`8e616508…`). All currently frozen artifacts (SHA256SUMS, payloads, package
audits, seal, annotation-hash records) mutually verify, and the blind-view and
annotation hashes cited in the notes match the frozen state — consistent with
a manifest revision after the notes were written. Recorded here; not
re-adjudicated.

---

## Metric definitions used (disclosed by the auditor)

- **Exact formal-verdict agreement** — equality of the frozen 6-label
  `formal_verdict`.
- **Raw agreement** — binary valid-target signal: PRESENT =
  {ONE_VALID_TARGET, MULTIPLE_VALID_TARGETS} vs ABSENT = {NO_VALID_TARGET,
  RELATION_NOT_PRESENT}. (BUILD_CONTEXT_DEPENDENT / INSUFFICIENT_EVIDENCE: 0
  occurrences in Batch 05.)
- **Relation-presence agreement** — agreement on the raw `gold_relation_exists`
  field as recorded by each annotator. Field-semantics divergence observed:
  A recorded `true` on 64/64 (including its NO_VALID_TARGET cases), B aligned
  the field with its verdict (`false` exactly on its 5 RELATION_NOT_PRESENT
  cases).
- **Normalized build-context agreement** — auditor-defined normalization:
  A's `SOURCE_SUFFICIENT` and B's `NOT_APPLICABLE` both express "verdict not
  conditioned on build context". The frozen template constrains no value set
  for this field; the raw vocabulary divergence is reported alongside.
- **Cohen's κ** — computed over the stated category set; reported as **not
  informative** where a category margin is degenerate.

---

## Overall Agreement (n = 64)

```
Exact formal-verdict agreement   56/64 = 0.8750
Raw agreement                    56/64 = 0.8750
Relation-presence (gold field)   59/64 = 0.9219   κ = not informative (A margin degenerate)
Normalized build-context         64/64 = 1.0000   (raw label agreement 0/64 — vocabulary divergence only)
Formal-verdict Cohen's κ         0.7613   (po 0.8750, pe 0.4763) — informative
Presence-binary κ                0.7478
```

Verdict cross-tab:

| A \ B | ONE_VALID_TARGET | NO_VALID_TARGET | RELATION_NOT_PRESENT |
|---|---|---|---|
| ONE_VALID_TARGET | 33 | 3 | 5 |
| NO_VALID_TARGET | 0 | 23 | 0 |

Neither annotator used MULTIPLE_VALID_TARGETS, BUILD_CONTEXT_DEPENDENT, or
INSUFFICIENT_EVIDENCE.

---

## Primary / Audit-only tracks

Denominator reconciliation **closes**:

```
C/C++ CALLS 17 + C/C++ IMPORTS 22 = 39   (C/C++ primary)
Python audit-only                 = 25
Reconciliation issues: none
```

### C/C++ primary (n = 39)

```
formal agreement = 37/39 = 0.9487
κ                = 0.8660  (informative)
relation-presence (gold field) = 39/39 = 1.0000  (κ not informative — degenerate margins)
normalized build-context       = 1.0000
```

### C/C++ CALLS (n = 17)

```
formal agreement = 16/17 = 0.9412
κ                = 0.7671  (informative)
```

### C/C++ IMPORTS (n = 22)

```
formal agreement = 21/22 = 0.9545
κ                = 0.8991  (informative)
```

### Python REFERENCES — audit-only (n = 23)

```
formal agreement = 17/23 = 0.7391
κ                = 0.5660  (informative)
target-cardinality agreement = 0.7391 (κ 0.4651)
status = audit-only / separate HOLD — C/C++ gate impact = NONE
```

Python REFERENCES agreement is reported as a consistency change for the
record. The existing HOLD is **not** lifted, and this result does not gate
C/C++ primary Fidelity V1.

### Python CALLS — audit-only (n = 2)

```
formal agreement = 2/2 = 1.0000   κ = not informative (degenerate margins, n=2)
```

### Python audit-only total (n = 25)

```
formal agreement = 19/25 = 0.7600   κ = 0.5833
```

---

## Target Cardinality

Observed `valid_target_count` values: A {0: 23, 1: 41}; B {0: 31, 1: 33}.
Only 0/1 occur for both annotators (no MULTIPLE_VALID_TARGETS verdicts), so
the cardinality layer coincides with the presence layer.

```
Overall exact agreement   56/64 = 0.8750   κ 0.7478
C/C++                     37/39 = 0.9487   κ 0.8660
C/C++ CALLS               16/17 = 0.9412   κ 0.7671
C/C++ IMPORTS             21/22 = 0.9545   κ 0.8991
```

Supplementary (verdict-agreed cases where both chose a unique target, n = 33):
selected-target path agreement 31/33 = 0.9394. Two verdict-agreed cases differ
in selected target path — `FQV1-rocksdb-7c9c116938584ddb`
(`db/db_test_util.cc` vs `db/db_test_util.h`) and
`FQV1-rocksdb-3b90b89381b8d13d` (`include/rocksdb/utilities/stackable_db.h`
vs `include/rocksdb/db.h`). These are informational, non-gating, and supplied
to adjudication as context; no equivalence claim is made here.

---

## Navigation Analysis

Derived only from frozen telemetry (`navigation_files`, `navigation_files_count`,
`navigation_path`, `navigation_hop_count`). Disclosed derivation rule:
CROSS_FILE := (navigation_files_count > 0) OR (navigation_hop_count > 0) OR
(navigation_path length > 1); LOCAL_ONLY := otherwise.

```
                    n                    formal agreement   cardinality   presence
A LOCAL_ONLY        36                   0.8333             0.8333        0.8333
A CROSS_FILE        28                   0.9286             0.9286        0.9286
B LOCAL_ONLY        39                   0.7949             0.7949        0.7949
B CROSS_FILE        25                   1.0000             1.0000        1.0000

Dimension agreement 61/64 = 0.9531
  A-local/B-local 36 · A-cross/B-cross 25 · A-local/B-cross 0 · A-cross/B-local 3
```

The 3 dimension-divergent cases: the two C/C++ formal disagreements (B did no
navigation after concluding no in-tree target) and `FQV1-rocksdb-6dc21b13eb5505ab`
(verdict agreed).

`target_recovered_after_navigation`:

```
A count = 27    B count = 25
A/B agreement = 62/64 = 0.9688   (both true 25, A-true/B-false 2, A-false/B-true 0)
```

The 2 divergent recovery cases are exactly the 2 C/C++ formal disagreement
cases.

---

## Observed verification-depth labels

These are observed labels only; the frozen protocol defines no semantic
mapping for L0–L4, and none is asserted here.

```
A distribution: L0 = 51, L1 = 13
B distribution: L1 = 39, L2 = 25

Joint pair (A/B) → n, formal agreement:
  L0/L1 → 37, 0.8108
  L0/L2 → 14, 1.0000
  L1/L1 →  2, 0.5000
  L1/L2 → 11, 1.0000
```

---

## Q4 Decl/Def

```
Q4 = NOT COMPUTABLE
```

The sealed A/B records and blind views contain no
`target_equivalence_group` / `acceptable_targets` / `canonical_target` frozen
metadata. Equivalence membership was not constructed post hoc, per protocol.

---

## C/C++ Disagreement Classification (audit classification only)

2 C/C++ formal-verdict disagreements. No correctness decision is made here.

| Case | Relation | A | B | Primary classification | Sub-cause |
|---|---|---|---|---|---|
| FQV1-brpc-bc38ae52a3ef3090 | CALLS | ONE_VALID_TARGET (1; `src/butil/strings/string_piece.h`, cites inline definition at string_piece.h:214; vendored butil treated as in-tree) | NO_VALID_TARGET (0; "referent is external to the frozen repositories") | TARGET_CARDINALITY_DISAGREEMENT | in-tree vs external referent scope judgment — UNRESOLVED_FOR_ADJUDICATION |
| FQV1-brpc-547d0bee05c50525 | IMPORTS | ONE_VALID_TARGET (1; `#include "bthread/bthread.h"` → `src/bthread/bthread.h`) | NO_VALID_TARGET (0; "referent is external to the frozen repositories") | TARGET_CARDINALITY_DISAGREEMENT | include-target resolution scope (in-tree vs external) — UNRESOLVED_FOR_ADJUDICATION |

Python disagreements (6, audit-only, informational — outside the C/C++
taxonomy): 5 cases show A ONE_VALID_TARGET (same-file/same-line binding target)
vs B RELATION_NOT_PRESENT ("binding occurrence, not a semantic reference");
1 case (`FQV1-aria2-7d6c74d82bb26ca5`) shows A ONE_VALID_TARGET vs B
NO_VALID_TARGET (referent external). These belong to the separate Python
REFERENCES protocol study.

---

## Adjudication Queue

```
C/C++ formal disagreements queued: 2
  1. FQV1-brpc-bc38ae52a3ef3090   (CALLS)
  2. FQV1-brpc-547d0bee05c50525   (IMPORTS)

Supplementary non-gating context (verdict-agreed, target-path differs):
  - FQV1-rocksdb-7c9c116938584ddb
  - FQV1-rocksdb-3b90b89381b8d13d
```

This audit decides no "A correct / B correct", no final Gold verdict, and no
final target. All queued items await source-only adjudication in a later
phase.

---

## Drift Gate 05 (frozen four-condition gate)

| Condition | Result |
|---|---|
| NEW_SYSTEMATIC_SEMANTIC_AMBIGUITY | not triggered — the 2 C/C++ disagreements are case-level referent-scope judgments; no evidence of a newly introduced systematic ambiguity in the frozen protocol |
| BLINDNESS_VIOLATION | not triggered — A05 batch-05 case-specific exposure = 0; B05 violations = 0; the blocked B05 attempt demonstrates independence enforcement |
| SCOPE_MISMATCH | not triggered — identical 64/39/25 composition, 64/64 membership and order, identical frozen protocol hashes across packages |
| SCHEMA_INCOMPATIBILITY | not triggered — schema_version 2 identical, telemetry schema identical, 128/128 records schema-complete; label-vocabulary divergences (language_scope, build_context_status) are conventions on unconstrained fields, not schema incompatibilities |

Explicitly non-holding factors: agreement/κ levels, cross-model difference
(GLM vs GPT-5), ordinary target disagreements, candidate-missing questions,
navigation difficulty — these are analysis/adjudication matters only.

```
C/C++ Drift Gate 05 = PASS
```

---

## Final Report

```
Batch 05 Blind Agreement Audit
Status: COMPLETE

Case Alignment: 64/64

C/C++ primary:
n = 39
formal agreement = 0.9487 (37/39)
κ = 0.8660

CALLS:
n = 17
formal agreement = 0.9412 (16/17)
κ = 0.7671

IMPORTS:
n = 22
formal agreement = 0.9545 (21/22)
κ = 0.8991

Python REFERENCES:
n = 23
formal agreement = 0.7391 (17/23)
κ = 0.5660
status = audit-only / separate HOLD (C/C++ gate impact = NONE; HOLD not lifted)

Target Cardinality:
overall 0.8750 (κ 0.7478) · C/C++ 0.9487 (κ 0.8660)
CALLS 0.9412 (κ 0.7671) · IMPORTS 0.9545 (κ 0.8991)
observed counts 0/1 only; cardinality layer coincides with presence layer

Navigation:
LOCAL_ONLY  A 36 / B 39 · CROSS_FILE  A 28 / B 25
dimension agreement 0.9531 · B-CROSS_FILE stratum formal agreement 1.0000
target_recovered_after_navigation: A 27 · B 25 · agreement 0.9688

Observed verification-depth labels:
A: L0 51, L1 13 · B: L1 39, L2 25 (observed labels only; no semantics asserted)

C/C++ disagreements: 2

Adjudication queue: 2

C/C++ Drift Gate: PASS

P0 annotation mainline: READY FOR FINAL ADJUDICATION CLOSURE
```

---

Prohibited next steps were not executed: source-only adjudication, Gold Set
freeze, system prediction join, Graph Fidelity scoring, resolver/candidate
generation repair. No sealed annotation record was modified.

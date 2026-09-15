# Full Annotation Execution Plan V1

```text
status: ACTIVE (partition rule PLAN-1 RATIFIED by owner, 2026-09-14)
date: 2026-09-14
protocol_commit: 12f405c677582a2982d035433bf6837126772716
addenda_in_force:
  - protocol-addendum-calls-v1-macro-semantics.md (FROZEN)
  - protocol-addendum-evidence-scope-v1.md (FROZEN)
  - protocol-addendum-decl-def-equivalence-v1.md (FROZEN)
structured_plan: full-annotation-execution-plan-v1.json (contains the frozen batch manifests)
milestone_freeze: milestone-freeze-p0-fidelity-v1.md (2026-09-14)
coverage_gap: SFC-1 formalized as GRAPH_REPRESENTATION_GAP / CXX_REFERENCE_RELATION_NOT_MODELED (§7)
```

## 1. Universe accounting (corrected and verified)

Full-package verification (extension distribution over all 269 frozen cases, against the frozen
`benchmark-analysis` C/C++ extension set `.c/.cc/.cpp/.cxx/.c++/.h/.hh/.hpp/.hxx/.inc`):

```text
Protocol Universe            269  (all frozen cases; protocol executability/repeatability)
C/C++ Fidelity Universe      174  (2 .c + 104 .cc + 39 .cpp + 29 .h)
Python OUT_OF_SCOPE           95  (rocksdb 34 / aria2 30 / brpc 31; retained in audit)
```

**Correction to the owner review's assumption** (recorded verbatim in the plan JSON): the "9
Python" figure is true only for calibration batch 01. The whole package contains **95**
Python-source cases, so the C/C++ Fidelity Universe is **174, not 260**, and the remaining formal
C/C++ scoring n after calibration is **158, not 244**. The remaining 244 samples are all still
annotated as protocol assets; scope filtering applies at scoring time.

```text
remaining samples            244  = 158 C/C++ (scoring) + 86 Python (audit-only)
calibration consumed          25  = 16 C/C++ (scoring) +  9 Python (audit-only)
```

Optional follow-up (PLAN-2, owner decision, not executed): a supplementary C/C++-only sampling
round could enlarge the 174-case scoring universe; it requires an explicit protocol note because
the candidate set is FROZEN.

## 2. Batch plan (manifests frozen, rule pending ratification)

Partition: contiguous windows of the deterministic Annotator-A blinded view order (the verified
Calibration Batch 01 convention). **Ratified by the owner (PLAN-1, 2026-09-14).** Manifests are
embedded in the plan JSON and are frozen.

| batch | window | n | C/C++ | Python (audit-only) |
| --- | --- | ---: | ---: | ---: |
| batch_01_calibration | positions 1-25 | 25 | 16 | 9 |
| batch_02 | positions 26-85 | 60 | 38 | 22 |
| batch_03 | positions 86-145 | 60 | 40 | 20 |
| batch_04 | positions 146-205 | 60 | 41 | 19 |
| batch_05 | positions 206-269 | 64 | 39 | 25 |

Per batch: A/B independent annotation → agreement audit → protocol drift check. **No protocol
edits per batch.**

## 3. Per-case record schema (full phase)

Every record carries at least (full definitions in the plan JSON):

```text
sample_id, batch_id, annotator_id, relation_type,
language_scope (CPP_IN_SCOPE | PYTHON_OUT_OF_SCOPE, frozen extension rule),
gold_relation_exists,
formal_verdict (blind world-fact space; stratum join post-hoc),
valid_target_count (0|1|2|...|INDETERMINATE),
selected_target_if_unique {symbol_id, path, start_line},
build_context_status (SOURCE_SUFFICIENT | BUILD_CONTEXT_DEPENDENT + reason),
navigation_files[], evidence_locations[],
difficulty_tags (frozen vocabulary), confidence (HIGH|MEDIUM|LOW),
protocol_issue (null | {id, description})
```

`navigation_files[]` is mandatory: Evidence Scope V1 makes cross-file navigation admissible, so
navigation depth becomes measurable per relation (analysis input for "which relations need deeper
navigation for human confirmation").

Verification Depth is an **analysis-only** dimension derived from `navigation_files[]` /
`evidence_locations[]` (B02 already records `navigation_files_count` / `navigation_hops`):
L0 same-snippet / L1 same-file / L2 cross-file / L3 cross-module / L4 build-context-dependent.
No schema change; frozen verdicts are unaffected. It supports a later
resolver-accuracy-vs-verification-depth analysis.

Execution flow per sample:

```text
Sample → Blind view → Read source → Allowed read-only navigation (Evidence Scope V1)
→ Determine relation existence → Determine target cardinality → Assess Build Context
→ Assign formal verdict → Record evidence path
```

Verdict semantics note: `INSUFFICIENT_EVIDENCE` only when a case is undeterminable under the full
Evidence Scope V1; `EVIDENCE_SCOPE_TOO_NARROW` remains an audit-only process tag, never a verdict.

## 4. Protocol Drift Gate (per batch)

Checks:

```text
Blindness violations = 0
Schema violations = 0
Case alignment = 100%
Build-context completeness = 100%
Relation-presence agreement
Formal-verdict agreement
Cohen's kappa
new protocol issue categories
```

HOLD policy: HOLD only for one of the four blocking conditions — a **new systematic semantic
ambiguity**, a **blindness violation**, a **scope mismatch**, or a **schema incompatibility**.
Ordinary fact divergences proceed to adjudication without pausing the line. Proposed numeric
tripwires (owner-ratifiable defaults, recorded in the plan JSON): raw formal-verdict agreement
< 0.80, κ < 0.60, or relation-presence agreement < 0.90 flags a batch for owner review.

Audit 02 scope is frozen: the four mandatory questions (§5) plus the standard checks listed
above. No new metrics, no new rules, no protocol edits.

## 5. Batch 02 agreement audit — mandatory questions

The Batch 02 blind agreement audit must answer, at minimum:

1. **By relation:** CALLS vs IMPORTS formal-verdict agreement, reported separately (not pooled).
2. **By language scope:** C/C++ in-scope vs Python audit-only agreement, reported separately
   (same protocol, different scoring role).
3. **By verification depth:** local-only (L0/L1) vs cross-file (L2+) agreement, reported
   separately.
4. **Decl/Def twins:** on `DECLARATION_DEFINITION_TWIN` cases, Semantic Target Correctness
   agreement vs Canonical Node Correctness agreement, reported separately. Semantic agreement
   exceeding canonical agreement is graph-representation evidence, not annotator error.

## 6. Final report contract (three universes)

1. **Protocol Universe** (269): whether the annotation protocol is executable and repeatable.
2. **C/C++ Fidelity Universe** (174): formal Graph Fidelity metrics — Resolved Precision, False
   Resolution Rate, Selective Risk.
3. **Build-context-sufficient Universe**: subset of (2) excluding `BUILD_CONTEXT_DEPENDENT` and
   `INSUFFICIENT_EVIDENCE` verdicts — the cleanest precision metrics. Excluded cases are never
   dropped; they are reported via a separate **Context-limited rate** (guards against "filter hard
   cases to inflate precision").

### 6.1 Title and claim scope (frozen)

```text
Report title:  C/C++ Structural Relation Fidelity V1
Evaluated:     CALLS, IMPORTS
REFERENCES:    NOT REPRESENTED / NOT EVALUABLE (§7)
```

A bare "C/C++ Graph Fidelity = XX%" headline is not an admissible conclusion.

### 6.2 Mandatory reporting views (SFC-3 guard)

rocksdb CALLS_NONRESOLVED alone carries weight 0.5503 of the C/C++ population; a single
population-weighted number would largely report that one stratum. Every headline metric —
Resolved Precision, False Resolution Rate, and Selective Risk — is therefore reported in three
views, and the overall weighted figure is never the sole or primary conclusion:

```text
1. Population-weighted          → reflects the real graph population
2. Macro by relation/repository → prevents large strata from drowning others
3. Per-stratum                  → true bottleneck localization

breakdowns: overall weighted / CALLS macro / IMPORTS macro
            aria2 / brpc / rocksdb
            resolved / nonresolved
            each stratum
```

`Annotation Protocol Reliability` section of the Fidelity V1 report carries the calibration
results: κ 0.852 raw / 0.923 normalized; relation presence 24/25 → 25/25 under frozen CALLS_V1;
build-context agreement 25/25; IMPORTS and REFERENCES 100%.

## 7. Known Representation Gap — C/C++ REFERENCES (SFC-1 formalized)

SFC-1 is elevated from a sampling-correction remark to a formal research-conclusion boundary.
It is not `RETRIEVAL_MISS` and not sampling bias:

```text
classification: GRAPH_REPRESENTATION_GAP
gap_code:       CXX_REFERENCE_RELATION_NOT_MODELED

mechanism:
  C/C++ parser/extractor
    → emits no REFERENCES RawReference
    → no C/C++ REFERENCES universe exists for Fidelity audit
```

Mandatory formal wording (replaces "C/C++ REFERENCES fidelity 未测"):

> **C/C++ REFERENCES relation is currently not represented by the evaluated extraction
> pipeline; therefore fidelity cannot be estimated for this relation in V1.**

| Relation   | C/C++ population | Gold scoring | Status |
| --- | ---: | ---: | --- |
| CALLS      | 385,287 | 86 sampled | EVALUATED |
| IMPORTS    |  27,005 | 88 sampled | EVALUATED |
| REFERENCES |       0 |  0 | CAPABILITY GAP / NOT EVALUABLE |

Python REFERENCES (population 25,697; 89 sampled cases) stays in the Protocol Universe as
audit-only evidence and never enters C/C++ fidelity scoring. The gap is recorded in the
Evidence Inventory (RQ1 Known Representation Gap) and `milestone-freeze-p0-fidelity-v1.md` —
it is not surfaced for the first time in the final report.

## 8. Standing constraints

- No ProvenLattice development; no early Graph Precision computation. Gold Set first.
- A/B independence for all 244 remaining samples; no single-annotator shortcut despite high
  calibration agreement.
- All frozen rules (CALLS_V1, Evidence Scope V1, Decl/Def Equivalence V1) apply uniformly; no
  per-sample exceptions.
- Sequencing: Batch 03 stays HOLD until Batch 02 Annotator A + Agreement Audit 02 (incl.
  navigation-stratified splits) + Drift Gate PASS. B03 must not start before A02.
- `CXX_REFERENCE_RELATION_NOT_MODELED` repair is deferred: no REFERENCES extractor work during
  Fidelity V1. The documented gap preserves a clean capability addition → qualification evidence
  chain (Before: population = 0 → Implementation → After: population > 0 + independent Gold Set;
  see milestone freeze doc).

## Open owner decisions

- **PLAN-1**: ratify the partition rule (A-view order continuation) or supply an explicit manifest.
- **PLAN-2**: optional supplementary C/C++-only sampling round (frozen-candidate-set exception,
  requires protocol note).

# ProvenLattice V1.0-R2.3 — Agent Revalidation (T01 / T03 / T05 × Native / CodeGraph / Knowledge × r1 / r2 / r3)

Offline report over 27 frozen Agent cells. Raw cells stay local; this report, the manifest,
the aggregates and the pairwise file are versioned. No cell was re-run to replace a result, and
no Parser / Resolver / CrossLayerResolver / Knowledge / Evidence / EvidenceBundle / Structured
Query / Ranking / GroundTruthV2 / EvaluatorV2 / Task Prompt / Arm capability was modified.

## 1. Frozen protocol

| Item | Frozen value |
|---|---|
| Repository | `apache/brpc` @ `ae09e960c7291605dda52356cc0c2d45567fb53e` |
| Harness revision | `a80c79625f39f4809709b1ea8ab88963dd1ad98b` |
| Model | `claude-sonnet-4-5-20250929` |
| Claude Code | `2.1.268` (declared and observed identical in all 27 cells) |
| GroundTruthV2 | sha256 `2bec9208b0d1bb1c3e8509e4420a1e1b6d7ddffe0cb7c2ba57ac1af1559f373e` |
| EvaluatorV2 | `r2.2-groundtruth-v2` |
| Protocol revision | `r2.3` |
| Grid | 3 tasks × 3 arms × 3 repetitions = **27 / 27 VALID** |

Execution followed the frozen order: section-5 gate (54/54 unit tests, `compileall`,
`git diff --check` all clean) → Phase A qualification (9 cells, repetition 1, `9/9 VALID`) →
Phase B stability (18 cells, repetitions 2 and 3, all valid). The 9 qualification cells are
repetition 1 of the final 27 and were not re-executed.

## 2. Final status

| Gate | Status | Basis |
|---|---|---|
| Interface Qualification | **PASS** | 27/27 valid; single brpc SHA, model, Claude version, harness revision, ground-truth hash, evaluator version; arm isolation recomputed clean; zero policy violations; brpc worktree clean before and after every cell |
| CodeGraph Progression | **HOLD** | concept coverage unchanged and exact recall restored to 1.00, but retrieval-path reduction is not directionally consistent (turns MIXED in all three tasks) and returned-but-unused evidence rises consistently (+16 / +18 / +19) |
| Knowledge Progression | **POSITIVE CANDIDATE (task-scoped)** | strong consistent win on T03, positive on T05, neutral-to-negative on T01 |
| T05 × Knowledge | **POSITIVE ZONE CANDIDATE** | 3/3 vs Native 1/3; never worse; 9/9 required-evidence hits; 0 invalid / unsupported / wrong-path; turns and files decrease consistently |

n = 3 per Task × Arm. Only medians, min/max and task-level direction consistency are reported.
No p-value is computed and no statistical significance is claimed.

## 3. Integrity audit (section 19)

All 27 cells share, as singletons:

| Field | Value observed across all 27 cells |
|---|---|
| `agent_actual_commit` | `ae09e960c7291605dda52356cc0c2d45567fb53e` |
| `model_id` / `actual_model_id` | `claude-sonnet-4-5-20250929` |
| `claude_version` / `actual_claude_version` | `2.1.268` |
| `provenlattice_commit` | `a80c79625f39f4809709b1ea8ab88963dd1ad98b` |
| `protocol_revision` | `r2.3` |
| `evaluator_v2_version` | `r2.2-groundtruth-v2` |
| `ground_truth_v2_hash` | matches recomputed sha256 of GroundTruthV2 |
| prompt hashes | exactly 3 distinct values (one per task revision) |
| status / violations / repo state | all `completed`, zero policy violations, brpc clean before and after |

Mechanically recomputed section-10 arm isolation: **Native** cells performed no graph and no
knowledge operation and referenced no Evidence ID; **CodeGraph** cells performed no knowledge
operation and referenced no `E-XLINK-*` cross-layer evidence; **Knowledge** cells were free to use
both. Zero disallowed operations were recorded.

## 4. Task success grid

| Task | Native | CodeGraph | Knowledge |
|---|---|---|---|
| T01 (document → code, Easy) | PASS / PASS / PASS | PASS / PASS / PASS | **FAIL** / PASS / PASS |
| T03 (code → document, Easy) | PASS / PASS / PASS | PASS / **FAIL** / PASS | PASS / PASS / PASS |
| T05 (module understanding, Hard) | PASS / **FAIL** / **FAIL** | **FAIL** / PASS / PASS | PASS / PASS / PASS |
| **Totals** | 7 / 9 | 7 / 9 | **8 / 9** |

Corresponding per-Task × Arm success rates: T01 3/3 / 3/3 / 2/3 · T03 3/3 / 2/3 / 3/3 ·
T05 1/3 / 2/3 / 3/3.

## 5. Correctness (section 20)

| Cell | Success | Concept recall (med) | Exact recall (med) | Precision (med) | Wrong path (Σ) | Invalid evid. (Σ) | Unsupported (Σ) |
|---|---:|---:|---:|---:|---:|---:|---:|
| T01 Native | 3/3 | 1.000 | 0.000 † | — | 0 | 0 | 0 |
| T01 CodeGraph | 3/3 | 1.000 | 1.000 | 1.000 | 0 | 0 | 0 |
| T01 Knowledge | 2/3 | 1.000 | 1.000 | 1.000 | 0 | 1 | 0 |
| T03 Native | 3/3 | 1.000 | 0.000 † | — | 0 | 0 | 0 |
| T03 CodeGraph | 2/3 | 1.000 | 1.000 | 1.000 | 0 | 0 | 1 |
| T03 Knowledge | 3/3 | 1.000 | 1.000 | 1.000 | 0 | 0 | 0 |
| T05 Native | 1/3 | 1.000 | 0.000 † | — | 2 | 0 | 0 |
| T05 CodeGraph | 2/3 | 1.000 | 0.333 | 1.000 | 0 | 1 | 0 |
| T05 Knowledge | 3/3 | 1.000 | 1.000 | 1.000 | 0 | 0 | 0 |

† Native cells receive no Evidence IDs by construction and are graded on the frozen
natural-language evidence contract, so an exact-ID recall of 0.000 is a protocol property of the
Native arm, not a citation defect. Native's correctness signal is Concept Recall and Task Success.

**Concept recall is 1.000 in every one of the 27 cells** — no cell failed on concept coverage.
The four concepts of the failures (see section 8) are all citation- or path-discipline issues.

## 6. Retrieval efficiency (section 21, medians)

| Cell | Tool turns | Read | Grep | Glob | Shell | Graph q. | Knowledge q. | Unique files | File chars | Turn→1st evid. | Duration (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| T01 Native | 11 | 4 | 4 | 1 | 1 | 0 | 0 | 8 | 19,086 | 1 | 18.1 |
| T01 CodeGraph | 15 | 3 | 4 | 0 | 1 | 8 | 0 | 4 | 5,789 | 1 | 26.1 |
| T01 Knowledge | 16 | 4 | 5 | 0 | 0 | 5 | 2 | 5 | 13,054 | 4 | 32.1 |
| T03 Native | 12 | 4 | 6 | 1 | 0 | 0 | 0 | 6 | 15,813 | 12 | 20.0 |
| T03 CodeGraph | 10 | 3 | 2 | 1 | 0 | 3 | 0 | 5 | 6,921 | 1 | 28.0 |
| T03 Knowledge | **3** | **1** | 0 | 0 | 0 | 1 | 1 | **1** | **2,365** | 1 | **14.0** |
| T05 Native | 24 | 6 | 9 | 1 | 1 | 0 | 0 | 9 | 29,275 | — | 35.4 |
| T05 CodeGraph | 29 | 1 | 0 | 0 | 0 | 20 | 0 | 7 | 4,630 | 5 | 59.8 |
| T05 Knowledge | 20 | 1 | 0 | 0 | 0 | 11 | 4 | 6 | 4,630 | 2 | 38.7 |

`turn→1st evid.` is the median turn at which the first relevant evidence appears; "—" means no
relevant hit was detected in the event stream. Token counters were not stably available and are
carried in `aggregate-r2.3.json` for reference only.

## 7. Evidence utility (section 22, medians)

| Cell | Returned | Exposed | Used | GT used | Usage rate | Useful density | Returned-but-unused | Invalid citations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T01 Native | 0 | 0 | 0 | 0 | — | — | 0 | 0 |
| T01 CodeGraph | 20 | 20 | 2 | 1 | 0.100 | 0.500 | 18 | 0 |
| T01 Knowledge | 9 | 9 | 4 | 1 | **1.000** | 0.250 | 0 | 0 |
| T03 Native | 0 | 0 | 0 | 0 | — | — | 0 | 0 |
| T03 CodeGraph | 18 | 18 | 3 | 1 | 0.111 | 0.667 | 16 | 0 |
| T03 Knowledge | **6** | **6** | **6** | 1 | **1.000** | 0.333 | **0** | 0 |
| T05 Native | 0 | 0 | 0 | 0 | — | — | 0 | 0 |
| T05 CodeGraph | 38 | 38 | 16 | 1 | 0.333 | 0.062 | 19 | 0 |
| T05 Knowledge | 39 | 39 | 20 | **3** | 0.513 | 0.200 | 19 | 0 |

`GT used` is the number of ground-truth required Evidence IDs actually cited. Invalid citations
are zero in every median; the three cells that produced invalid/unknown citations are enumerated
in section 8.

## 8. Failure attribution (sections 13 and 20)

Five of 27 cells are non-success. None of them failed on concept coverage.

| Cell | Trigger | Attribution |
|---|---|---|
| `T01.knowledge.r1` | cited `E-CODE-9CEC5B84FB52B556C0C332C9`, classified `INVALID_EVIDENCE` | `INVALID_EVIDENCE` — the Knowledge bundle exposed an item that GroundTruthV2 declares **invalid for T01**, and the agent cited it. The bundle returned 10 items and the agent used all 10, so this is bundle-precision / distractor exposure, not a citation hallucination. |
| `T05.codegraph.r1` | cited `E-CODE-C2F8A2E93CB05E73B643FBBE`, classified `INVALID_EVIDENCE` | `INVALID_EVIDENCE` (agent-side) — a known evidence ID that this bundle never returned; the agent cited evidence it was not given. |
| `T03.codegraph.r2` | cited `E-CODE-9CEC`, classified `UNKNOWN_EVIDENCE` | `UNKNOWN_EVIDENCE` — a truncated Evidence ID. Exact recall was still 1.00; the failure is pure citation hygiene. |
| `T05.native.r2`, `T05.native.r3` | `wrong_path_count = 1`, path `src/brpc/*.cpp` | `PATH_PRECISION` — a wildcard path phrase flagged by the EvaluatorV2 path regex because no such file exists. Concept recall 1.00, no unmet concept. |

Notable structural finding: `E-CODE-9CEC5B84FB52B556C0C332C9` is the **required** evidence of T03
and simultaneously the **declared invalid distractor** of T01. The same bundle item is therefore
correct on one task and a task-failing citation on the other. Both failures above (`T01.knowledge.r1`
and `T03.codegraph.r2`) touch that single ID.

Aggregate attribution counts over 27 cells:

| Class | Count |
|---|---:|
| TRUE_CAPABILITY_SUCCESS | 22 |
| TRUE_CAPABILITY_FAILURE | **0** |
| INVALID_EVIDENCE (citation contract) | 2 |
| UNKNOWN_EVIDENCE (citation contract) | 1 |
| PATH_PRECISION (measurement-sensitive) | 2 |
| EVALUATOR_FALSE_NEGATIVE (reclassified offline) | 0 |

The two `PATH_PRECISION` cells are reported as a measurement-contract observation, not
reclassified: `src/brpc/*.cpp` is genuinely not a specific file, and adjudicating whether a glob
phrase should count as a wrong path is an EvaluatorV2 question that this round is frozen from
changing (section 16). It is registered as the first measurement item for a later round.

## 9. Pairwise comparison (section 24)

Deltas are `treatment − reference`; direction is computed over the three repetitions.

### CodeGraph − Native

| Task | Δ success | Δ concept recall | Δ turns | Δ files | Δ graph q. | Δ returned-unused | Δ wrong path |
|---|---|---|---|---|---|---|---|
| T01 | 0 / 0 / 0 (NO_CHANGE) | 0.000 (NO_CHANGE) | +1 (MIXED) | −4 (MIXED) | **+8 (INCREASE_CONSISTENT)** | **+18 (INCREASE_CONSISTENT)** | 0 (NO_CHANGE) |
| T03 | 0 / −1 / 0 (MIXED) | 0.000 (NO_CHANGE) | −2 (MIXED) | +1 (MIXED) | **+3 (INCREASE_CONSISTENT)** | **+16 (INCREASE_CONSISTENT)** | 0 (NO_CHANGE) |
| T05 | −1 / +1 / +1 (MIXED) | 0.000 (NO_CHANGE) | 0 (MIXED) | **−2 (DECREASE_CONSISTENT)** | **+20 (INCREASE_CONSISTENT)** | **+19 (INCREASE_CONSISTENT)** | −1 (MIXED) |

### Knowledge − Native

| Task | Δ success | Δ concept recall | Δ turns | Δ files | Δ knowledge q. | Δ returned-unused | Δ wrong path |
|---|---|---|---|---|---|---|---|
| T01 | −1 / 0 / 0 (MIXED) | 0.000 (NO_CHANGE) | +3 (INCREASE_CONSISTENT) | −5 (MIXED) | +2 (INCREASE_CONSISTENT) | 0 (MIXED) | 0 (NO_CHANGE) |
| T03 | 0 / 0 / 0 (NO_CHANGE) | 0.000 (NO_CHANGE) | **−9 (DECREASE_CONSISTENT)** | **−5 (DECREASE_CONSISTENT)** | +1 (INCREASE_CONSISTENT) | 0 (NO_CHANGE) | 0 (NO_CHANGE) |
| T05 | 0 / +1 / +1 (MIXED) | 0.000 (NO_CHANGE) | **−4 (DECREASE_CONSISTENT)** | **−3 (DECREASE_CONSISTENT)** | +4 (INCREASE_CONSISTENT) | **+19 (INCREASE_CONSISTENT)** | −1 (MIXED) |

### Knowledge − CodeGraph

| Task | Δ success | Δ concept recall | Δ precision | Δ turns | Δ files | Δ unused | Δ useful density | Δ knowledge q. |
|---|---|---|---|---|---|---|---|---|
| T01 | −1 / 0 / 0 (MIXED) | 0.000 | 0.000 (MIXED) | +2 (INCREASE_CONSISTENT) | 0 (MIXED) | **−15 (DECREASE_CONSISTENT)** | **−0.250 (DECREASE_CONSISTENT)** | +2 (INCREASE_CONSISTENT) |
| T03 | 0 / +1 / 0 (MIXED) | 0.000 | 0.000 (MIXED) | **−7 (DECREASE_CONSISTENT)** | **−4 (DECREASE_CONSISTENT)** | **−16 (DECREASE_CONSISTENT)** | **−0.333 (DECREASE_CONSISTENT)** | +1 (INCREASE_CONSISTENT) |
| T05 | +1 / 0 / 0 (MIXED) | 0.000 | 0.000 (MIXED) | −2 (MIXED) | 0 (MIXED) | −2 (MIXED) | **+0.079 (INCREASE_CONSISTENT)** | +4 (INCREASE_CONSISTENT) |

Reading of the three comparisons:

- **CodeGraph versus Native.** Concept coverage is unchanged everywhere, and CodeGraph is the only
  non-Native arm that restores exact-ID recall to 1.00 on T01/T03 (Native is exact-ID-free by
  design). But the retrieval-path claim does not hold consistently: turn deltas are MIXED in all
  three tasks, file reads fall consistently only on T05, and CodeGraph always adds a graph-query
  stream (+8 / +3 / +20) together with a consistently larger unused-evidence surplus (+16…+20).
  It also loses one success on T03 through a truncated citation.
- **Knowledge versus Native.** Never worse on success, strictly better in 2/3 on T05, and cheaper on
  T03 (−9 turns, −5 files) and T05 (−4 turns, −3 files), both direction-consistent. On T01 it is
  more expensive (+3 turns) and loses one success.
- **Knowledge versus CodeGraph.** This is the decisive comparison for "does Knowledge add anything
  beyond the graph". On **T03 it clearly does**: success 3/3 vs 2/3, turns −7, files −4, graph
  queries −2 and unused evidence −16, all direction-consistent, with a 6-returned / 6-used bundle in
  every repetition. On **T05 the gain is partial**: success 3/3 vs 2/3 and a consistently higher
  useful-evidence density (+0.079), but turns are MIXED. On **T01 there is no gain**: one success
  lost, turns +2 and useful density consistently worse (−0.250) — the Knowledge bundle returns fewer
  unused items but cites proportionally more non-ground-truth evidence.
  Honest trade-off: where Knowledge wins on cost it is also less citation-dense (T03 useful density
  −0.333, consistent) — it cites more items per accepted item than CodeGraph does. This is a citation
  style difference, not a success regression, but it must not be presented as a pure improvement.

## 10. Answers to the six R2.3 questions

**1. Do T01/T03 still exhibit a real capability failure under GroundTruthV2?**
No. Concept recall is 1.000 in all 27 cells and TRUE_CAPABILITY_FAILURE = 0. Every residual failure
is a citation- or path-discipline event: two invalid citations, one truncated Evidence ID, two
wildcard path claims. The R2.2 evaluator false negatives on T01/T03 are not reproduced in this
round: T01 CodeGraph is 3/3 and T03 Native is 3/3.

**2. Does CodeGraph stably reduce retrieval paths without reducing correctness?**
Not stably. Correctness in concept terms is unchanged (Δ concept recall = 0.000 with NO_CHANGE in all
three tasks) and precision is 1.000 where it is applicable, but the path reduction is not
direction-consistent (turns MIXED everywhere) and every task pays a consistent unused-evidence
surplus. Verdict: **HOLD**.

**3. Does T05 advance from Positive Signal to a stable Positive Zone Candidate?**
Yes, for the Knowledge arm. T05 × Knowledge is 3/3 against Native 1/3, is never worse across
repetitions, cites 9/9 required evidence items, records zero invalid / unsupported / wrong-path
findings, and reduces turns (−4) and file reads (−3) with consistent direction. T05 × CodeGraph is
2/3 with MIXED turns and is explicitly not promoted. Label: **POSITIVE ZONE CANDIDATE**, not frozen,
n = 3.

**4. Does Knowledge provide additional stable benefit over pure CodeGraph?**
Task-dependent, and it is the sharpest result of this round. Yes on T03 (all cost axes
direction-consistent, plus one extra success and a perfect 6/6 bundle). Partially on T05 (one extra
success, higher useful density). No on T01 (costlier, lower citation density, one success lost).

**5. Is the current Knowledge bottleneck still Evidence Usage / Citation, or has it become a
Capability problem?**
It is Evidence Usage / Citation, and it is no longer a Capability problem. Capability is saturated:
concept recall is 1.000 everywhere and no cell failed on concept coverage. What remains is (a)
citation discipline — three cells cited an invalid or unknown Evidence ID, one of them a truncated
ID — and (b) bundle precision — CodeGraph returns 18–38 items to have 2–16 used (usage rate
0.100 / 0.111 / 0.333) and T05 Knowledge returns 39 to have 20 used (0.513). The single best-shaped
cell in the whole grid is T03 × Knowledge: 3 turns, 1 read, 6 returned, 6 used, 3/3 success.

**6. Should the next round optimise Query, Knowledge, or open a new Evidence Layer?**
The evidence points at **Query / bundle precision (evidence selection)**, not at Knowledge expansion
and not at a new Evidence Layer. Recall-side headroom is exhausted on these tasks, every remaining
failure is a selection or citation error rather than a missing evidence kind, and the only
consistently negative axis across arms is the returned-but-unused surplus. A new Evidence Layer has
no failure in this round that would justify it. Recommended single next variable: bundle precision
(retrieval target size / ranking of `--max-evidence` bundles) measured against the T03 × Knowledge
shape, with a citation-contract guardrail as a separate, later item.

## 11. Observations registered, not fixed (section 16)

1. **EvaluatorV2 path-regex sensitivity.** A prose wildcard such as `src/brpc/*.cpp` is flagged as a
   wrong path. It caused 2 of the 5 non-success cells. Not adjudicated this round.
2. **Distractor exposure by the Knowledge bundle on T01.** The bundle returned the T01-declared
   invalid item, and the agent cited it. Whether a bundle should expose task-invalid distractors is a
   Query-design question, not an evaluator question.
3. **Native is exact-ID-free by construction**, so Δ exact recall between Native and non-Native arms
   is a protocol property rather than an improvement claim. All Native comparisons in this report are
   made on concept recall, success, and cost.
4. **Token counters were not stably available** across cells; they are carried as auxiliary values
   only and are not used for any verdict.

## 12. Reproducibility artifacts

- [manifest-r2.3.json](../../experiments/retrieval-v2/r2_3/results/manifest-r2.3.json) — per-cell provenance, artifact SHA256, consistency and arm-isolation audit
- [aggregate-r2.3.json](../../experiments/retrieval-v2/r2_3/results/aggregate-r2.3.json) — correctness / efficiency / evidence-utility aggregates
- [pairwise-r2.3.json](../../experiments/retrieval-v2/r2_3/results/pairwise-r2.3.json) — pairwise deltas and direction consistency
- [qualification-summary.json](../../experiments/retrieval-v2/r2_3/results/qualification-summary.json)
- [stability-summary.json](../../experiments/retrieval-v2/r2_3/results/stability-summary.json)
- [failure-attribution-r2.3.md](../../experiments/retrieval-v2/r2_3/failure-attribution-r2.3.md)
- [protocol-deviations.md](../../experiments/retrieval-v2/r2_3/protocol-deviations.md)
- [summarize_r2_3.py](../../experiments/retrieval-v2/r2_3/summarize_r2_3.py) — offline audit / aggregation tool (no Agent calls)

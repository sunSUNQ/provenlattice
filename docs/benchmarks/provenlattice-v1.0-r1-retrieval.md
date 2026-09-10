# ProvenLattice V1.0-R1 Retrieval Qualification

Status: **R1 COMPLETE**

Qualification: **PASS**

Qualification runs: **18 / 18**

Final audited dataset: **54 / 54**

## Frozen execution baseline

| Item | Frozen value |
| --- | --- |
| ProvenLattice Harness | `ba4f87b29e616dd28d1aa4939dbc805dbb296cb4` |
| Original Harness tag | `provenlattice-v1.0-r1-harness` at `f323622` |
| Infrastructure fix tag | `provenlattice-v1.0-r1-harness-fix1` |
| brpc | `ae09e960c7291605dda52356cc0c2d45567fb53e` |
| Claude Code | `2.1.267` |
| Model | `claude-sonnet-4-5-20250929` |
| Matrix | 6 tasks × 3 arms × 3 repetitions |

The original frozen Adapter could not transport a Claude prompt or address repetitions on
Windows. Before any valid run existed, the single permitted infrastructure repair corrected
prompt transport, UTF-8 stream decoding, Windows launcher resolution, repetition identity,
resume/quarantine, and audit/report plumbing. Tasks, prompts, Ground Truth, Arm capabilities,
metric meaning, evaluator semantics, Core, Resolver, and Knowledge Layer did not change.

## Qualification result

All eight required gates passed: Prompt Identity, Native Isolation, CodeGraph Isolation,
Knowledge Capability, Event/Metrics Consistency, evaluator repeatability, failure-artifact
completeness, and Run auditability. Native made zero Graph and Knowledge calls; CodeGraph made
zero Knowledge calls. No valid run modified brpc and every valid run completed on its first
attempt.

Qualification PASS means the dataset is internally auditable; it does not mean that
ProvenLattice outperformed Native.

## Critical interpretation limit

The frozen evaluator produced `task_success=false` for all 54 runs while evidence precision
was `1.0` for all 54. The cause is the frozen `wrong_path` rule: any supporting path mentioned
outside each task's narrow `expected_files`/`expected_documents` list is counted as wrong,
including legitimate related implementation files. Consequently, Task Success is saturated
at zero and cannot discriminate the Arms. This report does not change or retroactively repair
that evaluator; it uses evidence recall and paired retrieval metrics as secondary observations.

`time_to_first_relevant_evidence_ms` is absent in all 54 runs, and exact returned/used
Cross-Layer evidence IDs were not captured. Latency-to-first-evidence and the utilization of
the 80 trusted Cross-Layer Edges therefore remain unqualified.

## Per-task medians

Each cell below is `evidence recall / tool turns / unique files / duration` over r1–r3.

| Task | Type | Native | CodeGraph | Knowledge | Result zone |
| --- | --- | --- | --- | --- | --- |
| T01 | Document → Code | `0.67 / 7 / 3 / 12.8s` | `0.67 / 13 / 4 / 26.7s` | `0.67 / 13 / 4 / 23.2s` | Neutral correctness; negative efficiency |
| T02 | Document → Code | `0.67 / 7 / 6 / 13.9s` | `0.67 / 9 / 4 / 17.6s` | `0.67 / 11 / 4 / 24.5s` | Neutral; fewer files but more turns/time |
| T03 | Code → Document | `1.00 / 10 / 3 / 18.7s` | `1.00 / 16 / 6 / 29.2s` | `1.00 / 15 / 6 / 29.6s` | Neutral correctness; negative efficiency |
| T04 | Code → Document | `1.00 / 8 / 4 / 13.7s` | `1.00 / 12 / 4 / 20.1s` | `1.00 / 12 / 4 / 20.5s` | Neutral correctness; negative efficiency |
| T05 | Module understanding | `1.00 / 29 / 11 / 37.0s` | `0.50 / 20 / 7 / 31.2s` | `0.50 / 30 / 8 / 38.5s` | Negative correctness; CodeGraph search path shorter |
| T06 | Module understanding | `0.50 / 26 / 10 / 35.9s` | `0.50 / 24 / 9 / 37.9s` | `0.50 / 30 / 12 / 39.8s` | Mixed / neutral |

The paired per-repetition deltas remain authoritative in `pairwise-deltas.json`. Notable
paired medians are:

- T05 CodeGraph vs Native: 11 fewer turns, 10 fewer reads, 4 fewer files, and 5.8s less time,
  but one of three CodeGraph repetitions lost evidence recall.
- T05 Knowledge vs Native: recall delta `-0.5`, 8 fewer reads, 3 fewer files, but 2.4s more time.
- T06 CodeGraph vs Native: 3 fewer turns and 5 fewer reads, but one more file and 3.0s more time.
- T06 Knowledge vs Native: 4 fewer turns and 8 fewer reads, but one more file; the paired
  duration median was 3.6s lower.

## Graph and Knowledge use

| Observation | Result |
| --- | ---: |
| CodeGraph runs issuing at least one Graph query | 18 / 18 |
| Knowledge runs issuing at least one Graph query | 15 / 18 |
| Knowledge runs issuing at least one Knowledge query | 9 / 18 |
| CodeGraph Graph queries | 42 |
| Knowledge Graph queries | 34 |
| Knowledge evidence/requirements queries | 11 |
| Native Graph or Knowledge queries | 0 |
| CodeGraph Knowledge queries | 0 |
| Runs with auditable Cross-Layer utilization | 0 / 54 |

Knowledge use was voluntary as required. T01 never used a Knowledge query; T02 and T05 used
one in two repetitions; T03 and T04 used one in one repetition; T06 used Knowledge in all
three repetitions. Several runs retried broad symbol queries or formed malformed paths/CLI
arguments before falling back to native reading. These are Agent Tool Selection and Query
Interface observations, not infrastructure retries.

## Answers to the R1 questions

### Q1 — Does CodeGraph improve evidence-location correctness?

Not demonstrated. Median evidence recall was equal on T01–T04 and T06. T05 showed one
CodeGraph recall regression; Task Success cannot discriminate Arms because of the frozen
wrong-path rule. There was no wrong-evidence precision regression (`1.0` throughout), but the
data does not support a correctness improvement claim.

### Q2 — Does it reduce search and file-reading paths?

Only in specific module-understanding cells. T05 CodeGraph substantially reduced turns,
reads, files, and duration. T02 reduced unique files but increased turns and time. T01, T03,
and T04 generally required more turns and time than Native. This is task-dependent rather
than a general reduction.

### Q3 — Does it reach the first valid evidence faster?

Unqualified. All 54 `time_to_first_relevant_evidence_ms` values are null because elapsed
timestamps were not attached to semantic evidence events.

### Q4 — Does Knowledge add value beyond CodeGraph?

No repeatable additional value was demonstrated. Knowledge had no consistent recall gain and
usually added turns or time. It did save some reads in T03/T04, but the pattern was not stable
across tasks. Only 9/18 Knowledge runs voluntarily used a Knowledge command.

### Q5 — Which task types are in the Positive Zone?

None satisfies the frozen Positive definition across correctness and multiple retrieval
metrics. T05 CodeGraph is an efficiency-positive candidate, but its recall was not stable.

### Q6 — Which tasks are neutral or negative?

T01–T04 are correctness-neutral with mostly negative efficiency. T06 is mixed/neutral. T05 is
negative for Knowledge correctness and unstable for CodeGraph correctness despite a shorter
CodeGraph exploration path.

### Q7 — Coverage, Resolver, Query Interface, or Agent Usage?

The strongest observable issues are Query Interface and Agent Tool Selection: repeated broad
symbol queries, malformed CLI/path attempts, and Knowledge capability unused in half of its
runs. Coverage and Resolver may contribute, but this dataset did not retain enough structured
query-return evidence to separate them reliably. They should not be changed based on this run.

### Q8 — Were the 80 trusted Cross-Layer Edges actually used?

Not auditable. Seven `evidence` and four `requirements` commands were observed, but returned
and used edge IDs were not serialized into events. Cross-Layer utilization is null in every
run, so actual use of the 80 edges is not proven.

### Q9 — What should be developed next?

Prioritize a stable structured Query Interface and evidence instrumentation before expanding
Knowledge Coverage, changing Resolver behavior, or entering History Evidence. The next
qualification harness should expose machine-readable query results with evidence IDs,
capture time-to-first-relevant-evidence, and preflight CLI argument/path correctness. The
strict wrong-path evaluator contract also needs a separately versioned correction before a
new comparative run. Do not reinterpret or overwrite this R1 dataset.

## Artifacts

- `experiments/retrieval-v1/results/manifest.json` — 54 run keys and artifact hashes
- `experiments/retrieval-v1/results/qualification.json` — 18-cell gate result
- `experiments/retrieval-v1/results/aggregate.json` and `.csv` — all repetitions and summaries
- `experiments/retrieval-v1/results/pairwise-deltas.json` — paired task-level deltas
- `experiments/retrieval-v1/results/failure-attribution.md` — observational attribution
- `experiments/retrieval-v1/results/execution-log.ndjson` — execution order and lifecycle

Raw per-run artifacts occupy approximately 39.8 MiB and remain local. The manifest records
their relative paths and SHA-256 hashes; they are intentionally excluded from Git.

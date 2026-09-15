# Annotator A — batch_02 Execution Note

Read this note fully before opening any case. It is the execution contract for Annotator A's
Batch 02 annotation. Work from a fresh session that has not read any other annotator's records.

## Identity and scope

```text
annotator_id: A
batch: batch_02 (60 cases; worksheet order = blinded-view positions 26-85, contiguous)
protocol_commit: 12f405c677582a2982d035433bf6837126772716
```

## Read-only inputs (whitelist)

Only these files may be opened:

```text
provenlattice/experiments/fidelity_v1/results/annotator-a-batch-02-worksheet.md
provenlattice/experiments/fidelity_v1/results/annotator-a-batch-02-worksheet.json
provenlattice/experiments/fidelity_v1/README.md
provenlattice/experiments/fidelity_v1/results/full-annotation-execution-plan-v1.md
provenlattice/experiments/fidelity_v1/results/protocol-addendum-calls-v1-macro-semantics.md
provenlattice/experiments/fidelity_v1/results/protocol-addendum-evidence-scope-v1.md
provenlattice/experiments/fidelity_v1/results/protocol-addendum-decl-def-equivalence-v1.md
```

Do NOT open anything else under `results/` — in particular: the other annotator's files
(`annotator-b-*`), any audit / agreement / gate / milestone artifact, `pilot-candidates.json`
(contains system status), and the execution plan JSON's `execution_state`. If you notice a
forbidden file has been opened, stop and record it as a `protocol_issue` instead of continuing.

## Environment check (before case 1)

```text
- verify the frozen commits of aria2 / brpc / rocksdb against
  benchmark-analysis/v0.2-{aria2,brpc,rocksdb}.json and git rev-parse HEAD in each repo
- all three working trees must be clean
- record the verified SHAs and the check result in the execution metadata
```

## Blindness (hard rules)

```text
- no system status, resolver strategy, confidence, or system selected target
- no stratum membership for any case
- no other annotator's records or audit products
- graph database lookups are limited to candidate symbol definition recovery:
  read-only, never query status / resolved_symbol_id / strategy / confidence fields
- no network retrieval of source facts
- no repository mutation
```

## Evidence rules (Evidence Scope V1, FROZEN)

- From the sample's source location, navigate read-only inside the same frozen commit.
- Declaration/definition lookup, type/owner/namespace/include tracing, and local type
  propagation are admissible.
- A unique target determinable under this scope must NOT be judged `INSUFFICIENT_EVIDENCE`.
- `INSUFFICIENT_EVIDENCE` only when undeterminable under the full scope.
- `EVIDENCE_SCOPE_TOO_NARROW` is never a verdict.
- Record every file read beyond the sample's own file in `navigation_files`, and the deciding
  `path:line` anchors in `evidence_locations`.

## Verdict and record obligations (per case)

```text
gold_relation_exists      true | false
formal_verdict            blind world-fact space (stratum join post-hoc):
                          ONE_VALID_TARGET | NO_VALID_TARGET | MULTIPLE_VALID_TARGETS |
                          RELATION_NOT_PRESENT | BUILD_CONTEXT_DEPENDENT |
                          INSUFFICIENT_EVIDENCE
valid_target_count        0 | 1 | 2 | ... | INDETERMINATE
selected_target_if_unique {symbol_id, path, start_line} when applicable
build_context_status      SOURCE_SUFFICIENT | BUILD_CONTEXT_DEPENDENT (+reason)
difficulty_tags           frozen vocabulary only (worksheet header lists it)
confidence                HIGH | MEDIUM | LOW
protocol_issue            null | {id, description}
```

Decl/Def Equivalence V1 is in force: record the target your source evidence establishes;
equivalence groups are joined at scoring time — do not speculate about them.

## Outputs

- `results/annotator-a-batch-02.md` — readable record: execution metadata block
  (annotator_id, model/runtime, start/end times, verified repo SHAs, blindness declaration,
  case count), verdict summary table, then one row/block per case.
- `results/annotator-a-batch-02.json` — the worksheet scaffold with every annotation field
  filled and `status = COMPLETED`, same 60-case order, same case_ids.

## Sanity checks before closing

```text
- 60/60 cases, order preserved, no case skipped or duplicated
- no verdict outside the frozen vocabulary
- every case has build_context_status and confidence
- navigation_files / evidence_locations present for every cross-file determination
- protocol_issue used for anything anomalous (including accidental forbidden reads)
```

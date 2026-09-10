# V1.0-R1 Retrieval Qualification Harness

This experiment is standalone and does not depend on TASCO or MCP.

## Fixed matrix

The frozen task set contains six real `apache/brpc` tasks at commit `ae09e960c7291605dda52356cc0c2d45567fb53e`:

```text
6 tasks × 3 arms × 1 first-pass repetition = 18 cells
```

Arms are `native`, `codegraph`, and `knowledge`. The task prompt, repository, commit, model and runtime configuration must stay identical; only the allowed retrieval operations vary.

## Run one cell

Generic adapter commands receive a JSON `RunRequest` on stdin. Claude Code receives the
frozen task prompt as text while the complete request remains available in
`PL_R1_RUN_REQUEST`. Tool events are parsed from Claude `stream-json`; remaining output is
treated as the final answer.

```bash
python -m experiments.retrieval-v1.harness.runner \
  experiments/retrieval-v1/tasks/T01.json \
  --repo /path/to/brpc \
  --arm knowledge \
  --agent-command "your-agent-command" \
  --model-id claude-sonnet-4-5-20250929 \
  --claude-version 2.1.267 \
  --provenlattice-commit HARNESS_COMMIT \
  --database /path/to/brpc-knowledge.db \
  --results experiments/retrieval-v1/results
```

The agent must operate read-only. The runner rejects write operations, disallowed arm operations, and destructive shell commands. Use a disposable checkout when the external agent cannot guarantee read-only behavior.

## Run the matrix

```bash
python -m experiments.retrieval-v1.run_matrix \
  --repo /path/to/brpc \
  --agent-command "your-agent-command" \
  --repetitions 1
```

The autonomous matrix runner stages `T01.native.r1`, the remaining T01 arms, and the
remaining r1 cells. It enters r2/r3 only after all eight qualification gates pass. Valid
runs are resumed without overwrite; corrupt runs are quarantined.

## Qualification report

```bash
python -m experiments.retrieval-v1.harness.qualify \
  --output-json docs/benchmarks/provenlattice-v1.0-r1-retrieval.json \
  --output-md docs/benchmarks/provenlattice-v1.0-r1-retrieval.md
```

Every cell writes `run.json`, `events.ndjson`, `agent-output.txt`, `metrics.json`, and `evaluation.json`. The evaluator is deterministic and reports correctness, retrieval efficiency, and graph utility; no result is interpreted until the gates pass.

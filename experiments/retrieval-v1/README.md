# V1.0-R1 Retrieval Qualification Harness

This experiment is standalone and does not depend on TASCO or MCP.

## Fixed matrix

The frozen task set contains six real `apache/brpc` tasks at commit `ae09e960c7291605dda52356cc0c2d45567fb53e`:

```text
6 tasks × 3 arms × 1 first-pass repetition = 18 cells
```

Arms are `native`, `codegraph`, and `knowledge`. The task prompt, repository, commit, model and runtime configuration must stay identical; only the allowed retrieval operations vary.

## Run one cell

The adapter command receives a JSON `RunRequest` on stdin. It may emit tool events as NDJSON lines with `event_type: "tool"`; remaining stdout is treated as the final answer.

```bash
python -m experiments.retrieval-v1.harness.runner \
  experiments/retrieval-v1/tasks/T01.json \
  --repo /path/to/brpc \
  --arm knowledge \
  --agent-command "your-agent-command" \
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

Use `--repetitions 3` only after the first 18 cells pass qualification.

## Qualification report

```bash
python -m experiments.retrieval-v1.harness.qualify \
  --output-json docs/benchmarks/provenlattice-v1.0-r1-retrieval.json \
  --output-md docs/benchmarks/provenlattice-v1.0-r1-retrieval.md
```

Every cell writes `run.json`, `events.ndjson`, `agent-output.txt`, `metrics.json`, and `evaluation.json`. The evaluator is deterministic and reports correctness, retrieval efficiency, and graph utility; no result is interpreted until the gates pass.

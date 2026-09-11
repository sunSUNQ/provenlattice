# R2.3 protocol deviations and execution notes

Frozen harness revision `a80c79625f39f4809709b1ea8ab88963dd1ad98b` was **not** modified. No file
under `src/`, no task JSON, no GroundTruthV2 entry, no EvaluatorV2 module and no arm capability was
edited at any point, before or during the run. Because no harness fix was needed, the section-17
"infrastructure fix" procedure (regression test + separate commit + revision record) was not
triggered; the 54-test suite was nevertheless re-run after all additive tooling was written.

## 1. Attempt 1 of qualification failed on a dead transport (section 12 recovery)

| Field | Value |
|---|---|
| Cell | `T01.native.r1`, phase `qualification`, attempt 1 |
| Observed | `agent-output.txt` = `Not logged in - Please run /login`; `exit_reason = agent_nonzero_exit`; `tool_calls = 0`; `duration_ms = 1109` |
| Effect on the cell | `RUN_STATUS:failed` -> cell INVALID; harness exited 2 and did **not** enter stability |
| Classification | Recoverable infrastructure fault, frozen protocol section 12: "Claude process failed before task execution" |
| Root cause | `ANTHROPIC_AUTH_TOKEN` was absent from the execution environment, so the Claude Code CLI was unauthenticated. A bare `claude -p` also returned `Not logged in`, confirming the CLI had no usable credential at all. |
| Remediation | Restored the transport credential from the project `.env` already present in this workspace. `ANTHROPIC_BASE_URL` (`https://api.deepseek.com/anthropic`) was already injected by the environment and was left untouched. |
| Semantics impact | None. Endpoint, frozen model ID, Claude Code version, task prompts, GroundTruthV2, EvaluatorV2 and arm capabilities are all unchanged; `actual_model_id` and `actual_claude_version` recorded in every cell prove the frozen model and CLI were the ones served. |
| Artifact preservation | The failed cell was **moved, not deleted**, to `experiments/retrieval-v2/r2_3/results/_invalid/T01-native-r1-attempt1-not-logged-in-20260911/` with all six artifacts plus `failure-reason.json`. |
| Retry | One retry (attempt 2) after the transport was restored and verified by a throwaway model round trip. No further qualification cell failed. |

Records of the attempt are append-only: the original `run.json`, `events.ndjson`, `metrics.json`,
`evaluation.json`, `evaluation-v2.json` and `agent-output.txt` are intact in the archive directory.
The archive is a raw local artifact and is intentionally not committed, consistent with the
repository rule that raw Agent cells stay local.

## 2. Additive offline tooling (no Agent calls, no scoring change)

`experiments/retrieval-v2/r2_3/summarize_r2_3.py` was added **after** the harness was frozen. It
only reads the 27 frozen cells and emits `manifest-r2.3.json`, `aggregate-r2.3.json` and
`pairwise-r2.3.json`. It never calls an Agent, never re-runs a cell, never re-scores an answer and
never rewrites a raw cell; it re-reads the frozen `evaluation-v2.json` verbatim. This mirrors the
R2.1 precedent (`summarize_r2_1.py` + `close_r2_1.py`).

One recomputation is deliberately independent of the harness: the section-10 arm-isolation gate is
re-derived from the raw `events.ndjson` of every cell (allowed-operation subset per arm, no
cross-layer evidence in CodeGraph, no Evidence IDs at all in Native) instead of being taken from the
harness verdict. It passes for all 27 cells.

## 3. External execution driver

Execution was orchestrated by a PowerShell driver living **outside** the repository (in the agent
session workspace, not in this git tree). It invoked the frozen commands in the frozen order,
refused to enter stability unless qualification returned 9/9 valid, and aborted on any non-zero
harness exit. It contains no experimental logic: arm prompts, task order, arm order, model,
timeout and evaluation all come from the frozen harness.

## 4. Registered observations (not fixed this round)

1. EvaluatorV2's path regex extracts prose wildcards such as `src/brpc/*.cpp` and classifies them as
   wrong paths. This produced 2 of the 5 non-success cells. Adjudicating it is a measurement-contract
   change and is outside this frozen round.
2. The T01 Knowledge bundle exposed the evidence item that GroundTruthV2 declares invalid for T01,
   and the agent cited it.
3. The Native arm receives no Evidence IDs by construction, so exact-ID recall deltas between Native
   and non-Native arms are a protocol property, not an improvement claim.
4. Token counters were not stably available in every cell and are carried as auxiliary values only.

## 5. Frozen revision history

| Item | Revision |
|---|---|
| Harness at freeze (section 4 preflight) | `a80c79625f39f4809709b1ea8ab88963dd1ad98b` |
| Harness during and after the run | `a80c79625f39f4809709b1ea8ab88963dd1ad98b` (unchanged) |
| brpc | `ae09e960c7291605dda52356cc0c2d45567fb53e` (unchanged, clean before and after every cell) |

Because the revision never changed, all 27 cells share one harness revision and no
mixed-revision question arises.

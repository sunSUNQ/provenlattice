# SQI-V1 Stage 3A Secondary Freeze Review — PASS

Freeze date: 2026-09-17

## Scope

Stage 3A (`SQI CLI Bridge + Evaluator Expansion + Secondary Seal`) is complete.
No formal cell has been executed; `results/formal/` remains empty and the
formal verdict is still `null`.

## 1. CLI Bridge — implemented and agent-invocable

`tools/sqi_cli.py` is the only SQI path available to a formal-session agent:

- exposes exactly the six canonical calls (`--call`), each with a frozen param
  key set; illegal params or unknown calls are rejected with structured errors
  and exit code 2;
- two frozen parameter forms: `--params '<json>'` and the shell-safe
  `--arg key=value` repeatable form (`budget=max_evidence,max_symbols,`
  `max_edges,max_sections`; `changed_shard_paths` comma-separated; `threshold`
  int) — the `--arg` form avoids Windows inline-JSON quoting entirely and is
  the form taught in the arm prompt;
- prints **exactly one JSON envelope** to stdout — the adapter's self-validated
  response — so the retrieval harness's structured-result extraction and the
  evaluator's citation-closure oracle see the same bytes the agent saw;
- appends one ndjson line per invocation to the session call log
  (`PL_SQI_CALL_LOG` / `--call-log`): call, params, response bytes, full
  envelope — evaluator-side first-hand evidence;
- no context smuggling, no budget bypass: budgets are declared by the agent
  and clamped inside the sealed adapter.

Agent-invocability is verified the way the formal session will run it: invoked
with the session cwd set to a benchmark repo (not the provenlattice checkout)
with the session `PYTHONPATH`, using the `--arg` form; plus integration tests
that run the bridge as a real subprocess through the real CLI path and assert
envelope validity, single-object stdout, deterministic repeat, log writing,
and budget enforcement.

Session-environment wiring: the formal runner injects the provenlattice
checkout (`src` + repo root) into the session `PYTHONPATH` so the frozen
`python -m experiments...` bridge command resolves from the agent's repo cwd;
both arms receive the same environment (native arm simply has no SQI tool and
no call log).

## 2. Adapter enrichment (one change, disciplined re-seal)

`symbol.references` rows now carry `file_path` (deterministic join against the
same frozen `files` table): raw `file_id` hashes are not human-reportable, and
the frozen T03 task requires file-and-line reporting. Per Stage-2 discipline:
22/22 implementation tests re-run PASS, the previous smoke run
(`SQI-SMOKE-20260916T101828Z-5bb591`) was marked superseded, and the six-task
smoke was fully re-executed against the re-sealed implementation
(`SQI-SMOKE-20260917T020338Z-15ea13`, 6/6 PASS, anchors verified).

## 3. Evaluator expansion — frozen oracles only

`tools/sqi_evaluator.py` implements protocol §5 verbatim; it defines no new
success criteria:

- T01: symbol + file + declaration line 84 + definition-source read.
- T02: ≥4 of the 5 frozen production callers named (full-5 coverage recorded);
  ≥2 call-site/definition source reads; ≥4 frozen CALLS edge ids present as
  session evidence fact ids.
- T03: all 6 frozen resolved locations (file_id→path resolved from the same
  frozen DB) + line numbers reported; ≥1 reference-site read; frozen `E-REF`
  ids present in the session; over-claiming flagged for human review.
- T04: 49 / 1031 / wide_impact reported; truncation explicitly reported;
  ≥1 affected-source read; interface aggregates cross-checked against the
  frozen values; symbol-level claims flagged for human review (shard-level
  frontier only).
- T05: target symbol + expected file + document section; required evidence id
  in session; equivalence read; content-level equivalence flagged for human
  review.
- T06: exactly one `bundle.explain` call within the frozen budget; truncation
  declared by the envelope; omission figures reported in the answer; omission
  honesty contradictions are machine-flagged and human-reviewed.
- Evidence oracle (SQI arm): `Evidence Used:` citation closure ⊆ session
  returned ids; unsupported claims counted.
- Source-verification oracle: per-task required read events from the session
  event stream.
- Capability-failure flags: `INVALID_ENVELOPE_IN_SESSION`, `BUDGET_VIOLATION`,
  `TRUNCATION_DISHONESTY`, `SQI_ACCESS_IN_NATIVE` — causally attributable SQI
  defects only; task failure is never auto-classified as capability failure.

Evaluator fixtures (known pass/fail variants per task) are unit-tested.

## 4. Formal runner wiring — arms comparable

`tools/sqi_formal_runner.py`:

- `--mode check`: preflight (all three seals round-trip, claude CLI present,
  three repos present, six frozen databases present) — currently PASS;
- `--mode run-cell` / `--mode batch`: 36 cells (6 tasks × 2 arms × 3 reps,
  frozen order), each cell an isolated session with raw artifacts
  (run.json / events.ndjson / agent-output.txt / evaluation.json /
  sqi-call-log.ndjson);
- arm parity enforced and unit-tested: the two arms share the identical base
  command and differ only in the system prompt (SQI citation + source-
  verification contract vs neutral read-only) and `--allowedTools`
  (`Read,Grep,Glob` vs `Read,Grep,Glob` + the sqi_cli Bash pattern);
- model/config come exclusively from the sealed `formal-protocol-config.json`.

## 5. Secondary seal

`contract/structured-query-interface-contract-v1.secondary-seal.sha256` —
9 files (schema, adapter, validator, smoke runner, implementation tests, CLI
bridge, evaluator, formal runner, wiring tests); SHA-256 round-trip 9/9 PASS
(after the `--arg` form and `PYTHONPATH` wiring fixes were folded in).
All earlier seals re-verified after every change: contract 7/7, implementation
5/5 (re-sealed for the adapter enrichment), protocol 2/2.

## 6. Test summary

- implementation tests: 22/22 PASS (`test_sqi_v1`)
- wiring tests: 19/19 PASS (`test_sqi_formal_wiring`, including the two
  `--arg`-form bridge tests)
- total: 41/41 PASS
- preflight (`--mode check`): PASS (three seals, claude CLI 2.1.270, three
  repos, six frozen databases, six tasks loaded)
- agent-style invocation from a foreign cwd: verified (`symbol.callers` on
  brpc returned the 7 frozen callers)
- formal batch: **NOT STARTED** (0 cells in `results/formal/`)

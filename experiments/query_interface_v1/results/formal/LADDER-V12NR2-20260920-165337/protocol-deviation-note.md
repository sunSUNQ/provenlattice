# LADDER-V12NR2-20260920-165337 — T06 gate FAIL, superseded by rule refinement

## Outcome

- T06 stage FAIL: r1 `task_success=false` (r2/r3 PASS).
- T05/SMOKE stages never started (fail-fast stage gating).

## T06.sqi.r1 mechanism (machine evidence)

- call 1: `bundle.explain {symbol: brpc.IsAskedToQuit}` with default (frozen)
  budget → 53311 bytes, `truncated=true` (31 edges + 41 symbols omitted).
- call 2: same anchor, REDUCED budget (10/12/4/6) → 32079 bytes.
- → `single_bundle_explain_call=false`, `budget_matches_frozen=false`.
- `empty_guidance_exposures=0`: the NR2 empty-result guidance was never
  shown — this failure is NOT the NR2 surface; it is the NR1 truncation
  rule's "issue a more targeted query instead" clause inviting a
  budget-shrink re-invocation after a truncated envelope. Stochastic in
  R3 (T06 3/3 with one call each), reproduced here.

## Response (generic, no task special-casing)

The NR1 truncation rule and its prompt mirror gained one generic clause:
a truncated envelope is normal and already contains everything that call
can return under its budget — finish from the returned evidence whenever
it suffices; do not re-query the same anchor with a different budget just
to obtain a shorter envelope (adapter `usage_discipline[0]` + arm prompt;
seals re-sealed; tests 96/96; verify_release PASS; commit cf5e8c9..).

This ladder is retained as the failure evidence that motivated the
refinement. The next ladder run (fresh id) is the qualification attempt.

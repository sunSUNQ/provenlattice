# LADDER-V12NR2-20260920-171310 — T06 gate FAIL (r2), superseded by subset clause

## Outcome

- T06 stage FAIL: r2 `task_success=false` (r1/r3 PASS, one call each).
- T05/SMOKE stages never started (fail-fast stage gating).

## T06.sqi.r2 mechanism (machine evidence)

- call 1: `bundle.explain {symbol: brpc.IsAskedToQuit}`, default (frozen)
  budget → 53630 bytes, `truncated=true` (matches the frozen budget).
- call 2: same anchor, REDUCED budget (10/12/4/6) → 32079 bytes; the
  agent's answer header explicitly adopts the shrunken budget
  ("budget 12 evidence / 6 symbols / 10 edges").
- → `single_bundle_explain_call=false`, `budget_matches_frozen=false`.
- Same mechanism as ladder #1 (different rep): the finish-over-requery
  clause ("do not re-query ... just to obtain a shorter envelope")
  reduced but did not eliminate the behavior.

## Response (subset clause, still generic)

Machine-verified interface fact (frozen DBs, both bundle.explain and
symbol.lookup paths): re-querying the SAME anchor with a smaller budget
returns an evidence-id SUBSET of the first envelope — budget slicing is a
deterministic prefix, so a smaller-budget retry can never add information.
This replaces the softer finish-over-requery wording in
usage_discipline[0] + arm prompt. Premise check committed with the tests;
seals re-sealed; 96/96 tests; verify_release PASS.

If the budget-shrink pattern still recurs after the subset clause, the
residual failure is pure backend behavioral noise on an already-correct
discipline text; the sanctioned paths are then (a) the NR1-precedent
single documented recheck, or (b) a user decision. No oracle changes.

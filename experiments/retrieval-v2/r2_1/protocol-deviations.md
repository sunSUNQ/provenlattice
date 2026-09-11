# R2.1 Protocol Deviations

## Deviation 1 — evaluator path-validation exception

During Track A, `T03.codegraph.r1` completed its Agent run but evaluator path validation raised a
`pathlib.glob` `ValueError` on a malformed wildcard. The pre-fix revision was `fb183cd`; the
post-fix revision was `8ace3b3`. The fix catches invalid patterns and returns a normal non-match;
it does not alter valid-path matching or any scoring formula. The interrupted empty directory was
removed, and the missing cell was run once. The other four pre-fix cells were preserved. Offline
replay of all 21 cells, including those four, reports identical `task_success`, recall, precision,
wrong-path, and unsupported-citation values: `EVALUATOR_FIX_NON_SEMANTIC = PASS`.

## Deviation 2 — frozen Ground Truth semantic mismatch

T01/T03 outputs identify plausible task-semantic implementation/document evidence, but the frozen
Ground Truth expects a local variable and a different document section. Original artifacts and
scores remain immutable; the mismatch is recorded only in attribution. No task or Ground Truth was
edited and no Agent cell was rerun.

# R2.1 Failure Attribution

## Track A — CodeGraph Progression: HOLD

Observed scores are preserved exactly: T01 CodeGraph `0/3` success and recall median `0.0`;
T03 `0/3` success with recall median `1.0`; T05 `1/3` success with recall median `1.0`, but two
unsupported citations. T01/T03 are marked `GROUND_TRUTH_SEMANTIC_MISMATCH`, not silently called
CodeGraph regressions: T01's frozen required symbol is a function-local `replicas` variable while
the prompt describes the bounded-load implementation; T03's frozen client section differs from the
consistent-hashing document the Agent actually used. Original prompts, Ground Truth, and scores are
unchanged. T05 is a positive signal, not a stable positive zone: R2's one-shot 17 turns/2 files did
not reproduce across R2.1 (median 48 turns/11 files for CodeGraph).

## Track B — Knowledge Progression: HOLD

The original `QUERY_BUNDLE_GAP` is **CLOSED**: all three R2.1 runs reached exact required recall
`1.0`, and the required DocumentSection Evidence entered the Agent-visible bundle. The gate remains
HOLD because one run has an unsupported citation and one has a fragment-path evaluator contract
false positive. These are Evidence Contract / Evaluator Contract issues, not Knowledge Coverage.

No further tuning or rerun is authorized by this closure.

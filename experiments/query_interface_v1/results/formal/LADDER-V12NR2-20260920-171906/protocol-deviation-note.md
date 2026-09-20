# LADDER-V12NR2-20260920-171906 — T06 GREEN, T05 gate FAIL (r2), superseded by call-semantics doc

## Outcome

- T06 stage GREEN 3/3 (subset clause holds; r2 2 calls but exactly one
  bundle.explain — the second call was a non-bundle.explain query).
- T05 stage FAIL: r1 PASS (8 calls), r3 PASS (9 calls, 4 exposures) —
  call counts down from 16-20 (C4-R3) to 6-9 under the v2 guidance.
- T05.r2 FAIL: 6 calls, 2 exposures.

## T05.sqi.r2 mechanism (machine evidence)

The v2 call-type-scoping guidance WORKED: after
`symbol.lookup {name: BoundedLoads}` → empty (hint shown), the agent
retried the bare slug under a different call type —
`bundle.explain {symbol: c_murmurhash_bl}` → RESOLVED (call 4, n=1).
But it then treated the local DOCUMENT_SECTION evidence as sufficient for
the document-to-code step and never issued
`code.related {document: c_murmurhash_bl}` — the only call that returns
the cross-layer link plus the linked code definition (verified on the
frozen DBs: bundle.explain(slug) → [DOCUMENT_SECTION] only; code.related
(slug) → [CROSS_LAYER_LINK, CODE_DEFINITION] = the frozen required pair).

## Root cause (generic, interface documentation)

The agent lacked the call-semantics distinction: bundle.explain returns
only an anchor's local bundle; code.related is the knowledge-to-code
composite query (cross-layer links + linked code definitions in one call).

## Response (prompt interface documentation, generic)

The SQI arm prompt gains a Call-semantics sentence documenting exactly
this distinction (no task ids, no anchors, no required ids). usage_
discipline unchanged (the empty-result rule already fired correctly).
Seal (secondary, sqi_formal_runner.py) re-sealed; tests 96/96;
verify_release PASS. Ladder #5 is the qualification attempt.

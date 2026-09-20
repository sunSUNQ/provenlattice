# LADDER-V12NR2-20260920-170205 — T06 GREEN, T05 gate FAIL (r2), superseded by guidance v2

## Outcome

- T06 stage GREEN (3/3, exactly one bundle.explain each) — the
  finish-over-requery refinement holds.
- T05 stage FAIL: r1 PASS (16 calls, 11 guidance exposures), r3 PASS
  (7 calls, 3 exposures — most efficient T05 on record), r2 FAIL
  (16 calls, 10 exposures).

## T05.sqi.r2 mechanism (machine evidence)

- 16 calls, 27 distinct evidence ids returned, content checks all true,
  citation closure ok — but the frozen required pair never entered the
  session (`required_evidence_id_in_session=false`,
  `knowledge_db_id_returned=[]`, `code_db_id_returned=[]`).
- call 2: `symbol.lookup {name: c_murmurhash_bl}` → empty (correct:
  find_symbol matches code-symbol kinds only). The agent then treated the
  anchor string as dead and only tried path-derived forms afterwards
  (calls 4/5/7/8) plus `bundle.explain` on the document (call 11, which
  returns the DOCUMENT node in related_entities — section node names are
  NOT discoverable there, so the v1 guidance's "discover stored names"
  path is a dead end).
- The resolving form — `code.related {document: c_murmurhash_bl}` (any
  node kind) — was never issued.

## Root cause (generic, interface semantics)

Anchor resolution is CALL-TYPE-SCOPED: symbol.lookup matches code symbols
only; code.related / bundle.explain resolve any node kind by exact id /
qualified_name / name. The same string can therefore resolve under one
call type and stay empty under another. The v1 guidance taught form
variation and bundle.explain discovery, not call-type retry.

## Response (guidance v2, still generic)

EMPTY_RESULT_GUIDANCE, usage_discipline[2] and the arm-prompt mirror now
state the call-type-scoping rule and prescribe: before abandoning an
anchor string, retry it under a different call type (an identifier that
stayed empty under symbol.lookup may resolve under code.related); never
retry semantically equivalent forms. The dead-end "discover stored names"
advice is removed. DB premise re-verified on the frozen databases
(symbol.lookup(slug)=0 rows with hint; code.related(slug)=2 rows returning
the frozen pair). Seals re-sealed; tests 96/96; verify_release PASS.

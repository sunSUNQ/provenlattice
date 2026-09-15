# Protocol Addendum — CALLS_V1 Macro Semantics (FROZEN)

```text
status: FROZEN_FOR_FIDELITY_V1
date: 2026-09-14
parent_protocol_commit: 12f405c677582a2982d035433bf6837126772716
decided_in: calibration-01 adjudication (post-join)
scope: every CALLS raw reference whose syntactic callee is a preprocessing macro,
       in this pilot and in all later Fidelity V1 annotation. No per-sample exceptions.
```

## Frozen rule

```text
CALLS_V1 semantics:
只认当前 Graph Fabric 实际建模层级中的可观察调用语义。
(Only the observable call semantics at the layer the current Graph Fabric
 actually models constitutes a CALLS_V1 relation.)
```

## Adjudication

The current Graph Fabric (V0.2) models the **pre-preprocessing source layer**
(tree-sitter syntax trees over repository files). Under the frozen rule the
macro classification is:

```text
A. macro invocation itself counts as CALLS   <-- SELECTED
B. macro expansion target counts as CALLS    <- rejected
C. macro invocation does not enter CALLS V1  <- rejected
D. build/preprocessor context insufficient   <- rejected
```

Derivation (no per-sample judgement involved):

- **A selected.** A macro invocation *is* an observable call expression at the
  modeled layer. The relation exists; whether a resolvable symbol target exists
  is a separate, downstream question (typically none — macros are not symbol
  nodes, and gtest-style macros live outside the repository).
- **B rejected.** Expansion targets are observable only after preprocessing,
  which is not the modeled layer; requiring them would smuggle build context
  into the relation-existence decision.
- **C rejected.** Excluding macro invocations requires recognizing that a given
  callee *is* a macro — preprocessor knowledge external to the modeled layer.
  Under the frozen rule such knowledge cannot gate relation existence.
- **D rejected.** The rule anchors CALLS_V1 semantics to the modeled layer, not
  to build/preprocessor context availability.

## Uniform verdict mapping consequences

For a CALLS raw reference whose callee is a macro:

1. `gold_relation_exists = true` (the call expression is observable at the
   modeled layer).
2. `relation_verdict` (blind world-fact space) = `NO_VALID_TARGET` when no
   valid repository symbol target exists among the candidates (the common
   case), or the normal target verdicts if a repository symbol target is
   genuinely determinable.
3. `difficulty_tags` must include `macro`; add `cross_module_homonym` only if
   same-named repository candidates exist.
4. Whether the macro is conditionally compiled or platform-specific does not
   change rule 1; it is recorded in evidence notes / `conditional_compilation`
   tag as usual.

## Effect on calibration-01

- Case `FQV1-rocksdb-1273fbd969565cef` (`ASSERT_EQ`): Annotator A's record
  (relation exists; macro; no in-repo candidate target) is the protocol-conformant
  reading under CALLS_V1. Annotator B's sealed record
  (`gold_relation_exists=false`, `RELATION_NOT_PRESENT`) reflects the
  pre-freeze protocol ambiguity — a strict post-expansion semantic reading —
  and is **not** an annotator-error adjudication. B's sealed files are not
  edited; the calibration gate applies the frozen rule symmetrically and
  documents both the raw and rule-normalized agreement.

This addendum does not modify the frozen protocol files; it is an
adjudication-phase addendum recorded for audit.

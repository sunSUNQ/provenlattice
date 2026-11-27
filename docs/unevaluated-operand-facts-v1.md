# Unevaluated operand access facts (V1)

Status: frozen for issue-pilot #139 (Parent #80; follow-up to #84).
Scope: C/C++ Sparse CFG/DFG producers in `sparsecfg.py`.

## 1. Contract

Naming an object inside a C/C++ unevaluated operand is not a runtime access.
The following contexts contribute **no** READ/WRITE/DEREFERENCE point and no
`memory_access_v1` / `buffer_extent_v1` value fact:

- C/C++ `sizeof` — `sizeof(type)`, `sizeof expr`, and `sizeof(expr)`;
- C11 `_Alignof` / C++ `alignof` when the operand parses as an expression;
- C++ `decltype` — both the expression and `decltype_specifier` forms;
- C++ `noexcept(expr)`;
- C++ `requires` expressions.

The rule is shared by all four access producers: the legacy READ/WRITE layer,
the structural DEREFERENCE layer, the V1 `local_access_v1` facts, and the CALL
memory-fact layer (`memory_access_v1` / `buffer_extent_v1` for
`memcpy`/`memmove`/`memset`). A single helper (`_in_unevaluated_operand`)
decides the language boundary.

## 2. Evaluated exceptions

`sizeof` is the only unevaluated context with evaluated sub-expressions:

- the bound of a VLA type is evaluated: `sizeof(int[n])` keeps the READ of
  `n`;
- an inner `sizeof` used as that bound is therefore evaluated:
  `sizeof(int[sizeof(int[n])])` keeps one READ of `n`;
- a still-outer unevaluated operand suppresses everything:
  `sizeof(sizeof(int[n]))` and `decltype(sizeof(int[n]))` publish no READ;
- only an array *result* type contributes a bound. `sizeof(int (*)[n])`
  (pointer to VLA) publishes no READ; `sizeof(int *[n])` (VLA of pointers)
  keeps it.

Array declaration bounds outside `sizeof` are ordinary evaluated expressions
and are unchanged.

## 3. What is retained

- Vocabulary identity is retained. A CALL spelled inside an unevaluated operand
  still publishes its CALL event (the call-graph fact); only its runtime memory
  facts and the `arguments` annotation are withheld. The same holds for other
  annotated event kinds: their identity survives, their runtime claims do not.
- Address computation is **not** an unevaluated operand. `&a[i]` keeps its
  structural DEREFERENCE point (and a resolvable `buffer_extent_v1`), but has no
  `memory_access_v1` value-access fact, as before.
- Declaration facts and type-name/static-semantics facts needed by the type
  system (for example `sizeof(int[4])`) remain; they are not object accesses.

## 4. Language boundary

`noexcept` is an operator only in C++. In C, `noexcept(x = 1)` is an ordinary
function call and its argument is evaluated; the WRITE is retained. The same
`call_expression` spelling is therefore interpreted by language, not by name
alone.

## 5. Out of scope (explicit unknown/unsupported)

- `typeid`: conditionally evaluated (polymorphic versus non-polymorphic
  operands); V1 does not suppress it and does not claim its evaluation state.
- Macro expansion that hides an unevaluated context, and unevaluated contexts
  produced by templates or default arguments.
- A full C++ constant-expression/template evaluator, `sizeof...` packs, and
  compiler-specific extensions.
- Non-access runtime effects inside unevaluated operands (allocations,
  releases, locks) remain governed by their own producers; this contract is
  limited to access facts.

These boundaries describe missing facts, not safety. A consumer that needs
evaluation certainty must fail closed when a fact is absent.

## 6. Identity, determinism, and freshness

- No relation, schema, or identity rule is added. Points are removed only at
  their existing producer; unrelated event streams are not rewritten. Within
  one owner/event-type stream, ordinals remain assigned by source order, so
  removing an unevaluated point may compact that stream's numbering rather
  than leave a hole.
- Byte-for-byte determinism is preserved for a fixed input.
- `sparse_cfg:cpp` advances **12 -> 13**. `sparse_dfg:cpp` stays at version 4;
  its recorded `dependencies["sparse_cfg:cpp"]` contract advances with SCFG and
  invalidates old DFG caches.
- The default L1 index does not run the walker, so no default-index artifact
  changes.

## 7. Acceptance evidence

- `tests/test_unevaluated_operand_facts.py` covers C/C++ sizeof/alignof/
  decltype/noexcept/requires, nested/parenthesized/call operands, global and
  member storage, the VLA boundary matrix, address-of, CALL identity, and
  determinism.
- Existing `test_buffer_extent_facts.py`, `test_sparsecfg_local_access_fact_gaps.py`,
  `test_uninitialized_use.py`, and `test_atomic_event.py` regressions are
  updated only where this contract deliberately changes the old expectation
  (a `sizeof`/`decltype`/`noexcept` operand no longer publishes a structural
  point or a legacy pointer-carrier event).

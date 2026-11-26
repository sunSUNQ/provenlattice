# C/C++ Local Declaration, Access, and Control-Position Facts V1

Status: frozen additive output contract for issue-pilot #84, with the #134
fact-production corrections. This layer produces
facts for a later definite-assignment consumer. It does **not** decide
`uninitialized_use`, mint defect candidates, build SSA or points-to relations,
add a parallel graph, change storage schema, or extend the public Evidence
projection.

## 1. Availability and carriers

The on-demand C/C++ sparse CFG analyzer publishes these facts. The default L1
index neither runs the sparse walker nor materializes them.

The analyzer adds edgeless `DECLARATION` points and ordinary method-local
`READ`/`WRITE` points. Existing local pointer `DEREFERENCE` points remain
threaded control points and are not duplicated. Facts are deterministic JSON
strings in the existing `payload.annotations` map:

- `local_declaration_v1` on `DECLARATION`;
- `local_access_v1` on local `READ`, `WRITE`, and `DEREFERENCE`;
- `control_position_v1` on every point carrying either V1 fact above.

JSON keys are sorted and encoding is compact. No storage table, column, edge
kind, or relation was added. `DECLARATION`, ordinary local `READ`/`WRITE`, and
all pre-existing accesses remain absent from `CONTROL_REACHES`; the walker
keeps a loud invariant against making them edge endpoints. A local
`DEREFERENCE` keeps its existing edges.

## 2. Declaration facts

One `DECLARATION` point is emitted per method-local object declarator. Its byte
span and `matched_name` identify that declarator, not the whole declaration
statement. Block-scope function declarations are not object facts. Parameters,
fields, globals, and declarations owned by a nested local type are outside this
population.

`local_declaration_v1` has the following fields:

| Field | Meaning |
| --- | --- |
| `declaration` | Scope-qualified declaration token, or `""` when unresolved. |
| `decl` | Existing legacy declaration spelling for information only; never a shadowing-safe join key. |
| `storage` | Existing declaration-index storage classification. |
| `storage_class` | `automatic`, `register`, `static`, `thread_local`, or `extern`. |
| `type` | Declaration-index type token, or `""` when unresolved. |
| `kind` | `scalar`, `pointer`, or `unsupported`. |
| `status` | `supported` only for a resolved built-in scalar or direct pointer object; otherwise `unsupported`. |
| `initialized` | `true`, `false`, or JSON `null` when initialization cannot be modeled. |
| `initializer` | `none`, `expression`, `zero_initialized`, `unknown`, or `not_applicable`. |
| `initializer_expression` | Exact retained initializer syntax, or JSON `null`. |
| `initializer_start_byte`, `initializer_end_byte` | Initializer span, or JSON `null`. |
| `zero_initialized` | Whether language rules or empty-brace value initialization guarantee zero initialization. |
| `limitation` | Empty for supported declarations; otherwise the unsupported boundary. |
| `coverage_status` | `complete` or `unknown` for the containing method walk. |
| `coverage_reasons` | Sorted stable reason strings; empty exactly when coverage is complete. |

Built-in scalar and direct pointer objects are the only supported positive
population. Arrays, references, class/struct/union objects, typedef/alias or
otherwise unresolved value types, unresolved declaration identities, and local
`extern` declarations are explicit `unsupported`. An unsupported declaration
is not silently treated as an uninitialized scalar.

`initialized=false` means a supported automatic/register object has no
initializer. Static and thread-local objects without a written initializer have
`initialized=true`, `initializer="zero_initialized"`, and
`zero_initialized=true`. C++ direct and brace initializers are retained: for
example, `int x(1)` and `int x{1}` use `expression`, while `int x{}` and
`int x = {}` use `zero_initialized`. An automatic unsupported class object with
no visible initializer uses `initialized=null` and `initializer="unknown"`;
its default constructor is not guessed away. A local `extern` declaration uses
`initialized=null` and `initializer="not_applicable"` because it is not an
automatic object definition.

C++ if-init statements are walked before their conditions. Condition declarations
whose grammar stores the initializer on the declaration itself retain the same
initializer metadata and initialization WRITE as an ordinary init-declarator.
A range-for variable remains in the declaration population even though the
installed grammar does not index its identity: it publishes an unsupported,
unresolved declaration with method-wide unknown coverage rather than disappearing
behind `unsupported_loop`.

## 3. Declaration identity and local accesses

A consumer joins `local_access_v1.declaration` to
`local_declaration_v1.declaration`. It must not join by variable spelling,
legacy `decl`, line number, ordinal, or event array position. The scoped token
includes the declaring file, enclosing function, name, and declaration byte
offset, so same-spelled nested locals remain distinct.

The token is deterministic within a source snapshot. It is **not** a permanent
cross-revision primary key: inserting or moving source can change its byte
offset, and cache rebuilding requires a new join. Event identity remains the
existing owner/type/ordinal identity; the annotation itself does not mint an
event id.

`local_access_v1` contains:

| Field | Meaning |
| --- | --- |
| `declaration` | The same scoped token as its declaration, or `""` when unresolved. |
| `direction` | `READ`, `WRITE`, or `DEREFERENCE`. |
| `target` | `direct` for a direct local object access, `pointer` for local pointer dereference, or `indirect` on a retained legacy indirect write event. |
| `status` | `supported` only for the resolved direct scalar/pointer access or resolved local pointer dereference; otherwise `unsupported`. |
| `limitation` | Empty when supported, otherwise the positive-support boundary. |
| `coverage_status`, `coverage_reasons` | The same method coverage as the declaration contract. |

Ordinary automatic-local accesses intentionally omit legacy `subject*`
annotations and do not enter the legacy sparse DFG subject channel. Existing
local pointer bare-copy and null-write exceptions retain all old annotations
and behavior, with the V1 fact added alongside them. Function-static accesses
also retain their legacy subject channel while carrying the same scoped V1
join to their local declaration. Shared-storage accesses retain their old
identity semantics. Parameters retain the historical WRITE-only rule.

A declarator's own identifier is not a use. Automatic-local declarator names
emit no access event. A pre-existing function-static declarator-name READ is
retained only for legacy compatibility and carries neither `local_access_v1`
nor `control_position_v1`; actual later static uses carry both V1 facts.

A direct call callee resolved to a local function pointer publishes a local
READ; treating every callee as a non-access would hide an uninitialized `fp()`
use. Other callee shapes retain their existing DEREFERENCE/nested-expression
handling.

A bare local identifier used as an `if` condition publishes a declaration-linked
READ before the branch point. Operands in `sizeof`, `alignof`, `decltype`,
`noexcept`, `requires`, and equivalent unevaluated contexts publish no V1
READ/WRITE; naming an object in a compile-time operand is not a runtime access.
The evaluated bound of a VLA type is the explicit exception: `sizeof(int[n])`
retains its runtime READ of `n`, unless a still-outer unevaluated operand
suppresses the entire expression. Range-for reads use the same explicitly
unresolved, unsupported identity boundary as their declaration.

Read-modify-write keeps the existing paired READ/WRITE representation and the
WRITE's `access_kind="READ_MODIFY_WRITE"`. Writing `*p` or `p[i]` is not a
direct WRITE of pointer variable `p`; it marks possible write-through coverage
unknown. A local pointer dereference carries a V1 fact on its existing
DEREFERENCE node.

## 4. Control positions

`control_position_v1` records the walker's actual incoming `_Open` positions
before the carrier would be threaded. It contains:

```json
{
  "status": "reachable",
  "entry": false,
  "predecessors": [
    {"event_type": "BRANCH", "ordinal": 0, "flags": ["branch=true"]}
  ],
  "evaluation_predecessor": null,
  "coverage_status": "complete",
  "coverage_reasons": []
}
```

The owner is inherited from the carrier. A predecessor's
`(event_type, ordinal)` therefore identifies an event in the same owner and
source snapshot. Entries are sorted and deduplicated; flags are sorted.
`entry=true` represents the synthetic method-entry open, for which no event id
is fabricated.

`evaluation_predecessor` is an additive, nullable `(event_type, ordinal, flags)`
identity for the immediately preceding local access at the same control
position. It is separate from `predecessors`, whose control-flow meaning is
unchanged for existing consumers. For `y = (x = y)`, the chain is RHS `READ y` →
`WRITE x` → outer `WRITE y`; the initial READ has no evaluation predecessor.
These identities compose without reparsing source or comparing byte spans, and
they do not turn edgeless accesses into CFG edge endpoints.

For straight-line code, positions chain through actual threaded events. Within
if/else arms they retain `branch=true` or `branch=false`; after a join they can
contain both predecessors. A return expression's access precedes RETURN, and a
later statement on the terminated chain has no reachable predecessor.

`status` has three values:

- `reachable`: at least one entry or event predecessor exists and the method has
  no V1 coverage gap;
- `unreachable`: the incoming list is empty and coverage is complete;
- `unknown`: a method coverage gap prevents a sound reachable/unreachable
  claim. Unknown never means unreachable.

The annotation does not add paths or change path budgets. A DEREFERENCE's
annotation captures the position before that DEREFERENCE is connected, while
its original control edges remain unchanged.

## 5. Coverage boundaries

V1 positively supports straight-line code, if/else, and early returns. Coverage
is method-wide and fail-closed: one unsupported shape marks every V1 local fact
and control position in that method unknown rather than presenting partial
definite-assignment knowledge as complete.

| Reason | Boundary |
| --- | --- |
| `partial_parse` | The file or method contains parse errors/missing syntax. The publisher's existing degraded status still applies. |
| `macro` | A preprocessor construct or an identifier matching a file-defined macro occurs in the method. |
| `goto` | A `goto` prevents the ordinary structured-walk interpretation from proving positions. |
| `unsupported_loop` | `while`, `do`, C `for`, or range-for requires a fixpoint outside V1. |
| `unsupported_conditional` | `switch` or a conditional expression is outside the if/else-only V1 contract. |
| `unsupported_short_circuit` | A local access in a short-circuit RHS cannot claim the LHS-gated position from the structured walk. The access has no entry/predecessor claim and the method coverage is unknown. |
| `unsupported_lambda` | Lambda execution is not part of the enclosing method's ordinary control path. |
| `unsupported_exception` | `try`, `catch`, or `throw` requires exceptional control semantics outside V1. |
| `unknown_write_through` | An indirect local write, a local address or pointer passed to a call/C++ constructor (including direct/brace initialization, `new_expression` constructor arguments, and ambiguous function-style construction), or a write through a reference may change an object through an unmodeled target. |
| `unsupported_reference` | A read through a local reference is outside direct-object V1; no direct access to the referenced object is invented. |
| `unresolved_declaration` | A required declaration identity cannot be resolved; no scoped token is invented. |

These reasons describe analysis coverage, not whether source is safe or unsafe.
An `unsupported` declaration status and an `unknown` method coverage status are
independent and may coexist.

## 6. Compatibility and versioning

`sparse_cfg:cpp` advances from v10 to v11 (after #104 advanced v9 to v10).
Existing v9/v10 materialization is stale and is not returned as current facts.
`events:cpp` is unchanged. `sparse_dfg:cpp` remains v4: its declared sparse-CFG
dependency changes to v11, which forces rematerialization, while its legacy
edge output remains unchanged.

Adding ordinary local READ/WRITE points can renumber source-order READ/WRITE
ordinals within an owner. Consumers must not assume v10 access event ids survive
the v11 migration. `DECLARATION` has its own event-type ordinal domain and does
not renumber DEREFERENCE or other event types.

The legacy held-lock fact producer ignores declaration points and ordinary
local V1 accesses that lack its subject channel. The legacy call-relation
reader likewise ignores V1-marked indirect callee READs, so a local `fp()` fact
does not become shared-slot `MAY_CALL` evidence. These boundaries keep additive
facts out of existing query inputs; no defect rule or Evidence schema changes.

Repeated materialization is byte-stable. Default-index absence, stale-version
rebuild, deterministic annotations, branch/early-return positions, shadowing,
partial parse, unsupported constructs, write-through, and legacy DFG/lockset
compatibility are covered by `tests/test_local_declaration_access_facts.py`,
`tests/test_sparsecfg_local_access_fact_gaps.py`, and the existing sparse CFG/DFG
and concurrency regressions.

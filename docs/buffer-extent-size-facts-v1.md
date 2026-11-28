# Buffer / Extent / Size Facts V1

Status: frozen output contract for issue-pilot #82, additively extended for
memory-API destination arrays by issue-pilot #94. This layer **produces facts
only**. It does not decide whether an access is in bounds, report an
overflow/OOB defect, add a graph relation, or extend the public Evidence
projection.

## 1. Availability and carrier

The facts are emitted by the on-demand C/C++ sparse CFG analyzer on existing
`ALLOC`, `CALL`, `READ`, `WRITE`, and `DEREFERENCE` nodes. The default L1 index
does not run this walker and does not create these facts.

Each fact is a deterministic JSON string in the node's existing
`payload.annotations` map:

- `buffer_extent_v1`: declared-array or allocation extent;
- `memory_access_v1`: subscript index, pointer offset, or memory-API length.

JSON object keys are sorted and the encoding is compact, so repeated
materialization is byte-stable. No storage column or schema changed.

The containing analysis node supplies the **source event identity**:
`event_id`, `event_type`, `owner_symbol_id`, owner triple, ordinal, and source
span. The fact deliberately does not mint a second event id. An annotation is
not an input to `identity.event_id`, so adding these facts does not rewrite
existing event identities.

## 2. Object identity

Both fact kinds contain an `object` object with the existing subject facts:

```json
{
  "decl": "local:buf",
  "storage": "local",
  "type": "char",
  "member": ""
}
```

These are the existing `subject_decl`, `subject_storage`, `subject_type`, and
`subject_member` values under shorter names local to the JSON contract. When an
array use resolves to a declaration, `object` additionally carries
`scoped_decl`, the existing declaration index's scope-qualified identity. For
example, two nested-block locals both retain legacy `decl="local:buf"`, but their
`scoped_decl` values include different declaration byte offsets. This additive
field does not rewrite any existing subject annotation. JSON examples below
elide `scoped_decl` for readability.

The object must be interpreted **together with the carrier's owner/event
identity**.
In particular, `local:buf` is not a repository-wide object id; two methods may
legitimately have different `buf` objects. A consumer joins by owner plus
subject identity, never by variable name, line number, or array position alone.

For an unresolved pointer, `object` identifies the pointer expression when the
existing subject facts can do so, while `source="unknown"` says that its pointee
extent is not known. It does not turn the pointer variable's own `sizeof` into
the pointee extent.

## 3. Resolution model

The following fields are common to extent/access values:

| Field | Meaning |
| --- | --- |
| `expression` | Retained source expression, or JSON `null` when no sound expression is available. |
| `constant` | Folded integer, or JSON `null` for an explicitly unknown value. |
| `unit` | `elements` or `bytes`; never interchangeable. |
| `status` | `constant`, `expression`, `unknown`, or `unsupported`. |
| `limitation` | Empty for a fully resolved constant; otherwise the reason the value is not a proven constant. |

`expression` means the syntax is retained but V1 does not supply a proven
constant. This includes dynamic values and constant-looking syntax whose target
semantics V1 declines to model. `unknown` means the requested fact applies but
cannot be resolved. `unsupported` marks a recognized shape outside V1, such as
a flexible array member. A missing annotation means the fact does not apply to
that point (for example, a scalar write has no buffer index); it does **not**
mean zero or in bounds.

For array extents, allocation sizes, and memory lengths, V1 folds only
non-negative numeric literals (including C's zero-prefixed octal spelling) and
`*`, `<<`, and `+` whose operands are recursively foldable, through parentheses.
Subscript indices and pointer offsets use the same bounded folder with negative
constants explicitly enabled. Every folded value and intermediate result must
fit a signed 32-bit int. A leading minus has identical semantics whether the
grammar retains it in a single numeric token or in a unary expression, including
zero-prefixed octal spellings. Only a **decimal** magnitude of 2147483648 may be
negated to produce `INT32_MIN`; hexadecimal, octal, and binary magnitudes must
not exceed `INT32_MAX`. Thus `-0x80000000`, `-(020000000000)`, and their binary
counterpart remain expressions rather than incorrectly publishing
`constant=-2147483648`. Outside index/offset positions, negative results remain
unevaluated. Unsigned-suffixed literals, wider results, and invalid or
potentially overflowing shifts are retained without a constant. Thus V1 never
uses Python's unbounded arithmetic to invent C/C++ unsigned wraparound, and UB
such as `1 << -1` cannot abort analysis. Pointer offsets have one explicit
signed projection, specified in §5.2: subtraction negates an already proved
signed magnitude, and negating `INT32_MIN` fails closed. V1 does not evaluate
identifiers, macros, `sizeof`, calls, casts, or general arithmetic. In particular,
`(_Bool)2` and `(bool)2` are retained expressions, not the incorrect constant 2; no cast is
folded without target-type semantics. No guessed value is substituted for a
failed fold. Compact expressions preserve semantic whitespace in ordinary/raw
string and character literals, between multi-word type tokens such as
`signed char`, and wherever joining tokens would change their meaning
(`n / *v` becomes `n/ *v`, not the comment opener `n/*v`). Comments act as
token-separating whitespace, so `unsigned/*comment*/char` retains the known
character-element type without merging the two tokens.

## 4. `buffer_extent_v1`

### 4.1 Declared arrays

A direct, single-dimensional fixed array access carries:

```json
{
  "source": "declared_array",
  "unit": "elements",
  "expression": "64",
  "constant": 64,
  "status": "constant",
  "limitation": "",
  "bytes": {
    "unit": "bytes",
    "expression": "64",
    "constant": 64,
    "status": "constant",
    "limitation": ""
  },
  "object": {"decl": "local:buf", "storage": "local", "type": "char", "member": ""}
}
```

The top-level value is always the declared **element count**. The nested `bytes`
value is the byte projection. It is constant for `char`, `signed char`, and
`unsigned char` arrays. For example, `int a[4]` has a known element count of 4,
but its byte value remains explicitly unknown:

```json
"bytes": {
  "unit": "bytes",
  "expression": "4 * sizeof(int)",
  "constant": null,
  "status": "unknown",
  "limitation": "target ABI element size is not available"
}
```

The declaration index resolves the use first. The extent map is keyed by the
resolved declaration's exact `(start_byte, name)`, not by the use-site name, so
shadowed and same-named arrays cannot exchange extents. Ordinary parenthesized
declarators such as `char (a)[4]` are unwrapped without accepting a pointer or
reference to an array as a direct array. Resolved objects also carry
`scoped_decl`, which distinguishes nested-block declarations. An explicit
`this->field` is accepted only when resolution reaches a field; it can never
borrow a same-named local or global array. Statement-local declarations (for
example a for-init array) do not lend their extent or identity to uses outside
that statement: the extent-only scope overlay skips the stale declaration and
continues resolving outward, so a visible outer array is still found. The
installed grammar's unindexed range-for declarator is the conservative
exception: inside that statement it yields unknown/empty object identity rather
than borrowing an outer array or minting a declaration id. Structured bindings
and lambda init-captures likewise shadow an outer same-spelled array without
acquiring its extent or declaration identity; their actual bound/captured type
is outside V1. Range initializers and capture initializers remain in the enclosing
scope, while a new nested local declaration takes precedence over the capture
overlay. Arbitrary member paths and cast/computed array bases remain unsupported. In particular,
`((unsigned char *)a)[i]` cannot reuse `a`'s element count with a differently
typed subscript.

### 4.2 Allocation extents

An `ALLOC` node has `source="allocation"`, `unit="bytes"`, and the common value
fields. Supported size positions are:

- `malloc(n)`, `memalign(alignment, n)`, `valloc(n)`, `pvalloc(n)`;
- `realloc(p, n)`, `aligned_alloc(alignment, n)`;
- `posix_memalign(&p, alignment, n)`;
- `calloc(count, element_size)` and
  `reallocarray(p, count, element_size)`.

For calloc-like allocation, `count_expression` and
`element_size_expression` retain the two source arguments and `expression` is
their deterministic `count * element_size` composition. Compound operands are
parenthesized (`calloc(1+2, 3+4)` retains `(1+2) * (3+4)`), so the retained text
cannot change the expression's meaning. The byte `constant` is present only
when both components fold **and their product also fits signed 32-bit int**.
Thus `calloc(65536, 65536)` and `reallocarray(0, 65536, 65536)` retain their
product expressions but publish `constant=null`, not `4294967296`. The same
unit rule applies to an array's nested `bytes` projection: a non-character
dynamic extent `n` is retained as `n * sizeof(T)`, never mislabeled as `n`
bytes.

Examples:

```json
{
  "source": "allocation", "unit": "bytes", "expression": "16",
  "constant": 16, "status": "constant", "limitation": "",
  "object": {"decl": "local:p", "storage": "local", "type": "char", "member": ""}
}
```

```json
{
  "source": "allocation", "unit": "bytes", "expression": "n",
  "constant": null, "status": "expression",
  "limitation": "size is not a compile-time constant",
  "object": {"decl": "local:p", "storage": "local", "type": "char", "member": ""}
}
```

Other allocator families and C++ `new` produce `status="unknown"` with a
limitation rather than guessing which argument is a size. `malloc(sizeof(p))`
retains only that byte-size expression; it is not treated as the extent of the
object pointed to by `p`.

The allocation `object` is populated only when the allocator result itself has
a direct value-flow path to a resolved **pointer** target of a plain `=`
assignment or initializer through language-checked wrappers, or for a declared
write-through out-argument. Requiring a
pointer excludes integer handles and, in C++, overloaded `operator=` and
converting initialization: `class_sink = malloc(64)` and
`ClassSink sink = malloc(96)` do not bind the class object as the allocation
buffer. C permits casts, a selected conditional arm, and the value-producing
right side of a built-in comma expression. C++ permits only a C-style cast whose
type descriptor has a direct pointer declarator, as in `(char *)malloc(128)`; a
class/scalar cast is not transparent. In particular, `(Rebind)malloc(64)` may
construct `Rebind` and return an unrelated address through `operator void *()`,
so it retains extent 64 with an empty/unknown object. C++ conditional expressions
are not traversed because common-type conversions can transform the selected
arm; even a pointer-only conditional leaves the allocation object unbound in V1.
C++ comma expressions are not traversed because an overloaded `operator,` need
not return its right operand. A compound
assignment does not bind the result: `n += (unsigned long)malloc(32)` reads and
updates `n`; it is not an allocation-object assignment. The LHS must also be a
direct identifier or member path. An indirect/subscript target such as
`*pp = malloc(32)` binds a pointee that V1 cannot name, so its object remains
empty/unknown rather than claiming the pointer variable `pp` itself.
Write-through out-arguments follow the same identity rule: only parentheses or
casts around a direct `&p` / `&s.member` form whose resolved target is a pointer
bind that target. Thus `posix_memalign(&p, 16, 32)` binds pointer `p`, but
`posix_memalign(pp, 16, 64)`, `posix_memalign((void **)*pp, 16, 128)`, and an
integer handle behind `(void **)&handle` leave the object empty/unknown rather
than claiming `pp` or the handle. In C++, the address-of must also be provably built-in:
`&p` on a class-like or unresolved operand may invoke overloaded `operator&`,
so it produces an empty/unknown object rather than binding the source operand.
`p = consume(malloc(32))`
and `p = (malloc(64), dst)` therefore leave the allocation object
empty/unknown; `p = malloc(128)` binds `p`. An unbound `malloc(n)` retains its
byte size but has an empty/unknown object, and its size argument `n` is never
presented as the allocated object.

A member LHS or out-argument needs more than a matching member spelling. V1
accepts only a direct `s.member` (or raw-pointer `s->member`) whose root
declaration has an explicitly spelled class/tag type with one visible,
unambiguous definition in the file, and then resolves the field inside that
exact definition. Plain/qualified/alias C++ type names, `M::Same` versus
`N::Same`, nested C tags with the same name, computed roots, overloaded
`operator->`, and out-of-line method member fallbacks do not supply positive
member-type evidence. A field
defined directly in the object's own class/tag declaration remains exact. These
rules exclude the valid but wrong bindings `s.p = malloc(64)` through an
overloaded assignment and `posix_memalign((void **)&s.handle, ...)` through an
integer member hidden by a same-spelled tag, while retaining an unambiguous
pointer member.

### 4.3 Memory-API destination arrays

An existing `memory_access_v1.kind="memory_length"` CALL also carries
`buffer_extent_v1` when its first argument names a destination whose extent V1
can resolve or explicitly classify. The destination expression is normalized
once and shared by the access object and extent lookup; an outer assignment
result is never consulted. Thus `char dst[4]; memset(dst, 0, 8);` has, on the
same CALL, a byte length of 8 and a declared extent of 4 elements / 4 bytes. No
additional `dst[i]` event is required. The same rule covers unqualified and
exact `std::` spellings of `memcpy`, `memmove`, and `memset`.

Access and extent use the same scope-overlay declaration, including after an
expired statement-heading shadow. The extent map is keyed by that declaration's
exact identity and its cached template is copied before attaching the
destination identity. A resolved fact retains the
access object identity and may additionally carry `scoped_decl`; direct member
destinations retain root-plus-member identity. Element/byte units follow §4.1,
so `int a[4]` still has 4 elements and an explicitly unknown target-ABI byte
size. Pointer, VLA, unresolved, and unsupported member targets fail closed with
unknown/unsupported facts rather than borrowing a declaration or guessing a
size. Computed destinations and resolved non-array scalar values do not acquire
an array extent fact.

### 4.4 Unknown access targets

A subscript or pointer dereference whose target cannot be resolved to a direct
fixed array receives `source="unknown"`, null values, and a limitation. This is
used for unknown pointers, array-adjusted parameters, unresolved member extents,
and unsupported pointer shapes. A plain non-array scalar access has no
`buffer_extent_v1` annotation.

## 5. `memory_access_v1`

Every access fact has `access`, `kind`, the common value fields, and `object`.

### 5.1 Subscript

```json
{
  "access": "WRITE",
  "kind": "subscript",
  "unit": "elements",
  "expression": "n-1",
  "constant": null,
  "status": "expression",
  "limitation": "index is not a compile-time constant",
  "object": {"decl": "local:buf", "storage": "local", "type": "char", "member": ""}
}
```

`access` is `READ`, `WRITE`, or `READ_MODIFY_WRITE`. Local array accesses often
have only a `DEREFERENCE` carrier because the existing access layer intentionally
filters most local READ/WRITE points. In that case V1 derives `access` from the
expression's direct assignment/update position and retains the DEREFERENCE event
id. On an existing WRITE carrier, a compound assignment/update likewise records
`READ_MODIFY_WRITE`; its separate READ half remains READ. No replacement event
is added and no existing event is renumbered. An expression such as `a[N-1]`
therefore produces a fact, not an OOB verdict.

Address computation and unevaluated type/size/exception queries are not value
accesses. `&a[i]` and `&a[i].member` keep their structural DEREFERENCE point (a
resolvable `buffer_extent_v1` may still be present) but have no
`memory_access_v1` annotation. `sizeof(a[i])`, `decltype(a[i])`, and
`noexcept(a[i])` are unevaluated operands: since #139 the producer publishes no
READ/WRITE/DEREFERENCE point for them at all, and therefore no
`memory_access_v1` or `buffer_extent_v1` value fact either. See
[`unevaluated-operand-facts-v1.md`](unevaluated-operand-facts-v1.md). Member and
conditional lvalue paths retain their actual direction: `a[i].x = 0` is WRITE,
`a[i].x += 1` is READ_MODIFY_WRITE, and both selected arms of
`(c ? a[i] : b[i]) = 0` are WRITE.
An arrow path is different: `a[i]->x = 0` writes `x` but READs the pointer
stored in `a[i]`, so the subscript's fact is READ rather than WRITE.
The transparent cancelling `&*` pair is preserved for direction only in C:
`*&a[i] = 0` is WRITE and `*&a[i] += 1` is READ_MODIFY_WRITE. C++ never
cancels this pair in V1 because the element type may overload `operator&` and
return an unrelated pointer. Arbitrary outer dereferences are not cancelled,
so `*a[i]` still requires the read of the pointer stored in `a[i]`. Likewise,
C propagates an outer lvalue write through the value-producing right operand
of a built-in comma, but C++ does not propagate through comma expressions:
overloaded `operator,` can return an unrelated reference. The underlying
array's declared extent may remain available even when no value-access fact
is emitted for these C++ shapes. A C-style or `static_cast` cast to a primitive
lvalue reference preserves an outer write, as in `((int&)a[i]) = 0` and
`static_cast<int&>(a[i]) = 0`. Other reference casts do not propagate direction
and omit the value-access fact rather than guessing READ or WRITE. For the same
reason, a subscript/pointer-offset expression whose resolved element type is
class-like has no V1 value-access annotation: overloaded assignment and
conversion operators are outside this contract, while the declared array extent
remains a valid fact.

Both tree-sitter spellings are supported: C's `index` and C++'s `indices`.
Every successfully parsed single index expression is retained, including
`sizeof(int)`, a character literal, or C++ `true`; these remain expressions
unless the bounded integer folder proves a value. Multiple/unparsed indices are
explicitly unknown. C/C++ commuted subscripts are normalized only with
declaration and direct-array syntax evidence: `2[a]` records index 2, while
`i[a]` and `i[(a)]` record index `i`, all with `a`'s object and extent.
Parentheses around either operand do not defeat that normalization. Direct
array-adjusted parameters provide orientation evidence even though their extent
is unknown: `i[parameter_array]` records index `i` and the parameter array's
object, while ordinary `parameter_array[i]` retains the same orientation as
`p[i]`. An ambiguous shape is never allowed to relabel the array as the index.
When a known non-pointer, non-array left operand is paired with a target that
lacks direct-array evidence, as in `i[p]`, `i[external_pointer]`,
`i[undeclared_target]`, or `i[s.data]`, both the index value and object identity
are explicitly unknown instead of recording the right operand as an index into
integer `i`. C++ adds overload boundaries on both operands: a known class-like
or unresolved left operand is not assumed to use built-in subscript semantics,
and an array/pointer left operand requires a provably builtin integral index.
For example, `i[a]` with `Idx::operator[](const char *)`, or `a[o]` with an
overloaded `operator+(char *, O)`, produces unknown index/object facts rather
than index `i`/`o` plus `a`'s declared extent. Builtin integral evidence covers
literals, `sizeof`/`alignof`, declared builtin integral values, parentheses,
and operators/conditionals whose value operands satisfy the same rule; V1 does
not infer class conversions. A direct member used as an integer or pointer value
must additionally satisfy the exact, unique-visible-type rule in §4.2; a field
borrowed from a same-spelled namespace type or nested tag is not evidence.
Built-in commuted normalization on an identifier requires a declared integral
left operand (or a numeric literal).

### 5.2 Pointer offset

For `*(p + k)` and `*(p - k)`, V1 emits `kind="pointer_offset"` and
`unit="elements"`. The expression/value describe the signed offset from `p`;
for example, `*(p - 2)` has expression `-(2)` and constant `-2`, while
`*(p + -2)` retains expression `-2` and the same constant. Negative literals and
the supported recursive operators follow §3, including consistent signed-octal
folding and the decimal-only `INT32_MIN` magnitude exception. A non-decimal 2³¹
magnitude therefore remains an expression, and pointer subtraction never turns
it into a positive constant through a second negation. Dynamic offsets retain
their expression with a null constant. Built-in commuted addition is
normalized with declaration evidence: `*(i + a)` and `*(i + p)` use `a`/`p` as
the base object and `i` as the offset, while `*(a + i)` and `*(p + i)` retain
that same base/offset orientation. If neither operand provides enough
pointer/array evidence, the offset and object are unknown rather than blindly
using the left operand as the base. C++ pointer arithmetic additionally
requires builtin operand types so an overloaded `operator+`/`operator-` is not
reinterpreted as pointer arithmetic. Arithmetic whose base/offset shape cannot
be separated safely is `status="unknown"` with `complex pointer arithmetic` or
`commuted pointer arithmetic` as its limitation. Plain `*p` has no offset
annotation.

### 5.3 Memory-API length

Direct unqualified `memcpy`, `memmove`, and `memset` CALL nodes, plus their exact
`std::memcpy`, `std::memmove`, and `std::memset` spellings, emit
`kind="memory_length"`, `access="CALL"`, and `unit="bytes"`. Other qualified
spellings such as `N::memset` have no memory-length fact: a same-leaf function in
another namespace does not inherit the standard API's semantics. `function` retains
the callee spelling, and the common value fields describe the third argument.
The `object` is resolved independently from the first (destination) argument;
it never reuses an outer assignment's result variable. Thus
`r = memcpy(dst, src, 16)` identifies `dst`, not `r`. Parentheses, casts, and a
leading address-of are unwrapped before identity resolution, so
`memset((void *)s.data, 0, 4)` and, in C, `memset(&s.data, 0, 8)` retain `s`'s
declaration identity and member path `data`. Without a leading address-of, the
unwrapped expression must resolve to a pointer or direct array for that same
object; an integer handle or unresolved value does not qualify. The address-of
must be built-in: C++ `&m` on a class-like or unresolved operand can invoke
`operator&`, so its object is empty/unknown. A C++ class value passed directly
or through a C-style cast may invoke a user-defined pointer conversion, so
`memset(c, 0, n)` and `memset((void *)c, 0, n)` retain length `n` but do not bind
`c`. Member destinations follow §4.2's exact field/type rule: a same-spelled
field from another namespace type or nested C tag cannot prove that the actual
member is a pointer or array, so its object remains empty/unknown. A computed
destination whose object cannot be identified conservatively has empty/unknown
identity.
The same CALL additively carries the destination's `buffer_extent_v1` under
§4.3. Length and extent remain independent values and units: the third argument
is always bytes, while a declared array's top-level extent is elements and its
nested `bytes` projection follows the character/target-ABI rules. Both facts use
the same normalized first argument and object identity, including when the CALL
is the right side of an assignment.
Dynamic lengths remain expressions with null constants. String-copy bounds are
not modeled as general byte extents in V1.

## 6. Deliberate V1 boundaries

The following are not proven ranges and must remain unknown/unsupported:

- VLA, macro-dependent, or otherwise non-constant declared extents;
- flexible/incomplete array members;
- multidimensional arrays/subscripts and arbitrary struct-member extent lookup;
- general member type resolution, including plain/qualified/alias C++ type
  names, ambiguous same-spelled classes/tags, computed member roots, and
  out-of-line method member fallback;
- array-adjusted parameters, pointers/references to arrays, typedef recovery,
  and points-to propagation;
- cast/computed array bases, ambiguous commuted subscripts, and unindexed
  range-for declaration identities;
- target-ABI byte sizes other than the character types listed above;
- target-dependent signed/unsigned arithmetic, general expression evaluation,
  complex pointer arithmetic, and `sizeof` evaluation;
- C++ conditional allocation value flow and non-pointer allocation casts;
- cross-function size summaries, full C++ object/RAII modeling, and general
  range analysis.

These boundaries describe missing facts, not safety. A later bounds query must
fail closed when the contract does not supply the value it needs.

## 7. Versioning, freshness, and non-detection guarantee

The metadata structure change advances:

- `sparse_cfg:cpp`: **5 -> 6** (`cpp-sparse_cfg-v6`) for the original facts,
  **6 -> 7** for issue-pilot #84, **7 -> 8** for #89 G1 ATOMIC event
  recognition, **8 -> 9** (`cpp-sparse_cfg-v9`) for #94 memory-API destination
  extents, **9 -> 10** for #104 negative index/offset facts, **10 -> 11** for
  #134 local declaration/access fact gaps, **11 -> 12** for #141 signed
  negative-literal boundary corrections, and **12 -> 13** for #139 unevaluated
  operand access facts;
- `sparse_dfg:cpp`: **3 -> 4** (`cpp-sparse_dfg-v4`), unchanged by #94.

`events:cpp` remained version 2 at the time of the original change because the
event vocabulary/identity producer was unchanged; it was later advanced to 3 by
issue-pilot #90 (member-level lock designations), and remains 3 after #94. SCFG
freshness rejects the old analyzer version/source hash. SDFG also records the
SCFG dependency contract, so `dependency_staleness` rejects a cache built under
`cpp-sparse_cfg-v12` even if its own source hash is unchanged.

No defect query or defect category consumes these annotations in V1. In
particular, an extent of 4 plus an index of 4 is only a pair of facts; it does not
create a candidate. The targeted Golden suite covers constants, dynamic values,
unknown/unsupported shapes, C/C++ identity, nested and statement-local scope,
range-for/structured-binding/init-capture shadowing, parenthesized declarators,
explicit this-member resolution, reference-cast access direction,
cast/octal handling, bounded integer overflow/shift failures, commuted
subscripts, cast array bases, member/conditional and unevaluated access
direction, RMW, direct allocation result binding, C++ overload/conversion
fail-closed boundaries, exact/ambiguous member type evidence, memory-API
destination identity and same-CALL extents, exact `std::` coverage,
pointer/VLA/unresolved/member destination failures, non-character element/byte
units, assignment-target independence, raw strings/comments/token boundaries,
byte-unit/expression fidelity, byte determinism, default-index absence,
version/dependency/source freshness, and zero defect candidates for OOB-shaped
subscript and memory-CALL fixtures. A positive
double-free control also verifies that removing both new annotation keys from
materialized SCFG/SDFG payloads leaves the complete defect query response
byte-identical.

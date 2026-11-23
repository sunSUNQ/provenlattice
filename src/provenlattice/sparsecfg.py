"""The sparse control-flow graph over semantic events (stage 3, appendix B.4).

Two halves share this module, and the split is deliberate:

* `SparseCfgBuilder` reads tree-sitter trees and produces one file's CFG as
  plain data (`models.ParsedCfg`). It runs at parse time, where the source
  bytes and the owner spans live, and never learns a repository id -- point
  identity travels as `models.PointKey`, which `graph.py` resolves against the
  events it published.
* `find_paths` and the three pattern functions answer reachability over
  published edges. They are pure functions over plain data, so tests can drive
  them without a database and the query layer stays a thin reader.

Neither half imports tree-sitter, so the module imports cleanly when the C
grammar is not installed.

What the graph compresses: a method's statements collapse to the events the
vocabulary produced plus three structurally-derived points (CHECK / BRANCH /
DEREFERENCE) and one synthetic exit per method. Straight-line code produces no
edges at all beyond the chain between its points -- that is what keeps the
graph sparse at million-line scale.
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Collection, Iterable, Mapping

from .identity import CFG_EXIT_PREFIX
from .models import (
    STORAGE_FIELD, STORAGE_FUNCTION_STATIC, STORAGE_FILE_STATIC, STORAGE_GLOBAL,
    STORAGE_LOCAL, STORAGE_PARAMETER, STORAGE_UNKNOWN,
    PointKey, ParsedCfg, ParsedEdge, ParsedPoint,
)
from .semantics.events import ACCESS_EVENTS

CONTROL_REACHES = "CONTROL_REACHES"

# Additive V1 facts for local definite-assignment consumers.  They travel in
# the existing annotation map; no storage relation or schema is introduced.
DECLARATION = "DECLARATION"
LOCAL_DECLARATION_KEY = "local_declaration_v1"
LOCAL_ACCESS_KEY = "local_access_v1"
CONTROL_POSITION_KEY = "control_position_v1"

# Edge flags (design doc §6, plus `fallthrough` for switch chains). The sorted
# flag set is the edge id's discriminator, so the exact spelling is frozen:
# renaming a flag changes every id in the database.
BRANCH_TRUE = "branch=true"
BRANCH_FALSE = "branch=false"
EXCEPTION = "exception"
LOOP_BACK = "loop_back"
FALLTHROUGH = "fallthrough"

# Point flag: the condition's top-level operator is a short-circuit, so the
# inner points feed both arms. Marks the `||` blind spot recorded in the stage
# 3 execution record: `if (p != NULL || p->f)` hides its dereference from the
# unchecked_dereferences pattern exactly like the guarded `p && p->f` does.
SHORT_CIRCUIT = "short_circuit"

# Annotation keys that ride on a point's metadata (stage 4). `subject` says
# which name an operation acts on; `subject_from` says how the walker got it,
# because a name recovered from an assignment is a stronger claim than one
# recovered from a member call's receiver -- and the typed queries need that
# difference to keep an unresolved identity from reading as a resolved one.
SUBJECT_FROM_ASSIGNMENT = "assignment"
SUBJECT_FROM_ARGUMENT = "argument"
SUBJECT_FROM_RECEIVER = "receiver"
SUBJECT_FROM_RAII = "raii"
SUBJECT_FROM_RETURN = "return"
# The subject a write-through allocator names: `posix_memalign(&p, ...)`
# allocates `p`, and the name is recovered from what the first argument
# addresses rather than from the call's value. Its own spelling and not
# `argument`, because the two are different claims: `free(p)` acts on the
# expression the argument *is*, while this acts on the expression the
# argument *points at*, and a reader of the annotation has to be able to
# tell which one produced the name.
SUBJECT_FROM_OUT_ARGUMENT = "out_argument"

# The event types that get a subject recovered for them. Stage 3 covered
# ALLOC/RELEASE/CALL; the typed queries need the lock, atomic, spawn and
# return points too -- `RETURN` because `return p;` is how a method hands a
# resource to its caller, which is the one ownership transfer a sparse CFG can
# see at all.
_ANNOTATED_EVENT_TYPES = frozenset(
    {"ALLOC", "RELEASE", "CALL", "LOCK", "UNLOCK", "ATOMIC", "THREAD_SPAWN", "THREAD_JOIN", "RETURN"}
)

# The two node types that bind a name to a value. `_plain_generic` carries the
# bound name down the whole subtree as `_assign_target`, which is what makes
# `p = malloc(n)` name the allocation `p`; `_assign_target_applies` reads the
# same set back off the tree to decide how far that carrying may reach.
_ASSIGNMENT_NODES = frozenset({"init_declarator", "assignment_expression"})

# The event types that are published but never connected (stage 5A). An access
# remains a fact about an expression rather than a new node on existing query
# paths: giving it an edge would change `find_paths` results and path budgets.
# V1 publishes its incoming control position as an annotation instead. Local
# declarations use the same edgeless carrier. Enforced in `_emit`, which is the
# one function every edge goes through, and it raises rather than dropping the
# edge silently -- this can only be broken by an edit to the walker, never by
# source code, so it must be loud.
_EDGELESS_EVENT_TYPES = ACCESS_EVENTS | frozenset({DECLARATION})

# Which child of a statement is the object being written. Position is the only
# signal there is: no keyword in `x = y` says which side is the write.
WRITE_TARGET_FIELDS: dict[str, str] = {
    "assignment_expression": "left",
    "compound_assignment_expression": "left",
    "update_expression": "argument",
    "init_declarator": "declarator",
}

def _is_read_modify_write(node: Any) -> bool:
    """Whether a write also reads its own target (read-modify-write).

    tree-sitter-c and tree-sitter-cpp both fold `x += y` into an
    ``assignment_expression`` whose operator is not `=` (a
    ``compound_assignment_expression`` node never appears in either installed
    grammar, so the operator is the signal); `x++` and `--x` are an
    ``update_expression``. A plain `x = y` is not RMW: reading x there, if it
    happens, is the right-hand side child's own READ, not a self-read.
    """
    if node.type == "update_expression":
        return True
    if node.type == "assignment_expression":
        operator = node.child_by_field_name("operator")
        return operator is not None and operator.type != "="
    return False

# A declaration names an object; it does not read one. `int x;` and the `x` in
# `int x = 0;` are the same non-access.
DECLARED_FIELDS: dict[str, str] = {
    "declaration": "declarator",
    "parameter_declaration": "declarator",
    "field_declaration": "declarator",
    "function_definition": "declarator",
}

# Fields whose expression is a name rather than a variable: the callee of a
# call is what is being invoked, not an object being touched.
ACCESS_SKIP_FIELDS: dict[str, str] = {"call_expression": "function"}

# Which storage classes publish a legacy access. V1 ordinary locals are admitted
# separately in `_access_point`, rather than added here: downstream escape
# classification also derives from this set and must retain its old meaning.
# Shared-storage accesses retain their original identity semantics. Parameters
# retain the historical write-only rule below. New local events stay edgeless,
# exactly like the existing access population.
ACCESS_STORAGES = frozenset({
    STORAGE_FIELD, STORAGE_FILE_STATIC, STORAGE_FUNCTION_STATIC, STORAGE_GLOBAL,
    STORAGE_PARAMETER, STORAGE_UNKNOWN,
})


@dataclass(frozen=True, slots=True)
class LanguageProfile:
    """The grammar facts the CFG walker reads, held as data.

    C and C++ agree on every fact the walker needs today, and the two shapes
    that do differ between the grammars (the node wrapping an if/while/switch
    condition, the subscript index field name) are handled by trying
    alternatives rather than by forking the algorithm. The profile exists so a
    third language joins as another instance, not another walker. Python's
    profile is a registered gap of stage 3, not an oversight.
    """

    name: str
    deref_node_types: frozenset[str] = frozenset(
        {"pointer_expression", "field_expression", "subscript_expression"}
    )
    # `*p` dereferences; `&p` does not.
    deref_unary_operators: frozenset[str] = frozenset({"*"})
    # `p->f` dereferences; `p.f` does not.
    deref_member_operators: frozenset[str] = frozenset({"->"})
    # The tree-sitter `null` rule covers NULL and nullptr in both dialects.
    # `p == 0` is a number_literal and stays unrecognised (registered
    # imprecision, matching the design doc's conservative reading).
    null_node_types: frozenset[str] = frozenset({"null"})
    short_circuit_operators: frozenset[str] = frozenset({"&&", "||"})
    # The expressions that denote an object being touched (stage 5A). One
    # access is one outermost expression: `p->buf[i]` is a subscript_expression
    # whose argument is a field_expression whose argument is an identifier, and
    # it is *one* access, not three -- the walker emits for the outermost and
    # stops. These are grammar facts like `deref_node_types` above, and they
    # live in the profile for the same reason: a third language joins by
    # declaring its own, not by editing the walker.
    access_node_types: frozenset[str] = frozenset(
        {"identifier", "field_expression", "subscript_expression", "pointer_expression"}
    )


C_PROFILE = LanguageProfile(name="c")
CPP_PROFILE = LanguageProfile(name="cpp")

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ControlPath:
    """One acyclic path, as three parallel tuples: event ids, their types, and
    the edge ids between consecutive points."""

    points: tuple[str, ...]
    types: tuple[str, ...]
    edges: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "points": list(self.points),
            "types": list(self.types),
            "edges": list(self.edges),
        }


def _field_of(edge_or_event: Any, name: str) -> Any:
    """Read a field from a `SemanticEdge`/`SemanticEvent` object or its row."""
    if isinstance(edge_or_event, dict):
        return edge_or_event[name]
    return getattr(edge_or_event, name)


def _optional_field_of(edge_or_event: Any, name: str) -> Any:
    """Like `_field_of`, but None when absent (FE-8 byte span may be missing)."""
    if isinstance(edge_or_event, dict):
        return edge_or_event.get(name)
    return getattr(edge_or_event, name, None)


def _flags_of(edge: Any) -> frozenset:
    flags = _field_of(edge, "flags")
    if isinstance(flags, str):
        flags = json.loads(flags)
    return frozenset(flags)


def _text_of(source: bytes, node: Any) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _expression_text(source: bytes, node: Any) -> str:
    """Whitespace-free source text, so `p  ->  f` reads as `p->f`."""
    return _WHITESPACE.sub("", _text_of(source, node))


def _operator_of(node: Any, source: bytes) -> str:
    """The operator token of an expression node, whatever the grammar names it.

    The bundled grammars carry an `operator` field on most expression nodes,
    but the fallback keeps the walker honest against grammars that leave the
    token anonymous: scan the node's own children for a operator-shaped token.
    """
    operator = node.child_by_field_name("operator")
    if operator is not None:
        return _text_of(source, operator).strip()
    for child in node.children:
        if not child.is_named and child.type in {
            "*", "&", "->", ".", "!", "&&", "||",
            "==", "!=", "<", ">", "<=", ">=",
        }:
            return _text_of(source, child).strip()
    return ""


def _span(node: Any) -> tuple[int, int] | None:
    """A node's identity as a span, or None. Comparing spans, not Node objects:
    py-tree-sitter hands back a fresh wrapper per accessor call, so `in` on the
    wrappers is whatever its `__eq__` does today."""
    return None if node is None else (node.start_byte, node.end_byte)


def _defined_macro_names(root: Any, source: bytes) -> set[str]:
    names: set[str] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in {"preproc_def", "preproc_function_def"}:
            name = node.child_by_field_name("name")
            if name is not None:
                names.add(_text_of(source, name))
        stack.extend(node.named_children)
    return names


def _declaration_shape_keys(
    root: Any, source: bytes, kinds: frozenset[str]
) -> set[tuple[int, str]]:
    """Declaration-index keys whose declarator contains one of ``kinds``."""
    keys: set[tuple[int, str]] = set()

    def contains(node: Any) -> bool:
        return node.type in kinds or any(contains(child) for child in node.named_children)

    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "declaration":
            for declarator in node.children_by_field_name("declarator"):
                if contains(declarator):
                    name = _declarator_name(source, declarator)
                    if name:
                        keys.add((node.start_byte, name))
        stack.extend(node.named_children)
    return keys


def _outermost_access(node: Any, access_types: frozenset[str]) -> Any:
    """The access expression a target denotes, skipping parens and casts.

    `s->buf` is already an access; `(int *)p->buf` reaches the
    `field_expression` through the cast. Returns None when the target names no
    object this stage recognises (a literal, a call, a compound literal).
    """
    if node is None:
        return None
    if node.type in access_types:
        return node
    for child in node.named_children:
        found = _outermost_access(child, access_types)
        if found is not None:
            return found
    return None


def _unwrap_condition(node: Any) -> Any:
    """The expression inside a condition's wrapper node, if there is one.

    C++ wraps if/while/switch conditions in `condition_clause`; C uses
    `parenthesized_expression`; `do` uses a parenthesized expression in both.
    Everything else is already the expression.
    """
    if node is None:
        return None
    if node.type == "condition_clause":
        value = node.child_by_field_name("value")
        if value is not None:
            return value
    if node.type == "parenthesized_expression" and node.named_children:
        return node.named_children[0]
    return node


def _label_flags(case: Any) -> tuple[str, ...]:
    """`default:` hangs off the false edge; every real case is a true edge."""
    if case.child_by_field_name("value") is None:
        return (BRANCH_FALSE,)
    return (BRANCH_TRUE,)


class SparseCfgBuilder:
    """Walk one parsed file and produce its compressed CFGs.

    The builder consumes the SAME hits the event layer consumed --
    `EventExtractor.extract_hits` -- so an operation cannot be an event while
    being invisible to the CFG, or the reverse. It never assigns event
    identity beyond `PointKey`: the repository id does not exist at parse time.
    """

    def __init__(
        self,
        source: bytes,
        owners: Any,
        hits: Iterable[Any],
        line_of: Callable[[int, bool], int],
        profile: LanguageProfile,
        declarations: Any = None,
        out_param: Iterable[str] = (),
    ) -> None:
        """`owners` is a parsing.events.OwnerIndex; `line_of(byte, is_end)`.

        `declarations` is a parsing.declarations.DeclarationIndex, or None when
        the language has none (Python today). It is handed in rather than built
        here because the index is shared with the other semantic consumers.
        The V1 array-extent map is the one bounded exception: declaration
        dimensions are not yet an index fact, so `build` reads that syntax from
        the same tree and joins it back by the declaration's exact `(start_byte,
        name)` identity.

        `out_param` is the vocabulary's list of allocation callees that hand
        the pointer back through their first argument, as last name
        components. It arrives as a fact for the same reason `declarations`
        does: which C functions have that shape is a language fact and lives
        in the vocabulary file, and the walker only reads it.
        """
        self.source = source
        self.owners = owners
        self.line_of = line_of
        self.profile = profile
        self.declarations = declarations
        self._out_param = frozenset(out_param)
        # `(declaration node start, declared name)` -> array extent fact. Built
        # once from the root in `build`, never keyed by a use-site name alone.
        self._array_extents: dict[tuple[int, str], dict[str, Any]] = {}
        # Direct array declarator identity, including array-adjusted parameters.
        # Unlike extents, this syntax set is also used only to orient subscripts.
        self._array_declaration_keys: set[tuple[int, str]] = set()
        self._reference_declaration_keys: set[tuple[int, str]] = set()
        # Exact declaration/type syntax for V1's one-level member type evidence.
        # Declaration.type_token is deliberately shallow and must never select a
        # same-spelled class or tag by itself.
        self._value_declaration_types: dict[tuple[int, str], Any] = {}
        self._value_type_definitions: list[Any] = []
        self._value_type_aliases: set[str] = set()
        # Statement headings are lexical scopes too, but DeclarationIndex
        # intentionally owns only compound/function/class scopes. These V1-only
        # maps skip stale heading declarations and recognize unindexed range-for
        # shadows without changing the index's global semantics.
        self._statement_declaration_scopes: dict[int, Any] = {}
        self._statement_declaration_names: dict[int, dict[str, int]] = {}
        # The hits grouped by the span of the node that produced them. Two
        # events share one span when one node matches two event types
        # (`free(p)` is both CALL and RELEASE); they chain in type order.
        self._hits_by_span: dict[tuple[int, int], list[Any]] = {}
        for hit in hits:
            self._hits_by_span.setdefault((hit.start_byte, hit.end_byte), []).append(hit)
        for group in self._hits_by_span.values():
            group.sort(key=lambda hit: (hit.event.event_type, hit.event.ordinal))
        self._points: list[_Point] = []
        # Edges under construction: (src, dst, flags) where dst is a _Point or
        # the _EXIT marker. `None` never appears -- it is dropped at _emit.
        self._edges: list[tuple[_Point, Any, tuple[str, ...]]] = []
        self._annotations: dict[PointKey, dict[str, str]] = {}
        self._seq = 0
        # Per-method state, reset in _build_method.
        self._span: Any = None
        self._has_points = False
        self._assign_target: str | None = None
        self._assign_exact = True
        self._assign_node: Any = None
        # How many conditional constructs the walk is currently inside. This
        # is the walker's *own* control model -- the same dispatch that builds
        # the edges -- so "depth 0" means what the graph means by it: no if,
        # loop, switch or catch encloses the statement being walked. The
        # escape facts (5C-2's 2.11) are keyed on it; a plain assignment that
        # every path of the method executes is the one an escape ruling can
        # trust.
        self._conditional_depth = 0
        # Where each vocabulary hit sits, by the same key its annotations are
        # stored under. The escape post-pass needs positions to tell "a write
        # after the allocation" from "a same-named local earlier in the
        # method"; hit points themselves are transient (the event layer
        # publishes them), so their positions are kept here instead.
        self._hit_positions: dict[PointKey, tuple[int, int]] = {}
        self._breaks: list[_BreakContext] = []
        self._switches: list[_SwitchContext] = []
        self._handlers: list[_HandlerContext] = []
        self._pending_throws: list[tuple[list[_Open], _HandlerContext]] = []
        # V1 local declaration/access state. Coverage is method-wide: when any
        # unsupported control or write-through shape is present, every local
        # declaration in that method explicitly says the analysis is unknown.
        self._file_partial = False
        self._macro_names: set[str] = set()
        self._coverage_reasons: set[str] = set()

    # ------------------------------------------------------------------
    # entry points

    def build(self, root: Any) -> ParsedCfg:
        self._file_partial = bool(getattr(root, "has_error", False))
        self._macro_names = _defined_macro_names(root, self.source)
        (
            self._array_extents,
            self._array_declaration_keys,
            self._value_declaration_types,
            self._value_type_definitions,
            self._value_type_aliases,
        ) = _collect_array_extents(root, self.source)
        self._reference_declaration_keys = _declaration_shape_keys(
            root, self.source, frozenset({"reference_declarator"})
        )
        (
            self._statement_declaration_scopes,
            self._statement_declaration_names,
        ) = _collect_statement_declaration_scopes(root, self.source)
        spans = {(span.start_byte, span.end_byte): span for span in self.owners.spans}
        nodes_by_span: dict[tuple[int, int], Any] = {}
        self._collect(root, spans, nodes_by_span)
        for span_key in sorted(nodes_by_span):
            self._build_method(spans[span_key], nodes_by_span[span_key])
        self._assign_ordinals()
        self._annotate_control_positions()
        return ParsedCfg(
            # The public shape: a ParsedPoint per point, flags in their sorted
            # canonical form. `matched_via` says which of the walker's two
            # products this is: a structural control point, or an access. The
            # vocabulary's own `matched_via` never reaches here -- those points
            # come from `_point_from_hit` and are published by the event layer.
            points=[
                ParsedPoint(
                    event_type=point.event_type,
                    owner_kind=point.owner_kind,
                    owner_qualified_name=point.owner_qualified_name,
                    owner_signature=point.owner_signature,
                    ordinal=point.ordinal,
                    start_line=point.start_line,
                    end_line=point.end_line,
                    matched_name=point.matched_name,
                    matched_via="access" if point.event_type in ACCESS_EVENTS else "structural",
                    flags=tuple(sorted(point.flags)),
                    start_byte=point.start_byte,
                    end_byte=point.end_byte,
                )
                for point in sorted(self._points, key=lambda point: point.key())
            ],
            edges=self._parsed_edges(),
            annotations=self._annotations,
        )

    def _collect(self, node: Any, spans: dict, found: dict) -> None:
        key = (node.start_byte, node.end_byte)
        if key in spans:
            found[key] = node
        for child in node.named_children:
            self._collect(child, spans, found)

    def _build_method(self, span: Any, node: Any) -> None:
        body = node.child_by_field_name("body")
        if body is None:
            # A prototype owns no control flow, and an EXIT after it would
            # claim a body the source does not have.
            return
        self._span = span
        self._has_points = False
        self._coverage_reasons = {"partial_parse"} if self._file_partial else set()
        try:
            _, opens = self._linearize(body, [_Open(None, ())])
        finally:
            self._finalize_local_facts()
            self._span = None
            self._assign_target = None
            self._assign_exact = True
            self._assign_node = None
            self._conditional_depth = 0
            self._breaks = []
            self._switches = []
            self._handlers = []
            self._pending_throws = []
            self._coverage_reasons = set()
        if not self._has_points:
            return
        self._annotate_escapes(span)
        self._annotate_aliases(span)
        # Every dangling open falls into the synthetic exit. Returns and throws
        # already emitted their own exit edges inside the walk. The open's own
        # flags ride along: a `while (c)` condition's false arm reaches the exit
        # as `branch=false`, not as a flag-less fall into the void.
        for open_edge in opens:
            if open_edge.src is not None:
                self._emit(open_edge.src, _EXIT, open_edge.flags)

    @staticmethod
    def _declarator_contains(node: Any, kinds: frozenset[str]) -> bool:
        if node is None:
            return False
        if node.type in kinds:
            return True
        return any(
            SparseCfgBuilder._declarator_contains(child, kinds)
            for child in node.named_children
        )

    def _local_declaration_points(self, node: Any) -> list[_Point]:
        """Publish one edgeless fact per method-local declarator.

        Positive definite-assignment support is deliberately limited to built-
        in scalar and direct pointer objects. Other declarations retain their
        stable syntax identity with `status=unsupported`; they are never
        silently treated as initialized or as ordinary automatic scalars.
        """
        if node.type != "declaration":
            return []
        points: list[_Point] = []
        for declarator in node.children_by_field_name("declarator"):
            name = _declarator_name(self.source, declarator)
            if not name:
                continue
            declaration = None
            if self.declarations is not None:
                candidate = self.declarations.resolve(node.start_byte, name)
                if (
                    candidate is not None
                    and candidate.start_byte == node.start_byte
                    and candidate.name == name
                    and candidate.storage in {STORAGE_LOCAL, STORAGE_FUNCTION_STATIC}
                ):
                    declaration = candidate
            # DeclarationIndex intentionally knows more than this V1 consumes.
            # A non-local declaration nested in a method (for example a field
            # declaration inside a local class) is not a local object fact.
            if declaration is None and self.declarations is not None:
                candidate = self.declarations.resolve(node.start_byte, name)
                if candidate is not None and candidate.storage not in {
                    STORAGE_LOCAL, STORAGE_FUNCTION_STATIC
                }:
                    continue

            specifiers = {
                self._text(child)
                for child in node.children
                if child.type in {"storage_class_specifier", "type_qualifier"}
            }
            if "extern" in specifiers:
                storage_class = "extern"
            elif specifiers & {"thread_local", "_Thread_local"}:
                storage_class = "thread_local"
            elif declaration is not None and declaration.storage == STORAGE_FUNCTION_STATIC:
                storage_class = "static"
            elif "register" in specifiers:
                storage_class = "register"
            else:
                storage_class = "automatic"

            is_pointer = (
                declaration.is_pointer if declaration is not None
                else self._declarator_contains(declarator, frozenset({"pointer_declarator"}))
            )
            # A block-scope function declaration is not an object definition.
            # Pointer-to-function declarators remain pointer objects.
            if declarator.type == "function_declarator" and not is_pointer:
                continue
            unsupported_shape = self._declarator_contains(
                declarator, frozenset({"array_declarator", "reference_declarator"})
            )
            type_node = node.child_by_field_name("type")
            scalar_type = type_node is not None and type_node.type in {
                "primitive_type", "enum_specifier",
            }
            if unsupported_shape:
                kind = "unsupported"
                limitation = "array and reference objects are outside local declaration V1"
            elif is_pointer:
                kind = "pointer"
                limitation = ""
            elif scalar_type:
                kind = "scalar"
                limitation = ""
            else:
                kind = "unsupported"
                limitation = "only built-in scalar and direct pointer declarations are supported"
            if declaration is None:
                kind = "unsupported"
                limitation = "local declaration identity is unresolved"
                self._coverage_reasons.add("unresolved_declaration")
            if storage_class == "extern":
                kind = "unsupported"
                limitation = "a local extern declaration is not an automatic object definition"

            value = (
                declarator.child_by_field_name("value")
                if declarator.type == "init_declarator" else None
            )
            zero_initialized = storage_class in {"static", "thread_local"}
            initialized: bool | None = False
            initializer = "none"
            if storage_class == "extern":
                initialized = None
                initializer = "not_applicable"
                zero_initialized = False
            elif value is not None:
                initialized = True
                initializer = "expression"
                if value.type == "initializer_list" and not value.named_children:
                    # C++ `T x{}` / `T x = {}` value-initializes the object.
                    zero_initialized = True
                    initializer = "zero_initialized"
            elif zero_initialized:
                initialized = True
                initializer = "zero_initialized"
            elif kind == "unsupported":
                # A class object's default constructor, an unresolved type, or
                # another unsupported shape is not evidence of no initialization.
                initialized = None
                initializer = "unknown"
            scoped = (
                self.declarations.scoped_identity(declaration)
                if declaration is not None and self.declarations is not None else ""
            )
            legacy = self._facts_for(declaration, "", "true") if declaration is not None else {}
            fact = {
                "declaration": scoped,
                "decl": legacy.get("subject_decl", ""),
                "storage": declaration.storage if declaration is not None else STORAGE_LOCAL,
                "storage_class": storage_class,
                "type": declaration.type_token if declaration is not None else "",
                "kind": kind,
                "status": "supported" if kind != "unsupported" else "unsupported",
                "initialized": initialized,
                "initializer": initializer,
                "initializer_expression": self._text(value) if value is not None else None,
                "initializer_start_byte": value.start_byte if value is not None else None,
                "initializer_end_byte": value.end_byte if value is not None else None,
                "zero_initialized": zero_initialized,
                "limitation": limitation,
            }
            point = self._new_point(
                DECLARATION,
                declarator,
                annotations={LOCAL_DECLARATION_KEY: _facts_json(fact)},
                matched_name=name,
            )
            points.append(point)
        return points

    def _finalize_local_facts(self) -> None:
        reasons = tuple(sorted(self._coverage_reasons))
        owner_key = (self._span.kind, self._span.qualified_name, self._span.signature)
        for point in self._points:
            if (
                point.owner_kind,
                point.owner_qualified_name,
                point.owner_signature,
            ) != owner_key:
                continue
            keys = [
                key for key in (LOCAL_DECLARATION_KEY, LOCAL_ACCESS_KEY)
                if key in point.annotations
            ]
            if not keys:
                continue
            # Retained until `_annotate_control_positions`, after ordinals are
            # assigned. Empty tuple means complete; None means not a V1 fact.
            point.local_coverage = reasons
            for key in keys:
                fact = json.loads(point.annotations[key])
                fact["coverage_status"] = "unknown" if reasons else "complete"
                fact["coverage_reasons"] = list(reasons)
                point.annotations[key] = _facts_json(fact)

    def _local_declaration_identity(self, node: Any, name: str) -> tuple[Any, str]:
        if self.declarations is None or not name:
            return None, ""
        declaration = self._resolve_extent_declaration(node, name)
        if declaration is None or declaration.storage not in {
            STORAGE_LOCAL, STORAGE_FUNCTION_STATIC,
        }:
            return None, ""
        return declaration, self.declarations.scoped_identity(declaration)

    def _supported_local_object(self, declaration: Any) -> bool:
        if declaration is None:
            return False
        key = (declaration.start_byte, declaration.name)
        if key in self._array_declaration_keys or key in self._reference_declaration_keys:
            return False
        if declaration.is_pointer:
            return True
        type_node = self._value_declaration_types.get(key)
        return type_node is not None and type_node.type in {
            "primitive_type", "enum_specifier",
        }

    def _unknown_address_of_in_call(self, node: Any) -> None:
        if node.type != "pointer_expression" or _operator_of(node, self.source) != "&":
            return

        def record(argument: Any) -> None:
            name = self._root_identifier(argument)
            if not name:
                return
            facts = self._subject_facts(argument, name)
            if facts.get("subject_storage") in {STORAGE_LOCAL, STORAGE_FUNCTION_STATIC}:
                self._coverage_reasons.add("unknown_write_through")

        argument = node.child_by_field_name("argument")
        ancestor = node.parent
        while ancestor is not None and ancestor.type not in {
            "declaration", "expression_statement", "return_statement",
        }:
            if ancestor.type == "call_expression":
                record(argument)
                return
            if ancestor.type == "init_declarator":
                value = ancestor.child_by_field_name("value")
                if value is not None and value.type in {"argument_list", "initializer_list"}:
                    # C++ direct/brace construction has no call_expression node,
                    # but its constructor receives the same pointer argument.
                    record(argument)
                return
            ancestor = ancestor.parent

    def _unknown_pointer_argument(self, node: Any) -> None:
        """A call or C++ constructor may write through a local pointer argument."""
        if node.type == "call_expression":
            arguments = node.child_by_field_name("arguments")
        elif node.type == "init_declarator":
            arguments = node.child_by_field_name("value")
            if arguments is not None and arguments.type not in {
                "argument_list", "initializer_list",
            }:
                arguments = None
        elif node.type == "declaration":
            # `B b(p)` is a function_declarator in tree-sitter's ambiguous
            # parse. If `p` is a local pointer, a C++ consumer cannot treat the
            # shape as a prototype and silently miss possible constructor
            # write-through; keep the whole method fail-closed instead.
            declarator = node.child_by_field_name("declarator")
            arguments = (
                declarator.child_by_field_name("parameters")
                if declarator is not None and declarator.type == "function_declarator"
                else None
            )
        else:
            arguments = None
        if arguments is None:
            return
        stack = list(arguments.named_children)
        while stack:
            current = stack.pop()
            if current.type in {"identifier", "type_identifier"}:
                name = self._text(current)
                declaration = self._resolve_extent_declaration(current, name)
                if (
                    declaration is not None
                    and declaration.storage in {STORAGE_LOCAL, STORAGE_FUNCTION_STATIC}
                    and declaration.is_pointer
                ):
                    self._coverage_reasons.add("unknown_write_through")
                    return
            stack.extend(current.named_children)

    def _annotate_escapes(self, span: Any) -> None:
        """Link frame-local allocations to the writes that let them escape.

        5C-2's 2.11, the half the WRITE events alone do not carry. `tmp =
        strdup(x)` declares a local, and `g_name = tmp;` copies the pointer
        into storage that outlives the frame; neither fact answers "does this
        allocation leak" on its own -- the lifetime walk sees an allocation
        with no release, and the WRITE is a fact about `g_name`, not about
        `tmp`. The link lands on the allocation, where the lifetime query's
        path-independent rulings read it.

        Only unconditional writes join, and only into storage that outlives
        the frame -- which is shared storage, plus a write *through* a
        parameter (see `_escapes_the_frame`): a conditional escape is exactly
        the shape where the other path still leaks, and the query would have
        to stay silent about it. A write that does not start after the
        allocation is not an escape of *this* allocation -- a same-named
        local in an earlier turn of a loop is a different object with the
        same spelling.
        """
        # `self._points` and `self._annotations` accumulate across methods; the
        # escape of one method's local is only ever written by the same
        # method's code.
        owner_key = (span.kind, span.qualified_name, span.signature)
        writes = [
            point for point in self._points
            if point.event_type == "WRITE"
            and (point.owner_kind, point.owner_qualified_name, point.owner_signature)
            == owner_key
            and point.annotations.get("write_source")
            and point.annotations.get("unconditional") == "true"
            and _escapes_the_frame(point.annotations)
        ]
        if not writes:
            return
        for key, anns in self._annotations.items():
            if (
                key.event_type != "ALLOC"
                or (key.owner_kind, key.owner_qualified_name, key.owner_signature)
                != owner_key
                or anns.get("subject_storage") not in _FRAME_LOCAL_STORAGES
            ):
                continue
            name = anns.get("subject", "")
            if not name:
                continue
            alloc_start = self._hit_positions.get(key)
            if alloc_start is None:
                continue
            targets: list[str] = []
            line = 0
            for write in writes:
                if write.annotations["write_source"] != name or write.start_byte <= alloc_start[0]:
                    continue
                target = write.annotations.get("subject", "")
                if target and target not in targets:
                    targets.append(target)
                if line == 0 or write.start_line < line:
                    line = write.start_line
            if targets:
                anns["escaped_to"] = ";".join(targets)
                anns["escaped_to_line"] = str(line)

    def _annotate_aliases(self, span: Any) -> None:
        """Stamp the MAY_ALIAS candidates a bare copy creates (stage 5B).

        `q = p` and `q = &p` make the two names possible aliases for the rest
        of the method; `_access_point` records the copy itself as
        `alias_source` on the write. This pass propagates the fact to the
        ends that have events of their own: the write, and every later point
        of either root. The annotation is a candidate, never a fact edge --
        the matrix's MAY_ALIAS stays at candidate metadata, and the DFG's
        chain walk reads `alias_source` to know a def continues another
        name's chain.

        Position discipline, same reasoning as `_annotate_escapes`: an event
        before the copy is not an access through the alias -- a same-named
        local in an earlier turn of a loop is a different object with the
        same spelling. Pairs where one side has no events record on the side
        that does; pairs where neither side has an event publish nothing,
        which is the registered residual, not a hidden one.
        """
        owner_key = (span.kind, span.qualified_name, span.signature)
        copies = [
            point for point in self._points
            if point.event_type == "WRITE"
            and (point.owner_kind, point.owner_qualified_name, point.owner_signature)
            == owner_key
            and point.annotations.get("alias_source")
        ]
        if not copies:
            return
        # Collected by point identity and written back onto the points
        # directly: mid-walk there are no ordinals yet (`_assign_ordinals`
        # runs after the walk), so `point.key()` would collapse every
        # same-type point onto one entry, and the point channel reaches
        # `cfg.annotations` only through that assignment. Hits (ALLOC,
        # RELEASE, CALL) stay untouched -- they publish through their own
        # vocabulary channel and read `alias_source`, not `alias`.
        alias_of: dict[int, set[str]] = {}
        for copy in copies:
            target = copy.annotations.get("subject", "")
            source = copy.annotations["alias_source"]
            start = copy.start_byte
            alias_of.setdefault(id(copy), set()).add(source)
            for point in self._points:
                if (
                    point.start_byte <= start
                    or (point.owner_kind, point.owner_qualified_name, point.owner_signature)
                    != owner_key
                ):
                    continue
                subject = point.annotations.get("subject", "")
                if subject == target:
                    alias_of.setdefault(id(point), set()).add(source)
                elif subject == source:
                    alias_of.setdefault(id(point), set()).add(target)
        for point in self._points:
            names = alias_of.get(id(point))
            if names:
                point.annotations["alias"] = ";".join(sorted(names))

    def _under_conditional_expression(self, node: Any) -> bool:
        """Whether the expression sits inside `&&`/`||` or a lambda body.

        The statement-level conditionals are the walker's own dispatch, which
        counts them in `_conditional_depth`. These two never reach that
        dispatch: a short-circuit's right operand runs only when the left
        allowed it, and a lambda body runs when the closure is called -- which
        is not a property of this method's paths at all.
        """
        while node is not None:
            node = node.parent
            if node is None:
                break
            if node.type == "lambda_expression":
                return True
            if node.type == "binary_expression" and _operator_of(
                node, self.source
            ) in self.profile.short_circuit_operators:
                return True
        return False

    def _assign_target_applies(self, node: Any) -> bool:
        """Whether the enclosing assignment still describes this expression.

        `auto compute = [&]() { ... lock.unlock(); };` walks the lambda body
        with `_assign_target` set to `compute`, so every call inside the body
        would be reported as acting on a name the body never mentions -- and
        `lock.unlock()` would release `compute`. A lambda body runs when the
        closure is called, which is not a property of this method's paths any
        more than `_under_conditional_expression`'s two cases are.

        The walk stops at the first enclosing assignment: one inside the body
        is the body's own and still applies, and only a lambda above that one
        makes the carried target foreign. A subtree with no enclosing
        assignment of either kind keeps the answer it has today, which is why
        this only ever narrows.
        """
        while node is not None:
            node = node.parent
            if node is None:
                return True
            if node.type in _ASSIGNMENT_NODES:
                return True
            if node.type == "lambda_expression":
                return False
        return True

    def _assign_ordinals(self) -> None:
        # Same rule as the event layer: source order, reproducible by reading
        # the file. CHECK/BRANCH/DEREFERENCE never come out of the vocabulary,
        # so these counters cannot collide with a hit's ordinals.
        ordered = sorted(self._points, key=lambda point: (point.start_byte, point.end_byte, point.seq))
        counters: dict[tuple[str, str, str, str], int] = {}
        for point in ordered:
            owner_key = (
                point.owner_kind,
                point.owner_qualified_name,
                point.owner_signature,
                point.event_type,
            )
            point.ordinal = counters.get(owner_key, 0)
            counters[owner_key] = point.ordinal + 1
            if point.annotations:
                self._annotations[point.key()] = point.annotations

    def _annotate_control_positions(self) -> None:
        """Serialize edgeless local facts' incoming control positions.

        Anchor identity is the same owner-local `(event_type, ordinal)` pair
        used by the published node. Flags are the exact flags that would ride
        on a threaded edge. No source line, spelling, or array position is a
        join key, and no READ/WRITE/DECLARATION endpoint enters existing CFG
        paths.
        """
        for point in self._points:
            incoming = point.control_incoming
            if incoming is None:
                continue
            predecessors = []
            entry = False
            seen = set()
            for open_edge in incoming:
                if open_edge.src is None:
                    entry = True
                    continue
                item = (
                    open_edge.src.event_type,
                    open_edge.src.ordinal,
                    tuple(sorted(open_edge.flags)),
                )
                if item not in seen:
                    seen.add(item)
                    predecessors.append(item)
            predecessors.sort()
            fact = {
                "status": (
                    "unknown" if point.local_coverage
                    else "reachable" if incoming else "unreachable"
                ),
                "entry": entry,
                "predecessors": [
                    {
                        "event_type": event_type,
                        "ordinal": ordinal,
                        "flags": list(flags),
                    }
                    for event_type, ordinal, flags in predecessors
                ],
                "coverage_status": "unknown" if point.local_coverage else "complete",
                "coverage_reasons": list(point.local_coverage or ()),
            }
            point.annotations[CONTROL_POSITION_KEY] = _facts_json(fact)
            self._annotations[point.key()] = point.annotations

    def _parsed_edges(self) -> list[ParsedEdge]:
        edges: list[ParsedEdge] = []
        seen: set[ParsedEdge] = set()
        for src, dst, flags in self._edges:
            edge = ParsedEdge(
                src=src.key(),
                dst=None if dst is _EXIT else dst.key(),
                flags=tuple(sorted(flags)),
            )
            if edge not in seen:
                seen.add(edge)
                edges.append(edge)
        # EXIT sorts after any real point for the same source; the order only
        # has to be total and stable, which (key, sentinel, flags) is.
        edges.sort(key=lambda edge: (edge.src, edge.dst if edge.dst is not None else _EXIT_SORT_KEY, edge.flags))
        return edges

    # ------------------------------------------------------------------
    # the walk

    def _linearize(
        self, node: Any, incoming: list[_Open]
    ) -> tuple["_Point | None", list[_Open]]:
        """Thread control through `node`; return (first point, open edges)."""
        if node is None:
            return None, list(incoming)
        span = self.owners.owner_of(node.start_byte, node.end_byte)
        if span is not None and span is not self._span:
            # Inside another symbol's span: that symbol's own walk covers it.
            # Lambda bodies carry no span and stay inlined here, which is the
            # event layer's attribution too.
            return None, list(incoming)
        if getattr(node, "has_error", False) or node.type == "ERROR":
            self._coverage_reasons.add("partial_parse")
        if node.type.startswith("preproc_") or "macro" in node.type:
            self._coverage_reasons.add("macro")
        if node.type in {"identifier", "type_identifier", "field_identifier"}:
            if self._text(node) in self._macro_names:
                self._coverage_reasons.add("macro")
        if node.type == "goto_statement":
            self._coverage_reasons.add("goto")
        if node.type in {"while_statement", "do_statement", "for_statement", "for_range_loop"}:
            self._coverage_reasons.add("unsupported_loop")
        if node.type in {"switch_statement", "conditional_expression"}:
            self._coverage_reasons.add("unsupported_conditional")
        if node.type == "lambda_expression":
            self._coverage_reasons.add("unsupported_lambda")
        if node.type in {"try_statement", "catch_clause", "throw_statement"}:
            self._coverage_reasons.add("unsupported_exception")
        self._unknown_address_of_in_call(node)
        self._unknown_pointer_argument(node)
        handler = _CONTROL_HANDLERS.get(node.type)
        if handler is not None or node.type in _CONDITIONAL_STATEMENTS:
            # The whole construct -- heading and arms -- walks one level
            # deeper. The heading counts too, deliberately: a write inside an
            # `if (c)` condition runs on the branch paths, not on every path,
            # and the escape facts would rather miss one than invent one. The
            # extra `_CONDITIONAL_STATEMENTS` are constructs the walker
            # linearizes as plain statements but whose bodies still run only
            # sometimes (a catch clause), so the CFG's fall-through must not
            # read as "always".
            self._conditional_depth += 1
            try:
                if handler is not None:
                    return getattr(self, handler)(node, incoming)
                return self._plain_generic(node, incoming)
            finally:
                self._conditional_depth -= 1
        return self._plain_generic(node, incoming)

    def _plain_generic(self, node: Any, incoming: list[_Open]) -> tuple["_Point | None", list[_Open]]:
        if node.type in _ASSIGNMENT_NODES:
            target_node = node.child_by_field_name("left")
            if target_node is None:
                target_node = node.child_by_field_name("declarator")
            target = self._root_identifier(target_node) if target_node is not None else ""
            saved = self._assign_target
            saved_exact = self._assign_exact
            # The inner assignment of `a = b = f()` wins while it is walked;
            # a failed extraction inherits the enclosing target, if any.
            self._assign_target = target or saved
            # `p = malloc(n)` binds the name `p`; `s->buf = malloc(n)` binds a
            # field of `s`, so the name recovered is the struct, not the
            # resource. The two are different identities and the queries say so.
            self._assign_exact = (
                _names_the_object(target_node) if target else saved_exact
            )
            saved_node = self._assign_node
            self._assign_node = target_node if target else saved_node
            try:
                return self._generic(node, incoming)
            finally:
                self._assign_target = saved
                self._assign_exact = saved_exact
                self._assign_node = saved_node
        return self._generic(node, incoming)

    def _generic(self, node: Any, incoming: list[_Open]) -> tuple["_Point | None", list[_Open]]:
        entry, current = self._children_linearize(node, incoming)
        # Post-order: this node's own points come after everything inside it.
        # One rule yields both "the condition's inner points precede the CHECK"
        # and "a call's arguments precede the CALL".
        return self._thread_own_points(node, entry, current)

    def _children_linearize(
        self, node: Any, incoming: list[_Open]
    ) -> tuple["_Point | None", list[_Open]]:
        entry: _Point | None = None
        current = list(incoming)
        for child in node.named_children:
            child_entry, current = self._linearize(child, current)
            if entry is None:
                entry = child_entry
        return entry, current

    def _connect(self, incoming: list[_Open], point: _Point) -> list[_Open]:
        for open_edge in incoming:
            if open_edge.src is not None:
                self._emit(open_edge.src, point, open_edge.flags)
        return [_Open(point, ())]

    def _emit(self, src: _Point | None, dst: Any, flags: tuple[str, ...]) -> None:
        if src is None or dst is None:
            # A malformed construct (an empty do-while body, say) must not
            # fabricate an edge to nowhere. `_EXIT`, not `None`, is the exit.
            return
        # The edgeless invariant, at the one function every edge goes through.
        # `_thread_own_points` already keeps the access layer off the chain, so
        # this cannot fire from source code -- only from an edit that routes an
        # access point somewhere else. It raises rather than dropping the edge
        # because a silent drop would leave a query reading a graph that is
        # quietly missing reachability, which is worse than a failed index.
        if src.event_type in _EDGELESS_EVENT_TYPES:
            raise RuntimeError(f"{src.event_type} point must not be an edge source")
        if dst is not _EXIT and dst.event_type in _EDGELESS_EVENT_TYPES:
            raise RuntimeError(f"{dst.event_type} point must not be an edge target")
        self._edges.append((src, dst, tuple(sorted(flags))))

    # ------------------------------------------------------------------
    # point construction

    def _own_points(self, node: Any) -> tuple[list[_Point], list[_Point]]:
        """The points this node itself contributes, in two sets.

        `threaded` is the control-flow chain: the vocabulary hits and the
        structural CHECK/BRANCH/DEREFERENCE points, exactly as before stage 5A.
        `event_only` is the access layer: READ/WRITE rows that are published
        and never connected. They are returned together rather than appended
        to `self._points` from two places because the *caller* is what decides
        whether a point is on the chain, and every caller must make the same
        decision -- see `_thread_own_points`.
        """
        threaded = [
            self._point_from_hit(hit, node)
            for hit in self._hits_by_span.get((node.start_byte, node.end_byte), ())
        ]
        # Matrix 2.1/2.2 (ARITH): the multiplication inside an allocation's size
        # argument. Emitted beside the ALLOC point it feeds, and only for an
        # ALLOC hit -- see `size_arithmetic` for why the population is bounded
        # this way.
        if any(point.event_type == "ALLOC" for point in threaded):
            threaded.extend(self._size_arithmetic_points(node))
        structural = self._structural_point(node)
        if structural is not None:
            threaded.append(structural)
        event_only = self._access_points(node)
        event_only.extend(self._local_declaration_points(node))
        return threaded, event_only

    def _thread_own_points(
        self, node: Any, entry: "_Point | None", current: list[_Open]
    ) -> tuple["_Point | None", list[_Open]]:
        """Connect this node's own points onto the chain, and nothing else.

        The one place `_own_points` is consumed, so the access layer's
        exclusion lives in one place. It has to cover the `entry` assignment
        and not just `_connect`: a point returned as `entry` becomes a jump
        target for the enclosing construct, so a READ returned as the entry of
        a `while` condition would collect the loop's back edge, the `continue`
        edges and the `do` statement's true arm -- real edges into an edgeless
        event type, which is the one thing this stage must not do.
        """
        threaded, event_only = self._own_points(node)
        for point in event_only:
            if point.event_type == DECLARATION or LOCAL_ACCESS_KEY in point.annotations:
                point.control_incoming = list(current)
        noreturn = False
        for point in threaded:
            if LOCAL_ACCESS_KEY in point.annotations:
                # DEREFERENCE remains threaded; retain the incoming position
                # before `_connect` replaces it with the dereference itself.
                point.control_incoming = list(current)
            current = self._connect(current, point)
            if entry is None:
                entry = point
            noreturn = noreturn or _never_returns(point)
        if noreturn:
            # Nothing after this call on this chain runs, so the chain stops
            # here. Same shape as `_throw_statement` and the same target, but
            # the edge is unflagged: `abort()` is not an exception, and only a
            # syntactic `throw` earns that flag.
            for open_edge in current:
                self._emit(open_edge.src, _EXIT, ())
            current = []
        return entry, current

    def _point_from_hit(self, hit: Any, node: Any) -> _Point:
        event = hit.event
        # No operation carries the variable it acts on in matched_name (`free`
        # is a keyword, not a subject), so the subject is recovered here and
        # rides to `graph.py` in `ParsedCfg.annotations`. Stage 3 annotated
        # ALLOC/RELEASE/CALL; stage 4 widened the set, because a lock-order or
        # race query without lock subjects and return subjects has nothing to
        # pair on.
        annotations = self._annotations_for_hit(event, node)
        if annotations:
            key = PointKey(
                event.owner_kind,
                event.owner_qualified_name,
                event.owner_signature,
                event.event_type,
                event.ordinal,
            )
            self._hit_positions[key] = (hit.start_byte, event.start_line)
            # Whole package, first writer wins. One span can carry two events
            # (`free(p)` is a CALL and a RELEASE), and merging key by key let the
            # second one fill in the gaps of the first -- a record whose subject
            # came from one event and whose declaration identity came from
            # another is a statement about no operation that ever ran. With the
            # two writers agreeing (they read the same node through the same
            # rules) the atomic rule costs nothing and cannot drift.
            self._annotations.setdefault(key, annotations)
        self._has_points = True
        return _Point(
            event_type=event.event_type,
            owner_kind=event.owner_kind,
            owner_qualified_name=event.owner_qualified_name,
            owner_signature=event.owner_signature,
            start_byte=hit.start_byte,
            end_byte=hit.end_byte,
            start_line=event.start_line,
            end_line=event.end_line,
            matched_name=event.matched_name,
            ordinal=event.ordinal,
            seq=0,
        )

    def _annotations_for_hit(self, event: Any, node: Any) -> dict[str, str]:
        """The subject-bearing annotations for one vocabulary hit.

        `raii` is recorded even when the subject is not: a RAII acquisition
        with an unidentifiable target is still known to release in its
        destructor, and that is exactly what keeps the incomplete-cleanup
        query (4.6) from reporting every `lock_guard` in the repository.
        """
        event_type = event.event_type
        if event_type not in _ANNOTATED_EVENT_TYPES:
            return {}
        annotations: dict[str, str] = {}
        if event_type in {"LOCK", "UNLOCK"} and node.type == "declaration":
            annotations["raii"] = "true"
        subject, subject_from, exact = self._subject_for_hit(
            event_type, event.matched_name, node
        )
        if subject:
            annotations["subject"] = subject
            annotations["subject_from"] = subject_from
            # Whether the name is the whole designation of the object or only
            # the root of a path that reaches it. `g_index_lock` names a lock;
            # `index` in `&index->slot_locks[i]` names the struct that holds
            # one, and two different elements of the array would otherwise look
            # like one lock acquired twice.
            annotations["subject_exact"] = "true" if exact else "false"
            annotations.update(self._subject_facts(
                self._subject_node(event_type, event.matched_name, node), subject
            ))
        elif event_type == "ALLOC" and node.type == "new_expression":
            # An anonymous heap object: it has no name, so there is no name to
            # resolve, but it does have an identity -- the allocation site. That
            # is what "this object" means for a value never bound to a variable,
            # and it is the fact that turns `new X(k)` from *identity unknown*
            # into *ownership unknown*: the two `new`s in a loop are the same
            # site and a different object from the two `new`s in another method.
            # Deterministic and line-free: the owner triple, the event type and
            # the ordinal within it -- the same inputs the event id hashes.
            annotations["subject_site"] = _site_token(event)
        if event_type == "ALLOC":
            # The two 5C-2 hand-off facts (2.4 and 2.12). An allocation that is
            # returned or passed as an argument *in its own acquiring
            # expression* leaves this frame at birth, and the leak walk cannot
            # see either: the RETURN point of `return new X(k)` has no subject
            # to join on, and the call that receives the allocation names its
            # own parameters. The annotation is the join.
            passed_to, returned = self._alloc_handoff(node)
            if passed_to:
                annotations["passed_to"] = passed_to
            if returned:
                annotations["returned"] = "true"
            extent = _alloc_extent_facts(node, event.matched_name, self.source)
            # A CALL argument is not the object returned by an allocator. Keep
            # the legacy subject annotations untouched, but never copy the `n`
            # in an unbound `malloc(n)` into the new allocation-object fact.
            extent["object"] = _allocation_object_fact(
                annotations,
                node,
                out_argument_is_direct=self._allocation_out_argument_is_direct(node),
                allow_comma=self.profile.name != "cpp",
                assignment_target_is_pointer=self._allocation_assignment_target_is_pointer,
                cpp=self.profile.name == "cpp",
            )
            annotations[BUFFER_EXTENT_KEY] = _facts_json(extent)
        elif event_type == "CALL":
            access = _memory_call_facts(node, event.matched_name, self.source)
            if access is not None:
                object_fact = self._memory_call_object_fact(node)
                access["object"] = object_fact
                annotations[MEMORY_ACCESS_KEY] = _facts_json(access)
                extent = self._memory_call_buffer_extent_fact(node, object_fact)
                if extent is not None:
                    annotations[BUFFER_EXTENT_KEY] = _facts_json(extent)
        arguments = _call_arguments(node, self.source)
        if arguments:
            annotations["arguments"] = arguments
        thread_function = self._thread_function(event_type, event.matched_name, node)
        if thread_function:
            annotations["thread_function"] = thread_function
        annotations.update(self._thread_argument_facts(event_type, event.matched_name, node))
        return annotations

    def _direct_builtin_address_of(self, identity: Any) -> bool:
        """Whether `identity` is built-in `&` of a directly nameable target."""
        if identity is None or identity.type != "pointer_expression" or (
            _operator_of(identity, self.source) != "&"
        ):
            return False
        target = _unwrap_parentheses(identity.child_by_field_name("argument"))
        if self.profile.name == "cpp":
            # A class/enum may overload unary `&`. Without a class/member type
            # resolver, only a declared builtin scalar, pointer, or direct array
            # is sufficient evidence that this is the built-in address operator.
            if target is None or target.type != "identifier":
                return False
            declaration = self._resolve_extent_declaration(
                target, _text_of(self.source, target)
            )
            if declaration is None:
                return False
            key = (declaration.start_byte, declaration.name)
            return (
                declaration.is_pointer
                or key in self._array_declaration_keys
                or declaration.type_token in _CPP_BUILTIN_ADDRESS_OF_TYPES
            )
        while target is not None and target.type == "field_expression":
            target = _unwrap_parentheses(target.child_by_field_name("argument"))
        return target is not None and target.type in {"identifier", "this"}

    def _allocation_out_argument_is_direct(self, node: Any) -> bool:
        argument = _unwrap_parentheses(_first_call_argument(node))
        while argument is not None and argument.type == "cast_expression":
            argument = _unwrap_parentheses(argument.child_by_field_name("value"))
        if not self._direct_builtin_address_of(argument):
            return False
        target = _unwrap_parentheses(argument.child_by_field_name("argument"))
        declaration = self._direct_value_declaration(target)
        return declaration is not None and declaration.is_pointer

    def _filter_cpp_value_access(
        self, access: dict[str, Any] | None, extent: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Do not claim builtin value access to a resolved C++ class element."""
        if self.profile.name != "cpp" or access is None or extent is None:
            return access
        object_type = extent.get("object", {}).get("type", "")
        if object_type and object_type not in _CPP_BUILTIN_ADDRESS_OF_TYPES:
            # Class elements may overload assignment or conversion operators.
            # Their declared extent remains valid, but V1 has no general C++
            # value-access semantics to attach to that element.
            return None
        return access

    def _memory_destination_argument(self, node: Any) -> tuple[Any, bool] | None:
        """Normalize the first argument once for destination identity and extent."""
        identity = _unwrap_parentheses(_first_call_argument(node))
        while identity is not None and identity.type == "cast_expression":
            identity = _unwrap_parentheses(identity.child_by_field_name("value"))
        addressed = False
        if identity is not None and identity.type == "pointer_expression" and (
            _operator_of(identity, self.source) == "&"
        ):
            if not self._direct_builtin_address_of(identity):
                return None
            identity = _unwrap_parentheses(identity.child_by_field_name("argument"))
            addressed = True
        return identity, addressed

    def _memory_call_object_fact(self, node: Any) -> dict[str, str]:
        """Resolve a memory API's destination argument, not its return target."""
        destination = self._memory_destination_argument(node)
        if destination is None:
            return _object_fact({})
        identity, addressed = destination
        if identity is None or identity.type not in {"identifier", "field_expression"}:
            return _object_fact({})
        if not addressed and not self._memory_value_preserves_identity(identity):
            # A value of class or builtin scalar type is not the address of its
            # source variable. In C++ it may involve a user-defined conversion;
            # even a C-style cast must not launder that identity back in.
            return _object_fact({})
        subject = self._root_identifier(identity)
        if not subject:
            return _object_fact({})
        return _object_fact(self._subject_facts(identity, subject))

    def _memory_call_buffer_extent_fact(
        self, node: Any, object_fact: Mapping[str, str]
    ) -> dict[str, Any] | None:
        """Resolve the same normalized destination through the array extent map."""
        destination = self._memory_destination_argument(node)
        if destination is None:
            return None
        identity, addressed = destination
        if identity is None or identity.type not in {"identifier", "field_expression"}:
            return None
        if not addressed and not self._memory_value_preserves_identity(identity) and (
            self._direct_value_declaration(identity) is not None
        ):
            return None
        return self._buffer_extent_facts(
            identity, object_fact=object_fact, direct_target=True
        )

    def _subject_node(self, event_type: str, matched_name: str, node: Any) -> Any:
        """The expression the subject name was recovered from.

        `_subject_for_hit` returns the name and not the node, because the name
        is what the query joins on; the declaration index needs the node as
        well, to know *where* the use is. The rules are the same ones
        `_subject_for_hit` applies, in the same order, and they must stay that
        way: a name read from one expression and a declaration looked up at
        another would be two different objects.
        """
        if event_type == "RELEASE":
            return self._release_argument_node(node)
        if event_type in {"LOCK", "UNLOCK"} and node.type == "declaration":
            return self._declaration_argument_node(node)
        if event_type == "RETURN":
            return self._return_value_node(node)
        if event_type == "THREAD_SPAWN" and node.type == "declaration":
            return self._declaration_target_node(node)
        argument = self._out_argument_node(event_type, matched_name, node)
        if argument is not None:
            return argument
        if self._assign_target and self._assign_target_applies(node):
            return self._assign_node
        if event_type == "ALLOC" and node.type == "new_expression":
            return None
        argument = _first_call_argument(node)
        if argument is not None:
            return argument
        if node.type == "call_expression":
            return self._call_receiver_node(node)
        return None

    def _subject_facts(self, node: Any, name: str) -> dict[str, str]:
        """The declaration identity behind a subject name (stage 4.5).

        A name is not an object. `int n` in one method and `int n` in another
        are two variables, `index->slot_locks[i]` and `index->global_lock` are
        two locks, and `g_total` is one variable however many files mention it.
        The stage 4 queries joined on the name, which is what made the race
        query return 557,315 candidates for redis -- every one of them a pair
        of same-named locals in different methods.

        What is recorded is deliberately a *token*, not a resolved object:
        storage class, declared type name, and the member path left over after
        the root identifier. The declaration index answers where the name comes
        from in this file, and answers nothing -- visibly -- when the file does
        not say. An empty `subject_decl` is that answer: the name may be a
        macro, an enum constant, or a global declared in a header this parser
        never sees, and the consumer falls back to the name rather than
        dropping the candidate.
        """
        if not name:
            return {}
        root, member, this_root, exact = self._member_chain(node)
        exact_value = "true" if exact else "false"
        if this_root:
            # `this->m_` is the whole designation: the object is the field, and
            # there is no path left over. The field declaration is looked up for
            # its type, but the identity is the member either way -- a local
            # that happens to share the name cannot be what `this->` means.
            declaration = self._resolve(node, member)
            if declaration is None:
                # Same 2.9 fallback as the bare-root path: `this->` in an
                # out-of-line body still names the class's field, and the
                # class comes from the method's qualified name.
                declaration = self._resolve_member(node, member)
                if declaration is not None and declaration.storage == STORAGE_FIELD:
                    return self._facts_for(declaration, "", exact_value)
            if declaration is None or declaration.storage != STORAGE_FIELD:
                class_name = self._enclosing_class(node)
                token = f"field:{class_name}:{member}" if class_name else ""
                if not token:
                    return {"subject_storage": STORAGE_UNKNOWN, "subject_member": "", "subject_exact": exact_value}
                return {
                    "subject_decl": token, "subject_storage": STORAGE_FIELD,
                    "subject_type": "", "subject_member": "", "subject_exact": exact_value,
                }
            return self._facts_for(declaration, "", exact_value)
        declaration = self._resolve(node, root)
        if declaration is None:
            # Out-of-line member function definitions (`void S::touch()`) sit
            # outside every scope `S` opens, so the plain resolve cannot see
            # the class's fields from their bodies. The method's qualified
            # name carries the class (`S.touch`), and the index can still
            # answer from the class frame -- the same token an in-class access
            # records, so both spellings join instead of splitting into
            # `field:S:m_` and `name:m_`. This is 5C-2's item 2.9, and it is
            # also why the unknown bucket widens: without it every bare member
            # of an out-of-line body lands here as `unknown`.
            declaration = self._resolve_member(node, root)
            if declaration is not None:
                return self._facts_for(declaration, member, exact_value)
            # No declaration in this file. `unknown` is a value, not a failure:
            # a cross-file global is the most important shared state a race
            # query can see, and a name with no declaration is exactly what it
            # looks like.
            return {
                "subject_storage": STORAGE_UNKNOWN,
                "subject_member": member, "subject_exact": exact_value,
            }
        if declaration.storage == STORAGE_FIELD and not member:
            # A bare field name inside a method (`m_.lock()`): the object is
            # the field, so the field *is* the designation.
            return self._facts_for(declaration, "", exact_value)
        return self._facts_for(declaration, member, exact_value)

    @staticmethod
    def _facts_for(declaration: Any, member: str, exact_value: str) -> dict[str, str]:
        if declaration.storage == STORAGE_FIELD:
            token = f"field:{declaration.scope_token}:{declaration.name}"
        elif declaration.scope_token:
            token = f"{declaration.storage}:{declaration.scope_token}:{declaration.name}"
        else:
            token = f"{declaration.storage}:{declaration.name}"
        facts = {
            "subject_decl": token,
            "subject_storage": declaration.storage,
            "subject_type": declaration.type_token,
            "subject_member": member,
            "subject_exact": exact_value,
        }
        # 5C-2's 2.6: when the declaration initializes from a call, the first
        # argument is the pure syntax fact a lock query joins a guard to its
        # mutex with. Recorded only when it exists, so every other subject's
        # facts stay byte-identical.
        init_arg0 = getattr(declaration, "init_arg0", "")
        if init_arg0:
            facts["subject_init_arg0"] = init_arg0
        return facts

    def _resolve(self, node: Any, name: str) -> Any:
        if self.declarations is None or not name:
            return None
        return self.declarations.resolve(node.start_byte, name)

    def _resolve_member(self, node: Any, name: str) -> Any:
        """The field `name` of the class the current method belongs to.

        Only an out-of-line definition needs this: inside the class body the
        plain resolve already walks the class frame. The method's qualified
        name spells the owner path with dots (`S.touch`), so the class is
        everything before the last dot -- a free function has none, and the
        fallback answers nothing for it.
        """
        if self.declarations is None or not name or self._span is None:
            return None
        qualified = self._span.qualified_name or ""
        if "." not in qualified:
            return None
        class_name = qualified.rsplit(".", 1)[0]
        return self.declarations.resolve_member(node.start_byte, class_name, name)

    def _enclosing_class(self, node: Any) -> str:
        if self.declarations is None:
            return ""
        return self.declarations.enclosing_class(node.start_byte)

    def _member_chain(self, node: Any) -> tuple[str, str, bool, bool]:
        """`(root identifier, member path, root is this, exact)` for a subject.

        `index->slot_locks[i]` is the root `index` with the path
        `slot_locks[i]` left over; `this->m_` is the field itself, and `m_`
        is the whole designation. The path is the member names and the
        subscript texts the descent passed, joined with whitespace removed, so
        `slot_locks[0]` and `slot_locks[1]` stay two identities -- collapsing
        them to the bare member name would report an array of locks as one
        lock acquired twice.

        The subscript text is spelled by the grammar and the two grammars
        differ: tree-sitter-cpp's `indices` is a node that carries the
        brackets (`[i]`), tree-sitter-c's `index` is the bare expression
        (`i`). So the same expression gives `slot_locks[i]` in C++ and
        `slot_locksi` in C. That is a spelling difference and not a split:
        an identity is only ever compared against another identity from the
        same repository, and the declaring file's language fixes the spelling
        on both sides of the comparison.

        Exactness is asked of the *whole* expression and not of the root the
        descent stopped on: `&index->slot_locks[i]` is inexact because it left a
        path behind, and the root `index` being a plain identifier says nothing
        about that. Asking the residual would call every member access exact.
        """
        whole = node
        pieces: list[str] = []
        while node is not None:
            kind = node.type
            if kind == "field_expression":
                pieces.insert(0, self._text(node.child_by_field_name("field")))
                node = node.child_by_field_name("argument")
                continue
            if kind == "subscript_expression":
                index_node = node.child_by_field_name("indices") or node.child_by_field_name("index")
                pieces.append(_path_text(self._text(index_node)))
                node = node.child_by_field_name("argument")
                continue
            if kind in {"pointer_expression", "parenthesized_expression"}:
                node = node.child_by_field_name("argument") or (
                    node.named_children[0] if node.named_children else None
                )
                continue
            if kind == "this":
                return "", "".join(pieces), True, True
            break
        root = self._root_identifier(node)
        return root, "".join(pieces), False, _names_the_object(whole)

    def _subject_for_hit(
        self, event_type: str, matched_name: str, node: Any
    ) -> tuple[str, str, bool]:
        """The name an operation acts on, how it was recovered, and whether it
        is the whole designation of the object or only the root of a path.

        The rules are ordered by how much the source actually says: a declared
        target is the thing being bound; a first argument is the thing being
        passed; a receiver is the object a member call is made on, which for
        `g_pool_lock.lock()` is the mutex but for `pool->lock()` is a struct
        that may merely contain one. Downstream keeps that difference, and the
        third element keeps a further one: `&g_index_lock` names the lock,
        `&index->slot_locks[i]` names the struct that holds an array of them.

        An unbound `new` is the one allocation with no name at all, and it is
        excluded from the argument rule rather than served by it: in
        `sink.emplace_back(new X(k))` the first argument `k` is a different
        object from the allocation, and the same for
        `return new X(params);`. Reporting one of them as the subject would
        attribute the candidate to something it is not and call the identity
        resolved; an anonymous heap object has no name, so the candidate is
        `unresolved` and the transfer to whatever consumes it is the missing
        fact (recorded in the stage 4 execution record).

        A write-through allocator is the second allocation that the argument
        rule would answer wrongly, and it is the rule's own subject: the
        first argument of `posix_memalign(&p, ...)` names `p`, while the
        assignment binds `rc` -- an error code, which is not a resource. So
        for the callees the vocabulary lists as `out_param` the rule runs
        before the assignment rule rather than after it.
        """
        if event_type == "RELEASE":
            value = self._release_argument_node(node)
            return self._root_identifier(value), SUBJECT_FROM_ARGUMENT, _names_the_object(value)
        if event_type in {"LOCK", "UNLOCK"} and node.type == "declaration":
            value = self._declaration_argument_node(node)
            return self._root_identifier(value), SUBJECT_FROM_RAII, _names_the_object(value)
        if event_type == "RETURN":
            value = self._return_value_node(node)
            return self._root_identifier(value), SUBJECT_FROM_RETURN, _names_the_object(value)
        if event_type == "THREAD_SPAWN" and node.type == "declaration":
            # A declaration binds a name to the handle, so the target is always
            # the whole designation.
            return self._declaration_target(node), SUBJECT_FROM_ASSIGNMENT, True
        if event_type == "THREAD_JOIN" and matched_name == "WaitForMultipleObjects":
            # The first argument is the handle *count*, not a handle; the handles
            # themselves are an array passed second, and a join against one
            # specific thread cannot be proved from it. Refuse to name a subject
            # rather than pairing the join against the count expression.
            return "", "", False
        argument = self._out_argument_node(event_type, matched_name, node)
        if argument is not None:
            return (
                self._root_identifier(argument), SUBJECT_FROM_OUT_ARGUMENT,
                _names_the_object(argument),
            )
        if self._assign_target and self._assign_target_applies(node):
            return self._assign_target, SUBJECT_FROM_ASSIGNMENT, self._assign_exact
        if event_type == "ALLOC" and node.type == "new_expression":
            return "", "", False
        argument = _first_call_argument(node)
        if argument is not None:
            return self._root_identifier(argument), SUBJECT_FROM_ARGUMENT, _names_the_object(argument)
        if node.type == "call_expression":
            name, _, exact = self._receiver_subject(node)
            return name, SUBJECT_FROM_RECEIVER, exact
        return "", "", False

    def _receiver_subject(self, node: Any) -> tuple[str, Any, bool]:
        """The object a member call is made on, as a name and as an expression.

        `g_pool_lock.lock()` names the mutex, `p->m.f()` names `p` with `m` left
        as the member path -- the root is what a declaration index can resolve.
        `this->m_.lock()` names the field `m_`, and it is the one case the root
        rule cannot reach: `this` is not a name but the method's own object, so
        the literal token would join every field of every class into a single
        identity. The field name is the designation instead, and the declaration
        index resolves it to the field it is.
        """
        receiver = self._call_receiver_node(node)
        if receiver is None:
            return "", None, False
        root, member, this_root, _ = self._member_chain(receiver)
        if this_root:
            return member, receiver, True
        return root, receiver, _names_the_object(receiver)

    def _return_value_node(self, node: Any) -> Any:
        # `return buffer;` hands the pointer to the caller; `return -1;` and
        # `return 0;` name nothing. Only the first is a transfer, and the
        # difference is the whole reason the return subject is recorded.
        if node.type != "return_statement" or not node.named_children:
            return None
        return node.named_children[0]

    def _call_receiver_node(self, node: Any) -> Any:
        callee = node.child_by_field_name("function")
        if callee is None or callee.type != "field_expression":
            return None
        return callee.child_by_field_name("argument")

    def _declaration_target(self, node: Any) -> str:
        """The name a declaration binds: `std::thread t{fn};` names `t`."""
        return self._root_identifier(self._declaration_target_node(node))

    def _declaration_target_node(self, node: Any) -> Any:
        """The declarator a declaration binds, or None when identity is unclear.

        Both spellings reach here. `t{fn}` is an `init_declarator`; `t(fn)` is a
        `function_declarator` left by the most-vexing-parse, and the name it
        binds sits in the same `declarator` field either way -- the difference
        is entirely in what follows it. The node comes back rather than the name
        because the declaration index resolves a name at a position, and the
        position is the declarator's, not the whole statement's.
        """
        declarator = self._single_declarator(node)
        if declarator is None or declarator.type not in {"init_declarator", "function_declarator"}:
            return None
        return declarator.child_by_field_name("declarator")

    def _declaration_argument_node(self, node: Any) -> Any:
        """The expression a RAII declaration locks or binds, not its variable.

        `lock_guard<std::mutex> guard{g_pool_lock};` locks `g_pool_lock`; the
        name `guard` is a local handle whose identity is worthless to a
        lock-order query.

        Two shapes reach here, because tree-sitter reads the same statement two
        ways depending on what is inside the parentheses:

        - `guard{a}`, `guard(a)`, `guard(p->m)`, `guard(&a)` and `guard(f())`
          parse as an `init_declarator` whose value is an `initializer_list` or
          an `argument_list`, and the argument is that list's first element.
        - `guard(a)` where `a` is a bare name parses as a **function
          declaration** (the most-vexing-parse): a `function_declarator` whose
          parameter list is really a constructor argument list. The argument is
          the parameter's `type` node, because there is nothing else -- the
          parser has already committed to reading `a` as a type name.

        What is deliberately *not* read: a parameter that carries its own
        declarator is a function type, which means the argument was a call
        (`guard(get_mutex())`, `guard(std::move(m))`). The object being locked
        is then whatever that call returns, which this layer cannot name, so the
        subject stays empty and the candidate is capped at `ambiguous` rather
        than attributed to the callee's name.
        """
        declarator = self._single_declarator(node)
        if declarator is None:
            return None
        if declarator.type == "function_declarator":
            return self._mmp_argument_node(declarator)
        if declarator.type != "init_declarator":
            return None
        value = declarator.child_by_field_name("value")
        if value is None:
            return None
        if value.type in {"initializer_list", "argument_list"}:
            value = value.named_children[0] if value.named_children else None
        return value

    def _mmp_argument_node(self, declarator: Any) -> Any:
        """The argument of a most-vexing-parse declaration, or None.

        The first parameter that is not a function type is the constructor's
        first argument: `guard(m)` names `m`, and `lk(m, std::defer_lock)` --
        the canonical way to spell a deferred `unique_lock` -- names `m` as
        well, with `std::defer_lock` reading as a second parameter declaration.
        A parameter that has a declarator of its own is a call, not an object,
        and stops the read.
        """
        parameters = declarator.child_by_field_name("parameters")
        if parameters is None:
            return None
        for parameter in parameters.named_children:
            if parameter.type != "parameter_declaration":
                return None
            if parameter.child_by_field_name("declarator") is not None:
                return None
            return parameter.child_by_field_name("type")
        return None

    def _declaration_argument(self, node: Any) -> str:
        return self._root_identifier(self._declaration_argument_node(node))

    def _single_declarator(self, node: Any) -> Any:
        """The declaration's one declarator, or None when identity is unclear.

        `lock_guard<std::mutex> a{m}, b{n};` acquires twice through two
        handles; reporting one argument for both would be a guess about which
        one a lock point refers to.
        """
        declarators = list(node.children_by_field_name("declarator"))
        if len(declarators) != 1:
            return None
        return declarators[0]

    def _thread_function(self, event_type: str, matched_name: str, node: Any) -> str:
        """The function a spawn starts, when the call shape says where it is."""
        if event_type != "THREAD_SPAWN":
            return ""
        if node.type == "declaration":
            return self._declaration_argument(node)
        if matched_name in _THREAD_QUALIFIED_SPAWNS:
            index = 0
        else:
            index = _THREAD_ENTRY_ARGUMENT.get(matched_name)
        if index is None:
            return ""
        arguments = node.child_by_field_name("arguments")
        named = list(arguments.named_children) if arguments is not None else []
        if index >= len(named):
            return ""
        return self._root_identifier(named[index])

    def _thread_argument_facts(self, event_type: str, matched_name: str, node: Any) -> dict[str, str]:
        """Candidate-level address-passed facts for `pthread_create`'s 4th arg.

        Gate A1 (throwaway integration spike, NOT a shipped feature): verifies
        that the real THREAD_SPAWN path can extract a deterministic,
        scope-qualified address-passed fact for the object handed to the new
        thread.

        Contracts enforced here:

        * `thread_argument_form` records the *syntax* only: `address_of` is
          must-eligible for a query-time consumer, `pointer_var`/`deref` are
          may-only (never must), `opaque`/`empty` prove nothing.
        * `thread_argument_decl` reuses the existing scope-qualified identity
          (`_subject_facts` -> `subject_decl`, storage class + scope + name); an
          unresolvable declaration stays empty (= unknown), never a guessed token.
        * purely additive next to the existing THREAD_SPAWN annotations; no
          POINTS_TO/ALIASES relation, no StorageObject redesign, no confidence
          change.
        """
        if event_type != "THREAD_SPAWN" or matched_name != "pthread_create":
            return {}
        arguments = node.child_by_field_name("arguments")
        named = list(arguments.named_children) if arguments is not None else []
        if len(named) < 4:
            return {}
        arg = named[3]
        form = _thread_argument_form(arg, self.source)
        root = self._root_identifier(arg)
        if not root:
            return {
                "thread_argument": "",
                "thread_argument_decl": "",
                "thread_argument_decl_scoped": "",
                "thread_argument_form": form,
            }
        facts = self._subject_facts(arg, root)
        decl = facts.get("subject_decl", "")
        member = facts.get("subject_member", "")
        if decl and member:
            decl = f"{decl}.{member}"
        scoped = self._scoped_decl_token(arg, root)
        return {
            "thread_argument": root,
            "thread_argument_decl": decl,
            "thread_argument_decl_scoped": scoped,
            "thread_argument_form": form,
        }

    def _scoped_decl_token(self, node: Any, root: str) -> str:
        """The A1B scope-qualified declaration token for a spawn argument.

        Mirrors ``_subject_facts``' resolution (bare root, then the out-of-line
        member fallback) but asks the declaration index for the *scoped* token
        instead of the public frame-blind ``subject_decl``. Empty (= unknown)
        whenever the file does not resolve the name, never a guessed token. The
        member path is appended the same way ``thread_argument_decl`` appends
        it, so ``&s.a`` stays distinguished from ``&s.b``.
        """
        if self.declarations is None or not root:
            return ""
        declaration = self._resolve(node, root)
        if declaration is None:
            declaration = self._resolve_member(node, root)
        if declaration is None:
            return ""
        token = self.declarations.scoped_identity(declaration)
        if not token:
            return ""
        _, member, _, _ = self._member_chain(node)
        if member:
            token = f"{token}.{member}"
        return token

    def _structural_point(self, node: Any) -> _Point | None:
        kind = node.type
        if kind not in self.profile.deref_node_types:
            return None
        if kind == "pointer_expression":
            if _operator_of(node, self.source) not in self.profile.deref_unary_operators:
                return None
        elif kind == "field_expression":
            if _operator_of(node, self.source) not in self.profile.deref_member_operators:
                return None
        return self._deref_point(node)

    def _deref_point(self, node: Any) -> _Point:
        operand = self._deref_operand(node)
        subject = self._root_identifier(operand)
        text = self._text(node)
        annotations = {"expression": text}
        if subject:
            annotations["subject"] = subject
            # The structural points carry subjects too, and they are not a
            # minority: nearly half the race query's subjects arrive through
            # `p[i]` and `if (!p)` rather than through a vocabulary hit. Leaving
            # the identity keys off here would send that half back to the
            # name-based join, and the stage's reduction would be half of what
            # the declaration index actually buys.
            annotations.update(self._subject_facts(operand, subject))
            if annotations.get("subject_storage") in {STORAGE_LOCAL, STORAGE_FUNCTION_STATIC}:
                declaration, scoped = self._local_declaration_identity(operand, subject)
                supported = bool(scoped) and declaration is not None and declaration.is_pointer
                annotations[LOCAL_ACCESS_KEY] = _facts_json({
                    "declaration": scoped,
                    "direction": "DEREFERENCE",
                    "target": "pointer",
                    "status": "supported" if supported else "unsupported",
                    "limitation": "" if supported else "only a resolved local pointer dereference is supported",
                })
                if not scoped:
                    self._coverage_reasons.add("unresolved_declaration")
        extent = self._buffer_extent_facts(node, annotations)
        if extent is not None:
            annotations[BUFFER_EXTENT_KEY] = _facts_json(extent)
        access = _access_facts(
            node,
            "DEREFERENCE",
            self.source,
            commuted=self._commuted_subscript(node),
            pointer_commuted=self._commuted_pointer_addition(node),
            cpp=self.profile.name == "cpp",
        )
        access = self._filter_cpp_value_access(access, extent)
        if access is not None:
            access["object"] = (
                extent.get("object") if extent is not None else _object_fact(annotations)
            )
            annotations[MEMORY_ACCESS_KEY] = _facts_json(access)
        return self._new_point("DEREFERENCE", node, annotations=annotations, matched_name=text)

    def _deref_operand(self, node: Any) -> Any:
        # The subject of `p[i]` is `p`, the pointer being indexed -- the index
        # expression is not what dereferences. C++ names the index field
        # `indices`, C names it `index`; only the subject matters here.
        return node.child_by_field_name("argument")

    def _resolve_extent_declaration(self, node: Any, name: str) -> Any:
        """Resolve through V1's statement-scope overlay, innermost outward."""
        if self.declarations is None or not name:
            return None
        declaration = self.declarations.resolve(node.start_byte, name)
        ancestor = node.parent
        while ancestor is not None:
            names = self._statement_declaration_names.get(ancestor.start_byte)
            visible_from = names.get(name) if names is not None else None
            if visible_from is not None and node.start_byte >= visible_from:
                if declaration is None or not (
                    ancestor.start_byte <= declaration.start_byte < ancestor.end_byte
                ):
                    # An unindexed statement/capture declaration still shadows
                    # an outer array. A real declaration inside this overlay is
                    # nested more deeply and must retain its own identity.
                    return None
                break
            ancestor = ancestor.parent
        while declaration is not None:
            statement = self._statement_declaration_scopes.get(declaration.start_byte)
            if statement is None or statement.start_byte <= node.start_byte < statement.end_byte:
                return declaration
            # The index owns only compound scopes and therefore returns a stale
            # for/if/switch/while heading declaration after that statement. Ask
            # again immediately before it so an outer visible declaration can
            # still answer, instead of stopping at unknown after the first miss.
            declaration = self.declarations.resolve(declaration.start_byte - 1, name)
        return None

    def _member_declaration_in_type(self, definition: Any, member: str) -> Any:
        """Resolve a direct field inside one exact class/tag definition."""
        if self.declarations is None or definition is None:
            return None
        body = definition.child_by_field_name("body")
        if body is None:
            return None
        matches = []
        for field_node in body.named_children:
            if field_node.type != "field_declaration":
                continue
            for declarator in field_node.children_by_field_name("declarator"):
                if _declarator_name(self.source, declarator) != member:
                    continue
                declaration = self.declarations.resolve(field_node.start_byte, member)
                if (
                    declaration is not None
                    and declaration.storage == STORAGE_FIELD
                    and declaration.start_byte == field_node.start_byte
                    and declaration.name == member
                ):
                    matches.append(declaration)
        return matches[0] if len(matches) == 1 else None

    def _direct_this_member_declaration(self, node: Any, member: str) -> Any:
        """Resolve `this->member` only in a lexically enclosing class body."""
        ancestor = node.parent
        while ancestor is not None:
            if (
                ancestor.type in {"class_specifier", "struct_specifier", "union_specifier"}
                and ancestor.child_by_field_name("body") is not None
            ):
                return self._member_declaration_in_type(ancestor, member)
            ancestor = ancestor.parent
        # An out-of-line method has no enclosing class syntax. V1 does not use
        # the legacy shallow owner/name fallback as positive type evidence.
        return None

    def _value_type_definition(self, declaration: Any) -> Any:
        """The unique visible definition of an explicitly spelled class/tag.

        Plain/qualified C++ type identifiers and aliases are outside V1. For an
        elaborated `struct S` / `union S` spelling, one same-named definition in
        the whole file must be visible from the declaration and precede it. This
        deliberately rejects ambiguous namespace types and nested C tags rather
        than borrowing whichever same-named field DeclarationIndex finds last.
        """
        type_node = self._value_declaration_types.get(
            (declaration.start_byte, declaration.name)
        )
        if type_node is None or type_node.type not in {
            "class_specifier", "struct_specifier", "union_specifier",
        } or getattr(type_node, "has_error", False):
            return None
        name_node = type_node.child_by_field_name("name")
        if name_node is None or name_node.type != "type_identifier":
            return None
        if _text_of(self.source, name_node) != declaration.type_token:
            return None
        if type_node.child_by_field_name("body") is not None:
            # A definition in the object declaration itself is exact regardless
            # of unrelated same-named types elsewhere in the file.
            return type_node
        if self.profile.name == "cpp" and declaration.type_token in self._value_type_aliases:
            return None

        definitions = []
        for candidate in self._value_type_definitions:
            candidate_name = candidate.child_by_field_name("name")
            if candidate_name is None or candidate_name.type != "type_identifier":
                continue
            if _text_of(self.source, candidate_name) != declaration.type_token:
                continue
            same_kind = candidate.type == type_node.type or (
                self.profile.name == "cpp"
                and {candidate.type, type_node.type} <= {
                    "class_specifier", "struct_specifier",
                }
            )
            if same_kind:
                definitions.append(candidate)
        if len(definitions) != 1:
            return None
        definition = definitions[0]
        if (
            getattr(definition, "has_error", False)
            or definition.start_byte >= declaration.start_byte
        ):
            return None

        scope_types = {
            "compound_statement", "function_definition", "namespace_definition",
            "class_specifier", "struct_specifier", "union_specifier",
            "translation_unit",
        }
        scope = definition.parent
        while scope is not None and scope.type not in scope_types:
            scope = scope.parent
        if scope is None:
            return None
        ancestor = type_node.parent
        while ancestor is not None:
            if ancestor.type == scope.type and _span(ancestor) == _span(scope):
                return definition
            ancestor = ancestor.parent
        return None

    def _direct_member_declaration(
        self, root_declaration: Any, member: str, operator: str
    ) -> Any:
        # `->` on a C++ class-like value may invoke overloaded operator->. A
        # resolved raw pointer retains built-in member access in both languages.
        if operator not in {".", "->"}:
            return None
        if operator == "->" and not root_declaration.is_pointer:
            return None
        definition = self._value_type_definition(root_declaration)
        return self._member_declaration_in_type(definition, member)

    def _direct_value_declaration(self, node: Any) -> Any:
        """Declaration for a direct identifier or one-level member value.

        This is V1's small amount of type evidence, not a general type resolver.
        Member evidence comes from exact syntax and a unique visible type; the
        shallow type_token / resolve_member lookup is never sufficient here.
        """
        node = _unwrap_parentheses(node)
        if node is None:
            return None
        if node.type == "identifier":
            name = _text_of(self.source, node)
            return self._resolve_extent_declaration(node, name)
        if node.type != "field_expression":
            return None
        root, member, this_root, _exact = self._member_chain(node)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", member or ""):
            return None
        argument = _unwrap_parentheses(node.child_by_field_name("argument"))
        if this_root:
            if argument is None or argument.type != "this":
                return None
            return self._direct_this_member_declaration(node, member)
        if (
            argument is None
            or argument.type != "identifier"
            or _text_of(self.source, argument) != root
        ):
            # Computed/dereferenced/nested roots do not preserve the shallow
            # root Declaration's type, especially under C++ operator overloads.
            return None
        root_declaration = self._resolve_extent_declaration(node, root)
        if root_declaration is None or not root_declaration.type_token:
            return None
        return self._direct_member_declaration(
            root_declaration,
            member,
            _operator_of(node, self.source),
        )

    def _cpp_builtin_integral_expression(self, node: Any) -> bool:
        """Whether C++ overload resolution cannot replace integral operators.

        V1 does not infer class conversions. Numeric/character/boolean literals,
        sizeof/alignof, declared builtin integral values, and operators whose
        operands all satisfy the same rule are sufficient. Everything else is
        deliberately unknown, even when a compiler could accept it.
        """
        node = _unwrap_parentheses(node)
        if node is None:
            return False
        if node.type in {
            "number_literal", "char_literal", "true", "false",
            "sizeof_expression", "alignof_expression",
        }:
            return True
        if node.type in {"identifier", "field_expression"}:
            declaration = self._direct_value_declaration(node)
            if declaration is None or declaration.is_pointer:
                return False
            key = (declaration.start_byte, declaration.name)
            return (
                key not in self._array_declaration_keys
                and declaration.type_token in _CPP_BUILTIN_SUBSCRIPT_TYPES
            )
        if node.type == "unary_expression":
            return self._cpp_builtin_integral_expression(
                node.child_by_field_name("argument")
            )
        if node.type == "binary_expression":
            return self._cpp_builtin_integral_expression(
                node.child_by_field_name("left")
            ) and self._cpp_builtin_integral_expression(
                node.child_by_field_name("right")
            )
        if node.type == "conditional_expression":
            # The condition affects only which already-integral arm is selected;
            # it cannot turn the outer subscript into an overloaded operator.
            return self._cpp_builtin_integral_expression(
                node.child_by_field_name("consequence")
            ) and self._cpp_builtin_integral_expression(
                node.child_by_field_name("alternative")
            )
        return False

    def _cpp_subscript_operand_kind(self, node: Any) -> str:
        if self._cpp_builtin_integral_expression(node):
            return "integral"
        declaration = self._direct_value_declaration(node)
        if declaration is None:
            return "unknown"
        key = (declaration.start_byte, declaration.name)
        if key in self._array_declaration_keys:
            return "array"
        if declaration.is_pointer:
            return "pointer"
        return "other"

    def _allocation_assignment_target_is_pointer(self, parent: Any) -> bool:
        """Whether plain assignment/initialization stores into a pointer.

        A C++ class LHS may overload `operator=` or converting-initialize from
        `void *`; neither stores the allocation as that class object's buffer.
        Restricting both languages to a resolved pointer also excludes numeric
        handles produced by an integer cast.
        """
        field = "left" if parent.type == "assignment_expression" else "declarator"
        target = _unwrap_parentheses(parent.child_by_field_name(field))
        if parent.type == "init_declarator":
            name = _declarator_name(self.source, target)
            declaration = self._resolve_extent_declaration(parent, name)
        else:
            declaration = self._direct_value_declaration(target)
        return declaration is not None and declaration.is_pointer

    def _memory_value_preserves_identity(self, identity: Any) -> bool:
        """Whether a destination value is a pointer/array for the named object."""
        declaration = self._direct_value_declaration(identity)
        if declaration is None:
            return False
        key = (declaration.start_byte, declaration.name)
        return declaration.is_pointer or key in self._array_declaration_keys

    def _commuted_subscript(self, expr: Any) -> bool | None:
        """True for proven `index[array]`, False for ordinary subscripting.

        None means V1 cannot prove the accessed target. C++ additionally needs
        builtin operand/operator evidence: class-like operands may invoke
        `operator[]` or overload the `+` hidden inside subscript semantics.
        """
        if expr.type != "subscript_expression":
            return False
        argument = _unwrap_parentheses(expr.child_by_field_name("argument"))
        index = _unwrap_parentheses(_subscript_index_node(expr))
        if argument is None or index is None:
            return None if self.profile.name == "cpp" else False
        if self.profile.name == "cpp":
            argument_kind = self._cpp_subscript_operand_kind(argument)
            index_kind = self._cpp_subscript_operand_kind(index)
            if argument_kind in {"array", "pointer"} and index_kind == "integral":
                return False
            if argument_kind == "integral" and index_kind == "array":
                # Keep V1's direct-array target boundary. A pointer on the right
                # remains unknown rather than widening commuted normalization.
                return True
            return None
        if argument.type == "number_literal":
            return True
        if argument.type != "identifier":
            return False
        argument_name = _text_of(self.source, argument)
        argument_declaration = self._resolve_extent_declaration(argument, argument_name)
        argument_is_array = (
            (argument_declaration.start_byte, argument_declaration.name)
            in self._array_declaration_keys
            if argument_declaration is not None else False
        )
        if index.type == "identifier":
            index_name = _text_of(self.source, index)
            index_declaration = self._resolve_extent_declaration(index, index_name)
            index_is_array = (
                (index_declaration.start_byte, index_declaration.name)
                in self._array_declaration_keys
                if index_declaration is not None else False
            )
            if index_is_array and not argument_is_array:
                return True
            if (
                argument_declaration is not None
                and not argument_declaration.is_pointer
                and not argument_is_array
            ):
                return None
            return False
        if (
            index.type != "number_literal"
            and argument_declaration is not None
            and not argument_declaration.is_pointer
            and not argument_is_array
        ):
            return None
        return False

    def _commuted_pointer_addition(self, expr: Any) -> bool | None:
        """Orientation for unary `*(base + offset)`, or None when ambiguous."""
        if expr.type != "pointer_expression" or _operator_of(expr, self.source) != "*":
            return False
        argument = _unwrap_parentheses(expr.child_by_field_name("argument"))
        if argument is None or argument.type != "binary_expression":
            return False
        operator = _operator_of(argument, self.source)
        if operator not in {"+", "-"}:
            return False
        left = _unwrap_parentheses(argument.child_by_field_name("left"))
        right = _unwrap_parentheses(argument.child_by_field_name("right"))
        if left is None or right is None:
            return None

        def declaration_and_array(node: Any) -> tuple[Any, bool]:
            if node.type != "identifier":
                return None, False
            declaration = self._resolve_extent_declaration(
                node, _text_of(self.source, node)
            )
            is_array = (
                (declaration.start_byte, declaration.name)
                in self._array_declaration_keys
                if declaration is not None else False
            )
            return declaration, is_array

        left_declaration, left_is_array = declaration_and_array(left)
        right_declaration, right_is_array = declaration_and_array(right)
        left_is_pointer = (
            left_declaration.is_pointer if left_declaration is not None else False
        )
        right_is_pointer = (
            right_declaration.is_pointer if right_declaration is not None else False
        )

        if self.profile.name == "cpp":
            if left_is_array or left_is_pointer:
                # Built-in pointer arithmetic also requires a builtin integral
                # offset; a class/enum right operand could overload + or -.
                return False if self._cpp_builtin_integral_expression(right) else None
            if operator == "-":
                return None
            if self._cpp_builtin_integral_expression(left):
                return True if right_is_array or right_is_pointer else None
            return None

        if operator == "-":
            return False
        if left.type == "number_literal":
            return True
        if left_is_array or left_is_pointer:
            return False
        if left_declaration is not None:
            # A known scalar on the left can only be the offset. Normalize only
            # a declared pointer/array right operand; otherwise fail closed.
            return True if right_is_array or right_is_pointer else None
        if right.type == "number_literal":
            return False
        return None

    def _buffer_extent_facts(
        self,
        expr: Any,
        annotations: Mapping[str, str] | None = None,
        *,
        object_fact: Mapping[str, str] | None = None,
        direct_target: bool = False,
    ) -> dict[str, Any] | None:
        """The declared or explicitly-unknown extent for a memory access.

        A local array access often has only a DEREFERENCE carrier (the access
        layer deliberately filters most local READ/WRITE points), so this fact
        is attached here as well as to access points. Resolved arrays join by
        the exact declaration returned by DeclarationIndex. Pointer/member
        shapes that V1 cannot resolve get an explicit source="unknown" fact;
        a plain non-array scalar access gets no buffer fact at all.
        """
        commuted = self._commuted_subscript(expr)
        pointer_commuted = self._commuted_pointer_addition(expr)
        inherited = (
            dict(object_fact) if object_fact is not None
            else _object_fact(annotations or {})
        )

        def unknown(limitation: str) -> dict[str, Any] | None:
            if expr.type not in {"subscript_expression", "pointer_expression"} and not (
                direct_target and expr.type in {"identifier", "field_expression"}
            ):
                return None
            return {
                "source": "unknown", "unit": "elements", "expression": None,
                "constant": None, "status": "unknown", "limitation": limitation,
                "bytes": {
                    "unit": "bytes", "expression": None, "constant": None,
                    "status": "unknown", "limitation": limitation,
                },
                "object": inherited,
            }

        if commuted is None:
            inherited = _object_fact({})
            return unknown("commuted subscript target is not modeled in V1")
        if pointer_commuted is None:
            inherited = _object_fact({})
            return unknown("commuted pointer arithmetic is not modeled in V1")
        base = _array_extent_base(
            expr, self.source, commuted=commuted, pointer_commuted=pointer_commuted
        )
        if base is None:
            return unknown("pointer target extent is unavailable")
        base = _unwrap_parentheses(base)
        if base is not None and base.type == "subscript_expression":
            return unknown("multidimensional subscripts are not modeled in V1")
        if base is None or base.type not in {"identifier", "field_expression"}:
            return unknown("cast or computed array bases are not modeled in V1")
        root, member, this_root, _exact = self._member_chain(base)
        if member:
            inherited["member"] = member
        # `s->buf[i]` requires a struct-type resolver that V1 does not have.
        # A bare field and `this->buf` are safe because DeclarationIndex can
        # resolve those fields directly; an arbitrary member path cannot borrow
        # the root object's extent.
        if member and not this_root:
            return unknown("member array extent resolution is not modeled in V1")
        name = member if this_root else root
        if this_root:
            declaration = self._direct_this_member_declaration(base, name)
        else:
            declaration = self._resolve_extent_declaration(base, name)
        if declaration is None:
            # Legacy subject facts intentionally retain the original shallow
            # fallback. V1 never turns that fallback into positive extent/type
            # evidence, especially for out-of-line methods with same-named types.
            inherited = _object_fact({})
            return unknown("pointer target declaration or extent is unavailable")
        extent = self._array_extents.get((declaration.start_byte, declaration.name))
        if extent is None:
            inherited = self._object_for_declaration(declaration)
            return unknown("pointer target is not a direct fixed-array declaration")
        fact = dict(extent)
        fact["object"] = self._object_for_declaration(declaration)
        return fact

    def _object_for_declaration(self, declaration: Any) -> dict[str, str]:
        """V1 object identity plus the declaration's scope-qualified token.

        The legacy `subject_decl` remains byte-identical (`local:a` for both an
        outer and an inner `a`). V1 additionally carries the already-available
        scoped identity so nested-block arrays do not collapse when a consumer
        joins their facts. No existing subject annotation is changed.
        """
        value = _object_fact(self._facts_for(declaration, "", "true"))
        if self.declarations is not None:
            scoped = self.declarations.scoped_identity(declaration)
            if scoped:
                value["scoped_decl"] = scoped
        return value

    # ------------------------------------------------------------------
    # the access layer (stage 5A)

    def _access_points(self, node: Any) -> list[_Point]:
        """The READ/WRITE accesses this node contributes (stage 5A).

        An access has no keyword. Nothing in `x = y` says which side is the
        write -- only position does -- so this cannot be a vocabulary matcher
        axis, and it lives here where the walker already computes the
        assignment target.

        Three rules; the third is what keeps the count honest:

        * **Write side.** This node is an assignment, a compound assignment, an
          update or an initializer: the object written is the outermost access
          expression inside its target field. `p->buf[i] = 5` writes one
          thing, not three.
        * **Read side.** Each named child that is itself an access expression
          is one read. The rule does not descend past it: `p->buf[i]`'s
          children are the same access spelled more finely, and the walker will
          reach them on its own (their DEREFERENCE points must not change).
        * **Skips.** A declarator names an object being declared, not one being
          read; a callee is what is invoked, not a variable. The write target
          is not read for a plain assignment, but *is* read for a
          read-modify-write (`x += y`, `x++`/`--x`): there the write consumes
          the written subject's own value, so both sides are published.

        Emission is filtered by storage class, and the filter is the identity
        rather than a heuristic -- see `ACCESS_STORAGES`. The subject comes
        from `_subject_facts` on the access *expression*, the same ruler every
        other event's identity is measured with, which is also what keeps the
        member path: `s->buf = malloc(n)` is `s#buf`, not `s`.
        """
        points: list[_Point] = []
        target = None
        target_field = WRITE_TARGET_FIELDS.get(node.type)
        if target_field is not None:
            target = node.child_by_field_name(target_field)
            written = _outermost_access(target, self.profile.access_node_types)
            if written is not None:
                point = self._access_point(written, "WRITE", origin=node)
                if point is not None:
                    points.append(point)
                if _is_read_modify_write(node):
                    # The read half of a read-modify-write: `x += y` and `x++`
                    # consume x's own value, so the same subject is read as well
                    # as written. This is what lets a concurrent pair of two
                    # updates on one shared object surface as an honest race
                    # (read+write, write+write) instead of a silent write-only.
                    read_point = self._access_point(written, "READ", origin=node)
                    if read_point is not None:
                        points.append(read_point)
        # F1 (SUB-09/R6): bounded indirect callee READs. In C, a field callee
        # reads a function-pointer slot. In both languages, a direct callee
        # resolved to a method-local pointer is also an ordinary local READ:
        # skipping every callee would otherwise make uninitialized `fp()` uses
        # invisible. Other callee shapes keep their existing DEREFERENCE/nested
        # expression handling rather than being guessed into a direct access.
        if node.type == "call_expression":
            callee = node.child_by_field_name("function")
            if (
                self.profile.name == "c"
                and callee is not None and callee.type == "field_expression"
            ):
                point = self._access_point(callee, "READ", indirect_callee=True)
                if point is not None:
                    points.append(point)
            if callee is not None and callee.type == "identifier":
                name = self._text(callee)
                declaration, _scoped = self._local_declaration_identity(callee, name)
                if declaration is not None and declaration.is_pointer:
                    point = self._access_point(callee, "READ", indirect_callee=True)
                    if point is not None:
                        points.append(point)
        skip_fields = (DECLARED_FIELDS.get(node.type), ACCESS_SKIP_FIELDS.get(node.type))
        skip = {
            _span(node.child_by_field_name(field))
            for field in skip_fields if field is not None
        }
        skip.discard(None)
        # This node is itself an access expression: its parent emits for it.
        # Emitting here too would count `p->buf[i]` three times over.
        if node.type in self.profile.access_node_types:
            return points
        for child in node.named_children:
            if child.type not in self.profile.access_node_types:
                continue
            if _span(child) in skip or _span(child) == _span(target):
                continue
            point = self._access_point(child, "READ")
            if point is not None:
                points.append(point)
        return points

    def _bare_alias_source(self, expr: Any, origin: Any, declared: bool = False) -> str:
        """The copied-from root for the bare copy shapes (`q = p`, `q = &p`).

        Empty for everything else: `q = p->f` reads a field and aliases
        nothing, and the LHS must be the bare root as well -- `*p = q` writes
        *through* `p`, it does not alias anything. Shared by the WRITE
        annotation block and the STORAGE_LOCAL bare-copy exception: the copy
        write is the alias fact carrier, the one local write the chain needs.
        `declared` marks an init_declarator LHS: there the `*` belongs to the
        type (`int *q = p` declares `q`), so the spelled text may carry the
        star and the written name is the root identifier itself.
        """
        rhs_field = WRITE_SOURCE_FIELDS.get(origin.type)
        rhs = origin.child_by_field_name(rhs_field) if rhs_field else None
        if rhs is None:
            return ""
        source_root = self._root_identifier(rhs)
        if not source_root:
            return ""
        rhs_text = self._text(rhs)
        lhs_root = self._root_identifier(expr)
        if (declared or self._text(expr) == lhs_root) and (
            rhs_text == source_root or rhs_text == f"&{source_root}"
        ):
            return source_root
        return ""

    def _declared_pointer(self, expr: Any, subject: str) -> bool:
        """Whether the subject's declaration binds a pointer type.

        Reads the `is_pointer` syntax fact the declaration index records from
        the declarator chain (a `pointer_declarator` wraps the name). False
        when the file declares nothing here or the resolution misses --
        conservative: no pointer claim without evidence, so a value copy can
        never be mistaken for a pointer alias.
        """
        declaration = self._resolve(expr, subject)
        if declaration is None:
            declaration = self._resolve_member(expr, subject)
        return declaration is not None and declaration.is_pointer

    def _is_null_literal(self, node: Any) -> bool:
        """A null node or the NULL/nullptr macro spelling."""
        return node is not None and (node.type == "null" or self._text(node) in ("NULL", "nullptr"))

    def _writes_null(self, origin: Any) -> bool:
        """Whether this write node's right-hand side is the null literal.

        Shared by the annotation block (which stamps `null_source`) and the
        STORAGE_LOCAL null-write exception -- a null write is a null-ness fact
        that must publish even for a frame-local name, or a re-nullification
        inside a guard becomes invisible to the null_flow query.
        """
        rhs_field = WRITE_SOURCE_FIELDS.get(origin.type)
        rhs = origin.child_by_field_name(rhs_field) if rhs_field else None
        return self._is_null_literal(rhs)

    def _is_declarator_name(self, expr: Any) -> bool:
        """Whether an identifier is the name being declared, not an initializer."""
        ancestor = expr.parent
        while ancestor is not None and ancestor.type != "declaration":
            if ancestor.type == "init_declarator":
                value = ancestor.child_by_field_name("value")
                if (
                    value is not None
                    and value.start_byte <= expr.start_byte < value.end_byte
                ):
                    return False
            ancestor = ancestor.parent
        if ancestor is None:
            return False
        return any(
            declarator.start_byte <= expr.start_byte < declarator.end_byte
            for declarator in ancestor.children_by_field_name("declarator")
        )

    def _access_point(
        self, expr: Any, event_type: str, origin: Any = None, indirect_callee: bool = False
    ) -> _Point | None:
        root, member, this_root, _exact = self._member_chain(expr)
        # `this->m_` names the field directly. Taking only `_root_identifier`
        # here would stop at `this` -- a keyword, not an identifier -- and the
        # whole access would be dropped, so the chain is the gate and the
        # subject is the member when the chain rooted on `this`.
        subject = member if this_root else root
        if not subject:
            return None
        facts = self._subject_facts(expr, subject)
        storage = facts.get("subject_storage")
        # The STORAGE_LOCAL bare-copy exception: the local writes the alias
        # chain needs are the pointer copies -- `int *q = p;` (declaration)
        # and `q = p;` (assignment, `q` declared pointer). The pointer fact
        # comes from the declaration index (a `pointer_declarator` in the
        # declarator chain), which covers both spellings where the declared
        # type token carries no pointer level and the routed identifier no
        # star. A value copy (`x = n`) and a pointer of unknown type stay
        # excluded -- conservative, no binding without evidence.
        bare_copy = (
            storage == STORAGE_LOCAL
            and event_type == "WRITE"
            and origin is not None
            and self._declared_pointer(expr, subject)
            and self._bare_alias_source(
                expr, origin, declared=(origin.type == "init_declarator")) != ""
        )
        # The STORAGE_LOCAL null-write exception: `p = NULL;` is a null-ness
        # fact regardless of storage -- without it a local re-nullification
        # inside a guard (`if (p) { p = NULL; *p; }`) is invisible and the
        # deref binds back to the stale allocation. A value write to a null
        # literal is the same fact for `int *p = NULL;` (declaration).
        null_write = (
            storage == STORAGE_LOCAL
            and event_type == "WRITE"
            and origin is not None
            and self._writes_null(origin)
        )
        legacy_local = bare_copy or null_write
        ordinary_local = storage == STORAGE_LOCAL and not legacy_local
        declarator_name = event_type == "READ" and self._is_declarator_name(expr)
        if ordinary_local and declarator_name:
            # A declarator's nested identifier is not a use. Initializer reads
            # are explicitly excluded by `_is_declarator_name` and remain.
            return None
        # Function-static declarator names retain their pre-existing legacy
        # READ, but must not acquire a V1 access: declaration is not a use.
        v1_storage = (
            not declarator_name
            and storage in {STORAGE_LOCAL, STORAGE_FUNCTION_STATIC}
        )
        declaration = None
        scoped = ""
        if v1_storage:
            declaration, scoped = self._local_declaration_identity(expr, subject)
            direct = expr.type == "identifier"
            if event_type == "WRITE" and not direct:
                self._coverage_reasons.add("unknown_write_through")
            key = (
                (declaration.start_byte, declaration.name)
                if declaration is not None else None
            )
            if key in self._reference_declaration_keys:
                self._coverage_reasons.add(
                    "unknown_write_through" if event_type == "WRITE"
                    else "unsupported_reference"
                )
            if ordinary_local and (
                not direct or not scoped or not self._supported_local_object(declaration)
            ):
                if not scoped:
                    self._coverage_reasons.add("unresolved_declaration")
                return None
        if storage not in ACCESS_STORAGES and not ordinary_local and not bare_copy and not null_write:
            return None
        if storage == STORAGE_PARAMETER and event_type != "WRITE":
            # Stage 5B publishes the write side of a parameter only. The
            # value arrives from the caller, so an in-frame read has no
            # consumer of its own; the query-time parameter join composes
            # the cross-method pairs from these writes in the caller's
            # terms. Registered approximation: a callee that only *reads*
            # through its parameter publishes nothing (see the plan's
            # registration list).
            return None
        text = self._text(expr)
        annotations = {"expression": text}
        if not ordinary_local:
            # New V1 automatic-local accesses deliberately do not enter the
            # legacy DFG subject channel. Their consumer joins
            # `local_access_v1` to the declaration fact; existing
            # bare-copy/null-write and function-static events retain every
            # legacy annotation and therefore their old DFG behavior.
            annotations["subject"] = subject
            annotations.update(facts)
        if v1_storage:
            direct = expr.type == "identifier"
            supported = (
                bool(scoped) and direct and self._supported_local_object(declaration)
            )
            annotations[LOCAL_ACCESS_KEY] = _facts_json({
                "declaration": scoped,
                "direction": event_type,
                "target": "direct" if direct else "indirect",
                "status": "supported" if supported else "unsupported",
                "limitation": "" if supported else "only direct resolved scalar/pointer objects are supported",
            })
        extent = None if ordinary_local else self._buffer_extent_facts(expr, annotations)
        if extent is not None:
            annotations[BUFFER_EXTENT_KEY] = _facts_json(extent)
        access = None if ordinary_local else _access_facts(
            expr, event_type, self.source, origin=origin,
            commuted=self._commuted_subscript(expr),
            pointer_commuted=self._commuted_pointer_addition(expr),
            cpp=self.profile.name == "cpp",
        )
        if access is not None:
            access = self._filter_cpp_value_access(access, extent)
        if access is not None:
            access["object"] = (
                extent.get("object") if extent is not None else _object_fact(annotations)
            )
            annotations[MEMORY_ACCESS_KEY] = _facts_json(access)
        # R1: first-class access kind, additive to the READ/WRITE event. The
        # write half of a read-modify-write (`x += y`, `x++`, `--x`) is the one
        # access that is both; a plain `x = x + 1` writes (WRITE) and reads
        # (READ) but never publishes a READ_MODIFY_WRITE kind. `event_type` is
        # left unchanged so existing event identity and packing are preserved.
        if event_type == "WRITE":
            annotations["is_write"] = "true"
            annotations["access_kind"] = (
                "READ_MODIFY_WRITE"
                if origin is not None and _is_read_modify_write(origin)
                else "WRITE"
            )
        else:
            annotations["is_write"] = "false"
            annotations["access_kind"] = "READ"
        if indirect_callee:
            # F1 (SUB-09/R6): the bounded indirect field-callee READ. `is_indirect`
            # marks the READ as a call-site function-pointer field dereference;
            # `field_path` is an additive, informative designation of the slot.
            # Neither is a join key -- the canonical slot stays (subject_decl,
            # subject_member), which is what the matching WRITE publishes too.
            annotations["is_indirect"] = "true"
            if root and member:
                annotations["field_path"] = f"{root}.{member}"
        if event_type == "WRITE" and origin is not None and not ordinary_local:
            # The escape half of 5C-2's 2.11: what the write *read*, and
            # whether the statement carrying it runs on every path of the
            # method. A later frame-local allocation whose pointer this write
            # copies into shared storage is then one post-pass away from an
            # escape fact on the allocation itself.
            rhs_field = WRITE_SOURCE_FIELDS.get(origin.type)
            rhs = origin.child_by_field_name(rhs_field) if rhs_field else None
            if rhs is not None:
                source_root = self._root_identifier(rhs)
                if source_root and source_root != subject:
                    annotations["write_source"] = source_root
                    # 5B's alias facts ride the write too, but only for the
                    # bare shapes: `q = p` and `q = &p` make the names
                    # possible aliases of one another, while `q = p->f` reads
                    # a field and aliases nothing. The LHS must be the bare
                    # root as well -- `*p = q` writes *through* `p`, it does
                    # not alias anything.
                    rhs_text = self._text(rhs)
                    if self._bare_alias_source(
                        expr, origin, declared=(origin.type == "init_declarator")
                    ) == source_root:
                        annotations["alias_source"] = source_root
                # The null half of the DFG's NULL_SOURCE class: a write whose
                # right-hand side is the null literal defines the subject as
                # null. Number literals (`p = 0`) stay unrecognized -- the
                # registered stage-4 approximation, not re-litigated here.
                if self._is_null_literal(rhs):
                    annotations["null_source"] = "true"
            annotations["unconditional"] = (
                "true" if self._conditional_depth == 0 and not self._under_conditional_expression(expr)
                else "false"
            )
        return self._new_point(event_type, expr, annotations=annotations, matched_name=text)

    def _condition_point(self, condition: Any) -> _Point:
        event_type, subject, polarity, subject_node = self._classify(condition)
        text = self._text(condition)
        annotations: dict[str, str] = {"expression": text}
        flags: tuple[str, ...] = ()
        if (
            condition.type == "binary_expression"
            and _operator_of(condition, self.source) in self.profile.short_circuit_operators
        ):
            flags = (SHORT_CIRCUIT,)
        if subject:
            annotations["subject"] = subject
            annotations.update(self._subject_facts(subject_node, subject))
        if polarity:
            annotations["polarity"] = polarity
        return self._new_point(event_type, condition, flags=flags, annotations=annotations, matched_name=text)

    def _classify(self, condition: Any) -> tuple[str, str, str, Any]:
        """CHECK for validity tests, BRANCH for everything else (v1 rule).

        A validity test is `!p`, or `p == NULL` / `p != NULL` with a `null`
        node on one side. Bare identifiers, comparisons against 0, calls and
        conjunctions are all plain branches -- picking more would need type
        information this stage deliberately does not use.

        The expression the subject was read from comes back with the name: the
        declaration index resolves a name *at a position*, and `!p->buf` and
        `!q->buf` share a name without sharing an object.
        """
        if condition.type == "unary_expression":
            if _operator_of(condition, self.source) == "!":
                argument = condition.child_by_field_name("argument")
                return "CHECK", self._root_identifier(argument), "true_when_null", argument
        if condition.type == "binary_expression":
            operator = _operator_of(condition, self.source)
            if operator in {"==", "!="}:
                left = condition.child_by_field_name("left")
                right = condition.child_by_field_name("right")
                null_side, other = (left, right) if self._is_null(left) else (right, left) if self._is_null(right) else (None, None)
                if null_side is not None:
                    polarity = "true_when_null" if operator == "==" else "true_when_non_null"
                    return "CHECK", self._root_identifier(other), polarity, other
            if operator == "&&":
                # A conjunction guards each pointer operand: the true arm
                # implies every operand non-null. `||` guards none (the true
                # arm can come from the other side). The pointer fact comes
                # from the declaration index -- a value operand (`flag`) or a
                # pointer of unknown type is never claimed as a guard.
                for operand in (condition.child_by_field_name("left"),
                                condition.child_by_field_name("right")):
                    name = self._root_identifier(operand)
                    if name and self._declared_pointer(operand, name):
                        return "CHECK", name, "true_when_non_null", operand
        name = self._root_identifier(condition)
        if condition.type in ("identifier", "field_identifier") and name and self._declared_pointer(condition, name):
            # `if (p)` reads as "p is non-null on the true arm": the same
            # guard `if (p != NULL)` spells, with the null arm on the false
            # branch. Recorded only for pointer declarations -- a bare int
            # condition is a branch, not a null test.
            return "CHECK", name, "true_when_non_null", condition
        return "BRANCH", "", "", None

    def _is_null(self, node: Any) -> bool:
        return node is not None and node.type in self.profile.null_node_types

    def _size_arithmetic_points(self, node: Any) -> list["_Point"]:
        """ARITH points for the multiplications inside this allocation's size.

        The subject is the first operand that is not a literal: the value that
        carries the runtime count. A product of two literals has no subject, is
        published with `constant=true`, and the query declines it -- a folded
        product cannot wrap at run time, and saying so out loud is more useful
        than omitting the point.
        """
        points: list[_Point] = []
        for record in size_arithmetic(node, self.source):
            subject = next(
                (item["text"] for item in record["operands"] if not item["literal"]), "")
            annotations = {
                "expression": record["expression"],
                "operator": record["operator"],
                "operands": ",".join(item["text"] for item in record["operands"]),
                "constant": "false" if subject else "true",
            }
            subject_node = next(
                (item["node"] for item in record["operands"] if not item["literal"]), None)
            if subject and subject_node is not None:
                annotations["subject"] = subject
                annotations.update(self._subject_facts(subject_node, subject))
            points.append(self._new_point(
                "ARITH", record["node"], annotations=annotations,
                matched_name=record["operator"]))
        return points

    def _new_point(
        self,
        event_type: str,
        node: Any,
        flags: tuple[str, ...] = (),
        annotations: dict[str, str] | None = None,
        matched_name: str = "",
    ) -> _Point:
        point = _Point(
            event_type=event_type,
            owner_kind=self._span.kind,
            owner_qualified_name=self._span.qualified_name,
            owner_signature=self._span.signature,
            start_byte=node.start_byte,
            end_byte=node.end_byte,
            start_line=self.line_of(node.start_byte, False),
            end_line=self.line_of(node.end_byte, True),
            matched_name=matched_name,
            flags=flags,
            annotations=dict(annotations or {}),
            seq=self._seq,
        )
        self._seq += 1
        self._points.append(point)
        self._has_points = True
        return point

    def _text(self, node: Any) -> str:
        return _expression_text(self.source, node)

    # ------------------------------------------------------------------
    # helpers over the current node

    def _root_identifier(self, node: Any) -> str:
        """The leftmost identifier of an expression: `p->buf[i]` names `p`."""
        return _root_identifier(self.source, node)

    def _release_argument_node(self, node: Any) -> Any:
        """The expression a release acts on: `free(p)` names `p`, and
        `delete p->buf` names the field's root, which `_names_the_object`
        reports as the path it is."""
        if node.type == "delete_expression":
            value = node.child_by_field_name("value")
            if value is None and node.named_children:
                value = node.named_children[-1]
            return value
        return _first_call_argument(node)

    def _out_argument_node(self, event_type: str, matched_name: str, node: Any) -> Any:
        """The expression a write-through allocator's first argument addresses.

        `posix_memalign(&p, align, size)` hands the allocation to `p`, so the
        subject is what the argument points at and not the expression the
        argument is. The `&` needs no unwrapping here: `_root_identifier` and
        `_member_chain` already treat a `pointer_expression` as transparent,
        so `&c->send_mem` names `c` with the path `send_mem` left over, which
        is the object and not the field's address. A cast does need it --
        `(void **)&c->send_mem` is the argument's *type*, and neither helper
        steps over a `cast_expression`, so without this the member path would
        be lost and every element of a struct would read as its root.

        Returns None when the callee is not one of the vocabulary's
        `out_param` names, or when the call has no first argument at all --
        the ordinary rules are the right answer for both, and the two callers
        fall through to them.
        """
        if event_type != "ALLOC" or matched_name.rpartition(".")[2] not in self._out_param:
            return None
        argument = _first_call_argument(node)
        while argument is not None and argument.type in {"cast_expression", "parenthesized_expression"}:
            if argument.type == "cast_expression":
                argument = argument.child_by_field_name("value")
            else:
                argument = argument.named_children[0] if argument.named_children else None
        return argument

    def _alloc_handoff(self, node: Any) -> tuple[str, bool]:
        """`(callee, returned)` for an allocation's own acquiring expression.

        The walk goes from the allocation's node to the *nearest* ancestor
        that says where the value goes: a `return_statement` means the caller
        receives it, and a call's `argument_list` means the callee is handed
        it. Nearest wins because the two are not the same hand-over --
        `return push(new X(k))` records `push`, since what happens past `push`
        is `push`'s contract, and this method's own return says nothing about
        the object itself. Anything else (`tmp = strdup(x)` bound to a local,
        an allocation in a loop heading) hands over nobody, and answers
        without a fact.
        """
        node = node.parent
        while node is not None:
            if node.type == "return_statement":
                return "", True
            if node.type == "argument_list":
                call = node.parent
                if call is not None and call.type == "call_expression":
                    callee = call.child_by_field_name("function")
                    if callee is not None:
                        return _expression_text(self.source, callee), False
                return "", False
            node = node.parent
        return "", False

    # ------------------------------------------------------------------
    # control handlers

    def _if_statement(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        condition = _unwrap_condition(node.child_by_field_name("condition"))
        if condition is None:
            return self._plain_generic(node, incoming)
        entry, cond_opens = self._linearize(condition, incoming)
        check = self._condition_point(condition)
        self._connect(cond_opens, check)
        _, true_opens = self._linearize(
            node.child_by_field_name("consequence"), [_Open(check, (BRANCH_TRUE,))]
        )
        alternative = node.child_by_field_name("alternative")
        if alternative is not None:
            # An else-if chain is a nested if_statement inside the else_clause;
            # recursing lands in this handler again. No special case needed.
            _, false_opens = self._linearize(alternative, [_Open(check, (BRANCH_FALSE,))])
        else:
            false_opens = [_Open(check, (BRANCH_FALSE,))]
        return entry or check, [*true_opens, *false_opens]

    def _while_statement(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        condition = _unwrap_condition(node.child_by_field_name("condition"))
        if condition is None:
            return self._plain_generic(node, incoming)
        entry, cond_opens = self._linearize(condition, incoming)
        check = self._condition_point(condition)
        self._connect(cond_opens, check)
        loop_entry = entry or check
        context = _LoopContext()
        self._breaks.append(context)
        try:
            _, body_opens = self._linearize(
                node.child_by_field_name("body"), [_Open(check, (BRANCH_TRUE,))]
            )
        finally:
            self._breaks.pop()
        # The back edge to the re-tested condition carries only `loop_back`:
        # the `branch=true` fact already lives on the check-to-body edge.
        self._flush_loop(context, loop_entry, body_opens, loop_entry)
        return loop_entry, [*context.breaks, _Open(check, (BRANCH_FALSE,))]

    def _flush_loop(
        self,
        context: _LoopContext,
        continue_target: _Point | None,
        back_opens: list[_Open],
        back_target: _Point | None,
    ) -> None:
        for open_edge in context.continues:
            self._emit(open_edge.src, continue_target, (*open_edge.flags, LOOP_BACK))
        for open_edge in back_opens:
            self._emit(open_edge.src, back_target, (*open_edge.flags, LOOP_BACK))

    def _do_statement(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        condition = _unwrap_condition(node.child_by_field_name("condition"))
        if condition is None:
            return self._plain_generic(node, incoming)
        context = _LoopContext()
        self._breaks.append(context)
        try:
            body_entry, body_opens = self._linearize(node.child_by_field_name("body"), incoming)
        finally:
            self._breaks.pop()
        cond_entry, cond_opens = self._linearize(condition, body_opens)
        check = self._condition_point(condition)
        self._connect(cond_opens, check)
        # The true arm IS the back edge here -- there is no separate
        # check-to-body edge, so both facts share the one edge. An empty body
        # loops straight back into the re-tested condition.
        self._emit(check, body_entry or cond_entry or check, (BRANCH_TRUE, LOOP_BACK))
        for open_edge in context.continues:
            self._emit(open_edge.src, cond_entry or check, (LOOP_BACK,))
        return body_entry, [*context.breaks, _Open(check, (BRANCH_FALSE,))]

    def _for_statement(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        init = node.child_by_field_name("initializer")
        if init is not None:
            _, incoming = self._linearize(init, incoming)
        condition = _unwrap_condition(node.child_by_field_name("condition"))
        update = node.child_by_field_name("update")
        check: _Point | None = None
        cond_entry: _Point | None = None
        body_incoming = incoming
        if condition is not None:
            cond_entry, cond_opens = self._linearize(condition, incoming)
            check = self._condition_point(condition)
            self._connect(cond_opens, check)
            body_incoming = [_Open(check, (BRANCH_TRUE,))]
        context = _LoopContext()
        self._breaks.append(context)
        try:
            body_entry, body_opens = self._linearize(node.child_by_field_name("body"), body_incoming)
        finally:
            self._breaks.pop()
        # C semantics: `continue` runs the update before re-testing.
        continue_target = cond_entry or check or body_entry
        back_opens = body_opens
        if update is not None:
            upd_entry, upd_opens = self._linearize(update, body_opens)
            continue_target = upd_entry or continue_target
            back_opens = upd_opens
        back_target = cond_entry or check or body_entry
        self._flush_loop(context, continue_target, back_opens, back_target)
        if check is None:
            # `for (;;)` has no condition to fail: only `break` leaves.
            return body_entry, list(context.breaks)
        return cond_entry or body_entry, [*context.breaks, _Open(check, (BRANCH_FALSE,))]

    def _for_range_loop(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        right = node.child_by_field_name("right")
        if right is None:
            return self._plain_generic(node, incoming)
        entry, cond_opens = self._linearize(right, incoming)
        check = self._condition_point(right)
        self._connect(cond_opens, check)
        loop_entry = entry or check
        context = _LoopContext()
        self._breaks.append(context)
        try:
            _, body_opens = self._linearize(
                node.child_by_field_name("body"), [_Open(check, (BRANCH_TRUE,))]
            )
        finally:
            self._breaks.pop()
        self._flush_loop(context, loop_entry, body_opens, loop_entry)
        return loop_entry, [*context.breaks, _Open(check, (BRANCH_FALSE,))]

    def _switch_statement(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        condition = _unwrap_condition(node.child_by_field_name("condition"))
        if condition is None:
            return self._plain_generic(node, incoming)
        entry, cond_opens = self._linearize(condition, incoming)
        check = self._condition_point(condition)
        self._connect(cond_opens, check)
        context = _SwitchContext(check=check)
        self._breaks.append(context)
        self._switches.append(context)
        pending: list[_Open] = []
        try:
            body = node.child_by_field_name("body")
            for child in body.named_children if body is not None else ():
                if child.type == "case_statement":
                    # Every label is an entry off the same check. The body
                    # threads linearly between labels, so the fallthrough into
                    # the next label is exactly the pending chain, flagged --
                    # keeping whatever arm the open arrived on, then marked.
                    fallthrough = [
                        _Open(open_edge.src, (*open_edge.flags, FALLTHROUGH))
                        for open_edge in pending
                    ]
                    _, pending = self._linearize(
                        child, [*fallthrough, _Open(check, _label_flags(child))]
                    )
                else:
                    _, pending = self._linearize(child, pending)
        finally:
            self._breaks.pop()
            self._switches.pop()
        opens = [*context.breaks, *pending]
        if not context.saw_default:
            opens.append(_Open(check, (BRANCH_FALSE,)))
        return entry or check, opens

    def _case_statement(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        switch = self._switches[-1] if self._switches else None
        if switch is None:
            return self._plain_generic(node, incoming)
        value = node.child_by_field_name("value")
        if value is None:
            switch.saw_default = True
        entry: _Point | None = None
        current = list(incoming)
        if value is not None:
            entry, current = self._linearize(value, current)
        for statement in node.named_children:
            if statement is value:
                continue
            if statement.type == "case_statement":
                # `case 1: case 2: ...` -- the nested label is another entry
                # off the same switch check.
                label = _Open(switch.check, _label_flags(statement))
                child_entry, current = self._linearize(statement, [*current, label])
            else:
                child_entry, current = self._linearize(statement, current)
            if entry is None:
                entry = child_entry
        return entry, current

    def _return_statement(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        entry, current = self._children_linearize(node, incoming)
        entry, current = self._thread_own_points(node, entry, current)
        # Control leaves the method: the chain ends at the synthetic exit.
        for open_edge in current:
            self._emit(open_edge.src, _EXIT, ())
        return entry, []

    def _throw_statement(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        entry, current = self._children_linearize(node, incoming)
        entry, current = self._thread_own_points(node, entry, current)
        for open_edge in current:
            self._emit(open_edge.src, _EXIT, (EXCEPTION,))
        if self._handlers and current:
            # Which catch clauses these edges land on is unknown until the
            # enclosing try has walked them; the flush happens there. A throw
            # binds to the innermost try -- picking among its handlers is the
            # source's business, not this walker's, so every handler gets an
            # edge and no handler is fabricated for `exit()`-style calls.
            self._pending_throws.append((current, self._handlers[-1]))
        return entry, []

    def _break_statement(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        # Outside every loop and switch the break is simply dropped -- bad code
        # must not crash the walk.
        if self._breaks:
            self._breaks[-1].breaks.extend(incoming)
        return None, []

    def _continue_statement(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        # `continue` binds to loops only; inside a bare switch it is dropped.
        if self._breaks and isinstance(self._breaks[-1], _LoopContext):
            self._breaks[-1].continues.extend(incoming)
        return None, []

    def _try_statement(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        context = _HandlerContext()
        self._handlers.append(context)
        try:
            body_entry, opens = self._linearize(node.child_by_field_name("body"), incoming)
        finally:
            self._handlers.pop()
        # Over-approximation: the body's normal completion continues past the
        # try even though a throw may have routed it into a handler instead.
        for child in node.named_children:
            if child.type not in {"catch_clause", "handler", "except_clause"}:
                continue
            # Nothing normal flows into a handler; the exception edges from the
            # body's throws are its only in-edges.
            catch_entry, catch_opens = self._linearize(child, [])
            if catch_entry is not None:
                context.entries.append(catch_entry)
            opens = [*opens, *catch_opens]
        self._flush_throws(context)
        return body_entry, opens

    def _flush_throws(self, context: _HandlerContext) -> None:
        remaining: list[tuple[list[_Open], _HandlerContext]] = []
        for opens, owner in self._pending_throws:
            if owner is not context:
                remaining.append((opens, owner))
                continue
            for open_edge in opens:
                for entry in context.entries:
                    self._emit(open_edge.src, entry, (EXCEPTION,))
        self._pending_throws = remaining

    def _goto_statement(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        # The jump target is not modelled; the chain simply ends. The resulting
        # incompleteness is a registered imprecision of stage 3.
        return None, []

    def _conditional_expression(self, node: Any, incoming: list[_Open]) -> tuple[_Point | None, list[_Open]]:
        children = node.named_children
        condition = node.child_by_field_name("condition")
        if condition is None or len(children) < 3:
            return self._plain_generic(node, incoming)
        consequence = node.child_by_field_name("consequence")
        alternative = node.child_by_field_name("alternative")
        if consequence is None:
            consequence = children[1]
        if alternative is None:
            alternative = children[-1]
        entry, cond_opens = self._linearize(condition, incoming)
        check = self._condition_point(condition)
        self._connect(cond_opens, check)
        _, true_opens = self._linearize(consequence, [_Open(check, (BRANCH_TRUE,))])
        _, false_opens = self._linearize(alternative, [_Open(check, (BRANCH_FALSE,))])
        return entry or check, [*true_opens, *false_opens]


# Joins the root identifiers of a call's arguments into one annotation value.
# A C identifier cannot contain it, so the encoding is unambiguous without a
# second storage column, and the annotation channel stays `dict[str, str]`.
ARGUMENT_SEPARATOR = "\x1f"

# `p->buf` descends through `argument`; `*buffer` and `(Foo *)p` too. Declarator
# kinds matter because `char *buffer = malloc(n)` names the target through a
# pointer_declarator, not an identifier.
_DESCEND_FIELDS = {
    "field_expression": "argument",
    "pointer_expression": "argument",
    "subscript_expression": "argument",
    "unary_expression": "argument",
    "update_expression": "argument",
    "cast_expression": "value",
    "pointer_declarator": "declarator",
    "array_declarator": "declarator",
    "reference_declarator": "declarator",
}


def _root_identifier(source: bytes, node: Any) -> str:
    """The leftmost identifier of an expression: `p->buf[i]` names `p`."""
    while node is not None:
        if node.type in {"identifier", "type_identifier"}:
            # `type_identifier` is a leaf name too, and it is what a
            # most-vexing-parse leaves behind where an expression would
            # otherwise be: `guard(m)` spells `m` as a type name.
            return _expression_text(source, node)
        if node.type == "parenthesized_expression":
            node = node.named_children[0] if node.named_children else None
            continue
        field_name = _DESCEND_FIELDS.get(node.type)
        node = node.child_by_field_name(field_name) if field_name else None
    return ""


def _path_text(text: str) -> str:
    """A member path with its whitespace removed, so it is an identity.

    `arr[i + 1]` and `arr[i+1]` are the same object, and an identity token that
    changes when someone reformats an expression is a token that splits one
    object into two candidates.
    """
    return "".join(text.split())


def _site_token(event: Any) -> str:
    """The identity of an allocation that binds no name.

    Same shape as `PointKey`, same reason: it must be computable at parse time,
    before the repository id exists, and must not contain a line number -- a
    blank line inserted at the top of the file may not create a new object.
    """
    return "|".join((
        event.owner_kind,
        event.owner_qualified_name,
        event.owner_signature,
        event.event_type,
        str(event.ordinal),
    ))


def _call_arguments(node: Any, source: bytes) -> str:
    """Every argument's root identifier, in source order, `\\x1f`-joined.

    Stage 4 recorded the *first* argument as the subject, which is right for
    `free(p)` and wrong for `RedisModule_SetKeyMeta(cls, key, p)`: the resource
    is handed over as the third argument, and a query that only ever looks at
    the first one calls that hand-off resolved. The whole list is kept so the
    ownership question ("is this name passed to a callee at all?") can be asked
    without a second parse.

    `\\x1f` because the channel is a `dict[str, str]` of annotations and the
    names in it are C identifiers: a separator that cannot appear inside one
    keeps the decoding unambiguous without a second storage column.
    """
    arguments = node.child_by_field_name("arguments")
    if arguments is None:
        return ""
    names = [_root_identifier(source, item) for item in arguments.named_children]
    names = [name for name in names if name]
    return ARGUMENT_SEPARATOR.join(names)


def _thread_argument_form(node: Any, source: bytes) -> str:
    """The syntactic form of a `pthread_create` 4th argument (Gate A1 spike).

    ``address_of`` means the address of a storage object is passed (must-eligible
    for a query-time consumer). ``pointer_var`` means a pointer-typed *value* is
    passed (may only, never must). ``deref`` is the value a pointer points at.
    ``opaque`` is any expression whose address/identity cannot be proved.
    ``empty`` means no 4th argument is present. No form is ever upgraded.
    """
    if node is None:
        return "empty"
    kind = node.type
    if kind == "pointer_expression":
        op = _operator_of(node, source)
        if op == "&":
            return "address_of"
        if op == "*":
            return "deref"
        return "opaque"
    if kind == "cast_expression":
        inner = _thread_argument_form(node.child_by_field_name("value"), source)
        return "address_of" if inner == "address_of" else "opaque"
    if kind == "identifier":
        return "pointer_var"
    return "opaque"


def _first_call_argument(node: Any) -> Any:
    arguments = node.child_by_field_name("arguments")
    if arguments is not None and arguments.named_children:
        return arguments.named_children[0]
    return None


# ---------------------------------------------------------------------------
# Buffer / Extent / Size facts V1 (issue-pilot#82)
#
# Two additive, versioned annotation keys ride on the points the walker already
# publishes. Neither changes any existing key, the event identity, the edge
# set or any defect query -- they only *describe* facts a later bounds query
# (M5-M8) can consume:
#
#   buffer_extent_v1   on an ALLOC point (source="allocation"), on a
#                      READ/WRITE/DEREFERENCE whose root resolves to a fixed
#                      array declaration (source="declared_array"), and on a
#                      memory-API CALL whose destination resolves to one
#   memory_access_v1   on a READ/WRITE/DEREFERENCE that carries a subscript
#                      index or pointer offset, and on a memory-API CALL that
#                      carries a length argument
#
# Both values are compact JSON (sorted keys) so the structure is versioned and
# deterministic. Three states are kept distinct: a resolved constant
# (status="constant" + "constant"), a retained-but-unevaluated expression
# (status="expression"), and an explicitly-unknown or unsupported shape
# (status="unknown"/"unsupported" + "limitation"). "Absent" means the point has
# no such fact at all (a plain `int x` access publishes no buffer_extent_v1);
# it never means "extent 0" or "in bounds". No bounds verdict is produced here.
# ---------------------------------------------------------------------------

BUFFER_EXTENT_KEY = "buffer_extent_v1"
MEMORY_ACCESS_KEY = "memory_access_v1"

# The size-argument position (0-based) for the allocators V1 models exactly.
# `malloc(n)` -> 0, `realloc(p, n)` -> 1, `memalign(alignment, n)` -> 1,
# `aligned_alloc(a, n)` -> 1, and the write-through
# `posix_memalign(&p, a, n)` -> 2. Anything not listed (the
# Windows/glibc convenience families, `new`, ...) stays explicitly unknown
# rather than guessing which argument is a size.
_ALLOC_SIZE_ARG = {
    "malloc": 0, "realloc": 1, "memalign": 1, "valloc": 0, "pvalloc": 0,
    "aligned_alloc": 1, "posix_memalign": 2,
}
# Calloc-like allocators take (count, element_size) as two arguments:
# `calloc(n, sizeof(T))` -> (0, 1), `reallocarray(p, n, s)` -> (1, 2).
_ALLOC_CALLOC_LIKE = {"calloc": (0, 1), "reallocarray": (1, 2)}

# Memory-API byte-length argument position (0-based): `memcpy(d, s, n)` and
# `memset(p, v, n)` -> 2. String-copy bounds are not byte extents in the
# general case, so strncpy/strncat deliberately stay outside V1.
_MEMORY_LENGTH_ARG = {"memcpy": 2, "memmove": 2, "memset": 2}

_INT_SUFFIX = re.compile(r"[uUlL]+\Z")
_CPP_BUILTIN_SUBSCRIPT_TYPES = frozenset({
    "bool", "char", "signed", "unsigned", "short", "int", "long",
    "wchar_t", "char8_t", "char16_t", "char32_t",
})
_CPP_BUILTIN_ADDRESS_OF_TYPES = _CPP_BUILTIN_SUBSCRIPT_TYPES | {
    "float", "double", "nullptr_t",
}
_RAW_STRING_START = re.compile(r'(?:u8|u|U|L)?R"([^ ()\\\t\r\n]{0,16})\(')
_TOKEN_JOIN_PAIRS = frozenset({
    "++", "+=", "--", "-=", "->", ".*", "..", "::", ":>",
    "<<", "<=", "<:", "<%", ">>", ">=", "==", "!=", "&&", "&=",
    "||", "|=", "^^", "^=", "*=", "/=", "/*", "//", "%=", "%>",
    "%:", "##",
})


def _needs_token_separator(previous: str, following: str) -> bool:
    """Whether deleting whitespace would merge two C/C++ tokens."""
    previous_word = previous.isalnum() or previous == "_"
    following_word = following.isalnum() or following == "_"
    if previous_word and following_word:
        return True
    if previous_word and following in {'"', "'"}:
        return True
    if previous in {'"', "'"} and following_word:
        return True
    if (previous.isdigit() and following == ".") or (previous == "." and following.isdigit()):
        return True
    return previous + following in _TOKEN_JOIN_PAIRS


def _facts_json(obj: dict[str, Any]) -> str:
    """Deterministic, compact JSON for a versioned fact block."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _object_fact(annotations: Mapping[str, str]) -> dict[str, str]:
    """The existing subject identity, embedded without inventing a second one.

    Local declaration tokens are owner-scoped: consumers must use this object
    together with the carrier event's owner/event id, never join on `decl` alone.
    """
    return {
        "decl": annotations.get("subject_decl", ""),
        "storage": annotations.get("subject_storage", STORAGE_UNKNOWN),
        "type": annotations.get("subject_type", ""),
        "member": annotations.get("subject_member", ""),
    }


def _allocation_result_is_directly_bound(
    node: Any,
    allow_comma: bool,
    assignment_target_is_pointer: Callable[[Any], bool],
    cpp: bool = False,
) -> bool:
    """Whether an allocator's result, not a sibling expression, is assigned."""
    current = node
    while current is not None:
        parent = current.parent
        if parent is None:
            return False
        if parent.type == "parenthesized_expression":
            current = parent
            continue
        if parent.type == "cast_expression":
            if cpp:
                # A class-type cast can construct a temporary whose conversion
                # operator returns an unrelated pointer. Only a syntactic pointer
                # result preserves this already-pointer allocation value without
                # invoking a C++ user-defined conversion.
                descriptor = parent.child_by_field_name("type")
                declarator = (
                    descriptor.child_by_field_name("declarator")
                    if descriptor is not None else None
                )
                if declarator is None or declarator.type != "abstract_pointer_declarator":
                    return False
            current = parent
            continue
        if parent.type in {"assignment_expression", "init_declarator"}:
            if _is_read_modify_write(parent) or not assignment_target_is_pointer(parent):
                return False
            if parent.type == "assignment_expression":
                target = _unwrap_parentheses(parent.child_by_field_name("left"))
                while target is not None and target.type == "field_expression":
                    target = _unwrap_parentheses(target.child_by_field_name("argument"))
                if target is None or target.type not in {"identifier", "this"}:
                    # `*pp = malloc(n)` binds pp's pointee, not pp itself.
                    # V1 has no points-to identity for that target; subscript,
                    # dereference and computed LHS shapes therefore fail closed.
                    return False
            value_field = "right" if parent.type == "assignment_expression" else "value"
            value = parent.child_by_field_name(value_field)
            return value is not None and _span(value) == _span(current)
        if parent.type == "comma_expression":
            if not allow_comma:
                # C++ may overload operator, even when the allocator is the
                # right operand, so the outer value need not be its result.
                return False
            right = parent.child_by_field_name("right")
            if right is None or _span(right) != _span(current):
                return False
            current = parent
            continue
        if parent.type == "conditional_expression":
            if cpp:
                # Conditional class conversion can transform the selected arm
                # after that arm was chosen. V1 does not attempt partial C++
                # conditional-type resolution; even a pointer-only conditional
                # therefore stays an unbound allocation object.
                return False
            consequence = parent.child_by_field_name("consequence")
            alternative = parent.child_by_field_name("alternative")
            if _span(current) not in {_span(consequence), _span(alternative)}:
                return False
            current = parent
            continue
        return False
    return False


def _allocation_object_fact(
    annotations: Mapping[str, str],
    node: Any,
    out_argument_is_direct: bool,
    allow_comma: bool,
    assignment_target_is_pointer: Callable[[Any], bool],
    cpp: bool = False,
) -> dict[str, str]:
    """The object bound to an allocation result, or explicitly unknown.

    The legacy CALL/ALLOC fallback names the first call argument. That is useful
    to existing queries but is not an allocation-object claim: in `malloc(n)`,
    `n` is a size, not the returned buffer. Only a direct value-flow path to an
    assignment and write-through out-argument recovery bind the result in V1.
    """
    subject_from = annotations.get("subject_from")
    if subject_from == SUBJECT_FROM_OUT_ARGUMENT:
        if out_argument_is_direct:
            return _object_fact(annotations)
        return _object_fact({})
    if subject_from == SUBJECT_FROM_ASSIGNMENT and _allocation_result_is_directly_bound(
        node,
        allow_comma=allow_comma,
        assignment_target_is_pointer=assignment_target_is_pointer,
        cpp=cpp,
    ):
        return _object_fact(annotations)
    return _object_fact({})


def _fact_expression_text(source: bytes, node: Any) -> str:
    """Compact source syntax without deleting semantic whitespace.

    Unlike the legacy `_expression_text`, fact expressions must preserve spaces
    inside ordinary/raw string and character literals (`"a b"`) and between
    adjacent word tokens (`signed char`, `unsigned long`). Comments act as
    token-separating whitespace. Other formatting whitespace is removed to
    retain the deterministic compact spelling (`n - 1` -> `n-1`).
    """
    text = _text_of(source, node)
    result: list[str] = []
    quote = ""
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        if quote:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
            index += 1
            continue
        previous_is_word = index > 0 and (text[index - 1].isalnum() or text[index - 1] == "_")
        raw = None if previous_is_word else _RAW_STRING_START.match(text, index)
        if raw is not None:
            closing = f"){raw.group(1)}\""
            end = text.find(closing, raw.end())
            if end < 0:
                # An incomplete raw literal is erroneous source, but deleting
                # its contents would still corrupt the retained expression.
                result.append(text[index:])
                break
            end += len(closing)
            result.append(text[index:end])
            index = end
            continue
        if character in {'"', "'"}:
            quote = character
            result.append(character)
            index += 1
            continue
        is_comment = text.startswith("/*", index) or text.startswith("//", index)
        if character.isspace() or is_comment:
            following = index
            while following < len(text):
                if text[following].isspace():
                    following += 1
                    continue
                if text.startswith("/*", following):
                    close = text.find("*/", following + 2)
                    following = len(text) if close < 0 else close + 2
                    continue
                if text.startswith("//", following):
                    close_candidates = [
                        position for position in (text.find("\n", following + 2), text.find("\r", following + 2))
                        if position >= 0
                    ]
                    following = min(close_candidates) if close_candidates else len(text)
                    continue
                break
            if result and following < len(text) and _needs_token_separator(
                result[-1], text[following]
            ):
                result.append(" ")
            index = following
            continue
        result.append(character)
        index += 1
    return "".join(result).strip()


def _product_operand(node: Any, text: str) -> str:
    """Parenthesize an operand whose precedence is below multiplication."""
    if node is not None and node.type in {
        "binary_expression", "conditional_expression", "assignment_expression",
        "comma_expression",
    }:
        return f"({text})"
    return text


def _byte_product_expression(size_node: Any, expression: str, type_text: str) -> str:
    return f"{_product_operand(size_node, expression)} * sizeof({type_text or 'unknown'})"


_STATEMENT_LOCAL_SCOPES = frozenset({
    "for_statement", "for_range_loop", "range_based_for_statement",
    "if_statement", "switch_statement", "while_statement",
})


def _declarator_inner(node: Any) -> Any:
    inner = node.child_by_field_name("declarator")
    if inner is None and node.type in {
        "reference_declarator", "parenthesized_declarator",
    } and node.named_children:
        inner = node.named_children[-1]
    return inner


def _declarator_name(source: bytes, node: Any) -> str:
    """Read a declared name through the grammar's transparent wrappers."""
    while node is not None:
        if node.type in {"identifier", "field_identifier", "type_identifier"}:
            return _text_of(source, node)
        if node.type in {
            "init_declarator", "function_declarator", "pointer_declarator",
            "reference_declarator", "array_declarator", "parenthesized_declarator",
        }:
            inner = _declarator_inner(node)
            node = inner
            continue
        return ""
    return ""


def _statement_local_scope(declaration: Any) -> Any:
    """The statement-owned scope of a heading declaration, if it has one."""
    parent = declaration.parent
    while parent is not None:
        if parent.type in _STATEMENT_LOCAL_SCOPES:
            return parent
        if parent.type in {
            "compound_statement", "function_definition", "class_specifier",
            "struct_specifier", "union_specifier", "translation_unit",
        }:
            break
        parent = parent.parent
    return None


def _collect_statement_declaration_scopes(
    root: Any, source: bytes
) -> tuple[dict[int, Any], dict[int, dict[str, int]]]:
    """Index statement-heading names without changing DeclarationIndex.

    Ordinary heading declarations already have Declaration objects, but the
    installed C++ grammar represents a range-for declaration directly on the
    `for_range_loop` node. Recording both shapes lets the extent layer reject
    an outer same-named array inside that statement and skip stale heading
    declarations after it, without minting an identity for an unindexed range
    declarator. Each name carries its first visible byte: range initializers
    and structured-binding initializers still belong to the enclosing scope.
    """
    scope_by_declaration: dict[int, Any] = {}
    names_by_statement: dict[int, dict[str, int]] = {}

    def record_name(statement: Any, declarator: Any, visible_from: int) -> None:
        if declarator is None:
            return
        if declarator.type == "init_declarator":
            record_name(
                statement, declarator.child_by_field_name("declarator"), visible_from
            )
            return
        if declarator.type == "structured_binding_declarator":
            for child in declarator.named_children:
                if child.type == "identifier":
                    record_name(statement, child, visible_from)
            return
        name = _declarator_name(source, declarator)
        if name:
            names = names_by_statement.setdefault(statement.start_byte, {})
            names[name] = min(visible_from, names.get(name, visible_from))

    def visit(node: Any) -> None:
        if node.type == "declaration":
            statement = _statement_local_scope(node)
            if statement is not None:
                scope_by_declaration[node.start_byte] = statement
                for declarator in node.children_by_field_name("declarator"):
                    record_name(statement, declarator, node.end_byte)
        elif node.type in {"for_range_loop", "range_based_for_statement"}:
            body = node.child_by_field_name("body")
            record_name(
                node, node.child_by_field_name("declarator"),
                body.start_byte if body is not None else node.end_byte,
            )
        elif node.type == "lambda_expression":
            # An init-capture declares a new object only inside the lambda body.
            # It must not hide an outer same-named array, but the initializer
            # itself remains in the enclosing scope and is therefore excluded.
            capture = next(
                (child for child in node.named_children
                 if child.type == "lambda_capture_specifier"),
                None,
            )
            body = next(
                (child for child in node.named_children
                 if child.type == "compound_statement"),
                None,
            )
            if capture is not None and body is not None:
                for initializer in capture.named_children:
                    if initializer.type != "lambda_capture_initializer":
                        continue
                    name = next(
                        (child for child in initializer.named_children
                         if child.type == "identifier"),
                        None,
                    )
                    record_name(body, name, body.start_byte)
        for child in node.named_children:
            visit(child)

    visit(root)
    return scope_by_declaration, names_by_statement


def _unwrap_parentheses(node: Any) -> Any:
    while node is not None and node.type == "parenthesized_expression":
        node = node.named_children[0] if node.named_children else None
    return node


def _parent_through_parentheses(node: Any) -> tuple[Any, Any]:
    current = node
    parent = current.parent
    while parent is not None and parent.type == "parenthesized_expression":
        current = parent
        parent = current.parent
    return current, parent


def _cpp_reference_cast_transparency(
    current: Any, parent: Any, source: bytes
) -> bool | None:
    """Whether a cast preserves a builtin lvalue for outer WRITE propagation.

    ``True`` accepts only a C-style cast to a primitive lvalue reference or the
    equivalent ``static_cast``. ``False`` rejects a recognized reference cast
    whose semantics V1 cannot prove. ``None`` means this is not a reference
    cast, so ordinary READ handling can continue.
    """
    type_node = None
    cast_name = ""
    if parent.type == "cast_expression":
        value = parent.child_by_field_name("value")
        if value is None or _span(value) != _span(current):
            return None
        type_node = parent.child_by_field_name("type")
    elif parent.type == "call_expression":
        function = parent.child_by_field_name("function")
        arguments = parent.child_by_field_name("arguments")
        if function is None or function.type != "template_function" or arguments is None:
            return None
        if len(arguments.named_children) != 1 or (
            _span(arguments.named_children[0]) != _span(current)
        ):
            return None
        identifier = next(
            (child for child in function.named_children if child.type == "identifier"),
            None,
        )
        template = next(
            (child for child in function.named_children
             if child.type == "template_argument_list"),
            None,
        )
        if identifier is None or template is None or len(template.named_children) != 1:
            return None
        cast_name = _text_of(source, identifier)
        if cast_name not in {"static_cast", "const_cast", "reinterpret_cast", "dynamic_cast"}:
            return None
        type_node = template.named_children[0]
    else:
        return None

    if type_node is None or type_node.type != "type_descriptor":
        return None
    references = [
        child for child in type_node.named_children
        if child.type == "abstract_reference_declarator"
    ]
    if not references:
        return None
    if len(references) != 1 or _text_of(source, references[0]) != "&":
        return False
    is_builtin = any(child.type == "primitive_type" for child in type_node.named_children)
    if is_builtin and (parent.type == "cast_expression" or cast_name == "static_cast"):
        return True
    return False


def _semantic_access_kind(
    expr: Any,
    carrier_event_type: str,
    source: bytes,
    origin: Any = None,
    cpp: bool = False,
) -> str | None:
    """READ/WRITE/RMW for a value access, or None for a non-value use."""
    ancestor = expr.parent
    while ancestor is not None:
        if ancestor.type in {
            "sizeof_expression", "alignof_expression", "decltype",
            "decltype_specifier", "noexcept_expression",
        }:
            return None
        if ancestor.type == "call_expression":
            function = ancestor.child_by_field_name("function")
            if function is not None and _expression_text(source, function) == "noexcept":
                return None
        ancestor = ancestor.parent

    current, parent = _parent_through_parentheses(expr)
    while parent is not None:
        if parent.type == "parenthesized_expression":
            current, parent = _parent_through_parentheses(parent)
            continue
        if parent.type in {"field_expression", "subscript_expression"}:
            argument = parent.child_by_field_name("argument")
            if argument is None or _span(argument) != _span(current):
                break
            if parent.type == "field_expression" and _operator_of(parent, source) == "->":
                # `a[i]->x = 0` writes `x`, but it must read the pointer stored
                # in `a[i]`. Dot-member lvalue paths remain transparent below.
                return "READ"
            current, parent = _parent_through_parentheses(parent)
            continue
        if parent.type == "conditional_expression":
            consequence = parent.child_by_field_name("consequence")
            alternative = parent.child_by_field_name("alternative")
            if _span(current) not in {_span(consequence), _span(alternative)}:
                break
            current, parent = _parent_through_parentheses(parent)
            continue
        if parent.type == "comma_expression":
            if cpp:
                # An overloaded comma need not return its right operand, so an
                # outer assignment says nothing about a write to that operand.
                return None
            # Only the right operand supplies a C comma-expression's result.
            right = parent.child_by_field_name("right")
            if right is None or _span(right) != _span(current):
                break
            current, parent = _parent_through_parentheses(parent)
            continue
        if parent.type == "pointer_expression" and _operator_of(parent, source) == "&":
            if cpp:
                # `operator&` may return an unrelated pointer. Without a full
                # expression-type resolver V1 never cancels a C++ `*&` pair.
                return None
            addressed, outer = _parent_through_parentheses(parent)
            if outer is None or outer.type != "pointer_expression" or (
                _operator_of(outer, source) != "*"
            ):
                return None
            argument = outer.child_by_field_name("argument")
            if argument is None or _span(argument) != _span(addressed):
                return None
            current, parent = _parent_through_parentheses(outer)
            continue
        if cpp and parent.type == "argument_list" and (
            parent.parent is not None and parent.parent.type == "call_expression"
        ):
            # Named C++ casts wrap their sole value in an argument_list. Let the
            # reference-cast check below inspect the cast itself; ordinary calls
            # remain non-transparent and fall through to READ.
            parent = parent.parent
        if cpp:
            reference_cast = _cpp_reference_cast_transparency(current, parent, source)
            if reference_cast is True:
                current, parent = _parent_through_parentheses(parent)
                continue
            if reference_cast is False:
                # A user-defined or otherwise unproven reference cast need not
                # preserve the source element. Do not default its access to READ.
                return None
        break

    if carrier_event_type != "DEREFERENCE":
        if carrier_event_type == "WRITE" and origin is not None and _is_read_modify_write(origin):
            return "READ_MODIFY_WRITE"
        return carrier_event_type
    if parent is not None and parent.type == "assignment_expression":
        left = parent.child_by_field_name("left")
        if left is not None and _span(left) == _span(current):
            return "READ_MODIFY_WRITE" if _is_read_modify_write(parent) else "WRITE"
    if parent is not None and parent.type == "update_expression":
        argument = parent.child_by_field_name("argument")
        if argument is not None and _span(argument) == _span(current):
            return "READ_MODIFY_WRITE"
    return "READ"


def _array_extent_base(
    expr: Any,
    source: bytes,
    commuted: bool = False,
    pointer_commuted: bool = False,
) -> Any:
    """The expression naming the declared array, or None for an unsafe join."""
    if expr.type == "subscript_expression":
        if commuted:
            return _subscript_index_node(expr)
        return expr.child_by_field_name("argument")
    if expr.type in {"identifier", "field_expression"}:
        return expr
    if expr.type == "pointer_expression" and _operator_of(expr, source) == "*":
        argument = _unwrap_parentheses(expr.child_by_field_name("argument"))
        if argument is not None and argument.type == "binary_expression" and (
            _operator_of(argument, source) in {"+", "-"}
        ):
            if _operator_of(argument, source) == "+" and pointer_commuted:
                return argument.child_by_field_name("right")
            return argument.child_by_field_name("left")
    return None


def _const_int(node: Any, source: bytes) -> int | None:
    """Fold only target-independent, non-negative signed-int expressions.

    Numeric literals and `*`/`<<`/`+` are retained only when every operand and
    result fits a signed 32-bit int. Unsigned-suffixed literals, negative
    values, wider results and invalid shift counts return None: without target
    integer semantics, Python's unbounded arithmetic could otherwise invent a
    value that C/C++ does not have. The bounds also make malformed/UB source
    fail closed instead of raising or allocating an enormous integer.
    """
    while node is not None and node.type == "parenthesized_expression":
        node = node.named_children[0] if node.named_children else None
    if node is None:
        return None
    maximum = 2_147_483_647
    if node.type == "number_literal":
        raw = _fact_expression_text(source, node)
        text = _INT_SUFFIX.sub("", raw)
        suffix = raw[len(text):]
        if "u" in suffix.lower() or len(text) > 40:
            return None
        try:
            # Python's base-0 parser rejects C's traditional octal spelling.
            if re.fullmatch(r"0[0-7]+", text):
                value = int(text, 8)
            else:
                value = int(text, 0)
        except ValueError:
            return None
        return value if 0 <= value <= maximum else None
    if node.type == "binary_expression":
        operator = _operator_of(node, source)
        if operator not in {"*", "<<", "+"}:
            return None
        left = _const_int(node.child_by_field_name("left"), source)
        right = _const_int(node.child_by_field_name("right"), source)
        if left is None or right is None:
            return None
        if operator == "*":
            if right and left > maximum // right:
                return None
            return left * right
        if operator == "<<":
            if right > 30 or left > (maximum >> right):
                return None
            return left << right
        if left > maximum - right:
            return None
        return left + right
    return None


def _callee_leaf(matched_name: str) -> str:
    """The last name component of a callee (`ns::malloc`/`M.malloc` -> `malloc`)."""
    return matched_name.rpartition(".")[2].rpartition("::")[2]


def _call_argument_nodes(node: Any) -> list[Any]:
    arguments = node.child_by_field_name("arguments")
    return list(arguments.named_children) if arguments is not None else []


def _alloc_extent_facts(node: Any, matched_name: str, source: bytes) -> dict[str, Any]:
    """buffer_extent_v1 for an ALLOC point (source="allocation").

    Constant sizes fold to `constant`; dynamic sizes keep their expression with
    status="expression" and an explicit null value. Allocators V1 does not
    model, and C++ `new` (no argument list), report status="unknown" with a
    limitation -- never a fabricated extent. Unit is bytes for this family.
    """
    callee = _callee_leaf(matched_name)
    args = _call_argument_nodes(node)
    fact: dict[str, Any] = {
        "source": "allocation", "unit": "bytes", "expression": None,
        "constant": None, "status": "unknown", "limitation": "",
    }
    if callee in _ALLOC_CALLOC_LIKE:
        count_i, size_i = _ALLOC_CALLOC_LIKE[callee]
        if len(args) <= max(count_i, size_i):
            fact["limitation"] = "calloc-like arity"
            return fact
        count_node, size_node = args[count_i], args[size_i]
        count_text = _fact_expression_text(source, count_node)
        size_text = _fact_expression_text(source, size_node)
        count = _const_int(count_node, source)
        elem = _const_int(size_node, source)
        fact.update(
            expression=(
                f"{_product_operand(count_node, count_text)} * "
                f"{_product_operand(size_node, size_text)}"
            ),
            count_expression=count_text,
            element_size_expression=size_text,
        )
        if count is not None and elem is not None:
            product = count * elem
            if product <= 2_147_483_647:
                fact.update(status="constant", constant=product)
            else:
                fact.update(
                    status="expression",
                    limitation="allocation size exceeds signed 32-bit range",
                )
        else:
            fact.update(
                status="expression",
                limitation="count or element size is not a compile-time constant",
            )
        return fact
    if callee not in _ALLOC_SIZE_ARG:
        fact["limitation"] = "allocator size argument not modeled in V1"
        return fact
    index = _ALLOC_SIZE_ARG[callee]
    if len(args) <= index:
        fact["limitation"] = "missing size argument"
        return fact
    size_node = args[index]
    fact["expression"] = _fact_expression_text(source, size_node)
    value = _const_int(size_node, source)
    if value is not None:
        fact.update(status="constant", constant=value)
    else:
        fact.update(status="expression", limitation="size is not a compile-time constant")
    return fact


def _memory_call_facts(node: Any, matched_name: str, source: bytes) -> dict[str, Any] | None:
    """memory_access_v1 for a memcpy/memmove/memset byte length, or None."""
    function = node.child_by_field_name("function")
    if function is None or function.type not in {"identifier", "qualified_identifier"}:
        return None
    callee_text = _fact_expression_text(source, function)
    callee = _callee_leaf(callee_text or matched_name)
    if function.type == "qualified_identifier" and callee_text != f"std::{callee}":
        # Same-named functions in user namespaces do not inherit the standard
        # memory API's semantics. Only the exact std::<leaf> spelling is V1.
        return None
    if callee not in _MEMORY_LENGTH_ARG:
        return None
    args = _call_argument_nodes(node)
    index = _MEMORY_LENGTH_ARG[callee]
    if len(args) <= index:
        return {
            "access": "CALL", "kind": "memory_length", "unit": "bytes",
            "function": callee_text, "expression": None, "constant": None,
            "status": "unknown", "limitation": "missing length argument",
        }
    length_node = args[index]
    value = _const_int(length_node, source)
    fact: dict[str, Any] = {
        "access": "CALL", "kind": "memory_length", "unit": "bytes",
        "function": callee_text,
        "expression": _fact_expression_text(source, length_node), "constant": value,
    }
    if value is not None:
        fact.update(status="constant", limitation="")
    else:
        fact.update(status="expression", limitation="length is not a compile-time constant")
    return fact


def _subscript_index_node(expr: Any) -> Any:
    """The index expression of a subscript, across the two grammar spellings.

    tree-sitter-cpp names the field `indices` (a node that wraps the brackets),
    tree-sitter-c names it `index` (the bare expression). Unwrap a wrapper down
    to the real expression so `buf[5]` folds in both dialects.
    """
    index_node = expr.child_by_field_name("indices")
    if index_node is not None:
        if index_node.type != "subscript_argument_list":
            return None
        children = index_node.named_children
        return children[0] if len(children) == 1 else None
    index_node = expr.child_by_field_name("index")
    if index_node is None or index_node.type == "ERROR" or getattr(index_node, "is_missing", False):
        return None
    return index_node


def _access_facts(
    expr: Any, event_type: str, source: bytes, origin: Any = None,
    commuted: bool | None = False,
    pointer_commuted: bool | None = False,
    cpp: bool = False,
) -> dict[str, Any] | None:
    """memory_access_v1 for a subscript or supported pointer-offset shape.

    `access` is the semantic operation, not necessarily the carrier event type:
    a local array write carried by DEREFERENCE still records WRITE. Address-of
    and unevaluated sizeof operands publish no access fact. A plain `*p` or
    bare identifier has no structured index/offset and publishes no fact.
    """
    access = _semantic_access_kind(
        expr, event_type, source, origin=origin, cpp=cpp
    )
    if access is None:
        return None
    if expr.type == "subscript_expression":
        if commuted is None:
            return {
                "access": access, "kind": "subscript", "unit": "elements",
                "expression": None, "constant": None, "status": "unknown",
                "limitation": "commuted subscript target is not modeled in V1",
            }
        index_node = (
            expr.child_by_field_name("argument") if commuted else _subscript_index_node(expr)
        )
        if index_node is None:
            return {
                "access": access, "kind": "subscript", "unit": "elements",
                "expression": None, "constant": None, "status": "unknown",
                "limitation": "unparsed or multiple subscript indices",
            }
        value = _const_int(index_node, source)
        fact: dict[str, Any] = {
            "access": access, "kind": "subscript", "unit": "elements",
            "expression": _fact_expression_text(source, index_node), "constant": value,
        }
        if value is not None:
            fact.update(status="constant", limitation="")
        else:
            fact.update(status="expression", limitation="index is not a compile-time constant")
        return fact
    if expr.type == "pointer_expression" and _operator_of(expr, source) == "*":
        if pointer_commuted is None:
            return {
                "access": access, "kind": "pointer_offset", "unit": "elements",
                "expression": None, "constant": None, "status": "unknown",
                "limitation": "commuted pointer arithmetic is not modeled in V1",
            }
        argument = _unwrap_parentheses(expr.child_by_field_name("argument"))
        if argument is not None and argument.type == "binary_expression" and (
            _operator_of(argument, source) in {"+", "-"}
        ):
            operator = _operator_of(argument, source)
            is_commuted = operator == "+" and pointer_commuted
            base_node = (
                argument.child_by_field_name("right" if is_commuted else "left")
            )
            base = _unwrap_parentheses(base_node)
            offset_node = argument.child_by_field_name("left" if is_commuted else "right")
            if base is None or base.type not in {"identifier", "field_expression"}:
                return {
                    "access": access, "kind": "pointer_offset", "unit": "elements",
                    "expression": _fact_expression_text(source, argument), "constant": None,
                    "status": "unknown", "limitation": "complex pointer arithmetic",
                }
            if offset_node is not None:
                value = _const_int(offset_node, source)
                offset_text = _fact_expression_text(source, offset_node)
                fact = {
                    "access": access, "kind": "pointer_offset", "unit": "elements",
                    "expression": offset_text if operator == "+" else f"-({offset_text})",
                    "constant": value if operator == "+" or value is None else -value,
                }
                if value is not None:
                    fact.update(status="constant", limitation="")
                else:
                    fact.update(status="expression", limitation="offset is not a compile-time constant")
                return fact
    return None


def _collect_array_extents(
    root: Any, source: bytes,
) -> tuple[
    dict[tuple[int, str], dict[str, Any]],
    set[tuple[int, str]],
    dict[tuple[int, str], Any],
    list[Any],
    set[str],
]:
    """Map declaration identity to extent and bounded member-type syntax.

    The second result includes array-adjusted parameters. It carries no extent
    claim; it only gives commuted-subscript handling enough syntax evidence to
    distinguish `parameter_array[i]` from `i[parameter_array]`.

    The last three results retain exact syntax nodes for V1's direct member
    type check. A shallow `Declaration.type_token` cannot distinguish
    `M::Same` from `N::Same`, or two nested C tags named `S`; consumers must
    prove one visible definition instead of calling `resolve_member` directly.

    The key mirrors `Declaration.start_byte` and `Declaration.name`, so shadowed
    arrays and `int a[4], b[8]` cannot be joined by a use-site spelling alone.
    Only direct, single-dimensional arrays are modeled. Parameters (adjusted to
    pointers), pointers/references to arrays, multidimensional arrays, VLA and
    flexible members stay explicitly unknown/unsupported. Byte extent is given
    only for char arrays; other element sizes are target-ABI facts V1 cannot
    invent. Statement-local visibility is handled by the builder's separate
    overlay, so this map contains only serializable facts.
    """
    extents: dict[tuple[int, str], dict[str, Any]] = {}
    array_declaration_keys: set[tuple[int, str]] = set()
    value_declaration_types: dict[tuple[int, str], Any] = {}
    value_type_definitions: list[Any] = []
    value_type_aliases: set[str] = set()
    character_types = {"char", "signed char", "unsigned char"}

    def unknown_bytes(expression: str | None, limitation: str) -> dict[str, Any]:
        return {
            "unit": "bytes", "expression": expression, "constant": None,
            "status": "unknown", "limitation": limitation,
        }

    def visit(node: Any) -> None:
        if node.type in {"class_specifier", "struct_specifier", "union_specifier"}:
            if node.child_by_field_name("body") is not None:
                value_type_definitions.append(node)
        if node.type in {"alias_declaration", "type_definition", "using_declaration"}:
            names = []
            if node.type == "alias_declaration":
                names = [node.child_by_field_name("name")]
            else:
                names = list(node.children_by_field_name("declarator"))
                if node.type == "using_declaration" and not names:
                    # `using M::Same` introduces Same; `using namespace M`
                    # conservatively marks M even though it is not a type alias.
                    spelling = _fact_expression_text(source, node)
                    identifiers = re.findall(r"[A-Za-z_][A-Za-z_0-9]*", spelling)
                    if identifiers:
                        value_type_aliases.add(identifiers[-1])
            for name_node in names:
                name = _declarator_name(source, name_node)
                if name:
                    value_type_aliases.add(name)
        if node.type in {"declaration", "field_declaration", "parameter_declaration"}:
            type_node = node.child_by_field_name("type")
            declarators = list(node.children_by_field_name("declarator"))
            if type_node is not None:
                for declarator in declarators:
                    name = _declarator_name(source, declarator)
                    if name:
                        value_declaration_types[(node.start_byte, name)] = type_node
            type_text = (
                _fact_expression_text(source, type_node) if type_node is not None else ""
            )
            for declarator in declarators:
                array = declarator
                if array is not None and array.type == "init_declarator":
                    array = array.child_by_field_name("declarator")
                while array is not None and array.type == "parenthesized_declarator":
                    array = _declarator_inner(array)
                if array is None or array.type != "array_declarator":
                    continue
                name = _declarator_name(source, array)
                if not name:
                    continue
                key = (node.start_byte, name)
                array_declaration_keys.add(key)
                if node.type == "parameter_declaration":
                    continue
                size_node = array.child_by_field_name("size")
                expression = (
                    _fact_expression_text(source, size_node) if size_node is not None else None
                )
                fact: dict[str, Any] = {
                    "source": "declared_array", "unit": "elements",
                    "expression": expression, "constant": None,
                    "status": "unknown", "limitation": "",
                }
                inner = array.child_by_field_name("declarator")
                shape = inner
                while shape is not None and shape.type == "parenthesized_declarator":
                    shape = _declarator_inner(shape)
                if shape is not None and shape.type == "array_declarator":
                    fact["limitation"] = "multidimensional arrays are not modeled in V1"
                    fact["bytes"] = unknown_bytes(None, fact["limitation"])
                elif shape is not None and shape.type in {
                    "pointer_declarator", "reference_declarator",
                }:
                    fact.update(
                        status="unsupported",
                        limitation="pointer/reference array declarators are not modeled in V1",
                    )
                    fact["bytes"] = unknown_bytes(None, fact["limitation"])
                elif getattr(node, "has_error", False):
                    fact["limitation"] = "partial or erroneous declaration"
                    byte_expression = expression
                    if expression is not None and type_text not in character_types:
                        byte_expression = _byte_product_expression(
                            size_node, expression, type_text
                        )
                    fact["bytes"] = unknown_bytes(byte_expression, fact["limitation"])
                elif size_node is None:
                    fact.update(
                        status="unsupported",
                        limitation="flexible or incomplete array has no declared extent",
                    )
                    fact["bytes"] = unknown_bytes(None, fact["limitation"])
                else:
                    value = _const_int(size_node, source)
                    if value is None:
                        fact["limitation"] = (
                            "non-constant array extent (VLA, macro or unsupported expression)"
                        )
                        byte_expression = expression
                        if expression is not None and type_text not in character_types:
                            byte_expression = _byte_product_expression(
                                size_node, expression, type_text
                            )
                        fact["bytes"] = unknown_bytes(byte_expression, fact["limitation"])
                    else:
                        fact.update(status="constant", constant=value)
                        if type_text in character_types:
                            fact["bytes"] = {
                                "unit": "bytes", "expression": expression,
                                "constant": value, "status": "constant", "limitation": "",
                            }
                        else:
                            fact["bytes"] = unknown_bytes(
                                _byte_product_expression(size_node, expression, type_text),
                                "target ABI element size is not available",
                            )
                extents[key] = fact
        for child in node.named_children:
            visit(child)

    visit(root)
    return (
        extents,
        array_declaration_keys,
        value_declaration_types,
        value_type_definitions,
        value_type_aliases,
    )


# Node types the name walk passes through without leaving an object behind:
# `&m`, `*m`, `(m)`, a cast, and the declarators that spell a pointer,
# reference or array around the name they bind. Everything else the walk can
# descend -- `s->m`, `a[i]`, `!p` -- leaves an object behind, so the identifier
# recovered from it names that object and not the one the operation acts on.
_TRANSPARENT_WRAPPERS = frozenset({
    "parenthesized_expression", "pointer_expression", "cast_expression",
    "pointer_declarator", "reference_declarator", "array_declarator",
})


def _names_the_object(node: Any) -> bool:
    """Whether the recovered identifier is the whole designation.

    `&g_index_lock` names the lock; `&index->slot_locks[i]` names the struct
    that holds an array of locks, so two different elements of that array would
    otherwise read as one lock acquired twice. The difference is not in the
    name but in whether anything was left behind on the way down to it -- the
    same descent `_root_identifier` makes, with a note of what it passed.

    A bare `type_identifier` is the one node type that has to be read the other
    way: in `guard(m)` the most-vexing-parse leaves `m` spelled as a *type*,
    and that spelling is a fact about the parse and not about the object. It is
    a single token with nothing left behind on the way down, so it names the
    object exactly.
    """
    if node is not None and node.type == "type_identifier" and not node.named_children:
        return True
    while node is not None and node.type != "identifier":
        if node.type not in _TRANSPARENT_WRAPPERS:
            return False
        if node.type == "parenthesized_expression":
            node = node.named_children[0] if node.named_children else None
            continue
        node = node.child_by_field_name(_DESCEND_FIELDS[node.type])
    return node is not None


# Where a spawn call names the function the new thread runs. Positional
# arguments, not names: `pthread_create(&t, NULL, worker, NULL)` names `worker`
# third. A spawn whose name is missing from this table gets NO thread function
# -- guessing a position would attach a thread to whatever expression happened
# to sit there, and a wrong edge is worse than a missing one.
_THREAD_ENTRY_ARGUMENT = {
    "pthread_create": 2,
    "thrd_create": 1,
    "CreateThread": 2,
    "_beginthread": 1,
    "_beginthreadex": 2,
    "g_thread_new": 1,
    "g_thread_try_new": 1,
}

# The qualified C++ spawns take the callable as the construction argument, so
# their thread function is the declaration's argument rather than a fixed
# position in a call's argument list.
_THREAD_QUALIFIED_SPAWNS = frozenset({"std.thread", "std.jthread", "std.async"})


_EXIT_SORT_KEY = PointKey("", "", "", "", -1)

# Internal marker for the synthetic method exit on an edge under construction.
# Deliberately not None: None means "no target", which a malformed construct
# produces and which must be dropped rather than published.
_EXIT = object()


@dataclass(slots=True)
class _Point:
    """One CFG point under construction; becomes an edge endpoint key."""

    event_type: str
    owner_kind: str
    owner_qualified_name: str
    owner_signature: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    matched_name: str
    seq: int
    # Hits carry their ordinal from the event layer; structural points get one
    # in `_assign_ordinals` (-1 is never observable after `build`).
    ordinal: int = -1
    flags: tuple[str, ...] = ()
    annotations: dict[str, str] = field(default_factory=dict)
    # Edgeless local facts retain the walker's actual incoming opens until all
    # source-order ordinals have been assigned. None means no V1 association.
    control_incoming: list[_Open] | None = None
    # Frozen method coverage for all three V1 annotation channels.
    local_coverage: tuple[str, ...] | None = None

    def key(self) -> PointKey:
        return PointKey(
            self.owner_kind,
            self.owner_qualified_name,
            self.owner_signature,
            self.event_type,
            self.ordinal,
        )


@dataclass(frozen=True, slots=True)
class _Open:
    """Control flowing from `src` into whatever is linearized next.

    Flags ride on the open edge, not on the point: it is the edge that leaves a
    check's true arm which must carry `branch=true`. `src is None` is the
    method entry -- consumed by the first point, never published, because
    there is no entry node to hang an edge on.
    """

    src: _Point | None
    flags: tuple[str, ...] = ()


@dataclass(slots=True)
class _BreakContext:
    breaks: list[_Open] = field(default_factory=list)


@dataclass(slots=True)
class _LoopContext(_BreakContext):
    continues: list[_Open] = field(default_factory=list)


@dataclass(slots=True)
class _SwitchContext(_BreakContext):
    check: _Point | None = None
    saw_default: bool = False


@dataclass(slots=True)
class _HandlerContext:
    entries: list[_Point] = field(default_factory=list)


# Handler names, resolved per node type. String names rather than bound
# methods: the table lives before the class body finishes.
_CONTROL_HANDLERS = {
    "if_statement": "_if_statement",
    "switch_statement": "_switch_statement",
    "case_statement": "_case_statement",
    "while_statement": "_while_statement",
    "do_statement": "_do_statement",
    "for_statement": "_for_statement",
    "for_range_loop": "_for_range_loop",
    "return_statement": "_return_statement",
    "throw_statement": "_throw_statement",
    "break_statement": "_break_statement",
    "continue_statement": "_continue_statement",
    "try_statement": "_try_statement",
    "goto_statement": "_goto_statement",
    "conditional_expression": "_conditional_expression",
}

# Constructs whose bodies run only sometimes but which the walker linearizes
# as plain statements, so the handler map does not already answer for them.
# The try body itself is unconditional and is deliberately absent: the escape
# facts would rather under-count one write than invent one.
_CONDITIONAL_STATEMENTS = {"catch_clause", "handler"}

# Calls that do not come back. A fact about the callee, so it is matched on the
# name rather than on the syntax around it: `std::exit` and `sys.exit` make the
# same claim `exit` does, and a project's own abort macro (`GGML_ABORT`) makes
# it too. The walker has always ended the chain at a syntactic `throw`
# (`_throw_statement`); this is the same statement about a call, and without it
# the statements after `abort()` read as reachable -- which is how two arms
# that are in fact exclusive come to look like they both fall through.
#
# Matched on the last name component, because that is the axis the vocabulary's
# `calls` list matches on, and because a qualified spelling of the same name is
# the same claim. `assert` is deliberately absent: it returns when the
# condition holds, so it is a branch, not a terminator, and ending the chain
# there would invent paths to the exit that the source does not have.
_NORETURN_CALLS = frozenset({
    "abort", "terminate", "exit", "_exit", "quick_exit", "longjmp", "GGML_ABORT",
})


def _never_returns(point: "_Point") -> bool:
    """Whether this point is a call the walker knows does not come back.

    Only a `THROW` can be one: that is the event type whose own docstring says
    it is a non-local exit, and it is the only one that carries the callee's
    name rather than the node type it was read from. A syntactic `throw`
    matches the syntax axis and carries `throw_statement`, which is not in the
    set -- it is already ended by its own handler, and this must not end it
    twice.
    """
    if point.event_type != "THROW":
        return False
    return point.matched_name.rpartition(".")[2] in _NORETURN_CALLS

# The storages an escape can land in: the same set the access layer publishes,
# because the question is the same -- does this object outlive the frame? An
# `unknown` target is a name the file does not declare, which can never be a
# local of the method doing the writing.
# Stage 5B put the parameter storage into ACCESS_STORAGES so the write side
# of a parameter could publish, and that must not silently widen this set:
# a parameter slot is frame-local (it dies with the frame), so `q = p`
# writes into one is not an escape -- if the value leaves, the RETURN that
# carries it is the fact that says so, not the write.
_ESCAPE_TARGET_STORAGES = ACCESS_STORAGES - {STORAGE_PARAMETER}


def _escapes_the_frame(annotations: Mapping[str, str]) -> bool:
    """Whether a write lands somewhere that outlives the frame it is written in.

    Shared storage is the whole answer for every storage but one. A parameter
    is the storage whose answer depends on the *shape* of the write: `p = q`
    rebinds this frame's copy of the pointer and the caller sees nothing,
    while `*out = q`, `param->f = q` and `param[i] = q` write into memory the
    caller owns -- which is what outliving the frame means. That is the C
    out-parameter idiom, and reading it as a leak is what the stage 7 review
    sheet's `*meta = metadata_string` case was.

    The signal is the one the alias rule already reads -- the written
    expression is not the bare name -- so the two rules agree by construction
    rather than by two spellings of the same idea drifting apart.
    """
    storage = annotations.get("subject_storage", "")
    if storage in _ESCAPE_TARGET_STORAGES:
        return True
    return (
        storage == STORAGE_PARAMETER
        and annotations.get("expression", "") != annotations.get("subject", "")
    )

# The allocations whose escape matters for the lifetime query: a frame-local
# is the only acquire whose leak claim an escape write can overturn. A
# function-static or a field does not leak by outliving the frame -- it *is*
# the longer-lived owner.
_FRAME_LOCAL_STORAGES = frozenset({STORAGE_LOCAL, STORAGE_PARAMETER})

# Where the written-to value is read from, per write-shaped node.
WRITE_SOURCE_FIELDS = {
    "assignment_expression": "right",
    "compound_assignment_expression": "right",
    "init_declarator": "value",
}


# ----------------------------------------------------------------------
# reachability over published edges


DEFAULT_ADJACENCY_RELATIONS = frozenset({CONTROL_REACHES})


def build_adjacency(
    edges: Iterable[Any],
    relations: frozenset[str] = DEFAULT_ADJACENCY_RELATIONS,
) -> dict[str, list[tuple[str, str, frozenset[str]]]]:
    """`src -> [(edge_id, dst, flags)]`, neighbours ordered by (dst, edge_id).

    Accepts `SemanticEdge` objects or the rows the storage loader returns --
    both are the same four facts. The ordering here is what makes a walk's
    result independent of the order rows came out of SQLite in.

    The `relations` filter exists because stage 5B started sharing the
    `semantic_edges` table: a DATA_FLOW_TO neighbour is not a control
    predecessor, and every path walk in this module (and the defect layer's)
    reasons about control reachability only. The default keeps the pre-5B
    behaviour bit for bit; a consumer that wants flow edges names them
    explicitly, so no existing caller had to change.
    """
    adjacency: dict[str, list[tuple[str, str, frozenset[str]]]] = {}
    for edge in edges:
        if relations is not None and _field_of(edge, "relation") not in relations:
            continue
        entry = (_field_of(edge, "edge_id"), _field_of(edge, "dst_event_id"), _flags_of(edge))
        adjacency.setdefault(_field_of(edge, "src_event_id"), []).append(entry)
    for neighbours in adjacency.values():
        neighbours.sort(key=lambda item: (item[1], item[0]))
    return adjacency


def _flags_of_point(point: Any) -> tuple[str, ...]:
    flags = _field_of(point, "flags")
    if isinstance(flags, str):
        flags = json.loads(flags) if flags else []
    return tuple(flags)


def materialize_points(events: Iterable[Any], edges: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """One info record per event, plus one synthetic record per exit id.

    The exit has no `semantic_events` row (口径 1: it is an edge endpoint, not
    an event), so paths that end at it need it materialised from the edge rows.

    Three keys are the reachability contract the pattern functions read --
    `event_type`, `subject`, `polarity` -- and they are all stage 3 ever put
    here. The rest are the defect layer's: `subject_from`, `subject_exact` and
    `raii` decide whether an identity is resolved or a name-level proxy,
    `thread_function` is what a spawn edge would point at, and the
    span/owner/file keys are what a candidate cites. Widening this dict is how
    stage 4 reads facts without a second query against the database.

    Stage 4.5 adds the declaration identity: `subject_decl` is the token that
    says *which* object a subject name refers to, `subject_storage` how long it
    lives, `subject_type` what it was declared as, `subject_member` the member
    path left over after the root name, `subject_site` the allocation site of an
    anonymous `new`, and `arguments` every root identifier passed to the call.
    A record without `subject_decl` is an old row or a name the file does not
    declare; the defect layer falls back to the name rather than dropping it.
    """
    points: dict[str, dict[str, Any]] = {}
    for event in events:
        metadata = _field_of(event, "metadata")
        if isinstance(metadata, str):
            metadata = json.loads(metadata) if metadata else {}
        metadata = metadata or {}
        points[_field_of(event, "event_id")] = {
            "event_type": _field_of(event, "event_type"),
            "subject": metadata.get("subject", ""),
            "polarity": metadata.get("polarity", ""),
            "subject_from": metadata.get("subject_from", ""),
            "subject_exact": metadata.get("subject_exact", ""),
            "raii": metadata.get("raii", ""),
            "thread_function": metadata.get("thread_function", ""),
            "subject_decl": metadata.get("subject_decl", ""),
            "subject_storage": metadata.get("subject_storage", ""),
            "subject_type": metadata.get("subject_type", ""),
            "subject_member": metadata.get("subject_member", ""),
            "subject_site": metadata.get("subject_site", ""),
            "arguments": metadata.get("arguments", ""),
            # 5C-2's annotation facts, read off the acquisition point itself:
            # `passed_to`/`returned` say where an allocation goes on its own
            # line (a call argument, the method's return value), `escaped_to`/
            # `escaped_to_line` name the shared storages a plain assignment
            # copies the pointer into, and `subject_init_arg0` is the mutex
            # bound in the same declaration as a guard variable. The escape
            # rulings in the defect layer join on these with no contract
            # dependency, so they must survive materialisation like the
            # declaration-identity keys above them.
            "passed_to": metadata.get("passed_to", ""),
            "returned": metadata.get("returned", ""),
            "escaped_to": metadata.get("escaped_to", ""),
            "escaped_to_line": metadata.get("escaped_to_line", ""),
            "subject_init_arg0": metadata.get("subject_init_arg0", ""),
            # The access layer's own annotation keys (5A/5C-2's 2.11): the
            # expression text, the root name a plain assignment read, and
            # whether the write sits outside every conditional construct.
            # Stage 5B adds the data-flow pair: `alias` is the MAY_ALIAS
            # candidate a bare copy stamped on this point (semicolon-joined
            # opposite roots), and `null_source` marks a write whose
            # right-hand side was the null literal. Both are candidate-
            # grade facts -- neither ever becomes a fact edge by itself.
            "expression": metadata.get("expression", ""),
            "write_source": metadata.get("write_source", ""),
            "unconditional": metadata.get("unconditional", ""),
            "alias": metadata.get("alias", ""),
            "null_source": metadata.get("null_source", ""),
            # ARITH (matrix 2.1/2.2): the operator, the operands it combines,
            # and whether the product is a compile-time constant. The integer
            # overflow query reads these directly, so they must survive
            # materialisation like every other annotation fact above.
            "operator": metadata.get("operator", ""),
            "operands": metadata.get("operands", ""),
            "constant": metadata.get("constant", ""),
            "matched_name": _field_of(event, "matched_name"),
            "matched_via": _field_of(event, "matched_via"),
            # Ordinal is a per-(owner, event type) source-order counter, so it
            # orders acquisitions without a line number: the lock-order query
            # sorts LOCK points by it, and reformatting cannot move a lock.
            "ordinal": _field_of(event, "ordinal"),
            "flags": _flags_of_point(event),
            "owner_symbol_id": _field_of(event, "owner_symbol_id"),
            "file_id": _field_of(event, "file_id"),
            "start_line": _field_of(event, "start_line"),
            "end_line": _field_of(event, "end_line"),
            "start_byte": _optional_field_of(event, "start_byte"),
            "end_byte": _optional_field_of(event, "end_byte"),
            "relative_path": metadata.get("relative_path", ""),
        }
    for edge in edges:
        dst = _field_of(edge, "dst_event_id")
        if dst.startswith(CFG_EXIT_PREFIX) and dst not in points:
            points[dst] = {
                "event_type": "EXIT",
                "subject": "",
                "polarity": "",
                "subject_from": "",
                "subject_exact": "",
                "raii": "",
                "thread_function": "",
                # The synthetic exit is not an operation, so it has no identity
                # to declare. The keys are present and empty rather than absent:
                # every reader does `info.get(key, "")`, and a record with a
                # different shape is one `KeyError` away from being the only
                # path nobody tested.
                "subject_decl": "",
                "subject_storage": "",
                "subject_type": "",
                "subject_member": "",
                "subject_site": "",
                "arguments": "",
                "passed_to": "",
                "returned": "",
                "escaped_to": "",
                "escaped_to_line": "",
                "subject_init_arg0": "",
                "expression": "",
                "write_source": "",
                "unconditional": "",
                "alias": "",
                "null_source": "",
                "matched_name": "",
                "matched_via": "",
                "ordinal": 0,
                "flags": (),
                "owner_symbol_id": "",
                "file_id": "",
                "start_line": 0,
                "end_line": 0,
                "start_byte": None,
                "end_byte": None,
                "relative_path": "",
            }
    return points


def find_paths(
    adjacency: dict[str, list[tuple[str, str, frozenset[str]]]],
    points: dict[str, dict[str, Any]],
    *,
    starts: Iterable[str],
    is_target: Callable[[dict[str, Any]], bool],
    is_blocked: Callable[[dict[str, Any]], bool] | None = None,
    blocked_points: Collection[str] = (),
    blocked_edges: Collection[str] = (),
    require_flags: Collection[str] = (),
    max_hops: int = 32,
    max_paths: int = 8,
) -> tuple[list[ControlPath], bool]:
    """Deterministic breadth-first search for the first `max_paths` acyclic
    paths from any start to any point the predicates accept.

    Determinism contract: starts are visited in sorted order, neighbours in
    (dst, edge_id) order, and the reported paths sort by (length, points). The
    per-path visited set makes cycles terminate without losing the second,
    longer way round a loop -- two genuinely different paths are two facts.
    Returns (paths, truncated), where `truncated` says some work was left
    unexplored because a cap fired.
    """
    blocked_edges = frozenset(blocked_edges)
    require = frozenset(require_flags)
    found: list[ControlPath] = []
    truncated = False
    for start in sorted(starts):
        if len(found) >= max_paths:
            truncated = True
            break
        start_info = points.get(start)
        if (
            start_info is None
            or (is_blocked is not None and is_blocked(start_info))
            or start in blocked_points
        ):
            continue
        queue: deque[tuple[str, tuple[str, ...], tuple[str, ...], frozenset[str]]] = deque()
        queue.append((start, (start,), (), frozenset({start})))
        while queue and len(found) < max_paths:
            current, point_ids, edge_ids, visited = queue.popleft()
            for edge_id, dst, flags in adjacency.get(current, ()):
                if len(found) >= max_paths:
                    break
                if edge_id in blocked_edges or not require <= flags:
                    continue
                if dst in visited or dst in blocked_points:
                    continue
                dst_info = points.get(dst)
                if dst_info is None:
                    continue
                if is_blocked is not None and is_blocked(dst_info):
                    continue
                next_points = point_ids + (dst,)
                next_edges = edge_ids + (edge_id,)
                if is_target(dst_info):
                    found.append(
                        ControlPath(
                            next_points,
                            tuple(points.get(pid, {}).get("event_type", "") for pid in next_points),
                            next_edges,
                        )
                    )
                if len(next_edges) >= max_hops:
                    continue
                queue.append((dst, next_points, next_edges, visited | {dst}))
        if queue and len(found) >= max_paths:
            truncated = True
    found.sort(key=lambda path: (len(path.points), path.points))
    return found, truncated
def _subject_matches(info: dict[str, Any], subject: str) -> bool:
    return bool(subject) and info.get("subject", "") == subject


# Matrix 2.1/2.2's shape: an allocation size computed by multiplying (or
# shifting) a runtime value. Only the operators that *grow* a value are read --
# `size + 1` cannot make a small size wrap on its own, while `count * elem`
# can, and emitting every arithmetic node in a translation unit would bury that
# distinction in noise.
SIZE_OPERATORS = frozenset({"*", "<<"})
_NUMERIC_LITERAL_KINDS = frozenset({
    "number_literal", "integer_literal", "float_literal", "char_literal",
})
_ARITH_WRAPPER_KINDS = frozenset({"parenthesized_expression", "cast_expression"})
_ARITH_TYPE_KINDS = frozenset({
    "type_descriptor", "type_identifier", "sized_type_specifier", "primitive_type",
})


def _unwrap_arithmetic(node: Any) -> Any:
    """Strip parentheses and casts down to the expression that computes a value.

    A cast changes the width the arithmetic happens in, which matters for the
    defect, but it does not change *which* expression multiplies. The width is
    not recorded here, so the cast is peeled and the fact stays about the
    multiplication.
    """
    while node is not None and node.type in _ARITH_WRAPPER_KINDS:
        inner = None
        for child in node.named_children:
            if child.type in _ARITH_TYPE_KINDS:
                continue
            inner = child
            break
        node = inner
    return node


def size_arithmetic(node: Any, source: bytes) -> list[dict[str, Any]]:
    """The multiplications inside an allocation call's argument list.

    One record per multiplication/shift, with the operands it combines and
    whether each is a compile-time literal. A product of two literals is
    emitted too -- a folded constant is a fact worth having, and the query is
    what decides it cannot wrap at run time.
    """
    def text(item: Any) -> str:
        return source[item.start_byte:item.end_byte].decode("utf-8", "replace").strip()

    arguments = None
    for child in node.named_children:
        if child.type == "argument_list":
            arguments = child
            break
    if arguments is None:
        return []

    records: list[dict[str, Any]] = []
    for argument in arguments.named_children:
        candidate = _unwrap_arithmetic(argument)
        if candidate is None or candidate.type != "binary_expression":
            continue
        operator_node = candidate.child_by_field_name("operator")
        operator = text(operator_node) if operator_node is not None else ""
        if operator not in SIZE_OPERATORS:
            continue
        left = candidate.child_by_field_name("left")
        right = candidate.child_by_field_name("right")
        if left is None or right is None:
            continue
        operands = []
        for side in (left, right):
            bare = _unwrap_arithmetic(side) or side
            operands.append({
                "text": text(bare),
                "literal": bare.type in _NUMERIC_LITERAL_KINDS,
                "node": bare,
            })
        records.append({
            "operator": operator,
            "operands": operands,
            "expression": text(candidate),
            "node": candidate,
        })
    return records

def unreleased_resources(
    edges: Iterable[Any],
    points: dict[str, dict[str, Any]],
    *,
    acquire: str = "ALLOC",
    release: str = "RELEASE",
    exclude_null_guard: bool = True,
    excluded: Collection[str] = (),
    max_hops: int = 64,
    max_paths: int = 8,
    adjacency: dict[str, list[tuple[str, str, frozenset[str]]]] | None = None,
) -> tuple[list[ControlPath], bool]:
    """A point of type `acquire` reaches the exit with no `release` of the same
    subject on the path.

    Parameterised in stage 4 so the same walk answers 4.1 (`ALLOC`/`RELEASE`)
    and the incomplete-cleanup half of 4.6 (`LOCK`/`UNLOCK`). The two differ in
    more than their type names:

    * `exclude_null_guard` is right for allocations and wrong for locks. A
      `true_when_null` guard on an allocation is "the allocation failed, return
      early" -- not a leak. The same guard on a lock is "the lock failed, return
      early" -- which is precisely the error path 4.6 exists to report, so the
      lock query turns the exclusion off.
    * `excluded` removes points as starts and as traversal targets rather than
      deleting them from `points`. Deleting would make `find_paths` skip paths
      that pass *through* the point (`dst_info is None`), silently weakening
      reachability for every other query in the same call.

    A subject-less acquire still produces candidates -- its block set is empty.
    Over-reporting is the intended bias for a candidate generator; the AI judge
    decides.

    `adjacency` is the caller's, when it has one: the defect layer runs this
    twice per `resource_lifetime` (once per mode) and both walks are over the
    same `edges`, so building it a third and fourth time bought nothing.
    """
    if adjacency is None:
        adjacency = build_adjacency(edges)
    excluded_set = frozenset(excluded)

    # Index the two lookups this walk makes per acquisition, instead of scanning
    # `points` for each one. The walk visits every acquire point, and each visit
    # used to filter the whole point map twice -- once for the releases of that
    # subject, once for the null checks on it. On a repo with A allocations and
    # P points that is O(A x P) with a dict.get per element, which is what
    # dominated a measured `resource_lifetime` run (61M lookups, 4.6M subject
    # comparisons, 3.0s of a 3.4s query) while the graph build beside it cost
    # 0.05s.
    #
    # The two indexes are keyed by the same `subject` string the per-visit scan
    # compared with `_subject_matches`, so every blocked point and blocked edge
    # is the same set as before -- this changes how the set is found, not what
    # it is. `_subject_matches` treats an empty subject as "matches nothing",
    # which the per-visit code keeps by only consulting the index when the
    # acquire has a subject.
    releases_by_subject: dict[str, set[str]] = {}
    null_checks_by_subject: dict[str, list[str]] = {}
    for pid, info in points.items():
        event_type = info.get("event_type")
        if event_type == release:
            subject = info.get("subject", "")
            if subject:
                releases_by_subject.setdefault(subject, set()).add(pid)
        elif (
            event_type == "CHECK"
            and info.get("polarity") == "true_when_null"
            and info.get("subject", "")
        ):
            null_checks_by_subject.setdefault(info["subject"], []).append(pid)

    found: list[ControlPath] = []
    truncated = False
    for start in sorted(
        pid
        for pid, info in points.items()
        if info.get("event_type") == acquire and pid not in excluded_set
    ):
        subject = points[start].get("subject", "")
        blocked = set(excluded_set)
        blocked_edges: set[str] = set()
        if subject:
            blocked |= releases_by_subject.get(subject, set())
        if subject and exclude_null_guard:
            for pid in null_checks_by_subject.get(subject, ()):
                for edge_id, _dst, flags in adjacency.get(pid, ()):
                    if BRANCH_TRUE in flags:
                        blocked_edges.add(edge_id)
        paths, more = find_paths(
            adjacency,
            points,
            starts={start},
            is_target=lambda info: info.get("event_type") == "EXIT",
            blocked_points=blocked,
            blocked_edges=blocked_edges,
            max_hops=max_hops,
            max_paths=max_paths,
        )
        found.extend(paths)
        truncated = truncated or more
    return found, truncated

def leaked_allocations(
    edges: Iterable[Any], points: dict[str, dict[str, Any]], *, max_hops: int = 64, max_paths: int = 8
) -> tuple[list[ControlPath], bool]:
    """Matrix 4.1 verbatim: ALLOC reaches the exit with no RELEASE of the same
    subject on the path. The stage 3 spelling of `unreleased_resources`."""
    return unreleased_resources(edges, points, max_hops=max_hops, max_paths=max_paths)

def unchecked_dereferences(
    edges: Iterable[Any], points: dict[str, dict[str, Any]], *, max_hops: int = 64, max_paths: int = 8
) -> tuple[list[ControlPath], bool]:
    """Matrix 3.1: a dereference reachable from the null side of a check on the
    same subject.

    `true_when_null` seeds from `branch=true` (`!p` true means p is null),
    `true_when_non_null` from `branch=false`. The `||` blind spot applies: a
    check whose condition is a short-circuit feeds both arms, and this pattern
    does not expand them -- the `short_circuit` flag makes those checkers
    queryable for stage 4.
    """
    adjacency = build_adjacency(edges)
    found: list[ControlPath] = []
    truncated = False
    checks = sorted(
        pid
        for pid, info in points.items()
        if info.get("event_type") == "CHECK"
        and bool(info.get("subject"))
        and info.get("polarity") in {"true_when_null", "true_when_non_null"}
    )
    for check_id in checks:
        info = points[check_id]
        wanted = BRANCH_TRUE if info["polarity"] == "true_when_null" else BRANCH_FALSE
        seeds = [dst for _edge_id, dst, flags in adjacency.get(check_id, ()) if wanted in flags]
        if not seeds:
            continue
        subject = info["subject"]
        paths, more = find_paths(
            adjacency,
            points,
            starts=seeds,
            is_target=lambda target_info, subject=subject: (
                target_info.get("event_type") == "DEREFERENCE" and _subject_matches(target_info, subject)
            ),
            max_hops=max_hops,
            max_paths=max_paths,
        )
        found.extend(paths)
        truncated = truncated or more
    return found, truncated

def use_after_release(
    edges: Iterable[Any], points: dict[str, dict[str, Any]], *, max_hops: int = 64, max_paths: int = 8
) -> tuple[list[ControlPath], bool]:
    """Matrix 4.3's first half: a dereference of a subject after its release.

    USE is DEREFERENCE-only in stage 3 (口径 2): passing the pointer to a
    callee is a registered gap. Aliases are invisible (`q = p; free(p);
    sink(q)` reports nothing, `free(p); p = NULL` guards nothing) -- that is
    the "confirmation slides to B" half of matrix 4.3, awaiting the DFG.
    """
    adjacency = build_adjacency(edges)
    found: list[ControlPath] = []
    truncated = False
    releases = sorted(
        pid for pid, info in points.items() if info.get("event_type") == "RELEASE" and bool(info.get("subject"))
    )
    for release_id in releases:
        subject = points[release_id]["subject"]
        paths, more = find_paths(
            adjacency,
            points,
            starts={release_id},
            is_target=lambda target_info, subject=subject: (
                target_info.get("event_type") == "DEREFERENCE" and _subject_matches(target_info, subject)
            ),
            max_hops=max_hops,
            max_paths=max_paths,
        )
        found.extend(paths)
        truncated = truncated or more
    return found, truncated


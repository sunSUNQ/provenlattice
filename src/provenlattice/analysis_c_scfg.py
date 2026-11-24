"""Sparse CFG materializer (I1-B) over the derived-analysis store.

Ported from PR #1's stage-3 walker and re-shaped for main's architecture, the
same way the I1-A events analyzer was:

* On demand only -- ``analyze --features sparse_cfg``; the default index never
  runs the walker. File x analyzer cached in AnalysisStore, fail-closed
  freshness with a dependency attestation (``dependencies`` =
  ``{"events:cpp": EVENTS_CONTRACT}``): a vocabulary/matcher upgrade
  invalidates every sparse CFG built under the previous one.
* The walker consumes the SAME hits the event layer consumed
  (``EventExtractor.extract_hits``), so an operation cannot be an event while
  being invisible to the CFG -- one matcher, two consumers, no drift.
* Owner binding and stable identity are shared with the events analyzer
  (analysis_semantic_common): vocabulary events get the same
  ``identity.event_id`` here that the events:cpp analyzer computes, and the
  walker's structural points (CHECK/BRANCH/DEREFERENCE) and access events
  (READ/WRITE) get ordinals from the walker's own source-order counters --
  the two families cannot collide because the structural types never come
  from the vocabulary.
* Published rows: one analysis_nodes row per event/point (kind = event type,
  payload carries the owner binding, span, matched facts and the point's
  annotations), one analysis_edges row per CONTROL_REACHES edge
  (``identity.semantic_edge_id``, flag set as discriminator, synthetic exit
  targets resolved as ``identity.cfg_exit_id``).
* Language scope: the C/C++ family (cpp.toml extensions); the C or C++
  grammar profile is chosen per suffix. Known precision boundaries (goto
  targets, macro invocations, single-line short-circuit collapse) travel with
  the PR walker unchanged and are surfaced as diagnostics, never as resolved
  claims.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from .analysis import (
    ANALYZER_VERSIONS,
    AnalysisEdge,
    AnalysisNode,
    AnalysisStore,
    PayloadTooLargeError,
    analyzer_contract,
    analyzer_id,
)
from .analysis_c_frontend import collect_atomic_facts
from .analysis_ast import normalize_scope, scoped_sources
from .models import ParsedPoint, PointKey
from .analysis_c_events import EVENTS_CONTRACT, EVENTS_SUFFIXES, VOCABULARY
from .analysis_semantic_common import (
    _LineIndex,
    owner_index,
    owner_symbol_id,
    tree_diagnostics,
)
from .identity import cfg_exit_id, event_id, path_id, semantic_edge_id
from .parsing.cpp import CppTreeSitterParser
from .parsing.declarations import DeclarationIndex
from .parsing.events import EventExtractor
from .semantics.vocabulary import vocabulary_for_path
from .sparsecfg import (
    CONTROL_REACHES,
    CPP_PROFILE,
    C_PROFILE,
    SparseCfgBuilder,
    _semantic_access_kind,
)
from .storage import SQLiteStorage

ANALYZER = analyzer_id("sparse_cfg", "cpp")
SCFG_VERSION = ANALYZER_VERSIONS[ANALYZER]
SCFG_CONTRACT = analyzer_contract("sparse_cfg", "cpp", SCFG_VERSION)
CAPABILITY_LEVEL = "level0+structural+access"

_C_SUFFIXES = frozenset({".c", ".h"})


# ---------------------------------------------------------------------------
# ATOMIC points (issue-pilot#89, G1)
#
# The walker publishes READ/WRITE/DEREFERENCE points and the vocabulary
# publishes atomic *operations*. Neither covers the two atomic shapes this
# issue is about, and the access layer deliberately filters ordinary local
# READ/WRITE points. So the points are added here, after the walker has
# assigned every existing ordinal: the new ATOMIC ordinals continue the
# owner's existing ATOMIC sequence, which keeps every vocabulary event id
# byte-identical (events:cpp and sparse_cfg must agree on those ids).
#
# No edge is added. `_touches_atomically` and `atomic_subjects` join an
# ATOMIC point to a race subject through the same subject annotations the
# access point carries, so the annotations are copied, never re-spelled.
# ---------------------------------------------------------------------------

_ATOMIC_ACCESS_TYPES = frozenset({"READ", "WRITE", "DEREFERENCE"})


def _walk_tree(root):
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.named_children))


def _node_text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _contains(outer, node) -> bool:
    return outer.start_byte <= node.start_byte and node.end_byte <= outer.end_byte


def _declarator_contains(declarator, node) -> bool:
    """Whether `node` is part of the declarator or its type, not its value.

    `int x = c;` spells the read of `c` inside the same `declaration` node as
    the name `x`; treating the whole initializer as declarator context would
    hide that read. An array's size expression is evaluated (`int a[n];` reads
    `n`), so only the array declarator's name is context -- not its extent.
    """
    current = declarator
    while current is not None:
        if current.type == "init_declarator":
            current = current.child_by_field_name("declarator")
            continue
        if current.type in {"array_declarator", "abstract_array_declarator"}:
            inner = current.child_by_field_name("declarator")
            return inner is not None and _contains(inner, node)
        if current.type in {
            "pointer_declarator", "reference_declarator",
            "function_declarator", "parenthesized_declarator",
        }:
            inner = current.child_by_field_name("declarator")
            if inner is not None and _contains(inner, node):
                return True
            return _contains(current, node)
        return _contains(current, node)
    return False


def _in_declaration_context(node) -> bool:
    """Whether `node` is a declarator or type spelling, not a use.

    A declaration's *initializer value* is an ordinary expression: in
    `int y = x;` the read of `x` is a real access. Only the type and the
    declarator chain are context.
    """
    ancestor = node.parent
    while ancestor is not None:
        if ancestor.type in {
            "declaration", "parameter_declaration", "field_declaration",
            "type_definition",
        }:
            type_node = ancestor.child_by_field_name("type")
            if type_node is not None and _contains(type_node, node):
                return True
            for declarator in ancestor.children_by_field_name("declarator"):
                if _declarator_contains(declarator, node):
                    return True
            return False
        if ancestor.type == "function_definition":
            declarator = ancestor.child_by_field_name("declarator")
            return declarator is not None and _contains(declarator, node)
        ancestor = ancestor.parent
    return False


def _is_callee(node) -> bool:
    parent = node.parent
    return (
        parent is not None
        and parent.type == "call_expression"
        and parent.child_by_field_name("function") is node
    )


def _member_of_root(node, source: bytes) -> tuple[str, object | None]:
    """The field name and field expression when `node` is the root of one."""
    parent = node.parent
    if parent is None or parent.type != "field_expression":
        return "", None
    if parent.child_by_field_name("argument") is not node:
        return "", None
    field = parent.child_by_field_name("field")
    if field is None:
        return "", None
    return _node_text(source, field), parent


def _is_address_expression(expression: str) -> bool:
    """Whether the access expression only takes the object's address.

    `&g` neither reads nor writes the atomic value; it is exactly the shape
    that later reaches the object through an unknown alias. It must not become
    an atomic fact.
    """
    return expression.lstrip(" \t\r\n(").startswith("&")


def _is_addressed_expression(node, source: bytes) -> bool:
    parent = node.parent
    while parent is not None and parent.type == "parenthesized_expression":
        node = parent
        parent = parent.parent
    return (
        parent is not None
        and parent.type == "pointer_expression"
        and _same_node(parent.child_by_field_name("argument"), node)
        and source[parent.start_byte:parent.start_byte + 1] == b"&"
    )


def _is_dereference_expression(expression: str) -> bool:
    """Whether an access expression reads/writes the pointee, not the pointer.

    `*p`, `p[i]`, `*(p + 1)` and their parenthesized spellings are pointee
    accesses; a bare `p`, `&p[i]` and `p->f` are not (the last is a member of a
    different object type).
    """
    stripped = expression.lstrip(" \t\r\n(")
    if not stripped or stripped.startswith("&"):
        return False
    return stripped.startswith("*") or "[" in stripped


_UNEVALUATED_NODES = frozenset({
    "sizeof_expression", "alignof_expression", "typeof_expression",
})


def _array_size(node):
    """The extent expression of an array declarator, if it has one."""
    size = node.child_by_field_name("size")
    if size is not None:
        return size
    declared = node.child_by_field_name("declarator")
    remaining = [
        child for child in node.named_children
        if declared is None
        or child.start_byte != declared.start_byte
        or child.end_byte != declared.end_byte
    ]
    return remaining[-1] if remaining else None


def _in_any_vla_bound(node) -> bool:
    """Whether `node` is evaluated as a VLA extent inside an ordinary sizeof."""
    ancestor = node.parent
    while ancestor is not None:
        if ancestor.type in _UNEVALUATED_NODES:
            return _in_vla_bound(node, ancestor)
        ancestor = ancestor.parent
    return False


def _in_vla_bound(node, boundary) -> bool:
    """Whether `node` is an array extent inside `boundary`.

    `sizeof(int[n])` is usually unevaluated, but a variable-length array's
    extent is evaluated, so the read of `n` is a real access.
    """
    ancestor = node.parent
    while ancestor is not None and ancestor is not boundary:
        if ancestor.type in {"array_declarator", "abstract_array_declarator"}:
            size = _array_size(ancestor)
            if (
                size is not None
                and size.start_byte <= node.start_byte
                and node.end_byte <= size.end_byte
            ):
                return True
        ancestor = ancestor.parent
    return False


def _in_unevaluated_context(node) -> bool:
    """Whether `node` is an operand the language does not evaluate.

    `sizeof(g)` names `g` but reads nothing; publishing an access for it would
    turn a compile-time query into a runtime race fact. `_Generic`'s
    controlling expression is unevaluated, while its selected association is
    an ordinary expression. A VLA extent inside `sizeof` is evaluated.
    """
    ancestor = node.parent
    while ancestor is not None:
        if ancestor.type in _UNEVALUATED_NODES:
            return not _in_vla_bound(node, ancestor)
        if ancestor.type == "generic_expression" and ancestor.named_children:
            control = ancestor.named_children[0]
            if (
                control.start_byte <= node.start_byte
                and node.end_byte <= control.end_byte
            ):
                return True
        if ancestor.type in {"function_definition", "translation_unit"}:
            return False
        ancestor = ancestor.parent
    return False


def _unevaluated_spans(root) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]:
    """Unevaluated spans and the VLA-extent spans evaluated inside them."""
    unevaluated: list[tuple[int, int]] = []
    evaluated: list[tuple[int, int]] = []
    for node in _walk_tree(root):
        if node.type in _UNEVALUATED_NODES:
            unevaluated.append((node.start_byte, node.end_byte))
            for inner in _walk_tree(node):
                if inner.type in {"array_declarator", "abstract_array_declarator"}:
                    size = _array_size(inner)
                    if size is not None:
                        evaluated.append((size.start_byte, size.end_byte))
        elif node.type == "generic_expression" and node.named_children:
            control = node.named_children[0]
            unevaluated.append((control.start_byte, control.end_byte))
    return tuple(unevaluated), tuple(evaluated)


def _inside_spans(
    byte: int,
    spans: tuple[tuple[int, int], ...],
    evaluated: tuple[tuple[int, int], ...] = (),
) -> bool:
    """Whether the innermost enclosing span is unevaluated.

    A VLA extent inside `sizeof` is evaluated, while a `_Generic` controlling
    expression inside that extent is still unevaluated. The narrowest enclosing
    span decides; looking for any evaluated span first would hide the nested
    unevaluated context.
    """
    candidates = [
        (end - start, True)
        for start, end in spans
        if start <= byte < end
    ]
    candidates.extend(
        (end - start, False)
        for start, end in evaluated
        if start <= byte < end
    )
    if not candidates:
        return False
    return min(candidates, key=lambda item: item[0])[1]


def _root_is_dereferenced(node, source: bytes) -> bool:
    """Whether `node` is the operand of a `*` through casts/parentheses.

    `*(int *)p` puts a cast between the identifier and the dereference, so the
    expression text recovered from the identifier alone does not start with
    `*`. Walking the ancestor chain keeps the judgement on syntax.
    """
    current = node
    while True:
        parent = current.parent
        if parent is None:
            return False
        if parent.type in {"parenthesized_expression", "cast_expression"}:
            current = parent
            continue
        if parent.type == "binary_expression":
            current = parent
            continue
        argument = parent.child_by_field_name("argument")
        if parent.type == "subscript_expression" and argument is not None:
            if (
                argument.start_byte == current.start_byte
                and argument.end_byte == current.end_byte
            ):
                return True
            return False
        if (
            parent.type == "pointer_expression"
            and argument is not None
            and argument.start_byte == current.start_byte
            and argument.end_byte == current.end_byte
            and source[parent.start_byte:parent.start_byte + 1] == b"*"
        ):
            return True
        return False


def _same_node(left, right) -> bool:
    return (
        left is not None
        and left.start_byte == right.start_byte
        and left.end_byte == right.end_byte
    )


def _access_expression(node, source: bytes):
    """The whole access expression an identifier roots (`a[i]`, `*a`, `(a)`).

    Casts and parentheses are climbed as well: in `((int *)p)[0]` the
    identifier `p` designates the subscripted access, not a bare pointer read.
    """
    current = node
    while True:
        parent = current.parent
        if parent is None:
            break
        argument = parent.child_by_field_name("argument")
        if parent.type == "subscript_expression" and _same_node(argument, current):
            current = parent
            continue
        if (
            parent.type == "pointer_expression"
            and _same_node(argument, current)
            and source[parent.start_byte:parent.start_byte + 1] == b"*"
        ):
            current = parent
            continue
        if parent.type in {"parenthesized_expression", "cast_expression"}:
            current = parent
            continue
        if parent.type == "binary_expression":
            current = parent
            continue
        break
    return current


def _node_at_span(root, start: int, end: int):
    """The named node with exactly this span, or None."""
    for node in _walk_tree(root):
        if node.start_byte == start and node.end_byte == end:
            return node
    return None


def _is_element_access(node, source: bytes) -> bool:
    """Whether the expression reads/writes an array element or pointee.

    A bare array identifier (`p = a`, `sink(a)`, `a + 1`) converts to a pointer
    and touches no element; only a subscript or `*` access does.
    """
    if node is None:
        return False
    if node.type == "subscript_expression":
        return True
    return (
        node.type == "pointer_expression"
        and source[node.start_byte:node.start_byte + 1] == b"*"
    )


_NESTED_MEMBER = re.compile(
    r"[A-Za-z_][A-Za-z_0-9]*\s*(?:\.|->)\s*[A-Za-z_][A-Za-z_0-9]*"
    r"\s*(?:\.|->)\s*[A-Za-z_][A-Za-z_0-9]*"
)


def _nested_member_expression(expression: str) -> bool:
    return bool(_NESTED_MEMBER.search(expression or ""))


def _subject_declaration(declarations, byte: int, subject: str, annotations):
    if declarations is None or not subject:
        return None
    declaration = declarations.resolve(byte, subject)
    if declaration is None and annotations.get("subject_storage") == "field":
        class_name = declarations.enclosing_class(byte)
        if class_name:
            declaration = declarations.resolve_member(byte, class_name, subject)
    return declaration


def _atomic_member(atomic, declarations, byte: int, declaration, member: str) -> bool:
    if not member:
        return False
    if (
        declaration is not None
        and atomic.is_atomic_member(declaration.type_token, member)
    ):
        return True
    if declarations is None or declaration is None:
        return False
    member_declaration = declarations.resolve_member(byte, declaration.type_token, member)
    return atomic.is_atomic_declaration(member_declaration)


def _atomic_source_for_annotations(atomic, declarations, owners, byte: int, annotations) -> str:
    """Why this point's subject is atomic, or "" when it is not."""
    if _is_address_expression(annotations.get("expression", "")):
        return ""
    if atomic.inside_region(byte):
        return "atomic_block"
    subject = annotations.get("subject", "")
    member = annotations.get("subject_member", "")
    declaration = _subject_declaration(declarations, byte, subject, annotations)
    expression = annotations.get("expression", "") or ""
    dereferenced = _is_dereference_expression(expression)
    if _atomic_member(atomic, declarations, byte, declaration, member):
        return "type_qualifier"
    if atomic.is_atomic_array(declaration) and dereferenced:
        return "type_qualifier"
    if atomic.is_atomic_declaration(declaration) and not dereferenced:
        return "type_qualifier"
    if atomic.is_atomic_pointee(declaration) and dereferenced:
        return "type_qualifier"
    if declaration is None and subject:
        owner = owners.owner_of(byte, byte) if owners is not None else None
        recovered = atomic.recovered_declaration(
            subject,
            owner.start_byte if owner is not None else None,
            owner.end_byte if owner is not None else None,
            byte,
        )
        if recovered is not None:
            expression = annotations.get("expression", "") or ""
            dereferenced = _is_dereference_expression(expression)
            if recovered.kind == "pointee":
                if dereferenced:
                    return "type_specifier"
            elif recovered.kind == "array":
                if dereferenced:
                    return "type_specifier"
            elif not dereferenced:
                return "type_specifier"
    return ""


def _recovered_name_node(atomic, node) -> bool:
    return any(
        declaration.name_start == node.start_byte
        and declaration.name_end == node.end_byte
        for declaration in atomic.recovered
    )


def _atomic_subject_facts(builder, declaration, subject: str, member: str, exact: str):
    if declaration is not None:
        facts = builder._facts_for(declaration, member, exact)
    else:
        facts = {
            "subject_storage": "unknown", "subject_type": "",
            "subject_decl": f"unknown:{subject}",
            "subject_member": member, "subject_exact": exact,
        }
    facts["subject"] = subject
    return facts


def _atomic_candidate_key(candidate) -> tuple:
    return (
        candidate["owner_kind"], candidate["owner_qualified_name"],
        candidate["owner_signature"], candidate["start_byte"],
        candidate["end_byte"], candidate["annotations"].get("subject_decl", ""),
        candidate["annotations"].get("subject", ""),
    )


def _collect_atomic_candidates(
    cfg, root, builder, declarations, owners, atomic, source: bytes, cpp: bool,
) -> tuple[list[dict], list[str]]:
    """Existing access points plus a bounded scan for local atomic uses.

    Returns the candidates and the scan's own limitations (currently the
    unresolved-alias shapes that cannot be attributed to an atomic object).
    """

    candidates: list[dict] = []
    covered: set[tuple] = set()
    covered_spans: set[tuple] = set()
    limitations: list[str] = []
    has_atomic_objects = bool(
        atomic.declaration_keys
        or atomic.recovered
        or atomic.array_keys
        or atomic.pointee_keys
    )
    unevaluated, evaluated = _unevaluated_spans(root)

    def append(owner, start_byte: int, end_byte: int, expression: str, annotations: dict) -> None:
        candidates.append({
            "owner_kind": owner.kind,
            "owner_qualified_name": owner.qualified_name,
            "owner_signature": owner.signature,
            "start_byte": start_byte,
            "end_byte": end_byte,
            "matched_name": expression,
            "annotations": dict(annotations),
        })

    def cover(owner, start_byte: int, end_byte: int, subject: str) -> None:
        covered.add((
            owner.kind, owner.qualified_name, owner.signature,
            start_byte, end_byte, subject,
        ))

    # 1. Every access point the walker already published: its subject identity
    #    is the one the race query compares, so copy it verbatim.
    for point in cfg.points:
        if point.event_type not in _ATOMIC_ACCESS_TYPES:
            continue
        if point.start_byte is None or point.end_byte is None:
            continue
        if _inside_spans(point.start_byte, unevaluated, evaluated):
            continue
        point_node = _node_at_span(root, point.start_byte, point.end_byte)
        if _is_addressed_expression(point_node, source):
            # `&a[0]` computes an address; it neither reads nor writes the
            # element, even inside an atomic region.
            continue
        annotations = cfg.annotations.get(point.key()) or {}
        if not annotations.get("subject"):
            continue
        atomic_source = _atomic_source_for_annotations(
            atomic, declarations, owners, point.start_byte, annotations)
        if not atomic_source:
            if (
                has_atomic_objects
                and _nested_member_expression(annotations.get("expression", ""))
            ):
                limitations.append(
                    f"atomic_member_chain_unsupported@{point.start_byte}")
            continue
        owner = owners.owner_of(point.start_byte, point.end_byte)
        if owner is None:
            continue
        annotations = dict(annotations)
        annotations["atomic_source"] = atomic_source
        annotations["atomic_access"] = annotations.get("access_kind", point.event_type)
        append(owner, point.start_byte, point.end_byte, point.matched_name, annotations)
        cover(owner, point.start_byte, point.end_byte, annotations.get("subject", ""))
        covered_spans.add((
            owner.kind, owner.qualified_name, owner.signature,
            point.start_byte, point.end_byte,
        ))

    # 2. Local atomic uses: the access layer filters ordinary local READ/WRITE,
    #    so `_Atomic int c; c++;` has no point to copy. Only direct identifier
    #    and direct member uses are modelled; deeper paths stay limitations.
    for node in _walk_tree(root):
        if node.type != "identifier":
            continue
        if _in_unevaluated_context(node):
            continue
        if _is_callee(node) or _in_declaration_context(node):
            continue
        if _recovered_name_node(atomic, node):
            continue
        subject = _node_text(source, node)
        member, member_expression = _member_of_root(node, source)
        base_expression = member_expression if member_expression is not None else node
        expression_node = _access_expression(base_expression, source)
        if _is_addressed_expression(expression_node, source):
            continue
        declaration = (
            declarations.resolve(node.start_byte, subject) if declarations is not None else None
        )
        inside_region = atomic.inside_region(expression_node.start_byte)
        owner = owners.owner_of(expression_node.start_byte, expression_node.end_byte)
        if owner is None:
            continue
        span_key = (
            owner.kind, owner.qualified_name, owner.signature,
            expression_node.start_byte, expression_node.end_byte,
        )
        if span_key in covered_spans:
            continue
        expression_text = _node_text(source, expression_node)
        dereferenced = (
            _is_dereference_expression(expression_text)
            or _root_is_dereferenced(node, source)
        )
        atomic_source = ""
        recovered = None
        if declaration is not None:
            if member:
                if _atomic_member(atomic, declarations, node.start_byte, declaration, member):
                    atomic_source = "type_qualifier"
                elif inside_region:
                    atomic_source = "atomic_block"
            elif atomic.is_atomic_array(declaration) and _is_element_access(
                expression_node, source
            ):
                atomic_source = "type_qualifier"
            elif atomic.is_atomic_declaration(declaration) and not dereferenced:
                atomic_source = "type_qualifier"
            elif atomic.is_atomic_pointee(declaration) and dereferenced:
                atomic_source = "type_qualifier"
            elif inside_region:
                atomic_source = "atomic_block"
        else:
            recovered = atomic.recovered_declaration(
                subject, owner.start_byte, owner.end_byte, node.start_byte)
            if recovered is not None:
                # `_Atomic(int *) p` makes the pointer object atomic, not the
                # plain int it points at: only a dereference of `p` is atomic.
                # An array of atomic elements is atomic for its element
                # accesses; a plain object for non-dereference uses.
                if recovered.kind == "pointee":
                    if dereferenced:
                        atomic_source = "type_specifier"
                elif recovered.kind == "array":
                    if _is_element_access(expression_node, source):
                        atomic_source = "type_specifier"
                elif not dereferenced:
                    atomic_source = "type_specifier"
                if not atomic_source and inside_region:
                    atomic_source = "atomic_block"
            elif inside_region:
                atomic_source = "atomic_block"
        if not atomic_source:
            if has_atomic_objects and _nested_member_expression(expression_text):
                limitations.append(
                    f"atomic_member_chain_unsupported@{expression_node.start_byte}")
            if (
                has_atomic_objects
                and recovered is None
                and dereferenced
                and (
                    declaration is None
                    or declaration.type_token in {"", "void"}
                )
            ):
                # A write/read through a pointer whose pointee type the graph
                # cannot name may reach an atomic object. It is not an atomic
                # fact; it is an explicit unknown.
                limitations.append(
                    f"atomic_alias_unresolved@{expression_node.start_byte}")
            continue
        access = _semantic_access_kind(
            expression_node, "DEREFERENCE", source, cpp=cpp)
        if access is None and _in_any_vla_bound(node):
            # `sizeof(int[n])` is a sizeof, but the VLA extent is evaluated:
            # the read of `n` is a real access.
            access = "READ"
        if access is None:
            continue
        key = (
            owner.kind, owner.qualified_name, owner.signature,
            expression_node.start_byte, expression_node.end_byte, subject,
        )
        if key in covered:
            continue
        facts = _atomic_subject_facts(
            builder, declaration, subject, member, "true")
        expression = _node_text(source, expression_node)
        annotations = {"expression": expression}
        annotations.update(facts)
        annotations["atomic_source"] = atomic_source
        annotations["atomic_access"] = access
        annotations["access_kind"] = access
        annotations["is_write"] = "true" if access in {"WRITE", "READ_MODIFY_WRITE"} else "false"
        append(owner, expression_node.start_byte, expression_node.end_byte, expression, annotations)
        covered.add(key)
    return candidates, limitations


def _inject_atomic_points(cfg, candidates: list[dict], lines) -> int:
    """Append ATOMIC points after the walker's ordinals, without touching ids.

    New ordinals continue each owner's existing ATOMIC sequence. Vocabulary
    ATOMIC events keep the ordinals the walker assigned them, so their event
    ids still equal the events:cpp layer's.
    """
    max_ordinal: dict[tuple[str, str, str], int] = {}
    existing: set[tuple] = set()
    for point in cfg.points:
        if point.event_type != "ATOMIC":
            continue
        owner = (point.owner_kind, point.owner_qualified_name, point.owner_signature)
        max_ordinal[owner] = max(max_ordinal.get(owner, -1), point.ordinal)
        annotations = cfg.annotations.get(point.key()) or {}
        existing.add((
            owner, point.start_byte, point.end_byte,
            annotations.get("subject_decl", ""), annotations.get("subject", ""),
        ))

    unique: dict[tuple, dict] = {}
    access_rank = {"READ": 0, "WRITE": 1, "READ_MODIFY_WRITE": 2}
    for candidate in candidates:
        owner = (
            candidate["owner_kind"], candidate["owner_qualified_name"],
            candidate["owner_signature"],
        )
        key = (
            owner, candidate["start_byte"], candidate["end_byte"],
            candidate["annotations"].get("subject_decl", ""),
            candidate["annotations"].get("subject", ""),
        )
        if key in existing:
            continue
        previous = unique.get(key)
        if previous is None:
            unique[key] = candidate
            continue
        # A read-modify-write produces both a READ and a WRITE point at the
        # same span. One ATOMIC fact is enough; keep the stronger direction.
        if access_rank.get(candidate["annotations"].get("atomic_access"), -1) > (
            access_rank.get(previous["annotations"].get("atomic_access"), -1)
        ):
            unique[key] = candidate

    next_ordinal = dict(max_ordinal)
    added = 0
    for key in sorted(unique, key=lambda item: (item[0], item[1], item[2], item[3], item[4])):
        candidate = unique[key]
        owner = key[0]
        ordinal = next_ordinal.get(owner, -1) + 1
        next_ordinal[owner] = ordinal
        point = ParsedPoint(
            event_type="ATOMIC",
            owner_kind=candidate["owner_kind"],
            owner_qualified_name=candidate["owner_qualified_name"],
            owner_signature=candidate["owner_signature"],
            ordinal=ordinal,
            start_line=lines.line_of(candidate["start_byte"], False),
            end_line=lines.line_of(candidate["end_byte"], True),
            matched_name=candidate["matched_name"],
            matched_via="structural",
            flags=(),
            start_byte=candidate["start_byte"],
            end_byte=candidate["end_byte"],
        )
        cfg.points.append(point)
        cfg.annotations[point.key()] = candidate["annotations"]
        added += 1
    return added


def analyze_c_scfg_scope(
    repo: str | Path, scope: str, database: str | Path | None = None
) -> dict:
    started = time.perf_counter()
    root = Path(repo).resolve()
    scope_path = normalize_scope(scope)
    if not (root.joinpath(*scope_path.parts)).is_dir():
        raise ValueError(f"scope directory does not exist: {scope}")
    database = Path(database).resolve() if database else root / ".provenlattice" / "codegraph.db"
    scoped = scoped_sources(root, scope_path)
    materialized: list[str] = []
    reused: list[str] = []
    skipped_unsupported: list[str] = []
    skipped_not_in_base: list[str] = []
    skipped_base_out_of_date: list[str] = []
    skipped_no_points: list[str] = []
    skipped_payload_too_large: list[str] = []
    atomic_limitations: set[str] = set()
    counters = {
        "points_published": 0, "edges_published": 0,
        "events_outside_owner": 0,
        "functions_bound": 0, "functions_unbound": 0,
        "atomic_points_published": 0,
    }
    nodes_written = 0
    edges_written = 0
    parser = CppTreeSitterParser(language="cpp")
    with SQLiteStorage(database) as storage:
        repository = storage.repository()
        if not repository:
            raise RuntimeError("repository is not indexed; run `provenlattice index` first")
        repo_id = repository["repo_id"]
        store = AnalysisStore(storage)
        # One transaction for the whole file loop instead of one commit per
        # file; see AnalysisStore.defer_commit for the measurement.
        store.defer_commit()
        for source in scoped:
            if Path(source.relative_path).suffix.lower() not in EVENTS_SUFFIXES:
                skipped_unsupported.append(source.relative_path)
                continue
            file_id = path_id(repo_id, "File", source.relative_path)
            base_hash = store.base_source_hash(file_id)
            if base_hash is None:
                skipped_not_in_base.append(source.relative_path)
                continue
            if base_hash != source.source_hash:
                skipped_base_out_of_date.append(source.relative_path)
                continue
            state = store.get_analysis_state(file_id, ANALYZER)
            if (
                state is not None
                and state.get("metadata", {}).get("contract") == SCFG_CONTRACT
                and state.get("metadata", {}).get("analyzer") == ANALYZER
                and store.is_analysis_fresh(file_id, ANALYZER, base_hash, SCFG_VERSION)
            ):
                reused.append(source.relative_path)
                continue
            source_bytes = source.path.read_bytes()
            outcome = parser.parse_bytes(source_bytes, source.relative_path)
            lines = _LineIndex(source_bytes)
            owners, owner_counters, owner_ids = owner_index(
                store, file_id, outcome.tree.root_node, source_bytes)
            extractor = EventExtractor(source_bytes, VOCABULARY, owners, lines.line_of)
            hits = extractor.extract_hits(outcome.tree.root_node)
            declarations = DeclarationIndex.build(
                source_bytes, source.relative_path, outcome.tree.root_node)
            atomic = collect_atomic_facts(outcome.tree.root_node, source_bytes, owners)
            suffix = Path(source.relative_path).suffix.lower()
            profile = C_PROFILE if suffix in _C_SUFFIXES else CPP_PROFILE
            builder = SparseCfgBuilder(
                source_bytes, owners, hits, lines.line_of, profile,
                declarations=declarations,
                out_param=VOCABULARY.out_param_names("ALLOC"),
            )
            cfg = builder.build(outcome.tree.root_node)
            atomic_candidates, atomic_scan_limitations = _collect_atomic_candidates(
                cfg, outcome.tree.root_node, builder, declarations, owners,
                atomic, source_bytes, profile.name == "cpp")
            atomic_published = _inject_atomic_points(cfg, atomic_candidates, lines)
            atomic_limitations_all = tuple(sorted((
                *atomic.limitations, *atomic_scan_limitations)))
            diagnostics = tree_diagnostics(outcome.tree.root_node)

            # -- publish: vocabulary events + walker points under one identity
            id_by_key: dict = {}
            nodes: list[AnalysisNode] = []
            for hit in hits:
                event = hit.event
                owner = owner_symbol_id(owner_ids, event)
                key = PointKey(event.owner_kind, event.owner_qualified_name,
                               event.owner_signature, event.event_type,
                               event.ordinal)
                node_id = event_id(repo_id, owner, event.event_type, event.ordinal)
                id_by_key[key] = node_id
                payload = {
                    "owner_symbol_id": owner,
                    "file_id": file_id,
                    "owner_kind": event.owner_kind,
                    "owner_qualified_name": event.owner_qualified_name,
                    "owner_signature": event.owner_signature,
                    "ordinal": event.ordinal,
                    "start_byte": hit.start_byte, "end_byte": hit.end_byte,
                    "start_line": event.start_line, "end_line": event.end_line,
                    "matched_name": event.matched_name,
                    "matched_via": event.matched_via,
                    "flags": list(event.flags),
                    "analyzer": ANALYZER, "contract": SCFG_CONTRACT,
                    "language": VOCABULARY.language, "level": CAPABILITY_LEVEL,
                }
                # annotations travel on the node they describe -- vocabulary
                # events included (PR: the annotations dict covers them too,
                # subject facts have nowhere else to travel)
                annotations = cfg.annotations.get(key) or {}
                if annotations:
                    payload["annotations"] = dict(annotations)
                nodes.append(AnalysisNode(node_id, event.event_type, payload))
            for point in cfg.points:
                owner = owner_symbol_id(owner_ids, point)
                key = PointKey(point.owner_kind, point.owner_qualified_name,
                               point.owner_signature, point.event_type,
                               point.ordinal)
                node_id = event_id(repo_id, owner, point.event_type, point.ordinal)
                id_by_key[key] = node_id
                payload = {
                    "owner_symbol_id": owner,
                    "file_id": file_id,
                    "owner_kind": point.owner_kind,
                    "owner_qualified_name": point.owner_qualified_name,
                    "owner_signature": point.owner_signature,
                    "ordinal": point.ordinal,
                    "start_byte": point.start_byte, "end_byte": point.end_byte,
                    "start_line": point.start_line, "end_line": point.end_line,
                    "matched_name": point.matched_name,
                    "matched_via": point.matched_via,
                    "flags": list(point.flags),
                    "analyzer": ANALYZER, "contract": SCFG_CONTRACT,
                    "language": VOCABULARY.language, "level": CAPABILITY_LEVEL,
                }
                # annotations travel on the node they describe (PR: the
                # metadata column takes them without a schema change)
                annotations = cfg.annotations.get(point.key()) or {}
                if annotations:
                    payload["annotations"] = dict(annotations)
                nodes.append(AnalysisNode(node_id, point.event_type, payload))

            # -- publish CONTROL_REACHES edges (exit resolves per source owner)
            edges: list[AnalysisEdge] = []
            for edge in cfg.edges:
                src_id = id_by_key.get(edge.src)
                if src_id is None:
                    raise RuntimeError(
                        f"sparse cfg edge source was never published: {edge.src}")
                src_owner = _owner_of_key(owner_ids, edge.src)
                if edge.dst is None:
                    dst_id = cfg_exit_id(repo_id, src_owner)
                else:
                    dst_id = id_by_key.get(edge.dst)
                    if dst_id is None:
                        raise RuntimeError(
                            f"sparse cfg edge target was never published: {edge.dst}")
                edges.append(AnalysisEdge(
                    semantic_edge_id(src_id, dst_id, CONTROL_REACHES,
                                     "\x1f".join(sorted(edge.flags))),
                    src_id, dst_id, CONTROL_REACHES,
                    {"owner_symbol_id": src_owner,
                     "flags": list(sorted(edge.flags)),
                     "analyzer": ANALYZER, "contract": SCFG_CONTRACT},
                ))

            try:
                store.replace_analysis_for_file(
                    file_id, ANALYZER, base_hash, SCFG_VERSION, nodes, edges,
                    metadata={
                        "analyzer": ANALYZER, "contract": SCFG_CONTRACT,
                        "language": VOCABULARY.language, "level": CAPABILITY_LEVEL,
                        "scope": scope_path.as_posix(),
                        "event_count": len(nodes), "edge_count": len(edges),
                        "atomic_points": atomic_published,
                        "atomic_limitations": list(atomic_limitations_all),
                        "events_outside_owner": extractor.skipped_outside_owner,
                        "dependencies": {"events:cpp": EVENTS_CONTRACT},
                        **owner_counters,
                        **diagnostics,
                        "analysis_status": "degraded" if diagnostics["partial"] else "complete",
                    },
                )
            except PayloadTooLargeError:
                skipped_payload_too_large.append(source.relative_path)
                continue
            if not nodes:
                # A file whose methods contain no events and no structural
                # points (rare: every return emits a point) still persists its
                # empty state so the freshness contract answers repeats.
                skipped_no_points.append(source.relative_path)
            materialized.append(source.relative_path)
            counters["points_published"] += len(nodes)
            counters["edges_published"] += len(edges)
            counters["atomic_points_published"] += atomic_published
            atomic_limitations.update(atomic_limitations_all)
            counters["events_outside_owner"] += extractor.skipped_outside_owner
            counters["functions_bound"] += owner_counters["functions_bound"]
            counters["functions_unbound"] += owner_counters["functions_unbound"]
            nodes_written += len(nodes)
            edges_written += len(edges)
    return {
        "repo_id": repo_id,
        "database": str(database),
        "scope": scope_path.as_posix(),
        "analyzer": ANALYZER,
        "contract": SCFG_CONTRACT,
        "feature_version": SCFG_VERSION,
        "level": CAPABILITY_LEVEL,
        "scope_source_files": len(scoped),
        "materialized": sorted(materialized),
        "reused": sorted(reused),
        "skipped_unsupported": sorted(skipped_unsupported),
        "skipped_not_in_base": sorted(skipped_not_in_base),
        "skipped_base_out_of_date": sorted(skipped_base_out_of_date),
        "skipped_no_points": sorted(skipped_no_points),
        "skipped_payload_too_large": sorted(skipped_payload_too_large),
        "points_published": counters["points_published"],
        "edges_published": counters["edges_published"],
        "atomic_points_published": counters["atomic_points_published"],
        "atomic_limitations": sorted(atomic_limitations),
        "events_outside_owner": counters["events_outside_owner"],
        "functions_bound": counters["functions_bound"],
        "functions_unbound": counters["functions_unbound"],
        "nodes_written": nodes_written,
        "edges_written": edges_written,
        "analyze_time_ms": (time.perf_counter() - started) * 1000,
    }


def _owner_of_key(owner_ids: dict, key) -> str:
    identity = (key.owner_kind, key.owner_qualified_name, key.owner_signature)
    if identity not in owner_ids or owner_ids[identity] is None:
        raise RuntimeError(f"sparse cfg point owner is unresolvable: {key}")
    return owner_ids[identity]

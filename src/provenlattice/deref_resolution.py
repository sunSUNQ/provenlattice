"""S7-F2: restricted query-time ``DEREF_RESOLVES_TO`` derivation (Issue #48).

SUB-07 step 2 consumes S7-F1's ``thread_argument_decl_scoped`` (produced on
THREAD_SPAWN, contract §1.3) together with the existing ``alias`` /
``alias_source`` facts to resolve a *thread-entry* dereference (``*f``) back to
the storage object whose address was passed to ``pthread_create``.

The derivation is strictly three-state (contract §5.11.1 / §1.5 / §1.6):

* ``must``    — provable identity chain only: ``form == address_of`` AND the
  entry function has a single parameter AND the dereferenced pointer is an
  unconditional, unique frame-local bare copy of that parameter AND there is no
  runtime instance ambiguity (exactly one distinct scoped identity per entry
  function).
* ``may``     — any weaker evidence (address form missing, conditional or
  multi-source copy, multiple distinct spawns, or an unresolvable parameter
  name). Never upgraded to ``must``.
* ``unknown`` — no evidence at all (no spawn for the function, or the passed
  declaration is unresolved/empty).

``same_storage=true`` is emitted only for cross-owner dereference pairs that
BOTH resolve with ``must`` to the same scoped identity (contract §1.6); a
``may``/``unknown`` resolution is never treated as ``false`` and never promotes
to ``true``.

Default OFF (contract §1.8): with ``enable=False`` the function returns an empty
derivation, so the pre-existing envelope (and FIX-05's 0-candidate behavior) is
byte-for-byte unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from .analysis_query import query_analysis
from .models import STORAGE_LOCAL, STORAGE_PARAMETER
from .parsing.cpp import CppTreeSitterParser
from .parsing.declarations import DeclarationIndex

_MUST = "must"
_MAY = "may"
_UNKNOWN = "unknown"


def _text_of(source: bytes, node: Any) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _operator_of(node: Any, source: bytes) -> str:
    """The operator token of an expression node, whatever the grammar names it."""
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


def _unwrap_parentheses(node: Any) -> Any:
    while node is not None and node.type == "parenthesized_expression":
        node = node.named_children[0] if node.named_children else None
    return node


def _annotations(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return event.get("annotations") or {}


def _sole_param_name(signature: str | None) -> str | None:
    """The single parameter name of a function signature, or ``None``.

    A pthread thread entry is always ``void *(*)(void *)``, so a well-formed
    signature has exactly one parameter. ``None`` means "not a single-argument
    entry" and forces a ``may`` downgrade rather than a guessed resolution.
    """
    if not signature:
        return None
    inner = signature.strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    inner = inner.strip()
    if not inner:
        return None
    parts = [part.strip() for part in inner.split(",")]
    if len(parts) != 1:
        return None
    token = parts[0].split()[-1] if parts[0].split() else ""
    return token.lstrip("*") or None


def _resolve_deref(
    event: Mapping[str, Any],
    alias: str,
    spawns: list[Mapping[str, str]],
    writes: list[Mapping[str, str]],
) -> tuple[str, str]:
    """Return ``(confidence, scoped_identity)`` for one DEREFERENCE event."""
    if not spawns:
        return (_UNKNOWN, "")  # not a known thread entry: no chain to resolve.

    scoped_ids = {spawn["scoped"] for spawn in spawns}
    forms = {spawn["form"] for spawn in spawns}
    if len(scoped_ids) != 1:
        return (_MAY, "")  # multiple distinct bindings: runtime ambiguity.
    scoped = next(iter(scoped_ids))
    if not scoped:
        return (_UNKNOWN, "")  # passed declaration is unresolved/undeclared.

    if forms != {"address_of"}:
        return (_MAY, scoped)  # not a provable address pass (e.g. pointer_var).

    # Single-argument entry: the dereferenced pointer's alias must be the
    # function's sole parameter, and that pointer must be an unconditional,
    # unique bare copy of the parameter (contract §1.5 frame-local chain).
    param = _sole_param_name(event.get("owner_signature"))
    if param is None or alias != param:
        return (_MAY, scoped)
    if not writes or {write["write_source"] for write in writes} != {alias}:
        return (_MAY, scoped)  # not a unique bare copy: conditional/multi-source.
    if any(write["unconditional"] != "true" for write in writes):
        return (_MAY, scoped)

    return (_MUST, scoped)


def _side(record: Mapping[str, Any]) -> dict[str, Any]:
    """One side of a same-storage dereference pair."""
    return {
        "access_event_id": record["access_event_id"],
        "event_type": "DEREFERENCE",
        "owner": record["owner"],
        "expression": record["expression"],
        "start_line": record["start_line"],
        "deref_resolves_to": record["deref_resolves_to"],
        "confidence": record["confidence"],
    }


def build_deref_resolution(
    events: Iterable[Mapping[str, Any]], *, enable: bool = False,
) -> dict[str, Any]:
    """Derive query-time ``DEREF_RESOLVES_TO`` and must-only ``same_storage``.

    Args:
        events: sparse_cfg events for a scope (as returned by ``query_analysis``).
        enable: opt-in switch. When false (default) nothing is derived and the
            result is an empty envelope (contract §1.8 default-OFF).
    """
    result: dict[str, Any] = {
        "deref_resolves_to": [],
        "same_storage": [],
        "coverage": {
            "dereferences": 0,
            "resolved_must": 0,
            "resolved_may": 0,
            "resolved_unknown": 0,
            "same_storage_pairs": 0,
        },
    }
    if not enable:
        return result

    events = list(events)
    spawns_by_function: dict[str, list[dict[str, str]]] = {}
    writes_by_decl: dict[str, list[dict[str, str]]] = {}
    for event in events:
        event_type = event.get("event_type")
        annotations = _annotations(event)
        if event_type == "THREAD_SPAWN":
            function = annotations.get("thread_function", "")
            if function:
                spawns_by_function.setdefault(function, []).append({
                    "scoped": annotations.get("thread_argument_decl_scoped", ""),
                    "form": annotations.get("thread_argument_form", ""),
                })
        elif event_type == "WRITE":
            decl = annotations.get("subject_decl", "")
            if decl:
                writes_by_decl.setdefault(decl, []).append({
                    "write_source": annotations.get("write_source", ""),
                    "unconditional": annotations.get("unconditional", ""),
                })

    resolved: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") != "DEREFERENCE":
            continue
        annotations = _annotations(event)
        owner = event.get("owner_qualified_name") or ""
        alias = annotations.get("alias", "") or ""
        decl = annotations.get("subject_decl", "") or ""
        confidence, scoped = _resolve_deref(
            event, alias,
            spawns_by_function.get(owner, []),
            writes_by_decl.get(decl, []),
        )
        resolved.append({
            "access_event_id": event.get("event_id"),
            "owner": owner,
            "expression": annotations.get("subject")
                          or event.get("matched_name") or "",
            "start_line": int(event.get("start_line") or 0),
            "deref_resolves_to": scoped,
            "confidence": confidence,
        })
        result["coverage"][f"resolved_{confidence}"] += 1
        result["coverage"]["dereferences"] += 1

    result["deref_resolves_to"] = resolved

    # same_storage=true only for cross-owner pairs that both MUST-resolve to the
    # same scoped identity (contract §1.6).
    by_target: dict[str, list[dict[str, Any]]] = {}
    for record in resolved:
        if record["confidence"] == _MUST and record["deref_resolves_to"]:
            by_target.setdefault(record["deref_resolves_to"], []).append(record)

    same_storage: list[dict[str, Any]] = []
    for target in sorted(by_target):
        entries = by_target[target]
        for index in range(len(entries)):
            for other in range(index + 1, len(entries)):
                left, right = entries[index], entries[other]
                if left["owner"] == right["owner"]:
                    continue  # same method is not a cross-thread competition.
                same_storage.append({
                    "storage_object_id": target,
                    "same_storage": "true",
                    "deref_resolves_to": target,
                    "accesses": [_side(left), _side(right)],
                })
    result["same_storage"] = same_storage
    result["coverage"]["same_storage_pairs"] = len(same_storage)
    return result


# ---------------------------------------------------------------------------
# G2b-1 (issue-pilot #99): query-time pointer target sets.
#
# The derivation is deliberately narrow. It answers one question -- "which
# declarations can this frame-local pointer reach at this access, when every
# assignment to it is a provable address-of?" -- from a read-only re-parse of
# the file plus the published sparse_cfg access events. It never writes a
# fact, never mints a relation, and never feeds a detector.
#
# Fail-closed boundaries:
#   * only frame-local pointers (`local` / `parameter`) are considered;
#   * a parameter has no local initialization, and call-site binding belongs
#     to D1, so a parameter access is `unknown`;
#   * any assignment whose right-hand side is not `&target` or a two-arm
#     conditional of two `&target` arms makes the whole pointer unknown;
#   * a target identity must resolve through the read-only DeclarationIndex;
#     a name that does not resolve is never guessed;
#   * only a single field level on the pointer itself is composed into the
#     candidate identity; nested/subscript paths stay target-level with a
#     `member_path_unresolved` limitation.
#
# Registered limitations (review #99, non-blocking):
#   * C++ reference aliases (`S *&r = p; r = &s2;`) and `std::swap(p, q)` are
#     not modelled; a pointer changed only through such an alias can still
#     report its direct address-of set.  Follow-up, not a silent claim.
#   * `function_static` pointers are not frame-local and produce no record;
#     the query scope is local / parameter pointers only.
#   * a target declared after the access resolves as unresolved (fail-closed);
#     forward-declared file-level targets narrow coverage rather than guess.
#   * `pointer_identity` is owner + `DeclarationIndex.scoped_identity`; a
#     shadowed frame-local declaration is distinguished by file/function and
#     its declaration byte offset.
# ---------------------------------------------------------------------------

POINTER_UNIQUE = "unique_candidate"
POINTER_MULTIPLE = "multiple_candidates"
POINTER_UNKNOWN = "unknown"

_FRAME_POINTER_STORAGES = frozenset({STORAGE_LOCAL, STORAGE_PARAMETER})
_LANGUAGE_BY_SUFFIX = {".c": "c"}


def _language_for(relative_path: str) -> str:
    return _LANGUAGE_BY_SUFFIX.get(Path(relative_path).suffix.lower(), "cpp")


def _declarator_name(source: bytes, node: Any) -> str:
    while node is not None:
        if node.type in {"identifier", "field_identifier", "type_identifier"}:
            return _text_of(source, node)
        for field in ("declarator", "name", "function"):
            child = node.child_by_field_name(field)
            if child is not None:
                found = _declarator_name(source, child)
                if found:
                    return found
        for child in node.named_children:
            found = _declarator_name(source, child)
            if found:
                return found
        return ""
    return ""


def _function_nodes(root: Any) -> list[Any]:
    functions: list[Any] = []

    def visit(node: Any) -> None:
        if node.type == "function_definition":
            functions.append(node)
            return
        for child in node.named_children:
            visit(child)

    visit(root)
    return functions


def _containing_function(functions: list[Any], start: int, end: int) -> Any | None:
    matches = [
        node for node in functions
        if node.start_byte <= start and end <= node.end_byte
    ]
    if not matches:
        return None
    return min(matches, key=lambda node: node.end_byte - node.start_byte)


def _declarator_is_array(declarator: Any) -> bool:
    """The declared object itself is an array (not a pointer to one)."""
    node = declarator
    while node is not None and node.type == "init_declarator":
        node = node.child_by_field_name("declarator")
    return node is not None and node.type == "array_declarator"


def _array_typedef_names(root: Any, source: bytes) -> set[str]:
    names: set[str] = set()

    def visit(node: Any) -> None:
        if node.type == "type_definition":
            declarator = node.child_by_field_name("declarator")
            if _declarator_is_array(declarator):
                name = _declarator_name(source, declarator)
                if name:
                    names.add(name)
        for child in node.named_children:
            visit(child)

    visit(root)
    return names


def _array_declaration_keys(
    root: Any, source: bytes, index: DeclarationIndex,
) -> set[tuple[int, str]]:
    """`(declaration node start, name)` for every declared array object.

    Covers a direct `int a[2]`, a typedef array (`typedef int A[2]; A a;`) and
    a typedef-array field.  A pointer *to* an array (`int (*p)[2]`, `A *p`) is
    not itself an array and is left alone.
    """
    array_typedefs = _array_typedef_names(root, source)
    keys: set[tuple[int, str]] = set()

    def visit(node: Any) -> None:
        if node.type in {
            "declaration", "field_declaration", "parameter_declaration",
        }:
            for declarator in node.children_by_field_name("declarator"):
                name = _declarator_name(source, declarator)
                if not name:
                    continue
                direct = _declarator_is_array(declarator)
                typedef_array = False
                if not direct:
                    core = declarator
                    while core is not None and core.type == "init_declarator":
                        core = core.child_by_field_name("declarator")
                    if core is not None and core.type != "pointer_declarator":
                        declaration = index.resolve(node.start_byte, name)
                        typedef_array = (
                            declaration is not None
                            and declaration.type_token in array_typedefs
                        )
                if direct or typedef_array:
                    keys.add((node.start_byte, name))
        for child in node.named_children:
            visit(child)

    visit(root)
    return keys


def _target_from_address_of(
    source: bytes, index: DeclarationIndex, node: Any,
    array_declarations: set[tuple[int, str]],
) -> tuple[str | None, list[str]]:
    """Resolve `&target` / `&target.field` to one identity, or fail closed."""
    node = _unwrap_parentheses(node)
    if node is None or node.type != "pointer_expression" or _operator_of(node, source) != "&":
        return None, ["pointer_source_unsupported"]
    target = _unwrap_parentheses(node.child_by_field_name("argument"))
    if target is None:
        return None, ["pointer_source_unsupported"]
    member = ""
    if target.type == "field_expression":
        field = target.child_by_field_name("field")
        argument = _unwrap_parentheses(target.child_by_field_name("argument"))
        if (
            _operator_of(target, source) != "."
            or field is None
            or argument is None
            or argument.type != "identifier"
        ):
            return None, ["target_member_unsupported"]
        member = _text_of(source, field)
        root_declaration = index.resolve(
            argument.start_byte, _text_of(source, argument))
        if root_declaration is None:
            return None, ["target_declaration_unresolved"]
        field_declaration = index.resolve_member(
            argument.start_byte, root_declaration.type_token, member)
        if field_declaration is None:
            return None, ["target_declaration_unresolved"]
        if (
            field_declaration.start_byte,
            field_declaration.name,
        ) in array_declarations:
            return None, ["target_array_unsupported"]
        target = argument
    if target.type not in {"identifier", "type_identifier"}:
        return None, ["pointer_source_unsupported"]
    if target.type == "type_identifier" and target.named_children:
        return None, ["pointer_source_unsupported"]
    name = _text_of(source, target)
    declaration = index.resolve(target.start_byte, name)
    if declaration is None:
        return None, ["target_declaration_unresolved"]
    if (declaration.start_byte, declaration.name) in array_declarations:
        # Issue #99 excludes arrays; `&a` is an address but not the pointer
        # object this derivation models.
        return None, ["target_array_unsupported"]
    identity = index.scoped_identity(declaration)
    if member:
        identity = f"{identity}#{member}"
    return identity, []


def _targets_from_rhs(
    source: bytes, index: DeclarationIndex, node: Any,
    array_declarations: set[tuple[int, str]],
) -> tuple[set[str], list[str]]:
    """The provable target set of one pointer right-hand side."""
    node = _unwrap_parentheses(node)
    if node is None:
        return set(), ["pointer_source_missing"]
    if node.type == "conditional_expression":
        arms: list[str] = []
        limitations: list[str] = []
        for field in ("consequence", "alternative"):
            arm = node.child_by_field_name(field)
            if arm is None:
                limitations.append("conditional_arm_missing")
                continue
            identity, missing = _target_from_address_of(
                source, index, arm, array_declarations)
            limitations.extend(missing)
            if identity is not None:
                arms.append(identity)
        if len(arms) != 2:
            return set(), sorted(set(limitations + ["conditional_arm_unsupported"]))
        return set(arms), sorted(set(limitations + ["conditional_pointer_source"]))
    identity, limitations = _target_from_address_of(
        source, index, node, array_declarations)
    if identity is None:
        return set(), limitations
    return {identity}, []


def _inside_control(source: bytes, node: Any, function: Any) -> bool:
    """Whether an assignment may be skipped on some path of the function.

    A declaration initializer is definite for its own scope and is not routed
    here; an assignment inside `if`/loop/switch/case/conditional/short-circuit/
    try/lambda can be skipped, so the pointer's set cannot be called complete.
    """
    ancestor = node.parent
    while ancestor is not None and ancestor is not function:
        if ancestor.type in {
            "if_statement", "while_statement", "do_statement",
            "for_statement", "for_range_loop", "switch_statement",
            "case_statement", "conditional_expression", "lambda_expression",
            "try_statement", "catch_clause",
        }:
            return True
        if (
            ancestor.type == "binary_expression"
            and _operator_of(ancestor, source) in {"&&", "||"}
        ):
            return True
        ancestor = ancestor.parent
    return False


def _lvalue_target_keys(
    source: bytes, index: DeclarationIndex, node: Any,
) -> tuple[set[tuple[int, str]], bool]:
    """Declaration keys a C/C++ lvalue expression may write.

    `(0, p)` writes `p` (the comma's right operand is the value), and
    `(cond ? p : q)` writes one of the two arms.  Returns ``(keys, exact)``;
    ``exact`` is false when an arm could not be modelled, so a caller that sees
    the pointer among ``keys`` must fail closed rather than assume a complete
    binding.  Non-lvalue pointer forms (`*p`, `p->f`) are not rebinding writes
    and return an empty set.
    """
    node = _unwrap_parentheses(node)
    if node is None:
        return set(), False
    if node.type == "identifier":
        name = _text_of(source, node)
        declaration = index.resolve(node.start_byte, name)
        if declaration is None:
            return set(), False
        return {(declaration.start_byte, declaration.name)}, True
    if node.type == "comma_expression":
        return _lvalue_target_keys(
            source, index, node.child_by_field_name("right"))
    if node.type == "conditional_expression":
        keys: set[tuple[int, str]] = set()
        for field in ("consequence", "alternative"):
            arm_keys, exact = _lvalue_target_keys(
                source, index, node.child_by_field_name(field))
            if not exact:
                return keys, False
            keys |= arm_keys
        return keys, True
    return set(), False


def _assignments_for(
    source: bytes, index: DeclarationIndex, function: Any, pointer: Any,
) -> tuple[list[Any], list[str], int | None]:
    """Every initializer/assignment whose left side resolves to `pointer`.

    An update (`p++`), a compound assignment and a taken address (`&p`) are
    recorded as an unknown write: each can change the pointer's target set
    without an address-of RHS that this derivation can prove.  The unknown
    write propagates to ``resolution=unknown`` and clears the whole set.

    Parentheses are unwrapped before the identifier check: `(p) = &s2` and
    `((p)) = &s2` are the same rebinding as `p = &s2`, and `(p)++` is the same
    update; missing them would publish a partial set as if it were unique.
    """
    rhs_nodes: list[Any] = []
    limitations: list[str] = []
    earliest: int | None = None
    goto_seen = False

    def mark(start: int) -> None:
        nonlocal earliest
        if earliest is None or start < earliest:
            earliest = start

    def visit(node: Any) -> None:
        nonlocal goto_seen
        if node.type == "function_definition" and node is not function:
            return
        if node.type == "goto_statement":
            goto_seen = True
        if node.type == "init_declarator":
            declarator = node.child_by_field_name("declarator")
            value = node.child_by_field_name("value")
            name = _declarator_name(source, declarator)
            if value is not None and name and index.resolve(node.start_byte, name) == pointer:
                rhs_nodes.append(value)
                mark(node.start_byte)
        elif node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            keys, exact = _lvalue_target_keys(source, index, left)
            pointer_key = (pointer.start_byte, pointer.name)
            if pointer_key in keys:
                mark(node.start_byte)
                if not exact or len(keys) > 1:
                    # `(cond ? p : q) = ...` may write p on one path only;
                    # the complete rebinding cannot be claimed.
                    rhs_nodes.append(None)
                    limitations.append("ambiguous_lvalue_target")
                elif _inside_control(source, node, function):
                    # `if (cond) p = &s1;` does not initialize p on every
                    # path; a union with later assignments is partial.
                    rhs_nodes.append(None)
                    limitations.append("conditional_assignment")
                elif right is not None:
                    rhs_nodes.append(right)
                else:
                    rhs_nodes.append(None)
                    limitations.append("pointer_assignment_unsupported")
        elif node.type == "update_expression":
            argument = _unwrap_parentheses(node.child_by_field_name("argument"))
            if argument is not None and argument.type == "identifier":
                name = _text_of(source, argument)
                if name and index.resolve(argument.start_byte, name) == pointer:
                    mark(node.start_byte)
                    rhs_nodes.append(None)
                    limitations.append("pointer_assignment_unsupported")
        elif (
            node.type == "pointer_expression"
            and _operator_of(node, source) == "&"
        ):
            argument = _unwrap_parentheses(node.child_by_field_name("argument"))
            if argument is not None and argument.type == "identifier":
                name = _text_of(source, argument)
                if name and index.resolve(argument.start_byte, name) == pointer:
                    rhs_nodes.append(None)
                    limitations.append("pointer_address_escapes")
        for child in node.named_children:
            visit(child)

    visit(function)
    if goto_seen and rhs_nodes:
        # A goto can jump over an assignment; byte order alone cannot prove
        # definite initialization.
        limitations.append("goto_control_flow_unmodelled")
        rhs_nodes.append(None)
    if not rhs_nodes:
        limitations.append("pointer_assignment_missing")
    return rhs_nodes, sorted(set(limitations)), earliest


def _pointer_state(
    source: bytes, index: DeclarationIndex, function: Any, pointer: Any,
    array_declarations: set[tuple[int, str]],
    cache: dict[tuple[int, int, str], tuple[set[str], str, list[str], int | None]],
) -> tuple[set[str], str, list[str], int | None]:
    """The pointer's union target set, cached per function + declaration."""
    key = (function.start_byte, pointer.start_byte, pointer.name)
    cached = cache.get(key)
    if cached is not None:
        return cached
    rhs_nodes, limitations, earliest = _assignments_for(
        source, index, function, pointer)
    targets: set[str] = set()
    known = bool(rhs_nodes)
    for rhs in rhs_nodes:
        ids, problems = _targets_from_rhs(
            source, index, rhs, array_declarations)
        limitations.extend(problems)
        if not ids:
            known = False
            break
        targets |= ids
    if not known or not targets:
        state = (set(), POINTER_UNKNOWN, limitations, earliest)
    else:
        if len(rhs_nodes) > 1:
            limitations.append("flow_insensitive_assignment_union")
        resolution = POINTER_UNIQUE if len(targets) == 1 else POINTER_MULTIPLE
        state = (targets, resolution, limitations, earliest)
    cache[key] = state
    return state


def _node_at(root: Any, start: int, end: int) -> Any | None:
    return root.descendant_for_byte_range(start, end)


def _deref_operand(source: bytes, node: Any) -> Any | None:
    node = _unwrap_parentheses(node)
    if (
        node is not None
        and node.type == "pointer_expression"
        and _operator_of(node, source) == "*"
    ):
        return _unwrap_parentheses(node.child_by_field_name("argument"))
    return None


def _member_for_access(
    source: bytes, root: Any, start: int, end: int, subject: str,
) -> tuple[str, list[str]]:
    """The single field level on the pointer, or '' with a limitation."""
    node = _node_at(root, start, end)
    current = node
    while current is not None:
        if current.type == "subscript_expression":
            # A subscripted member path has no provable single field identity;
            # keep the target-level candidate and say so.
            return "", ["member_path_unresolved"]
        if current.type == "field_expression":
            field = current.child_by_field_name("field")
            argument = _unwrap_parentheses(current.child_by_field_name("argument"))
            if field is None or argument is None:
                return "", ["member_path_unresolved"]
            names_pointer = (
                argument.type in {"identifier", "type_identifier"}
                and _text_of(source, argument) == subject
            ) or (
                (operand := _deref_operand(source, argument)) is not None
                and operand.type == "identifier"
                and _text_of(source, operand) == subject
            )
            if not names_pointer:
                return "", ["member_path_unresolved"]
            return _text_of(source, field), []
        if current.type in {"parenthesized_expression", "pointer_expression"}:
            current = current.parent
            continue
        break
    return "", ["member_unresolved"]


def _pointer_identity(
    event: Mapping[str, Any], declaration: Any, index: DeclarationIndex,
) -> str:
    owner = str(event.get("owner_symbol_id") or "")
    token = index.scoped_identity(declaration)
    return f"{owner}#{token}" if owner else token


def _pointer_record(
    event: Mapping[str, Any], subject: str, pointer_identity: str,
    candidates: set[str], resolution: str, limitations: list[str],
    start: int, end: int,
) -> dict[str, Any]:
    annotations = event.get("annotations") or {}
    event_id = event.get("event_id")
    return {
        "status": "available",
        "access_event_id": event_id,
        "owner": event.get("owner_qualified_name") or "",
        "owner_symbol_id": event.get("owner_symbol_id") or "",
        "expression": annotations.get("expression") or event.get("matched_name") or "",
        "pointer": subject,
        "pointer_identity": pointer_identity,
        "candidates": sorted(candidates),
        "resolution": resolution,
        "subject_exact": False,
        "limitations": sorted(set(limitations)),
        "evidence_event_ids": [event_id] if event_id else [],
        "evidence_spans": [[start, end]],
        "start_line": int(event.get("start_line") or 0),
        "start_byte": start,
        "end_byte": end,
    }


def build_pointer_target_sets(
    events: Iterable[Mapping[str, Any]], source: bytes, relative_path: str,
) -> dict[str, Any]:
    """Derive per-access pointer target sets from one file's sparse events.

    Pure and deterministic: the same events + source yield the same records,
    sorted by ``(owner_symbol_id, start_byte, access_event_id)``.
    """
    events = list(events)
    parser = CppTreeSitterParser(language=_language_for(relative_path))
    outcome = parser.parse_bytes(source, relative_path)
    root = outcome.tree.root_node
    if getattr(root, "has_error", False):
        # A partial tree cannot prove a declaration or an arm; do not derive
        # a candidate set from the parse that the indexer itself flagged.
        return {
            "pointer_targets": [],
            "coverage": {
                "accesses": 0, "unique_candidate": 0,
                "multiple_candidates": 0, "unknown": 0,
            },
            "missing_evidence": ["partial_parse"],
            "provenance": {
                "upstream_analyzer": "sparse_cfg:cpp",
                "derivation": "read-only tree-sitter + DeclarationIndex",
                "default": "off",
            },
        }
    index = DeclarationIndex.build(source, relative_path, root)
    array_declarations = _array_declaration_keys(root, source, index)
    functions = _function_nodes(root)

    records: list[dict[str, Any]] = []
    missing: set[str] = set()
    state_cache: dict[
        tuple[int, int, str], tuple[set[str], str, list[str], int | None]
    ] = {}
    for event in events:
        if event.get("event_type") != "DEREFERENCE":
            continue
        annotations = event.get("annotations") or {}
        subject = str(annotations.get("subject") or "")
        if not subject:
            continue
        start = int(event.get("start_byte") or 0)
        end = int(event.get("end_byte") or 0)
        function = _containing_function(functions, start, end)
        if function is None:
            continue
        declaration = index.resolve(start, subject)
        if declaration is None:
            missing.add("pointer_declaration_unresolved")
            records.append(_pointer_record(
                event, subject, "", set(), POINTER_UNKNOWN,
                ["pointer_declaration_unresolved"], start, end))
            continue
        if not declaration.is_pointer or declaration.storage not in _FRAME_POINTER_STORAGES:
            continue
        member, member_missing = _member_for_access(source, root, start, end, subject)
        limitations = list(member_missing)
        identity = _pointer_identity(event, declaration, index)
        if declaration.storage == STORAGE_PARAMETER:
            records.append(_pointer_record(
                event, subject, identity, set(), POINTER_UNKNOWN,
                limitations + ["parameter_without_callsite"], start, end))
            continue
        targets, resolution, state_limitations, earliest = _pointer_state(
            source, index, function, declaration, array_declarations,
            state_cache)
        limitations.extend(state_limitations)
        if resolution == POINTER_UNKNOWN:
            records.append(_pointer_record(
                event, subject, identity, set(), POINTER_UNKNOWN,
                limitations, start, end))
            continue
        if earliest is not None and start < earliest:
            # The access precedes every assignment: the pointer has no proven
            # value here.  A later assignment's set would be a partial answer.
            records.append(_pointer_record(
                event, subject, identity, set(), POINTER_UNKNOWN,
                limitations + ["access_before_assignment"], start, end))
            continue
        if not member:
            limitations.append("member_unresolved")
        candidates = {
            f"{target}#{member}" if member else target for target in targets
        }
        records.append(_pointer_record(
            event, subject, identity, candidates, resolution, limitations,
            start, end))

    records.sort(key=lambda record: (
        record["owner_symbol_id"], record["start_byte"],
        record["access_event_id"] or "",
    ))
    return {
        "pointer_targets": records,
        "coverage": {
            "accesses": len(records),
            "unique_candidate": sum(
                1 for record in records if record["resolution"] == POINTER_UNIQUE),
            "multiple_candidates": sum(
                1 for record in records if record["resolution"] == POINTER_MULTIPLE),
            "unknown": sum(
                1 for record in records if record["resolution"] == POINTER_UNKNOWN),
        },
        "missing_evidence": sorted(missing),
        "provenance": {
            "upstream_analyzer": "sparse_cfg:cpp",
            "derivation": "read-only tree-sitter + DeclarationIndex",
            "default": "off",
        },
    }


def query_pointer_targets(
    repo: str | Path, file_path: str, *, database: str | Path | None = None,
) -> dict[str, Any]:
    """Read one file's sparse facts and derive its pointer target sets.

    C/C++ only, same-file scope, read-only and default OFF: nothing here is
    registered as an analyzer or capability, and no detector consumes it.
    Python/Java and unbuilt/stale/corrupt files fall through to the
    sparse_cfg query's own honest status.
    """
    env = query_analysis(repo, "sparse_cfg", file_path=file_path, database=database)
    empty = {
        "pointer_targets": [],
        "coverage": {
            "accesses": 0, "unique_candidate": 0,
            "multiple_candidates": 0, "unknown": 0,
        },
        "missing_evidence": [],
    }
    if env["status"] != "available":
        return {"status": env["status"], "reason": env.get("reason"), **empty}
    root = Path(repo).resolve()
    path = Path(file_path)
    if not path.is_absolute():
        path = root / path
    try:
        source = path.read_bytes()
    except OSError:
        return {"status": "not_built", "reason": "file_not_readable", **empty}
    relative = (
        path.relative_to(root).as_posix()
        if path.is_relative_to(root)
        else Path(file_path).as_posix()
    )
    result = build_pointer_target_sets(env.get("events", []), source, relative)
    result["status"] = "available"
    result["reason"] = None
    return result


__all__ = [
    "POINTER_UNIQUE",
    "POINTER_MULTIPLE",
    "POINTER_UNKNOWN",
    "build_deref_resolution",
    "build_pointer_target_sets",
    "query_pointer_targets",
]
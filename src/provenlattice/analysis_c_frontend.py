"""Tree-sitter C frontend and normalized AST boundary for optional analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .parser import parser_for_language


@dataclass(frozen=True, slots=True)
class CParseDiagnostics:
    error_nodes: int
    missing_nodes: int
    parse_coverage: float
    partial: bool


@dataclass(frozen=True, slots=True)
class NormalizedCNode:
    kind: str
    parser_kind: str
    start_byte: int
    end_byte: int
    start_point: tuple[int, int]
    end_point: tuple[int, int]
    child_order: int
    name: str | None
    is_error: bool
    is_missing: bool
    children: tuple["NormalizedCNode", ...]
    part_role: str | None = None


@dataclass(frozen=True, slots=True)
class CFrontendResult:
    root: NormalizedCNode
    diagnostics: CParseDiagnostics
    scenario_pragmas: tuple["ScenarioPragma", ...] = ()


@dataclass(frozen=True, slots=True)
class ScenarioPragma:
    """One decoded whitelist pragma marker (FE-8 §1, frozen grammar).

    ``start_byte``/``end_byte`` cover the whole ``preproc_call`` node (including
    any trailing newline); ``action`` is ``begin`` or ``end``. ``is_error`` is
    True when the marker's span is covered by an ``ERROR``/missing node --
    the ``annotation_parse_partial`` signal of the frozen contract (§5).
    """

    scenario_id: str
    action: str
    start_byte: int
    end_byte: int
    is_error: bool = False
    is_missing: bool = False


CONTROL_KINDS = frozenset({
    "if_statement", "switch_statement", "case_statement", "while_statement",
    "do_statement", "for_statement", "break_statement", "continue_statement",
    "goto_statement",
})

NORMALIZED_KINDS = {
    "translation_unit": "FILE",
    "function_definition": "FUNCTION",
    "parameter_declaration": "PARAMETER",
    "compound_statement": "BLOCK",
    "expression_statement": "EXPRESSION",
    "return_statement": "RETURN",
    "labeled_statement": "LABEL",
    "call_expression": "CALL",
    "assignment_expression": "ASSIGNMENT",
    "unary_expression": "OPERATOR",
    "binary_expression": "OPERATOR",
    "update_expression": "OPERATOR",
    "field_expression": "FIELD_ACCESS",
    "subscript_expression": "SUBSCRIPT",
    "cast_expression": "CAST",
    "conditional_expression": "CONDITIONAL",
    "identifier": "IDENTIFIER",
    "field_identifier": "IDENTIFIER",
    "type_identifier": "IDENTIFIER",
    "statement_identifier": "IDENTIFIER",
    "number_literal": "LITERAL",
    "string_literal": "LITERAL",
    "char_literal": "LITERAL",
    "true": "LITERAL",
    "false": "LITERAL",
    "null": "LITERAL",
    "type_definition": "TYPE_DECL",
    "struct_specifier": "TYPE_DECL",
    "union_specifier": "TYPE_DECL",
    "enum_specifier": "TYPE_DECL",
    "field_declaration": "FIELD",
    "declaration": "DECLARATION",
    "init_declarator": "DECLARATION",
    "comment": "COMMENT",
    "ERROR": "UNKNOWN",
}

# Normalized child roles, resolved by the frontend from parser field names.
# This is the only layer allowed to consult parser field APIs; downstream
# consumers (CFG builder, queries) see roles only.
FIELD_ROLES = {
    "if_statement": {
        "condition": "condition", "consequence": "consequence",
        "alternative": "alternative",
    },
    "while_statement": {"condition": "condition", "body": "body"},
    "do_statement": {"body": "body", "condition": "condition"},
    "for_statement": {
        "initializer": "init", "condition": "condition",
        "update": "update", "body": "body",
    },
    "switch_statement": {"condition": "condition", "body": "body"},
    "conditional_expression": {
        "condition": "condition", "consequence": "consequence",
        "alternative": "alternative",
    },
    "case_statement": {"value": "value"},
}

# FE-8 (frozen, fe8_formal_feature_contract.md §1): the only accepted pragma
# shape is the exact whitelist `#pragma provenlattice scenario <id> begin|end`.
# No fuzzy match, no case folding, no comment/TODO/attribute/_Pragma/manifest.
SCENARIO_NAMESPACE = ("provenlattice", "scenario")
SCENARIO_ACTIONS = frozenset({"begin", "end"})
SCENARIO_ID_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")


class CFrontend:
    """Convert Tree-sitter C nodes into a small language-neutral vocabulary."""

    def parse(self, source: bytes, relative_path: str) -> CFrontendResult:
        outcome = parser_for_language("c").parse_bytes(source, relative_path)
        raw_root = outcome.tree.root_node
        diagnostics = self._diagnostics(raw_root, len(source))
        root = self._normalize(
            raw_root, source, child_order=0, in_function=False, part_role=None)
        scenario_pragmas = tuple(self.decode_scenario_pragmas(raw_root, source))
        return CFrontendResult(root, diagnostics, scenario_pragmas)

    def _normalize(
        self, node: Any, source: bytes, *, child_order: int, in_function: bool,
        part_role: str | None,
    ) -> NormalizedCNode:
        kind = self._kind(node, in_function=in_function)
        nested_in_function = in_function or node.type == "function_definition"
        raw_children = [
            child for child in node.children
            if child.is_named or child.is_error or child.is_missing
        ]
        roles = self._child_roles(node)
        children = tuple(
            self._normalize(
                child, source, child_order=index,
                in_function=nested_in_function,
                part_role=roles.get((child.start_byte, child.end_byte)),
            )
            for index, child in enumerate(raw_children)
        )
        return NormalizedCNode(
            kind=kind,
            parser_kind=node.type,
            start_byte=node.start_byte,
            end_byte=node.end_byte,
            start_point=tuple(node.start_point),
            end_point=tuple(node.end_point),
            child_order=child_order,
            name=self._name(node, source, kind),
            is_error=bool(node.is_error),
            is_missing=bool(node.is_missing),
            children=children,
            part_role=part_role,
        )

    @staticmethod
    def _child_roles(node: Any) -> dict:
        fields = FIELD_ROLES.get(node.type)
        if not fields:
            return {}
        roles: dict = {}
        for field_name, role in fields.items():
            child = node.child_by_field_name(field_name)
            if child is not None:
                roles[(child.start_byte, child.end_byte)] = role
        return roles

    def _kind(self, node: Any, *, in_function: bool) -> str:
        if node.type in CONTROL_KINDS:
            return "CONTROL_STRUCTURE"
        if node.type.startswith("preproc_"):
            return "PREPROCESSOR"
        if node.type == "binary_expression" and any(
            child.type == "&&" for child in node.children
        ):
            return "LOGICAL_AND"
        if node.type == "binary_expression" and any(
            child.type == "||" for child in node.children
        ):
            return "LOGICAL_OR"
        if node.type == "declaration":
            if self._is_function_prototype(node):
                return "FUNCTION"
            return "LOCAL" if in_function else "DECLARATION"
        if node.type in {
            "primitive_type", "sized_type_specifier", "type_qualifier",
            "storage_class_specifier",
        }:
            return "TYPE"
        return NORMALIZED_KINDS.get(node.type, "SYNTAX")

    def _is_function_prototype(self, node: Any) -> bool:
        declarator = node.child_by_field_name("declarator")
        function = self._find(declarator, "function_declarator")
        if function is None:
            return False
        inner = function.child_by_field_name("declarator")
        return self._find(inner, "pointer_declarator") is None

    def _name(self, node: Any, source: bytes, kind: str) -> str | None:
        if kind == "FUNCTION":
            return self._declarator_name(node.child_by_field_name("declarator"), source)
        if kind in {"PARAMETER", "LOCAL", "DECLARATION", "FIELD"}:
            return self._declarator_name(node.child_by_field_name("declarator"), source)
        if kind == "TYPE_DECL":
            candidate = node.child_by_field_name("name") or node.child_by_field_name("declarator")
            return self._declarator_name(candidate, source) or self._text(candidate, source)
        if kind == "LABEL":
            return self._text(node.child_by_field_name("label"), source)
        if kind == "CALL":
            return self._compact(self._text(node.child_by_field_name("function"), source))
        if node.type in {"identifier", "field_identifier", "type_identifier", "statement_identifier"}:
            return self._text(node, source)
        return None

    def _declarator_name(self, node: Any | None, source: bytes) -> str | None:
        if node is None:
            return None
        if node.type in {"identifier", "field_identifier", "type_identifier"}:
            return self._text(node, source)
        for field in ("declarator", "name", "function"):
            value = self._declarator_name(node.child_by_field_name(field), source)
            if value:
                return value
        for child in node.named_children:
            value = self._declarator_name(child, source)
            if value:
                return value
        return None

    @staticmethod
    def _find(node: Any | None, parser_kind: str) -> Any | None:
        if node is None:
            return None
        if node.type == parser_kind:
            return node
        for child in node.named_children:
            found = CFrontend._find(child, parser_kind)
            if found is not None:
                return found
        return None

    @staticmethod
    def _text(node: Any | None, source: bytes) -> str | None:
        if node is None:
            return None
        return source[node.start_byte:node.end_byte].decode("utf-8", "replace")

    @staticmethod
    def _compact(value: str | None) -> str | None:
        compact = " ".join((value or "").split())
        return compact or None

    @staticmethod
    def _child_by_type(node: Any, parser_kind: str) -> Any | None:
        for child in node.children:
            if child.type == parser_kind:
                return child
        return None

    @staticmethod
    def _span_overlaps(start_byte: int, end_byte: int, spans: list[tuple[int, int]]) -> bool:
        return any(s < end_byte and start_byte < e for s, e in spans)

    @staticmethod
    def decode_scenario_pragmas(root_node: Any, source: bytes) -> list["ScenarioPragma"]:
        """Decode the frozen whitelist pragma grammar (FE-8 §1), exact match.

        Only ``#pragma provenlattice scenario <scenario_id> begin|end`` is
        recognised, with ``<scenario_id>`` matching the frozen ASCII-identifier
        charset. Every other shape -- plain comment, ``// TODO``, benchmark
        marker, GCC/Clang attribute, ``_Pragma``, external manifest, or any
        near-miss namespace -- decodes to zero markers (0 annotations).

        A marker whose span is covered by an ``ERROR``/missing node is flagged
        ``is_error`` -- the ``annotation_parse_partial`` signal (§5).
        """
        preproc_calls: list[Any] = []
        error_spans: list[tuple[int, int]] = []
        stack = [root_node]
        while stack:
            node = stack.pop()
            if node.is_error or node.is_missing:
                error_spans.append((node.start_byte, node.end_byte))
            elif node.type == "preproc_call":
                preproc_calls.append(node)
            stack.extend(node.children)

        # The walk above pops in reverse child order; markers must be emitted in
        # source order so the pairing stack in the materializer sees begin/end
        # in the order they appear in the file.
        preproc_calls.sort(key=lambda node: node.start_byte)

        markers: list["ScenarioPragma"] = []
        for node in preproc_calls:
            directive = CFrontend._child_by_type(node, "preproc_directive")
            argument = CFrontend._child_by_type(node, "preproc_arg")
            if directive is None or argument is None:
                continue
            directive_text = CFrontend._text(directive, source)
            if directive_text is None or directive_text.strip() != "#pragma":
                continue
            arg_text = CFrontend._text(argument, source) or ""
            tokens = arg_text.strip().split()
            if not (
                len(tokens) == 4
                and tokens[0] == SCENARIO_NAMESPACE[0]
                and tokens[1] == SCENARIO_NAMESPACE[1]
                and tokens[3] in SCENARIO_ACTIONS
                and SCENARIO_ID_PATTERN.fullmatch(tokens[2])
            ):
                continue
            markers.append(ScenarioPragma(
                scenario_id=tokens[2],
                action=tokens[3],
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                is_error=CFrontend._span_overlaps(
                    node.start_byte, node.end_byte, error_spans),
                is_missing=bool(node.is_missing),
            ))
        return markers

    @staticmethod
    def _diagnostics(root: Any, source_size: int) -> CParseDiagnostics:
        error_nodes = 0
        missing_nodes = 0
        error_bytes = 0
        stack = [root]
        while stack:
            node = stack.pop()
            if node.is_error:
                error_nodes += 1
                error_bytes += max(0, node.end_byte - node.start_byte)
            if node.is_missing:
                missing_nodes += 1
            stack.extend(node.children)
        denominator = max(1, source_size)
        coverage = max(0.0, 1.0 - min(error_bytes, denominator) / denominator)
        return CParseDiagnostics(
            error_nodes=error_nodes,
            missing_nodes=missing_nodes,
            parse_coverage=round(coverage, 6),
            partial=bool(error_nodes or missing_nodes),
        )


# ---------------------------------------------------------------------------
# ATOMIC facts (issue-pilot#89, G1)
#
# The event lexicon already names atomic *operations* (atomic_load, fetch_add,
# ...). It cannot see the two shapes where atomicity is carried by the object
# or by a region:
#
#   _Atomic int c;                         the object itself is atomic
#   __VERIFIER_atomic_begin(); ... end();  a paired region is atomic
#
# This module owns the syntax side of both. It produces plain data; the
# sparse-CFG materializer turns it into additive ATOMIC points. Nothing here
# decides a defect, and a use is bound through the declaration index whenever
# the index can answer -- the recovered `_Atomic(type)` form is the bounded
# exception, because the installed grammars do not parse that C11 spelling.
# ---------------------------------------------------------------------------

ATOMIC_QUALIFIER = "_Atomic"
VERIFIER_ATOMIC_BEGIN = "__VERIFIER_atomic_begin"
VERIFIER_ATOMIC_END = "__VERIFIER_atomic_end"

# `_declarator_name` is stateless; the frontend instance is only the holder.
_DECLARATOR_NAME = CFrontend()._declarator_name


@dataclass(frozen=True, slots=True)
class AtomicDeclaration:
    """One declaration whose object is atomic in V1's sense."""

    start_byte: int
    end_byte: int
    name: str
    name_start: int
    name_end: int
    owner_start: int | None
    owner_end: int | None
    source: str  # "type_qualifier" | "type_specifier"
    # "object" (the name is the atomic object), "pointee" (the name is a
    # pointer to an atomic object; only dereferences are atomic), or "array"
    # (an array of atomic elements; element accesses are atomic).
    kind: str = "object"


@dataclass(frozen=True, slots=True)
class AtomicFacts:
    """What the atomic syntax facts say about one file.

    `declaration_keys` mirrors the `Declaration` identity the index stores
    (`start_byte`, `name`). `recovered` covers the `_Atomic(type)` spelling the
    installed grammars parse as an ERROR; those declarations are not in the
    index, so the only matching rule is the recorded owner span plus the
    declaration's own position. `limitations` is data, never a silent drop.
    """

    declaration_keys: frozenset[tuple[int, str]] = frozenset()
    pointee_keys: frozenset[tuple[int, str]] = frozenset()
    array_keys: frozenset[tuple[int, str]] = frozenset()
    member_keys: frozenset[tuple[str, str]] = frozenset()
    aliases: frozenset[str] = frozenset()
    recovered: tuple[AtomicDeclaration, ...] = ()
    regions: tuple[tuple[int, int], ...] = ()
    limitations: tuple[str, ...] = ()

    def is_atomic_declaration(self, declaration: Any) -> bool:
        return (
            declaration is not None
            and (declaration.start_byte, declaration.name) in self.declaration_keys
        )

    def is_atomic_array(self, declaration: Any) -> bool:
        """Whether the declaration is an array of atomic elements."""
        return (
            declaration is not None
            and (declaration.start_byte, declaration.name) in self.array_keys
        )

    def is_atomic_member(self, type_token: str, member: str) -> bool:
        """Whether `type_token`'s member `member` is declared atomic.

        The type is the shallow token the declaration index records (a struct
        tag or a typedef alias), so an anonymous `typedef struct {...} S;`
        still names its field list through `S`.
        """
        return bool(type_token) and bool(member) and (type_token, member) in self.member_keys

    def is_atomic_pointee(self, declaration: Any) -> bool:
        """Whether the declaration is a one-level pointer to an atomic object.

        `_Atomic int *p` declares a pointer *to* an atomic object: `*p` and
        `p[i]` are atomic, the pointer variable itself is not. Deeper pointer
        levels stay unsupported (the dereference count would have to match).
        """
        return (
            declaration is not None
            and (declaration.start_byte, declaration.name) in self.pointee_keys
        )

    def inside_region(self, byte: int) -> bool:
        return any(start <= byte < end for start, end in self.regions)

    def recovered_declaration(
        self, name: str, owner_start: int | None, owner_end: int | None, byte: int,
    ) -> AtomicDeclaration | None:
        """The visible recovered `_Atomic(type)` declaration for a use, if any.

        Visibility is bounded to the declaration's own owner span and the
        declaration's start byte; a same-spelled name declared later is not
        evidence for an earlier use.
        """
        matches = [
            declaration for declaration in self.recovered
            if declaration.name == name
            and (
                declaration.owner_start is None
                or (
                    declaration.owner_start == owner_start
                    and declaration.owner_end == owner_end
                )
            )
            and declaration.start_byte <= byte
        ]
        return max(matches, key=lambda declaration: declaration.start_byte) if matches else None


def _walk_nodes(root: Any) -> Any:
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.named_children))


def _node_text(source: bytes, node: Any) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _inner_declarator(node: Any) -> Any:
    inner = node.child_by_field_name("declarator")
    if inner is not None:
        return inner
    return node.named_children[-1] if node.named_children else None


def _type_definition_names(node: Any, source: bytes) -> list[str]:
    """Every name a typedef declares, multi-declarator aware (`T, U`)."""
    names: list[str] = []
    for declarator in node.children_by_field_name("declarator"):
        name = _DECLARATOR_NAME(declarator, source)
        if name:
            names.append(name)
    if names:
        return names
    seen_type = False
    for child in node.named_children:
        if child.type in {"primitive_type", "sized_type_specifier"} | _AGGREGATE_NODES:
            seen_type = True
            continue
        if child.type == "type_qualifier":
            continue
        if child.type in {"type_identifier", "identifier"}:
            if seen_type:
                names.append(_node_text(source, child).strip())
            else:
                seen_type = True
    return [name for name in names if name]


def _type_definition_name(node: Any, source: bytes) -> str:
    names = _type_definition_names(node, source)
    return names[-1] if names else ""


_AGGREGATE_NODES = frozenset({
    "struct_specifier", "union_specifier", "enum_specifier",
})


def _typedef_underlying_children(node: Any, source: bytes) -> list[Any]:
    """The typedef's type children, with every declared alias name removed.

    `typedef struct { _Atomic int a; } S;` has the struct as its type and `S`
    as its name; the alias is not atomic even though one of its *fields* is.
    `typedef _Atomic int T, U;` declares two names off one type.
    """
    names = set(_type_definition_names(node, source))
    children: list[Any] = []
    for child in node.named_children:
        if (
            child.type in {"type_identifier", "identifier"}
            and _node_text(source, child).strip() in names
        ):
            continue
        children.append(child)
    return children


def _enclosing_scope(node: Any) -> Any:
    """The nearest block or the file, for typedef visibility."""
    current = node.parent
    while current is not None:
        if current.type in {"compound_statement", "translation_unit"}:
            return current
        current = current.parent
    return None


@dataclass(frozen=True, slots=True)
class _AliasEntry:
    name: str
    start_byte: int
    scope_start: int
    scope_end: int
    # "" when the name is not atomic; otherwise "object" (the name itself is
    # atomic), "pointee" (a pointer to an atomic object), or "array".
    kind: str
    # Macro entries carry their replacement text so the kind is resolved at
    # the use site, not at definition time. ``None`` with ``is_macro`` means
    # the macro was #undef'ed.
    macro_text: str | None = None
    is_macro: bool = False


class AtomicTypeIndex:
    """Scoped view over the atomic typedefs and object-like macros.

    A typedef's name is visible from its declaration to the end of its
    enclosing block, and an inner declaration shadows an outer one. Macros
    follow preprocessor order, including `#undef` and redefinition; their
    replacement text is expanded at the use site. Macro and typedef names are
    separate namespaces: an `#undef` removes the macro, it does not hide an
    equally named typedef. A flat name set would mark `typedef int T;` inside
    a function as atomic because an outer `typedef _Atomic int T;` exists --
    a fail-open that hides real races.
    """

    def __init__(
        self, entries: list[_AliasEntry], macros: list[_AliasEntry] | None = None,
    ) -> None:
        self.entries = tuple(entries)
        self.macros = tuple(macros or ())

    @property
    def aliases(self) -> frozenset[str]:
        return frozenset(entry.name for entry in self.entries if entry.kind)

    def _macro_at(self, name: str, byte: int) -> _AliasEntry | None:
        visible = [
            entry for entry in self.macros
            if entry.name == name and entry.start_byte <= byte
        ]
        if not visible:
            return None
        return max(visible, key=lambda entry: entry.start_byte)

    def kind_of(self, name: str, byte: int) -> str:
        return self._kind_of(name, byte, ())

    def _kind_of(self, name: str, byte: int, seen: tuple[str, ...]) -> str:
        if not name or name in seen:
            return ""
        macro = self._macro_at(name, byte)
        if macro is not None:
            if macro.macro_text is None:
                # `#undef`: the macro is gone, but a typedef of the same name
                # remains visible.
                pass
            else:
                return _macro_type_kind(macro.macro_text, self, byte,
                                        seen + (name,))
        visible = [
            entry for entry in self.entries
            if entry.name == name
            and entry.start_byte <= byte
            and entry.scope_start <= byte < entry.scope_end
        ]
        if not visible:
            return ""
        return max(visible, key=lambda entry: entry.start_byte).kind

    def is_atomic(self, name: str, byte: int) -> bool:
        return bool(self.kind_of(name, byte))


_ATOMIC_TOKEN = re.compile(r"(?<![A-Za-z0-9_])_Atomic(?![A-Za-z0-9_])")
_MACRO_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_DIRECTIVE = re.compile(r"^[ \t]*#[ \t]*([A-Za-z_]+)(.*)$", re.DOTALL)


def _active_text(source: bytes) -> str:
    """Source text with comments, string bodies and `#if 0` branches blanked.

    Length and newlines are preserved so offsets recovered from this text still
    address the original source. A full preprocessor is out of scope; literal
    `#if 0` (and its `#else` arm) is the only conditional form treated as
    inactive, and everything else is left for the normal token/AST paths.
    """
    text = source.decode("utf-8", "replace")
    chars = list(text)
    n = len(text)

    def blank(start: int, end: int) -> None:
        for index in range(start, min(end, n)):
            if chars[index] not in "\r\n":
                chars[index] = " "

    index = 0
    quote = ""
    while index < n:
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
            else:
                chars[index] = " "
            index += 1
            continue
        if char in {'"', "'"}:
            quote = char
            index += 1
            continue
        if text.startswith("/*", index):
            close = text.find("*/", index + 2)
            end = n if close < 0 else close + 2
            blank(index, end)
            index = end
            continue
        if text.startswith("//", index):
            close = text.find("\n", index + 2)
            end = n if close < 0 else close
            blank(index, end)
            index = end
            continue
        index += 1

    # Blank literal `#if 0` branches. The `#else` arm, when present, is active.
    lines = "".join(chars).splitlines(keepends=True)
    result: list[str] = []
    offset = 0
    skip_depth = 0
    for line in lines:
        stripped = line.lstrip()
        directive = ""
        rest = ""
        if stripped.startswith("#"):
            match = _DIRECTIVE.match(stripped)
            if match is not None:
                directive = match.group(1).lower()
                rest = match.group(2).strip()
        blank_line = False
        if skip_depth == 0:
            if directive == "if" and rest == "0":
                skip_depth = 1
                blank_line = True
        else:
            if directive in {"if", "ifdef", "ifndef"}:
                skip_depth += 1
                blank_line = True
            elif directive == "else" and skip_depth == 1:
                skip_depth = 0
                blank_line = True
            elif directive == "endif":
                skip_depth = max(0, skip_depth - 1)
                blank_line = True
            else:
                blank_line = True
        if blank_line:
            result.append("".join(
                char if char in "\r\n" else " " for char in line))
        else:
            result.append(line)
        offset += len(line)
    return "".join(result)


def _macro_type_kind(
    value: str, types: "AtomicTypeIndex", byte: int,
    seen: tuple[str, ...] = (),
) -> str:
    """The kind a macro replacement text denotes, or "".

    `_Atomic int` and `_Atomic(int)` declare an atomic object; `_Atomic int *`
    is a pointer to an atomic object, while `_Atomic(int *)` makes the pointer
    object itself atomic. A macro naming another macro/typedef is resolved at
    the use site, not when the `#define` was read.
    """
    stripped = value.strip()
    if not stripped:
        return ""
    if _ATOMIC_TOKEN.search(stripped):
        without_group = re.sub(r"_Atomic\s*\([^)]*\)", " ", stripped)
        without_qualifier = _ATOMIC_TOKEN.sub(" ", without_group)
        return "pointee" if "*" in without_qualifier else "object"
    if _MACRO_NAME.fullmatch(stripped):
        return types._kind_of(stripped, byte, seen)
    return ""


def _collect_atomic_macro_entries(source: bytes) -> tuple[list[_AliasEntry], list[_AliasEntry]]:
    """Object-like macro entries in preprocessor order.

    Comments, strings and literal `#if 0` branches are blanked before scanning.
    Function-like macros are not type aliases and are skipped. Backslash
    continuations are joined into one logical directive; the entry keeps the
    first physical line's offset. The replacement text is stored verbatim and
    resolved at the use site, so `#undef`/redefinition order is honoured.
    """
    text = _active_text(source)
    lines = text.splitlines(keepends=True)
    macros: list[_AliasEntry] = []
    offset = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        start = offset
        offset += len(line)
        index += 1
        logical = line
        while logical.rstrip("\r\n").endswith("\\") and index < len(lines):
            logical = logical.rstrip("\r\n")[:-1] + " " + lines[index]
            offset += len(lines[index])
            index += 1
        match = re.match(
            r"^[ \t]*#[ \t]*(define|undef)[ \t]+([A-Za-z_][A-Za-z_0-9]*)",
            logical,
        )
        if match is None:
            continue
        directive, name = match.group(1), match.group(2)
        rest = logical[match.end():]
        if directive == "define":
            if rest.startswith("("):
                # Function-like macro: `T` without an argument list never
                # expands, so it cannot name a type alias.
                continue
            macros.append(_AliasEntry(
                name, start, 0, 1 << 62, "",
                macro_text=rest.strip(), is_macro=True))
        else:
            macros.append(_AliasEntry(
                name, start, 0, 1 << 62, "",
                macro_text=None, is_macro=True))
    return [], macros


def _type_children_kind(
    children: list[Any], source: bytes, types: "AtomicTypeIndex",
) -> str:
    """The atomic kind these type children spell, or "".

    An aggregate with a body is deliberately *not* atomic: a qualifier inside
    its field list qualifies a field, not the aggregate object.
    """
    for child in children:
        if child.type in _AGGREGATE_NODES and child.child_by_field_name("body") is not None:
            continue
        if child.type == "type_qualifier" and _node_text(source, child).strip() == ATOMIC_QUALIFIER:
            return "object"
        if child.type == "type_identifier":
            kind = types.kind_of(_node_text(source, child).strip(), child.start_byte)
            if kind:
                return kind
    return ""


def _scope_at(root: Any, byte: int) -> tuple[int, int]:
    """The smallest compound/translation-unit span containing `byte`."""
    best = (0, 1 << 62)
    for node in _walk_nodes(root):
        if (
            node.type in {"compound_statement", "translation_unit"}
            and node.start_byte <= byte < node.end_byte
            and node.end_byte - node.start_byte < best[1] - best[0]
        ):
            best = (node.start_byte, node.end_byte)
    return best


def _declarator_shape(declarator: Any) -> tuple[str, int]:
    """`(shape, pointer level)` for a declarator chain."""
    node = declarator
    if node is not None and node.type == "init_declarator":
        node = node.child_by_field_name("declarator") or node
    while node is not None and node.type == "parenthesized_declarator":
        node = _inner_declarator(node)
    if node is None:
        return "plain", 0
    if node.type == "pointer_declarator":
        return "pointer", _pointer_level(node) or 0
    if node.type == "array_declarator":
        return "array", 0
    if node.type == "function_declarator":
        return "function", 0
    return "plain", 0


def _combine_type_kind(type_kind: str, shape: str, level: int) -> str:
    """How a declarator shape turns a type kind into an object kind."""
    if type_kind == "object":
        if shape == "pointer":
            return "pointee" if level == 1 else ""
        if shape == "array":
            return "array"
        return "object" if shape == "plain" else ""
    if type_kind == "pointee":
        return "pointee" if shape == "plain" else ""
    if type_kind == "array":
        return "array" if shape == "plain" else ""
    return ""


def _type_definition_entries(node: Any, source: bytes) -> list[tuple[str, Any]]:
    """`(name, declarator)` for every name a typedef declares."""
    pairs: list[tuple[str, Any]] = []
    for declarator in node.children_by_field_name("declarator"):
        name = _DECLARATOR_NAME(declarator, source)
        if name:
            pairs.append((name, declarator))
    if pairs:
        return pairs
    candidates = [
        child for child in node.named_children
        if child.type in {
            "pointer_declarator", "array_declarator",
            "parenthesized_declarator", "function_declarator",
        }
    ]
    for candidate in candidates:
        name = _DECLARATOR_NAME(candidate, source)
        if name:
            pairs.append((name, candidate))
    if pairs:
        return pairs
    return [(name, None) for name in _type_definition_names(node, source)]


_RECOVERED_TYPEDEF = re.compile(
    r"typedef\s+_Atomic\s*\(([^)]*)\)\s*([^;]+);")


def _build_atomic_type_index(root: Any, source: bytes) -> AtomicTypeIndex:
    """Every typedef/macro entry with its scope and kind."""
    entries, macros = _collect_atomic_macro_entries(source)
    for node in _walk_nodes(root):
        if node.type != "type_definition":
            continue
        pairs = _type_definition_entries(node, source)
        if not pairs:
            continue
        types = AtomicTypeIndex(entries, macros)
        type_kind = _type_children_kind(
            _typedef_underlying_children(node, source), source, types)
        scope = _enclosing_scope(node)
        scope_start = scope.start_byte if scope is not None else 0
        scope_end = scope.end_byte if scope is not None else (1 << 62)
        for name, declarator in pairs:
            shape, level = _declarator_shape(declarator)
            kind = _combine_type_kind(type_kind, shape, level)
            entries.append(_AliasEntry(
                name, node.start_byte, scope_start, scope_end, kind))
    # `typedef _Atomic(type) AI;` arrives as a grammar ERROR, so the recovered
    # spelling is read from the source with the same scope rules and kind
    # combination as the AST typedefs. Comments, strings and `#if 0` branches
    # are blanked by `_active_text`, so they cannot fabricate a typedef.
    text = _active_text(source)
    for match in _RECOVERED_TYPEDEF.finditer(text):
        for part, offset in _top_level_parts(match.group(2)):
            part = _strip_initializer(part)
            part, paren_shift = _strip_wrapping_parens(part)
            base = match.start(2) + offset + paren_shift
            pointer = _RECOVERED_POINTER.match(part)
            if pointer is not None:
                stars, name = pointer.group(1), pointer.group(2)
                name_start = base + pointer.start(2)
                kind = "pointee" if len(stars) == 1 else ""
            else:
                array = _RECOVERED_ARRAY.match(part)
                if array is not None:
                    name = array.group(1)
                    name_start = base + array.start(1)
                    kind = "array"
                else:
                    object_match = _RECOVERED_OBJECT.match(part)
                    if object_match is None:
                        continue
                    name = object_match.group(1)
                    name_start = base + object_match.start(1)
                    kind = "object"
            scope_start, scope_end = _scope_at(root, name_start)
            entries.append(_AliasEntry(
                name, name_start, scope_start, scope_end, kind))
    return AtomicTypeIndex(entries, macros)


def _declaration_type_kind(node: Any, source: bytes, types: AtomicTypeIndex) -> str:
    type_node = node.child_by_field_name("type")
    children = ([type_node] if type_node is not None else []) + list(node.named_children)
    return _type_children_kind(children, source, types)


def _pointer_level(declarator: Any) -> int | None:
    """The pointer depth of a stable pointer-to-identifier declarator.

    Returns None for anything V1 should not turn into a pointee fact: a
    function/reference declarator, a pointer to an array/function, or an
    ambiguous chain. A one-level pointer to a plain name is the supported
    `_Atomic int *p` shape.
    """
    node = declarator
    if node is not None and node.type == "init_declarator":
        node = node.child_by_field_name("declarator") or node
    while node is not None and node.type == "parenthesized_declarator":
        node = _inner_declarator(node)
    if node is None or node.type != "pointer_declarator":
        return None
    level = 0
    while node is not None and node.type == "pointer_declarator":
        level += 1
        node = _inner_declarator(node)
        while node is not None and node.type == "parenthesized_declarator":
            node = _inner_declarator(node)
    if node is None or node.type not in {"identifier", "type_identifier"}:
        return None
    return level


def _collect_atomic_declarations(
    root: Any, source: bytes, types: AtomicTypeIndex,
) -> tuple[
    frozenset[tuple[int, str]],
    frozenset[tuple[int, str]],
    frozenset[tuple[int, str]],
    tuple[str, ...],
]:
    keys: set[tuple[int, str]] = set()
    pointee_keys: set[tuple[int, str]] = set()
    array_keys: set[tuple[int, str]] = set()
    limitations: list[str] = []
    for node in _walk_nodes(root):
        if node.type not in {"declaration", "parameter_declaration", "field_declaration"}:
            continue
        type_kind = _declaration_type_kind(node, source, types)
        if not type_kind:
            continue
        for declarator in node.children_by_field_name("declarator"):
            name = _DECLARATOR_NAME(declarator, source)
            if not name:
                continue
            shape, level = _declarator_shape(declarator)
            kind = _combine_type_kind(type_kind, shape, level)
            if not kind:
                if shape in {"pointer", "array", "function"}:
                    limitations.append(
                        f"atomic_pointer_or_function:{name}@{node.start_byte}")
                continue
            if kind == "object":
                keys.add((node.start_byte, name))
            elif kind == "pointee":
                pointee_keys.add((node.start_byte, name))
            else:
                array_keys.add((node.start_byte, name))
    return frozenset(keys), frozenset(pointee_keys), frozenset(array_keys), tuple(limitations)


def _owner_span(owners: Any, start_byte: int, end_byte: int) -> tuple[int | None, int | None]:
    if owners is None:
        return None, None
    span = owners.owner_of(start_byte, end_byte)
    if span is None:
        return None, None
    return span.start_byte, span.end_byte


def _recovered_declarators(node: Any, source: bytes) -> tuple[list[tuple[Any, str]], list[str]]:
    """The declarators of a recovered `_Atomic(type) ...` ERROR node.

    Returns `(node, kind)` pairs plus the limitations for shapes V1 declines.
    A top-level `identifier` (or `init_declarator`) declares an atomic object;
    a one-level `pointer_declarator` declares a pointer *to* an atomic object
    (only its dereference is atomic); an `array_declarator` declares an array
    of atomic elements. Initializer values are not declarators, and commas
    separate declarators even when one of them has an initializer.
    """
    children = list(node.named_children)
    type_end = node.start_byte
    for index, child in enumerate(children):
        if child.type == "type_qualifier" and _node_text(source, child).strip() == ATOMIC_QUALIFIER:
            following = children[index + 1] if index + 1 < len(children) else None
            if following is not None and following.type in {
                "parenthesized_declarator", "parenthesized_expression", "parameter_list",
            }:
                type_end = following.end_byte
            break
    candidates = [
        child for child in children
        if child.start_byte >= type_end
        and child.type in {
            "identifier", "init_declarator", "pointer_declarator",
            "array_declarator", "parenthesized_declarator",
        }
    ]
    declarators: list[tuple[Any, str]] = []
    limitations: list[str] = []
    after_equals = False
    previous_end = type_end
    for candidate in candidates:
        gap = source[previous_end:candidate.start_byte].decode("utf-8", "replace")
        last_equals = gap.rfind("=")
        last_comma = gap.rfind(",")
        if last_equals != -1 or last_comma != -1:
            after_equals = last_equals > last_comma
        previous_end = candidate.end_byte
        if after_equals:
            continue
        inner = candidate
        while inner is not None and inner.type == "parenthesized_declarator":
            inner = _inner_declarator(inner)
        if inner is None:
            continue
        name = _DECLARATOR_NAME(inner, source)
        if not name:
            continue
        if inner.type in {"identifier", "init_declarator"}:
            declarators.append((inner, "object"))
            continue
        if inner.type == "pointer_declarator":
            level = _pointer_level(inner)
            if level == 1:
                declarators.append((inner, "pointee"))
            else:
                limitations.append(f"atomic_pointer_depth:{name}@{node.start_byte}")
            continue
        if inner.type == "array_declarator":
            declarators.append((inner, "array"))
            continue
        limitations.append(f"atomic_declarator_unsupported:{name}@{node.start_byte}")
    return declarators, limitations


_RECOVERED_DECLARATION = re.compile(
    r"_Atomic\s*\([^)]*\)\s*([^;]+);")
_RECOVERED_POINTER = re.compile(r"^\s*(\*+)\s*([A-Za-z_][A-Za-z_0-9]*)")
_RECOVERED_ARRAY = re.compile(r"^\s*([A-Za-z_][A-Za-z_0-9]*)\s*\[")
_RECOVERED_OBJECT = re.compile(r"^\s*([A-Za-z_][A-Za-z_0-9]*)")


def _strip_wrapping_parens(text: str) -> tuple[str, int]:
    """Strip balanced parentheses wrapping the whole declarator.

    Returns the inner text and the number of characters removed before it, so
    offsets into the original source remain exact (`(T)` -> `T`, 1;
    ` (*P)` -> `*P`, 2).
    """
    shift = 0
    current = text
    while True:
        leading = len(current) - len(current.lstrip())
        stripped = current.lstrip()
        if not stripped.startswith("("):
            return current, shift
        depth = 0
        close = -1
        for index, character in enumerate(stripped):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    close = index
                    break
        if close < 0 or stripped[close + 1:].strip():
            return current, shift
        shift += leading + 1
        current = stripped[1:close]


def _top_level_parts(text: str) -> list[tuple[str, int]]:
    """Split a declarator list on top-level commas, keeping byte offsets."""
    parts: list[tuple[str, int]] = []
    depth = 0
    start = 0
    for index, character in enumerate(text):
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
        elif character == "," and depth == 0:
            parts.append((text[start:index], start))
            start = index + 1
    parts.append((text[start:], start))
    return parts


def _strip_initializer(text: str) -> str:
    depth = 0
    for index, character in enumerate(text):
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
        elif character == "=" and depth == 0:
            return text[:index]
    return text


def _source_recovered_declarations(
    source: bytes, owners: Any, seen: set[tuple[int, int]],
) -> tuple[list[AtomicDeclaration], list[str]]:
    """Text-level fallback for the `_Atomic(type)` spelling.

    The ERROR-node shape covers the common declarators, but the grammar's
    recovery for arrays and some multi-declarator forms is not stable. The
    source spelling is unambiguous: every `_Atomic(...)` declaration's
    declarator list is split on top-level commas and classified the same way.
    Entries already recovered from the AST are not repeated.
    """
    recovered: list[AtomicDeclaration] = []
    limitations: list[str] = []
    text = _active_text(source)
    for match in _RECOVERED_DECLARATION.finditer(text):
        prefix = text[max(0, match.start() - 32):match.start()]
        if re.search(r"typedef\s*$", prefix):
            continue
        owner_start, owner_end = _owner_span(owners, match.start(), match.end())
        for part, offset in _top_level_parts(match.group(1)):
            part = _strip_initializer(part)
            part, paren_shift = _strip_wrapping_parens(part)
            base = match.start(1) + offset + paren_shift
            pointer = _RECOVERED_POINTER.match(part)
            if pointer is not None:
                stars, name = pointer.group(1), pointer.group(2)
                name_start = base + pointer.start(2)
                name_end = base + pointer.end(2)
                kind = "pointee" if len(stars) == 1 else ""
                if not kind:
                    limitations.append(f"atomic_pointer_depth:{name}@{name_start}")
                    continue
            else:
                array = _RECOVERED_ARRAY.match(part)
                if array is not None:
                    name = array.group(1)
                    name_start = base + array.start(1)
                    name_end = base + array.end(1)
                    kind = "array"
                else:
                    object_match = _RECOVERED_OBJECT.match(part)
                    if object_match is None:
                        continue
                    name = object_match.group(1)
                    name_start = base + object_match.start(1)
                    name_end = base + object_match.end(1)
                    kind = "object"
            if (name_start, name_end) in seen:
                continue
            seen.add((name_start, name_end))
            recovered.append(AtomicDeclaration(
                start_byte=match.start(),
                end_byte=match.end(),
                name=name,
                name_start=name_start,
                name_end=name_end,
                owner_start=owner_start,
                owner_end=owner_end,
                source="type_specifier",
                kind=kind,
            ))
    return recovered, limitations


def _collect_recovered_atomic(
    root: Any, source: bytes, owners: Any,
) -> tuple[tuple[AtomicDeclaration, ...], tuple[str, ...]]:
    """Recover the C11 `_Atomic(type) name;` spelling from the ERROR node.

    Neither installed grammar has an atomic type-specifier rule, so the source
    arrives as `ERROR[_Atomic, parenthesized type, declarator...]` followed by
    `;`. The recovered names are the ERROR's declarator children (the type's
    own identifiers live inside the parenthesized declarator). This is the one
    place a use is matched without a DeclarationIndex record; the match stays
    bounded to the same owner span and position, never to a bare spelling
    across methods.
    """
    recovered: list[AtomicDeclaration] = []
    limitations: list[str] = []
    for node in _walk_nodes(root):
        if node.type != "ERROR":
            continue
        text = _node_text(source, node).lstrip()
        if not text.startswith(ATOMIC_QUALIFIER) or "(" not in text:
            continue
        prefix = source[max(0, node.start_byte - 32):node.start_byte].decode(
            "utf-8", "replace")
        if re.search(r"typedef\s*$", prefix):
            # `typedef _Atomic(int) T;` declares a type, not an object; the
            # typedef index handles it.
            continue
        declarators, declarator_limitations = _recovered_declarators(node, source)
        limitations.extend(declarator_limitations)
        if not declarators:
            limitations.append(f"atomic_type_specifier_unresolved@{node.start_byte}")
            continue
        owner_start, owner_end = _owner_span(owners, node.start_byte, node.end_byte)
        for name_node, kind in declarators:
            recovered.append(AtomicDeclaration(
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                name=_DECLARATOR_NAME(name_node, source) or _node_text(source, name_node),
                name_start=name_node.start_byte,
                name_end=name_node.end_byte,
                owner_start=owner_start,
                owner_end=owner_end,
                source="type_specifier",
                kind=kind,
            ))
    seen = {(entry.name_start, entry.name_end) for entry in recovered}
    extra, extra_limitations = _source_recovered_declarations(source, owners, seen)
    recovered.extend(extra)
    limitations.extend(extra_limitations)
    return tuple(recovered), tuple(limitations)


def _enclosing_compound(node: Any) -> Any:
    while node is not None:
        if node.type == "compound_statement":
            return node
        node = node.parent
    return None


def _direct_statement_of(node: Any, compound: Any) -> bool:
    """Whether `node` is the call of a statement directly inside `compound`.

    A call under an `if`, a loop, or any other nested construct is conditional:
    the region it appears to open may not execute on every path through the
    block, so pairing it with an unconditional end would fabricate atomicity.
    """
    parent = node.parent
    grandparent = parent.parent if parent is not None else None
    return (
        compound is not None
        and parent is not None
        and parent.type == "expression_statement"
        and grandparent is not None
        and grandparent.type == "compound_statement"
        and grandparent.start_byte == compound.start_byte
        and grandparent.end_byte == compound.end_byte
    )


def _collect_atomic_regions(
    root: Any, source: bytes, owners: Any,
) -> tuple[tuple[tuple[int, int], ...], tuple[str, ...]]:
    """Pair `__VERIFIER_atomic_begin/end` calls inside one owner.

    A pair is strong only when it is sequential, both calls sit in the same
    compound statement, and each call is a direct statement of that compound.
    A nested begin invalidates the open pair and itself; a conditional call, an
    end in a different block, and an unmatched call are named limitations --
    none becomes ATOMIC.
    """
    calls: list[tuple[int, int, str, int, tuple[int | None, int | None]]] = []
    limitations: list[str] = []
    # Any non-direct begin/end inside a candidate pair makes that pair's
    # extent path-dependent. Keep their positions so the pair can be revoked
    # after the direct-only pairing pass.
    invalidating: list[tuple[tuple[int | None, int | None], int]] = []
    for node in _walk_nodes(root):
        if node.type != "call_expression":
            continue
        function = node.child_by_field_name("function")
        if function is None or function.type != "identifier":
            continue
        name = _node_text(source, function).strip()
        if name not in {VERIFIER_ATOMIC_BEGIN, VERIFIER_ATOMIC_END}:
            continue
        compound = _enclosing_compound(node)
        owner = _owner_span(owners, node.start_byte, node.end_byte)
        if not _direct_statement_of(node, compound):
            limitations.append(f"atomic_block_conditional@{node.start_byte}")
            invalidating.append((owner, node.start_byte))
            continue
        calls.append((
            node.start_byte, node.end_byte, name,
            compound.start_byte if compound is not None else -1,
            owner,
        ))
    calls.sort(key=lambda call: (call[0], call[1]))

    groups: dict[tuple[int | None, int | None], list[tuple[int, int, str, int]]] = {}
    for start, end, name, compound, owner in calls:
        groups.setdefault(owner, []).append((start, end, name, compound))

    regions: list[tuple[tuple[int | None, int | None], int, int, int]] = []
    for owner, ordered in groups.items():
        stack: list[tuple[int, int, int, bool]] = []  # (start, end, compound, valid)
        for start, end, name, compound in ordered:
            if name == VERIFIER_ATOMIC_BEGIN:
                if stack:
                    # A nested begin makes every open pair and the new one
                    # non-strong: the region's extent is no longer sequential.
                    stack = [(a, b, c, False) for a, b, c, _valid in stack]
                    limitations.append(f"atomic_block_nested@{start}")
                    stack.append((start, end, compound, False))
                    continue
                stack.append((start, end, compound, True))
                continue
            if not stack:
                limitations.append(f"atomic_block_unpaired_end@{start}")
                continue
            begin_start, begin_end, begin_compound, valid = stack.pop()
            if not valid or begin_compound != compound:
                limitations.append(f"atomic_block_interleaved@{begin_start}")
                continue
            if begin_end > start:
                limitations.append(f"atomic_block_inverted@{begin_start}")
                continue
            regions.append((owner, begin_start, begin_end, start))
        for begin_start, _begin_end, _compound, _valid in stack:
            limitations.append(f"atomic_block_unpaired_begin@{begin_start}")

    strong: list[tuple[int, int]] = []
    for owner, begin_start, begin_end, end_start in regions:
        if any(
            invalid_owner == owner and begin_start <= byte <= end_start
            for invalid_owner, byte in invalidating
        ):
            # A conditional call inside the span means at least one path may
            # leave the region early; keep the whole pair unknown.
            continue
        strong.append((begin_end, end_start))
    return tuple(sorted(strong)), tuple(limitations)


def _collect_atomic_members(
    root: Any, source: bytes, types: AtomicTypeIndex,
) -> frozenset[tuple[str, str]]:
    """`(type token, member)` pairs whose member is declared atomic.

    `typedef struct { _Atomic int a; int b; } S; S s; s.a` is an atomic access
    while `s.b` is not, and the declaration index cannot answer that for an
    anonymous aggregate typedef: its fields are not reachable from `S` through
    `resolve_member`. The member list is therefore recorded per type token --
    a struct tag or any typedef name that wraps the aggregate.
    """
    members: set[tuple[str, str]] = set()
    aggregates: list[tuple[int, int, set[str]]] = []
    for node in _walk_nodes(root):
        if node.type not in {"struct_specifier", "union_specifier"}:
            continue
        body = node.child_by_field_name("body")
        if body is None:
            continue
        names: set[str] = set()
        for field in body.named_children:
            if field.type != "field_declaration":
                continue
            if _declaration_type_kind(field, source, types) not in {"object", "array"}:
                continue
            for declarator in field.children_by_field_name("declarator"):
                name = _DECLARATOR_NAME(declarator, source)
                if name:
                    names.add(name)
        if not names:
            continue
        tag_node = node.child_by_field_name("name")
        if tag_node is not None:
            tag = _node_text(source, tag_node).strip()
            if tag:
                members.update((tag, name) for name in names)
        aggregates.append((node.start_byte, node.end_byte, names))
    for node in _walk_nodes(root):
        if node.type != "type_definition":
            continue
        aliases = _type_definition_names(node, source)
        if not aliases:
            continue
        for start, end, names in aggregates:
            if node.start_byte <= start and end <= node.end_byte:
                for alias in aliases:
                    members.update((alias, name) for name in names)
    return frozenset(members)


def collect_atomic_facts(root: Any, source: bytes, owners: Any = None) -> AtomicFacts:
    """Collect the file's atomic declaration/region facts (issue-pilot#89)."""
    types = _build_atomic_type_index(root, source)
    (
        declaration_keys, pointee_keys, array_keys, declaration_limitations,
    ) = _collect_atomic_declarations(root, source, types)
    recovered, recovered_limitations = _collect_recovered_atomic(root, source, owners)
    regions, region_limitations = _collect_atomic_regions(root, source, owners)
    return AtomicFacts(
        declaration_keys=declaration_keys,
        pointee_keys=pointee_keys,
        array_keys=array_keys,
        member_keys=_collect_atomic_members(root, source, types),
        aliases=types.aliases,
        recovered=recovered,
        regions=regions,
        limitations=tuple(sorted(
            (*declaration_limitations, *recovered_limitations, *region_limitations)
        )),
    )

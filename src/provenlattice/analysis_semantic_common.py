"""Shared helpers of the semantic analyzers (I1-A/I1-B).

Owner binding, line indexing, tree diagnostics and declarator naming are the
same for every analyzer that walks a tree-sitter C/C++ parse against the base
graph's Function/Method symbols. They live here once so the events and
sparse_cfg analyzers cannot drift apart -- the same reason PR #1 feeds one
OwnerIndex to both its event layer and its CFG builder.
"""

from __future__ import annotations

import json
from bisect import bisect_left, bisect_right

from .identity import path_id
from .parsing.events import OwnerIndex, OwnerSpan


class _LineIndex:
    """Byte offset -> 1-based line, for start and inclusive end positions."""

    def __init__(self, source: bytes) -> None:
        starts = [0]
        for index, byte in enumerate(source):
            if byte == 0x0A:
                starts.append(index + 1)
        self._starts = starts

    def line_of(self, byte_offset: int, is_end: bool = False) -> int:
        if not is_end:
            return bisect_right(self._starts, byte_offset)
        # An end offset sits just past the last byte of the node: the line it
        # belongs to is the last line that starts strictly before it.
        return max(1, bisect_left(self._starts, byte_offset))


def tree_diagnostics(root) -> dict:
    error_nodes = 0
    missing_nodes = 0
    stack = [root]
    while stack:
        node = stack.pop()
        if node.is_error:
            error_nodes += 1
        if node.is_missing:
            missing_nodes += 1
        stack.extend(node.children)
    return {"error_node_count": error_nodes, "missing_node_count": missing_nodes,
            "partial": bool(error_nodes or missing_nodes)}


def declarator_name(node, source: bytes) -> str | None:
    if node is None:
        return None
    if node.type in {"identifier", "field_identifier", "type_identifier"}:
        return source[node.start_byte:node.end_byte].decode("utf-8", "replace")
    for field in ("declarator", "name", "function"):
        value = declarator_name(node.child_by_field_name(field), source)
        if value:
            return value
    for child in node.named_children:
        value = declarator_name(child, source)
        if value:
            return value
    return None


def function_symbols(store, file_id: str) -> dict:
    """Base Function/Method symbols keyed by (start_line, end_line)."""
    spans: dict[tuple[int, int], list[dict]] = {}
    for row in store.storage.rows(
        "SELECT id, kind, name, qualified_name, signature, start_line, end_line, "
        "metadata FROM nodes WHERE file_id=? AND kind IN ('Function', 'Method')",
        (file_id,),
    ):
        if row["start_line"] is None:
            continue
        try:
            definition = json.loads(row["metadata"] or "{}").get("definition")
        except ValueError:
            definition = None
        spans.setdefault((row["start_line"], row["end_line"]), []).append({
            "id": row["id"], "kind": row["kind"], "name": row["name"],
            "qualified_name": row["qualified_name"], "signature": row["signature"],
            "definition": definition,
        })
    return spans


def owner_index(
    store, file_id: str, root, source: bytes
) -> tuple[OwnerIndex, dict, dict]:
    """OwnerIndex over base-symbol identities, aligned per function definition.

    Every ``function_definition`` node in the parse claims the base symbol that
    shares its line span; a collapsed span with several candidates prefers the
    ``definition: true`` symbol, then the matching name, and stays unbound
    (counted) when both fail -- the I0R1 alignment rule, applied here against
    the base graph directly so the analyzers cover .cc/.cpp files that the
    .c/.h-only ast layer does not materialize.

    The third return value maps the owner identity triple the PR event model
    repeats (kind, qualified_name, signature) to the base symbol's stable id;
    a key claimed by two different symbols maps to None (ambiguous) and makes
    the file fail loudly rather than binding events to a guessed owner.
    """
    spans = function_symbols(store, file_id)
    counters = {"functions_unbound": 0, "functions_bound": 0}
    owner_spans: list[OwnerSpan] = []
    owner_ids: dict[tuple[str, str, str], str | None] = {}
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "function_definition":
            key = (node.start_point[0] + 1, node.end_point[0] + 1)
            candidates = list(spans.get(key, []))
            chosen = None
            if len(candidates) == 1:
                chosen = candidates[0]
            elif candidates:
                defined = [item for item in candidates if item["definition"] is True]
                if len(defined) == 1:
                    chosen = defined[0]
                else:
                    name = declarator_name(
                        node.child_by_field_name("declarator"), source)
                    named = [item for item in candidates
                             if name is not None and item["name"] == name]
                    if len(named) == 1:
                        chosen = named[0]
            if chosen is None:
                counters["functions_unbound"] += 1
            else:
                counters["functions_bound"] += 1
                owner_spans.append(OwnerSpan(
                    start_byte=node.start_byte, end_byte=node.end_byte,
                    kind=chosen["kind"], qualified_name=chosen["qualified_name"],
                    signature=chosen["signature"] or "",
                ))
                identity = (chosen["kind"], chosen["qualified_name"],
                            chosen["signature"] or "")
                if owner_ids.get(identity, chosen["id"]) != chosen["id"]:
                    owner_ids[identity] = None
                else:
                    owner_ids[identity] = chosen["id"]
        stack.extend(node.children)
    return OwnerIndex(owner_spans), counters, owner_ids


def owner_symbol_id(owner_ids: dict, event) -> str:
    """Resolve the repeating owner identity to the base symbol's stable id.

    A miss (or an ambiguous triple claimed by two symbols) raises rather than
    writing an event that claims an owner no query can resolve.
    """
    identity = (event.owner_kind, event.owner_qualified_name, event.owner_signature)
    if identity not in owner_ids:
        raise RuntimeError(
            f"event owner not found in base graph: {event.owner_qualified_name!r}"
        )
    symbol_id = owner_ids[identity]
    if symbol_id is None:
        raise RuntimeError(
            f"event owner is ambiguous in base graph: {event.owner_qualified_name!r}"
        )
    return symbol_id


__all__ = [
    "_LineIndex", "tree_diagnostics", "declarator_name", "function_symbols",
    "owner_index", "owner_symbol_id", "path_id",
]

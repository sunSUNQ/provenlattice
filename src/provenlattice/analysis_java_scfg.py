"""Java Sparse CFG materializer (I1-B-Java) over the derived-analysis store.

Extends the C/C++ Sparse CFG capability to Java using the tree-sitter Java
grammar (``parsing.java.JavaTreeSitterParser``). The DFG mint in
``sparsedfg.mint_dataflow_edges`` is reused unchanged; this module only builds
the Java-specific control-flow + access points and annotations that feed it.

Scope (V2, local-variable + field level):
  * local variable declaration / initialization;
  * assignment, compound assignment, update expression;
  * method parameter binding;
  * identifier read/write with lexical scoping and shadowing;
  * field read/write on a bindable receiver (`this.field`, `obj.field` where
    `obj` is a known local/parameter); identity is (receiver-root, member-path),
    so distinct objects' fields never merge without alias evidence;
  * return;
  * if/else branch + merge;
  * while/for loop + back edge.

Deliberately NOT produced (degraded to no data-flow fact, never fabricated):
  * cross-procedural points-to; alias tracking; heap-sensitive analysis;
    reflection targets; try-with-resources; ALLOC/RELEASE/CONSUMES/DEREFERENCE;
    field access with a non-`this`/non-local receiver (method-call receiver,
    array index, nested `a.b.c`, class-name receiver).
"""

from __future__ import annotations

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
from .analysis_ast import normalize_scope, scoped_sources
from .analysis_semantic_common import _LineIndex, function_symbols, tree_diagnostics
from .identity import cfg_exit_id, event_id, path_id, semantic_edge_id
from .models import (
    ParsedCfg,
    ParsedEdge,
    ParsedPoint,
    PointKey,
    STORAGE_FIELD,
    STORAGE_LOCAL,
    STORAGE_PARAMETER,
    STORAGE_UNKNOWN,
)
from .parsing.java import JavaTreeSitterParser
from .sparsecfg import (
    BRANCH_FALSE,
    BRANCH_TRUE,
    CONTROL_REACHES,
    FALLTHROUGH,
    LOOP_BACK,
)
from .storage import SQLiteStorage

ANALYZER = analyzer_id("sparse_cfg", "java")
SCFG_VERSION = ANALYZER_VERSIONS[ANALYZER]
SCFG_CONTRACT = analyzer_contract("sparse_cfg", "java", SCFG_VERSION)
CAPABILITY_LEVEL = "level0+structural+access"

JAVA_SUFFIXES = frozenset({".java"})

# Serialization separator for a CALL point's argument-root list. Kept local
# (mirrors sparsedfg.ARGUMENT_SEPARATOR) so the SCFG builder has no DFG-layer
# import; empty roots keep their ordinal slot so interprocedural binding aligns
# caller argument i to callee parameter i.
ARGUMENT_SEPARATOR = "\x1f"

_METHOD_NODES = frozenset(
    {"method_declaration", "constructor_declaration", "compact_constructor_declaration"}
)
_ACCESS_EVENT_TYPES = frozenset({"READ", "WRITE"})
_STRUCTURAL_EVENT_TYPES = frozenset({"CHECK", "BRANCH", "RETURN"})

# A Java statement/declaration node that opens a lexical scope for locals.
_BLOCK_NODES = frozenset({"block", "for_statement", "enhanced_for_statement"})


def java_owner_index(store, file_id: str, root, source: bytes):
    """OwnerIndex over base Method symbols, aligned per Java method declaration.

    Same rule as ``analysis_semantic_common.owner_index`` but walks
    ``method_declaration`` / ``constructor_declaration`` /
    ``compact_constructor_declaration`` nodes. Java Method symbols carry
    ``kind='Method'``; the span key (start_line, end_line) is the alignment
    fact, the name field breaks same-span collisions.
    """
    spans = function_symbols(store, file_id)
    counters = {"functions_unbound": 0, "functions_bound": 0}
    owner_spans = []
    owner_ids: dict[tuple[str, str, str], str | None] = {}
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type not in _METHOD_NODES:
            stack.extend(node.children)
            continue
        key = (node.start_point[0] + 1, node.end_point[0] + 1)
        candidates = list(spans.get(key, []))
        chosen = None
        if len(candidates) == 1:
            chosen = candidates[0]
        elif candidates:
            name = _method_name(node, source)
            named = [c for c in candidates if name is not None and c["name"] == name]
            if len(named) == 1:
                chosen = named[0]
        if chosen is None:
            counters["functions_unbound"] += 1
        else:
            counters["functions_bound"] += 1
            owner_spans.append(
                OwnerSpanLike(node.start_byte, node.end_byte, chosen["kind"],
                              chosen["qualified_name"], chosen["signature"] or ""))
            identity = (chosen["kind"], chosen["qualified_name"],
                        chosen["signature"] or "")
            owner_ids[identity] = (None if owner_ids.get(identity, chosen["id"]) != chosen["id"]
                                   else chosen["id"])
        stack.extend(node.children)
    return _OwnerIndex(owner_spans), counters, owner_ids


class OwnerSpanLike:  # mirrors parsing.events.OwnerSpan (avoids importing the C matcher)
    __slots__ = ("start_byte", "end_byte", "kind", "qualified_name", "signature")

    def __init__(self, start_byte, end_byte, kind, qualified_name, signature):
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.kind = kind
        self.qualified_name = qualified_name
        self.signature = signature


class _OwnerIndex:
    def __init__(self, spans):
        self._spans = sorted(spans, key=lambda s: (s.start_byte, -s.end_byte))
        self._starts = [s.start_byte for s in self._spans]

    def owner_of(self, start_byte: int, end_byte: int):
        from bisect import bisect_right
        index = bisect_right(self._starts, start_byte) - 1
        while index >= 0:
            span = self._spans[index]
            if span.end_byte >= end_byte:
                return span
            index -= 1
        return None

    @property
    def spans(self):
        return tuple(self._spans)


def _method_name(node, source: bytes) -> str | None:
    name = node.child_by_field_name("name")
    if name is None:
        return None
    return source[name.start_byte:name.end_byte].decode("utf-8", "replace") or None


def _node_text(source: bytes, node) -> str:
    if node is None:
        return ""
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _dedup(points: list) -> list:
    seen: set = set()
    out: list = []
    for point in points:
        if point.key() in seen:
            continue
        seen.add(point.key())
        out.append(point)
    return out


class JavaSparseCfgBuilder:
    """Build the method-local sparse CFG + access points for one Java parse."""

    def __init__(self, source: bytes, owners, line_of):
        self.source = source
        self.owners = owners
        self.line_of = line_of
        self.points: list[ParsedPoint] = []
        self.edges: list[ParsedEdge] = []
        self.annotations: dict[PointKey, dict[str, str]] = {}
        self._ordinal = 0
        self._decl_counter = 0
        self._scopes: list[dict[str, str]] = [{}]
        self._current_owner = None
        self._last_control: ParsedPoint | None = None

    # -- ordinal / identity -------------------------------------------------
    def _new_point(self, event_type, node, matched_name, flags=()) -> ParsedPoint:
        owner = self._current_owner
        self._ordinal += 1
        point = ParsedPoint(
            event_type=event_type,
            owner_kind=owner.kind,
            owner_qualified_name=owner.qualified_name,
            owner_signature=owner.signature,
            ordinal=self._ordinal,
            start_line=self.line_of(node.start_byte),
            end_line=self.line_of(node.end_byte, is_end=True),
            matched_name=matched_name,
            matched_via="structural",
            flags=tuple(flags),
        )
        self.points.append(point)
        return point

    def _link(self, src: ParsedPoint, dst: ParsedPoint | None, flags=()):
        self.edges.append(ParsedEdge(src=src.key(), dst=dst.key() if dst else None, flags=tuple(flags)))

    # -- lexical scope ------------------------------------------------------
    def _declare(self, name: str, storage: str) -> str:
        self._decl_counter += 1
        token = f"{storage}:{name}#{self._decl_counter}"
        self._scopes[-1][name] = token
        return token

    def _lookup(self, name: str) -> tuple[str, str] | None:
        for scope in reversed(self._scopes):
            if name in scope:
                token = scope[name]
                storage = token.split(":", 1)[0]
                return token, storage
        return None

    # -- access points ------------------------------------------------------
    def _emit_read(self, name: str, node) -> None:
        resolved = self._lookup(name)
        point = self._new_point("READ", node, name)
        if resolved is not None:
            token, storage = resolved
            self.annotations[point.key()] = self._facts(token, storage, name)
        # An unresolved identifier (field / static / unknown) is a READ with no
        # declared local identity: published edgeless with no flow facts, so the
        # DFG never mints a false def-use through a name it cannot bind.

    def _emit_write(self, name: str, node, storage: str) -> None:
        token = self._declare(name, storage)
        point = self._new_point("WRITE", node, name)
        self.annotations[point.key()] = self._facts(token, storage, name)

    @staticmethod
    def _facts(token: str, storage: str, name: str) -> dict[str, str]:
        return {
            "subject_decl": token,
            "subject_storage": storage,
            "subject_member": "",
            "subject": name,
            "subject_site": "",
            "subject_exact": "true",
        }

    # -- field access (V2: field read/write on this / local-object receivers) --
    def _field_facts(self, node):
        """The flow facts for a `field_access`, or None when it cannot be bound.

        Supported and bound to a stable identity:
          * ``this.field`` -> subject=field, storage=field, decl=field:<owner>:field;
          * ``obj.field``  -> subject=obj, storage=obj's storage, member="field",
            decl=obj's local declaration token.

        Returns (subject, subject_decl, subject_storage, subject_member).
        Anything else (nested field_access, method-call receiver, array index,
        class-name receiver, unresolved local) returns None so the caller
        degrades instead of fabricating a precise dependency.
        """
        if node is None or node.type != "field_access":
            return None
        object_node = node.child_by_field_name("object")
        field_node = node.child_by_field_name("field")
        if object_node is None or field_node is None:
            return None
        field_name = _node_text(self.source, field_node)
        if object_node.type == "this":
            scope = self._current_owner.qualified_name if self._current_owner else ""
            return (field_name, f"field:{scope}:{field_name}", STORAGE_FIELD, "")
        if object_node.type == "identifier":
            obj_name = _node_text(self.source, object_node)
            resolved = self._lookup(obj_name)
            if resolved is None:
                return None
            token, storage = resolved
            return (obj_name, token, storage, field_name)
        return None

    @staticmethod
    def _field_annotation(decl, storage, member, subject) -> dict[str, str]:
        return {
            "subject_decl": decl,
            "subject_storage": storage,
            "subject_member": member,
            "subject": subject,
            "subject_site": "",
            "subject_exact": "true",
        }

    def _emit_field_read(self, node, facts) -> None:
        subject, decl, storage, member = facts
        point = self._new_point("READ", node, subject)
        self.annotations[point.key()] = self._field_annotation(decl, storage, member, subject)

    def _emit_field_write(self, node, facts) -> None:
        subject, decl, storage, member = facts
        point = self._new_point("WRITE", node, subject)
        self.annotations[point.key()] = self._field_annotation(decl, storage, member, subject)

    def _argument_roots(self, args_node) -> list[str]:
        """Argument root names, empty slot for anything non-identifier.

        An identifier argument binds by name; anything else (literal, call
        result, field access, ``this``) keeps an empty slot so the ordinal
        alignment is preserved without fabricating a root dependency.
        """
        if args_node is None:
            return []
        roots = []
        for arg in args_node.named_children:
            if arg.type == "identifier":
                roots.append(_node_text(self.source, arg))
            else:
                roots.append("")
        return roots

    def _emit_call(self, node) -> None:
        """Emit a CALL point for a method invocation.

        The annotation records the callee's short name and the argument-root
        list (ordinal-preserving). The method-local DFG reads ``arguments`` to
        mint input_to_sink (argument def -> CALL); the interprocedural pass
        reads ``callee`` + the same list to bind caller argument i to callee
        parameter i.
        """
        name_node = node.child_by_field_name("name")
        callee = _node_text(self.source, name_node) if name_node is not None else ""
        roots = self._argument_roots(node.child_by_field_name("arguments"))
        point = self._new_point("CALL", node, callee)
        self.annotations[point.key()] = {
            "subject": callee,
            "callee": callee,
            "arguments": ARGUMENT_SEPARATOR.join(roots),
            "subject_storage": "",
            "subject_decl": "",
            "subject_member": "",
            "subject_site": "",
            "subject_exact": "true",
        }

    # -- expression walking ------------------------------------------------
    def _walk_expression(self, node) -> None:
        if node is None:
            return
        t = node.type
        if t == "identifier":
            self._emit_read(_node_text(self.source, node), node)
        elif t in ("assignment_expression", "compound_assignment_expression"):
            self._walk_assignment(node)
        elif t == "update_expression":
            arg = next((c for c in node.named_children), None)
            name = self._lhs_name(arg)
            if name is not None and arg is not None and arg.type == "identifier":
                self._emit_read(name, arg)      # read-before-write (x++ / ++x)
                self._emit_write(name, arg, STORAGE_LOCAL)
            else:
                self._walk_expression(arg)
        elif t == "field_access":
            # V2: a bindable field access (this.field / obj.field) emits one
            # field READ; an un-bindable receiver degrades to walking the
            # receiver object only (no fabricated field dependency).
            facts = self._field_facts(node)
            if facts is not None:
                self._emit_field_read(node, facts)
            else:
                self._walk_expression(node.child_by_field_name("object"))
        elif t == "method_invocation":
            self._walk_expression(node.child_by_field_name("object"))
            args = node.child_by_field_name("arguments")
            if args is not None:
                self._walk_expression(args)
            self._emit_call(node)
        elif t == "object_creation_expression":
            args = node.child_by_field_name("arguments")
            if args is not None:
                self._walk_expression(args)
        else:
            for child in node.named_children:
                self._walk_expression(child)

    def _lhs_name(self, node) -> str | None:
        if node is None:
            return None
        if node.type == "identifier":
            return _node_text(self.source, node)
        if node.type == "field_access":
            return _node_text(self.source, node.child_by_field_name("field"))
        return None

    def _walk_assignment(self, node) -> None:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        operator = node.child_by_field_name("operator")
        op_text = _node_text(self.source, operator) if operator is not None else "="
        if left is not None and left.type == "field_access":
            facts = self._field_facts(left)
            if facts is not None:
                if op_text != "=":
                    self._emit_field_read(left, facts)  # compound read-before-write
                self._walk_expression(right)
                self._emit_field_write(left, facts)
            else:
                self._walk_expression(left.child_by_field_name("object"))
                self._walk_expression(right)
            return
        name = self._lhs_name(left)
        if name is not None and left.type == "identifier":
            if op_text != "=":
                self._emit_read(name, left)  # x += 2 => read-before-write
            self._walk_expression(right)
            self._emit_write(name, left, STORAGE_LOCAL)
        else:
            # array element or other unsupported LHS: read roots, no write fact.
            self._walk_expression(left)
            self._walk_expression(right)

    def _walk_local_decl(self, node) -> None:
        for declarator in node.named_children:
            if declarator.type != "variable_declarator":
                continue
            name_node = declarator.child_by_field_name("name")
            if name_node is None:
                continue
            name = _node_text(self.source, name_node)
            value = declarator.child_by_field_name("value")
            if value is not None:
                self._walk_expression(value)  # RHS reads first
            self._emit_write(name, name_node, STORAGE_LOCAL)

    def _walk_return(self, node):
        value = next((c for c in node.named_children), None)
        self._walk_expression(value)
        point = self._new_point("RETURN", node, "return")
        if value is not None and value.type == "identifier":
            name = _node_text(self.source, value)
            resolved = self._lookup(name)
            if resolved is not None:
                token, storage = resolved
                self.annotations[point.key()] = self._facts(token, storage, name)
        return point

    # -- statements ---------------------------------------------------------
    def _walk_statement(self, node):
        """Walk one statement, returning (entries, exits) of structural points.

        ``entries`` are the structural points that begin the statement's control
        flow; ``exits`` are the structural points that fall through to the next
        statement (empty for ``return``). A statement that emits no structural
        point (declaration, simple expression) is transparent: both lists empty.
        """
        if node is None:
            return [], []
        t = node.type
        if t == "block":
            return self._walk_block(node)
        if t == "local_variable_declaration":
            self._walk_local_decl(node)
            return [], []
        if t == "expression_statement":
            self._walk_expression(node)
            return [], []
        if t == "return_statement":
            point = self._walk_return(node)
            return ([point] if point is not None else []), []
        if t == "if_statement":
            return self._walk_if(node)
        if t in ("while_statement", "for_statement"):
            return self._walk_loop(node)
        if t in ("enhanced_for_statement", "try_statement", "try_with_resources_statement",
                 "switch_expression", "switch_statement", "synchronized_statement",
                 "lambda_expression", "throw_statement"):
            self._walk_expression(node)  # degrade: no fabricated control flow
            return [], []
        self._walk_expression(node)
        return [], []

    def _walk_block(self, node):
        self._scopes.append({})
        block_entries: list[ParsedPoint] = []
        prev_exits: list[ParsedPoint] = []
        for stmt in node.named_children:
            entries, exits = self._walk_statement(stmt)
            for src in prev_exits:
                for dst in entries:
                    self._link(src, dst, (FALLTHROUGH,))
            if entries:
                if not block_entries:
                    block_entries = entries
                prev_exits = exits
            # transparent statement: prev_exits carries through unchanged
        self._scopes.pop()
        return block_entries, prev_exits

    def _walk_if(self, node):
        cond = node.child_by_field_name("condition")
        self._walk_expression(cond)
        cond_text = _node_text(self.source, cond)[:40]
        check = self._new_point("CHECK", cond, cond_text)
        consequence = node.child_by_field_name("consequence")
        alternative = node.child_by_field_name("alternative")
        then_entries, then_exits = self._walk_statement(consequence)
        else_entries, else_exits = self._walk_statement(alternative)
        then_head = self._new_point("BRANCH", consequence or cond, cond_text)
        else_head = self._new_point("BRANCH", alternative or cond, cond_text)
        self._link(check, then_head, (BRANCH_TRUE,))
        self._link(check, else_head, (BRANCH_FALSE,))
        for dst in then_entries:
            self._link(then_head, dst, (FALLTHROUGH,))
        for dst in else_entries:
            self._link(else_head, dst, (FALLTHROUGH,))
        then_tails = then_exits if then_entries else [then_head]
        else_tails = else_exits if else_entries else [else_head]
        exits = _dedup(then_tails + else_tails)
        return [check], exits

    def _walk_loop(self, node):
        cond = node.child_by_field_name("condition")
        self._walk_expression(cond)
        check = self._new_point(
            "CHECK", cond, _node_text(self.source, cond)[:40] if cond is not None else "for")
        if node.type == "for_statement":
            self._walk_expression(node.child_by_field_name("init"))
        body = node.child_by_field_name("body")
        body_entries, body_exits = self._walk_statement(body)
        if node.type == "for_statement":
            self._walk_expression(node.child_by_field_name("update"))
        body_head = self._new_point("BRANCH", body or cond or node, "loop")
        self._link(check, body_head, (BRANCH_TRUE,))
        for dst in body_entries:
            self._link(body_head, dst, (FALLTHROUGH,))
        for src in (body_exits if body_entries else [body_head]):
            self._link(src, check, (LOOP_BACK,))
        return [check], [check]  # branch=false falls through from the check

    def build(self, root) -> ParsedCfg:
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type in _METHOD_NODES:
                owner = self.owners.owner_of(node.start_byte, node.end_byte)
                if owner is not None:
                    self._build_method(node, owner)
            stack.extend(node.children)
        return ParsedCfg(points=self.points, edges=self.edges, annotations=self.annotations)

    def _build_method(self, node, owner) -> None:
        self._current_owner = owner
        self._ordinal = 0
        self._decl_counter = 0
        self._scopes = [{}]
        params = node.child_by_field_name("parameters")
        if params is not None:
            for param in params.named_children:
                if param.type != "formal_parameter":
                    continue
                name_node = param.child_by_field_name("name")
                if name_node is None:
                    continue
                self._emit_write(_node_text(self.source, name_node), name_node, STORAGE_PARAMETER)
        body = node.child_by_field_name("body")
        if body is not None:
            _entries, exits = self._walk_block(body)
            for src in exits:
                self._link(src, None)  # fall through to the synthetic exit


def analyze_java_scfg_scope(repo, scope: str, database=None) -> dict:
    started = time.perf_counter()
    root = Path(repo).resolve()
    scope_path = normalize_scope(scope)
    database = Path(database).resolve() if database else root / ".provenlattice" / "codegraph.db"
    scoped = scoped_sources(root, scope_path)
    materialized, reused = [], []
    skipped_unsupported, skipped_not_in_base, skipped_base_out_of_date = [], [], []
    skipped_no_points, skipped_payload_too_large = [], []
    counters = {"points_published": 0, "edges_published": 0,
                "functions_bound": 0, "functions_unbound": 0}
    parser = JavaTreeSitterParser()
    with SQLiteStorage(database) as storage:
        if storage.repository() is None:
            raise RuntimeError("repository is not indexed; run `provenlattice index` first")
        repo_id = storage.repository()["repo_id"]
        store = AnalysisStore(storage)
        for source in scoped:
            if Path(source.relative_path).suffix.lower() not in JAVA_SUFFIXES:
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
            if (state is not None
                    and state.get("metadata", {}).get("contract") == SCFG_CONTRACT
                    and store.is_analysis_fresh(file_id, ANALYZER, base_hash, SCFG_VERSION)):
                reused.append(source.relative_path)
                continue
            source_bytes = source.path.read_bytes()
            outcome = parser.parse_bytes(source_bytes, source.relative_path)
            lines = _LineIndex(source_bytes)
            owners, owner_counters, owner_ids = java_owner_index(
                store, file_id, outcome.tree.root_node, source_bytes)
            builder = JavaSparseCfgBuilder(source_bytes, owners, lines.line_of)
            cfg = builder.build(outcome.tree.root_node)
            diagnostics = tree_diagnostics(outcome.tree.root_node)

            id_by_key = {}
            nodes = []
            for point in cfg.points:
                owner = _owner_of(owner_ids, point)
                key = point.key()
                node_id = event_id(repo_id, owner, point.event_type, point.ordinal)
                id_by_key[key] = node_id
                payload = {
                    "owner_symbol_id": owner, "file_id": file_id,
                    "owner_kind": point.owner_kind,
                    "owner_qualified_name": point.owner_qualified_name,
                    "owner_signature": point.owner_signature,
                    "ordinal": point.ordinal,
                    "start_line": point.start_line, "end_line": point.end_line,
                    "matched_name": point.matched_name,
                    "matched_via": point.matched_via,
                    "flags": list(point.flags),
                    "analyzer": ANALYZER, "contract": SCFG_CONTRACT,
                    "language": "java", "level": CAPABILITY_LEVEL,
                }
                annotations = cfg.annotations.get(key) or {}
                if annotations:
                    payload["annotations"] = dict(annotations)
                nodes.append(AnalysisNode(node_id, point.event_type, payload))

            edges = []
            for edge in cfg.edges:
                src_id = id_by_key[edge.src]
                src_owner = _owner_of(owner_ids, edge.src)
                if edge.dst is None:
                    dst_id = cfg_exit_id(repo_id, src_owner)
                else:
                    dst_id = id_by_key[edge.dst]
                edges.append(AnalysisEdge(
                    semantic_edge_id(src_id, dst_id, CONTROL_REACHES,
                                     "\x1f".join(sorted(edge.flags))),
                    src_id, dst_id, CONTROL_REACHES,
                    {"owner_symbol_id": src_owner, "flags": list(sorted(edge.flags)),
                     "analyzer": ANALYZER, "contract": SCFG_CONTRACT},
                ))

            try:
                store.replace_analysis_for_file(
                    file_id, ANALYZER, base_hash, SCFG_VERSION, nodes, edges,
                    metadata={"analyzer": ANALYZER, "contract": SCFG_CONTRACT,
                              "language": "java", "level": CAPABILITY_LEVEL,
                              "scope": scope_path.as_posix(),
                              "event_count": len(nodes), "edge_count": len(edges),
                              **owner_counters, **diagnostics,
                              "analysis_status": "degraded" if diagnostics["partial"] else "complete"},
                )
            except PayloadTooLargeError:
                skipped_payload_too_large.append(source.relative_path)
                continue
            if not nodes:
                skipped_no_points.append(source.relative_path)
            materialized.append(source.relative_path)
            counters["points_published"] += len(nodes)
            counters["edges_published"] += len(edges)
            counters["functions_bound"] += owner_counters["functions_bound"]
            counters["functions_unbound"] += owner_counters["functions_unbound"]
    return {
        "repo_id": repo_id, "database": str(database), "scope": scope_path.as_posix(),
        "analyzer": ANALYZER, "contract": SCFG_CONTRACT, "feature_version": SCFG_VERSION,
        "level": CAPABILITY_LEVEL,
        "scope_source_files": len(scoped),
        "materialized": sorted(materialized), "reused": sorted(reused),
        "skipped_unsupported": sorted(skipped_unsupported),
        "skipped_not_in_base": sorted(skipped_not_in_base),
        "skipped_base_out_of_date": sorted(skipped_base_out_of_date),
        "skipped_no_points": sorted(skipped_no_points),
        "skipped_payload_too_large": sorted(skipped_payload_too_large),
        "points_published": counters["points_published"],
        "edges_published": counters["edges_published"],
        "functions_bound": counters["functions_bound"],
        "functions_unbound": counters["functions_unbound"],
        "analyze_time_ms": (time.perf_counter() - started) * 1000,
    }


def _owner_of(owner_ids: dict, point) -> str:
    identity = (point.owner_kind, point.owner_qualified_name, point.owner_signature)
    if identity not in owner_ids or owner_ids[identity] is None:
        raise RuntimeError(f"sparse cfg point owner unresolvable: {identity}")
    return owner_ids[identity]

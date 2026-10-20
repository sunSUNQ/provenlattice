"""Java intraprocedural CFG V1 materializer over the derived-analysis store."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path, PurePosixPath

from .analysis import (
    ANALYZER_VERSIONS, AnalysisEdge, AnalysisNode, AnalysisStore,
    PayloadTooLargeError, analyzer_contract, analyzer_id,
)
from .analysis_java_ast import (
    JAVA_AST_CONTRACT, ast_node_id, normalize_scope, scoped_sources,
)
from .identity import path_id
from .parsing.java import JavaTreeSitterParser
from .scanner import scan_repository
from .storage import SQLiteStorage

AST_ANALYZER = "ast:java"
ANALYZER = analyzer_id("cfg", "java")
JAVA_CFG_VERSION = ANALYZER_VERSIONS[ANALYZER]
JAVA_CFG_CONTRACT = analyzer_contract("cfg", "java", JAVA_CFG_VERSION)

METHOD_KINDS = frozenset({"method_declaration", "constructor_declaration",
                           "compact_constructor_declaration"})
# Unsupported Java constructs for V1 CFG (conservative skip)
FORBIDDEN = frozenset({
    "try_statement", "try_with_resources_statement", "throw_statement",
    "synchronized_statement", "switch_expression", "yield_statement",
    "labeled_statement",
})


class _Unsupported(Exception):
    pass


class _LoopFrame:
    __slots__ = ("header_id", "breaks", "continues")
    def __init__(self, header: str) -> None:
        self.header_id = header
        self.breaks: list[str] = []
        self.continues: list[str] = []


class _FunctionCFG:
    __slots__ = ("file_id", "owner", "nodes", "edges", "returns",
                 "loop_stack", "breaks", "continues", "_ord")

    def __init__(self, file_id: str, owner: str) -> None:
        self.file_id = file_id
        self.owner = owner
        self.nodes: list[AnalysisNode] = []
        self.edges: list[AnalysisEdge] = []
        self.returns: list[str] = []
        self.loop_stack: list[_LoopFrame] = []
        self.breaks: list[str] = []
        self.continues: list[str] = []
        self._ord: dict[tuple[str, str, str], int] = {}

    def node(self, kind: str, role: str, path: str, *,
             start_byte: int | None = None, end_byte: int | None = None) -> str:
        canonical = "\x1f".join((self.file_id, self.owner, role, path))
        nid = f"cnode:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
        self.nodes.append(AnalysisNode(nid, kind, {
            "owner_symbol_id": self.owner,
            "start_byte": start_byte, "end_byte": end_byte,
            "structural_role": role, "structural_path": path,
        }))
        return nid

    def edge(self, src: str, dst: str, kind: str) -> None:
        key = (src, dst, kind)
        ordinal = self._ord.get(key, 0)
        self._ord[key] = ordinal + 1
        canonical = "\x1f".join((*key, str(ordinal)))
        eid = f"cedge:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
        self.edges.append(AnalysisEdge(eid, src, dst, kind,
                                       {"owner_symbol_id": self.owner}))


def _ast_id(file_id: str, paths: dict, node) -> str | None:
    p = paths.get((node.type, node.start_byte, node.end_byte))
    return ast_node_id(file_id, p) if p else None


def _scan_unsupported(func_node) -> str | None:
    stack = [func_node]
    while stack:
        n = stack.pop()
        if n is not func_node and n.type in METHOD_KINDS:
            continue
        if n.type in FORBIDDEN:
            return n.type
        stack.extend(n.named_children)
    return None


def analyze_cfg_scope(repo: str | Path, scope: str, database: str | Path | None = None) -> dict:
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
    skipped_ast_missing: list[str] = []
    skipped_ast_stale: list[str] = []
    skipped_payload_too_large: list[str] = []
    counters = {"methods_built": 0, "methods_skipped_unmatched_owner": 0,
                "methods_skipped_unsupported_construct": 0,
                "methods_skipped_parse_error": 0,
                "methods_skipped_ast_node_missing": 0}
    nodes_written = 0
    edges_written = 0
    with SQLiteStorage(database) as storage:
        repo_row = storage.repository()
        if not repo_row:
            raise RuntimeError("repository is not indexed")
        repo_id = repo_row["repo_id"]
        store = AnalysisStore(storage)
        for source in scoped:
            if source.language != "java":
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
            ast_read = store.read_current_analysis(file_id, AST_ANALYZER)
            if ast_read is None or ast_read["state"]["metadata"].get("contract") != JAVA_AST_CONTRACT:
                skipped_ast_missing.append(source.relative_path)
                continue
            if not ast_read["fresh"]:
                skipped_ast_stale.append(source.relative_path)
                continue
            state = store.get_analysis_state(file_id, ANALYZER)
            if (state is not None
                    and state.get("metadata", {}).get("contract") == JAVA_CFG_CONTRACT
                    and state.get("metadata", {}).get("analyzer") == ANALYZER
                    and store.is_analysis_fresh(file_id, ANALYZER, base_hash, JAVA_CFG_VERSION)):
                reused.append(source.relative_path)
                continue
            try:
                nodes, edges, fc = _build_file_cfg(store, file_id, source, ast_read)
                store.replace_analysis_for_file(
                    file_id, ANALYZER, base_hash, JAVA_CFG_VERSION, nodes, edges,
                    metadata={"analyzer": ANALYZER, "contract": JAVA_CFG_CONTRACT,
                              "language": "java", "scope": scope_path.as_posix(),
                              "node_count": len(nodes), "edge_count": len(edges),
                              "ast_contract": JAVA_AST_CONTRACT,
                              "dependencies": {"ast:java": JAVA_AST_CONTRACT},
                              **fc})
            except PayloadTooLargeError:
                skipped_payload_too_large.append(source.relative_path)
                continue
            for k in counters:
                counters[k] += fc.get(k, 0)
            materialized.append(source.relative_path)
            nodes_written += len(nodes)
            edges_written += len(edges)
    return {"repo_id": repo_id, "database": str(database),
            "scope": scope_path.as_posix(), "analyzer": ANALYZER,
            "contract": JAVA_CFG_CONTRACT, "feature_version": JAVA_CFG_VERSION,
            "ast_dependency": AST_ANALYZER, "scope_source_files": len(scoped),
            "materialized": sorted(materialized), "reused": sorted(reused),
            "skipped_unsupported": sorted(skipped_unsupported),
            "skipped_not_in_base": sorted(skipped_not_in_base),
            "skipped_base_out_of_date": sorted(skipped_base_out_of_date),
            "skipped_ast_missing": sorted(skipped_ast_missing),
            "skipped_ast_stale": sorted(skipped_ast_stale),
            "skipped_payload_too_large": sorted(skipped_payload_too_large),
            "methods_built": counters["methods_built"],
            "methods_skipped_unmatched_owner": counters["methods_skipped_unmatched_owner"],
            "methods_skipped_unsupported_construct": counters["methods_skipped_unsupported_construct"],
            "methods_skipped_parse_error": counters["methods_skipped_parse_error"],
            "methods_skipped_ast_node_missing": counters["methods_skipped_ast_node_missing"],
            "nodes_written": nodes_written, "edges_written": edges_written,
            "analyze_time_ms": (time.perf_counter() - started) * 1000}


def _build_file_cfg(store: AnalysisStore, file_id: str, source, ast_read: dict):
    parser = JavaTreeSitterParser()
    outcome = parser.parse_bytes(source.path.read_bytes(), source.relative_path)
    root = outcome.tree.root_node
    ast_read_map = {}
    for row in ast_read["nodes"]:
        if row["kind"] in METHOD_KINDS:
            payload = row["payload"]
            ast_read_map[(payload["start_byte"], payload["end_byte"])] = payload
    nodes: list[AnalysisNode] = []
    edges: list[AnalysisEdge] = []
    counters = {"methods_built": 0, "methods_skipped_unmatched_owner": 0,
                "methods_skipped_unsupported_construct": 0,
                "methods_skipped_parse_error": 0,
                "methods_skipped_ast_node_missing": 0}
    ordered = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in METHOD_KINDS:
            ordered.append(node)
        stack.extend(node.named_children)
    for func_node in ordered:
        key = (func_node.start_byte, func_node.end_byte)
        info = ast_read_map.get(key)
        if info is None:
            counters["methods_skipped_ast_node_missing"] += 1
            continue
        owner = info.get("owner_symbol_id")
        if owner is None:
            counters["methods_skipped_unmatched_owner"] += 1
            continue
        # has_error covers ERROR and MISSING nodes in all descendants
        # (including nested methods): a method whose tree did not fully
        # parse is skipped instead of producing a guessed CFG.
        if func_node.has_error:
            counters["methods_skipped_parse_error"] += 1
            continue
        unsupported = _scan_unsupported(func_node)
        if unsupported is not None:
            counters["methods_skipped_unsupported_construct"] += 1
            continue
        builder = _JavaCFGBuilder(file_id, owner)
        fn_nodes, fn_edges = builder.build(func_node)
        nodes.extend(fn_nodes)
        edges.extend(fn_edges)
        counters["methods_built"] += 1
    return nodes, edges, counters


class _JavaCFGBuilder:
    def __init__(self, file_id: str, owner: str) -> None:
        self.f = _FunctionCFG(file_id, owner)

    def _node(self, kind: str, role: str, node, **kw) -> str:
        return self.f.node(kind, role, f"{node.type}@{node.start_byte}",
                           start_byte=node.start_byte,
                           end_byte=node.end_byte, **kw)

    def build(self, func_node):
        entry = self.f.node("entry", "entry", "entry")
        exit_id = self.f.node("exit", "exit", "exit")
        body = func_node.child_by_field_name("body")
        if body is None:
            self.f.edge(entry, exit_id, "next")
            return self.f.nodes, self.f.edges
        first, ends = self._block(body)
        if first:
            self.f.edge(entry, first, "next")
            for end in ends:
                self.f.edge(end, exit_id, "next")
        else:
            self.f.edge(entry, exit_id, "next")
        for ret in self.f.returns:
            self.f.edge(ret, exit_id, "return")
        return self.f.nodes, self.f.edges

    def _block(self, node):
        return self._seq(node.named_children)

    def _seq(self, stmts):
        first = None
        pending: list[str] = []
        for stmt in stmts:
            entry, ends = self._stmt(stmt)
            if entry is None:
                continue
            if first is None:
                first = entry
            for end in pending:
                self.f.edge(end, entry, "next")
            pending = ends
        return first, pending

    def _stmt(self, node):
        k = node.type
        if k == "if_statement":
            return self._if(node)
        if k in ("for_statement", "enhanced_for_statement", "while_statement"):
            return self._loop(node)
        if k == "do_statement":
            return self._do_while(node)
        if k == "return_statement":
            nid = self._node("return", "return", node)
            self.f.returns.append(nid)
            return nid, []
        if k == "break_statement":
            nid = self._node("break", "break", node)
            if self.f.loop_stack:
                self.f.loop_stack[-1].breaks.append(nid)
            return nid, []
        if k == "continue_statement":
            nid = self._node("continue", "continue", node)
            if self.f.loop_stack:
                self.f.loop_stack[-1].continues.append(nid)
            return nid, []
        if k == "expression_statement" and node.named_children:
            inner = node.named_children[0]
            if inner.type == "method_invocation":
                nid = self._node("callsite", "callsite", node)
                return nid, [nid]
        nid = self._node("statement", "statement", node)
        return nid, [nid]

    def _if(self, node):
        cond = node.child_by_field_name("condition")
        cid = self._node("condition", "if_condition", cond)
        merge = self._node("merge", "branch_merge", node)
        t_entry, t_ends = self._block_or_stmt(node.child_by_field_name("consequence"))
        e_entry, e_ends = None, []
        for clause in node.named_children:
            if clause.type == "else_clause":
                block = next((c for c in clause.named_children
                              if c.type in ("block", "if_statement")), None)
                if block:
                    if block.type == "if_statement":
                        e_entry, e_ends = self._if(block)
                    else:
                        e_entry, e_ends = self._block(block)
                break
        self.f.edge(cid, t_entry or merge, "true")
        self.f.edge(cid, e_entry or merge, "false")
        for end in t_ends:
            self.f.edge(end, merge, "next")
        for end in e_ends:
            self.f.edge(end, merge, "next")
        return cid, [merge]

    def _loop(self, node):
        header = self._node("condition", "loop_header", node)
        exit_m = self._node("merge", "loop_exit", node)
        frame = _LoopFrame(header)
        self.f.loop_stack.append(frame)
        body = node.child_by_field_name("body")
        b_entry, b_ends = (self._block_or_stmt(body) if body else (None, []))
        self.f.loop_stack.pop()
        self.f.edge(header, b_entry or exit_m, "true")
        self.f.edge(header, exit_m, "false")
        for end in b_ends:
            self.f.edge(end, header, "back")
        for br in frame.breaks:
            self.f.edge(br, exit_m, "break")
        for cont in frame.continues:
            self.f.edge(cont, header, "continue")
        return header, [exit_m]

    def _do_while(self, node):
        body = node.child_by_field_name("body")
        cond = node.child_by_field_name("condition")
        header = self._node("condition", "do_while_header", node)
        exit_m = self._node("merge", "do_while_exit", node)
        frame = _LoopFrame(header)
        self.f.loop_stack.append(frame)
        b_entry, b_ends = (self._block_or_stmt(body) if body else (None, []))
        self.f.loop_stack.pop()
        # do-while is body-first: the first iteration reaches the body without
        # passing the condition; the header only gates later iterations.
        if b_entry is not None:
            for end in b_ends:
                self.f.edge(end, header, "next")
            self.f.edge(header, b_entry, "true")
        else:
            self.f.edge(header, exit_m, "true")
        self.f.edge(header, exit_m, "false")
        for br in frame.breaks:
            self.f.edge(br, exit_m, "break")
        for cont in frame.continues:
            self.f.edge(cont, header, "continue")
        return (b_entry or header), [exit_m]

    def _block_or_stmt(self, node):
        if node is None:
            return None, []
        if node.type == "block":
            return self._block(node)
        return self._stmt(node)

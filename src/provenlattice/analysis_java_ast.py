"""Java AST V1 materializer over the derived-analysis store."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path, PurePosixPath

from .analysis import (
    ANALYZER_VERSIONS,
    AnalysisNode,
    AnalysisStore,
    PayloadTooLargeError,
    analyzer_contract,
    analyzer_id,
)
from .identity import path_id
from .parsing.java import JavaTreeSitterParser
from .scanner import scan_repository
from .storage import SQLiteStorage

ANALYZER = analyzer_id("ast", "java")
JAVA_AST_VERSION = ANALYZER_VERSIONS[ANALYZER]
JAVA_AST_CONTRACT = analyzer_contract("ast", "java", JAVA_AST_VERSION)
AST_UNIT = "file"
BASE_SYMBOL_KINDS = frozenset({"Class", "Interface", "Method"})
ALIGNABLE_KINDS = {
    "class_declaration": frozenset({"Class"}),
    "interface_declaration": frozenset({"Interface"}),
    "enum_declaration": frozenset({"Class"}),
    "record_declaration": frozenset({"Class"}),
    "annotation_type_declaration": frozenset({"Interface"}),
    "method_declaration": frozenset({"Method"}),
    "constructor_declaration": frozenset({"Method"}),
    "compact_constructor_declaration": frozenset({"Method"}),
}


def ast_node_id(file_id: str, structural_path: str) -> str:
    canonical = "\x1f".join((file_id, AST_UNIT, structural_path))
    return f"jnode:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def normalize_scope(scope: str) -> PurePosixPath:
    raw = scope.replace("\\", "/")
    if raw.startswith("/"):
        raise ValueError(f"scope must be repo-relative: {scope}")
    normalized = raw.strip("/")
    if not normalized or normalized == ".":
        raise ValueError("scope must be a repo-relative directory")
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        raise ValueError(f"scope must stay inside the repository: {scope}")
    return PurePosixPath(normalized)


def scoped_sources(root: Path, scope_path: PurePosixPath) -> list:
    return [
        s for s in scan_repository(root)
        if PurePosixPath(s.relative_path).parts[:len(scope_path.parts)] == scope_path.parts
    ]


def analyze_ast_scope(repo: str | Path, scope: str, database: str | Path | None = None) -> dict:
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
    skipped_payload_too_large: list[str] = []
    nodes_written = 0
    with SQLiteStorage(database) as storage:
        repo_row = storage.repository()
        if not repo_row:
            raise RuntimeError("repository is not indexed; run `provenlattice index` first")
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
            state = store.get_analysis_state(file_id, ANALYZER)
            if (
                state is not None
                and state.get("metadata", {}).get("contract") == JAVA_AST_CONTRACT
                and state.get("metadata", {}).get("analyzer") == ANALYZER
                and store.is_analysis_fresh(file_id, ANALYZER, base_hash, JAVA_AST_VERSION)
            ):
                reused.append(source.relative_path)
                continue
            try:
                nodes = _materialize(store, file_id, source)
                store.replace_analysis_for_file(
                    file_id, ANALYZER, base_hash, JAVA_AST_VERSION, nodes, [],
                    metadata={
                        "analyzer": ANALYZER, "contract": JAVA_AST_CONTRACT,
                        "language": "java", "scope": scope_path.as_posix(),
                        "node_count": len(nodes),
                    },
                )
            except PayloadTooLargeError:
                skipped_payload_too_large.append(source.relative_path)
                continue
            materialized.append(source.relative_path)
            nodes_written += len(nodes)
    return {
        "repo_id": repo_id, "database": str(database),
        "scope": scope_path.as_posix(), "analyzer": ANALYZER,
        "contract": JAVA_AST_CONTRACT, "feature_version": JAVA_AST_VERSION,
        "scope_source_files": len(scoped), "materialized": sorted(materialized),
        "reused": sorted(reused), "skipped_unsupported": sorted(skipped_unsupported),
        "skipped_not_in_base": sorted(skipped_not_in_base),
        "skipped_base_out_of_date": sorted(skipped_base_out_of_date),
        "skipped_payload_too_large": sorted(skipped_payload_too_large),
        "nodes_written": nodes_written,
        "analyze_time_ms": (time.perf_counter() - started) * 1000,
    }


def _symbol_spans(store: AnalysisStore, file_id: str) -> dict:
    spans: dict[tuple[int, int], list[dict]] = {}
    for row in store.storage.rows(
        "SELECT id, kind, start_line, end_line FROM nodes WHERE file_id=?", (file_id,)
    ):
        if row["kind"] in BASE_SYMBOL_KINDS and row["start_line"] is not None:
            spans.setdefault((row["start_line"], row["end_line"]), []).append(
                {"id": row["id"], "kind": row["kind"]}
            )
    return spans


def _materialize(store: AnalysisStore, file_id: str, source) -> list[AnalysisNode]:
    parser = JavaTreeSitterParser()
    outcome = parser.parse_bytes(source.path.read_bytes(), source.relative_path)
    root = outcome.tree.root_node
    spans = _symbol_spans(store, file_id)
    nodes: list[AnalysisNode] = []
    stack: list[tuple] = [(root, None, root.type)]
    while stack:
        node, parent_id, path = stack.pop()
        node_id = ast_node_id(file_id, path)
        owner_symbol_id, alignment = None, "unmatched"
        expected = ALIGNABLE_KINDS.get(node.type)
        if expected is not None:
            key = (node.start_point[0] + 1, node.end_point[0] + 1)
            cands = [c for c in spans.get(key, []) if c["kind"] in expected]
            if len(cands) == 1:
                owner_symbol_id, alignment = cands[0]["id"], "resolved"
        nodes.append(AnalysisNode(
            node_id, node.type,
            {"parent_id": parent_id, "structural_path": path,
             "start_byte": node.start_byte, "end_byte": node.end_byte,
             "start_row": node.start_point[0], "start_col": node.start_point[1],
             "end_row": node.end_point[0], "end_col": node.end_point[1],
             "owner_symbol_id": owner_symbol_id, "alignment": alignment},
        ))
        children = node.named_children
        for i in range(len(children) - 1, -1, -1):
            child = children[i]
            stack.append((child, node_id, f"{path}/{child.type}[{i}]"))
    return nodes

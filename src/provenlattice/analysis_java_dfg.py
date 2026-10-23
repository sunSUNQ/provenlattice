"""Java Sparse DFG materializer (I1-C-Java) over the derived-analysis store.

Reuses ``sparsedfg.mint_dataflow_edges`` unchanged: the Java walker in
``analysis_java_scfg`` produces the points + annotations, and this module mints
DATA_FLOW_TO edges for method-local def->use of Java local variables.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

from .analysis import (
    ANALYZER_VERSIONS,
    AnalysisEdge,
    AnalysisStore,
    PayloadTooLargeError,
    analyzer_contract,
    analyzer_id,
)
from .analysis_ast import normalize_scope, scoped_sources
from .analysis_java_scfg import (
    JAVA_SUFFIXES,
    SCFG_CONTRACT,
    JavaSparseCfgBuilder,
    java_owner_index,
)
from .analysis_semantic_common import _LineIndex, tree_diagnostics
from .identity import event_id, path_id
from .models import PointKey
from .parsing.java import JavaTreeSitterParser
from .semantics.events import ACCESS_EVENTS
from .sparsedfg import CONSUMES, DATA_FLOW_TO, mint_dataflow_edges
from .storage import SQLiteStorage

ANALYZER = analyzer_id("sparse_dfg", "java")
DFG_VERSION = ANALYZER_VERSIONS[ANALYZER]
DFG_CONTRACT = analyzer_contract("sparse_dfg", "java", DFG_VERSION)
CAPABILITY_LEVEL = "level0+structural+access+dfg"
CAPABILITY_GRADE = "local-only, diagnostic"


def analyze_java_dfg_scope(repo, scope: str, database=None) -> dict:
    started = time.perf_counter()
    root = Path(repo).resolve()
    scope_path = normalize_scope(scope)
    database = Path(database).resolve() if database else root / ".provenlattice" / "codegraph.db"
    scoped = scoped_sources(root, scope_path)
    materialized, reused = [], []
    skipped_unsupported, skipped_not_in_base, skipped_base_out_of_date = [], [], []
    skipped_no_edges, skipped_payload_too_large = [], []
    counters = {"dfg_edges": 0, "data_flow_to": 0, "consumes": 0,
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
                    and state.get("metadata", {}).get("contract") == DFG_CONTRACT
                    and store.is_analysis_fresh(file_id, ANALYZER, base_hash, DFG_VERSION)):
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

            id_by_key: dict[PointKey, str] = {}
            for point in cfg.points:
                owner = _owner_of(owner_ids, point)
                id_by_key[point.key()] = event_id(repo_id, owner, point.event_type, point.ordinal)

            parsed_view = SimpleNamespace(events=[], cfg=cfg)
            semantic_edges = mint_dataflow_edges(
                repo_id, parsed_view, id_by_key, file_id,
                relative_path=source.relative_path, shard_path="")

            event_type_by_id = {nid: key.event_type for key, nid in id_by_key.items()}
            edges = []
            for edge in semantic_edges:
                payload = dict(edge.metadata)
                if payload.get("control_reachable") == "false":
                    src_type = event_type_by_id.get(edge.src_event_id)
                    dst_type = event_type_by_id.get(edge.dst_event_id)
                    if diagnostics["partial"]:
                        payload["control_reachable"] = "unknown"
                        payload["control_reachable_note"] = "partial parse"
                    elif src_type in ACCESS_EVENTS or dst_type in ACCESS_EVENTS:
                        payload["control_reachable"] = "unknown"
                        payload["control_reachable_note"] = "edgeless access point"
                edges.append(AnalysisEdge(edge.edge_id, edge.src_event_id, edge.dst_event_id,
                                          edge.relation, payload))

            try:
                store.replace_analysis_for_file(
                    file_id, ANALYZER, base_hash, DFG_VERSION, [], edges,
                    metadata={"analyzer": ANALYZER, "contract": DFG_CONTRACT,
                              "language": "java", "level": CAPABILITY_LEVEL,
                              "grade": CAPABILITY_GRADE, "scope": scope_path.as_posix(),
                              "edge_count": len(edges),
                              "data_flow_to": sum(1 for e in edges if e.kind == DATA_FLOW_TO),
                              "consumes": sum(1 for e in edges if e.kind == CONSUMES),
                              "dependencies": {"sparse_cfg:java": SCFG_CONTRACT},
                              **owner_counters, **diagnostics,
                              "analysis_status": "degraded" if diagnostics["partial"] else "complete"},
                )
            except PayloadTooLargeError:
                skipped_payload_too_large.append(source.relative_path)
                continue
            if not edges:
                skipped_no_edges.append(source.relative_path)
            materialized.append(source.relative_path)
            counters["dfg_edges"] += len(edges)
            counters["data_flow_to"] += sum(1 for e in edges if e.kind == DATA_FLOW_TO)
            counters["consumes"] += sum(1 for e in edges if e.kind == CONSUMES)
            counters["functions_bound"] += owner_counters["functions_bound"]
            counters["functions_unbound"] += owner_counters["functions_unbound"]
    return {
        "repo_id": repo_id, "database": str(database), "scope": scope_path.as_posix(),
        "analyzer": ANALYZER, "contract": DFG_CONTRACT, "feature_version": DFG_VERSION,
        "level": CAPABILITY_LEVEL, "grade": CAPABILITY_GRADE,
        "scope_source_files": len(scoped),
        "materialized": sorted(materialized), "reused": sorted(reused),
        "skipped_unsupported": sorted(skipped_unsupported),
        "skipped_not_in_base": sorted(skipped_not_in_base),
        "skipped_base_out_of_date": sorted(skipped_base_out_of_date),
        "skipped_no_edges": sorted(skipped_no_edges),
        "skipped_payload_too_large": sorted(skipped_payload_too_large),
        "dfg_edges": counters["dfg_edges"],
        "data_flow_to": counters["data_flow_to"],
        "consumes": counters["consumes"],
        "functions_bound": counters["functions_bound"],
        "functions_unbound": counters["functions_unbound"],
        "analyze_time_ms": (time.perf_counter() - started) * 1000,
    }


def _owner_of(owner_ids: dict, point) -> str:
    identity = (point.owner_kind, point.owner_qualified_name, point.owner_signature)
    if identity not in owner_ids or owner_ids[identity] is None:
        raise RuntimeError(f"sparse dfg point owner unresolvable: {identity}")
    return owner_ids[identity]

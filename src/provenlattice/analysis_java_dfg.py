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
    ARGUMENT_SEPARATOR,
    JAVA_SUFFIXES,
    SCFG_CONTRACT,
    JavaSparseCfgBuilder,
    java_owner_index,
)
from .analysis_semantic_common import _LineIndex, tree_diagnostics
from .identity import event_id, path_id, semantic_edge_id
from .models import PointKey
from .parsing.java import JavaTreeSitterParser
from .semantics.events import ACCESS_EVENTS, SemanticEdge
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
            interprocedural_edges = _mint_interprocedural_edges(
                repo_id, cfg, owner_ids, id_by_key, semantic_edges, file_id,
                source.relative_path)

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
            for edge in interprocedural_edges:
                edges.append(AnalysisEdge(edge.edge_id, edge.src_event_id, edge.dst_event_id,
                                          edge.relation, dict(edge.metadata)))

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


INTERPROC_PARAMETER = "interprocedural_parameter"
INTERPROC_RETURN = "interprocedural_return"


def _mint_interprocedural_edges(
    repo_id: str,
    cfg,
    owner_ids: dict,
    id_by_key: dict,
    method_edges: list[SemanticEdge],
    file_id: str,
    relative_path: str,
) -> list[SemanticEdge]:
    """Mint cross-method DATA_FLOW_TO edges across the caller<->callee interface.

    Reuses the method-local DFG facts unchanged: the input_to_sink edges already
    name each call's argument definition (caller side), and the value_flow edges
    already name each return value's definition (callee side). This pass only
    joins those two facts through the callee's parameter/return rows, minting:

      * ``interprocedural_parameter``: caller argument def -> callee parameter WRITE;
      * ``interprocedural_return``:   callee return-value def -> caller CALL point.

    Callee resolution is same-file short-name only: a short name that maps to
    exactly one method binds; anything else (overload / unbound / cross-file)
    stays unbound rather than guessed, matching the method-local discipline.
    """
    annotations = cfg.annotations
    params_by_owner: dict[str, list[str]] = {}
    returns_by_owner: dict[str, list[str]] = {}
    owners_by_short: dict[str, set[str]] = {}
    calls: list[tuple[str, str, str, str]] = []

    for point in cfg.points:
        triple = (point.owner_kind, point.owner_qualified_name, point.owner_signature)
        owner_id = owner_ids.get(triple)
        if owner_id is None:
            continue
        info = annotations.get(point.key(), {})
        point_id = id_by_key[point.key()]
        short = point.owner_qualified_name.rsplit(".", 1)[-1]
        if point.event_type == "WRITE" and info.get("subject_storage") == "parameter":
            params_by_owner.setdefault(owner_id, []).append(point_id)
            owners_by_short.setdefault(short, set()).add(owner_id)
        elif point.event_type == "RETURN":
            returns_by_owner.setdefault(owner_id, []).append(point_id)
            owners_by_short.setdefault(short, set()).add(owner_id)
        elif point.event_type == "CALL":
            calls.append((owner_id, info.get("callee", ""), info.get("arguments", ""), point_id))

    if not calls:
        return []

    call_event_ids = {call[3] for call in calls}
    return_event_ids = {eid for eids in returns_by_owner.values() for eid in eids}
    arg_def_by_call: dict[tuple[str, str], str] = {}
    return_def_by_return: dict[str, str] = {}
    for edge in method_edges:
        if edge.relation != DATA_FLOW_TO:
            continue
        flow_class = edge.metadata.get("flow_class", "")
        if flow_class == "input_to_sink" and edge.dst_event_id in call_event_ids:
            arg_def_by_call[(edge.dst_event_id, edge.metadata.get("arg_root", ""))] = edge.src_event_id
        if edge.dst_event_id in return_event_ids:
            return_def_by_return[edge.dst_event_id] = edge.src_event_id

    edges: dict[str, SemanticEdge] = {}

    def mint(src_id: str, dst_id: str, flow_class: str, caller_id: str, callee_short: str) -> None:
        edge = SemanticEdge(
            edge_id=semantic_edge_id(src_id, dst_id, DATA_FLOW_TO, ""),
            src_event_id=src_id,
            dst_event_id=dst_id,
            relation=DATA_FLOW_TO,
            owner_symbol_id=caller_id,
            file_id=file_id,
            flags=(),
            metadata={
                "relative_path": relative_path,
                "shard_path": "",
                "flow_class": flow_class,
                "via": [], "via_copies": [],
                "control_reachable": "true",
                "callee": callee_short,
            },
        )
        edges.setdefault(edge.edge_id, edge)

    for caller_id, callee_short, args_str, call_eid in calls:
        if not callee_short:
            continue
        callee_set = owners_by_short.get(callee_short, set())
        if len(callee_set) != 1:
            continue
        callee_id = next(iter(callee_set))
        callee_params = params_by_owner.get(callee_id, [])
        roots = args_str.split(ARGUMENT_SEPARATOR) if args_str else []
        for index, root in enumerate(roots):
            if not root:
                continue
            if index >= len(callee_params):
                continue
            src = arg_def_by_call.get((call_eid, root))
            if src is None:
                continue
            mint(src, callee_params[index], INTERPROC_PARAMETER, caller_id, callee_short)
        for ret_eid in returns_by_owner.get(callee_id, []):
            src = return_def_by_return.get(ret_eid)
            if src is None:
                continue
            mint(src, call_eid, INTERPROC_RETURN, caller_id, callee_short)

    return [edges[eid] for eid in sorted(edges)]

"""Level-0 semantic event materializer (I1-A) over the derived-analysis store.

Ported from PR #1's semantic layer, re-shaped for main's architecture:

* Events are extracted **on demand only** -- the default index never runs the
  extractor. The analyzer follows the same shape as the C CFG analyzer:
  scope-driven, file x analyzer cached in AnalysisStore, fail-closed
  freshness.
* Owner binding reuses main's L1 symbol identity: every tree-sitter
  ``function_definition`` span is aligned against the base graph's
  Function/Method symbols (same-line collisions disambiguated by the
  definition flag, then by name -- the I0R1 rule); the helpers are shared
  with the sparse_cfg analyzer (analysis_semantic_common).
* Level scope: vocabulary events only (CALL/RETURN/THROW/ALLOC/RELEASE/
  LOCK/UNLOCK/ATOMIC/THREAD_SPAWN/THREAD_JOIN). The structural
  CHECK/BRANCH/DEREFERENCE and READ/WRITE access events are sparse-CFG-walker
  products and live in the sparse_cfg analyzer (I1-B). The capability is
  therefore registered as ``partially_implemented`` (level 0), never as fully
  implemented.
* One analyzer covers the whole C/C++ family: the vocabulary table
  (``semantics/vocabularies/cpp.toml``) names the extensions, and the parse
  uses the C++ grammar for every covered file, matching the PR extraction the
  vocabulary was written against.
"""

from __future__ import annotations

import time
from pathlib import Path

from .analysis import (
    ANALYZER_VERSIONS,
    AnalysisNode,
    AnalysisStore,
    PayloadTooLargeError,
    analyzer_contract,
    analyzer_id,
)
from .analysis_ast import normalize_scope, scoped_sources
from .analysis_semantic_common import (
    _LineIndex,
    owner_index,
    owner_symbol_id,
    tree_diagnostics,
)
from .identity import event_id, path_id
from .parsing.cpp import CppTreeSitterParser
from .parsing.events import EventExtractor
from .semantics.vocabulary import load_vocabulary
from .storage import SQLiteStorage

ANALYZER = analyzer_id("events", "cpp")
EVENTS_VERSION = ANALYZER_VERSIONS[ANALYZER]
EVENTS_CONTRACT = analyzer_contract("events", "cpp", EVENTS_VERSION)
VOCABULARY = load_vocabulary("cpp")
EVENTS_SUFFIXES = frozenset(VOCABULARY.extensions)
CAPABILITY_LEVEL = "level0"


def analyze_c_events_scope(
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
    skipped_no_events: list[str] = []
    skipped_payload_too_large: list[str] = []
    counters = {
        "events_extracted": 0, "events_outside_owner": 0,
        "functions_bound": 0, "functions_unbound": 0,
    }
    nodes_written = 0
    parser = CppTreeSitterParser(language="cpp")
    with SQLiteStorage(database) as storage:
        repository = storage.repository()
        if not repository:
            raise RuntimeError("repository is not indexed; run `provenlattice index` first")
        repo_id = repository["repo_id"]
        store = AnalysisStore(storage)
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
                and state.get("metadata", {}).get("contract") == EVENTS_CONTRACT
                and state.get("metadata", {}).get("analyzer") == ANALYZER
                and store.is_analysis_fresh(file_id, ANALYZER, base_hash, EVENTS_VERSION)
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
            nodes = [
                AnalysisNode(
                    event_id(
                        repo_id,
                        owner_symbol_id(owner_ids, hit.event),
                        hit.event.event_type,
                        hit.event.ordinal,
                    ),
                    hit.event.event_type,
                    {
                        "owner_symbol_id": owner_symbol_id(owner_ids, hit.event),
                        "owner_kind": hit.event.owner_kind,
                        "owner_qualified_name": hit.event.owner_qualified_name,
                        "owner_signature": hit.event.owner_signature,
                        "ordinal": hit.event.ordinal,
                        "start_byte": hit.start_byte, "end_byte": hit.end_byte,
                        "start_line": hit.event.start_line,
                        "end_line": hit.event.end_line,
                        "matched_name": hit.event.matched_name,
                        "matched_via": hit.event.matched_via,
                        "flags": list(hit.event.flags),
                        "analyzer": ANALYZER, "contract": EVENTS_CONTRACT,
                        "language": VOCABULARY.language, "level": CAPABILITY_LEVEL,
                    },
                )
                for hit in hits
            ]
            diagnostics = tree_diagnostics(outcome.tree.root_node)
            try:
                store.replace_analysis_for_file(
                    file_id, ANALYZER, base_hash, EVENTS_VERSION, nodes, [],
                    metadata={
                        "analyzer": ANALYZER, "contract": EVENTS_CONTRACT,
                        "language": VOCABULARY.language, "level": CAPABILITY_LEVEL,
                        "scope": scope_path.as_posix(),
                        "event_count": len(nodes),
                        "events_outside_owner": extractor.skipped_outside_owner,
                        **owner_counters,
                        **diagnostics,
                        "analysis_status": "degraded" if diagnostics["partial"] else "complete",
                    },
                )
            except PayloadTooLargeError:
                skipped_payload_too_large.append(source.relative_path)
                continue
            if not nodes:
                # A file with zero level-0 events is a legitimate outcome, and
                # the empty state is persisted so the freshness contract (not
                # repeated extraction) answers repeat requests.
                skipped_no_events.append(source.relative_path)
            materialized.append(source.relative_path)
            counters["events_extracted"] += len(nodes)
            counters["events_outside_owner"] += extractor.skipped_outside_owner
            counters["functions_bound"] += owner_counters["functions_bound"]
            counters["functions_unbound"] += owner_counters["functions_unbound"]
            nodes_written += len(nodes)
    return {
        "repo_id": repo_id,
        "database": str(database),
        "scope": scope_path.as_posix(),
        "analyzer": ANALYZER,
        "contract": EVENTS_CONTRACT,
        "feature_version": EVENTS_VERSION,
        "level": CAPABILITY_LEVEL,
        "scope_source_files": len(scoped),
        "materialized": sorted(materialized),
        "reused": sorted(reused),
        "skipped_unsupported": sorted(skipped_unsupported),
        "skipped_not_in_base": sorted(skipped_not_in_base),
        "skipped_base_out_of_date": sorted(skipped_base_out_of_date),
        "skipped_no_events": sorted(skipped_no_events),
        "skipped_payload_too_large": sorted(skipped_payload_too_large),
        "events_extracted": counters["events_extracted"],
        "events_outside_owner": counters["events_outside_owner"],
        "functions_bound": counters["functions_bound"],
        "functions_unbound": counters["functions_unbound"],
        "nodes_written": nodes_written,
        "analyze_time_ms": (time.perf_counter() - started) * 1000,
    }

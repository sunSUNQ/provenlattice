from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Node:
    id: str
    kind: str
    repo_id: str
    shard_id: str | None
    file_id: str | None
    name: str
    qualified_name: str
    language: str | None
    start_line: int | None
    end_line: int | None
    signature: str | None
    source_hash: str | None
    generation: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Edge:
    id: str
    src_id: str
    dst_id: str
    type: str
    provenance: str = "static_analysis"
    confidence: float = 1.0
    generation: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Shard:
    shard_id: str
    repo_id: str
    path: str
    nodes_count: int
    edges_count: int
    public_symbols: list[str]
    api_fingerprint: str
    generation: int
    boundary_dirty: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Delta:
    nodes_added: int = 0
    nodes_removed: int = 0
    nodes_updated: int = 0
    edges_added: int = 0
    edges_removed: int = 0
    old_api_fingerprint: dict[str, str] = field(default_factory=dict)
    new_api_fingerprint: dict[str, str] = field(default_factory=dict)
    boundary_dirty: list[str] = field(default_factory=list)
    shards_updated: list[str] = field(default_factory=list)
    references_reprocessed: int = 0
    references_reused: int = 0
    directly_affected_shards: list[str] = field(default_factory=list)
    affected_boundary_edges: list[str] = field(default_factory=list)
    impact_frontier_size: int = 0
    wide_impact: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Metrics:
    files_scanned: int = 0
    files_parsed: int = 0
    parse_failures: int = 0
    syntax_error_files: int = 0
    nodes_created: int = 0
    edges_created: int = 0
    raw_references: int = 0
    resolved_references: int = 0
    ambiguous_references: int = 0
    unresolved_references: int = 0
    shards_created: int = 0
    boundary_edges: int = 0
    files_reparsed: int = 0
    files_reused: int = 0
    references_reprocessed: int = 0
    references_reused: int = 0
    shards_updated: int = 0
    shards_reused: int = 0
    boundary_edges_reprocessed: int = 0
    boundary_edges_reused: int = 0
    impact_frontier_size: int = 0
    wide_impact: bool = False
    index_time_ms: float = 0.0
    query_time_ms: float = 0.0
    incremental_time_ms: float = 0.0
    changed_files: int = 0
    affected_nodes: int = 0
    affected_edges: int = 0
    database_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ParsedSymbol:
    kind: str
    name: str
    qualified_name: str
    start_line: int
    end_line: int
    signature: str
    public: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedReference:
    source_qualified_name: str
    type: str
    target: str
    target_module: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    start_line: int | None = None
    end_line: int | None = None


@dataclass(slots=True)
class ParsedImport:
    source_qualified_name: str
    target: str
    module: str
    alias: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedFile:
    symbols: list[ParsedSymbol]
    references: list[ParsedReference]
    imports: list[ParsedImport]
    parser: str = "tree-sitter"


@dataclass(slots=True)
class RawReference:
    id: str
    repo_id: str
    file_id: str
    owner_symbol_id: str
    raw_name: str
    reference_type: str
    target_module: str | None
    start_line: int | None
    end_line: int | None
    status: str
    candidate_symbols: list[str]
    resolved_symbol_id: str | None
    resolution_strategy: str
    provenance: str
    confidence: float
    generation: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OverlayMetadata:
    overlay_id: str
    overlay_type: str
    repository_id: str
    base_commit: str
    base_generation: int
    branch_name: str | None
    parent_overlay_id: str | None
    status: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OverlayDelta:
    overlay_id: str
    entity_type: str
    entity_id: str
    operation: str
    base_version: str | None
    new_value: dict[str, Any] | None
    generation: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OverlayConflict:
    conflict_type: str
    entity_type: str | None = None
    entity_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RawEvidenceLink:
    id: str
    repository_id: str
    source_node_id: str
    raw_anchor: str
    anchor_type: str
    candidate_targets: list[str]
    resolved_target_id: str | None
    resolution_status: str
    resolution_strategy: str
    provenance: str
    confidence: float
    generation: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Compatibility names for the initial V0 public surface.
SymbolDraft = ParsedSymbol
RelationDraft = ParsedReference

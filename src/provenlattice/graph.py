from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from .identity import edge_id, path_id, repository_id, symbol_id
from .models import Edge, Metrics, Node, ParsedFile, ParsedImport, ParsedReference, ParsedSymbol
from .parser import parse_file_with_diagnostics
from .resolver import ReferenceResolver
from .scanner import SourceFile, scan_repository
from .shard import DirectoryShardStrategy, ShardStrategy, assign_shard, build_shards
from .storage import SQLiteStorage


def parsed_to_dict(parsed: ParsedFile) -> dict:
    return {
        "symbols": [asdict(item) for item in parsed.symbols],
        "references": [asdict(item) for item in parsed.references],
        "imports": [asdict(item) for item in parsed.imports],
        "parser": parsed.parser,
    }


def parsed_from_dict(data: dict) -> ParsedFile:
    references = data.get("references")
    imports = data.get("imports")
    if references is None:  # Read caches written by the first V0 prototype.
        references, imports = [], []
        for item in data.get("relations", []):
            if item.get("type") == "IMPORTS":
                imports.append(
                    {
                        "source_qualified_name": item["source_qualified_name"],
                        "target": item["target"],
                        "module": item.get("target_module") or item["target"],
                    }
                )
            else:
                references.append(item)
    return ParsedFile(
        symbols=[ParsedSymbol(**item) for item in data.get("symbols", [])],
        references=[ParsedReference(**item) for item in references],
        imports=[ParsedImport(**item) for item in imports],
        parser=data.get("parser", "legacy-ast"),
    )


def _module_name(relative_path: str) -> str:
    parts = list(PurePosixPath(relative_path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def build_graph(
    root: Path,
    sources: list[SourceFile],
    parsed_files: dict[str, ParsedFile],
    generation: int,
    *,
    strategy: ShardStrategy | None = None,
    old_fingerprints: dict[str, str] | None = None,
    cached_references: dict[str, dict] | None = None,
    changed_file_ids: set[str] | None = None,
    affected_reference_ids: set[str] | None = None,
) -> tuple[str, list[dict], list[Node], list[Edge], list, object]:
    root = root.resolve()
    repo_id = repository_id(root)
    strategy = strategy or DirectoryShardStrategy()
    prepare = getattr(strategy, "prepare", None)
    if prepare is not None:
        prepare(root, sources, parsed_files)
    nodes: list[Node] = []
    edges: list[Edge] = []
    file_records: list[dict] = []

    repo_node_id = path_id(repo_id, "Repository", ".")
    nodes.append(
        Node(repo_node_id, "Repository", repo_id, None, None, root.name, root.name,
             None, None, None, None, None, generation, {"root_path": str(root)})
    )
    directory_nodes: dict[str, Node] = {}
    file_nodes: dict[str, Node] = {}
    symbol_nodes_by_id: dict[str, Node] = {}

    for source in sources:
        parsed = parsed_files[source.relative_path]
        sid, shard_path = assign_shard(repo_id, source.relative_path, strategy)
        file_id = path_id(repo_id, "File", source.relative_path)
        file_records.append(
            {"file_id": file_id, "shard_id": sid, "path": source.relative_path,
             "language": source.language, "source_hash": source.source_hash}
        )
        parent_id = repo_node_id
        accumulated: list[str] = []
        for part in PurePosixPath(source.relative_path).parts[:-1]:
            accumulated.append(part)
            directory_path = "/".join(accumulated)
            directory = directory_nodes.get(directory_path)
            if directory is None:
                directory = Node(
                    path_id(repo_id, "Directory", directory_path), "Directory", repo_id,
                    sid, None, part, directory_path, None, None, None, None, None,
                    generation, {"relative_path": directory_path, "shard_path": shard_path},
                )
                directory_nodes[directory_path] = directory
                edges.append(
                    Edge(
                        edge_id(parent_id, directory.id, "CONTAINS"), parent_id, directory.id,
                        "CONTAINS", provenance="filesystem_scan", generation=generation,
                    )
                )
            parent_id = directory.id
        module = _module_name(source.relative_path)
        file_node = Node(
            file_id, "File", repo_id, sid, file_id, PurePosixPath(source.relative_path).name,
            module, source.language, 1, None, None, source.source_hash, generation,
            {"relative_path": source.relative_path, "shard_path": shard_path,
             "parsed": parsed_to_dict(parsed)},
        )
        file_nodes[source.relative_path] = file_node
        edges.append(
            Edge(
                edge_id(parent_id, file_id, "CONTAINS"), parent_id, file_id, "CONTAINS",
                provenance="filesystem_scan", generation=generation,
            )
        )
        for draft in parsed.symbols:
            node = Node(
                symbol_id(repo_id, source.relative_path, draft.kind, draft.qualified_name, draft.signature),
                draft.kind, repo_id, sid, file_id, draft.name, draft.qualified_name,
                source.language, draft.start_line, draft.end_line, draft.signature,
                source.source_hash, generation,
                {**draft.metadata, "public": draft.public, "relative_path": source.relative_path,
                 "shard_path": shard_path},
            )
            existing = symbol_nodes_by_id.get(node.id)
            if existing is not None:
                sites = existing.metadata.setdefault("duplicate_sites", [])
                sites.append({"start_line": node.start_line, "end_line": node.end_line})
                continue
            symbol_nodes_by_id[node.id] = node
            edges.append(
                Edge(
                    edge_id(file_id, node.id, "DEFINES"), file_id, node.id, "DEFINES",
                    provenance="tree_sitter_syntax", generation=generation,
                )
            )

    nodes.extend(directory_nodes.values())
    nodes.extend(file_nodes.values())
    symbol_nodes = list(symbol_nodes_by_id.values())
    nodes.extend(symbol_nodes)
    resolution = ReferenceResolver().resolve(
        parsed_files=parsed_files,
        file_nodes=file_nodes,
        symbol_nodes=symbol_nodes,
        generation=generation,
        cached_references=cached_references,
        changed_file_ids=changed_file_ids,
        affected_reference_ids=affected_reference_ids,
    )
    edges.extend(resolution.edges)

    unique_edges = {edge.id: edge for edge in edges}
    edges = sorted(unique_edges.values(), key=lambda edge: edge.id)
    nodes = sorted(nodes, key=lambda node: node.id)
    shards = build_shards(repo_id, nodes, edges, generation, old_fingerprints)
    return repo_id, file_records, nodes, edges, shards, resolution


def full_index(
    repo: str | Path, database: str | Path | None = None, *, strategy: ShardStrategy | None = None
) -> dict:
    started = time.perf_counter()
    root = Path(repo).resolve()
    database = Path(database).resolve() if database else root / ".provenlattice" / "codegraph.db"
    sources = scan_repository(root)
    parsed_files: dict[str, ParsedFile] = {}
    parse_failures = 0
    syntax_error_files = 0
    for source in sources:
        try:
            parsed, has_error = parse_file_with_diagnostics(
                source.path, source.relative_path, source.language
            )
        except Exception as error:
            parsed = ParsedFile([], [], [], parser=f"failed:{type(error).__name__}")
            has_error = False
            parse_failures += 1
        parsed_files[source.relative_path] = parsed
        syntax_error_files += int(has_error)
    repo_id = repository_id(root)
    with SQLiteStorage(database) as storage:
        generation = storage.current_generation(repo_id) + 1
        repo_id, files, nodes, edges, shards, resolution = build_graph(
            root, sources, parsed_files, generation, strategy=strategy
        )
        status_counts = {status: 0 for status in ("resolved", "ambiguous", "unresolved")}
        for reference in resolution.references:
            status_counts[reference.status] += 1
        metrics = Metrics(
            files_scanned=len(sources), files_parsed=len(sources) - parse_failures,
            parse_failures=parse_failures, syntax_error_files=syntax_error_files,
            nodes_created=len(nodes), edges_created=len(edges),
            raw_references=len(resolution.references),
            resolved_references=status_counts["resolved"],
            ambiguous_references=status_counts["ambiguous"],
            unresolved_references=status_counts["unresolved"],
            shards_created=len(shards),
            boundary_edges=sum(edge.metadata.get("scope") == "boundary" for edge in edges),
        )
        storage.replace_snapshot(
            repo_id=repo_id, root=root, generation=generation, mode="full", files=files,
            nodes=nodes, edges=edges, shards=shards, raw_references=resolution.references,
            metrics=metrics,
        )
        metrics.database_size = storage.database_size
        metrics.index_time_ms = (time.perf_counter() - started) * 1000
        storage.connection.execute(
            "UPDATE graph_generation SET metrics=? WHERE repo_id=? AND generation=?",
            (__import__("json").dumps(metrics.to_dict(), sort_keys=True), repo_id, generation),
        )
        storage.connection.commit()
    return {"repo_id": repo_id, "graph_generation": generation, "metrics": metrics.to_dict(), "database": str(database)}

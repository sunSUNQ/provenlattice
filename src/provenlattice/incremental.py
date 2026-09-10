from __future__ import annotations

import json
import time
from pathlib import Path

from .graph import build_graph, parsed_from_dict
from .identity import path_id, repository_id, symbol_id
from .impact import compute_impact_frontier
from .models import Delta, Metrics, ParsedFile
from .parser import parse_file_with_diagnostics
from .scanner import scan_repository
from .shard import ShardStrategy
from .storage import SQLiteStorage


def incremental_update(
    repo: str | Path, database: str | Path | None = None, *, strategy: ShardStrategy | None = None
) -> dict:
    started = time.perf_counter()
    root = Path(repo).resolve()
    database = Path(database).resolve() if database else root / ".provenlattice" / "codegraph.db"
    repo_id = repository_id(root)
    sources = scan_repository(root)
    source_by_path = {source.relative_path: source for source in sources}
    with SQLiteStorage(database) as storage:
        generation = storage.current_generation(repo_id)
        if generation == 0:
            raise RuntimeError("repository is not indexed; run `provenlattice index` first")
        old_states = storage.file_states(repo_id)
        old_cache = storage.parser_cache(repo_id)
        old_nodes = storage.snapshot_ids("nodes")
        old_edges = storage.snapshot_ids("edges")
        old_fingerprints = storage.shard_fingerprints()
        old_references = storage.raw_reference_cache(repo_id)

        current_paths = set(source_by_path)
        old_paths = set(old_states)
        added = current_paths - old_paths
        deleted = old_paths - current_paths
        modified = {
            path for path in current_paths & old_paths
            if source_by_path[path].source_hash != old_states[path]["source_hash"]
        }
        changed = added | modified | deleted
        if not changed:
            return {
                "repo_id": repo_id,
                "graph_generation": generation,
                "changed": False,
                "delta": Delta().to_dict(),
                "metrics": Metrics(
                    files_scanned=len(sources), files_reused=len(sources),
                    shards_reused=len(storage.shard_fingerprints()), database_size=storage.database_size,
                ).to_dict(),
            }

        parsed_files = {}
        parse_failures = 0
        syntax_error_files = 0
        for path, source in source_by_path.items():
            if path in added or path in modified:
                try:
                    parsed_files[path], has_error = parse_file_with_diagnostics(
                        source.path, path, source.language
                    )
                except Exception as error:
                    parsed_files[path] = ParsedFile(
                        [], [], [], parser=f"failed:{type(error).__name__}"
                    )
                    has_error = False
                    parse_failures += 1
                syntax_error_files += int(has_error)
            else:
                cached = old_cache.get(path)
                if cached is None:
                    raise RuntimeError(f"missing parser cache for unchanged file: {path}")
                parsed_files[path] = parsed_from_dict(cached)

        changed_file_ids = {path_id(repo_id, "File", path) for path in changed}
        old_symbol_facts = {
            node_id: (row["name"], row["qualified_name"])
            for node_id, row in old_nodes.items()
            if row["file_id"] in changed_file_ids
            and row["kind"] in {"File", "Namespace", "Class", "Struct", "Interface", "Function", "Method", "Type"}
        }
        new_symbol_facts: dict[str, tuple[str, str]] = {}
        for path in added | modified:
            file_id = path_id(repo_id, "File", path)
            module_parts = list(Path(path).with_suffix("").parts)
            if module_parts and module_parts[-1] == "__init__":
                module_parts.pop()
            module = ".".join(module_parts)
            new_symbol_facts[file_id] = (Path(path).name, module)
            for draft in parsed_files[path].symbols:
                node_id = symbol_id(
                    repo_id, path, draft.kind, draft.qualified_name, draft.signature
                )
                new_symbol_facts[node_id] = (draft.name, draft.qualified_name)
        changed_symbol_ids = set(old_symbol_facts) ^ set(new_symbol_facts)
        affected_names = {
            value
            for node_id in changed_symbol_ids
            for value in (*old_symbol_facts.get(node_id, ()), *new_symbol_facts.get(node_id, ()))
        }
        affected_reference_ids = storage.references_for_names(affected_names)

        new_generation = generation + 1
        repo_id, files, nodes, edges, shards, resolution = build_graph(
            root, sources, parsed_files, new_generation,
            strategy=strategy,
            old_fingerprints=old_fingerprints,
            cached_references=old_references,
            changed_file_ids=changed_file_ids,
            affected_reference_ids=affected_reference_ids,
        )
        new_nodes = {node.id: node for node in nodes}
        new_edges = {edge.id: edge for edge in edges}
        common_node_ids = set(old_nodes) & set(new_nodes)
        updated_nodes = 0
        for node_id in common_node_ids:
            old = old_nodes[node_id]
            new = new_nodes[node_id]
            if (
                old["source_hash"], old["start_line"], old["end_line"], old["metadata"]
            ) != (
                new.source_hash, new.start_line, new.end_line,
                json.dumps(new.metadata, sort_keys=True),
            ):
                updated_nodes += 1
        new_fingerprints = {shard.shard_id: shard.api_fingerprint for shard in shards}
        dirty = sorted(
            shard.shard_id for shard in shards
            if shard.boundary_dirty
        )
        file_shards = {item["path"]: item["shard_id"] for item in files}
        updated_shards = sorted(
            {file_shards[path] for path in added | modified if path in file_shards}
            | {
                row["shard_id"] for row in old_nodes.values()
                if row["kind"] == "File" and row["file_id"] in changed_file_ids
                and row["shard_id"] is not None
            }
        )
        old_edge_dicts = old_edges
        new_edge_dicts = {edge.id: edge.to_dict() for edge in edges}
        impact = compute_impact_frontier(updated_shards, old_edge_dicts, new_edge_dicts)
        old_boundary_ids = {
            edge_id for edge_id, edge in old_edges.items()
            if '"scope": "boundary"' in edge.get("metadata", "")
            or '"scope":"boundary"' in edge.get("metadata", "")
        }
        new_boundary_ids = {
            edge_id for edge_id, edge in new_edge_dicts.items()
            if edge.get("metadata", {}).get("scope") == "boundary"
        }
        boundary_edges_reprocessed = len(old_boundary_ids ^ new_boundary_ids)
        delta = Delta(
            nodes_added=len(set(new_nodes) - set(old_nodes)),
            nodes_removed=len(set(old_nodes) - set(new_nodes)),
            nodes_updated=updated_nodes,
            edges_added=len(set(new_edges) - set(old_edges)),
            edges_removed=len(set(old_edges) - set(new_edges)),
            old_api_fingerprint=old_fingerprints,
            new_api_fingerprint=new_fingerprints,
            boundary_dirty=dirty,
            shards_updated=updated_shards,
            references_reprocessed=resolution.reprocessed,
            references_reused=resolution.reused,
            directly_affected_shards=impact["directly_affected_shards"],
            affected_boundary_edges=impact["affected_boundary_edges"],
            impact_frontier_size=impact["impact_frontier_size"],
            wide_impact=impact["wide_impact"],
        )
        status_counts = {status: 0 for status in ("resolved", "ambiguous", "unresolved")}
        for reference in resolution.references:
            status_counts[reference.status] += 1
        metrics = Metrics(
            files_scanned=len(sources), files_parsed=len(added | modified) - parse_failures,
            parse_failures=parse_failures, syntax_error_files=syntax_error_files,
            nodes_created=len(nodes), edges_created=len(edges),
            raw_references=len(resolution.references),
            resolved_references=status_counts["resolved"],
            ambiguous_references=status_counts["ambiguous"],
            unresolved_references=status_counts["unresolved"],
            shards_created=len(shards),
            boundary_edges=sum(edge.metadata.get("scope") == "boundary" for edge in edges),
            files_reparsed=len(added | modified), files_reused=max(len(sources) - len(added | modified), 0),
            references_reprocessed=resolution.reprocessed, references_reused=resolution.reused,
            shards_updated=len(updated_shards), shards_reused=max(len(shards) - len(updated_shards), 0),
            boundary_edges_reprocessed=boundary_edges_reprocessed,
            boundary_edges_reused=max(len(new_boundary_ids) - boundary_edges_reprocessed, 0),
            impact_frontier_size=impact["impact_frontier_size"], wide_impact=impact["wide_impact"],
            changed_files=len(changed), affected_nodes=delta.nodes_added + delta.nodes_removed + delta.nodes_updated,
            affected_edges=delta.edges_added + delta.edges_removed,
        )
        storage.replace_snapshot(
            repo_id=repo_id, root=root, generation=new_generation, mode="incremental",
            files=files, nodes=nodes, edges=edges, shards=shards,
            raw_references=resolution.references, metrics=metrics,
        )
        metrics.database_size = storage.database_size
        metrics.incremental_time_ms = (time.perf_counter() - started) * 1000
        storage.connection.execute(
            "UPDATE graph_generation SET metrics=? WHERE repo_id=? AND generation=?",
            (json.dumps(metrics.to_dict(), sort_keys=True), repo_id, new_generation),
        )
        storage.connection.commit()
    return {
        "repo_id": repo_id, "graph_generation": new_generation, "changed": True,
        "changes": {"added": sorted(added), "modified": sorted(modified), "deleted": sorted(deleted)},
        "delta": delta.to_dict(), "metrics": metrics.to_dict(), "database": str(database),
    }

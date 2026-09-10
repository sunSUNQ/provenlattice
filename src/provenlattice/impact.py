from __future__ import annotations

import json
from collections.abc import Iterable


def _metadata(edge: dict) -> dict:
    value = edge.get("metadata", {})
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value


def compute_impact_frontier(
    changed_shards: Iterable[str],
    old_edges: dict[str, dict],
    new_edges: dict[str, dict],
    threshold: int = 8,
) -> dict:
    """Return the conservative 0-hop/1-hop frontier for a snapshot transition."""
    changed = set(changed_shards)

    def boundary(edges: dict[str, dict]) -> dict[str, dict]:
        return {edge_id: edge for edge_id, edge in edges.items() if _metadata(edge).get("scope") == "boundary"}

    old_boundary = boundary(old_edges)
    new_boundary = boundary(new_edges)
    changed_boundary_ids = set(old_boundary) ^ set(new_boundary)
    changed_boundary_edges = [
        old_boundary.get(edge_id) or new_boundary[edge_id]
        for edge_id in sorted(changed_boundary_ids)
    ]
    directly_affected = {
        _metadata(edge).get("src_shard_id")
        for edge in changed_boundary_edges
        if _metadata(edge).get("dst_shard_id") in changed
        and _metadata(edge).get("src_shard_id") not in changed
    }
    directly_affected.discard(None)
    frontier = sorted(directly_affected)
    return {
        "changed_shards": sorted(changed),
        "directly_affected_shards": frontier,
        "affected_boundary_edges": sorted(changed_boundary_ids),
        "impact_frontier_size": len(frontier),
        "wide_impact": len(frontier) > threshold,
    }

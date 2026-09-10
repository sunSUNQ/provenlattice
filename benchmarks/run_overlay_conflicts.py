from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import time
from pathlib import Path

from provenlattice.models import OverlayDelta
from provenlattice.overlay import (
    GraphView, OverlayStore, commit_to_branch, detect_conflicts, merge_overlays,
    rebase_overlay,
)


def load(database: Path, sql: str) -> list[dict]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(sql)]
    finally:
        connection.close()


def run_case(name: str, database: Path, commit: str) -> dict:
    repository = load(database, "SELECT * FROM repositories LIMIT 1")[0]
    nodes = load(database, "SELECT * FROM nodes WHERE shard_id IS NOT NULL ORDER BY shard_id,id")
    first = nodes[0]
    second = next(node for node in nodes if node["shard_id"] != first["shard_id"])
    boundary = load(database, "SELECT * FROM shard_edges ORDER BY edge_id LIMIT 1")[0]

    def create(root: Path, label: str, overlay_type: str = "BRANCH") -> OverlayStore:
        return OverlayStore.create(
            root / f"{label}.db", overlay_type=overlay_type,
            repository_id=repository["repo_id"], base_commit=commit,
            base_generation=repository["current_generation"], branch_name=label,
        )

    with tempfile.TemporaryDirectory(prefix=f"pl-v04-conflict-{name}-") as temp:
        root = Path(temp)
        left, right, merged = create(root, "left"), create(root, "right"), create(root, "merged")
        left.put(OverlayDelta(left.metadata.overlay_id, "Node", first["id"], "UPDATE", "base",
                              {**first, "source_hash": "left"}, 2))
        right.put(OverlayDelta(right.metadata.overlay_id, "Node", second["id"], "UPDATE", "base",
                               {**second, "source_hash": "right"}, 2))
        no_conflict = merge_overlays(left, right, merged)["status"]
        different_shards = first["shard_id"] != second["shard_id"]
        left.close(); right.close(); merged.close()

        left, right = create(root, "same-left"), create(root, "same-right")
        left.put(OverlayDelta(left.metadata.overlay_id, "Node", first["id"], "UPDATE", "base",
                              {**first, "source_hash": "left"}, 2))
        right.put(OverlayDelta(right.metadata.overlay_id, "Node", first["id"], "UPDATE", "base",
                               {**first, "source_hash": "right"}, 2))
        entity_types = {item.conflict_type for item in detect_conflicts(left, right)}
        left.close(); right.close()

        left, right = create(root, "api-left"), create(root, "boundary-right")
        shard_id = boundary["dst_shard_id"]
        left.put(OverlayDelta(left.metadata.overlay_id, "Shard", shard_id, "UPDATE", "base",
                              {"shard_id": shard_id, "boundary_dirty": 1}, 2))
        right.put(OverlayDelta(right.metadata.overlay_id, "BoundaryEdge", boundary["edge_id"],
                               "UPDATE", "base", boundary, 2))
        boundary_types = {item.conflict_type for item in detect_conflicts(left, right)}
        rebased = create(root, "rebased")
        rebase_started = time.perf_counter()
        rebase = rebase_overlay(database, database, left, rebased)
        rebase_ms = (time.perf_counter() - rebase_started) * 1000
        left.close(); right.close(); rebased.close()

        branch, session = create(root, "branch"), create(root, "session", "SESSION")
        session.put(OverlayDelta(session.metadata.overlay_id, "Node", first["id"], "UPDATE", "base",
                                 {**first, "source_hash": "session"}, 2))
        commit_started = time.perf_counter()
        committed = commit_to_branch(session, branch)
        commit_ms = (time.perf_counter() - commit_started) * 1000
        session_status = session.metadata.status
        branch.close(); session.close()

        stale = create(root, "stale")
        stale_path = stale.path
        stale.close()
        try:
            GraphView(database, stale_path, current_base_commit="advanced")
            stale_status = "MISSED"
        except RuntimeError:
            with OverlayStore(stale_path) as reopened:
                stale_status = reopened.metadata.status

        return {
            "benchmark": name, "different_shards": different_shards,
            "no_conflict_merge": no_conflict,
            "same_entity_conflicts": sorted(entity_types),
            "boundary_conflicts": sorted(boundary_types),
            "rebase": rebase, "rebase_time_ms": round(rebase_ms, 3),
            "session_commit": committed, "commit_time_ms": round(commit_ms, 3),
            "session_status": session_status, "stale_status": stale_status,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", required=True, type=Path)
    args = parser.parse_args()
    baseline = json.loads((args.analysis / "provenlattice-v0.2-baseline.json").read_text(encoding="utf-8"))
    commits = {item["benchmark"]: item["commit_sha"] for item in baseline["benchmarks"]}
    results = [run_case(name, args.analysis / "v0.2-db" / f"{repo}.db", commits[name])
               for name, repo in (("B1-aria2", "aria2"), ("B2-brpc", "brpc"))]
    output = {"schema_version": 1, "benchmarks": results}
    target = args.analysis / "provenlattice-v0.4-conflicts.json"
    target.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

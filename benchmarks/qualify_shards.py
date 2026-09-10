from __future__ import annotations

import argparse
import json
import math
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path

from provenlattice.graph import full_index
from provenlattice.shard import BuildAwareShardStrategy, DirectoryShardStrategy, StructuralShardStrategy


def commit_sha(repo: Path) -> str:
    git_dir = repo / ".git"
    if not (git_dir / "HEAD").exists():
        return "fixture"
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref: "):
        return head
    reference = head[5:]
    loose = git_dir / reference
    if loose.exists():
        return loose.read_text(encoding="utf-8").strip()
    for line in (git_dir / "packed-refs").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith(("#", "^")):
            sha, name = line.split(" ", 1)
            if name == reference:
                return sha
    raise RuntimeError(f"cannot resolve Git HEAD for {repo}")


def summary(values: list[int]) -> dict[str, int]:
    if not values:
        return {"min": 0, "median": 0, "p95": 0, "max": 0}
    values = sorted(values)
    return {"min": values[0], "median": values[(len(values) - 1) // 2],
            "p95": values[max(0, math.ceil(len(values) * 0.95) - 1)], "max": values[-1]}


def qualify(database: Path) -> dict:
    with closing(sqlite3.connect(database)) as connection:
        file_counts = Counter(row[0] for row in connection.execute("SELECT shard_id FROM files"))
        node_counts = Counter(row[0] for row in connection.execute("SELECT shard_id FROM nodes WHERE shard_id IS NOT NULL"))
        internal = connection.execute(
            "SELECT COUNT(*) FROM edges WHERE json_extract(metadata, '$.scope')='internal'"
        ).fetchone()[0]
        boundary = connection.execute(
            "SELECT COUNT(*) FROM edges WHERE json_extract(metadata, '$.scope')='boundary'"
        ).fetchone()[0]
        incident = Counter()
        for source, target in connection.execute("SELECT src_shard_id,dst_shard_id FROM shard_edges"):
            incident[source] += 1
            incident[target] += 1
        shard_ids = [row[0] for row in connection.execute("SELECT shard_id FROM shards")]
        metrics = json.loads(connection.execute(
            "SELECT metrics FROM graph_generation ORDER BY generation DESC LIMIT 1"
        ).fetchone()[0])
    total_nodes = sum(node_counts.values())
    structural_edges = internal + boundary
    return {
        "shard_count": len(shard_ids), "files_per_shard": summary(list(file_counts.values())),
        "nodes_per_shard": summary([node_counts[sid] for sid in shard_ids]),
        "internal_edges": internal, "boundary_edges": boundary,
        "boundary_ratio": round(boundary / structural_edges, 6) if structural_edges else 0.0,
        "isolated_shards": sum(not incident[sid] for sid in shard_ids),
        "giant_shard_ratio": round(max((node_counts[sid] for sid in shard_ids), default=0) / total_nodes, 6),
        "full_index_time_ms": metrics.get("index_time_ms", 0),
        "database_size_bytes": metrics.get("database_size", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append", required=True, help="name|repository-path")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    factories = {
        "directory": DirectoryShardStrategy,
        "build-aware": BuildAwareShardStrategy,
        "structural": StructuralShardStrategy,
    }
    results = []
    for case in args.case:
        name, repo = case.split("|", 1)
        for strategy_name, factory in factories.items():
            print(f"[{name}/{strategy_name}] indexing", flush=True)
            with tempfile.TemporaryDirectory(prefix="pl-v03-shard-") as temp:
                database = Path(temp) / "graph.db"
                full_index(repo, database, strategy=factory())
                item = qualify(database)
            item.update({"benchmark": name, "strategy": strategy_name,
                         "repository_path": str(Path(repo).resolve()),
                         "commit_sha": commit_sha(Path(repo).resolve())})
            results.append(item)
    output = {"schema_version": 1, "strategies": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path

from provenlattice.graph import full_index
from provenlattice.models import OverlayDelta
from provenlattice.overlay import (
    OverlayStore, capture_snapshot_delta, materialization_parity, overlay_metrics,
)
from provenlattice.query import GraphQuery
from provenlattice.shard import DirectoryShardStrategy


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(len(ordered) * fraction + 0.999) - 1))]


def query_latency(database: Path, name: str, branch: Path | None = None,
                  session: Path | None = None, samples: int = 20) -> dict:
    values = []
    with GraphQuery(database, branch_overlay=branch, session_overlay=session) as query:
        for _ in range(samples):
            started = time.perf_counter()
            query.find_symbol(name)
            values.append((time.perf_counter() - started) * 1000)
    return {"p50_ms": round(statistics.median(values), 4),
            "p95_ms": round(percentile(values, 0.95), 4)}


def base_repository(database: Path) -> dict:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        return dict(connection.execute("SELECT * FROM repositories LIMIT 1").fetchone())
    finally:
        connection.close()


def anchor_node(database: Path) -> dict:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        return dict(connection.execute(
            "SELECT * FROM nodes WHERE kind IN ('Function','Method') ORDER BY id LIMIT 1"
        ).fetchone())
    finally:
        connection.close()


def run_case(name: str, repo: Path, base_db: Path, relative_file: str,
             commit: str, output_dir: Path) -> dict:
    started = time.perf_counter()
    base = base_repository(base_db)
    with tempfile.TemporaryDirectory(prefix=f"pl-v04-{name}-") as temp:
        root = Path(temp) / repo.name
        shutil.copytree(repo, root, ignore=shutil.ignore_patterns(".git"))
        path = root / relative_file
        path.write_text(path.read_text(encoding="utf-8") + "\n// provenlattice-v04-overlay-body\n",
                        encoding="utf-8")
        target_db = Path(temp) / "target.db"
        full_index(root, target_db, strategy=DirectoryShardStrategy(),
                   repository_id_override=base["repo_id"])
        branch_path = output_dir / f"{name}-branch-overlay.db"
        session_path = output_dir / f"{name}-session-overlay.db"
        for overlay_path in (branch_path, session_path):
            if overlay_path.exists():
                overlay_path.unlink()
        branch = OverlayStore.create(
            branch_path, overlay_type="BRANCH", repository_id=base["repo_id"],
            base_commit=commit, base_generation=base["current_generation"], branch_name=f"{name}-branch",
        )
        session = OverlayStore.create(
            session_path, overlay_type="SESSION", repository_id=base["repo_id"],
            base_commit=commit, base_generation=base["current_generation"], branch_name=f"{name}-branch",
            parent_overlay_id=branch.metadata.overlay_id,
        )
        try:
            apply_started = time.perf_counter()
            capture_snapshot_delta(base_db, target_db, branch)
            apply_ms = (time.perf_counter() - apply_started) * 1000
            parity = materialization_parity(base_db, target_db, branch)
            node = anchor_node(base_db)
            session_value = dict(node)
            session_value["metadata"] = json.dumps({"overlay_session": True}, sort_keys=True)
            session.put(OverlayDelta(
                session.metadata.overlay_id, "Node", node["id"], "UPDATE", "session-base",
                session_value, base["current_generation"] + 1,
            ))
            base_latency = query_latency(base_db, node["name"])
            branch_latency = query_latency(base_db, node["name"], branch_path)
            session_latency = query_latency(base_db, node["name"], branch_path, session_path)
            metrics = overlay_metrics(base_db, branch)
            metrics["session_overlay_size"] = session.database_size
            metrics["overlay_apply_time_ms"] = round(apply_ms, 3)
            metrics["materialization_parity"] = parity
            metrics["query_latency"] = {"base": base_latency, "branch": branch_latency,
                                        "branch_session": session_latency}
            metrics["query_overhead_p95"] = {
                "branch": branch_latency["p95_ms"] / base_latency["p95_ms"] - 1,
                "branch_session": session_latency["p95_ms"] / base_latency["p95_ms"] - 1,
            }
            metrics["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
            return {"benchmark": name, "commit_sha": commit, "changed_file": relative_file,
                    "metrics": metrics}
        finally:
            branch.close()
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads((args.analysis / "provenlattice-v0.2-baseline.json").read_text(encoding="utf-8"))
    commits = {item["benchmark"]: item["commit_sha"] for item in baseline["benchmarks"]}
    cases = [
        ("B1-aria2", "aria2", "src/AbstractCommand.cc"),
        ("B2-brpc", "brpc", "src/brpc/builtin/common.cpp"),
        ("B3-rocksdb", "rocksdb", "db/db_impl/db_impl.cc"),
    ]
    output_dir = args.analysis / "v0.4-overlays"
    output_dir.mkdir(parents=True, exist_ok=True)
    results = [run_case(name, args.root / "benchmark-repos" / repo,
                        args.analysis / "v0.2-db" / f"{repo}.db", relative,
                        commits[name], output_dir) for name, repo, relative in cases]
    output = {"schema_version": 1, "benchmarks": results}
    target = args.analysis / "provenlattice-v0.4-overlay.json"
    target.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

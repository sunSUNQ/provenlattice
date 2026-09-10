from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import platform
import sqlite3
import statistics
import time
from contextlib import closing
from pathlib import Path
from typing import Callable

from provenlattice.graph import full_index
from provenlattice.query import GraphQuery


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * quantile) - 1)]


def latency(call: Callable[[], object], samples: int) -> dict[str, float]:
    for _ in range(3):
        call()
    values = []
    for _ in range(samples):
        started = time.perf_counter()
        call()
        values.append((time.perf_counter() - started) * 1000)
    return {
        "p50_ms": round(statistics.median(values), 4),
        "p95_ms": round(percentile(values, 0.95), 4),
    }


def peak_memory_bytes() -> int | None:
    if os.name == "nt":
        from ctypes import wintypes

        class MemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        counters = MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        process = kernel32.GetCurrentProcess()
        get_memory = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
        get_memory.restype = wintypes.BOOL
        if get_memory(process, ctypes.byref(counters), counters.cb):
            return int(counters.PeakWorkingSetSize)
        return None
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(usage if platform.system() == "Darwin" else usage * 1024)
    except (ImportError, ValueError):
        return None


def commit_sha(repo: Path) -> str:
    git_dir = repo / ".git"
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref: "):
        return head
    reference = head[5:]
    loose = git_dir / reference
    if loose.exists():
        return loose.read_text(encoding="utf-8").strip()
    packed = git_dir / "packed-refs"
    if packed.exists():
        for line in packed.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith(("#", "^")):
                sha, name = line.split(" ", 1)
                if name == reference:
                    return sha
    raise RuntimeError(f"cannot resolve Git HEAD for {repo}")


def run(repo: Path, name: str, database: Path, samples: int, c_cpp_loc: int) -> dict:
    repo = repo.resolve()
    database = database.resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        database.unlink()
    print(f"[{name}] indexing {repo}", flush=True)
    indexed = full_index(repo, database)
    metrics = indexed["metrics"]
    print(f"[{name}] index complete; sampling queries", flush=True)

    with GraphQuery(database) as query:
        anchor = query.storage.row(
            """WITH call_degree AS (
                   SELECT node_id, SUM(degree) AS degree FROM (
                       SELECT src_id AS node_id, COUNT(*) AS degree
                       FROM edges WHERE type='CALLS' GROUP BY src_id
                       UNION ALL
                       SELECT dst_id AS node_id, COUNT(*) AS degree
                       FROM edges WHERE type='CALLS' GROUP BY dst_id
                   ) GROUP BY node_id
               )
               SELECT n.id, n.name, n.qualified_name, call_degree.degree
               FROM call_degree JOIN nodes n ON n.id=call_degree.node_id
               WHERE n.kind IN ('Function','Method')
               ORDER BY call_degree.degree DESC, n.qualified_name LIMIT 1"""
        )
        if anchor:
            query_latencies = {
                "symbol": latency(lambda: query.find_symbol(anchor["name"]), samples),
                "caller": latency(lambda: query.get_callers(anchor["id"]), samples),
                "callee": latency(lambda: query.get_callees(anchor["id"]), samples),
                "subgraph": latency(
                    lambda: query.get_subgraph(anchor["id"], max_hops=2, max_nodes=100), samples
                ),
            }
        else:
            query_latencies = {}
    print(f"[{name}] query sampling complete", flush=True)

    with closing(sqlite3.connect(database)) as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("nodes", "edges", "raw_references", "shards")
        }
        reference_status = {
            status: connection.execute(
                "SELECT COUNT(*) FROM raw_references WHERE status=?", (status,)
            ).fetchone()[0]
            for status in ("resolved", "ambiguous", "unresolved")
        }
        boundary_edges = connection.execute(
            "SELECT COUNT(*) FROM edges WHERE json_extract(metadata, '$.scope')='boundary'"
        ).fetchone()[0]

    files_scanned = int(metrics["files_scanned"])
    parse_failures = int(metrics["parse_failures"])
    syntax_error_files = int(metrics["syntax_error_files"])
    return {
        "benchmark": name,
        "repository_path": str(repo),
        "commit_sha": commit_sha(repo),
        "c_cpp_loc": c_cpp_loc,
        "files_scanned": files_scanned,
        "files_parsed": int(metrics["files_parsed"]),
        "parse_failures": parse_failures,
        "syntax_error_files": syntax_error_files,
        "parse_coverage_percent": round(
            100.0 * int(metrics["files_parsed"]) / files_scanned, 3
        ) if files_scanned else 100.0,
        "syntax_clean_percent": round(
            100.0 * (files_scanned - syntax_error_files) / files_scanned, 3
        ) if files_scanned else 100.0,
        "nodes": counts["nodes"],
        "raw_references": counts["raw_references"],
        "resolved_references": reference_status["resolved"],
        "ambiguous_references": reference_status["ambiguous"],
        "unresolved_references": reference_status["unresolved"],
        "edges": counts["edges"],
        "shards": counts["shards"],
        "boundary_edges": boundary_edges,
        "full_index_time_ms": round(float(metrics["index_time_ms"]), 3),
        "peak_memory_bytes": peak_memory_bytes(),
        "database_size_bytes": database.stat().st_size,
        "query_anchor": anchor,
        "query_latency": query_latencies,
        "query_samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--c-cpp-loc", required=True, type=int)
    parser.add_argument("--samples", type=int, default=30)
    args = parser.parse_args()
    result = run(args.repo, args.name, args.database, args.samples, args.c_cpp_loc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

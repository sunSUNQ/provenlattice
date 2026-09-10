from __future__ import annotations

import argparse
import ctypes
import json
import math
import shutil
import sqlite3
import time
from pathlib import Path

from provenlattice.knowledge import index_knowledge
from provenlattice.query import GraphQuery


class ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_working_set() -> int | None:
    if not hasattr(ctypes, "windll"):
        return None
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    get_process = ctypes.windll.kernel32.GetCurrentProcess
    get_process.restype = ctypes.c_void_p
    process = get_process()
    get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory.argtypes = (ctypes.c_void_p, ctypes.POINTER(ProcessMemoryCounters),
                           ctypes.c_ulong)
    get_memory.restype = ctypes.c_int
    if not get_memory(
        process, ctypes.byref(counters), counters.cb
    ):
        return None
    return int(counters.PeakWorkingSetSize)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)], 4)


def latency(samples: int, operation) -> dict:
    values = []
    for _ in range(samples):
        started = time.perf_counter()
        operation()
        values.append((time.perf_counter() - started) * 1000)
    return {"p50_ms": percentile(values, 0.50), "p95_ms": percentile(values, 0.95),
            "samples": samples}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("base_database", type=Path)
    parser.add_argument("output_database", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--samples", type=int, default=30)
    args = parser.parse_args()
    args.output_database.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.base_database, args.output_database)
    before_size = args.output_database.stat().st_size
    metrics = index_knowledge(args.repo, args.output_database, incremental=False)
    with sqlite3.connect(args.output_database) as connection:
        resolved = connection.execute(
            "SELECT source_node_id,resolved_target_id FROM raw_evidence_links "
            "WHERE resolution_status='resolved' ORDER BY id LIMIT 1"
        ).fetchone()
        requirement = connection.execute(
            "SELECT id FROM nodes WHERE kind='Requirement' ORDER BY id LIMIT 1"
        ).fetchone()
    query_latency = {}
    with GraphQuery(args.output_database) as query:
        query_latency["evidence_lookup"] = latency(
            args.samples, lambda: query.get_evidence_links(status="resolved")
        )
        if resolved:
            query_latency["document_to_code"] = latency(
                args.samples, lambda: query.get_document_targets(resolved[0])
            )
            query_latency["cross_layer_subgraph"] = latency(
                args.samples, lambda: query.get_subgraph(resolved[0], 2, 100)
            )
        if requirement:
            query_latency["requirement_to_code"] = latency(
                args.samples, lambda: query.get_implemented_code(requirement[0])
            )
    result = {
        "schema_version": 1,
        "benchmark": "B2-brpc-knowledge",
        "repository_path": str(args.repo.resolve()),
        "commit_sha": args.commit_sha,
        "source_codegraph_database": str(args.base_database.resolve()),
        "codegraph_database_size_bytes": before_size,
        "combined_database_size_bytes": args.output_database.stat().st_size,
        "knowledge_database_growth_bytes": args.output_database.stat().st_size - before_size,
        "peak_working_set_bytes": peak_working_set(),
        "metrics": metrics,
        "query_latency": query_latency,
        "notes": [
            "Existing V0.2 CodeGraph database was copied; C/C++ Full Index was not rerun.",
            "The benchmark checkout was read only and no synthetic requirements were added.",
            "Missing query classes mean the real repository contained no resolvable source of that kind.",
        ],
    }
    args.output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Deterministic systems workload runner for SYSTEMS_BENCHMARK_CONTRACT_V1 (P1/RQ2).

Workloads (cache terminology per review R1; "cold filesystem cache" / "true cold
cache" are not valid V1 terms because OS page-cache eviction is never attempted):
  A  Full Build (process-cold, db-fresh)     - fresh DB + fresh child process per rep
  B  Full Build (process-cold, db-fresh, prior-run OS-cache-eligible)
  C  Incremental Update - Full(A) -> frozen mutations -> Incremental(A->B) -> Full(B) parity
      per-rep execution order is hard-gated (blocker WORKLOAD_C_MUTATION_ORDER):
      copy frozen A -> initial index from UNMODIFIED A -> verify baseline A
      against frozen file hashes -> apply mutation -> Incremental(A->B) ->
      freshness probe -> Full(B) -> exact parity
  D  Online Query - frozen query manifest against a read-only DB, first-query + warm-repeat

Instrumentation rules (contract section 5):
  * every measured build / query session runs in a dedicated child process, so
    per-rep peak RSS and CPU time refer to the main measured child only
    (review R3): Windows PeakWorkingSetSize / POSIX RUSAGE_SELF; neither is
    process-tree memory/CPU nor total system consumption;
  * raw per-rep measurements are stored verbatim; medians/percentiles/normalized
    values are recomputable and live in a separate "derived" block;
  * parity is judged by SHA256 snapshot digests over canonical, order-independent
    tuple streams of the state tables (nodes, edges, raw_references incl.
    candidates, shards incl. api_fingerprint, files, shard_edges) of both DBs of
    the SAME repository path (review R8); strict metadata digests are diagnostic
    only with a recorded disposition; +-10% count drift is an anomaly guard and
    never a parity substitute;
  * update latency and query-visible freshness are separate clocks (review R9):
    update_completion_latency_ms is the system-under-test incremental command
    time; query_visible_time_to_freshness_ms is measured with a frozen
    post-update validation probe that must observe the expected changed graph
    state;
  * system-under-test time is recorded separately from harness/setup and
    validation/parity overhead (review R10);
  * the emitted run record is validated against
    schema/systems-run-schema-v1.json BEFORE any artifact is written; invalid
    records are not written as run artifacts (review R4).

Usage (parent mode):
  python tools/run-systems-workload-v1.py --benchmark B1-aria2 --workload A
  python tools/run-systems-workload-v1.py --benchmark B1-aria2 --workload C \
      --mutation-manifest manifests/mutations-aria2-v1.json --mutation-family M1
  python tools/run-systems-workload-v1.py --benchmark B1-aria2 --workload D \
      --query-manifest manifests/queries-aria2-v1.json
Validation only:
  python tools/run-systems-workload-v1.py --validate results/<record>.json
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import json
import math
import os
import platform
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 2
CONTRACT_ID = "SYSTEMS_BENCHMARK_CONTRACT_V1"
CHILD_MARKER = "@@CHILD_RESULT@@"
SYMBOL_KINDS = ("Namespace", "Class", "Struct", "Interface", "Function", "Method", "Type")

# Frozen qualification minima (contract section 4; review R5). Smoke runs are
# exempt but are labelled run_kind=smoke and never enter formal statistics.
MIN_BUILD_MEASURED_REPS = 5
MIN_WORKLOAD_C_REPS = 3
MIN_QUERY_WARM_ROUNDS = 30

HERE = Path(__file__).resolve().parent
SYSTEMS_V1 = HERE.parent
REPO_ROOT = SYSTEMS_V1.parent.parent
CONTRACT_PATH = SYSTEMS_V1 / "contract" / "systems-benchmark-contract-v1.md"
SCHEMA_PATH = SYSTEMS_V1 / "schema" / "systems-run-schema-v1.json"
MANIFESTS_DIR = SYSTEMS_V1 / "manifests"
RESULTS_DIR = SYSTEMS_V1 / "results"
SCHEDULE_PATH = MANIFESTS_DIR / "schedule-v1.json"


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def r(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_git_head(repo: Path) -> str:
    git_dir = repo / ".git"
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


def _tool_version(distribution: str) -> str:
    try:
        from importlib.metadata import version
        return version(distribution)
    except Exception:
        return "UNKNOWN"


def _windows_cpu_and_ram() -> tuple[str, str, int | str]:
    """(cpu_model, physical_cores, ram_total_bytes); UNKNOWN where unavailable."""
    ram = "UNKNOWN"
    try:
        from ctypes import wintypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            ram = int(status.ullTotalPhys)
    except Exception:
        pass
    cpu_model = platform.processor() or "UNKNOWN"
    physical = "UNKNOWN"
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$c=Get-CimInstance Win32_Processor | Select-Object -First 1; "
             "\"{0}|{1}\"".format("$($c.Name)", "$($c.NumberOfCores)")],
            capture_output=True, text=True, timeout=30)
        if completed.returncode == 0 and "|" in completed.stdout:
            name, cores = completed.stdout.strip().split("|", 1)
            if name:
                cpu_model = name.strip()
            if cores.strip().isdigit():
                physical = int(cores.strip())
    except Exception:
        pass
    return cpu_model, physical, ram


def _posix_cpu_and_ram() -> tuple[str, str, int | str]:
    ram = "UNKNOWN"
    cpu_model = platform.processor() or "UNKNOWN"
    physical = "UNKNOWN"
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                ram = int(line.split()[1]) * 1024
                break
        model = ""
        packages: set[str] = set()
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name") and not model:
                model = line.split(":", 1)[1].strip()
            if line.startswith("physical id"):
                packages.add(line.split(":", 1)[1].strip())
        if model:
            cpu_model = model
        if packages:
            physical = len(packages)
    except Exception:
        pass
    return cpu_model, physical, ram


def _storage_type_for(path: Path) -> str:
    try:
        if os.name == "nt":
            kernel32 = ctypes.WinDLL("kernel32")
            drive = path.drive + "\\"
            kinds = {0: "UNKNOWN_DRIVE", 1: "NO_ROOT_DIR", 2: "REMOVABLE",
                     3: "FIXED", 4: "REMOTE", 5: "CDROM", 6: "RAMDISK"}
            kind = kinds.get(kernel32.GetDriveTypeW(ctypes.c_wchar_p(drive)), "UNKNOWN_DRIVE")
            fs_buf = ctypes.create_unicode_buffer(64)
            ok = kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(drive), None, 0, None, None, None, fs_buf, 64)
            fs = fs_buf.value if (ok and fs_buf.value) else "UNKNOWN_FS"
            return f"{kind}/{fs}"
        target = path.resolve()
        best, best_fs = "", "UNKNOWN_FS"
        for line in Path("/proc/mounts").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 3 and target.as_posix().startswith(parts[1]) and \
                    len(parts[1]) > len(best):
                best, best_fs = parts[1], parts[2]
        return best_fs
    except Exception:
        return "UNKNOWN"


def environment() -> dict:
    if os.name == "nt":
        cpu_model, physical, ram = _windows_cpu_and_ram()
    else:
        cpu_model, physical, ram = _posix_cpu_and_ram()
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "cpu_model": cpu_model,
        "cpu_logical_cores": os.cpu_count() if os.cpu_count() is not None else "UNKNOWN",
        "cpu_physical_cores": physical,
        "ram_total_bytes": ram,
        "storage_type": _storage_type_for(HERE),
        "python": platform.python_version(),
        "provenlattice_git_head": repo_git_head(REPO_ROOT),
        "sqlite_version": sqlite3.sqlite_version,
        "thread_configuration": "single_process_sequential",
        "tool_versions": {
            "tree_sitter": _tool_version("tree-sitter"),
            "tree_sitter_cpp": _tool_version("tree-sitter-cpp"),
            "tree_sitter_python": _tool_version("tree-sitter-python"),
        },
        "load_note": "",
    }


def effective_config(shard_strategy: str) -> dict:
    """Canonical effective configuration (review R2). Hashed into the record."""
    return {
        "parser_backend": "tree_sitter",
        "languages": ["c", "cpp", "python"],
        "resolver": "provenlattice.resolver.SymbolResolver (V0.2 default)",
        "shard_strategy_effective": shard_strategy,
        "threading": "single_process_sequential",
        "persistence": "sqlite3",
    }


def strategy_for(name: str):
    from provenlattice.shard import (
        BuildAwareShardStrategy, DirectoryShardStrategy, StructuralShardStrategy)
    return {
        "directory": DirectoryShardStrategy,
        "build-aware": BuildAwareShardStrategy,
        "structural": StructuralShardStrategy,
    }[name]()


def peak_rss_bytes() -> int | None:
    """Peak RSS of the MAIN measured child only (review R3)."""
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


def db_counts(database: Path, files_scanned: int | None = None) -> dict:
    # contextlib.closing, not `with connection`: sqlite3 context managers only
    # scope transactions; an unclosed handle keeps the file locked on Windows
    # and breaks workdir cleanup (disk-full run invalidations).
    with contextlib.closing(
            sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as connection:
        nodes = connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edges = connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        raw_references = connection.execute("SELECT COUNT(*) FROM raw_references").fetchone()[0]
        shards = connection.execute("SELECT COUNT(*) FROM shards").fetchone()[0]
        symbols = connection.execute(
            "SELECT COUNT(*) FROM nodes WHERE kind IN "
            "(?,?,?,?,?,?,?)", SYMBOL_KINDS).fetchone()[0]
        boundary_edges = connection.execute(
            "SELECT COUNT(*) FROM edges WHERE json_extract(metadata, '$.scope')='boundary'"
        ).fetchone()[0]
        status = {
            s: connection.execute(
                "SELECT COUNT(*) FROM raw_references WHERE status=?", (s,)
            ).fetchone()[0]
            for s in ("resolved", "ambiguous", "unresolved")
        }
    return {
        "nodes": nodes,
        "symbols": symbols,
        "raw_references": raw_references,
        "edges": edges,
        "shards": shards,
        "boundary_edges": boundary_edges,
        "resolved_references": status["resolved"],
        "ambiguous_references": status["ambiguous"],
        "unresolved_references": status["unresolved"],
        "files_scanned": files_scanned if files_scanned is not None else 0,
    }


def _order_free(obj: object) -> object:
    if isinstance(obj, dict):
        return {key: _order_free(value) for key, value in obj.items()}
    if isinstance(obj, list):
        items = [_order_free(value) for value in obj]
        return sorted(
            items,
            key=lambda item: canonical_json(item) if isinstance(item, (dict, list)) else str(item))
    return obj


def _canon_column(value: object) -> str:
    """Canonical form of a JSON-string column; order-independent (review R8)."""
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", "replace")
    if not isinstance(value, str):
        return str(value)
    try:
        loaded = json.loads(value)
    except (ValueError, TypeError):
        return value
    return canonical_json(_order_free(loaded))


def snapshot_digests(database: Path) -> dict:
    """SHA256 over canonical tuple streams of the state tables (review R8).

    Parity gate (facts digests): node identities, edge identities,
    raw-reference identity/location/resolution state incl. candidates,
    shard state incl. api_fingerprint, file identities incl. source hashes,
    and the boundary shard-edge index.
    Strict digests add provenance/metadata JSON columns and are diagnostic
    only: JSON field/element ordering noise is handled via canonicalization,
    but any remaining strict divergence is recorded as
    RECORDED_NON_GATING_PROVENANCE_DIVERGENCE, never silently dropped.
    Generation counters are deliberately excluded: they are build-history
    artifacts, not query-visible state, and necessarily differ between an
    incrementally updated DB (generation n+1) and a fresh full rebuild.
    """

    def hash_rows(sql: str) -> str:
        digest = hashlib.sha256()
        with contextlib.closing(
                sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as connection:
            for row in connection.execute(sql):
                line = "\x1f".join(
                    f"{v:.6f}" if isinstance(v, float) else _canon_column(v)
                    for v in row
                )
                digest.update(line.encode("utf-8"))
                digest.update(b"\n")
        return digest.hexdigest()

    return {
        "nodes_facts": hash_rows(
            "SELECT id, kind, name, qualified_name, file_id, start_line, end_line, signature "
            "FROM nodes ORDER BY id"),
        "nodes_strict": hash_rows(
            "SELECT id, kind, name, qualified_name, file_id, start_line, end_line, signature, "
            "metadata FROM nodes ORDER BY id"),
        "edges_facts": hash_rows("SELECT id, src_id, dst_id, type FROM edges ORDER BY id"),
        "edges_strict": hash_rows(
            "SELECT id, src_id, dst_id, type, provenance, confidence, metadata "
            "FROM edges ORDER BY id"),
        "raw_references_facts": hash_rows(
            "SELECT id, repo_id, file_id, owner_symbol_id, raw_name, reference_type, "
            "target_module, start_line, end_line, status, resolved_symbol_id, "
            "resolution_strategy, confidence, candidate_symbols "
            "FROM raw_references ORDER BY id"),
        "raw_references_strict": hash_rows(
            "SELECT id, status, resolved_symbol_id, resolution_strategy, confidence, "
            "candidate_symbols, metadata FROM raw_references ORDER BY id"),
        "shards_facts": hash_rows(
            "SELECT shard_id, repo_id, path, nodes_count, edges_count, "
            "public_symbols, api_fingerprint FROM shards ORDER BY shard_id"),
        "files_facts": hash_rows(
            "SELECT file_id, repo_id, shard_id, path, language, source_hash "
            "FROM files ORDER BY file_id"),
        "shard_edges_facts": hash_rows(
            "SELECT edge_id, src_shard_id, dst_shard_id, edge_type, raw_reference_id "
            "FROM shard_edges ORDER BY edge_id"),
    }


PARITY_FACT_KEYS = [
    "nodes_facts", "edges_facts", "raw_references_facts",
    "shards_facts", "files_facts", "shard_edges_facts",
]
PARITY_STRICT_KEYS = ["nodes_strict", "edges_strict", "raw_references_strict"]

PARITY_COVERED_STATES = [
    "node identities (nodes_facts)",
    "edge identities (edges_facts)",
    "raw-reference identity/location/resolution state incl. candidates (raw_references_facts)",
    "shard state incl. api_fingerprint and public symbols (shards_facts)",
    "file identities incl. source hashes (files_facts)",
    "boundary shard-edge index (shard_edges_facts)",
]
PARITY_NOT_COVERED_STATES = [
    "generation counters (build-history artifacts, not query-visible state)",
    "graph_generation metrics rows",
    "nodes/edges/shards metadata JSON beyond identity columns (strict digests, diagnostic only)",
    "document_state (redundant with file_state/files for code-index workloads)",
    "raw_evidence_links (knowledge layer; not produced by A/B/C/D code-index workloads)",
    "OS-level database file byte layout",
]


# --------------------------------------------------------------------------
# child task execution
# --------------------------------------------------------------------------

def run_freshness_probe(database: Path, repo: Path, probe: dict) -> list:
    """Frozen post-update validation query (review R9): must observe the
    expected changed graph state; per-check results are recorded verbatim."""
    checks: list = []
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        for path in probe.get("expect_file_state_hash_changed", []):
            row = connection.execute(
                "SELECT source_hash FROM file_state WHERE path=?", (path,)).fetchone()
            disk = sha256_file(Path(repo) / path)
            ok = bool(row) and row[0] == disk
            checks.append({
                "check": "file_state_hash_changed",
                "expected": f"file_state.source_hash == sha256(mutated {path})",
                "observed": (
                    f"db={str(row[0])[:12] if row else 'ABSENT'} "
                    f"disk={disk[:12]}"),
                "passed": ok,
            })
        for path in probe.get("expect_file_state_absent", []):
            count = connection.execute(
                "SELECT COUNT(*) FROM file_state WHERE path=?", (path,)).fetchone()[0]
            checks.append({
                "check": "file_state_absent",
                "expected": f"no file_state row for {path}",
                "observed": f"rows={count}",
                "passed": count == 0,
            })
    if probe.get("expect_symbol_present") or probe.get("expect_signature_contains"):
        from provenlattice.query import GraphQuery
        with GraphQuery(database) as query:
            for name in probe.get("expect_symbol_present", []):
                result = query.find_symbol(name)
                rows = result.get("data") if isinstance(result, dict) else result
                rows = [row for row in (rows or []) if row]
                checks.append({
                    "check": "symbol_present",
                    "expected": f"find_symbol({name!r}) returns >= 1 row",
                    "observed": f"rows={len(rows)}",
                    "passed": len(rows) >= 1,
                })
            for item in probe.get("expect_signature_contains", []):
                result = query.find_symbol(item["symbol"])
                rows = result.get("data") if isinstance(result, dict) else result
                rows = [row for row in (rows or []) if row]
                hits = [row for row in rows
                        if item["token"] in str(row.get("signature") or "")]
                checks.append({
                    "check": "signature_contains",
                    "expected": (
                        f"signature of {item['symbol']!r} contains "
                        f"{item['token']!r}"),
                    "observed": f"rows={len(rows)} signature_hits={len(hits)}",
                    "passed": len(hits) >= 1,
                })
    return checks


def run_build_child(repo: Path, database: Path, shard_strategy: str) -> dict:
    from provenlattice.graph import full_index

    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        raise RuntimeError(
            f"db-fresh assertion failed: output database already exists: {database}")
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    indexed = full_index(repo, database, strategy=strategy_for(shard_strategy))
    cpu_ms = (time.process_time() - started_cpu) * 1000
    wall_ms = (time.perf_counter() - started_wall) * 1000
    metrics = indexed["metrics"]
    counts = db_counts(database, files_scanned=int(metrics["files_scanned"]))
    counts["files_parsed"] = int(metrics["files_parsed"])
    counts["parse_failures"] = int(metrics["parse_failures"])
    counts["syntax_error_files"] = int(metrics["syntax_error_files"])
    return {
        "wall_time_ms": r(wall_ms, 3),
        "cpu_time_ms": r(cpu_ms, 3),
        "peak_rss_bytes": peak_rss_bytes(),
        "db_size_bytes": database.stat().st_size,
        "counts": counts,
    }


def run_incremental_child(repo: Path, database: Path, shard_strategy: str,
                          probe: dict | None) -> dict:
    from provenlattice.incremental import incremental_update

    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    result = incremental_update(repo, database, strategy=strategy_for(shard_strategy))
    cpu_ms = (time.process_time() - started_cpu) * 1000
    wall_ms = (time.perf_counter() - started_wall) * 1000
    metrics = result["metrics"]
    delta = result["delta"]

    digest_started = time.perf_counter()
    digests = snapshot_digests(database)
    digest_ms = (time.perf_counter() - digest_started) * 1000

    probe_started = time.perf_counter()
    checks = run_freshness_probe(database, repo, probe or {})
    probe_latency_ms = (time.perf_counter() - probe_started) * 1000
    probe_ok = bool(checks) and all(check["passed"] for check in checks)
    # Query-Visible Time-to-Freshness (measured, not assumed): mutation applied
    # -> incremental_update returns -> probe observes changed state. Same
    # sequential child process; excludes harness spawn overhead (recorded in
    # clocks.benchmark_setup_time_ms).
    query_visible_ttf_ms = wall_ms + probe_latency_ms

    return {
        "wall_time_ms": r(wall_ms, 3),
        "cpu_time_ms": r(cpu_ms, 3),
        "peak_rss_bytes": peak_rss_bytes(),
        "db_size_bytes": database.stat().st_size,
        "changed": bool(result["changed"]),
        "changes": result.get("changes"),
        "files_reparsed": int(metrics["files_reparsed"]),
        "files_reused": int(metrics["files_reused"]),
        "files_changed_reported": int(metrics.get("changed_files") or 0),
        "nodes_changed": int(delta["nodes_added"]) + int(delta["nodes_removed"]) + int(delta["nodes_updated"]),
        "edges_changed": int(delta["edges_added"]) + int(delta["edges_removed"]),
        "references_reprocessed": int(delta["references_reprocessed"]),
        "references_reused": int(delta["references_reused"]),
        "impact_frontier_size": int(delta["impact_frontier_size"]),
        "digests": digests,
        "digest_ms": r(digest_ms, 3),
        "freshness_probe": {
            "probe_ok": probe_ok,
            "checks": checks,
            "probe_latency_ms": r(probe_latency_ms, 3),
            "query_visible_time_to_freshness_ms": r(query_visible_ttf_ms, 3),
            "note": (
                "frozen post-update validation query; observation measured, "
                "not assumed equal to update latency"),
        },
    }


def execute_query(query, spec: dict, anchor) -> object:
    kind = spec["type"]
    if kind == "symbol":
        return query.find_symbol(anchor["name"])
    if kind == "callers":
        return query.get_callers(anchor["id"])
    if kind == "callees":
        return query.get_callees(anchor["id"])
    if kind == "subgraph":
        return query.get_subgraph(anchor["id"], max_hops=2, max_nodes=100)
    raise RuntimeError(f"unknown query type: {kind}")


def resolve_anchor(query, spec: dict):
    """Resolve a manifest anchor and validate qualified identity (review R11)."""
    result = query.find_symbol(spec["name"])
    rows = result.get("data") if isinstance(result, dict) else result
    rows = [row for row in (rows or []) if row]
    matches = [row for row in rows
               if str(row.get("qualified_name")) == spec["anchor"]]
    if not matches:
        found = sorted({str(row.get("qualified_name")) for row in rows})[:5]
        raise RuntimeError(
            f"anchor validation failed for name {spec['name']!r}: manifest anchor "
            f"{spec['anchor']!r} not among candidates {found}")
    return min(matches, key=lambda row: str(row.get("id")))


def run_query_session_child(database: Path, queries: list, warmup_rounds: int,
                            measured_rounds: int, cache_state: str) -> dict:
    from provenlattice.query import GraphQuery

    per_type: dict = {}
    with GraphQuery(database) as query:
        resolved = [(spec, resolve_anchor(query, spec)) for spec in queries]
        for _ in range(warmup_rounds):
            for spec, anchor in resolved:
                execute_query(query, spec, anchor)
        for _ in range(measured_rounds):
            for spec, anchor in resolved:
                started = time.perf_counter()
                execute_query(query, spec, anchor)
                per_type.setdefault(spec["type"], []).append(
                    (time.perf_counter() - started) * 1000)

    def aggregate(values: list) -> dict:
        ordered = sorted(values)
        return {
            "median": r(statistics.median(values)),
            "p95": r(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]),
            "p99": r(ordered[max(0, math.ceil(len(ordered) * 0.99) - 1)]),
            "min": r(ordered[0]),
            "max": r(ordered[-1]),
            "n": len(values),
        }

    phase = {
        "cache_state": cache_state,
        "process_cold": True,
        "warmup_rounds": warmup_rounds,
        "measured_rounds": measured_rounds,
        "per_query_type": {k: aggregate(v) for k, v in sorted(per_type.items())},
        "raw_samples_ms": {k: [r(v) for v in values] for k, values in sorted(per_type.items())},
    }
    total = sum(sum(v) for v in per_type.values()) / 1000
    count = sum(len(v) for v in per_type.values())
    phase["throughput_qps"] = r(count / total) if total > 0 else 0.0
    return {"phases": [phase]}


def run_child_task(task: dict) -> dict:
    kind = task["task"]
    if kind == "build":
        return run_build_child(
            Path(task["repo"]), Path(task["database"]), task["shard_strategy"])
    if kind == "incremental":
        return run_incremental_child(
            Path(task["repo"]), Path(task["database"]), task["shard_strategy"],
            task.get("probe"))
    if kind == "query_session":
        return run_query_session_child(
            Path(task["database"]), task["queries"],
            int(task["warmup_rounds"]), int(task["measured_rounds"]),
            task["cache_state"])
    raise RuntimeError(f"unknown child task: {kind}")


def spawn_child(task: dict) -> dict:
    payload = json.dumps(task, ensure_ascii=False)
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--child-task", "-"],
        input=payload, capture_output=True, text=True, encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"child task {task.get('task')} failed (rc={completed.returncode}): "
            f"{(completed.stderr or '').strip()[-2000:]}")
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith(CHILD_MARKER):
            return json.loads(line[len(CHILD_MARKER):].strip())
    raise RuntimeError(f"child task {task.get('task')} produced no result marker")


# --------------------------------------------------------------------------
# workload orchestration (parent mode)
# --------------------------------------------------------------------------

def aggregate(values: list) -> dict:
    ordered = sorted(values)
    return {
        "median": r(statistics.median(values)),
        "p95": r(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]),
        "p99": r(ordered[max(0, math.ceil(len(ordered) * 0.99) - 1)]),
        "min": r(ordered[0]),
        "max": r(ordered[-1]),
        "n": len(values),
    }


def load_benchmark_manifest() -> dict:
    return json.loads((MANIFESTS_DIR / "benchmarks-v1.json").read_text(encoding="utf-8"))


def normalized_block(median: dict, counts: dict, c_cpp_loc: int) -> dict:
    """Non-LOC cost normalization (review R12). null = N/A (zero/unavailable
    denominator); raw denominators are always retained. No single LOC slope."""
    kloc = c_cpp_loc / 1000
    symbols = counts.get("symbols") or 0

    def ratio(numerator: float, denominator: float, digits: int = 6):
        return r(numerator / denominator, digits) if denominator else None

    return {
        "sec_per_kloc": ratio(median["wall_time_ms"] / 1000, kloc),
        "sec_per_1k_symbols": ratio(median["wall_time_ms"] / 1000, symbols / 1000),
        "mib_per_kloc": ratio(median["peak_rss_bytes"] / (1024 * 1024), kloc),
        "mib_per_1k_symbols": ratio(
            median["peak_rss_bytes"] / (1024 * 1024), symbols / 1000),
        "db_bytes_per_kloc": ratio(median["db_size_bytes"], kloc, 3),
        "db_bytes_per_node": ratio(median["db_size_bytes"], counts["nodes"], 3),
        "db_bytes_per_rawref": ratio(median["db_size_bytes"], counts["raw_references"], 3),
        "nodes_per_kloc": ratio(counts["nodes"], kloc, 3),
        "edges_per_kloc": ratio(counts["edges"], kloc, 3),
        "rawrefs_per_kloc": ratio(counts["raw_references"], kloc, 3),
        "edges_per_node": ratio(counts["edges"], counts["nodes"]),
        "cost_denominators": {
            "c_cpp_loc": c_cpp_loc,
            "files": counts["files_scanned"],
            "nodes": counts["nodes"],
            "symbols": symbols,
            "raw_references": counts["raw_references"],
            "edges": counts["edges"],
        },
    }


def baseline_crosscheck(counts: dict, median_wall_ms: float, observed: dict) -> dict:
    """Anomaly guard ONLY (review R8 / contract section 6): never a parity
    substitute and never a correctness claim."""
    checks = []
    for field in ("nodes", "edges", "raw_references"):
        baseline = int(observed[field])
        got = counts[field]
        checks.append({
            "field": field, "baseline": baseline, "observed": got,
            "within_band": abs(got - baseline) <= 0.10 * baseline,
        })
    return {
        "v0_2_full_index_time_ms": observed["full_index_time_ms"],
        "median_wall_time_ms": median_wall_ms,
        "wall_time_ratio": r(median_wall_ms / observed["full_index_time_ms"], 4),
        "counts_within_band": all(check["within_band"] for check in checks),
        "count_checks": checks,
        "interpretation": "ANOMALY_DETECTOR_NOT_PARITY_SUBSTITUTE",
    }


def copy_repo(source: Path, destination: Path) -> None:
    shutil.copytree(
        source, destination,
        ignore=shutil.ignore_patterns(".git", ".provenlattice"),
        dirs_exist_ok=True,
    )


def _expect_frozen(target: Path, op: dict) -> None:
    current = sha256_file(target)
    if current != op["expect_sha256"]:
        raise RuntimeError(
            f"frozen state mismatch for {op['file']}: expected {op['expect_sha256']}, "
            f"found {current}")


def file_state_hashes(database: Path, paths: list) -> dict:
    """file_state.source_hash rows read directly from an indexed DB."""
    out = {}
    with contextlib.closing(
            sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as connection:
        for path in paths:
            row = connection.execute(
                "SELECT source_hash FROM file_state WHERE path=?", (path,)).fetchone()
            out[path] = row[0] if row else None
    return out


def apply_mutations(repo: Path, family: dict) -> list:
    """Apply the frozen mutation family to a throwaway repository copy.

    Returns one record per op with pre/post SHA256 and an explicit anchor
    check, so the record proves the mutation verifiably happened (blocker
    WORKLOAD_C_MUTATION_ORDER: pre/post hash equality means no A->B delta
    exists and the rep is invalid).
    """
    ops = []
    for op in family["ops"]:
        target = repo / op["file"]
        if not target.exists():
            raise RuntimeError(f"mutation op target missing: {op['file']}")
        _expect_frozen(target, op)
        pre_sha256 = sha256_file(target)
        if op["type"] == "replace_first":
            text = target.read_text(encoding="utf-8", errors="surrogateescape")
            if op["find"] not in text:
                raise RuntimeError(f"mutation anchor not found in {op['file']}")
            target.write_text(
                text.replace(op["find"], op["replace"], 1),
                encoding="utf-8", errors="surrogateescape", newline="")
            anchor_changed = op["replace"] in target.read_text(
                encoding="utf-8", errors="surrogateescape")
        elif op["type"] == "append_text":
            with target.open("a", encoding="utf-8", errors="surrogateescape", newline="") as handle:
                handle.write(op["text"])
            anchor_changed = op["text"] in target.read_text(
                encoding="utf-8", errors="surrogateescape")
        elif op["type"] == "delete_file":
            target.unlink()
            anchor_changed = not target.exists()
        else:
            raise RuntimeError(f"unknown mutation op type: {op['type']}")
        post_sha256 = sha256_file(target) if target.exists() else None
        ops.append({
            "file": op["file"],
            "type": op["type"],
            "pre_sha256": pre_sha256,
            "post_sha256": post_sha256,
            "content_changed": post_sha256 != pre_sha256,
            "anchor_changed": bool(anchor_changed),
        })
    return ops


def workload_c_rep_gate(mutation_ops: list, incremental: dict,
                        input_db_built_before_mutation: bool,
                        expected_files_touched_min: int) -> dict:
    """Hard gate (blocker WORKLOAD_C_MUTATION_ORDER). A Workload C rep is
    valid only if: the frozen mutation verifiably changed the frozen inputs
    (pre-hash != post-hash and the expected anchor changed), the incremental
    input DB was built before the mutation was applied, the incremental run
    reports changed=true, and mutations that touch files report
    files_changed_reported >= 1. files_reparsed is intentionally NOT gated
    here: deletion families and future non-reparse invalidation paths may
    legitimately report zero reparses while still being valid increments."""
    checks = {
        "mutation_pre_hash_differs_from_post_hash": all(
            op["content_changed"] for op in mutation_ops),
        "incremental_changed_true": bool(incremental["changed"]),
        "mutation_anchor_changed": all(op["anchor_changed"] for op in mutation_ops),
        "incremental_input_db_built_before_mutation": bool(input_db_built_before_mutation),
        "files_changed_reported_min_met": (
            expected_files_touched_min == 0
            or int(incremental["files_changed_reported"]) >= 1),
    }
    gate = dict(checks)
    gate["expected_files_touched_min"] = expected_files_touched_min
    gate["files_changed_reported_observed"] = int(incremental["files_changed_reported"])
    gate["files_reparsed_observed"] = int(incremental["files_reparsed"])
    gate["changed_paths"] = incremental.get("changes")
    gate["passed"] = all(checks.values())
    return gate


CACHE_TERMINOLOGY = [
    "db-fresh: the output database path did not exist before the measured unit (asserted at runtime)",
    "process-cold: the measured unit runs in a freshly spawned child process; no application-level cache is inherited",
    "first-query: the first query round executed by a newly spawned query process",
    "warm-repeat: measured query rounds executed by the same query process after three warm-up rounds (SQLite page cache warm within that connection; GraphQuery holds no result cache)",
    "OS page cache uncontrolled: no privileged page-cache eviction was attempted (eviction_attempted=not_attempted)",
    "prior-run OS-cache-eligible: measured units follow prior build reps over the same source tree; OS file cache may be warm; state unobserved",
    "the terms 'cold filesystem cache' and 'true cold cache' are not valid V1 terms and are banned",
]


def cache_policy(workload: str) -> dict:
    states = {
        "A": ("uncontrolled",
              "no application/DB cache can persist across reps: fresh DB path plus a new process per rep"),
        "B": ("prior_run_cache_eligible",
              "no application/DB cache persists across reps (fresh DB path plus new process); prior build reps may have warmed the OS file cache over the same source tree; unobserved"),
        "C": ("prior_run_cache_eligible",
              "each rep reopens the SQLite DB in a new child process; the initial index within the rep may have warmed the OS file cache; unobserved"),
        "D": ("uncontrolled",
              "cold phase: new query process, first round; warm phase: same process after three warm-up rounds - GraphQuery holds no result cache, warmth comes from the SQLite connection page cache; no cache is inherited from the preceding cold child process"),
    }
    state, application_note = states[workload]
    return {
        "os_page_cache_state": state,
        "eviction_attempted": "not_attempted",
        "platform_privilege_note": (
            "no privileged page-cache eviction was attempted (Windows has no "
            "unprivileged eviction API; Linux drop_caches not used); OS page "
            "cache state is therefore uncontrolled, not 'cold'"),
        "application_cache_note": application_note,
        "terminology": CACHE_TERMINOLOGY,
    }


def load_schedule(path: Path, benchmark: str, workload: str, family: str | None) -> dict:
    schedule = json.loads(path.read_text(encoding="utf-8"))
    seq = None
    for entry in schedule["workload_sequence"]:
        if (entry["benchmark"] == benchmark and entry["workload"] == workload
                and entry.get("mutation_family") == family):
            seq = entry["seq"]
            break
    if seq is None:
        raise RuntimeError(
            f"combination benchmark={benchmark} workload={workload} "
            f"family={family} not found in frozen schedule {path.name}")
    return {
        "manifest": str(path.relative_to(SYSTEMS_V1)).replace("\\", "/"),
        "manifest_sha256": sha256_file(path),
        "order_policy": schedule["order_policy"],
        "schedule_seq": seq,
        "frozen_before_formal_run": True,
    }


def workload_build(workload: str, benchmark: dict, run_id: str, reps: int,
                   warmup: int, shard_strategy: str, workdir: Path) -> list:
    repo = (SYSTEMS_V1 / benchmark["repo_path"]).resolve()
    # Warm-up reps are labelled "warmup" and are excluded from aggregation for
    # BOTH A and B (review R5; the old code labelled all A reps "measured").
    roles = ["warmup"] * warmup + ["measured"] * reps
    raw_reps = []
    for index, role in enumerate(roles):
        database = workdir / f"{run_id}-rep-{index}.db"
        result = spawn_child({
            "task": "build", "repo": str(repo), "database": str(database),
            "shard_strategy": shard_strategy,
        })
        result["rep"] = index
        result["role"] = role
        raw_reps.append(result)
    return raw_reps


def workload_incremental(benchmark: dict, run_id: str, mutation_manifest_path: Path,
                         mutation_family: str, reps: int, shard_strategy: str,
                         workdir: Path) -> tuple:
    repo = (SYSTEMS_V1 / benchmark["repo_path"]).resolve()
    manifest = json.loads(mutation_manifest_path.read_text(encoding="utf-8"))
    families = {family["mutation_id"]: family for family in manifest["families"]}
    if mutation_family not in families:
        raise RuntimeError(
            f"mutation family {mutation_family} not in manifest (available: {sorted(families)})")
    family = families[mutation_family]
    probe_spec = family["freshness_probe"]
    mutation_target_paths = [op["file"] for op in family["ops"]]
    expected_files_touched_min = 1 if family["ops"] else 0

    run_started = time.perf_counter()
    raw_reps = []
    parity_all = True
    strict_all = True
    setup_times: list = []
    validation_times: list = []
    parity_verify_times: list = []
    for rep in range(reps):
        rep_root = workdir / f"rep-{rep}"
        copy_dir = rep_root / "repo"

        copy_started = time.perf_counter()
        copy_repo(repo, copy_dir)
        copy_ms = (time.perf_counter() - copy_started) * 1000

        # Step 1: initial index is built from UNMODIFIED frozen A. The frozen
        # mutation is applied only AFTER this build returns (blocker C1 fix).
        initial = spawn_child({
            "task": "build", "repo": str(copy_dir), "shard_strategy": shard_strategy,
            "database": str(rep_root / "incremental.db"),
        })
        initial["rep"] = rep
        initial["role"] = "initial_index"
        initial["built_at_utc"] = utc_now()
        initial_built_at = time.time()
        raw_reps.append(initial)

        # Step 2: verify baseline snapshot A - the input DB must carry the
        # frozen pre-mutation source hashes for every mutation target.
        verify_started = time.perf_counter()
        initial["baseline_digests"] = snapshot_digests(rep_root / "incremental.db")
        baseline_hashes = file_state_hashes(
            rep_root / "incremental.db", mutation_target_paths)
        initial["baseline_file_state_hashes"] = baseline_hashes
        initial["file_state_matches_frozen_a"] = all(
            baseline_hashes.get(op["file"]) == op["expect_sha256"]
            for op in family["ops"])
        if not initial["file_state_matches_frozen_a"]:
            raise RuntimeError(
                f"rep {rep}: incremental input DB does not reflect frozen state A "
                f"(file_state mismatch for mutation targets); aborting before mutation")
        baseline_verify_ms = (time.perf_counter() - verify_started) * 1000

        # Step 3: apply the frozen mutation A->B (pre/post hashes recorded).
        mutation_started = time.perf_counter()
        mutation_ops = apply_mutations(copy_dir, family)
        mutation_ms = (time.perf_counter() - mutation_started) * 1000
        mutation_applied_at_utc = utc_now()
        mutation_applied_at = time.time()
        setup_times.append(copy_ms + mutation_ms)

        # Step 4: incremental update A->B; the frozen freshness probe inside
        # the same child must observe the changed state B.
        incremental = spawn_child({
            "task": "incremental", "repo": str(copy_dir),
            "shard_strategy": shard_strategy, "probe": probe_spec,
            "database": str(rep_root / "incremental.db"),
        })

        incremental["rep"] = rep
        incremental["role"] = "incremental"
        incremental["mutation_ops"] = mutation_ops
        incremental["initial_db_built_at_utc"] = initial["built_at_utc"]
        incremental["mutation_applied_at_utc"] = mutation_applied_at_utc
        incremental["mutation_applied_after_initial_build_s"] = r(
            mutation_applied_at - initial_built_at, 6)
        incremental["workload_c_gate"] = workload_c_rep_gate(
            mutation_ops, incremental,
            initial["file_state_matches_frozen_a"]
            and mutation_applied_at >= initial_built_at,
            expected_files_touched_min)
        raw_reps.append(incremental)

        validation_times.append(
            baseline_verify_ms
            + incremental["freshness_probe"]["probe_latency_ms"] + incremental["digest_ms"])

        spawn_child({
            "task": "build", "repo": str(copy_dir), "shard_strategy": shard_strategy,
            "database": str(rep_root / "full.db"),
        })
        digest_started = time.perf_counter()
        parity_digests = snapshot_digests(rep_root / "full.db")
        parity_digest_ms = (time.perf_counter() - digest_started) * 1000
        parity_verify_times.append(incremental["digest_ms"] + parity_digest_ms)
        raw_reps.append({
            "rep": rep, "role": "parity_full",
            "digest_ms": r(parity_digest_ms, 3), "digests": parity_digests})

        facts_match = all(
            incremental["digests"][key] == parity_digests[key]
            for key in PARITY_FACT_KEYS)
        strict_match = all(
            incremental["digests"][key] == parity_digests[key]
            for key in PARITY_STRICT_KEYS)
        parity_all = parity_all and facts_match
        strict_all = strict_all and strict_match
        incremental["full_vs_incremental_parity"] = facts_match
        incremental["strict_digest_match"] = strict_match

    increments = [entry for entry in raw_reps if entry["role"] == "incremental"]
    probes = [entry["freshness_probe"] for entry in increments]
    probe_ok_all = all(probe["probe_ok"] for probe in probes)
    rep_gates = [entry["workload_c_gate"] for entry in increments]
    gate_meta = {
        "execution_order": "build_frozen_A_then_mutation_then_incremental_then_full_B",
        "expected_files_touched_min": expected_files_touched_min,
        "mutation_pre_hash_differs_from_post_hash": all(
            gate["mutation_pre_hash_differs_from_post_hash"] for gate in rep_gates),
        "incremental_changed_true": all(
            gate["incremental_changed_true"] for gate in rep_gates),
        "mutation_anchor_changed": all(
            gate["mutation_anchor_changed"] for gate in rep_gates),
        "incremental_input_db_built_before_mutation": all(
            gate["incremental_input_db_built_before_mutation"] for gate in rep_gates),
        "files_changed_reported_min_met": all(
            gate["files_changed_reported_min_met"] for gate in rep_gates),
        "per_rep": [
            {"rep": entry["rep"], **entry["workload_c_gate"]} for entry in increments],
        "passed": all(gate["passed"] for gate in rep_gates),
    }
    meta = {
        "mutation_family": family["family"],
        "mutation_id": family["mutation_id"],
        "mutation_scope": family.get("scope", "local"),
        "mutation_interface_sensitive": bool(family.get("interface_sensitive", False)),
        "reps": reps,
        "files_touched": sum(e["files_changed_reported"] for e in increments),
        "files_reparsed": sum(e["files_reparsed"] for e in increments),
        "files_reused": sum(e["files_reused"] for e in increments),
        "nodes_changed": sum(e["nodes_changed"] for e in increments),
        "edges_changed": sum(e["edges_changed"] for e in increments),
        "references_reprocessed": sum(e["references_reprocessed"] for e in increments),
        "references_reused": sum(e["references_reused"] for e in increments),
        "update_completion_latency_ms": r(
            statistics.median([e["wall_time_ms"] for e in increments])),
        "freshness_probe": {
            "probe_ok": probe_ok_all,
            "checks": probes[0]["checks"],
            "probe_latency_ms": r(
                statistics.median([p["probe_latency_ms"] for p in probes])),
            "query_visible_time_to_freshness_ms": r(
                statistics.median(
                    [p["query_visible_time_to_freshness_ms"] for p in probes])),
            "note": (
                "checks shown for rep 0; per-rep probe results are retained in "
                "raw_reps. Query-Visible Time-to-Freshness is measured as "
                "mutation applied -> incremental_update returns -> frozen probe "
                "observes expected changed graph state (same sequential child "
                "process; harness spawn overhead is reported separately in "
                "clocks.benchmark_setup_time_ms)."),
        },
        "full_vs_incremental_parity": parity_all,
        "workload_c_gate": gate_meta,
        "parity_gate": {
            "covered_states": PARITY_COVERED_STATES,
            "digest_fields": PARITY_FACT_KEYS,
            "not_covered_states": PARITY_NOT_COVERED_STATES,
            "strict_digest_match": strict_all,
            "strict_mismatch_disposition": "RECORDED_NON_GATING_PROVENANCE_DIVERGENCE",
        },
        "clocks": {
            "system_under_test_latency_ms": r(
                statistics.median([e["wall_time_ms"] for e in increments])),
            "benchmark_setup_time_ms": r(statistics.median(setup_times)),
            "validation_time_ms": r(statistics.median(validation_times)),
            "parity_verification_time_ms": r(statistics.median(parity_verify_times)),
            "end_to_end_benchmark_wall_time_ms": r((time.perf_counter() - run_started) * 1000),
            "boundary_note": (
                "system_under_test_latency_ms = median incremental_update child "
                "wall time only; benchmark_setup = repository copy plus frozen "
                "mutation application (initial A index and baseline verification "
                "are excluded from setup); validation = baseline A verification "
                "plus freshness probe plus snapshot digest computation; "
                "parity_verification = digest computation for both DBs; "
                "end_to_end includes all harness orchestration and is NOT a "
                "system latency. C-vs-A comparisons must use "
                "system_under_test_latency_ms only."),
        },
    }
    return raw_reps, meta


def workload_query(benchmark: dict, run_id: str, query_manifest_path: Path,
                   measured_rounds: int, shard_strategy: str, workdir: Path) -> tuple:
    manifest = json.loads(query_manifest_path.read_text(encoding="utf-8"))
    repo = (SYSTEMS_V1 / benchmark["repo_path"]).resolve()
    database = workdir / f"{run_id}-query.db"
    setup = spawn_child({
        "task": "build", "repo": str(repo), "shard_strategy": shard_strategy,
        "database": str(database),
    })
    setup["rep"] = 0
    setup["role"] = "setup"

    cold = spawn_child({
        "task": "query_session", "database": str(database),
        "queries": manifest["queries"], "warmup_rounds": 0,
        "measured_rounds": 1, "cache_state": "first_query",
    })
    warm = spawn_child({
        "task": "query_session", "database": str(database),
        "queries": manifest["queries"], "warmup_rounds": 3,
        "measured_rounds": measured_rounds, "cache_state": "warm_repeat",
    })

    raw_reps = [setup]
    for session in (cold, warm):
        phase = session["phases"][0]
        raw_reps.append({
            "rep": 0 if phase["cache_state"] == "first_query" else 1,
            "role": "query_first" if phase["cache_state"] == "first_query"
                    else "query_warm_repeat",
            **phase,
        })
    meta = {
        "query_set_sha256": sha256_file(query_manifest_path),
        "execution_order": "manifest_file_order",
        "order_frozen": True,
        "anchor_validation": "qualified_name_exact_match",
        "phases": cold["phases"] + warm["phases"],
    }
    return raw_reps, meta


# --------------------------------------------------------------------------
# run record assembly, validation, persistence
# --------------------------------------------------------------------------

def run_id_for(benchmark_id: str, workload: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"SYSV1-{benchmark_id.replace('-', '').upper()}-{workload}-{stamp}"


def build_record(args, benchmark: dict, raw_reps: list, workload_meta: dict,
                 workdir: Path) -> dict:
    repo = (SYSTEMS_V1 / benchmark["repo_path"]).resolve()
    head = repo_git_head(repo)
    effective = effective_config(args.shard_strategy)
    inputs = {
        "repo_path": str(repo),
        "commit_sha": head,
        "commit_matches_manifest": head == benchmark["commit_sha"],
        "c_cpp_loc": benchmark["c_cpp_loc"],
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "benchmark_manifest": "manifests/benchmarks-v1.json",
        "benchmark_manifest_sha256": sha256_file(MANIFESTS_DIR / "benchmarks-v1.json"),
        "schema_sha256": sha256_file(SCHEMA_PATH),
        "schedule_manifest": str(Path(args.schedule).relative_to(SYSTEMS_V1)).replace("\\", "/"),
        "schedule_manifest_sha256": sha256_file(Path(args.schedule)),
        "effective_config_sha256": sha256_text(canonical_json(effective)),
        "mutation_manifest": None,
        "mutation_manifest_sha256": None,
        "query_manifest": None,
        "query_manifest_sha256": None,
    }
    if getattr(args, "mutation_manifest", None):
        inputs["mutation_manifest"] = Path(args.mutation_manifest).as_posix()
        inputs["mutation_manifest_sha256"] = sha256_file(Path(args.mutation_manifest))
    if getattr(args, "query_manifest", None):
        inputs["query_manifest"] = Path(args.query_manifest).as_posix()
        inputs["query_manifest_sha256"] = sha256_file(Path(args.query_manifest))

    environment_record = environment()
    environment_record["load_note"] = args.load_note

    protocol = {
        "shard_strategy": args.shard_strategy,
        "effective_config": effective,
        "output_path_preexistence_asserted": True,
        "warmup": args.warmup,
        "reps": args.reps,
        "measured_rounds": args.measured_rounds if args.workload == "D" else None,
        "measurement_boundary": {
            "rss_scope": "main_measured_child_only",
            "cpu_scope": "main_measured_child_only",
            "rss_semantics": (
                "Windows: GetProcessMemoryInfo PeakWorkingSetSize of the main "
                "measured child process; POSIX: getrusage RUSAGE_SELF ru_maxrss. "
                "This is NOT process-tree memory and NOT total system memory "
                "consumption; parser descendants/grandchildren are not included."),
            "cpu_semantics": (
                "time.process_time() delta of the main measured child process "
                "only; NOT process-tree CPU time and NOT total system CPU time."),
        },
        "notes": [
            "child-process isolation per measured unit",
            "warm-up reps labelled role=warmup and excluded from all aggregates",
            "raw measurements retained verbatim; derived block is recomputable",
            f"workdir: {workdir.name}",
        ],
    }

    record = {
        "schema": "SYSTEMS_RUN_SCHEMA_V1",
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT_ID,
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "run_id": args.run_id,
        "run_kind": args.run_kind,
        "workload": args.workload,
        "benchmark": benchmark["benchmark"],
        "started_at_utc": args.started_at_utc,
        "completed_at_utc": utc_now(),
        "environment": environment_record,
        "inputs": inputs,
        "protocol": protocol,
        "cache_policy": cache_policy(args.workload),
        "schedule": load_schedule(
            Path(args.schedule), args.benchmark, args.workload,
            args.mutation_family if args.workload == "C" else None),
        "statistical_policy": {
            "primary_statistic": "median",
            "retained": ["min", "max"],
            "p95_interpretation": "DESCRIPTIVE_ONLY_FOR_SMALL_N",
            "p99_interpretation": "DESCRIPTIVE_ONLY_WITH_SAMPLE_COUNT",
            "tail_claim_allowed": False,
        },
        "raw_reps": raw_reps,
        "governance": {
            "evidence_level": "OBSERVED",
            "claim_scope": (
                "Windows 11, frozen benchmark commits, single machine, B1-B3 bands, "
                "ProvenLattice V0.2 implementation, SYSTEMS_BENCHMARK_CONTRACT_V1; "
                "no concurrency stress, no S3+ scale bands, no cross-version comparison"),
        },
    }

    if args.workload in ("A", "B"):
        measured = [entry for entry in raw_reps if entry["role"] == "measured"]
        derived = {}
        for field in ("wall_time_ms", "cpu_time_ms", "peak_rss_bytes", "db_size_bytes"):
            values = [float(e[field]) for e in measured if e.get(field) is not None]
            derived[field] = aggregate(values)
        median_rep = min(
            measured,
            key=lambda e: (abs(e["wall_time_ms"] - derived["wall_time_ms"]["median"]), e["rep"]))
        counts = median_rep["counts"]
        derived["normalized_median"] = normalized_block(
            {k: v["median"] for k, v in derived.items()}, counts, benchmark["c_cpp_loc"])
        record["derived"] = derived
        record["baseline_crosscheck"] = baseline_crosscheck(
            counts, derived["wall_time_ms"]["median"], benchmark["v0_2_observed"])
    elif args.workload == "C":
        record["incremental"] = workload_meta
    elif args.workload == "D":
        record["query"] = workload_meta

    if args.run_kind == "qualification":
        record["qualification_gates"] = qualification_gates(args)
    return record


def qualification_gates(args) -> dict:
    build_ok = args.workload not in ("A", "B") or args.reps >= MIN_BUILD_MEASURED_REPS
    c_ok = args.workload != "C" or args.reps >= MIN_WORKLOAD_C_REPS
    d_ok = args.workload != "D" or args.measured_rounds >= MIN_QUERY_WARM_ROUNDS
    gates = {
        "build_measured_reps_minimum_met": build_ok,
        "workload_c_reps_minimum_met": c_ok,
        "query_warm_rounds_minimum_met": d_ok,
        "schedule_frozen": True,
        "load_note_present": bool(args.load_note.strip()),
    }
    gates["passed"] = all(gates.values())
    return gates


REQUIRED_TOP = ["schema", "schema_version", "contract", "contract_sha256", "run_id",
                "run_kind", "workload", "benchmark", "started_at_utc", "completed_at_utc",
                "environment", "inputs", "protocol", "cache_policy", "schedule",
                "statistical_policy", "raw_reps", "governance"]


def schema_errors(instance: object, schema: dict, root: dict | None = None,
                  path: str = "$") -> list:
    """Minimal JSON Schema draft-07 subset validator (review R4).

    Supports the constructs used by SYSTEMS_RUN_SCHEMA_V1: type, const, enum,
    required, properties, additionalProperties, pattern, minimum, minItems,
    items, contains, $ref (local), allOf, if/then/else. The frozen schema file
    is the single source of truth; this validator never substitutes for it.
    """
    root = root or schema
    errors: list = []
    if "$ref" in schema:
        target = root
        for part in schema["$ref"][2:].split("/"):
            target = target[part]
        return schema_errors(instance, target, root, path)
    if "allOf" in schema:
        for sub in schema["allOf"]:
            errors.extend(schema_errors(instance, sub, root, path))
    if "if" in schema:
        condition_met = not schema_errors(instance, schema["if"], root, path)
        branch = schema.get("then") if condition_met else schema.get("else")
        if branch:
            errors.extend(schema_errors(instance, branch, root, path))
    expected_type = schema.get("type")
    if expected_type:
        types = [expected_type] if isinstance(expected_type, str) else list(expected_type)

        def type_ok(value: object, name: str) -> bool:
            if name == "object":
                return isinstance(value, dict)
            if name == "array":
                return isinstance(value, list)
            if name == "string":
                return isinstance(value, str)
            if name == "integer":
                return isinstance(value, int) and not isinstance(value, bool)
            if name == "number":
                return isinstance(value, (int, float)) and not isinstance(value, bool)
            if name == "boolean":
                return isinstance(value, bool)
            if name == "null":
                return value is None
            return True

        if not any(type_ok(instance, name) for name in types):
            errors.append(
                f"{path}: expected type {expected_type}, got {type(instance).__name__}")
            return errors
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']}")
    if "pattern" in schema and isinstance(instance, str) \
            and not re.search(schema["pattern"], instance):
        errors.append(f"{path}: {instance!r} does not match {schema['pattern']}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool) \
            and "minimum" in schema and instance < schema["minimum"]:
        errors.append(f"{path}: {instance} below minimum {schema['minimum']}")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        if additional is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}: additional property {key!r} not allowed")
        for key, value in instance.items():
            if key in properties:
                errors.extend(
                    schema_errors(value, properties[key], root, f"{path}.{key}"))
            elif isinstance(additional, dict):
                errors.extend(schema_errors(value, additional, root, f"{path}.{key}"))
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(
                f"{path}: needs >= {schema['minItems']} items, has {len(instance)}")
        if "items" in schema:
            for index, item in enumerate(instance):
                errors.extend(
                    schema_errors(item, schema["items"], root, f"{path}[{index}]"))
        if "contains" in schema and not any(
                not schema_errors(item, schema["contains"], root, f"{path}[{index}]")
                for index, item in enumerate(instance)):
            errors.append(f"{path}: no item matches the required 'contains' schema")
    return errors


def validate_record(record: dict) -> list:
    """Validate against the frozen JSON Schema file (review R4)."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return schema_errors(record, schema)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--benchmark", choices=("B1-aria2", "B2-brpc", "B3-rocksdb"))
    parser.add_argument("--workload", choices=("A", "B", "C", "D"))
    parser.add_argument("--mutation-manifest")
    parser.add_argument("--mutation-family")
    parser.add_argument("--query-manifest")
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--measured-rounds", type=int, default=30,
                        help="workload D warm-phase rounds")
    parser.add_argument("--shard-strategy", default="directory",
                        choices=("directory", "build-aware", "structural"))
    parser.add_argument("--run-kind", default="qualification", choices=("smoke", "qualification"))
    parser.add_argument("--load-note", default="",
                        help="operator-supplied load note (required for qualification)")
    parser.add_argument("--schedule", default=str(SCHEDULE_PATH))
    parser.add_argument("--output")
    parser.add_argument("--keep-workdir", action="store_true")
    parser.add_argument("--validate")
    parser.add_argument("--child-task", help="internal: '-' reads one JSON task from stdin")
    args = parser.parse_args(argv)

    if args.child_task is not None:
        payload = (sys.stdin.read() if args.child_task == "-"
                   else Path(args.child_task).read_text(encoding="utf-8"))
        result = run_child_task(json.loads(payload))
        print(CHILD_MARKER + json.dumps(result, ensure_ascii=False))
        return 0

    if args.validate:
        record = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_record(record)
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
        return 0 if not errors else 2

    if not (args.benchmark and args.workload):
        parser.error("--benchmark and --workload are required in parent mode")

    # Qualification minima are enforced by the runner itself, not just the
    # documentation (review R5). Smoke runs are exempt via run_kind=smoke.
    if args.run_kind == "qualification":
        if args.workload in ("A", "B") and args.reps < MIN_BUILD_MEASURED_REPS:
            parser.error(
                f"qualification workload {args.workload} requires >= "
                f"{MIN_BUILD_MEASURED_REPS} measured reps (got {args.reps})")
        if args.workload == "C" and args.reps < MIN_WORKLOAD_C_REPS:
            parser.error(
                f"qualification workload C requires >= {MIN_WORKLOAD_C_REPS} reps "
                f"per frozen mutation family (got {args.reps})")
        if args.workload == "D" and args.measured_rounds < MIN_QUERY_WARM_ROUNDS:
            parser.error(
                f"qualification workload D requires >= {MIN_QUERY_WARM_ROUNDS} "
                f"warm measured rounds (got {args.measured_rounds})")
        if not args.load_note.strip():
            parser.error("--load-note is required for qualification runs")

    args.started_at_utc = utc_now()
    args.run_id = run_id_for(args.benchmark, args.workload)
    manifest_doc = load_benchmark_manifest()
    benchmarks = {entry["benchmark"]: entry for entry in manifest_doc["benchmarks"]}
    benchmark = benchmarks[args.benchmark]
    repo = (SYSTEMS_V1 / benchmark["repo_path"]).resolve()

    workdir = Path(tempfile.mkdtemp(prefix=f"sysv1-{args.run_id}-"))
    failure = None
    raw_reps: list = []
    workload_meta: dict = {}
    try:
        if not (repo / ".git").exists():
            raise RuntimeError(f"benchmark repository missing .git: {repo}")
        head = repo_git_head(repo)
        if head != benchmark["commit_sha"]:
            raise RuntimeError(
                f"frozen commit mismatch for {args.benchmark}: manifest "
                f"{benchmark['commit_sha']} vs HEAD {head}")
        load_schedule(Path(args.schedule), args.benchmark, args.workload,
                      args.mutation_family if args.workload == "C" else None)
        if args.workload in ("A", "B"):
            raw_reps = workload_build(
                args.workload, benchmark, args.run_id, args.reps, args.warmup,
                args.shard_strategy, workdir)
        elif args.workload == "C":
            if not (args.mutation_manifest and args.mutation_family):
                raise RuntimeError("workload C requires --mutation-manifest and --mutation-family")
            raw_reps, workload_meta = workload_incremental(
                benchmark, args.run_id, Path(args.mutation_manifest), args.mutation_family,
                args.reps, args.shard_strategy, workdir)
            # Hard gate (blocker WORKLOAD_C_MUTATION_ORDER): a Workload C run
            # whose gate fails is never qualified evidence. The record is still
            # written (with infrastructure_failure) for the audit trail.
            if not workload_meta["workload_c_gate"]["passed"]:
                failed_checks = sorted(
                    key for key, value in workload_meta["workload_c_gate"].items()
                    if value is False)
                failure = {
                    "stage": "workload_c_hard_gate",
                    "detail": "WORKLOAD_C_MUTATION_ORDER gate failed: "
                              + ", ".join(failed_checks),
                }
        elif args.workload == "D":
            if not args.query_manifest:
                raise RuntimeError("workload D requires --query-manifest")
            raw_reps, workload_meta = workload_query(
                benchmark, args.run_id, Path(args.query_manifest),
                args.measured_rounds, args.shard_strategy, workdir)
    except Exception as error:  # recorded as INFRASTRUCTURE_FAILURE, per contract
        failure = {"stage": "workload_execution", "detail": f"{type(error).__name__}: {error}"}

    record = build_record(args, benchmark, raw_reps, workload_meta, workdir)
    if failure:
        record["infrastructure_failure"] = failure
    errors = validate_record(record)

    output = Path(args.output) if args.output else RESULTS_DIR / f"{args.run_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if errors:
        # Schema validation must PASS before an artifact is written (review R4).
        # Invalid records are written only to a .invalid.json diagnostic file.
        record["infrastructure_failure"] = record.get("infrastructure_failure") or {
            "stage": "record_validation", "detail": "; ".join(errors[:20])}
        output = output.with_suffix(".invalid.json")
        output.write_text(json.dumps(record, indent=2, ensure_ascii=False),
                          encoding="utf-8")
        if not args.keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
        print(json.dumps({
            "run_id": record["run_id"],
            "output": str(output),
            "valid": False,
            "errors": errors[:20],
            "infrastructure_failure": record.get("infrastructure_failure"),
        }, indent=2))
        return 2

    if args.keep_workdir:
        record["protocol"]["notes"].append(f"workdir kept: {workdir}")
    output.write_text(json.dumps(record, indent=2, ensure_ascii=False),
                      encoding="utf-8")
    if not args.keep_workdir:
        shutil.rmtree(workdir, ignore_errors=True)

    print(json.dumps({
        "run_id": record["run_id"],
        "output": str(output),
        "valid": True,
        "infrastructure_failure": record.get("infrastructure_failure"),
    }, indent=2))
    return 0 if not record.get("infrastructure_failure") else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Benchmark child: runs one index/update operation, prints one JSON line.

Usage: python bench_child.py <mode> <repo> <db> [touch_file]
Modes: full | incremental | delete
Peak RSS via GetProcessMemoryInfo (Windows Psapi).
"""
import ctypes
import json
import sys
import time
from ctypes import wintypes
from pathlib import Path

from provenlattice.graph import full_index
from provenlattice.incremental import incremental_update


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_rss_bytes() -> int:
    psapi = ctypes.WinDLL("Psapi.dll")
    kernel32 = ctypes.WinDLL("kernel32.dll")
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.argtypes = []
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(_PMC)
    if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        return int(pmc.PeakWorkingSetSize)
    return 0


def main() -> None:
    mode, repo, db = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    start = time.perf_counter()
    if mode == "full":
        result = full_index(repo, db)
    elif mode == "incremental":
        touch = Path(sys.argv[4])
        body = touch.read_text(encoding="utf-8")
        touch.write_text(body + "\n/* bench touch */\n", encoding="utf-8", newline="\n")
        result = incremental_update(repo, db)
    elif mode == "delete":
        victim = Path(sys.argv[4])
        victim.unlink()
        result = incremental_update(repo, db)
    else:
        raise SystemExit(f"unknown mode: {mode}")
    wall_ms = int((time.perf_counter() - start) * 1000)
    out = {
        "mode": mode,
        "wall_ms": wall_ms,
        "peak_rss_mb": round(peak_rss_bytes() / (1024 * 1024), 1),
        "graph_generation": result.get("graph_generation"),
        "metrics": {k: v for k, v in result["metrics"].items()
                    if isinstance(v, (int, float, str, bool))},
    }
    if "changes" in result:
        out["changes"] = result["changes"]
    print("RESULT_JSON:" + json.dumps(out))


if __name__ == "__main__":
    main()

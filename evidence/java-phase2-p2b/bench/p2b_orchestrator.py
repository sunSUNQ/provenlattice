"""P2-B orchestrator: measures a java child process (sampled peak RSS via
OpenProcess/GetProcessMemoryInfo polling, CPU via GetProcessTimes) and the
L1 python child (self-reported peak). Raw per-run JSON -> results/.

Usage:
  python p2b_orchestrator.py l1 <label> <repo> <runs>
  python p2b_orchestrator.py jdt <label> <repo> <runs> <mode:stats|full> [xmx] [extra_jars_semantic:...]
"""
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
RESULTS = HERE.parent / "results"
RESULTS.mkdir(exist_ok=True)
JDK = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\tools\jdk-path.txt").read_text().strip()
JARS = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\tools\jars")
P2B_CLASSES = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\p2b\classes")


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
    ]


psapi = ctypes.WinDLL("Psapi.dll")
kernel32 = ctypes.WinDLL("kernel32.dll")
psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                                     ctypes.POINTER(wintypes.FILETIME),
                                     ctypes.POINTER(wintypes.FILETIME),
                                     ctypes.POINTER(wintypes.FILETIME)]
kernel32.GetProcessTimes.restype = wintypes.BOOL


def sample_peak_rss_and_cpu(pid: int, proc: subprocess.Popen, interval: float = 0.1):
    """Poll child RSS while running; read cumulative CPU time at completion."""
    handle = kernel32.OpenProcess(0x1F0FFF, False, pid)  # PROCESS_ALL_ACCESS-ish
    peak = 0
    samples = 0
    start = time.perf_counter()
    while proc.poll() is None:
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        if handle and psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
            peak = max(peak, int(pmc.WorkingSetSize))  # instantaneous, sampled
        samples += 1
        time.sleep(interval)
    wall_ms = int((time.perf_counter() - start) * 1000)
    cpu_ms = 0
    if handle:
        ft = [wintypes.FILETIME() for _ in range(4)]
        if kernel32.GetProcessTimes(handle, *map(ctypes.byref, ft)):
            def to_100ns(f):
                return (f.dwHighDateTime << 32) | f.dwLowDateTime
            cpu_100ns = to_100ns(ft[2]) + to_100ns(ft[3])
            cpu_ms = int(cpu_100ns / 10_000)
        ctypes.windll.kernel32.CloseHandle(handle)
    return {"wall_ms": wall_ms, "sampled_peak_rss_mb": round(peak / 1048576, 1),
            "rss_samples": samples, "cpu_ms": cpu_ms}


def cpu_time_exact(pid: int) -> int:
    handle = kernel32.OpenProcess(0x1F0FFF, False, pid)
    if not handle:
        return 0
    ft = [wintypes.FILETIME() for _ in range(4)]
    ok = kernel32.GetProcessTimes(handle, *map(ctypes.byref, ft))
    ctypes.windll.kernel32.CloseHandle(handle)
    if not ok:
        return 0
    to = lambda f: (f.dwHighDateTime << 32) | f.dwLowDateTime
    return int((to(ft[2]) + to(ft[3])) / 10_000)  # ms


def run_java(repo: Path, mode: str, out_file: Path, xmx: str, cp: str = "") -> dict:
    cp_jars = ";".join(str(j) for j in JARS.glob("*.jar")) + ";" + str(P2B_CLASSES)
    if cp:
        cp_jars += ";" + cp
    cmd = [Path(JDK) / "bin" / "java.exe", f"-Xmx{xmx}", "-cp", cp_jars, "P2bDriver",
           str(repo), mode, str(out_file), cp]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    sampled = sample_peak_rss_and_cpu(proc.pid, proc)
    stdout, stderr = proc.communicate()
    result = {"cmd_xmx": xmx, "rc": proc.returncode, **sampled,
              "cpu_ms_exact": cpu_time_exact(proc.pid)}
    if proc.returncode != 0:
        result["error"] = stderr[-1200:]
    else:
        for line in stdout.splitlines():
            if line.startswith("P2B:"):
                result["summary"] = json.loads(line[4:])
    return result


def run_l1(repo: Path, db: Path) -> dict:
    child = REPO_ROOT / "evidence" / "java-overnight-longrun-v1" / "bench" / "bench_child.py"
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    proc = subprocess.Popen([sys.executable, str(child), "full", str(repo), str(db)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    sampled = sample_peak_rss_and_cpu(proc.pid, proc)
    stdout, stderr = proc.communicate()
    result = {"rc": proc.returncode, **sampled, "cpu_ms_exact": cpu_time_exact(proc.pid)}
    if proc.returncode != 0:
        result["error"] = stderr[-1200:]
    else:
        for line in stdout.splitlines():
            if line.startswith("RESULT_JSON:"):
                payload = json.loads(line[len("RESULT_JSON:"):])
                m = payload.get("metrics", {})
                result["metrics"] = {k: m.get(k) for k in (
                    "files_scanned", "nodes_created", "edges_created",
                    "resolved_references", "ambiguous_references",
                    "unresolved_references", "parse_failures", "index_time_ms")}
    return result


def main() -> None:
    mode = sys.argv[1]
    label = sys.argv[2]
    repo = Path(sys.argv[3]).resolve()
    runs = int(sys.argv[4])
    sub = {"mode": sys.argv[5] if len(sys.argv) > 5 else "stats"}
    xmx = sys.argv[6] if len(sys.argv) > 6 else "2g"
    cp_arg = sys.argv[7] if len(sys.argv) > 7 else ""
    out = {"label": label, "mode": mode, "repo": str(repo), "runs": [],
           "classpath": cp_arg or "(none)"}
    for i in range(runs):
        if mode == "l1":
            db = RESULTS / f"p2b-{label}-l1-{i}.db"
            for suffix in ("", "-wal", "-shm"):
                Path(str(db) + suffix).unlink(missing_ok=True)
            r = run_l1(repo, db)
            r["db_size_mb"] = round(db.stat().st_size / 1048576, 1) if db.exists() else 0
        else:
            detail = RESULTS / f"p2b-{label}-detail.jsonl"
            if detail.exists():
                detail.unlink()
            r = run_java(repo, sub["mode"], detail, xmx, cp_arg)
            r["xmx"] = xmx
            if detail.exists():
                r["detail_lines"] = sum(1 for _ in open(detail, encoding="utf-8"))
                target = RESULTS / f"p2b-{label}-detail-{i}.jsonl"
                if target.exists():
                    target.unlink()
                detail.rename(target)
            r["run"] = i
        out["runs"].append(r)
        print(json.dumps({k: v for k, v in r.items() if k != "summary"}))
    (RESULTS / f"p2b-{mode}-{label}{'-' + xmx if mode == 'jdt' else ''}-raw.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

"""T9-A benchmark orchestrator: cold x3, warm x3, incremental x3, delete x1.

Raw results (no aggregation) -> bench-raw-<label>.json
Stats (median/min/max) -> bench-stats-<label>.json
Repo manifest -> repos-manifest.json

Usage: python run_bench.py <label> <repo-path>
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHILD = Path(__file__).parent / "bench_child.py"
OUT_DIR = Path(__file__).parent
ENV = {"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": "", "SYSTEMROOT": "C:\\Windows"}
import os

ENV = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
TIMEOUT_S = 900


def run_child(mode: str, repo: Path, db: Path, arg: str | None = None) -> dict:
    cmd = [sys.executable, str(CHILD), mode, str(repo), str(db)]
    if arg:
        cmd.append(arg)
    start = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, env=ENV)
    orchestrator_overhead_ms = int((time.perf_counter() - start) * 1000)
    if proc.returncode != 0:
        return {"mode": mode, "error": proc.stderr[-2000:], "rc": proc.returncode,
                "orchestrator_overhead_ms": orchestrator_overhead_ms}
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT_JSON:"):
            payload = json.loads(line[len("RESULT_JSON:"):])
            payload["orchestrator_overhead_ms"] = orchestrator_overhead_ms
            return payload
    return {"mode": mode, "error": "no RESULT_JSON line", "stdout": proc.stdout[-500:]}


def stats(values: list[float]) -> dict:
    ordered = sorted(values)
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    return {"median": median, "min": min(values), "max": max(values),
            "spread": max(values) - min(values)}


def summarize(runs: list[dict], key: str) -> dict:
    ok = [r[key] for r in runs if key in r and not r.get("error")]
    return stats(ok) if ok else {"error": "no successful runs"}


def main() -> None:
    label, repo = sys.argv[1], Path(sys.argv[2])
    java_files = len(list(repo.rglob("*.java")))
    loc = sum(len(f.read_bytes()) for f in repo.rglob("*.java"))
    manifest = {"label": label, "repo_path": str(repo), "java_files": java_files,
                "java_bytes": loc}
    results = {"manifest": manifest, "runs": []}

    # warmup (1x, discarded)
    warm_db = OUT_DIR / f"warm-{label}.db"
    if warm_db.exists():
        warm_db.unlink()
    results["runs"].append({"phase": "warmup_discarded", **run_child("full", repo, warm_db)})
    warm_db.unlink(missing_ok=True)

    # cold x3 (fresh db each time; also delete the -wal/-shm siblings)
    for i in range(3):
        db = OUT_DIR / f"cold-{label}-{i}.db"
        for suffix in ("", "-wal", "-shm"):
            Path(str(db) + suffix).unlink(missing_ok=True)
        r = run_child("full", repo, db)
        r["phase"] = f"cold_{i}"
        r["db_size_bytes"] = db.stat().st_size if db.exists() else 0
        results["runs"].append(r)

    # warm x3 (db persists, full re-index in place)
    warm_run_db = OUT_DIR / f"warmrun-{label}.db"
    if warm_run_db.exists():
        warm_run_db.unlink()
    run_child("full", repo, warm_run_db)
    for i in range(3):
        r = run_child("full", repo, warm_run_db)
        r["phase"] = f"warm_{i}"
        r["db_size_bytes"] = warm_run_db.stat().st_size
        results["runs"].append(r)

    # incremental x3 (touch 3 different files)
    incr_db = OUT_DIR / f"incr-{label}.db"
    if incr_db.exists():
        incr_db.unlink()
    run_child("full", repo, incr_db)
    java_paths = sorted(repo.rglob("*.java"))
    stride = max(1, len(java_paths) // 50)
    victims = [java_paths[i * stride] for i in range(3)]
    for i, victim in enumerate(victims):
        r = run_child("incremental", repo, incr_db, str(victim))
        r["phase"] = f"incremental_{i}"
        r["touched_file"] = str(victim.relative_to(repo))
        r["db_size_bytes"] = incr_db.stat().st_size
        results["runs"].append(r)

    # delete x1 + convergence
    del_db = OUT_DIR / f"del-{label}.db"
    if del_db.exists():
        del_db.unlink()
    run_child("full", repo, del_db)
    del_victim = victims[0]
    r = run_child("delete", repo, del_db, str(del_victim))
    r["phase"] = "delete_0"
    r["deleted_file"] = str(del_victim.relative_to(repo))
    r["db_size_bytes"] = del_db.stat().st_size
    results["runs"].append(r)

    (OUT_DIR / f"bench-raw-{label}.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")

    # stats
    by_phase: dict[str, list[dict]] = {}
    for r in results["runs"]:
        by_phase.setdefault(r["phase"].rsplit("_", 1)[0], []).append(r)
    summary = {
        "manifest": manifest,
        "cold_wall_ms": summarize(by_phase.get("cold", []), "wall_ms"),
        "cold_peak_rss_mb": summarize(by_phase.get("cold", []), "peak_rss_mb"),
        "warm_wall_ms": summarize(by_phase.get("warm", []), "wall_ms"),
        "warm_peak_rss_mb": summarize(by_phase.get("warm", []), "peak_rss_mb"),
        "incremental_wall_ms": summarize(by_phase.get("incremental", []), "wall_ms"),
        "delete_wall_ms": summarize(by_phase.get("delete", []), "wall_ms"),
    }
    # resolution profile from the last cold run metrics
    cold_last = [r for r in by_phase.get("cold", []) if "metrics" in r]
    if cold_last:
        m = cold_last[-1]["metrics"]
        summary["reference_profile_last_cold"] = {
            k: m.get(k) for k in (
                "files_scanned", "files_parsed", "nodes_created", "edges_created",
                "raw_references", "resolved_references", "ambiguous_references",
                "unresolved_references", "parse_failures", "syntax_error_files",
                "index_time_ms", "shards_created")
        }
        summary["db_size_last_cold_bytes"] = cold_last[-1].get("db_size_bytes")
    (OUT_DIR / f"bench-stats-{label}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

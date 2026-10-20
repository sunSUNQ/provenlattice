"""Issue Pilot #5 prototype: persist JDT-merged Java call bindings into the
derived analysis layer, and measure latency / invalidation / byte stability.

Research scope (Issue Pilot #5, APPROVE_RESEARCH_ONLY):
- write path: per (repo, commit, file, contract) via AnalysisStore
- freshness: reuse base_hash + contract rules; the classpath fingerprint is
  part of the prototype contract so a JDT jar change invalidates rows
- non-goals: NO change to src/, L1 graphs, default index behavior, or the
  fail-closed semantics of the query-time analyzer.

Registry note: KNOWN_FEATURES has no "semantic" feature, so the prototype
registers the provisional slot `ast:java-jdt` at runtime (in-process only).
The default index never dispatches from the registry (hardcoded analyzers),
so a fresh `full_index` process is unaffected; asserted at runtime (M5).

Evidence level: prototype measurement (Windows-only, T9-B JDT jar set).
Not a product claim; productionization needs a real feature contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from provenlattice.analysis import (
    AnalysisNode, AnalysisStore, SQLiteStorage, register_analyzer,
)
from provenlattice.analysis_java_ast import JAVA_AST_CONTRACT
from provenlattice.graph import full_index
from provenlattice.identity import path_id
from provenlattice.java_semantic import merge_with_l1, run_jdt_analysis

PROVISIONAL_ANALYZER = "ast:java-jdt"
PROVISIONAL_VERSION = 1
CONTRACT_PREFIX = "java-ast-jdt-persist-v1"
CHUNK_BYTES_LIMIT = 2800
JDT_CP = ""


def classpath_fingerprint() -> str:
    digest = hashlib.sha256()
    for jar in sorted(Path(p) for p in JDT_CP.split(";") if p):
        digest.update(jar.name.encode("utf-8"))
        digest.update(b"\x1f")
        digest.update(str(jar.stat().st_size).encode("utf-8"))
        digest.update(b"\x1f")
    return digest.hexdigest()


def build_contract() -> str:
    return f"{CONTRACT_PREFIX}+{classpath_fingerprint()[:12]}"


def register() -> None:
    try:
        register_analyzer(PROVISIONAL_ANALYZER, PROVISIONAL_VERSION)
    except ValueError:
        pass


def chunk_rows(rows: list[dict]) -> list[list[dict]]:
    chunks, current, size = [], [], 2
    for row in rows:
        encoded = len(json.dumps(row, sort_keys=True, ensure_ascii=False)) + 1
        if current and size + encoded > CHUNK_BYTES_LIMIT:
            chunks.append(current)
            current, size = [], 2
        current.append(row)
        size += encoded
    if current:
        chunks.append(current)
    return chunks


def feature_row_counts(database: Path) -> dict[str, int]:
    import sqlite3
    from contextlib import closing

    if not database.exists():
        return {}
    with closing(sqlite3.connect(str(database))) as conn:
        try:
            return {feat: n for feat, n in conn.execute(
                "SELECT feature, COUNT(*) FROM analysis_nodes GROUP BY feature")}
        except sqlite3.OperationalError:
            return {}


def persist_repo(repo: Path, database: Path, contract: str,
                 manifest: str | None = None) -> dict:
    """Run the full pipeline once (index -> JDT -> merge -> persist)."""
    register()
    index_t0 = time.perf_counter()
    full_index(repo, database)
    index_wall = time.perf_counter() - index_t0

    jdt_t0 = time.perf_counter()
    result = run_jdt_analysis(repo, classpath_manifest=manifest)
    jdt_wall = time.perf_counter() - jdt_t0
    if result.status != "available":
        return {"status": result.status, "reason": result.reason,
                "jdt_wall_s": jdt_wall}

    merge_t0 = time.perf_counter()
    merged = merge_with_l1(result, database)
    merge_wall = time.perf_counter() - merge_t0

    by_file: dict[str, list[dict]] = {}
    for row in merged["sites"]:
        by_file.setdefault(row["file"], []).append(row)

    counts_before = feature_row_counts(database)
    write_t0 = time.perf_counter()
    files_written, nodes_written, payload_bytes = 0, 0, 0
    with SQLiteStorage(database) as storage:
        repo_id = storage.repository()["repo_id"]
        store = AnalysisStore(storage)
        for rel_path in sorted(by_file):
            file_id = path_id(repo_id, "File", rel_path)
            base_hash = store.base_source_hash(file_id)
            if base_hash is None:
                continue
            rows = sorted(by_file[rel_path],
                          key=lambda r: (r["line"], r["expr"], r["state"]))
            nodes = [AnalysisNode(
                "jn:" + hashlib.sha256("\x1f".join(
                    (file_id, "java-jdt-persist", str(i))).encode("utf-8")
                ).hexdigest(),
                "java_call_binding",
                {"chunk": i, "count": len(chunk), "rows": chunk})
                for i, chunk in enumerate(chunk_rows(rows))]
            encoded = sum(len(json.dumps(n.payload, sort_keys=True,
                                         ensure_ascii=False)) for n in nodes)
            store.replace_analysis_for_file(
                file_id, PROVISIONAL_ANALYZER, base_hash, PROVISIONAL_VERSION,
                nodes, [],
                metadata={"analyzer": PROVISIONAL_ANALYZER, "contract": contract,
                          "language": "java-jdt", "scope": "src",
                          "node_count": len(nodes), "edge_count": 0,
                          "row_count": len(rows), "payload_bytes": encoded,
                          "classpath_fingerprint": classpath_fingerprint(),
                          "dependencies": {"ast:java": JAVA_AST_CONTRACT}})
            files_written += 1
            nodes_written += len(nodes)
            payload_bytes += encoded
    persist_wall = time.perf_counter() - write_t0
    counts_after = feature_row_counts(database)
    return {
        "status": "available", "index_wall_s": round(index_wall, 3),
        "jdt_wall_s": round(jdt_wall, 3), "merge_wall_s": round(merge_wall, 3),
        "merge_counts": merged["counts"], "files_written": files_written,
        "nodes_written": nodes_written, "payload_bytes_total": payload_bytes,
        "persist_wall_s": round(persist_wall, 3),
        "l1_non_pollution": {
            "ast_java_rows_before": counts_before.get("ast:java", 0),
            "ast_java_rows_after": counts_after.get("ast:java", 0),
            "ast_jdt_rows_after": counts_after.get(PROVISIONAL_ANALYZER, 0),
            "pass": counts_before.get("ast:java", 0)
            == counts_after.get("ast:java", 0),
        },
    }


def measure_read_latency(database: Path, contract: str) -> dict:
    register()
    import sqlite3
    from contextlib import closing

    with SQLiteStorage(database) as storage:
        repo_id = storage.repository()["repo_id"]
        store = AnalysisStore(storage)
        with closing(sqlite3.connect(str(database))) as conn:
            paths = [r[0] for r in conn.execute(
                "SELECT DISTINCT f.path FROM files f JOIN analysis_state s "
                "ON s.file_id=f.file_id WHERE s.feature=?",
                (PROVISIONAL_ANALYZER,))]
        samples, misses = [], 0
        for rel_path in paths:
            file_id = path_id(repo_id, "File", rel_path)
            t0 = time.perf_counter()
            read = store.read_current_analysis(file_id, PROVISIONAL_ANALYZER)
            fresh = read is not None and read["fresh"] and read[
                "state"]["metadata"].get("contract") == contract
            samples.append((time.perf_counter() - t0) * 1000.0)
            misses += int(not fresh)
    samples.sort()

    def pct(p: float) -> float:
        return round(samples[min(len(samples) - 1, int(p * len(samples)))], 3)

    return {"n": len(samples), "avg_ms": round(sum(samples) / len(samples), 3),
            "p50_ms": pct(0.50), "p95_ms": pct(0.95), "max_ms": samples[-1],
            "fresh_or_contract_misses": misses}


def sha_file_payloads(database: Path) -> dict[str, str]:
    import sqlite3
    from contextlib import closing

    digests: dict[str, list[str]] = {}
    with closing(sqlite3.connect(str(database))) as conn:
        for path, payload in conn.execute(
            "SELECT f.path, n.payload FROM analysis_nodes n "
            "JOIN files f ON n.file_id=f.file_id WHERE n.feature=? "
            "ORDER BY f.path, n.analysis_node_id", (PROVISIONAL_ANALYZER,)):
            digests.setdefault(path, []).append(payload)
    return {p: hashlib.sha256("\n".join(v).encode("utf-8")).hexdigest()
            for p, v in digests.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("--db", required=True)
    parser.add_argument("--jdk", required=True)
    parser.add_argument("--jars", required=True, help="dir of JDT jars")
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--xmx", default="1g")
    parser.add_argument("--out", required=True)
    parser.add_argument("--selfcheck-failclosed", action="store_true")
    args = parser.parse_args()

    global JDT_CP
    jdk = str(Path(args.jdk).resolve())
    jars = Path(args.jars).resolve()
    JDT_CP = ";".join(str(p) for p in sorted(jars.glob("*.jar")))
    os.environ["PL_JAVA_JDK"] = jdk
    os.environ["PL_JAVA_JDT_CLASSPATH"] = JDT_CP
    os.environ["PL_JAVA_SEMANTIC_CACHE"] = str(
        Path(args.db).resolve().parent / "jdt-driver-cache")

    repo = Path(args.repo).resolve()
    database = Path(args.db).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).resolve().parent.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()

    if args.selfcheck_failclosed:
        os.environ.pop("PL_JAVA_JDT_CLASSPATH")
        result = run_jdt_analysis(repo)
        rows = feature_row_counts(database).get(PROVISIONAL_ANALYZER, 0)
        payload = {"fail_closed": {"status": result.status,
                                   "reason": result.reason,
                                   "rows_persisted": rows,
                                   "pass": result.status == "unavailable"
                                   and rows == 0}}
        Path(args.out).write_text(json.dumps(payload, indent=2),
                                  encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 0 if payload["fail_closed"]["pass"] else 1

    contract = build_contract()
    evidence = {"repo": repo.name, "commit": commit,
                "env": {"jdk": jdk, "jars_dir": str(jars), "xmx": args.xmx,
                        "manifest": args.manifest,
                        "jar_count": len(JDT_CP.split(";"))},
                "contract": contract,
                "evidence_level": "prototype-windows-only"}

    first = persist_repo(repo, database, contract, args.manifest)
    evidence["pipeline"] = first
    if first["status"] != "available":
        Path(args.out).write_text(json.dumps(evidence, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        print(json.dumps(evidence, indent=2, ensure_ascii=False))
        return 1

    evidence["read_latency"] = measure_read_latency(database, contract)

    db2 = database.with_name(database.stem + "-stability.db")
    if db2.exists():
        db2.unlink()
    persist_repo(repo, db2, contract, args.manifest)
    d1, d2 = sha_file_payloads(database), sha_file_payloads(db2)
    evidence["byte_stability"] = {
        "files_compared": len(d1),
        "identical_files": sum(1 for p in d1 if d1.get(p) == d2.get(p)),
        "pass": d1 == d2,
    }

    target = next((p for p in sorted(d1) if (repo / p).is_file()
                   and p.endswith(".java")), None)
    if target:
        src = repo / target
        original = src.read_text(encoding="utf-8")
        src.write_text(original + "\n// invalidation-probe\n",
                       encoding="utf-8", newline="\n")
        full_index(repo, database)
        inv_t0 = time.perf_counter()
        persist_repo(repo, database, contract, args.manifest)
        rebuild_wall = time.perf_counter() - inv_t0
        src.write_text(original, encoding="utf-8", newline="\n")
        full_index(repo, database)
        persist_repo(repo, database, contract, args.manifest)
        d3 = sha_file_payloads(database)
        evidence["invalidation"] = {
            "touched_file": target, "rebuild_wall_s": round(rebuild_wall, 3),
            "restored_byte_identical": d3 == d1,
        }

    fc_db = database.with_name(database.stem + "-failclosed.db")
    if fc_db.exists():
        fc_db.unlink()
    fc_out = database.parent / f"{repo.name}-failclosed.json"
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), str(repo),
         "--db", str(fc_db), "--jdk", jdk, "--jars", str(jars),
         "--out", str(fc_out), "--selfcheck-failclosed"],
        capture_output=True, text=True)
    try:
        evidence["fail_closed"] = json.loads(
            fc_out.read_text(encoding="utf-8"))["fail_closed"]
    except Exception:
        evidence["fail_closed"] = {"pass": False}

    Path(args.out).write_text(json.dumps(evidence, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

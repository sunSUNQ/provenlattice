"""P2-A/P2-D atomic integration evaluation on the fixed-SHA real repos.

T1: 8 historical wrong-binding sites (L1-only post-P2-A must NOT resolve
    them; JDT enabled must CORRECTLY bind; counts feed T4).
T3: per-repo L1-before (P7 frozen numbers) vs L1-after (tightened) vs
    L1-after + JDT (recovered_by_jdt counts).
T5-failure: JDK-missing / invalid classpath fail-closed probes.
"""
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from provenlattice import java_semantic as jsem
from provenlattice.graph import full_index
from provenlattice.classpath import build_classpath

OUT = Path("evidence/java-phase2-p2ad/results")
OUT.mkdir(parents=True, exist_ok=True)
REPOS = {
    "hikaricp": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\hikaricp"),
    "gson": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\gson"),
    "jgit": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\jgit"),
}
SITES = {
    "hikaricp": [
        ("HikariConfig.java", 318, "getPassword", "com.zaxxer.hikari.util.Credentials"),
        ("ClockSourceTest.java", 41, "toMillis", "java.util.concurrent.TimeUnit"),
        ("ConcurrentBag.java", 305, "stream", "java.util.Collection"),
        ("HikariConfig.java", 1029, "get", "java.lang.reflect.Field"),
    ],
    "gson": [
        ("JsonObject.java", 223, "get", "com.google.gson.internal.LinkedTreeMap"),
        ("MapTest.java", 95, "put", "java.util.Map"),
        ("NumberLimitsTest.java", 103, "repeat", "java.lang.String"),
        ("CollectionTest.java", 273, "add", "java.util.List"),
    ],
}

SLF4J = r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\tools\jars\slf4j-api.jar"


def db_stats(db: Path) -> dict:
    with closing(sqlite3.connect(db)) as c:
        c.row_factory = sqlite3.Row
        row = dict(c.execute(
            "SELECT COUNT(*) AS calls_total, "
            "SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) AS resolved, "
            "SUM(CASE WHEN status='ambiguous' THEN 1 ELSE 0 END) AS ambiguous, "
            "SUM(CASE WHEN status='unresolved' THEN 1 ELSE 0 END) AS unresolved "
            "FROM raw_references WHERE reference_type='CALLS'").fetchone())
    return row


def site_l1_status(db: Path, tail: str, line: int, expr: str) -> dict | None:
    with closing(sqlite3.connect(db)) as c:
        c.row_factory = sqlite3.Row
        rows = [dict(r) for r in c.execute(
            "SELECT r.status, r.resolution_strategy, r.confidence FROM raw_references r "
            "JOIN files f ON r.file_id=f.file_id "
            "WHERE f.path LIKE ? AND r.reference_type='CALLS' AND r.start_line=? "
            "AND r.raw_name LIKE ? ORDER BY r.id LIMIT 1",
            (f"%{tail}", line, f"%{expr}%"))]
    return rows[0] if rows else None


def main() -> None:
    label_filter = sys.argv[1] if len(sys.argv) > 1 else None
    report_path = OUT / f"p2ad-evaluation-{label_filter or 'all'}.json"
    report = {"t1_sites": [], "t3": {}, "t5_failures": {}}
    for label, repo in REPOS.items():
        if label_filter and label != label_filter:
            continue
        # jgit: merge_with_l1 is prototype-grade (per-site SQL) and would take
        # hours at 1.9k files -> stats mode (summary only), documented limit
        heavy = label == "jgit"
        db = repo / ".provenlattice" / "codegraph.db"
        for suffix in ("", "-wal", "-shm"):
            Path(str(db) + suffix).unlink(missing_ok=True)
        full_index(repo, db)
        stats = db_stats(db)
        stats["resolved_pct"] = round(100 * stats["resolved"] / max(1, stats["calls_total"]), 1)
        report["t3"][f"l1_tightened_{label}"] = stats

        contract = build_classpath(dependencies=[SLF4J]) if label == "hikaricp" else build_classpath()
        result = jsem.run_jdt_analysis(repo, mode="stats" if heavy else "full",
                                       timeout_s=1800)
        entry = {"jdt_status": result.status, "reason": result.reason,
                 "mode": "stats" if heavy else "full"}
        if result.status == "available":
            entry["summary"] = {k: result.summary.get(k) for k in (
                "files_parsed", "calls_resolved", "calls_recovered",
                "calls_ambiguous", "types_recovered")}
            if label == "hikaricp":
                # prototype-grade merge (per-site SQL) is run once on the small
                # repo as linked-delivery proof; larger repos record the limit
                merged = jsem.merge_with_l1(result, db)
                entry["merge_counts"] = merged["counts"]
                entry["demoted_recovered_by_jdt"] = merged["counts"].get("recovered_by_jdt", 0)
            elif not heavy:
                entry["merge_note"] = "merge skipped: prototype per-site SQL too slow at this scale (P2-E engineering item)"
        report["t3"][f"jdt_{label}"] = entry

        # T1: historical sites
        if label in SITES:
            for tail, line, expr, truth in SITES[label]:
                l1row = site_l1_status(db, tail, line, expr)
                jdt_binding = None
                if result.status == "available" and not heavy:
                    for b in result.bindings:
                        if b.file.endswith(tail) and b.line == line and b.expr == expr:
                            jdt_binding = {"decl": b.decl, "state": b.state}
                            break
                report["t1_sites"].append({
                    "repo": label, "site": f"{tail}:{line}", "call": expr,
                    "truth": truth,
                    "l1_tightened": l1row,
                    "jdt": jdt_binding,
                })

    # T5 failure probes (fail-closed evidence)
    import os
    real_jdk = os.environ.get("PL_JAVA_JDK")
    if real_jdk:
        del os.environ["PL_JAVA_JDK"]
    os.environ.pop("JAVA_HOME", None)
    path_bak = os.environ.get("PATH")
    os.environ["PATH"] = "C:\\nonexistent" if os.name == "nt" else "/nonexistent"
    try:
        probe = jsem.run_jdt_analysis(REPOS["hikaricp"], timeout_s=10)
        report["t5_failures"]["no_jdk"] = {"status": probe.status, "reason": probe.reason}
    finally:
        if path_bak is not None:
            os.environ["PATH"] = path_bak
        if real_jdk:
            os.environ["PL_JAVA_JDK"] = real_jdk
    bad = build_classpath(dependencies=[str(REPOS["hikaricp"] / "no-such.jar")])
    report["t5_failures"]["invalid_classpath"] = {
        "usable": bad.usable, "status": bad.status}

    (report_path).write_text(json.dumps(report, indent=2),
                                              encoding="utf-8")
    print(json.dumps({"t3": report["t3"], "t5": report["t5_failures"],
                      "t1_count": len(report["t1_sites"])}, indent=2))


if __name__ == "__main__":
    main()

"""P7 end-to-end verification on real repos via the existing CLI only.

Stages per repo: index -> symbol/callers/references/task-context ->
incremental (edit) -> delete -> update -> restore -> update -> consistency.
Also exports a fixed-seed sample of resolved CALLS rows for manual audit.

Usage: python p7_e2e.py <label> <repo-path>
"""
import json
import random
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

OUT = Path(__file__).parent
REPO_SRC = Path(__file__).resolve().parents[3] / "src"


def cli(*args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "provenlattice", *args],
        capture_output=True, text=True, timeout=1800,
        env={"PYTHONPATH": str(REPO_SRC), **__import__("os").environ},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"CLI failed: {args}\n{proc.stderr[-1500:]}")
    return json.loads(proc.stdout)


def sql(db: Path, query: str, params=()) -> list[dict]:
    with closing(sqlite3.connect(db)) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(query, params)]


def main() -> None:
    label, repo = sys.argv[1], Path(sys.argv[2]).resolve()
    db = repo / ".provenlattice" / "codegraph.db"
    report = {"label": label, "repo": str(repo), "stages": {}}

    # 1) index (fresh)
    for suffix in ("", "-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    m = cli("index", str(repo), "--json")["metrics"]
    report["stages"]["index"] = {
        "files_scanned": m["files_scanned"], "nodes": m["nodes_created"],
        "edges": m["edges_created"], "resolved": m["resolved_references"],
        "ambiguous": m["ambiguous_references"],
        "unresolved": m["unresolved_references"],
        "parse_failures": m["parse_failures"], "index_time_ms": m["index_time_ms"],
    }

    # 2) pick a well-known symbol by scanning the source tree
    import re

    java_files = sorted(repo.rglob("*.java"))
    anchor_file = next(f for f in java_files if f.stat().st_size > 3000)
    text = anchor_file.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"\b(?:class|interface|enum|record)\s+(\w+)", text)
    anchor = match.group(1) if match else anchor_file.stem
    sym = cli("symbol", anchor, "--database", str(db), "--json")
    report["stages"]["symbol_query"] = {
        "anchor": anchor, "anchor_file": str(anchor_file.relative_to(repo)),
        "returned": sym["returned_evidence_count"],
        "matched": [d.get("qualified_name") for d in sym["data"]][:3],
    }
    callers = cli("callers", anchor, "--database", str(db), "--json")
    callees = cli("callees", anchor, "--database", str(db), "--json")
    refs = cli("references", anchor, "--database", str(db), "--json")
    report["stages"]["graph_queries"] = {
        "callers": callers["returned_evidence_count"],
        "callees": callees["returned_evidence_count"],
        "references": refs["returned_evidence_count"],
    }
    task = cli("task-context", anchor, "--database", str(db), "--json")
    report["stages"]["task_context"] = {
        "status": task.get("status"),
        "bundle_status": task.get("bundle", {}).get("status") if isinstance(task.get("bundle"), dict) else None,
        "bytes": len(json.dumps(task)),
    }

    # 3) incremental edit
    victim = java_files[len(java_files) // 2]
    body = victim.read_text(encoding="utf-8")
    victim.write_text(body + "\n/* p7 touch */\n", encoding="utf-8", newline="\n")
    up = cli("update", str(repo), "--json")
    report["stages"]["incremental_edit"] = {
        "changed": up["changed"], "files_reparsed": up["metrics"]["files_reparsed"],
        "wall_ms": up["metrics"]["incremental_time_ms"],
    }

    # 4) delete + update + restore + update
    doomed = java_files[-1]
    doomed_body = doomed.read_text(encoding="utf-8")
    doomed.unlink()
    up2 = cli("update", str(repo), "--json")
    deleted_ok = doomed.relative_to(repo).as_posix() in up2["changes"]["deleted"]
    doomed.write_text(doomed_body, encoding="utf-8", newline="\n")
    up3 = cli("update", str(repo), "--json")
    report["stages"]["delete_readd"] = {
        "deleted": deleted_ok, "reparsed_after_readd": up3["metrics"]["files_reparsed"],
    }

    # 5) consistency: node count sanity + generation ledger
    gens = sql(db, "SELECT mode, COUNT(*) AS n FROM graph_generation GROUP BY mode")
    node_total = sql(db, "SELECT COUNT(*) AS n FROM nodes")[0]["n"]
    orphan_edges = sql(db, (
        "SELECT COUNT(*) AS n FROM edges e LEFT JOIN nodes s ON e.src_id = s.id "
        "LEFT JOIN nodes d ON e.dst_id = d.id WHERE s.id IS NULL OR d.id IS NULL"
    ))[0]["n"]
    report["stages"]["consistency"] = {
        "generations": gens, "nodes": node_total, "orphan_edges": orphan_edges,
    }

    # 6) fixed-seed sample of resolved CALLS for manual audit
    rows = sql(db, (
        "SELECT f.path, r.start_line, r.raw_name, n.qualified_name AS target, "
        "r.confidence FROM raw_references r JOIN nodes n "
        "ON r.resolved_symbol_id = n.id JOIN files f ON r.file_id = f.file_id "
        "WHERE r.reference_type = 'CALLS' AND r.status = 'resolved' ORDER BY r.id"
    ))
    sample = random.Random(42).sample(rows, min(30, len(rows)))
    audit = []
    for row in sample:
        src = (repo / row["path"]).read_text(encoding="utf-8", errors="replace")
        lines = src.splitlines()
        line_text = lines[row["start_line"] - 1].strip() if 0 < row["start_line"] <= len(lines) else ""
        audit.append({**row, "source_line": line_text[:120]})
    (OUT / f"p7-audit-{label}.json").write_text(
        json.dumps({"denominator": len(rows), "sample": audit}, indent=2),
        encoding="utf-8")
    report["stages"]["audit_sample"] = {
        "denominator_resolved_calls": len(rows), "sample_size": len(audit),
        "file": f"p7-audit-{label}.json",
    }

    (OUT / f"p7-e2e-{label}.json").write_text(json.dumps(report, indent=2),
                                              encoding="utf-8")
    print(json.dumps(report["stages"], indent=2))


if __name__ == "__main__":
    main()

"""P2-E Phase 2: extract all conflict_conservative sites for manual audit."""
import json
from pathlib import Path

from provenlattice import java_semantic as jsem
from provenlattice.java_semantic import SemanticResult, SemanticBinding

RESULTS = Path("evidence/java-phase2-p2e/results")
OUT = {}

for label in ("hikaricp", "gson", "jgit"):
    merge = json.loads((RESULTS / f"p2e-merge-{label}.json").read_text(encoding="utf-8"))
    detail = RESULTS / f"p2e-{label}-full-detail.jsonl"
    detail_rows = {}
    for line in detail.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("{"):
            continue
        r = json.loads(line)
        if r.get("kind") == "call" and "file" in r:
            detail_rows.setdefault((r["file"], r["line"], r["expr"].split(".")[-1]), r)
    # rebuild merge to access sites (recompute is cheap and deterministic)
    bindings = [SemanticBinding(file=r["file"], line=r["line"], expr=r["expr"],
                                decl=r.get("decl"),
                                state="recovered_filtered" if r.get("recovered")
                                else ("ambiguous" if not r.get("decl") else "resolved"),
                                signature=r.get("signature"))
                for r in detail_rows.values()]
    # recover the full detail rows for l1 lists: rerun merge with a DB read
    import sqlite3
    from contextlib import closing
    db = {"hikaricp": r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\hikaricp\.provenlattice\codegraph.db",
          "gson": r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\gson\.provenlattice\codegraph.db",
          "jgit": r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\jgit\.provenlattice\codegraph.db"}[label]
    bulk = {}
    with closing(sqlite3.connect(db)) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            "SELECT f.path AS file, r.start_line AS line, r.raw_name, r.status, "
            "r.resolution_strategy, r.confidence, n.qualified_name AS target "
            "FROM raw_references r JOIN nodes n ON r.resolved_symbol_id=n.id "
            "JOIN files f ON r.file_id=f.file_id WHERE r.reference_type='CALLS'"):
            bulk.setdefault((row["file"], row["line"]), []).append(dict(row))
    conflicts = []
    for (file, line, root), b in detail_rows.items():
        jdt_state = ("recovered_filtered" if b.get("recovered")
                     else ("ambiguous" if not b.get("decl") else "resolved"))
        if jdt_state != "resolved":
            continue
        l1rows = [r for r in bulk.get((file, line), [])
                  if r["raw_name"].lower().endswith(root.lower())]
        l1_resolved = [r for r in l1rows if r["status"] == "resolved"]
        if not l1_resolved:
            continue
        agree = any(
            (r["target"] or "").split(".")[0] == (b.get("decl") or "").split(".")[0]
            or (b.get("decl") or "").startswith((r["target"] or "").split("(")[0])
            for r in l1_resolved)
        if agree:
            continue
        conflicts.append({
            "file": file, "line": line, "call": root,
            "jdt_decl": b.get("decl"),
            "l1": [{k: r[k] for k in ("raw_name", "target", "resolution_strategy",
                                      "confidence")} for r in l1_resolved],
        })
    OUT[label] = {"total_conflicts": len(conflicts), "sites": conflicts}
    print(label, "conflicts:", len(conflicts))

(RESULTS / "conflict-sites.json").write_text(json.dumps(OUT, indent=2), encoding="utf-8")

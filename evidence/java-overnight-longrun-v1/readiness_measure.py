"""Phase-2 readiness measurement: ladder-tier distribution of resolved CALLS
and per-audit-item strategy evidence, straight from the P7 verification DBs."""
import json
from contextlib import closing
from pathlib import Path

import sqlite3

REPOS = {
    "hikaricp": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\hikaricp\.provenlattice\codegraph.db"),
    "gson": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\gson\.provenlattice\codegraph.db"),
}

AUDIT = {
    "hikaricp": [
        ("ClockSourceTest.java", "MINUTES.toMillis"),
        ("HikariConfig.java:318", "current.getPassword"),
        ("ConcurrentBag.java", "sharedList.stream"),
        ("HikariConfig.java:1029", "field.get"),
    ],
    "gson": [
        ("JsonObject.java:223", "members.get"),
        ("MapTest.java:95", "map.put"),
        ("NumberLimitsTest.java:103", "\"1\".repeat"),
        ("CollectionTest.java:273", "target.add"),
    ],
}

out = {}
for label, db in REPOS.items():
    with closing(sqlite3.connect(db)) as c:
        c.row_factory = sqlite3.Row
        tiers = [dict(r) for r in c.execute(
            "SELECT resolution_strategy AS strategy, confidence, COUNT(*) AS n "
            "FROM raw_references WHERE reference_type='CALLS' AND status='resolved' "
            "GROUP BY resolution_strategy, confidence ORDER BY n DESC")]
        total = sum(t["n"] for t in tiers)
        heuristic = sum(t["n"] for t in tiers if t["confidence"] < 0.99)
        exact = total - heuristic
        # audit item evidence
        audit_rows = []
        for where, call in AUDIT[label]:
            rows = [dict(r) for r in c.execute(
                "SELECT f.path AS file, r.start_line, r.raw_name, r.status, "
                "r.resolution_strategy, r.confidence, n.qualified_name AS target "
                "FROM raw_references r JOIN nodes n ON r.resolved_symbol_id=n.id "
                "JOIN files f ON r.file_id=f.file_id "
                "WHERE r.reference_type='CALLS' AND r.status='resolved' AND r.raw_name LIKE ? "
                "LIMIT 40", (f"%{call.split('.')[-1]}%",))]
            match = [r for r in rows if call.split(".")[-1] in r["raw_name"]]
            audit_rows.append({"audit_call": call, "rows": match[:6]})
    out[label] = {
        "resolved_calls_total": total,
        "exact_tier (conf>=0.99)": exact,
        "heuristic_tier (conf<0.99)": heuristic,
        "heuristic_share_pct": round(100 * heuristic / total, 1),
        "tiers": tiers,
        "audit_item_evidence": audit_rows,
    }
out_path = Path("evidence/java-overnight-longrun-v1/readiness-ladder-measurement.json")
out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
for label, d in out.items():
    print(f"== {label}: total={d['resolved_calls_total']} exact={d['exact_tier (conf>=0.99)']} "
          f"heuristic={d['heuristic_tier (conf<0.99)']} ({d['heuristic_share_pct']}%)")
    for t in d["tiers"]:
        print("   ", t["strategy"], t["confidence"], t["n"])

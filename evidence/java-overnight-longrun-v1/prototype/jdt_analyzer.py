"""P5 prototype: optional JDT semantic binding vs L1 baseline on the shared fixture.

Fail-closed rules:
- recovered=true bindings are downgraded to UNRESOLVED (never exposed as resolved)
- files with compile problems still contribute non-recovered bindings (JDT is
  error-tolerant); ambiguity (resolved=null) stays AMBIGUOUS
- L1 graph is read-only here; nothing in this prototype writes the L1 db

Usage: python jdt_analyzer.py <fixture> <jdt_raw_txt> <out_json>
"""
import json
import subprocess
import sys
from contextlib import closing
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
JDK = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\tools\jdk-path.txt")
JARS = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\tools\jars")

# gold query points: (id, file, line, kind, expect, target)
QUERIES = [
    ("Q01", "com/x/app/Overloads.java", 6, "call", "CORRECT", "com.x.app.Overloads.build(int)"),
    ("Q02", "com/x/app/Overloads.java", 7, "call", "CORRECT", "com.x.app.Overloads.build(java.lang.String)"),
    ("Q03", "com/x/app/Overloads.java", 8, "call", "CORRECT", "com.x.app.Overloads.build(int,java.lang.String)"),
    ("Q04", "com/x/app/App.java", 5, "call", "CORRECT", "com.x.core.Helper.build(int)"),
    ("Q05", "com/x/app/App.java", 6, "call", "CORRECT", "com.x.core.Helper.build(int)"),
    ("Q06", "com/x/app/App.java", 7, "new", "CORRECT", "com.x.core.Helper"),
    ("Q07", "com/x/app/App.java", 7, "call", "CORRECT", "com.x.core.Helper.run()"),
    ("Q08", "com/x/app/App.java", 8, "type", "CORRECT", "com.x.core.Runner"),
    ("Q09", "com/x/app/App.java", 8, "new", "CORRECT", "com.x.core.Runner"),
    ("Q10", "com/x/app/Wild.java", 4, "type", "CORRECT", "com.x.util.Helper"),
    ("Q11", "com/x/app/Wild.java", 5, "type", "CORRECT", "com.x.util.Runner"),
    ("Q12", "com/x/app/Generic.java", 4, "type", "CORRECT", "java.util.List"),
    ("Q13", "com/x/app/Generic.java", 5, "new", "CORRECT", "com.x.app.Box"),
    ("Q14", "com/x/app/UseExternal.java", 4, "type", "CORRECT", "java.util.HashMap"),
    ("Q15", "com/x/app/UseExternal.java", 5, "type", "UNRESOLVED_OK", None),
    ("Q16", "com/x/core/Runner.java", 2, "extends", "CORRECT", "com.x.core.Base"),
    ("Q17", "com/x/core/Runner.java", 2, "implements", "CORRECT", "com.x.core.Shape"),
    ("Q18", "com/x/core/Runner.java", 4, "call", "CORRECT", "com.x.core.Base.calc(int)"),
    ("Q19", "com/x/app/Broken.java", 2, "class", "SYNTAX_RECOVERY", "com.x.app.Broken"),
    ("Q20", "com/x/app/Wild2.java", 5, "type", "AMBIGUOUS", "com.x.core.Helper|com.x.util.Helper"),
    ("Q21", "com/x/app/Wild2.java", 6, "type", "AMBIGUOUS", "com.x.core.Runner|com.x.util.Runner"),
]


def norm_jdt_target(kind, row):
    if row.get("recovered"):
        return None, "RECOVERED_FILTERED"
    resolved = row.get("resolved")
    if not resolved:
        return None, "AMBIGUOUS"
    sig = row.get("signature")
    base = resolved.split("<")[0]
    if kind == "call" and sig:
        # JDT signature carries the method name: "build(int,)"; normalize the
        # JDT trailing comma before ")" to match gold spelling.
        return f"{base}.{sig.replace(' ', '').replace(',)', ')')}", "CORRECT"
    return base, "CORRECT"


def l1_side(fixture: Path, workdir: Path) -> dict:
    """Index the fixture with L1 and return raw_references keyed by (file, line)."""
    from provenlattice.graph import full_index

    db = workdir / "l1.db"
    if db.exists():
        db.unlink()
    full_index(fixture, db)
    rows = {}
    sql = (
        "SELECT f.path AS file, r.raw_name, r.reference_type, r.status, "
        "r.resolution_strategy, r.confidence, n.kind AS target_kind, "
        "n.qualified_name AS target_qname, r.start_line "
        "FROM raw_references r LEFT JOIN nodes n ON r.resolved_symbol_id = n.id "
        "JOIN files f ON r.file_id = f.file_id"
    )
    with closing(__import__("sqlite3").connect(db)) as conn:
        conn.row_factory = __import__("sqlite3").Row
        for r in conn.execute(sql):
            rows.setdefault((r["file"].replace("\\", "/"), r["start_line"]), []).append(dict(r))
    return rows


def main() -> None:
    fixture = Path(sys.argv[1]).resolve()
    jdt_raw = Path(sys.argv[2])
    out = Path(sys.argv[3])
    workdir = out.parent / "proto-work"
    workdir.mkdir(exist_ok=True)

    # parse JDT raw (strip JDT_JSON: prefix on first line)
    jdt_rows = []
    for line in jdt_raw.read_text(encoding="utf-8").splitlines():
        if line.startswith("JDT_JSON:"):
            line = line[len("JDT_JSON:"):]
        if line.strip().startswith("{"):
            jdt_rows.append(json.loads(line))
    by_key = {}
    for r in jdt_rows:
        if r.get("kind") in {"call", "type", "new", "extends", "implements", "class"}:
            by_key.setdefault((r.get("file"), r.get("line"), r.get("kind")), []).append(r)

    l1_refs = l1_side(fixture, workdir)

    report = {"queries": [], "summary": {}}
    counts = {"l1_ambiguous_improvable": 0, "l1_unresolved_improvable": 0,
              "jdt_correct": 0, "jdt_wrong": 0, "recovered_filtered": 0,
              "l1_wrong": 0}
    for qid, file, line, kind, expect, target in QUERIES:
        # JDT driver rows: extends/implements evidence lives in "type" rows
        # (SimpleType on the declaration line); class recovery in "class" rows
        jdt_kind = {"extends": "type", "implements": "type"}.get(kind, kind)
        # extends/implements/class rows carry no line in the JDT output
        jdt_key_candidates = [(file, line, jdt_kind)] if kind in {"call", "type", "new"} else [
            (f, l, k) for (f, l, k) in by_key if f == file and k == jdt_kind
        ]
        jdt_rows_for_query = [row for k in jdt_key_candidates for row in by_key.get(k, [])]
        if kind in {"extends", "implements"} and jdt_rows_for_query:
            # same-line disambiguation: match the row whose expr equals the
            # gold simple name (e.g. Shape for "implements Shape")
            want = (target or "").rsplit(".", 1)[-1]
            named = [row for row in jdt_rows_for_query if row.get("expr") == want]
            jdt_rows_for_query = named or jdt_rows_for_query
        jdt = jdt_rows_for_query[0] if jdt_rows_for_query else {}
        jdt_target, jdt_status = None, "NOT_RUN"
        if jdt:
            jdt_target, jdt_status = norm_jdt_target(jdt_kind, jdt)
        if expect == "SYNTAX_RECOVERY":
            recovered_class = any(
                r.get("kind") == "class" and r.get("expr") in (target or "").rsplit(".", 1)[-1]
                for r in jdt_rows if r.get("file") == file)
            jdt_status = "CORRECT" if recovered_class else "WRONG"
            counts["jdt_correct" if recovered_class else "jdt_wrong"] += 1
        elif jdt_status == "RECOVERED_FILTERED":
            counts["recovered_filtered"] += 1
        elif expect == "CORRECT" and jdt_target == target:
            jdt_status = "CORRECT"
            counts["jdt_correct"] += 1
        elif expect in {"AMBIGUOUS", "UNRESOLVED_OK"} and jdt_target is None:
            jdt_status = "CORRECT"
            counts["jdt_correct"] += 1
        elif jdt:
            jdt_status = "WRONG"
            counts["jdt_wrong"] += 1
        l1rows = l1_refs.get((file, line), [])
        l1_status = "NO_REF"
        l1_detail = []
        improvable = False
        gold_alternatives = [a for a in (target or "").split("|") if a]
        for r in l1rows:
            l1_detail.append({k: r[k] for k in (
                "raw_name", "reference_type", "status", "resolution_strategy",
                "confidence", "target_kind", "target_qname")})
            if r["status"] == "ambiguous":
                l1_status = "AMBIGUOUS"
                if expect == "CORRECT":
                    improvable = True
            elif r["status"] == "unresolved":
                if l1_status != "RESOLVED":
                    l1_status = "UNRESOLVED"
                if expect == "CORRECT":
                    improvable = True
            elif r["status"] == "resolved":
                l1_status = "RESOLVED"
        if improvable and l1_status == "AMBIGUOUS":
            counts["l1_ambiguous_improvable"] += 1
        if improvable and l1_status == "UNRESOLVED":
            counts["l1_unresolved_improvable"] += 1
        report["queries"].append({
            "id": qid, "file": file, "line": line, "kind": kind,
            "expect": expect, "gold_target": target,
            "l1": {"status": l1_status, "refs": l1_detail},
            "jdt": {"binding": jdt_target, "status": jdt_status,
                    "raw": jdt if jdt else None},
        })
    # line-level wrong-resolution audit: a resolved L1 reference on a gold
    # line must match one of that line's gold targets (method-node qualified
    # names carry no signature, hence the "target(" prefix rule)
    line_gold: dict = {}
    for qid, file, line, kind, expect, target in QUERIES:
        if expect == "CORRECT":
            line_gold.setdefault((file, line), set()).update(
                a for a in (target or "").split("|") if a)
    for (file, line), rows in l1_refs.items():
        golds = line_gold.get((file, line))
        if not golds:
            continue
        for r in rows:
            if r["status"] == "resolved":
                tq = r["target_qname"] or ""
                ok = any(g == tq or g.startswith(tq + "(") or g.startswith(tq + ".")
                         for g in golds)
                if not ok:
                    counts["l1_wrong"] += 1
    report["summary"] = {**counts, "queries": len(QUERIES)}
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()

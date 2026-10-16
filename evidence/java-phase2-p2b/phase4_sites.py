"""Phase 4: verify the 8 historical wrong-binding call sites under JDT.
Extracts per-line bindings from the full-mode detail JSONL files."""
import json
from pathlib import Path

R = Path("evidence/java-phase2-p2b/results")

SITES = {
    "hikaricp": [
        {"id": 2, "file_tail": "HikariConfig.java", "line": 318, "call": "getPassword",
         "truth": "com.zaxxer.hikari.util.Credentials.getPassword"},
        {"id": 1, "file_tail": "ClockSourceTest.java", "line": 41, "call": "toMillis",
         "truth": "java.util.concurrent.TimeUnit.toMillis"},
        {"id": 3, "file_tail": "ConcurrentBag.java", "line": 305, "call": "stream",
         "truth": "java.util.List.stream"},
        {"id": 4, "file_tail": "HikariConfig.java", "line": 1029, "call": "get",
         "truth": "java.lang.reflect.Field.get"},
    ],
    "gson": [
        {"id": 5, "file_tail": "JsonObject.java", "line": 223, "call": "get",
         "truth": "com.google.gson.internal.LinkedTreeMap.get"},
        {"id": 6, "file_tail": "MapTest.java", "line": 95, "call": "put",
         "truth": "java.util.Map.put (or implementing class)"},
        {"id": 7, "file_tail": "NumberLimitsTest.java", "line": 103, "call": "repeat",
         "truth": "java.lang.String.repeat"},
        {"id": 8, "file_tail": "CollectionTest.java", "line": 273, "call": "add",
         "truth": "java.util.List.add (or implementing class)"},
    ],
}

verdicts = []
for label, sites in SITES.items():
    detail = R / f"p2b-{label}-full-detail-0.jsonl"
    rows = {}
    for line in detail.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("{"):
            continue
        r = json.loads(line)
        if "file" not in r:
            continue  # summary row
        rows.setdefault((r["file"].rsplit("/", 1)[-1], r["line"]), []).append(r)
    for site in sites:
        matches = rows.get((site["file_tail"], site["line"]), [])
        calls = [m for m in matches if m["kind"] == "call" and m["expr"] == site["call"]]
        entry = {"id": site["id"], "repo": label, "site": f"{site['file_tail']}:{site['line']}",
                 "call": site["call"], "truth": site["truth"], "jdt": calls or None}
        if calls:
            b = calls[0]
            if b.get("recovered"):
                entry["verdict"] = "RECOVERED_FILTERED (would be ambiguous/unresolved)"
            elif b["decl"] and site["truth"].startswith(b["decl"].split("<")[0]):
                entry["verdict"] = "CORRECT"
            elif site["truth"].split("(")[0].endswith(b["decl"]) or b["decl"] in site["truth"]:
                entry["verdict"] = "CORRECT"
            else:
                entry["verdict"] = f"CHECK: bound to {b['decl']}"
        else:
            entry["verdict"] = "SITE-NOT-MATCHED (verify manually)"
        verdicts.append(entry)
        print(json.dumps(entry, ensure_ascii=False))

(R / "phase4-historical-sites.json").write_text(
    json.dumps(verdicts, indent=2, ensure_ascii=False), encoding="utf-8")

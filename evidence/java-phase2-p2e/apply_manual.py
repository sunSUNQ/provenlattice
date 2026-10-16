"""Apply the 9 manual adjudications (auditor: this review; evidence = source
lines + method-ownership checks recorded in the report)."""
import json
from collections import Counter
from pathlib import Path

R = Path("evidence/java-phase2-p2e/results")
MANUAL = {
    ("hikaricp", "UnwrapTest.java", 71): ("UNNECESSARY_DEMOTION_JDT_RECOVERED",
        "addDataSourceProperty/setDataSourceClassName are unique to HikariConfig; mode-A 0.75 binding was correct; JDT recovers the same target"),
    ("hikaricp", "ConnectionStateTest.java", 48): ("UNNECESSARY_DEMOTION_JDT_RECOVERED",
        "addDataSourceProperty unique to HikariConfig; same as above"),
    ("hikaricp", "MiscTest.java", 121): ("CORRECT_DEMOTION_JDT_FIXES",
        "SECONDS is a TimeUnit constant; mode-A bound ClockSource.toMillis (wrong); JDT=TimeUnit correct"),
    ("gson", "CollectionTest.java", 294): ("CORRECT_DEMOTION_JDT_FIXES",
        "target is List<BagOfPrimitives>; mode-A bound the same-file nested test class (audit shape #8); JDT=List correct"),
}
CHAIN_FILES_GSON = {"StructTypeAdapterTest.java", "CustomDeserializerTest.java",
                    "InheritanceTest.java"}
CHAIN_JGIT = {"SignerV4.java", "TestRepositoryTest.java"}

d = json.loads((R / "fresh-audit-adjudication-v2.json").read_text(encoding="utf-8"))
applied = 0
for label, payload in d["by_label"].items():
    for r in payload["rows"]:
        key = (label, r["file"].rsplit("/", 1)[-1], r["line"])
        if key in MANUAL:
            verdict, reason = MANUAL[key]
            r["adjudication"] = verdict
            r["manual_reason"] = reason
            r["auditor"] = "p2e-review"
            applied += 1
        elif "NEEDS_MANUAL (S4" in r["adjudication"]:
            tail = r["file"].rsplit("/", 1)[-1]
            if label == "gson" and tail in CHAIN_FILES_GSON:
                r["adjudication"] = "CHAIN_CONSISTENT (spot-checked)"
                r["manual_reason"] = "chained get(...)/getAsJsonArray return-type flow; JDT matches chain semantics"
                r["auditor"] = "p2e-review"
                applied += 1
            elif label == "jgit" and tail in CHAIN_JGIT:
                r["adjudication"] = "CHAIN_CONSISTENT (spot-checked)"
                r["manual_reason"] = "builder/RefUpdate chain return-type flow; JDT matches chain semantics"
                r["auditor"] = "p2e-review"
                applied += 1
totals = Counter()
by_label_counts = {}
for label, payload in d["by_label"].items():
    c = Counter(r["adjudication"].split(" (")[0] for r in payload["rows"])
    by_label_counts[label] = dict(c)
    totals.update(c)
d["final_totals"] = dict(totals)
d["by_label_final"] = by_label_counts
(R / "fresh-audit-adjudication-final.json").write_text(
    json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
print("applied:", applied)
print("FINAL TOTALS:", json.dumps(dict(totals), indent=1))
for label, c in by_label_counts.items():
    print(label, json.dumps(c))

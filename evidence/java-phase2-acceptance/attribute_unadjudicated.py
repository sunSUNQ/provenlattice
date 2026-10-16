"""P2-E closure Phase 1: attribute and re-adjudicate the 147 UNADJUDICATED.

Independent truth method (NOT L1, NOT JDT): repo-wide declaration search for
the receiver identifier's declared type. If exactly one distinct declared
type exists across the repo (and its import maps to a full name), truth is
established; JDT/L1 verdicts are then compared against it. Ambiguity from
multiple distinct declaring types stays UNADJUDICATED (genuine)."""
import json
import re
from collections import Counter
from pathlib import Path

R = Path("evidence/java-phase2-p2e/results")
data = json.loads((R / "fresh-audit-adjudication-final.json").read_text(encoding="utf-8"))
REPOS = {
    "hikaricp": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\hikaricp"),
    "gson": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\gson"),
    "jgit": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\jgit"),
}
DECL_RX = re.compile(
    r"(?:private|protected|public|final|static|\s)*"
    r"([A-Z][\w]*(?:<[\w<>\.,\s\?\[\]]*>)?(?:\[\])?)\s+{R}\s*(?:=|;|\)|,)")
IMPORT_RX = re.compile(r"import\s+(?:static\s+)?([\w\.]+)\s*;")


def repo_decl_search(repo: Path, file: str, receiver: str) -> dict:
    """Repo-wide search for `Type receiver` declarations (binding-blind)."""
    simple = receiver.rsplit(".", 1)[-1]
    rx = re.compile(DECL_RX.pattern.replace("{R}", re.escape(simple)))
    found = {}
    for java in repo.rglob("*.java"):
        try:
            text = java.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        imports = {m.group(1).rsplit(".", 1)[-1]: m.group(1)
                   for m in IMPORT_RX.finditer(text) if "static" not in m.group(0)}
        for m in rx.finditer(text):
            candidate = m.group(1).strip()
            base = candidate.split("<")[0].strip()
            if base in {"return", "new", "throw", "if", "for", "while", "catch"}:
                continue
            full = imports.get(base, base)
            found.setdefault(full, java.name)
    return found


totals = Counter()
out = {"attributed": [], "still_unadjudicated": []}
for label, payload in data["by_label"].items():
    repo = REPOS[label]
    counts = Counter()
    for r in payload["rows"]:
        if not r["adjudication"].startswith("UNADJUDICATED"):
            totals[r["adjudication"].split(" (")[0]] += 1
            continue
        raw_name = r["raw_name"]
        receiver = raw_name.rsplit(".", 1)[0] if "." in raw_name else ""
        root = receiver.partition(".")[0]
        chain = "()." in raw_name or ".get(" in raw_name or ".stream()" in raw_name
        if not root or root in {"this", "super"} or root[:1].islower() and False:
            pass
        # mechanism classification (always recorded)
        if chain:
            mechanism = "chain_type_flow"
        elif root[:1].isupper():
            mechanism = "stdlib_or_class_static"
        else:
            mechanism = "cross_file_type_flow"
        found = repo_decl_search(repo, r["file"], root)
        entry = {"repo": label, "file": r["file"], "line": r["line"],
                 "raw_name": raw_name, "stratum": r["stratum"],
                 "receiver_root": root, "mechanism": mechanism,
                 "decl_candidates": found, "l1_status": r["status"],
                 "jdt_decl": r["jdt_decl"], "mode_a": r["mode_a_original_l1"]}
        if len(found) == 1:
            truth_full = next(iter(found))
            truth_simple = truth_full.rsplit(".", 1)[-1]
            entry["truth_decl"] = truth_full
            jdt_simple = (r["jdt_decl"] or "").split("<")[0].rsplit(".", 1)[-1] \
                if r["jdt_decl"] else None
            if r["jdt_decl"] is None:
                entry["new_verdict"] = "UNADJUDICATED (no JDT binding for site)"
                counts["UNADJUDICATED_NO_JDT"] += 1
                out["still_unadjudicated"].append(entry)
            elif jdt_simple == truth_simple:
                entry["new_verdict"] = "SUPPLEMENTAL_JDT_CORRECT"
                counts["SUPPLEMENTAL_JDT_CORRECT"] += 1
                out["attributed"].append(entry)
            else:
                entry["new_verdict"] = "SUPPLEMENTAL_MISMATCH (needs review)"
                counts["SUPPLEMENTAL_MISMATCH"] += 1
                out["attributed"].append(entry)
        elif len(found) > 1:
            entry["new_verdict"] = "UNADJUDICATED (multiple declaring types)"
            counts["UNADJUDICATED_MULTI_DECL"] += 1
            out["still_unadjudicated"].append(entry)
        else:
            entry["new_verdict"] = "UNADJUDICATED (declaration not in repo; external/JDK param)"
            counts["UNADJUDICATED_EXTERNAL_OR_MISSING"] += 1
            out["still_unadjudicated"].append(entry)
    by_label_counts = dict(counts)
    out.setdefault("counts_by_label", {})[label] = by_label_counts
    totals.update(counts)

out["totals"] = dict(totals)
(R / "unadjudicated-attribution.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print("TOTALS:", json.dumps(dict(totals), indent=1))

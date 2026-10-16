"""P2-E Phase 3 adjudication: classify the 225 fresh sampled sites.

Truth priority: receiver declared type from source context (binding-blind,
recorded in fresh-audit-samples.json) cross-checked against imports; sites
without an establishable truth stay UNADJUDICATED."""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

R = Path("evidence/java-phase2-p2e/results")
data = json.loads((R / "fresh-audit-samples.json").read_text(encoding="utf-8"))
REPOS = {
    "hikaricp": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\hikaricp"),
    "gson": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\gson"),
    "jgit": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\jgit"),
}


def jdk_class_for(receiver_decl_guess: str, repo: Path, file: str) -> str | None:
    """Map a receiver guess to a full type via the file's imports (JDK/in-project)."""
    path = repo / file
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        m = re.match(r"\s*import\s+(?:static\s+)?([\w\.]+);", line)
        if m and m.group(1).endswith("." + receiver_decl_guess):
            return m.group(1)
    return None


summary_total = Counter()
by_label = {}
manual_needed = []
for label, payload in data.items():
    repo = REPOS[label]
    counts = Counter()
    rows = []
    for s in payload["sites"]:
        truth_ctx = s["truth"]
        guess = truth_ctx.get("receiver_decl_guess")
        jdt_row = s.get("jdt") or {}
        jdt_decl = jdt_row.get("decl") if isinstance(jdt_row, dict) else None
        truth_full = None
        if guess:
            if guess[:1].isupper():
                truth_full = jdk_class_for(guess, repo, s["file"]) or guess
        entry = {k: s.get(k) for k in ("file", "line", "raw_name", "stratum",
                                       "status", "resolution_strategy",
                                       "confidence", "mode_a_original_l1")}
        entry["receiver_decl_guess"] = guess
        entry["jdt_decl"] = jdt_decl
        if truth_full is None:
            entry["adjudication"] = "UNADJUDICATED"
            counts["UNADJUDICATED"] += 1
            manual_needed.append({**entry, "source": truth_ctx.get("source_line")})
        else:
            entry["truth_decl"] = truth_full
            jdt_ok = jdt_decl and (jdt_decl == truth_full or
                                   jdt_decl.split("<")[0] == truth_full)
            l1_ok = None
            if s["status"] == "resolved":
                # target full name unavailable for demoted rows; use strategy
                l1_ok = entry["resolution_strategy"] in (
                    "import_resolution", "qualified_name_resolution")
            # classify by stratum
            if s["stratum"] == "S2":
                if entry["mode_a_original_l1"] == "resolved":
                    if truth_full and s["raw_name"].lower().endswith(
                            truth_full.rsplit(".", 1)[-1].lower()):
                        # conservative: name match is not type proof
                        entry["adjudication"] = "NEEDS_MANUAL (demoted; mode A resolved)"
                        counts["NEEDS_MANUAL"] += 1
                        manual_needed.append({**entry, "source": truth_ctx.get("source_line")})
                    else:
                        entry["adjudication"] = "CORRECT_DEMOTION"
                        counts["CORRECT_DEMOTION"] += 1
                else:
                    entry["adjudication"] = "NEEDS_MANUAL (demoted; mode A not resolved)"
                    counts["NEEDS_MANUAL"] += 1
                    manual_needed.append({**entry, "source": truth_ctx.get("source_line")})
            elif s["stratum"] == "S1":
                entry["adjudication"] = ("L1_EXACT_CORRECT" if l1_ok
                                         else "NEEDS_MANUAL (S1 exact-tier)")
                counts[entry["adjudication"]] += 1
                if entry["adjudication"] != "L1_EXACT_CORRECT":
                    manual_needed.append({**entry, "source": truth_ctx.get("source_line")})
            elif s["stratum"] == "S4":
                if jdt_ok:
                    entry["adjudication"] = "JDT_RECOVERED_CORRECT"
                else:
                    entry["adjudication"] = "NEEDS_MANUAL (S4 JDT mismatch)"
                counts[entry["adjudication"]] += 1
                if "NEEDS_MANUAL" in entry["adjudication"]:
                    manual_needed.append({**entry, "source": truth_ctx.get("source_line")})
            else:
                # S3/S5: unresolved or heuristic-origin rows; JDT cross-check
                if s["status"] == "unresolved" and jdt_ok:
                    entry["adjudication"] = "JDT_RESOLVES_UNRESOLVED"
                elif s["status"] == "unresolved":
                    entry["adjudication"] = "UNRESOLVED_JDK_OR_UNKNOWN"
                else:
                    entry["adjudication"] = "NEEDS_MANUAL (S5 resolved heuristic)"
                    manual_needed.append({**entry, "source": truth_ctx.get("source_line")})
                counts[entry["adjudication"]] += 1
        rows.append(entry)
    by_label[label] = {"counts": dict(counts), "rows": rows}
    summary_total.update(counts)

(R / "fresh-audit-adjudication.json").write_text(
    json.dumps({"by_label": by_label, "manual_needed": manual_needed},
               indent=2, ensure_ascii=False), encoding="utf-8")
print("TOTALS:", json.dumps(dict(summary_total), indent=1))
print("manual_needed:", len(manual_needed))

"""P2-E Phase 3: fresh stratified audit (60 sites x 3 repos, seed frozen).

Strata (per manifest): S1 exact-tier L1 resolved / S2 demoted (ambiguous +
demote_reason) / S3 unresolved CALLS / S4 JDT-resolved site outside S1 /
S5 residual CALLS. Audit mode A (original L1) uses an isolated git-archive
snapshot of commit 7ed0e8a (pre-P2-A) indexing the SAME repos.

Truth extraction is binding-blind: the truth classifier reads ONLY source
(imports, field/param declarations, call-site line) and never sees L1/JDT
verdicts; undecided sites are recorded UNADJUDICATED.
"""
import json
import random
import re
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

from provenlattice.graph import full_index

OUT = Path("evidence/java-phase2-p2e/results")
SEED = 20261015
REPOS = {
    "hikaricp": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\hikaricp"),
    "gson": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\gson"),
    "jgit": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\jgit"),
}
HISTORICAL = {  # audited separately; excluded from fresh frame
    ("HikariConfig.java", 318), ("ClockSourceTest.java", 41),
    ("ConcurrentBag.java", 305), ("HikariConfig.java", 1029),
    ("JsonObject.java", 223), ("MapTest.java", 95),
    ("NumberLimitsTest.java", 103), ("CollectionTest.java", 273),
}


def load_calls(db: Path) -> list[dict]:
    with closing(sqlite3.connect(db)) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(
            "SELECT f.path AS file, r.start_line AS line, r.raw_name, r.status, "
            "r.resolution_strategy, r.confidence, r.metadata, "
            "n.qualified_name AS target FROM raw_references r "
            "LEFT JOIN nodes n ON r.resolved_symbol_id=n.id "
            "JOIN files f ON r.file_id=f.file_id WHERE r.reference_type='CALLS' "
            "ORDER BY f.path, r.id")]


def jdt_bindings(detail: Path) -> dict:
    out = {}
    if not detail.exists():
        return out
    for line in detail.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("{"):
            continue
        r = json.loads(line)
        if r.get("kind") == "call" and "file" in r:
            out[(r["file"], r["line"], r["expr"].split(".")[-1])] = r
    return out


def stratified(calls: list[dict], jdt: dict, repo_root: Path, per_stratum: int = 15):
    """Build the strata frame and sample; returns sampled sites with strata ids."""
    rng = random.Random(SEED)
    strata: dict[str, list[dict]] = {"S1": [], "S2": [], "S3": [], "S4": [], "S5": []}
    seen_sites = set()
    for row in calls:
        tail = row["file"].rsplit("/", 1)[-1]
        if (tail, row["line"]) in HISTORICAL:
            continue
        site_key = (row["file"], row["line"], row["raw_name"])
        if site_key in seen_sites:
            continue
        seen_sites.add(site_key)
        md = json.loads(row["metadata"]) if row["metadata"] else {}
        jdt_row = jdt.get((row["file"], row["line"],
                           row["raw_name"].rsplit(".", 1)[-1].split("(")[0]))
        jdt_resolved = (jdt_row is not None and jdt_row.get("decl")
                        and not jdt_row.get("recovered"))
        if row["status"] == "resolved" and row["confidence"] >= 0.99:
            strata["S1"].append({**row, "stratum": "S1"})
        elif row["status"] == "ambiguous" and md.get("demote_reason"):
            strata["S2"].append({**row, "stratum": "S2", "jdt": jdt_row})
        elif row["status"] == "unresolved" and row["resolution_strategy"] != "indirect_call_shape":
            strata["S3"].append({**row, "stratum": "S3", "jdt": jdt_row})
        elif row["status"] == "unresolved" and jdt_resolved:
            strata["S4"].append({**row, "stratum": "S4", "jdt": jdt_row})
        else:
            strata["S5"].append({**row, "stratum": "S5", "jdt": jdt_row})
    sampled = []
    for sid, pool in strata.items():
        take = min(per_stratum, len(pool))
        picked = rng.sample(pool, take) if take else []
        sampled.extend(picked)
        print(f"  {sid}: pool={len(pool)} sampled={take}")
    return sampled, {k: len(v) for k, v in strata.items()}


def source_truth(repo: Path, file: str, line: int, raw_name: str) -> dict:
    """Binding-blind truth: read the source line + receiver context."""
    path = repo / file
    try:
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"verdict": "UNADJUDICATED", "reason": "source_unreadable"}
    if not (0 < line <= len(text)):
        return {"verdict": "UNADJUDICATED", "reason": "line_out_of_range"}
    src = text[line - 1].strip()
    short = raw_name.rsplit(".", 1)[-1].split("(")[0]
    receiver = raw_name.rsplit(".", 1)[0] if "." in raw_name else ""
    context = "\n".join(text[max(0, line - 8):line])
    # declared-type heuristics from the visible context (binding-blind)
    decl = None
    m = re.search(rf"(\w+)\s+{re.escape(receiver)}\s*[=;,)]", context) if receiver else None
    if m:
        decl = m.group(1)
    m2 = re.search(rf"for\s+\(\s*[\w<>,\s\.\[\]]+\s+(\w+)\s*:\s*([\w\.]+)", context)
    if m2 and m2.group(1) == receiver:
        decl = m2.group(2)
    return {"verdict": "CONTEXT_READ", "source_line": src[:120],
            "receiver": receiver, "short": short,
            "receiver_decl_guess": decl,
            "note": "final adjudication performed by reading the recorded context"}


def main() -> None:
    # mode A: original L1 via isolated pre-P2-A snapshot
    archive = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\p2e-proold")
    report = {}
    for label, repo in REPOS.items():
        db = repo / ".provenlattice" / "codegraph.db"
        if not db.exists():
            full_index(repo, db)
        calls = load_calls(db)
        detail = Path("evidence/java-phase2-p2e/results") / f"p2e-{label}-full-detail.jsonl"
        jdt = jdt_bindings(detail)
        sampled, pool_sizes = stratified(calls, jdt, repo)
        audited = []
        for row in sampled:
            truth = source_truth(repo, row["file"], row["line"], row["raw_name"])
            # mode A: original L1 status from the pre-P2-A snapshot DB
            a_status = None
            old_db = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\p2e-proold-db") / f"{label}.db"
            if old_db.exists():
                with closing(sqlite3.connect(old_db)) as c:
                    c.row_factory = sqlite3.Row
                    rows = [dict(r) for r in c.execute(
                        "SELECT r.status, r.resolution_strategy FROM raw_references r "
                        "JOIN files f ON r.file_id=f.file_id WHERE f.path=? AND "
                        "r.reference_type='CALLS' AND r.start_line=? LIMIT 3",
                        (row["file"], row["line"]))]
                    a_status = rows[0]["status"] if rows else None
            audited.append({k: row.get(k) for k in (
                "file", "line", "raw_name", "status", "resolution_strategy",
                "confidence", "stratum", "jdt")} | {
                "mode_a_original_l1": a_status, "truth": truth})
        report[label] = {"pool_sizes": pool_sizes, "sampled": len(sampled),
                         "sites": audited}
        print(label, "sampled", len(sampled), "pool", pool_sizes)
    (OUT / "fresh-audit-samples.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()

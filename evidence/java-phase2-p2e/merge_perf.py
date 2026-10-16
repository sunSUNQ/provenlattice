"""P2-E Phase 1 perf: batch merge wall time and site counts on all 3 repos."""
import json
import time
from contextlib import closing
from pathlib import Path

import sqlite3

from provenlattice import java_semantic as jsem
from provenlattice.java_semantic import SemanticResult, SemanticBinding

RESULTS = Path("evidence/java-phase2-p2e/results")
RESULTS.mkdir(parents=True, exist_ok=True)
JDK = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\tools\jdk-path.txt").read_text().strip()
JARS = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\tools\jars")
REPOS = {
    "hikaricp": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\hikaricp"),
    "gson": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\gson"),
    "jgit": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\jgit"),
}


def run_full_with_detail(repo: Path, label: str) -> tuple[SemanticResult, Path]:
    detail = RESULTS / f"p2e-{label}-full-detail.jsonl"
    if detail.exists():
        detail.unlink()
    import os
    os.environ.setdefault("PL_JAVA_JDK", JDK)
    os.environ.setdefault(
        "PL_JAVA_JDT_CLASSPATH",
        ";".join(str(j) for j in JARS.glob("*.jar")))
    # run the analyzer in full mode via the production module, but capture the
    # driver detail file directly by calling the internals with a detail path
    result = jsem.run_jdt_analysis(repo, mode="full", timeout_s=1800)
    # locate the driver detail file from the cache dir (p2d-*.jsonl, newest)
    cache = Path(os.environ.get("PL_JAVA_SEMANTIC_CACHE",
                                Path(__import__("tempfile").gettempdir()) / "provenlattice-java-semantic"))
    candidates = sorted(cache.glob("p2d-*.jsonl"), key=lambda p: p.stat().st_mtime)
    if candidates:
        detail.write_bytes(candidates[-1].read_bytes())
    return result, detail


def merge_timed(result: SemanticResult, db: Path) -> dict:
    t0 = time.perf_counter()
    merged = jsem.merge_with_l1(result, db)
    wall_ms = int((time.perf_counter() - t0) * 1000)
    with closing(sqlite3.connect(str(db))) as conn:
        total_calls = conn.execute(
            "SELECT COUNT(*) FROM raw_references WHERE reference_type='CALLS'").fetchone()[0]
    return {"merge_wall_ms": wall_ms, "sites": len(merged["sites"]),
            "counts": merged["counts"], "l1_calls_rows": total_calls}


out = {}
for label, repo in REPOS.items():
    db = repo / ".provenlattice" / "codegraph.db"
    result, detail = run_full_with_detail(repo, label)
    if result.status != "available":
        out[label] = {"status": result.status, "reason": result.reason}
        continue
    # rebuild SemanticResult with detail bindings for the timed merge
    bindings = [SemanticBinding(file=r["file"], line=r["line"], expr=r["expr"],
                                decl=r.get("decl"),
                                state="recovered_filtered" if r.get("recovered")
                                else ("ambiguous" if not r.get("decl") else "resolved"),
                                signature=r.get("signature"))
                for r in (json.loads(l) for l in detail.read_text(encoding="utf-8").splitlines())
                if r.get("kind") == "call" and "file" in r]
    timed = merge_timed(SemanticResult(status="available", bindings=bindings,
                                       meta=result.meta), db)
    timed["jdt_calls_resolved"] = result.summary.get("calls_resolved")
    out[label] = timed
    print(label, json.dumps(timed))
    (RESULTS / f"p2e-merge-{label}.json").write_text(
        json.dumps({**timed, "detail_lines": detail.stat().st_size // 1024}, indent=2),
        encoding="utf-8")
(RESULTS / "p2e-merge-perf.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

"""P2-E Phase 1 equivalence harness: prototype (a22a03a) vs batch merge."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\hikaricp")
DB = REPO / ".provenlattice" / "codegraph.db"
DETAIL = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\tools\jars")  # not used
BINDINGS_SRC = Path("evidence/java-phase2-p2b/results/p2b-hikaricp-full-detail-0.jsonl")
OLD_SRC = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\p2e-proold\src")
OUT = Path("evidence/java-phase2-p2e/results")
OUT.mkdir(parents=True, exist_ok=True)

bindings = []
for line in BINDINGS_SRC.read_text(encoding="utf-8").splitlines():
    if not line.strip().startswith("{"):
        continue
    row = json.loads(line)
    if row.get("kind") != "call" or "file" not in row:
        continue
    from provenlattice.java_semantic import SemanticBinding
    bindings.append(SemanticBinding(
        file=row["file"], line=row["line"], expr=row["expr"],
        decl=row.get("decl"),
        state="recovered_filtered" if row.get("recovered")
        else ("ambiguous" if not row.get("decl") else "resolved"),
        signature=row.get("signature")))
result_payload = {"status": "available", "meta": {"classpath_fingerprint": "cp:equiv"},
                  "bindings_count": len(bindings)}

harness = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from provenlattice.java_semantic import SemanticResult, SemanticBinding, merge_with_l1
bindings = [SemanticBinding(**b) for b in json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))]
result = SemanticResult(status="available", bindings=bindings,
                        meta={"classpath_fingerprint": "cp:equiv"})
merged = merge_with_l1(result, sys.argv[2])
sites = [{"file": s["file"], "line": s["line"], "expr": s["expr"], "state": s["state"],
          "l1_targets": sorted((r["target"] or "") for r in s["l1"]),
          "jdt_decl": s["jdt"]["decl"] if isinstance(s["jdt"], dict) else s["jdt"].decl}
         for s in merged["sites"]]
sites.sort(key=lambda s: (s["file"], s["line"], s["expr"]))
json.dump({"counts": merged["counts"], "sites": sites},
          open(sys.argv[4], "w", encoding="utf-8"), indent=1)
print("counts:", json.dumps(merged["counts"]))
'''
harness_path = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\p2e-equiv-harness.py")
harness_path.write_text(harness, encoding="utf-8")
bindings_json = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\p2e-bindings.json")
bindings_json.write_text(json.dumps([b.to_dict() for b in bindings]), encoding="utf-8")

env = {**__import__("os").environ, "PYTHONPATH": str(REPO.parents[3] / "src")}
# new implementation
cur_env = {**__import__("os").environ, "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src")}
r_new = subprocess.run([sys.executable, str(harness_path), ".",
                        str(DB), str(bindings_json),
                        str(OUT / "merge-new-sites.json")],
                       capture_output=True, text=True, env=cur_env, timeout=1800)
print("new:", r_new.stdout.strip(), r_new.stderr[-200:] if r_new.returncode else "")
# old prototype
old_env = {**__import__("os").environ, "PYTHONPATH": str(OLD_SRC)}
r_old = subprocess.run([sys.executable, str(harness_path), ".",
                        str(DB), str(bindings_json),
                        str(OUT / "merge-old-sites.json")],
                       capture_output=True, text=True, env=old_env, timeout=1800)
print("old:", r_old.stdout.strip(), r_old.stderr[-200:] if r_old.returncode else "")

new = json.loads((OUT / "merge-new-sites.json").read_text(encoding="utf-8"))
old = json.loads((OUT / "merge-old-sites.json").read_text(encoding="utf-8"))
identical = new == old
print("counts_old:", json.dumps(old["counts"]))
print("counts_new:", json.dumps(new["counts"]))
print("per-site identical:", identical, f"({len(new['sites'])} sites)")
(OUT / "merge-equivalence.json").write_text(json.dumps(
    {"identical": identical, "counts_old": old["counts"], "counts_new": new["counts"],
     "sites": len(new["sites"]),
     "frozen_oracle_counts": {"recovered_by_jdt": 3215, "conflict_conservative": 38,
                              "l1_and_jdt_agree": 716, "jdt_ambiguous": 1248}},
    indent=2), encoding="utf-8")

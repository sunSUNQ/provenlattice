"""P2-C real-project validation on fixed-SHA repos (A-F scenarios) plus an
isolated JDT prototype consumption check (NOT formal P2-D integration)."""
import json
import subprocess
import sys
from pathlib import Path

from provenlattice.classpath import build_classpath, load_classpath_file

OUT = Path("evidence/java-phase2-p2c/results")
OUT.mkdir(parents=True, exist_ok=True)
REPOS = {
    "hikaricp": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\hikaricp"),
    "gson": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\gson"),
    "jgit": Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\jgit"),
}
SLF4J = r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\tools\jars\slf4j-api.jar"
JDK = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\tools\jdk-path.txt").read_text().strip()
P2B = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\p2b\classes")
JARS = Path(r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\tools\jars")

report = {}

# A. no classpath -> empty, valid, usable
for label, repo in REPOS.items():
    c = build_classpath()
    report[f"A_empty_{label}"] = {"status": c.status, "usable": c.usable,
                                  "fingerprint": c.fingerprint}

# B. manual full classpath (project source roots + a real dependency jar)
for label, repo in REPOS.items():
    src_roots = sorted({str(p.parent.parent.parent.parent)
                        for p in repo.rglob("*.java")
                        if len(p.relative_to(repo).parts) > 3})
    c = build_classpath(project_roots=src_roots, dependencies=[SLF4J])
    report[f"B_full_{label}"] = {"status": c.status, "usable": c.usable,
                                 "roots": len(c.project_roots),
                                 "deps": len(c.dependencies),
                                 "fingerprint": c.fingerprint}

# C. partial classpath (one missing jar) -> invalid, fail-closed
c = build_classpath(project_roots=[str(REPOS["hikaricp"] / "src" / "main" / "java")],
                    dependencies=[SLF4J, str(REPOS["hikaricp"] / "no-such.jar")])
report["C_partial_hikaricp"] = {"status": c.status, "usable": c.usable,
                                "issues": [i.code for i in c.issues],
                                "fingerprint": c.fingerprint}

# D. wrong classpath (nonexistent + text file as jar) -> invalid
c = build_classpath(dependencies=[str(REPOS["gson"] / "nope"), str(REPOS["gson"] / "README.md")])
report["D_wrong_gson"] = {"status": c.status, "usable": c.usable,
                          "issues": [i.code for i in c.issues]}

# E. classpath update -> fingerprint changes (invalidation input)
dep_a = str(REPOS["hikaricp"] / "src" / "main" / "java")
dep_b = SLF4J
fp1 = build_classpath(dependencies=[dep_a]).fingerprint
fp2 = build_classpath(dependencies=[dep_a, dep_b]).fingerprint
report["E_update"] = {"fp_before": fp1, "fp_after": fp2, "changed": fp1 != fp2}

# F. duplicate + order stability/sensitivity
c1 = build_classpath(dependencies=[dep_b, dep_a, dep_b])
report["F_dup_order"] = {"deps": len(c1.dependencies),
                         "duplicates": len(c1.duplicates),
                         "order_preserved": c1.dependencies == tuple(
                             str(Path(p).resolve()).replace("\\", "/")
                             for p in [dep_b, dep_a])}

# JDT consumption via the contract (ISOLATED PROTOTYPE, not formal P2-D)
cp = ";".join(build_classpath(dependencies=[SLF4J]).dependencies)
env = {**__import__("os").environ}
cmd = [Path(JDK) / "bin" / "java.exe", "-Xmx1g",
       "-cp", ";".join(str(j) for j in JARS.glob("*.jar")) + ";" + str(P2B),
       "P2bDriver", str(REPOS["hikaricp"]), "stats",
       str(OUT / "jdt-consume-summary.json"), cp]
proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
summary = None
if proc.returncode == 0:
    summary = json.loads((OUT / "jdt-consume-summary.json").read_text(encoding="utf-8"))
report["jdt_consumption_isolated_prototype"] = {
    "rc": proc.returncode,
    "classpath_from_contract": cp,
    "calls_resolved": summary.get("calls_resolved") if summary else None,
    "types_recovered": summary.get("types_recovered") if summary else None,
    "problems": summary.get("problems_total") if summary else None,
}

(OUT / "p2c-real-project-validation.json").write_text(
    json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))

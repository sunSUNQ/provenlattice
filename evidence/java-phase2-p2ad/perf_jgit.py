import json
import time
from pathlib import Path

from provenlattice import java_semantic as jsem

times = []
for i in range(3):
    t0 = time.perf_counter()
    r = jsem.run_jdt_analysis(
        r"C:\Users\sunqinghw\AppData\Local\Temp\opencode\longrun\repos\jgit",
        mode="stats", xmx="1g", timeout_s=900)
    wall = int((time.perf_counter() - t0) * 1000)
    times.append(wall)
    print(f"run{i}: status={r.status} wall_ms={wall} "
          f"calls_resolved={r.summary.get('calls_resolved')}")
print("median_wall_ms:", sorted(times)[1],
      "| budget: <=15000ms wall, RSS<=1.6GB (P2-B sampled 1.13-1.19GB @1g)")
Path("evidence/java-phase2-p2ad/results/p2ad-jgit-production-path.json").write_text(
    json.dumps({"median_wall_ms": sorted(times)[1], "runs_wall_ms": times,
                "budget": {"xmx": "1g", "rss_max_gb": 1.6, "wall_max_s": 15}},
               indent=2), encoding="utf-8")

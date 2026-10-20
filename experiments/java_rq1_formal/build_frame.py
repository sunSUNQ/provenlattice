"""Issue Pilot #4: deterministic sampling-frame builder for Java RQ1 formal.

APPROVE_DESIGN_ONLY scope (PL-JAVA-ISSUE-DECISION-20261020):
- `stats` mode measures per-stratum population counts (frame statistics).
  This is measurement, not annotation.
- `sample` mode emits the frozen 174-case candidate package. It is present so
  the freeze is fully specified, but it MUST NOT be executed until the
  execution gates in plan-frozen-v1.md are met (owner gate + Issue #3 Linux
  JDT verification or explicit owner waiver + frame-freeze approval).
  Running it early is a protocol violation.

Strata (per repository, relation CALLS):
  S1 L1_RESOLVED_L1_ONLY      L1 resolved; site not bound by JDT merge
  S2 L1_RESOLVED_JDT_AGREE    L1 resolved and JDT agrees
  S3 L1_RESOLVED_JDT_CONFLICT L1 resolved and JDT disagrees (conservative keep)
  S4 NONRESOLVED_RECOVERED    L1 ambiguous/unresolved; JDT bound it
  S5 NONRESOLVED_JDT_AMB      L1 ambiguous/unresolved; JDT also ambiguous
  S6 NONRESOLVED_NOT_SEEN     L1 ambiguous/unresolved; JDT did not see site

Determinism: no RNG anywhere. Cases are ordered by (file, line, raw_name,
resolution_strategy); selection takes fixed per-stratum n from the ordered
list via largest-remainder allocation of the repo quota, floors/caps applied.
The emitted package records population_N and sample_n per stratum plus
SHA256 provenance, mirroring experiments/fidelity_v1 conventions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from provenlattice.java_semantic import run_jdt_analysis, merge_with_l1

STRATA = ["S1_L1_RESOLVED_L1_ONLY", "S2_L1_RESOLVED_JDT_AGREE",
          "S3_L1_RESOLVED_JDT_CONFLICT", "S4_NONRESOLVED_RECOVERED",
          "S5_NONRESOLVED_JDT_AMBIG", "S6_NONRESOLVED_NOT_SEEN"]

REPO_QUOTA = 58  # 3 x 58 = 174 (owner-frozen total)


def classify(repo: Path, database: Path, manifest: str | None) -> dict:
    result = run_jdt_analysis(repo, classpath_manifest=manifest)
    if result.status != "available":
        raise SystemExit(f"JDT unavailable: {result.reason}")
    merged = merge_with_l1(result, database)
    site_state: dict[tuple[str, int, str], str] = {}
    for site in merged["sites"]:
        site_state[(site["file"], site["line"], site["expr"])] = site["state"]

    populations = {s: [] for s in STRATA}
    with closing(sqlite3.connect(str(database))) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            "SELECT f.path AS file, r.start_line AS line, r.raw_name, "
            "r.status, r.resolution_strategy, r.confidence, "
            "n.qualified_name AS target, r.reference_type "
            "FROM raw_references r LEFT JOIN nodes n ON r.resolved_symbol_id=n.id "
            "JOIN files f ON r.file_id=f.file_id WHERE r.reference_type='CALLS'"
        ):
            root = row["raw_name"].split(".")[-1].lower()
            jdt_state = site_state.get((row["file"], row["line"], root))
            resolved = row["status"] == "resolved"
            if resolved:
                if jdt_state == "l1_and_jdt_agree":
                    stratum = "S2_L1_RESOLVED_JDT_AGREE"
                elif jdt_state == "conflict_conservative":
                    stratum = "S3_L1_RESOLVED_JDT_CONFLICT"
                else:
                    stratum = "S1_L1_RESOLVED_L1_ONLY"
            else:
                if jdt_state == "recovered_by_jdt":
                    stratum = "S4_NONRESOLVED_RECOVERED"
                elif jdt_state == "jdt_ambiguous":
                    stratum = "S5_NONRESOLVED_JDT_AMBIG"
                else:
                    stratum = "S6_NONRESOLVED_NOT_SEEN"
            populations[stratum].append({
                "file": row["file"], "line": row["line"],
                "raw_name": row["raw_name"], "status": row["status"],
                "resolution_strategy": row["resolution_strategy"],
                "confidence": row["confidence"], "target": row["target"],
                "jdt_state": jdt_state,
            })
    for stratum in STRATA:
        populations[stratum].sort(key=lambda c: (
            c["file"], c["line"], c["raw_name"], c["resolution_strategy"]))
    return populations


def allocate(populations: dict, repo_quota: int = REPO_QUOTA) -> dict:
    """Proportional-to-population largest-remainder allocation with floor 3
    and cap 24 per stratum (strata with population 0 get 0)."""
    total = sum(len(v) for v in populations.values())
    if total == 0:
        return {s: 0 for s in STRATA}
    eligible = {s: len(v) for s, v in populations.items() if len(v) > 0}
    raw = {s: repo_quota * n / total for s, n in eligible.items()}
    sample_n = {s: max(3, min(24, int(raw[s]))) for s in eligible}
    rest = repo_quota - sum(sample_n.values())
    order = sorted(eligible,
                   key=lambda s: (raw[s] - int(raw[s]), len(populations[s])),
                   reverse=True)
    i = 0
    while rest != 0 and order:
        s = order[i % len(order)]
        if rest > 0 and sample_n[s] < 24:
            sample_n[s] += 1
            rest -= 1
        elif rest < 0 and sample_n[s] > 3:
            sample_n[s] -= 1
            rest += 1
        i += 1
        if i > 1000:
            raise SystemExit("allocation did not converge")
    return {s: sample_n.get(s, 0) for s in STRATA}


def package_id(populations: dict) -> str:
    canonical = json.dumps(
        {s: [c["file"] + f":{c['line']}:" + c["raw_name"]
             for c in populations[s]] for s in STRATA},
        sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["stats", "sample"],
                        help="sample mode is GATED (see module docstring)")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--jdk", required=True)
    parser.add_argument("--jars", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--gate-ack", default=None,
                        help="sample mode requires the frame-freeze approval id")
    args = parser.parse_args()

    os_env_jdk = args.jdk
    import os
    os.environ["PL_JAVA_JDK"] = str(Path(os_env_jdk).resolve())
    os.environ["PL_JAVA_JDT_CLASSPATH"] = ";".join(
        str(p) for p in sorted(Path(args.jars).resolve().glob("*.jar")))

    if args.mode == "sample" and not args.gate_ack:
        print("REFUSED: sample mode is gated. Provide --gate-ack with the "
              "frame-freeze approval id issued by the owner after the "
              "execution gates in plan-frozen-v1.md are met.", file=sys.stderr)
        return 2

    populations = classify(Path(args.repo).resolve(), Path(args.db).resolve(),
                           args.manifest)
    allocation = allocate(populations)
    payload = {
        "task": "PL-JAVA-RQ1-FORMAL-V1 frame",
        "mode": args.mode,
        "repo": Path(args.repo).resolve().name,
        "evidence_level": "frame-statistics-windows-only",
        "population_N": {s: len(populations[s]) for s in STRATA},
        "sample_n_rule": "proportional, floor 3, cap 24, largest remainder",
        "sample_n": allocation,
        "total_sample_n": sum(allocation.values()),
        "frame_sha256": package_id(populations),
        "gates": {
            "sample_mode_executed": False,
            "gate_ack": args.gate_ack if args.mode == "sample" else None,
        },
    }
    if args.mode == "sample":
        cases = []
        for stratum in STRATA:
            n = allocation[stratum]
            cases.extend({**c, "stratum": stratum,
                          "annotation": {"relation_verdict": None,
                                         "gold_target": None,
                                         "build_context_status": None,
                                         "confounder_tags": []}}
                         for c in populations[stratum][:n])
        payload["cases"] = cases
        payload["gates"]["sample_mode_executed"] = True
    Path(args.out).resolve().parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "cases"},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

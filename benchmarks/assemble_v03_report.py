from __future__ import annotations

import json
import subprocess
from pathlib import Path


def current_state(repo: Path, expected: str) -> dict:
    repo = repo.resolve()
    git = ["git", "-c", "safe.directory=*", "-C", str(repo)]
    sha = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
    status = subprocess.check_output(git + ["status", "--porcelain"], text=True)
    return {
        "repository_path": str(repo),
        "commit_sha": sha,
        "expected_commit_sha": expected,
        "commit_matches": sha == expected,
        "shallow_clone": (repo / ".git" / "shallow").exists(),
        "git_status_clean": not status.strip(),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    analysis = root / "benchmark-analysis"
    repos = root / "benchmark-repos"
    baseline = json.loads((analysis / "provenlattice-v0.2-baseline.json").read_text(encoding="utf-8"))
    qualification = json.loads((analysis / "provenlattice-v0.3-shard.json").read_text(encoding="utf-8"))
    # The qualification file is also the final output; unwrap it when re-running
    # this assembler so repeated execution remains idempotent.
    if "strategies" not in qualification:
        qualification = qualification["qualification"]
    if "strategies" not in qualification:
        qualification = qualification["qualification"]
    mutations = json.loads((analysis / "provenlattice-v0.3-mutations.json").read_text(encoding="utf-8"))
    representative = [
        json.loads((analysis / "provenlattice-v0.3-B2-representative.json").read_text(encoding="utf-8")),
        json.loads((analysis / "provenlattice-v0.3-B3-representative.json").read_text(encoding="utf-8")),
    ]
    candidates = json.loads((analysis / "benchmark-results.json").read_text(encoding="utf-8"))
    validation = []
    for item in baseline["benchmarks"]:
        name = item["benchmark"].split("-", 1)[1]
        validation.append(current_state(repos / name, item["commit_sha"]))
    report = {
        "schema_version": 1,
        "stage": "ProvenLattice Core V0.3 — Shard Qualification and Incremental Foundation",
        "generated_at": "2026-09-10",
        "scope": ["pluggable shard strategies", "API fingerprint qualification", "reverse boundary index", "one-hop impact frontier", "B1 mutation parity"],
        "repository_validation": validation,
        "qualification": qualification,
        "mutations": mutations,
        "representative_mutations": representative,
        "v0_2_baseline": baseline,
        "benchmark_selection": {
            "target": candidates["target"],
            "similarity_weights": candidates["similarity"]["weights"],
            "frozen_set": {"B1": "aria2/aria2", "B2": "apache/brpc", "B3": "facebook/rocksdb"},
        },
        "recommendations": {
            "B1": "structural when giant_shard_ratio is the constraint; directory remains the low-boundary baseline",
            "B2": "directory baseline; build-aware lowers boundary ratio but creates a giant shard",
            "B3": "build-aware for slightly lower boundary ratio; structural is the balanced alternative when giant shards are capped",
            "policy": "Keep strategy pluggable and select per repository/profile; do not silently replace the directory baseline.",
        },
    }
    out = analysis / "provenlattice-v0.3-shard.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

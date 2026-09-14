from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def blinded_case(case: dict) -> dict:
    return {
        "case_id": case["case_id"],
        "repository": case["repository"],
        "raw_reference_id": case["raw_reference_id"],
        "relation_type": case["relation_type"],
        "source": case["source"],
        "candidate_symbol_ids": case["system"]["candidate_symbol_ids"],
        "build_context": case["build_context"],
        "annotation": {
            "status": "PENDING",
            "relation_verdict": "PENDING",
            "build_context_status": "PENDING",
            "gold_relation_exists": None,
            "gold_target_symbol_id": None,
            "gold_target_path": None,
            "gold_target_start_line": None,
            "difficulty_tags": [],
            "evidence_notes": None,
            "annotator_id": None,
        },
    }


def write_view(cases: list[dict], annotator: str, seed: str, output: Path) -> None:
    ordered = [blinded_case(case) for case in cases]
    random.Random(f"{seed}:{annotator}").shuffle(ordered)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "benchmark_id": "provenlattice-fidelity-v1-pilot",
        "schema_version": 1,
        "view": "BLINDED_ANNOTATION",
        "annotator": annotator,
        "cases": ordered,
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create independent blinded Gold Set annotation views.")
    parser.add_argument("--canonical", required=True, type=Path)
    parser.add_argument("--annotator-a", required=True, type=Path)
    parser.add_argument("--annotator-b", required=True, type=Path)
    parser.add_argument("--seed", default="provenlattice-fidelity-v1-blind")
    args = parser.parse_args()
    canonical = json.loads(args.canonical.read_text(encoding="utf-8"))
    if canonical.get("status") != "PILOT_GOLD_SET_READY_FOR_ANNOTATION":
        parser.error("canonical package is not ready for annotation")
    write_view(canonical["cases"], "A", args.seed, args.annotator_a)
    write_view(canonical["cases"], "B", args.seed, args.annotator_b)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

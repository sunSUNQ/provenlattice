from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
from collections.abc import Iterable
from pathlib import Path


RELATION_TYPES = ("CALLS", "IMPORTS", "REFERENCES")


def _open_read_only(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _decode(value: str | None) -> list[str]:
    if not value:
        return []
    parsed = json.loads(value)
    return parsed if isinstance(parsed, list) else []


def _case_id(repository: str, reference_id: str) -> str:
    digest = hashlib.sha256(f"{repository}:{reference_id}".encode()).hexdigest()[:16]
    return f"FQV1-{repository}-{digest}"


def _sample(rows: list[sqlite3.Row], count: int, seed: str) -> list[sqlite3.Row]:
    ordered = sorted(rows, key=lambda row: row["id"])
    random.Random(seed).shuffle(ordered)
    return ordered[:count]


def _load_rows(connection: sqlite3.Connection, relation: str, statuses: Iterable[str]) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in statuses)
    return list(connection.execute(
        f"""SELECT r.id, r.raw_name, r.reference_type, r.target_module,
                    r.start_line, r.end_line, r.status, r.candidate_symbols,
                    r.resolved_symbol_id, r.resolution_strategy, r.provenance,
                    r.confidence, source_file.path AS source_path,
                    owner.kind AS owner_kind, owner.qualified_name AS owner_qualified_name,
                    target.kind AS target_kind, target.qualified_name AS target_qualified_name,
                    target_file.path AS target_path, target.start_line AS target_start_line,
                    target.end_line AS target_end_line
             FROM raw_references r
             JOIN files source_file ON source_file.file_id=r.file_id
             JOIN nodes owner ON owner.id=r.owner_symbol_id
             LEFT JOIN nodes target ON target.id=r.resolved_symbol_id
             LEFT JOIN files target_file ON target_file.file_id=target.file_id
             WHERE r.reference_type=? AND r.status IN ({placeholders})""",
        (relation, *statuses),
    ))


def _to_case(repository: str, row: sqlite3.Row, stratum: str) -> dict:
    predicted = None
    if row["resolved_symbol_id"]:
        predicted = {
            "symbol_id": row["resolved_symbol_id"],
            "kind": row["target_kind"],
            "qualified_name": row["target_qualified_name"],
            "path": row["target_path"],
            "start_line": row["target_start_line"],
            "end_line": row["target_end_line"],
        }
    return {
        "case_id": _case_id(repository, row["id"]),
        "repository": repository,
        "raw_reference_id": row["id"],
        "stratum": stratum,
        "relation_type": row["reference_type"],
        "source": {
            "path": row["source_path"],
            "start_line": row["start_line"],
            "end_line": row["end_line"],
            "owner_kind": row["owner_kind"],
            "owner_qualified_name": row["owner_qualified_name"],
            "raw_name": row["raw_name"],
            "target_module": row["target_module"],
        },
        "system": {
            "status": row["status"],
            "resolution_strategy": row["resolution_strategy"],
            "provenance": row["provenance"],
            "confidence": row["confidence"],
            "predicted_target": predicted,
            "candidate_symbol_ids": _decode(row["candidate_symbols"]),
        },
        "build_context": {
            "build_context_available": None,
            "compile_commands_available": None,
            "build_target": None,
            "platform": None,
            "preprocessor_context": None,
            "generated_source_policy": None,
        },
        "annotation": {
            "status": "PENDING",
            "gold_relation_exists": None,
            "gold_target_symbol_id": None,
            "gold_target_path": None,
            "gold_target_start_line": None,
            "relation_correct": None,
            "abstention_correct": None,
            "difficulty_tags": [],
            "evidence_notes": None,
            "annotator_a": None,
            "annotator_b": None,
            "adjudicator": None,
        },
    }


def build_pilot(
    databases: dict[str, Path],
    positives_per_stratum: int = 20,
    negatives_per_stratum: int = 10,
    seed: str = "provenlattice-fidelity-v1",
) -> dict:
    cases: list[dict] = []
    availability: list[dict] = []
    for repository, database in sorted(databases.items()):
        with _open_read_only(database) as connection:
            for relation in RELATION_TYPES:
                strata = (
                    (f"{relation}_RESOLVED", ("resolved",), positives_per_stratum),
                    (f"{relation}_NONRESOLVED", ("ambiguous", "unresolved"), negatives_per_stratum),
                )
                for stratum, statuses, requested in strata:
                    rows = _load_rows(connection, relation, statuses)
                    selected = _sample(rows, requested, f"{seed}:{repository}:{stratum}")
                    cases.extend(_to_case(repository, row, stratum) for row in selected)
                    availability.append({
                        "repository": repository,
                        "database": str(database),
                        "stratum": stratum,
                        "requested": requested,
                        "available": len(rows),
                        "selected": len(selected),
                        "quota_met": len(selected) == requested,
                    })
    return {
        "benchmark_id": "provenlattice-fidelity-v1-pilot",
        "schema_version": 1,
        "seed": seed,
        "sampling_scope": {
            "language": "C/C++",
            "repositories": sorted(databases),
            "relation_types": list(RELATION_TYPES),
            "sampling_strata": "resolved and nonresolved (ambiguous/unresolved) RawReference cases",
            "positive_target_per_stratum": positives_per_stratum,
            "hard_negative_target_per_stratum": negatives_per_stratum,
        },
        "availability": availability,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the C/C++ Graph Fidelity V1 pilot annotation package."
    )
    parser.add_argument(
        "--database", action="append", required=True, metavar="NAME=PATH",
        help="Read-only V0.2 graph database for one repository; repeat for every repository.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--positive-per-stratum", type=int, default=20)
    parser.add_argument("--negative-per-stratum", type=int, default=10)
    parser.add_argument("--seed", default="provenlattice-fidelity-v1")
    args = parser.parse_args()

    databases: dict[str, Path] = {}
    for value in args.database:
        name, separator, raw_path = value.partition("=")
        if not separator or not name or not raw_path:
            parser.error(f"invalid --database value: {value!r}; expected NAME=PATH")
        path = Path(raw_path)
        if not path.is_file():
            parser.error(f"database does not exist: {path}")
        databases[name] = path
    if args.positive_per_stratum < 1 or args.negative_per_stratum < 1:
        parser.error("per-stratum targets must be positive")

    result = build_pilot(
        databases, args.positive_per_stratum, args.negative_per_stratum, args.seed
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "benchmark_id": result["benchmark_id"],
        "cases": len(result["cases"]),
        "quota_failures": [item for item in result["availability"] if not item["quota_met"]],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

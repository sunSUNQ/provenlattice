from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from provenlattice.parser import parse_file_with_diagnostics
from provenlattice.scanner import scan_repository


def classify(raw_name: str, reference_type: str) -> str:
    if reference_type == "IMPORTS":
        return "include"
    if "<" in raw_name or ">" in raw_name:
        return "template_or_cast"
    if "." in raw_name or "->" in raw_name:
        return "member_or_qualified_call"
    if re.fullmatch(r"[A-Z][A-Z0-9_]+", raw_name):
        return "macro_like_call"
    if raw_name.startswith("operator"):
        return "operator_call"
    return "simple_call"


def analyze(repo: Path, database: Path, result_path: Path) -> dict:
    sources = scan_repository(repo)
    syntax_errors: Counter[str] = Counter()
    for source in sources:
        _, has_error = parse_file_with_diagnostics(
            source.path, source.relative_path, source.language
        )
        if has_error:
            syntax_errors[source.path.suffix.lower() or "<none>"] += 1

    with closing(sqlite3.connect(database)) as connection:
        status_by_type = {
            f"{status}:{reference_type}": count
            for status, reference_type, count in connection.execute(
                "SELECT status, reference_type, COUNT(*) FROM raw_references "
                "GROUP BY status, reference_type ORDER BY status, reference_type"
            )
        }
        strategy_status = {
            f"{strategy}:{status}": count
            for strategy, status, count in connection.execute(
                "SELECT resolution_strategy, status, COUNT(*) FROM raw_references "
                "GROUP BY resolution_strategy, status ORDER BY resolution_strategy, status"
            )
        }
        unresolved_shapes = Counter(
            classify(raw_name, reference_type)
            for raw_name, reference_type in connection.execute(
                "SELECT raw_name, reference_type FROM raw_references WHERE status='unresolved'"
            )
        )
        ambiguous_shapes = Counter(
            classify(raw_name, reference_type)
            for raw_name, reference_type in connection.execute(
                "SELECT raw_name, reference_type FROM raw_references WHERE status='ambiguous'"
            )
        )

    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["diagnostics"] = {
        "syntax_error_files_by_extension": dict(sorted(syntax_errors.items())),
        "reference_status_by_type": status_by_type,
        "resolution_strategy_status": strategy_status,
        "unresolved_shape": dict(unresolved_shapes.most_common()),
        "ambiguous_shape": dict(ambiguous_shapes.most_common()),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case", action="append", required=True,
        help="name|repository-path|database-path|result-json",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cases = []
    for item in args.case:
        name, repo, database, result = item.split("|", 3)
        analyzed = analyze(Path(repo), Path(database), Path(result))
        analyzed["benchmark"] = name
        cases.append(analyzed)
    output = {"schema_version": 1, "benchmarks": cases}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build a frozen query manifest (QUERY_MANIFEST_V1) for systems workload D.

Selection is deterministic: the top-K functions by CALLS degree (ties broken by
qualified_name), plus K functions chosen by name-ascending order. The manifest
records symbol NAMES only (path-independent); the runner re-resolves anchors at
session start via GraphQuery.find_symbol with the same deterministic ordering.

Usage:
  python tools/build-query-manifest-v1.py --benchmark B1-aria2 --database <db path>
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFESTS_DIR = HERE.parent / "manifests"

TOP_DEGREE_SQL = """
WITH call_degree AS (
    SELECT src_id AS node_id, COUNT(*) AS degree
    FROM edges WHERE type='CALLS' GROUP BY src_id
    UNION ALL
    SELECT dst_id AS node_id, COUNT(*) AS degree
    FROM edges WHERE type='CALLS' GROUP BY dst_id
)
SELECT n.name, n.qualified_name, n.id, call_degree.degree
FROM call_degree JOIN nodes n ON n.id=call_degree.node_id
WHERE n.kind IN ('Function','Method')
ORDER BY call_degree.degree DESC, n.qualified_name
LIMIT ?
"""

NAME_ORDER_SQL = """
SELECT name, qualified_name, id, 0 AS degree
FROM nodes
WHERE kind IN ('Function','Method')
ORDER BY name, qualified_name
LIMIT ?
"""


def build(database: Path, benchmark: str, top_degree: int, name_order: int) -> dict:
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        top = [dict(row) for row in connection.execute(TOP_DEGREE_SQL, (top_degree,))]
        by_name = [dict(row) for row in connection.execute(NAME_ORDER_SQL, (name_order,))]

    chosen: dict = {}
    for row in top:
        chosen[row["qualified_name"]] = row
    for row in by_name:
        chosen.setdefault(row["qualified_name"], row)

    queries = []
    for qualified_name in sorted(chosen):
        name = chosen[qualified_name]["name"]
        for query_type in ("symbol", "callers", "callees", "subgraph"):
            queries.append({"type": query_type, "name": name, "anchor": qualified_name})

    manifest = {
        "manifest": "QUERY_MANIFEST_V1",
        "version": 2,
        "benchmark": benchmark,
        "note": "anchors are frozen qualified names; the runner must resolve each name to a candidate whose qualified_name equals the anchor string, else the run fails. No machine-local paths are recorded (review R11).",
        "selection_policy": {
            "top_degree_by_calls": top_degree,
            "name_ascending": name_order,
            "tie_break": "qualified_name ASC",
            "kinds": ["Function", "Method"],
            "query_types": ["symbol", "callers", "callees", "subgraph"],
        },
        "source_provenance": {
            "benchmark": benchmark,
            "selection": "deterministic top-degree + name-ascending policy above, computed from a full index of the frozen commit",
            "database": "temporary selection DB (discarded; portable provenance only)"
        },
        "queries": queries,
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--benchmark", required=True,
                        choices=("B1-aria2", "B2-brpc", "B3-rocksdb"))
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--top-degree", type=int, default=3)
    parser.add_argument("--name-order", type=int, default=2)
    parser.add_argument("--output")
    args = parser.parse_args()

    manifest = build(args.database, args.benchmark, args.top_degree, args.name_order)
    output = Path(args.output) if args.output else \
        MANIFESTS_DIR / f"queries-{args.benchmark.split('-')[1]}-v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(output), "queries": len(manifest["queries"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

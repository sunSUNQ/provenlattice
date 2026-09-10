from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from provenlattice.graph import full_index
from provenlattice.incremental import incremental_update
from provenlattice.shard import StructuralShardStrategy


def boundary_edge_ids(database: Path) -> set[str]:
    with closing(sqlite3.connect(database)) as connection:
        result = {
            row[0] for row in connection.execute(
                "SELECT id FROM edges WHERE json_extract(metadata, '$.scope')='boundary'"
            )
        }
        return result


def snapshot(database: Path) -> dict[str, list[dict]]:
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        result = {}
        for table in ("nodes", "edges", "raw_references", "shards", "shard_edges"):
            result[table] = []
            for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1"):
                item = dict(row)
                item.pop("generation", None)
                item.pop("boundary_dirty", None)
                result[table].append(item)
        return result


def select_cross_edge(database: Path) -> tuple[str, str, str]:
    with closing(sqlite3.connect(database)) as connection:
        row = connection.execute(
            """SELECT json_extract(e.metadata, '$.raw_reference_id'),
                      owner.metadata, target.qualified_name
               FROM edges e JOIN raw_references r
                    ON json_extract(e.metadata, '$.raw_reference_id')=r.id
               JOIN nodes owner ON owner.id=r.owner_symbol_id
               JOIN nodes target ON target.id=r.resolved_symbol_id
               WHERE e.type='CALLS' AND json_extract(e.metadata, '$.scope')='boundary'
                 AND r.status='resolved' LIMIT 1"""
        ).fetchone()
    if row is None:
        raise RuntimeError("baseline has no resolved cross-shard CALLS edge")
    metadata = json.loads(row[1])
    return metadata["relative_path"], row[2], row[0]


def apply_mutation(root: Path, name: str, cross_path: str | None = None, target: str | None = None) -> None:
    source = root / "src" / "AbstractCommand.cc"
    if name == "M1-local-body":
        text = source.read_text(encoding="utf-8")
        marker = "/* provenlattice-v03-local-body */"
        if marker not in text:
            text = text.replace("req_.reset();", f"req_.reset(); {marker}", 1)
        source.write_text(text, encoding="utf-8")
    elif name == "M2-internal-call":
        source.write_text(
            source.read_text(encoding="utf-8")
            + "\nstatic void _pl_v03_internal_helper() {}\n"
            "static void _pl_v03_internal_entry() { _pl_v03_internal_helper(); }\n",
            encoding="utf-8",
        )
    elif name == "M3-public-signature":
        text = source.read_text(encoding="utf-8")
        updated = text.replace("AbstractCommand::resetRequest()", "AbstractCommand::resetRequest(int v)", 1)
        if updated == text:
            raise RuntimeError("M3 signature marker not found")
        source.write_text(updated, encoding="utf-8")
    elif name in {"M4-cross-shard-add", "M5-cross-shard-remove"}:
        if cross_path is None or target is None:
            raise RuntimeError("cross-shard mutation target is missing")
        path = root / cross_path
        marker = "// provenlattice-v03-cross-shard\n"
        target_cpp = re.sub(r"(?<!:)\.", "::", target)
        block = f"\n{marker}void _pl_v03_cross_call() {{ {target_cpp}(); }}\n"
        text = path.read_text(encoding="utf-8")
        if name == "M4-cross-shard-add" and marker not in text:
            path.write_text(text + block, encoding="utf-8")
        elif name == "M5-cross-shard-remove":
            path.write_text(text.replace(block, ""), encoding="utf-8")
    else:
        raise ValueError(name)


def run_case(base: Path, name: str, cross_path: str, target: str) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"pl-v03-{name}-") as temp:
        root = Path(temp) / "aria2"
        shutil.copytree(base, root)
        incremental_db = Path(temp) / "incremental.db"
        full_db = Path(temp) / "full.db"
        strategy = StructuralShardStrategy()
        if name == "M5-cross-shard-remove":
            apply_mutation(root, "M4-cross-shard-add", cross_path, target)
            full_index(root, incremental_db, strategy=strategy)
            before_boundary = boundary_edge_ids(incremental_db)
            apply_mutation(root, name, cross_path, target)
        else:
            full_index(root, incremental_db, strategy=strategy)
            before_boundary = boundary_edge_ids(incremental_db)
            apply_mutation(root, name, cross_path, target)
        update = incremental_update(root, incremental_db, strategy=StructuralShardStrategy())
        full_index(root, full_db, strategy=StructuralShardStrategy())
        after_boundary = boundary_edge_ids(full_db)
        old_fp = update["delta"]["old_api_fingerprint"]
        new_fp = update["delta"]["new_api_fingerprint"]
        result = {
            "mutation": name,
            "parity": snapshot(incremental_db) == snapshot(full_db),
            "api_fingerprint_changed": old_fp != new_fp,
            "boundary_edge_added": len(after_boundary - before_boundary),
            "boundary_edge_removed": len(before_boundary - after_boundary),
            "delta": update["delta"],
            "metrics": update["metrics"],
        }
    result["clean_restored"] = not root.exists()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--baseline-db", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cross_path, target, _ = select_cross_edge(args.baseline_db)
    names = ["M1-local-body", "M2-internal-call", "M3-public-signature",
             "M4-cross-shard-add", "M5-cross-shard-remove"]
    results = [run_case(args.repo.resolve(), name, cross_path, target) for name in names]
    output = {"schema_version": 1, "repository": str(args.repo.resolve()), "mutations": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

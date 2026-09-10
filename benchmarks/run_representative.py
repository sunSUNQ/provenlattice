from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from provenlattice.graph import full_index
from provenlattice.incremental import incremental_update
from provenlattice.shard import StructuralShardStrategy
from run_mutations import snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--file", required=True, help="repository-relative C/C++ file")
    parser.add_argument("--name", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=f"pl-v03-{args.name}-") as temp:
        root = Path(temp) / args.repo.name
        shutil.copytree(args.repo, root)
        incremental_db = Path(temp) / "incremental.db"
        full_db = Path(temp) / "full.db"
        full_index(root, incremental_db, strategy=StructuralShardStrategy())
        target = root / args.file
        target.write_text(target.read_text(encoding="utf-8") + "\n// provenlattice-v03-representative-body\n", encoding="utf-8")
        update = incremental_update(root, incremental_db, strategy=StructuralShardStrategy())
        full_index(root, full_db, strategy=StructuralShardStrategy())
        result = {
            "mutation": args.name,
            "file": args.file,
            "parity": snapshot(incremental_db) == snapshot(full_db),
            "metrics": update["metrics"],
            "delta": {k: update["delta"][k] for k in ("nodes_added", "nodes_removed", "nodes_updated", "edges_added", "edges_removed", "boundary_dirty", "impact_frontier_size", "wide_impact")},
        }
    result["clean_restored"] = not root.exists()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

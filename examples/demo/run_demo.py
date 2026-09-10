"""Run index -> query -> modify -> incremental update -> updated query safely in a temp copy."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from provenlattice.graph import full_index
from provenlattice.incremental import incremental_update
from provenlattice.query import GraphQuery


def main() -> None:
    fixture = Path(__file__).parent / "repository"
    with tempfile.TemporaryDirectory() as directory:
        repo = Path(directory) / "demo-repo"
        shutil.copytree(fixture, repo)
        database = Path(directory) / "demo.db"
        print("INDEX", json.dumps(full_index(repo, database), indent=2))
        with GraphQuery(database) as query:
            print("QUERY", json.dumps(query.get_callees("module_a.app.calculate"), indent=2))
        target = repo / "module_b" / "maths.py"
        target.write_text(
            "def double(value: int) -> int:\n    return value * 3\n\n"
            "def triple(value: int) -> int:\n    return value * 3\n",
            encoding="utf-8",
        )
        print("UPDATE", json.dumps(incremental_update(repo, database), indent=2))
        with GraphQuery(database) as query:
            print("UPDATED QUERY", json.dumps(query.find_symbol("triple"), indent=2))


if __name__ == "__main__":
    main()

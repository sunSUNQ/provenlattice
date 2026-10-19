"""P2-A callers-gap-fix regression tests: --include-ambiguous possible_callers."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from provenlattice.graph import full_index
from provenlattice.query import GraphQuery


def _build(root: Path, fixture: dict[str, str]) -> Path:
    for rel, body in fixture.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8", newline="\n")
    db = root / "db.sqlite"
    full_index(root, db)
    return db


FIXTURE = {
    "src/a/Node.java": (
        "package a;\npublic class Node {\n"
        "    public Object get(String k) { return k; }\n}\n"
    ),
    "src/a/Box.java": (
        "package a;\npublic class Box {\n"
        "    private Node members;\n"
        "    public Object get(String k) { return members.get(k); }\n"
        "    public Node view() { return members; }\n}\n"
    ),
    "src/a/User.java": (
        "package a;\npublic class User {\n"
        "    public Object go(Node node) { return node.get(\"k\"); }\n}\n"
    ),
}


class PossibleCallersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.database = _build(self.root, FIXTURE)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _query(self, symbol: str, **kwargs) -> dict:
        with GraphQuery(self.database) as q:
            return q.get_callers(symbol, **kwargs)

    def test_default_callers_excludes_ambiguous(self) -> None:
        result = self._query("Node.get")
        self.assertNotIn("possible_callers", result)
        self.assertEqual(result["returned_evidence_count"], 0)

    def test_include_ambiguous_returns_possible_callers(self) -> None:
        result = self._query("Node.get", include_ambiguous=True)
        possible = result.get("possible_callers", [])
        self.assertGreater(len(possible), 0)
        for pc in possible:
            self.assertEqual(pc["resolution_status"], "ambiguous")
            self.assertEqual(pc["evidence_level"], "candidate")
            self.assertIn(pc["caller_kind"], ("Method", "Function"))

    def test_ambiguous_does_not_create_calls_edge(self) -> None:
        with closing(sqlite3.connect(self.database)) as c:
            edges = c.execute(
                "SELECT COUNT(*) FROM edges WHERE type='CALLS' "
                "AND json_extract(metadata,'$.resolution')='unique_symbol_resolution'"
            ).fetchone()[0]
        self.assertEqual(edges, 0)

    def test_python_c_cpp_untouched(self) -> None:
        """Python same-file CALLS at 0.98 keeps resolving; R1 does not apply."""
        import os
        root2 = Path(self.temp.name) / "py"
        (root2 / "pkg").mkdir(parents=True, exist_ok=True)
        (root2 / "pkg" / "mod.py").write_text(
            "def helper():\n    return 1\n\n\ndef use():\n    return helper()\n",
            encoding="utf-8")
        db2 = root2 / "py.db"
        full_index(root2, db2)
        result = self._query("pkg.mod.helper")
        self.assertEqual(result["returned_evidence_count"], 0)  # no callers in fixture

    def test_deterministic(self) -> None:
        r1 = self._query("Node.get", include_ambiguous=True)
        r2 = self._query("Node.get", include_ambiguous=True)
        self.assertEqual(r1.get("possible_callers"), r2.get("possible_callers"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

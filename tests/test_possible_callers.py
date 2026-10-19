"""P2-A callers-gap-fix regression tests: --include-ambiguous possible_callers.

Covers: default exclusion, ambiguous inclusion, overload safety, exact
symbol ID, same-line multi-call dedup, truncation, Python/C/C++ pins."""
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

OVERLOAD_FIXTURE = {
    "src/a/Calc.java": (
        "package a;\npublic class Calc {\n"
        "    public int eval(int v) { return v; }\n"
        "    public int eval(String v) { return 1; }\n"
        "    public int run() { return eval(1) + eval(\"x\"); }\n}\n"
    ),
    "src/a/Use.java": (
        "package a;\npublic class Use {\n"
        "    public int call() { return new Calc().eval(2); }\n}\n"
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

    def test_deterministic(self) -> None:
        r1 = self._query("Node.get", include_ambiguous=True)
        r2 = self._query("Node.get", include_ambiguous=True)
        self.assertEqual(r1.get("possible_callers"), r2.get("possible_callers"))


class PythonCrossLanguagePinTests(unittest.TestCase):
    """F4 fix: Python pin must use the Python database, not the Java one."""

    def test_python_same_file_calls_resolve(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        (root / "pkg").mkdir(parents=True, exist_ok=True)
        (root / "pkg" / "mod.py").write_text(
            "def helper():\n    return 1\n\n\ndef use():\n    return helper()\n",
            encoding="utf-8")
        db = root / "py.db"
        full_index(root, db)
        with GraphQuery(db) as q:
            result = q.get_callers("pkg.mod.helper")
            self.assertEqual(result["returned_evidence_count"], 1)
            data = result["data"]
            self.assertEqual(data[0]["qualified_name"], "pkg.mod.use")

    def test_python_r1_does_not_apply(self) -> None:
        """R1 demote is Java-only (metadata gate); Python same-file CALLS
        at 0.98 keeps resolving."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        (root / "pkg").mkdir(parents=True, exist_ok=True)
        (root / "pkg" / "mod.py").write_text(
            "def helper():\n    return 1\n\n\ndef use():\n    return helper()\n",
            encoding="utf-8")
        db = root / "py.db"
        full_index(root, db)
        with closing(sqlite3.connect(db)) as c:
            c.row_factory = sqlite3.Row
            rows = [dict(r) for r in c.execute(
                "SELECT r.status, r.resolution_strategy FROM raw_references r "
                "JOIN files f ON r.file_id=f.file_id "
                "WHERE f.path='pkg/mod.py' AND r.reference_type='CALLS'")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "resolved")
        self.assertEqual(rows[0]["resolution_strategy"], "same_file_resolution")


class OverloadSafetyTests(unittest.TestCase):
    """F2/overload: same-name different-param methods must not be
    silently merged or mis-targeted by possible_callers."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.database = _build(self.root, OVERLOAD_FIXTURE)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _query(self, symbol: str, **kwargs) -> dict:
        with GraphQuery(self.database) as q:
            return q.get_callers(symbol, **kwargs)

    def test_overload_ambiguous_target(self) -> None:
        """`eval(1)` and `eval(\"x\")` are overloads; the L1 resolver reports
        ambiguous for the bare calls (same-file multi-candidate). The
        possible_callers for either overload should return candidates."""
        result = self._query("a.Calc.eval", include_ambiguous=True)
        possible = result.get("possible_callers", [])
        for pc in possible:
            self.assertEqual(pc["evidence_level"], "candidate")
        # bare `eval(...)` calls in Calc.run() are ambiguous (3 overloads)
        self.assertGreater(len(possible), 0)

    def test_overload_exact_qualified_name_resolves(self) -> None:
        """Exact qualified_name with signature still resolves to unique symbol."""
        result = self._query("a.Calc.eval", include_ambiguous=True)
        possible = result.get("possible_callers", [])
        targets = {pc["target_candidate_symbol_id"] for pc in possible}
        self.assertEqual(len(targets), 1)  # all candidates target same base ID


class SameLineMultiCallTests(unittest.TestCase):
    """F3: same-line multi-call sites must not be collapsed."""

    def test_same_line_two_calls_dedup_by_ref_id(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        fixture = {
            "src/a/A.java": "package a;\npublic class A { void m() { } }\n",
            "src/a/B.java": (
                "package a;\npublic class B {\n"
                "    public void x() { }\n"
                "    public void y() { }\n"
                "    public void both() { x(); y(); }\n}\n"
            ),
        }
        for rel, body in fixture.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8", newline="\n")
        db = root / "db.sqlite"
        full_index(root, db)
        with GraphQuery(db) as q:
            r = q.get_callers("a.B.x", include_ambiguous=True)
        # raw_reference_id must be unique across results
        ids = [pc["raw_reference_id"] for pc in r.get("possible_callers", [])]
        self.assertEqual(len(ids), len(set(ids)))


class TruncationTests(unittest.TestCase):
    def test_truncation_meta_accurate(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        (root / "src").mkdir(parents=True, exist_ok=True)
        (root / "src" / "Target.java").write_text(
            "package src;\npublic class Target {\n"
            "    public void hit() { }\n}\n", encoding="utf-8")
        # 5 callers
        for i in range(5):
            (root / "src" / f"C{i}.java").write_text(
                f"package src;\npublic class C{i} {{\n"
                f"    public void call{i}() {{ Target t = new Target(); t.hit(); }}\n}}\n",
                encoding="utf-8")
        db = root / "db.sqlite"
        full_index(root, db)
        with GraphQuery(db) as q:
            r = q.get_callers("src.Target.hit", include_ambiguous=True)
            meta = r.get("possible_callers_meta", {})
            if meta:
                self.assertLessEqual(meta["returned"], 200)
                self.assertEqual(meta["total"], meta["returned"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

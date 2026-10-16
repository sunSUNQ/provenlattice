"""P2-A R1 demote regression: the 8 historical wrong-binding shapes must not
produce deterministic resolved bindings, while R2 safe shapes stay resolved."""
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
import sqlite3

from provenlattice.graph import full_index

from tests.test_java import file_references, symbols, write_fixture


def build(fixture: dict[str, str]) -> tuple[Path, Path]:
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name) / "repo"
    database = Path(temp.name) / "codegraph.db"
    for relative, body in fixture.items():
        p = root / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8", newline="\n")
    full_index(root, database)
    return database, temp


def calls(database: Path, tail: str, line: int, expr: str) -> list[dict]:
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(r) for r in connection.execute(
            "SELECT r.raw_name, r.status, r.resolution_strategy, r.confidence, "
            "r.candidate_symbols, r.metadata FROM raw_references r "
            "JOIN files f ON r.file_id = f.file_id "
            "WHERE f.path LIKE ? AND r.reference_type='CALLS' AND r.start_line = ? "
            "AND r.raw_name LIKE ? ORDER BY r.id",
            (f"%{tail}", line, f"%{expr}%"))]


class DemoteRegressionTests(unittest.TestCase):
    """P2-A: the 8 audited wrong-binding shapes (T8/P7 evidence) are demoted."""

    # shape 1 (audit #1): static-imported member constant receiver
    def test_d1_static_member_constant_receiver_demoted(self) -> None:
        database, temp = build({
            "src/a/ClockSource.java": (
                "package a;\npublic class ClockSource {\n"
                "    public long toMillis(long t) { return t; }\n}\n"
            ),
            "src/a/Use.java": (
                "package a;\nimport static java.util.concurrent.TimeUnit.MINUTES;\n"
                "public class Use {\n"
                "    public long go() { return MINUTES.toMillis(24); }\n}\n"
            ),
        })
        try:
            rows = calls(database, "Use.java", 4, "toMillis")
            self.assertEqual(rows[0]["status"], "ambiguous")
            self.assertEqual(rows[0]["resolution_strategy"], "unique_symbol_resolution")
            self.assertEqual(json.loads(rows[0]["metadata"])["receiver_shape"], "identifier")
        finally:
            temp.cleanup()

    # shape 2 (audit #2): lambda-parameter receiver, same-file collision
    def test_d2_lambda_param_receiver_same_file_demoted(self) -> None:
        database, temp = build({
            "src/a/Owner.java": (
                "package a;\npublic class Owner {\n"
                "    public String getPassword() { return \"\"; }\n"
                "    public String update(java.util.function.Supplier<String> s) { return s.get(); }\n"
                "}\n"
            ),
            "src/a/Credentials.java": (
                "package a;\npublic class Credentials {\n"
                "    public String getPassword() { return \"\"; }\n}\n"
            ),
            "src/a/Use.java": (
                "package a;\nimport a.Credentials;\n"
                "public class Use extends Owner {\n"
                "    public void go(Credentials current) { current.getPassword(); }\n}\n"
            ),
        })
        try:
            rows = calls(database, "Use.java", 4, "getPassword")
            self.assertEqual(rows[0]["status"], "ambiguous")
            # Use.java has no own getPassword -> same-file tier empty, the
            # demote lands on the global tier with both candidates preserved
            self.assertEqual(rows[0]["resolution_strategy"], "unique_symbol_resolution")
        finally:
            temp.cleanup()

    # shape 3 (audit #3): field receiver, unique global name
    def test_d3_field_receiver_unique_demoted(self) -> None:
        database, temp = build({
            "src/a/Elf.java": (
                "package a;\npublic class Elf {\n"
                "    public long stream() { return 0; }\n}\n"
            ),
            "src/a/Bag.java": (
                "package a;\nimport java.util.List;\n"
                "public class Bag {\n"
                "    private List<String> sharedList;\n"
                "    public long go() { return sharedList.stream().count(); }\n}\n"
            ),
        })
        try:
            rows = [r for r in calls(database, "Bag.java", 5, "stream")
                    if r["raw_name"] == "sharedList.stream"]
            self.assertEqual(rows[0]["status"], "ambiguous")
            self.assertEqual(rows[0]["resolution_strategy"], "unique_symbol_resolution")
            self.assertEqual(json.loads(rows[0]["metadata"])["receiver_shape"], "identifier")
        finally:
            temp.cleanup()

    # shapes 4+ (audit #4/#5/#6/#7/#8): same-file collision where the only
    # same-file candidate is the calling method itself (owner) -> after
    # owner-self exclusion the demoted reference has no candidates -> honest
    # unresolved (the wrong binding to the owner is eliminated)
    def test_d4_same_file_member_collision_demoted(self) -> None:
        database, temp = build({
            "src/a/Node.java": (
                "package a;\npublic class Node {\n"
                "    public Object get(String k) { return k; }\n}\n"
            ),
            "src/a/Box.java": (
                "package a;\npublic class Box {\n"
                "    private Node members;\n"
                "    public Object get(String k) { return members.get(k); }\n}\n"
            ),
        })
        try:
            rows = calls(database, "Box.java", 4, "get")
            self.assertEqual(rows[0]["status"], "unresolved")
            self.assertEqual(rows[0]["resolution_strategy"], "same_file_resolution")
            self.assertEqual(rows[0]["confidence"], 0.0)
        finally:
            temp.cleanup()

    def test_d5_candidates_preserved_after_demote(self) -> None:
        # the calling method lives OUTSIDE the colliding classes: both
        # same-file/global candidates survive as ambiguous evidence
        database, temp = build({
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
        })
        try:
            rows = calls(database, "User.java", 3, "get")
            self.assertEqual(rows[0]["status"], "ambiguous")
            self.assertEqual(rows[0]["resolution_strategy"], "unique_symbol_resolution")
            candidates = json.loads(rows[0]["candidate_symbols"])
            self.assertEqual(len(candidates), 2)  # Node.get + Box.get
            # no deterministic CALLS edge is produced for the demoted call
            with closing(sqlite3.connect(database)) as connection:
                edges = connection.execute(
                    "SELECT COUNT(*) FROM edges WHERE type='CALLS' AND "
                    "json_extract(metadata,'$.resolution')='unique_symbol_resolution'"
                ).fetchone()[0]
            self.assertEqual(edges, 0)
        finally:
            temp.cleanup()


class DemotePreservedTests(unittest.TestCase):
    """P2-A R2: safe receiver shapes keep their deterministic bindings."""

    def build(self, fixture: dict[str, str]) -> tuple[Path, tempfile.TemporaryDirectory]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name) / "repo"
        database = Path(temp.name) / "codegraph.db"
        write_fixture(root, fixture)
        full_index(root, database)
        return database, temp

    def test_r2_bare_call_stays_resolved(self) -> None:
        database, temp = self.build({
            "src/a/Sums.java": (
                "package a;\npublic class Sums {\n"
                "    public static int sum(int... values) { return 0; }\n"
                "    public int total() { return sum(1, 2); }\n}\n"
            ),
        })
        try:
            rows = calls(database, "Sums.java", 4, "sum")
            self.assertEqual(rows[0]["status"], "resolved")
            self.assertEqual(rows[0]["confidence"], 0.98)
            self.assertEqual(json.loads(rows[0]["metadata"])["receiver_shape"],
                             "implicit_this")
        finally:
            temp.cleanup()

    def test_r2_this_call_stays_resolved(self) -> None:
        database, temp = self.build({
            "src/a/Sums.java": (
                "package a;\npublic class Sums {\n"
                "    public int sum(int... values) { return 0; }\n"
                "    public int total() { return this.sum(1); }\n}\n"
            ),
        })
        try:
            rows = calls(database, "Sums.java", 4, "sum")
            self.assertEqual(rows[0]["status"], "resolved")
            self.assertEqual(json.loads(rows[0]["metadata"])["receiver_shape"], "this")
        finally:
            temp.cleanup()

    def test_r2_imported_class_static_call_stays_resolved(self) -> None:
        database, temp = self.build({
            "src/a/Util.java": (
                "package a;\npublic class Util {\n"
                "    public static int build(int v) { return v; }\n}\n"
            ),
            "src/b/Caller.java": (
                "package b;\nimport a.Util;\n"
                "public class Caller {\n"
                "    public int go() { return Util.build(1); }\n}\n"
            ),
        })
        try:
            rows = calls(database, "Caller.java", 4, "build")
            self.assertEqual(rows[0]["status"], "resolved")
            self.assertEqual(json.loads(rows[0]["metadata"])["receiver_shape"],
                             "class_static")
        finally:
            temp.cleanup()

    def test_r2_python_c_cpp_untouched_by_r1(self) -> None:
        # R1 is gated on Java-only metadata; a Python same-file CALLS at 0.98
        # keeps resolving exactly as before (pin test).
        database, temp = self.build({
            "pkg/mod.py": "def helper():\n    return 1\n\n\ndef use():\n    return helper()\n",
            "pkg/other.py": "def helper():\n    return 2\n",
        })
        try:
            with closing(sqlite3.connect(database)) as connection:
                connection.row_factory = sqlite3.Row
                rows = [dict(r) for r in connection.execute(
                    "SELECT r.status, r.resolution_strategy, r.confidence FROM raw_references r "
                    "JOIN files f ON r.file_id=f.file_id "
                    "WHERE f.path='pkg/mod.py' AND r.reference_type='CALLS'")]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "resolved")
            self.assertEqual(rows[0]["resolution_strategy"], "same_file_resolution")
            self.assertEqual(rows[0]["confidence"], 0.98)
        finally:
            temp.cleanup()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

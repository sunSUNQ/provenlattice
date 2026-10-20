"""Java AST + CFG analyzer tests."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from provenlattice.analysis_java_ast import analyze_ast_scope, ast_node_id
from provenlattice.analysis_java_cfg import analyze_cfg_scope
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


SIMPLE = {
    "src/Greet.java": (
        "package src;\npublic class Greet {\n"
        "    public String hello(String name) { return \"hello \" + name; }\n"
        "    public int add(int a, int b) { return a + b; }\n}\n"
    ),
}

CONTROL_FLOW = {
    "src/Flow.java": (
        "package src;\npublic class Flow {\n"
        "    public int sign(int v) {\n"
        "        if (v > 0) { return 1; }\n"
        "        else if (v < 0) { return -1; }\n"
        "        else { return 0; }\n"
        "    }\n"
        "    public int sum(int n) {\n"
        "        int total = 0;\n"
        "        for (int i = 0; i < n; i++) { total += i; }\n"
        "        return total;\n"
        "    }\n"
        "    public int countDown(int n) {\n"
        "        while (n > 0) { n--; }\n"
        "        return n;\n"
        "    }\n"
        "}\n"
    ),
}


class JavaASTTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.db = _build(self.root, SIMPLE)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_ast_scope_basic(self) -> None:
        r = analyze_ast_scope(self.root, "src", self.db)
        self.assertEqual(r["analyzer"], "ast:java")
        self.assertGreater(r["nodes_written"], 0)
        self.assertEqual(len(r["materialized"]), 1)
        self.assertEqual(r["skipped_unsupported"], [])

    def test_ast_deterministic(self) -> None:
        r1 = analyze_ast_scope(self.root, "src", self.db)
        r2 = analyze_ast_scope(self.root, "src", self.db)
        self.assertEqual(len(r2["reused"]), 1)
        self.assertEqual(len(r2["materialized"]), 0)

    def test_ast_cache_invalidation_on_source_change(self) -> None:
        r1 = analyze_ast_scope(self.root, "src", self.db)
        self.assertEqual(len(r1["materialized"]), 1)
        src = self.root / "src" / "Greet.java"
        src.write_text(
            src.read_text(encoding="utf-8").replace('"hello "', '"hi "'),
            encoding="utf-8", newline="\n")
        full_index(self.root, self.db)
        r2 = analyze_ast_scope(self.root, "src", self.db)
        self.assertEqual(len(r2["materialized"]), 1)
        self.assertEqual(len(r2["reused"]), 0)
        r3 = analyze_ast_scope(self.root, "src", self.db)
        self.assertEqual(len(r3["reused"]), 1)


class JavaCFGTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.db = _build(self.root, CONTROL_FLOW)
        analyze_ast_scope(self.root, "src", self.db)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_cfg_scope_basic(self) -> None:
        r = analyze_cfg_scope(self.root, "src", self.db)
        self.assertEqual(r["analyzer"], "cfg:java")
        self.assertGreater(r["methods_built"], 0)
        self.assertEqual(r["methods_skipped_unsupported_construct"], 0)

    def test_cfg_deterministic(self) -> None:
        r1 = analyze_cfg_scope(self.root, "src", self.db)
        r2 = analyze_cfg_scope(self.root, "src", self.db)
        self.assertEqual(len(r2["reused"]), 1)
        self.assertEqual(len(r2["materialized"]), 0)

    def test_cfg_cache_invalidation_on_source_change(self) -> None:
        r1 = analyze_cfg_scope(self.root, "src", self.db)
        self.assertEqual(r1["methods_built"], 3)
        src = self.root / "src" / "Flow.java"
        src.write_text(
            src.read_text(encoding="utf-8").replace("int total = 0;", "int total = 1;"),
            encoding="utf-8", newline="\n")
        full_index(self.root, self.db)
        analyze_ast_scope(self.root, "src", self.db)
        r2 = analyze_cfg_scope(self.root, "src", self.db)
        self.assertEqual(r2["methods_built"], 3)
        self.assertEqual(len(r2["reused"]), 0)
        self.assertEqual(len(r2["materialized"]), 1)

    def test_cfg_all_methods_built(self) -> None:
        r = analyze_cfg_scope(self.root, "src", self.db)
        self.assertEqual(r["methods_built"], 3)  # sign, sum, countDown
        self.assertEqual(r["methods_skipped_unsupported_construct"], 0)
        self.assertEqual(r["methods_skipped_unmatched_owner"], 0)


if __name__ == "__main__":
    unittest.main()

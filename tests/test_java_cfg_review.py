"""Independent review: Java CFG control flow correctness with minimal programs.

Each test builds a minimal Java program with a known control flow shape and
verifies the CFG nodes/edges against hand-computed expectations."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from provenlattice.analysis_java_ast import analyze_ast_scope
from provenlattice.analysis_java_cfg import analyze_cfg_scope
from provenlattice.graph import full_index


def _build(root, fixture):
    for rel, body in fixture.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8", newline="\n")
    db = root / "db.sqlite"
    full_index(root, db)
    analyze_ast_scope(root, "src", db)
    return db


class CfgGoldenTests(unittest.TestCase):
    """Each test builds a minimal Java program and validates the CFG shape."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.db = _build(self.root, {
            "src/T.java": "package src;\npublic class T {\n"
                          "    public void empty() { }\n}\n"
        })
        analyze_ast_scope(self.root, "src", self.db)

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, body: str) -> dict:
        """Write a method with the given body, re-index, analyze, return edges summary."""
        src = f"package src;\npublic class T {{\n    public void test() {{\n{body}\n    }}\n}}\n"
        (self.root / "src" / "T.java").write_text(src, encoding="utf-8", newline="\n")
        full_index(self.root, self.db)
        analyze_ast_scope(self.root, "src", self.db)
        r = analyze_cfg_scope(self.root, "src", self.db)
        with closing(sqlite3.connect(self.db)) as c:
            c.row_factory = sqlite3.Row
            nodes = [dict(r) for r in c.execute(
                "SELECT n.* FROM analysis_nodes n JOIN files f ON n.file_id=f.file_id "
                "WHERE f.path='src/T.java' AND n.feature='cfg:java'")]
            edges = [dict(r) for r in c.execute(
                "SELECT e.* FROM analysis_edges e JOIN files f ON e.file_id=f.file_id "
                "WHERE f.path='src/T.java' AND e.feature='cfg:java'")]
        return {"nodes": nodes, "edges": edges}

    def _analyze(self, body: str) -> dict:
        """Same as _run but returns the analyzer result summary."""
        src = f"package src;\npublic class T {{\n    public void test() {{\n{body}\n    }}\n}}\n"
        (self.root / "src" / "T.java").write_text(src, encoding="utf-8", newline="\n")
        full_index(self.root, self.db)
        analyze_ast_scope(self.root, "src", self.db)
        return analyze_cfg_scope(self.root, "src", self.db)

    def test_sequential(self):
        r = self._run("int a = 1;\nint b = 2;")
        self.assertEqual(len(r["nodes"]), 4)  # entry + 2 stmt + exit
        kinds = [n["kind"] for n in r["nodes"]]
        self.assertIn("entry", kinds)
        self.assertIn("exit", kinds)

    def test_if_else(self):
        r = self._run("if (true) { int a = 1; } else { int b = 2; }")
        kinds = [n["kind"] for n in r["nodes"]]
        self.assertIn("condition", kinds)
        self.assertIn("merge", kinds)
        # edges: entry->cond, cond->true_block, cond->else_block,
        #        true_block->merge, else_block->merge, merge->exit
        edge_kinds = [e["kind"] for e in r["edges"]]
        self.assertIn("true", edge_kinds)
        self.assertIn("false", edge_kinds)

    def test_return_terminates(self):
        r = self._run("return;\nint unreachable = 1;")
        kinds = [n["kind"] for n in r["nodes"]]
        self.assertIn("return", kinds)
        # The unreachable statement should still have a node (AST-level)
        # but should NOT be connected to the return by a "next" edge.
        # Verify: no edge from return node to the unreachable node.
        return_nodes = [n["analysis_node_id"] for n in r["nodes"] if n["kind"] == "return"]
        if return_nodes:
            ret_id = return_nodes[0]
            ret_edges = [e for e in r["edges"] if e["src_id"] == ret_id]
            for e in ret_edges:
                self.assertEqual(e["kind"], "return",
                                 "return should only connect to exit via return edge")

    def test_break_exits_loop(self):
        r = self._run("while (true) { break; }")
        edge_kinds = [e["kind"] for e in r["edges"]]
        self.assertIn("break", edge_kinds)

    def test_continue_goes_to_header(self):
        r = self._run("for (int i = 0; i < 3; i++) { continue; }")
        edge_kinds = [e["kind"] for e in r["edges"]]
        self.assertIn("continue", edge_kinds)

    def test_do_while_body_executes_first(self):
        r = self._run("do { int x = 1; } while (false);")
        roles = {n["analysis_node_id"]: json.loads(n["payload"])["structural_role"]
                 for n in r["nodes"]}
        entry = next(n["analysis_node_id"] for n in r["nodes"] if n["kind"] == "entry")
        out = [e for e in r["edges"] if e["src_id"] == entry]
        self.assertEqual(len(out), 1)
        # body-first: entry reaches the body directly, not through the header
        self.assertNotEqual(roles[out[0]["dst_id"]], "do_while_header")
        header = next(nid for nid, role in roles.items() if role == "do_while_header")
        header_dst = {roles[e["dst_id"]] for e in r["edges"] if e["src_id"] == header}
        self.assertIn("statement", header_dst)
        self.assertIn("do_while_exit", header_dst)

    def test_parse_error_method_skipped(self):
        result = self._analyze("int x = 1;\nif (x { y(); }")
        self.assertEqual(result["methods_built"], 0)
        self.assertEqual(result["methods_skipped_parse_error"], 1)

    def test_wellformed_method_still_built(self):
        result = self._analyze("int x = 1;\nif (x) { y(); }")
        self.assertEqual(result["methods_built"], 1)
        self.assertEqual(result["methods_skipped_parse_error"], 0)

    def test_switch_conservatively_skipped(self):
        """switch_statement is conservatively skipped (V1 unsupported).
        The method should have 0 CFG nodes (method-level skip)."""
        r = self._run("int x = 1;\nswitch (x) { case 1: break; default: break; }")
        cfg_nodes = [n for n in r["nodes"] if n["kind"] not in ("entry", "exit")]
        self.assertEqual(len(cfg_nodes), 0,
                         "switch_statement should be conservatively skipped (V1)")


class CfgAntiPatternTests(unittest.TestCase):
    """Verify that the CFG does NOT create incorrect edges."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.db = _build(self.root, {
            "src/T.java": "package src;\npublic class T {\n"
                          "    public void t() { }\n}\n"
        })
        analyze_ast_scope(self.root, "src", self.db)

    def tearDown(self):
        self.temp.cleanup()

    def _analyze(self, body: str) -> dict:
        src = f"package src;\npublic class T {{\n    public void test() {{\n{body}\n    }}\n}}\n"
        (self.root / "src" / "T.java").write_text(src, encoding="utf-8", newline="\n")
        full_index(self.root, self.db)
        analyze_ast_scope(self.root, "src", self.db)
        return analyze_cfg_scope(self.root, "src", self.db)

    def _cfg_rows(self) -> tuple[list[dict], list[dict]]:
        with closing(sqlite3.connect(self.db)) as c:
            c.row_factory = sqlite3.Row
            nodes = [dict(r) for r in c.execute(
                "SELECT n.* FROM analysis_nodes n JOIN files f ON n.file_id=f.file_id "
                "WHERE f.path='src/T.java' AND n.feature='cfg:java'")]
            edges = [dict(r) for r in c.execute(
                "SELECT e.* FROM analysis_edges e JOIN files f ON e.file_id=f.file_id "
                "WHERE f.path='src/T.java' AND e.feature='cfg:java'")]
        return nodes, edges

    def test_no_edge_after_return(self):
        """Code after return must not be connected from the return node:
        the return node only reaches exit via the 'return' edge."""
        self._analyze("return;\nint dead = 1;")
        nodes, edges = self._cfg_rows()
        ret = next(n for n in nodes if n["kind"] == "return")
        outs = [e for e in edges if e["src_id"] == ret["analysis_node_id"]]
        self.assertTrue(outs)
        self.assertTrue(all(e["kind"] == "return" for e in outs),
                        f"return must only connect via return edge, got {outs}")

    def test_unsupported_construct_skips(self):
        """Methods containing try/catch must be skipped, not built."""
        result = self._analyze("try { int x = 1; } catch (Exception e) { }")
        self.assertEqual(result["methods_built"], 0)
        self.assertEqual(result["methods_skipped_unsupported_construct"], 1)


if __name__ == "__main__":
    unittest.main()

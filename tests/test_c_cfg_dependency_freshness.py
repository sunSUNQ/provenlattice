"""I1-A Step 0: the cfg:c cache must be invalidated when its ast dependency moves.

A cfg:c cache built while the ast:c alignment was an older generation (a
span-collision function missing from the graph) must never be reported as
fresh after the ast analyzer upgrades: the reuse gate now compares the cached
``ast_contract`` against the current one and rebuilds on mismatch.
"""

import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import sqlite3

from provenlattice.analysis_c_ast import C_AST_CONTRACT
from provenlattice.analysis_c_cfg import ANALYZER as CFG_ANALYZER
from provenlattice.analysis_query import query_analysis
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope

BODY = (
    "int a01(int x) { return x + 1; }\n"
    "int b01(int n) { for (int i = 0; i < n; i += 1) { hit_b01(); } "
    "end_b01(); return 0; }\n"
)


class CfgDependencyFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.database = Path(self.temp.name) / "graph.db"
        (self.root / "src").mkdir(parents=True)
        (self.root / "src" / "t.c").write_text(BODY, encoding="utf-8")
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("ast", "cfg"), database=self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _cfg_metadata(self) -> dict:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT s.metadata FROM analysis_state s JOIN files f "
                "ON f.file_id=s.file_id WHERE f.path='src/t.c' AND s.feature=?",
                (CFG_ANALYZER,),
            ).fetchone()
        self.assertIsNotNone(row)
        return json.loads(row["metadata"])

    def _b01_owner(self) -> str:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT n.payload FROM analysis_nodes n JOIN files f "
                "ON f.file_id=n.file_id WHERE f.path='src/t.c' "
                "AND n.feature='ast:c' AND n.kind='FUNCTION'").fetchall()
        payloads = [json.loads(r["payload"]) for r in rows]
        return next(p["owner_symbol_id"] for p in payloads
                    if p.get("name") == "b01")

    def test_both_functions_present_after_aligned_build(self) -> None:
        metadata = self._cfg_metadata()
        self.assertEqual(metadata["functions_built"], 2)
        self.assertEqual(metadata["ast_contract"], C_AST_CONTRACT)
        env = query_analysis(self.root, "cfg", file_path="src/t.c",
                             database=self.database)
        self.assertEqual(env["status"], "available")
        owners = {n["payload"]["owner_symbol_id"] for n in env["nodes"]
                  if n["payload"].get("owner_symbol_id")}
        self.assertIn(self._b01_owner(), owners)

    def test_stale_ast_dependency_cache_is_rebuilt_not_reused(self) -> None:
        # Simulate a cache built under the previous ast generation: it only
        # contains function A, and its metadata names the old ast contract.
        owner_b = self._b01_owner()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "DELETE FROM analysis_nodes WHERE feature=? AND "
                "json_extract(payload,'$.owner_symbol_id')=?",
                (CFG_ANALYZER, owner_b))
            connection.execute(
                "DELETE FROM analysis_edges WHERE feature=? AND "
                "(json_extract(payload,'$.owner_symbol_id')=? OR "
                " src_id NOT IN (SELECT analysis_node_id FROM analysis_nodes "
                "                 WHERE feature=?) OR "
                " dst_id NOT IN (SELECT analysis_node_id FROM analysis_nodes "
                "                 WHERE feature=?))",
                (CFG_ANALYZER, owner_b, CFG_ANALYZER, CFG_ANALYZER))
            connection.execute(
                "UPDATE analysis_state SET metadata=json_set(metadata, "
                "'$.ast_contract', 'c-ast-v2', '$.functions_built', 1, "
                "'$.node_count', (SELECT COUNT(*) FROM analysis_nodes "
                "                  WHERE feature=?)) WHERE feature=?",
                (CFG_ANALYZER, CFG_ANALYZER))
            connection.commit()

        # without the dependency gate this would be reused as fresh
        result = analyze_scope(self.root, "src", ("ast", "cfg"),
                               database=self.database)
        self.assertEqual(result["features"]["cfg"]["materialized"], ["src/t.c"])
        metadata = self._cfg_metadata()
        self.assertEqual(metadata["functions_built"], 2)
        self.assertEqual(metadata["ast_contract"], C_AST_CONTRACT)
        env = query_analysis(self.root, "cfg", file_path="src/t.c",
                             database=self.database)
        self.assertEqual(env["status"], "available")
        owners = {n["payload"]["owner_symbol_id"] for n in env["nodes"]
                  if n["payload"].get("owner_symbol_id")}
        self.assertIn(owner_b, owners)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from provenlattice.identity import edge_id, repository_id, symbol_id
from provenlattice.impact import compute_impact_frontier
from provenlattice.models import Delta, Edge, Node
from provenlattice.parsing import TreeSitterParser
from provenlattice.shard import DirectoryShardStrategy, fingerprint


class CoreTests(unittest.TestCase):
    def test_symbol_id_is_stable_across_line_changes(self) -> None:
        repo = repository_id(Path("repo"))
        first = symbol_id(repo, "src/api.py", "Function", "src.api.run", "(value: int)")
        second = symbol_id(repo, "src/api.py", "Function", "src.api.run", "(value: int)")
        self.assertEqual(first, second)

    def test_signature_changes_symbol_identity(self) -> None:
        repo = repository_id(Path("repo"))
        self.assertNotEqual(
            symbol_id(repo, "api.py", "Function", "api.run", "(value)"),
            symbol_id(repo, "api.py", "Function", "api.run", "(value, mode)"),
        )

    def test_edge_identity_and_contract(self) -> None:
        edge = Edge(edge_id("a", "b", "CALLS"), "a", "b", "CALLS", generation=3)
        self.assertEqual(edge.provenance, "static_analysis")
        self.assertEqual(edge.confidence, 1.0)
        self.assertEqual(edge.id, edge_id("a", "b", "CALLS"))

    def test_shard_strategy(self) -> None:
        strategy = DirectoryShardStrategy()
        self.assertEqual(strategy.path_for("src/domain/model.py"), "src/domain")
        self.assertEqual(strategy.path_for("main.py"), ".")

    def test_fingerprint_ignores_body_hash_but_tracks_signature(self) -> None:
        base = dict(
            id="n", kind="Function", repo_id="r", shard_id="s", file_id="f",
            name="run", qualified_name="api.run", language="python", start_line=1,
            end_line=2, generation=1, metadata={"public": True},
        )
        node_a = Node(signature="(value)", source_hash="a", **base)
        node_b = Node(signature="(value)", source_hash="b", **base)
        node_c = Node(signature="(value, mode)", source_hash="b", **base)
        self.assertEqual(fingerprint([node_a])[1], fingerprint([node_b])[1])
        self.assertNotEqual(fingerprint([node_a])[1], fingerprint([node_c])[1])

    def test_delta_contract(self) -> None:
        delta = Delta(nodes_added=1, edges_removed=2, boundary_dirty=["s"])
        self.assertEqual(delta.to_dict()["nodes_added"], 1)
        self.assertEqual(delta.to_dict()["boundary_dirty"], ["s"])

    def test_impact_frontier_is_one_hop_and_conservative(self) -> None:
        old = {"e": {"metadata": '{"scope": "boundary", "src_shard_id": "a", "dst_shard_id": "b"}'}}
        new = {}
        result = compute_impact_frontier({"b"}, old, new)
        self.assertEqual(result["changed_shards"], ["b"])
        self.assertEqual(result["directly_affected_shards"], ["a"])
        self.assertEqual(result["impact_frontier_size"], 1)
        self.assertFalse(result["wide_impact"])

    def test_tree_sitter_adapter_emits_normalized_facts(self) -> None:
        parsed = TreeSitterParser().parse_bytes(
            b"from tools.api import helper\n\nclass Runner:\n"
            b"    def run(self, value: int) -> int:\n        return helper(value)\n"
            b"\nUserId: str\n",
            "service.py",
        ).parsed
        self.assertEqual(parsed.parser, "tree-sitter")
        self.assertIn("service.Runner", [symbol.qualified_name for symbol in parsed.symbols])
        self.assertIn("service.Runner.run", [symbol.qualified_name for symbol in parsed.symbols])
        self.assertIn("service.UserId", [symbol.qualified_name for symbol in parsed.symbols])
        self.assertEqual(parsed.imports[0].module, "tools.api")
        self.assertTrue(any(reference.type == "CALLS" for reference in parsed.references))

    def test_tree_sitter_exposes_incremental_tree_and_changed_ranges(self) -> None:
        parser = TreeSitterParser()
        old_source = b"def run():\n    return 1\n"
        new_source = old_source + b"\ndef added():\n    return 2\n"
        first = parser.parse_bytes(old_source, "api.py")
        first.tree.edit(
            start_byte=len(old_source), old_end_byte=len(old_source), new_end_byte=len(new_source),
            start_point=(2, 0), old_end_point=(2, 0), new_end_point=(5, 0),
        )
        second = parser.parse_bytes(new_source, "api.py", first.tree)
        self.assertTrue(second.changed_ranges)
        self.assertIn("api.added", [symbol.qualified_name for symbol in second.parsed.symbols])


if __name__ == "__main__":
    unittest.main()

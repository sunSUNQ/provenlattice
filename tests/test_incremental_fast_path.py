"""Phase 1: no-change fast path and File-node Delta comparison."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from provenlattice.graph import full_index
from provenlattice.incremental import (
    _file_node_metadata_changed,
    _node_changed,
    incremental_update,
)
from provenlattice.storage import SQLiteStorage


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class NoChangeFastPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        write(self.root / "src" / "a.py", "def alpha():\n    return 1\n")
        write(self.root / "src" / "b.py", "def beta():\n    return alpha()\n")
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_no_change_does_not_load_full_graph(self) -> None:
        with mock.patch.object(
            SQLiteStorage, "snapshot_ids",
            side_effect=AssertionError("snapshot_ids must not run"),
        ), mock.patch.object(
            SQLiteStorage, "parser_cache",
            side_effect=AssertionError("parser_cache must not run"),
        ), mock.patch.object(
            SQLiteStorage, "raw_reference_cache",
            side_effect=AssertionError("raw_reference_cache must not run"),
        ):
            result = incremental_update(self.root, self.database)
        self.assertFalse(result["changed"])
        self.assertEqual(result["delta"]["nodes_added"], 0)
        self.assertEqual(result["delta"]["nodes_removed"], 0)
        self.assertEqual(result["delta"]["nodes_updated"], 0)
        self.assertEqual(result["delta"]["edges_added"], 0)
        self.assertEqual(result["delta"]["edges_removed"], 0)
        self.assertEqual(result["metrics"]["files_scanned"], 2)
        self.assertEqual(result["metrics"]["files_reused"], 2)
        self.assertGreater(result["metrics"]["shards_reused"], 0)

    def test_integrity_mismatch_falls_closed(self) -> None:
        connection = sqlite3.connect(self.database)
        try:
            connection.execute("DELETE FROM files WHERE path = 'src/a.py'")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(RuntimeError) as raised:
            incremental_update(self.root, self.database)
        self.assertIn("integrity check failed", str(raised.exception))


class FileNodeCompareTests(unittest.TestCase):
    @staticmethod
    def _old(parser: str = "python-v1", shard: str = "src") -> dict:
        return {
            "kind": "File",
            "source_hash": "abc",
            "start_line": 1,
            "end_line": 10,
            "metadata": json.dumps({
                "relative_path": "src/t.py",
                "shard_path": shard,
                "parsed": {"parser": parser, "symbols": ["a"]},
            }),
        }

    def test_unchanged_file_does_not_serialise_new_metadata(self) -> None:
        old = self._old()
        # A non-JSON-serialisable value proves the fast path did not call
        # json.dumps(new.metadata): serialising would raise TypeError.
        new = SimpleNamespace(
            kind="File", source_hash="abc", start_line=1, end_line=10,
            metadata={
                "relative_path": "src/t.py",
                "shard_path": "src",
                "parsed": {"parser": "python-v1", "opaque": object()},
            },
        )
        self.assertFalse(_node_changed(old, new))
        self.assertFalse(_file_node_metadata_changed(old, new))

    def test_parser_or_shard_change_is_detected(self) -> None:
        new_parser = SimpleNamespace(
            kind="File", source_hash="abc", start_line=1, end_line=10,
            metadata={"relative_path": "src/t.py", "shard_path": "src",
                      "parsed": {"parser": "python-v2"}},
        )
        self.assertTrue(_node_changed(self._old(), new_parser))
        new_shard = SimpleNamespace(
            kind="File", source_hash="abc", start_line=1, end_line=10,
            metadata={"relative_path": "src/t.py", "shard_path": "other",
                      "parsed": {"parser": "python-v1"}},
        )
        self.assertTrue(_node_changed(self._old(), new_shard))

    def test_non_file_keeps_full_metadata_compare(self) -> None:
        old = {
            "kind": "Function",
            "source_hash": "abc",
            "start_line": 1,
            "end_line": 2,
            "metadata": json.dumps({"definition": True}),
        }
        same = SimpleNamespace(
            kind="Function", source_hash="abc", start_line=1, end_line=2,
            metadata={"definition": True},
        )
        changed = SimpleNamespace(
            kind="Function", source_hash="abc", start_line=1, end_line=2,
            metadata={"definition": False},
        )
        self.assertFalse(_node_changed(old, same))
        self.assertTrue(_node_changed(old, changed))


if __name__ == "__main__":
    unittest.main()

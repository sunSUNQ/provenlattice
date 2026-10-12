"""I2A-R1: old-DB PK migration and cross-analyzer same-id isolation tests.

The composite PK ``(analysis_node_id, feature)`` allows two analyzers to
publish the same derived fact under different features (shared
``identity.event_id``). Databases created before the change carry the old
single-column PK, which silently rejects the second analyzer's write.
``AnalysisStore.__init__`` detects the old PK and migrates the derived cache
in place, preserving every row.
"""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from provenlattice.analysis import (
    ANALYZER_VERSIONS,
    AnalysisNode,
    AnalysisStore,
    dependency_staleness,
)
from provenlattice.storage import SQLiteStorage

OLD_SCHEMA = """
CREATE TABLE analysis_nodes (
    analysis_node_id TEXT PRIMARY KEY, file_id TEXT NOT NULL,
    feature TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE analysis_edges (
    analysis_edge_id TEXT PRIMARY KEY, file_id TEXT NOT NULL,
    feature TEXT NOT NULL, src_id TEXT NOT NULL, dst_id TEXT NOT NULL,
    kind TEXT NOT NULL, payload TEXT NOT NULL
);
"""


def make_store(db: Path) -> tuple:
    storage = SQLiteStorage(db)
    return AnalysisStore(storage), storage


class StoreTestCase(unittest.TestCase):
    """Base: manages SQLiteStorage lifecycle to avoid Windows file locks."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "graph.db"
        self.storage = SQLiteStorage(self.db)
        self.store = AnalysisStore(self.storage)

    def tearDown(self) -> None:
        self.storage.close()
        self.temp.cleanup()


class PKMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "old.db"
        with closing(sqlite3.connect(self.db)) as conn:
            conn.executescript(OLD_SCHEMA)
            conn.execute(
                "INSERT INTO analysis_nodes VALUES"
                "('event:old1','file:1','events:cpp','CALL','{}')")
            conn.commit()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_old_pk_detected_and_migrated(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            old_pk = [row[1] for row in conn.execute(
                "PRAGMA table_info(analysis_nodes)") if row[5] > 0]
        self.assertEqual(old_pk, ["analysis_node_id"])
        store, storage = make_store(self.db)
        with closing(sqlite3.connect(self.db)) as conn:
            new_pk = [row[1] for row in conn.execute(
                "PRAGMA table_info(analysis_nodes)") if row[5] > 0]
        self.assertEqual(new_pk, ["analysis_node_id", "feature"])
        storage.close()

    def test_migration_preserves_existing_rows(self) -> None:
        store, storage = make_store(self.db)
        rows = store.storage.rows("SELECT * FROM analysis_nodes")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["analysis_node_id"], "event:old1")
        storage.close()

    def test_shared_event_id_coexists_across_features(self) -> None:
        store, storage = make_store(self.db)
        store.replace_analysis_for_file(
            "file:1", "sparse_cfg:cpp", "hash1", 1,
            [AnalysisNode("event:old1", "CALL", {"owner_symbol_id": "symbol:x"})], [])
        rows = store.storage.rows(
            "SELECT feature, analysis_node_id FROM analysis_nodes "
            "ORDER BY feature")
        self.assertEqual([(r["feature"], r["analysis_node_id"]) for r in rows],
                         [("events:cpp", "event:old1"),
                          ("sparse_cfg:cpp", "event:old1")])
        storage.close()

    def test_delete_one_feature_leaves_the_other(self) -> None:
        store, storage = make_store(self.db)
        store.replace_analysis_for_file(
            "file:1", "sparse_cfg:cpp", "hash1", 1,
            [AnalysisNode("event:old1", "CALL", {"owner_symbol_id": "symbol:x"})], [])
        store.delete_analysis_for_file("file:1", "events:cpp")
        rows = store.storage.rows("SELECT feature FROM analysis_nodes")
        self.assertEqual([r["feature"] for r in rows], ["sparse_cfg:cpp"])
        storage.close()

    def test_fresh_database_gets_composite_pk_directly(self) -> None:
        db = Path(self.temp.name) / "fresh.db"
        store, storage = make_store(db)
        store.replace_analysis_for_file(
            "file:1", "events:cpp", "h1", 1,
            [AnalysisNode("event:x", "CALL", {})], [])
        store.replace_analysis_for_file(
            "file:1", "sparse_cfg:cpp", "h1", 1,
            [AnalysisNode("event:x", "CALL", {})], [])
        rows = store.storage.rows(
            "SELECT feature FROM analysis_nodes WHERE analysis_node_id='event:x'")
        self.assertEqual(sorted(r["feature"] for r in rows),
                         ["events:cpp", "sparse_cfg:cpp"])
        storage.close()


class CrossAnalyzerIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "graph.db"
        self.storage = SQLiteStorage(self.db)
        self.store = AnalysisStore(self.storage)

    def tearDown(self) -> None:
        self.storage.close()
        self.temp.cleanup()

    def test_same_id_different_payload_coexists(self) -> None:
        self.store.replace_analysis_for_file(
            "f1", "events:cpp", "h1", 1,
            [AnalysisNode("event:a", "CALL",
                          {"level": "level0", "analyzer": "events:cpp"})], [])
        self.store.replace_analysis_for_file(
            "f1", "sparse_cfg:cpp", "h1", 1,
            [AnalysisNode("event:a", "CALL",
                          {"level": "level0+structural+access",
                           "analyzer": "sparse_cfg:cpp",
                           "annotations": {"subject": "p"}})], [])
        ev_nodes = self.store.storage.rows(
            "SELECT payload FROM analysis_nodes "
            "WHERE analysis_node_id='event:a' AND feature='events:cpp'")
        scfg_nodes = self.store.storage.rows(
            "SELECT payload FROM analysis_nodes "
            "WHERE analysis_node_id='event:a' AND feature='sparse_cfg:cpp'")
        self.assertEqual(len(ev_nodes), 1)
        self.assertEqual(len(scfg_nodes), 1)
        self.assertEqual(json.loads(ev_nodes[0]["payload"])["analyzer"], "events:cpp")
        self.assertEqual(json.loads(scfg_nodes[0]["payload"])["analyzer"],
                         "sparse_cfg:cpp")

    def test_updating_events_does_not_touch_sparse_cfg(self) -> None:
        self.store.replace_analysis_for_file(
            "f1", "events:cpp", "h1", 1,
            [AnalysisNode("event:a", "CALL", {"v": 1})], [])
        self.store.replace_analysis_for_file(
            "f1", "sparse_cfg:cpp", "h1", 1,
            [AnalysisNode("event:a", "CALL", {"v": 2})], [])
        self.store.replace_analysis_for_file(
            "f1", "events:cpp", "h2", 1,
            [AnalysisNode("event:b", "RETURN", {"v": 3})], [])
        ev = self.store.storage.rows(
            "SELECT analysis_node_id FROM analysis_nodes WHERE feature='events:cpp'")
        scfg = self.store.storage.rows(
            "SELECT analysis_node_id FROM analysis_nodes WHERE feature='sparse_cfg:cpp'")
        self.assertEqual([r["analysis_node_id"] for r in ev], ["event:b"])
        self.assertEqual([r["analysis_node_id"] for r in scfg], ["event:a"])

    def test_dependency_staleness_survives_pk_migration(self) -> None:
        from provenlattice.analysis import AnalysisEdge
        self.store.replace_analysis_for_file(
            "f1", "sparse_dfg:cpp", "h1", 1, [],
            [AnalysisEdge("se:x", "event:a", "event:b", "DATA_FLOW_TO", {})],
            metadata={"dependencies": {"events:cpp": "cpp-events-v0"}})
        result = dependency_staleness(
            self.store.get_analysis_state("f1", "sparse_dfg:cpp")["metadata"])
        self.assertIn("dependency_changed", result)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from provenlattice.graph import full_index
from provenlattice.incremental import incremental_update
from provenlattice.knowledge import index_knowledge
from provenlattice.models import OverlayDelta
from provenlattice.overlay import (
    OverlayStore, capture_snapshot_delta, detect_conflicts, materialize_view,
)
from provenlattice.query import GraphQuery


FIXTURE = Path(__file__).parent / "fixture_knowledge"


def snapshot(database: Path) -> dict[str, list[dict]]:
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        result = {}
        for table in ("nodes", "edges", "raw_evidence_links", "document_state"):
            rows = []
            for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1"):
                item = dict(row)
                item.pop("generation", None)
                rows.append(item)
            result[table] = rows
        return result


class KnowledgeLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_contract_statuses_provenance_and_queries(self) -> None:
        metrics = index_knowledge(self.root, self.database)
        self.assertGreaterEqual(metrics["knowledge_nodes"], 5)
        self.assertGreater(metrics["resolved_evidence"], 0)
        self.assertGreater(metrics["ambiguous_evidence"], 0)
        self.assertGreater(metrics["unresolved_evidence"], 0)
        with GraphQuery(self.database) as query:
            requirement = query.get_definition("REQ-RECOVERY-001")["data"]
            implemented = query.get_implemented_code(requirement["id"])["data"]
            self.assertEqual([item["qualified_name"] for item in implemented],
                             ["storage.StorageRecovery.retry"])
            reverse = query.get_requirements(implemented[0]["id"])["data"]
            self.assertEqual([item["name"] for item in reverse], ["REQ-RECOVERY-001"])
            ambiguous = query.get_evidence_links(status="ambiguous")["data"]
            unresolved = query.get_evidence_links(status="unresolved")["data"]
            self.assertTrue(ambiguous and unresolved)
            self.assertIsInstance(ambiguous[0]["candidate_targets"], list)
            self.assertTrue(all(item["resolved_target_id"] is None
                                for item in ambiguous + unresolved))
        with closing(sqlite3.connect(self.database)) as connection:
            invalid = connection.execute(
                "SELECT COUNT(*) FROM edges e JOIN raw_evidence_links r "
                "ON json_extract(e.metadata,'$.raw_evidence_link_id')=r.id "
                "WHERE r.resolution_status!='resolved'"
            ).fetchone()[0]
            provenances = {row[0] for row in connection.execute(
                "SELECT provenance FROM edges WHERE json_extract(metadata,'$.layer')='knowledge' "
                "AND type!='CONTAINS'"
            )}
        self.assertEqual(invalid, 0)
        self.assertIn("explicit_symbol_reference", provenances)
        unchanged = index_knowledge(self.root, self.database)
        self.assertEqual(unchanged["documents_reparsed"], 0)
        self.assertEqual(unchanged["evidence_links_reprocessed"], 0)
        self.assertEqual(unchanged["evidence_links_reused"], 6)

    def test_section_identity_incremental_reuse_and_delete(self) -> None:
        index_knowledge(self.root, self.database)
        with GraphQuery(self.database) as query:
            before = query.get_definition("REQ-RECOVERY-001")["data"]["id"]
        spec = self.root / "spec/recovery.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace(
            "The retry path", "The bounded retry path"), encoding="utf-8")
        changed = index_knowledge(self.root, self.database)
        with GraphQuery(self.database) as query:
            after = query.get_definition("REQ-RECOVERY-001")["data"]["id"]
        self.assertEqual(before, after)
        self.assertEqual(changed["documents_reparsed"], 1)
        self.assertGreater(changed["sections_reused"], 0)
        self.assertEqual(changed["evidence_links_reprocessed"], 3)
        self.assertEqual(changed["evidence_links_reused"], 3)
        spec.write_text(spec.read_text(encoding="utf-8").split("## Acceptance Criteria")[0],
                        encoding="utf-8")
        removed = index_knowledge(self.root, self.database)
        self.assertGreater(removed["cross_layer_edges_removed"], 0)
        with GraphQuery(self.database) as query:
            self.assertIsNone(query.get_definition("Acceptance Criteria")["data"])

    def test_code_signature_change_reprocesses_unchanged_document_evidence(self) -> None:
        index_knowledge(self.root, self.database)
        source = self.root / "src/recovery.cpp"
        source.write_text(source.read_text(encoding="utf-8").replace(
            "retry(int attempt)", "retry(long attempt)"), encoding="utf-8")
        incremental_update(self.root, self.database)
        metrics = index_knowledge(self.root, self.database)
        self.assertEqual(metrics["documents_reparsed"], 0)
        self.assertEqual(metrics["evidence_links_reprocessed"], 6)
        with GraphQuery(self.database) as query:
            implemented = query.get_implemented_code("REQ-RECOVERY-001")["data"]
        self.assertEqual(len(implemented), 1)
        self.assertIn("long", implemented[0]["signature"])

    def test_full_incremental_and_overlay_parity(self) -> None:
        index_knowledge(self.root, self.database)
        spec = self.root / "spec/recovery.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace(
            "failed recovery", "bounded recovery"), encoding="utf-8")
        index_knowledge(self.root, self.database)
        full_database = Path(self.temp.name) / "full.db"
        full_index(self.root, full_database)
        index_knowledge(self.root, full_database, incremental=False)
        self.assertEqual(snapshot(self.database), snapshot(full_database))

        with closing(sqlite3.connect(self.database)) as connection:
            repository = connection.execute(
                "SELECT repo_id,current_generation FROM repositories LIMIT 1").fetchone()
        branch_root = Path(self.temp.name) / "branch-repo"
        shutil.copytree(self.root, branch_root)
        branch_spec = branch_root / "spec/recovery.md"
        branch_spec.write_text(branch_spec.read_text(encoding="utf-8").replace(
            "bounded recovery", "branch recovery"), encoding="utf-8")
        branch_database = Path(self.temp.name) / "branch-target.db"
        full_index(branch_root, branch_database, repository_id_override=repository[0])
        index_knowledge(branch_root, branch_database, incremental=False)
        overlay_path = Path(self.temp.name) / "branch.db"
        with OverlayStore.create(
            overlay_path, overlay_type="BRANCH", repository_id=repository[0],
            base_commit="C100", base_generation=repository[1], branch_name="knowledge",
        ) as overlay:
            counts = capture_snapshot_delta(self.database, branch_database, overlay)
            self.assertGreater(sum(counts.values()), 0)
            effective = materialize_view(self.database, overlay)
            expected = snapshot(branch_database)
            for entity, table, key in (
                ("Node", "nodes", "id"), ("Edge", "edges", "id"),
                ("RawEvidenceLink", "raw_evidence_links", "id"),
            ):
                actual = [{k: v for k, v in row.items() if k != "generation"}
                          for row in effective[entity]]
                self.assertEqual(sorted(actual, key=lambda row: row[key]), expected[table])

    def test_divergent_knowledge_overlay_changes_conflict(self) -> None:
        index_knowledge(self.root, self.database)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            repository = connection.execute(
                "SELECT repo_id,current_generation FROM repositories LIMIT 1").fetchone()
            requirement = dict(connection.execute(
                "SELECT * FROM nodes WHERE kind='Requirement' LIMIT 1").fetchone())
        left_path, right_path = (Path(self.temp.name) / "left.db",
                                 Path(self.temp.name) / "right.db")
        with OverlayStore.create(
            left_path, overlay_type="BRANCH", repository_id=repository[0],
            base_commit="C100", base_generation=repository[1], branch_name="left",
        ) as left, OverlayStore.create(
            right_path, overlay_type="BRANCH", repository_id=repository[0],
            base_commit="C100", base_generation=repository[1], branch_name="right",
        ) as right:
            left_value, right_value = dict(requirement), dict(requirement)
            left_value["name"], right_value["name"] = "REQ-LEFT", "REQ-RIGHT"
            left.put(OverlayDelta(left.metadata.overlay_id, "Node", requirement["id"],
                                  "UPDATE", requirement["source_hash"], left_value,
                                  repository[1]))
            right.put(OverlayDelta(right.metadata.overlay_id, "Node", requirement["id"],
                                   "UPDATE", requirement["source_hash"], right_value,
                                   repository[1]))
            conflicts = detect_conflicts(left, right)
        self.assertIn("ENTITY_CONFLICT", {item.conflict_type for item in conflicts})


if __name__ == "__main__":
    unittest.main()

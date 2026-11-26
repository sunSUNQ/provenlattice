"""Phase 2: bounded / match-mode Raw References queries and CLI."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from provenlattice.cli import build_parser, run
from provenlattice.graph import full_index
from provenlattice.models import OverlayDelta
from provenlattice.overlay import OverlayStore
from provenlattice.query import GraphQuery


SOURCE = """def alpha():
    return 1

def alphabet():
    return 2

def beta_alpha():
    return 3

def use():
    alpha()
    alphabet()
    beta_alpha()
    missing()
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class RawReferenceBoundedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        write(self.root / "src" / "calls.py", SOURCE)
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_match_modes_are_case_sensitive(self) -> None:
        with GraphQuery(self.database) as query:
            exact = query.get_raw_references(raw_name="alpha")
            prefix = query.get_raw_references(raw_name="alpha", match="prefix")
            substring = query.get_raw_references(
                raw_name="alpha", match="substring")
            upper = query.get_raw_references(raw_name="ALPHA", match="prefix")
        self.assertEqual(exact["raw_references"]["total"], 1)
        self.assertEqual(prefix["raw_references"]["total"], 2)
        self.assertEqual(substring["raw_references"]["total"], 3)
        self.assertEqual(upper["raw_references"]["total"], 0)

    def test_limit_is_stable_and_reports_truncation(self) -> None:
        with GraphQuery(self.database) as query:
            full = query.get_raw_references(raw_name="alpha", match="prefix")
            bounded = query.get_raw_references(
                raw_name="alpha", match="prefix", limit=1)
        full_ids = [row["id"] for row in full["data"]]
        self.assertEqual(len(bounded["data"]), 1)
        self.assertEqual(bounded["data"][0]["id"], full_ids[0])
        self.assertEqual(bounded["raw_references"]["returned"], 1)
        self.assertEqual(bounded["raw_references"]["total"], 2)
        self.assertTrue(bounded["raw_references"]["truncated"])
        self.assertEqual(len(bounded["evidence"]), 1)

    def test_max_bytes_is_enforced_and_evidence_is_one_to_one(self) -> None:
        with GraphQuery(self.database) as query:
            bounded = query.get_raw_references(
                raw_name="alpha", match="substring", max_bytes=500)
        meta = bounded["raw_references"]
        self.assertLessEqual(meta["bytes"], 500)
        self.assertLess(meta["returned"], meta["total"])
        self.assertTrue(meta["truncated"])
        self.assertEqual(len(bounded["data"]), len(bounded["evidence"]))
        self.assertEqual(len(bounded["data"]), meta["returned"])

    def test_combined_filters(self) -> None:
        with GraphQuery(self.database) as query:
            file_id = query.get_raw_references(
                raw_name="alpha", match="prefix")["data"][0]["file_id"]
            result = query.get_raw_references(
                raw_name="alpha", match="prefix", file_id=file_id,
                status="resolved")
        self.assertGreaterEqual(result["raw_references"]["returned"], 1)
        for row in result["data"]:
            self.assertEqual(row["file_id"], file_id)
            self.assertEqual(row["status"], "resolved")

    def test_overlay_add_update_delete_is_applied_before_limit(self) -> None:
        with GraphQuery(self.database) as query:
            rows = query.get_raw_references(
                raw_name="alpha", match="prefix")["data"]
            repository = query.storage.repository()
        self.assertGreaterEqual(len(rows), 2)
        generation = int(repository["current_generation"])
        overlay_path = Path(self.temp.name) / "branch.overlay.db"
        overlay = OverlayStore.create(
            overlay_path, overlay_type="BRANCH",
            repository_id=repository["repo_id"], base_commit="base",
            base_generation=generation,
        )
        try:
            first, second = rows[0], rows[1]
            overlay.apply([
                OverlayDelta(overlay.metadata.overlay_id, "RawReference",
                             first["id"], "DELETE", None, None, generation),
                OverlayDelta(
                    overlay.metadata.overlay_id, "RawReference",
                    second["id"], "UPDATE", None,
                    {**second, "raw_name": "alphabet_updated"}, generation),
                OverlayDelta(
                    overlay.metadata.overlay_id, "RawReference",
                    "overlay:alpha-new", "ADD", None,
                    {**second, "id": "overlay:alpha-new",
                     "raw_name": "alpha_new"}, generation),
            ])
        finally:
            overlay.close()

        with GraphQuery(self.database, branch_overlay=overlay_path) as query:
            result = query.get_raw_references(
                raw_name="alpha", match="prefix", limit=1)
        names = {row["raw_name"] for row in result["data"]}
        self.assertEqual(len(names), 1)
        self.assertTrue(names <= {"alphabet_updated", "alpha_new"})
        self.assertEqual(result["raw_references"]["total"], 2)
        self.assertTrue(result["raw_references"]["truncated"])


class RawReferenceCliTests(unittest.TestCase):
    def test_cli_parses_and_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            write(root / "src" / "calls.py", SOURCE)
            database = Path(temp) / "graph.db"
            full_index(root, database)
            parser = build_parser()
            args = parser.parse_args([
                "raw-references", "alpha", "--match", "prefix",
                "--limit", "1", "--max-bytes", "10000",
                "--database", str(database), "--json",
            ])
            result = run(args)
            self.assertEqual(result["raw_references"]["match"], "prefix")
            self.assertEqual(result["raw_references"]["limit"], 1)
            self.assertLessEqual(result["raw_references"]["bytes"], 10000)
            self.assertEqual(len(result["data"]), 1)

    def test_cli_rejects_negative_bounds(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "raw-references", "alpha", "--limit", "-1",
                "--database", "unused.db",
            ])


if __name__ == "__main__":
    unittest.main()

"""SQI-V1 implementation tests (Contract V1 mechanical-correctness gates).

Run:  PYTHONPATH=src python -m unittest experiments.query_interface_v1.tests.test_sqi_v1 -v
(from the provenlattice checkout root)

Covers the eight frozen implementation behaviors: deterministic output,
evidence bidirectional binding, provenance mismatch rejection, truncation
honesty, budget non-circumvention, unresolved raw-reference verbatim return,
impact-frontier shard-level boundedness, and the source-verification policy.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

from sqi_adapter import SQIAdapter, _clamp  # noqa: E402
from sqi_validator import (  # noqa: E402
    HARD_CAPS, semantic_errors, validate_envelope)

REPO = Path(__file__).resolve().parents[3]
WORKSPACE = REPO.parent
DB = WORKSPACE / "benchmark-analysis" / "v0.2-db"
COMMITS = {
    "aria2": "9e7273583f83e881e3ec067b523ba88724088d2f",
    "brpc": "ae09e960c7291605dda52356cc0c2d45567fb53e",
    "rocksdb": "37234200b57d8d0a6a5c41f2d9811bbd2e293544",
}
REQUIRED_SOURCE_CLASSES = {
    "definition_semantics", "call_site_semantics", "reference_purpose",
    "downstream_impact", "document_equivalence",
}


def strip_nondeterministic(envelope: dict) -> dict:
    return {key: value for key, value in envelope.items() if key != "query_time_ms"}


class TestDeterministicOutput(unittest.TestCase):
    """1. same call on the same frozen DB -> identical response (minus the
    one contract-allowed non-deterministic field)."""

    def test_lookup_twice_identical(self):
        with SQIAdapter(DB / "aria2.db", COMMITS["aria2"]) as adapter:
            first = adapter.symbol_lookup("DownloadEngine", kind="Class",
                                          path_prefix="src/DownloadEngine.h")
            second = adapter.symbol_lookup("DownloadEngine", kind="Class",
                                           path_prefix="src/DownloadEngine.h")
        self.assertEqual(strip_nondeterministic(first), strip_nondeterministic(second))

    def test_neighbors_twice_identical(self):
        with SQIAdapter(DB / "brpc.db", COMMITS["brpc"]) as adapter:
            lookup = adapter.symbol_lookup("butil.Status.error_cstr")
            symbol_id = lookup["data"][0]["id"]
            first = adapter.symbol_callers(symbol_id)
            second = adapter.symbol_callers(symbol_id)
        self.assertEqual(strip_nondeterministic(first), strip_nondeterministic(second))


class TestEvidenceBidirectionalBinding(unittest.TestCase):
    """2. C1 in both directions on every canonical call shape."""

    def _check(self, envelope: dict):
        ok, errors = validate_envelope(envelope)
        self.assertTrue(ok, errors)
        row_ids = {row["id"] for row in envelope["data"]}
        covered = set()
        for item in envelope["evidence"]:
            covered.add(item["target_id"])
            covered.add(item["source_id"])
            covered.add((item.get("metadata") or {}).get("fact_id"))
            self.assertIn(item["evidence_id"], envelope["returned_evidence_ids"])
        for row_id in row_ids:
            self.assertIn(row_id, covered, f"fact {row_id} lacks evidence")

    def test_binding_across_calls(self):
        with SQIAdapter(DB / "aria2.db", COMMITS["aria2"]) as adapter:
            self._check(adapter.symbol_lookup("DownloadEngine"))
        with SQIAdapter(DB / "brpc.db", COMMITS["brpc"]) as adapter:
            lookup = adapter.symbol_lookup("butil.Status.error_cstr")
            self._check(lookup)
            self._check(adapter.symbol_callers(lookup["data"][0]["id"]))
        with SQIAdapter(DB / "rocksdb.db", COMMITS["rocksdb"]) as adapter:
            self._check(adapter.impact_frontier(["db", "file"]))


class TestProvenanceMismatch(unittest.TestCase):
    """3. tampered provenance must fail validation."""

    def _valid_envelope(self) -> dict:
        with SQIAdapter(DB / "aria2.db", COMMITS["aria2"]) as adapter:
            return adapter.symbol_lookup("DownloadEngine")

    def test_tampered_commit_rejected(self):
        envelope = self._valid_envelope()
        envelope["commit"] = "0" * 40
        ok, errors = validate_envelope(envelope, expected_commit=COMMITS["aria2"])
        self.assertFalse(ok)
        self.assertTrue(any("commit mismatch" in error for error in errors))

    def test_wrong_commit_fingerprint_rejected(self):
        envelope = self._valid_envelope()
        envelope["commit"] = "1a" * 20
        ok, errors = validate_envelope(envelope, expected_commit=COMMITS["aria2"])
        self.assertFalse(ok)
        self.assertTrue(any("commit mismatch" in error for error in errors))

    def test_tampered_repository_rejected(self):
        envelope = self._valid_envelope()
        envelope["repository"] = "repo:deadbeef"
        ok, errors = validate_envelope(envelope)
        self.assertFalse(ok)
        self.assertTrue(any("repository" in error for error in errors))

    def test_missing_params_rejected(self):
        envelope = self._valid_envelope()
        del envelope["params"]
        ok, errors = validate_envelope(envelope)
        self.assertFalse(ok)
        self.assertTrue(any("params" in error for error in errors))


class TestTruncationHonesty(unittest.TestCase):
    """4. over-budget responses declare truncation; C3 enforced by validator."""

    def test_over_budget_truncates_with_counts(self):
        with SQIAdapter(DB / "aria2.db", COMMITS["aria2"]) as adapter:
            envelope = adapter.symbol_lookup(
                "DownloadEngine", budget={"max_evidence": 20, "max_symbols": 3,
                                          "max_edges": 20, "max_sections": 4})
        self.assertTrue(envelope["truncation"]["truncated"])
        self.assertGreater(envelope["truncation"]["omitted_counts"]["symbols"], 0)
        self.assertLessEqual(len(envelope["data"]), 3)

    def test_under_budget_no_truncation(self):
        with SQIAdapter(DB / "aria2.db", COMMITS["aria2"]) as adapter:
            envelope = adapter.symbol_lookup(
                "DownloadEngine", kind="Class", path_prefix="src/DownloadEngine.h",
                budget={"max_evidence": 50, "max_symbols": 20, "max_edges": 50,
                        "max_sections": 10})
        self.assertFalse(envelope["truncation"]["truncated"])
        self.assertEqual(max(envelope["truncation"]["omitted_counts"].values()), 0)

    def test_validator_rejects_dishonest_truncation(self):
        envelope = TestProvenanceMismatch._valid_envelope(self)
        envelope["truncation"] = {"truncated": False,
                                  "omitted_counts": {"symbols": 5, "edges": 0,
                                                     "raw_refs": 0, "sections": 0}}
        errors = semantic_errors(envelope)
        self.assertTrue(any("C3" in error for error in errors))


class TestBudgetNonCircumvention(unittest.TestCase):
    """5. declared budgets cannot exceed hard caps; bundle shares one pool."""

    def test_declared_above_cap_is_clamped(self):
        applied = _clamp({"max_evidence": 999, "max_symbols": 999,
                          "max_edges": 999, "max_sections": 999})
        self.assertEqual(applied, HARD_CAPS)

    def test_foreign_budget_fields_ignored(self):
        with SQIAdapter(DB / "aria2.db", COMMITS["aria2"]) as adapter:
            envelope = adapter.symbol_lookup(
                "DownloadEngine", budget={"max_symbols": 2, "unlimited": True})
        self.assertNotIn("unlimited", envelope["budget"]["applied"])
        self.assertLessEqual(len(envelope["data"]), 2)

    def test_bundle_shared_pool_total_bound(self):
        with SQIAdapter(DB / "brpc.db", COMMITS["brpc"]) as adapter:
            envelope = adapter.bundle_explain(
                "IsAskedToQuit", budget={"max_evidence": 12, "max_symbols": 6,
                                         "max_edges": 10, "max_sections": 4})
        self.assertLessEqual(envelope["returned_evidence_count"], 12)
        self.assertLessEqual(len(envelope["data"].get("related_entities", [])), 6)
        used = envelope["budget"]["used"]
        self.assertLessEqual(used["evidence"], 12)
        self.assertTrue(envelope["truncation"]["truncated"],
                        "bundle cut 49 callers to budget; truncation must be declared")


class TestUnresolvedRawReferenceVerbatim(unittest.TestCase):
    """6. unresolved/ambiguous raw references come back exactly as recorded."""

    @classmethod
    def setUpClass(cls):
        con = sqlite3.connect(str(DB / "brpc.db"))
        row = con.execute(
            "SELECT owner_symbol_id FROM raw_references WHERE status='unresolved' "
            "GROUP BY owner_symbol_id ORDER BY COUNT(*) DESC LIMIT 1").fetchone()
        con.close()
        cls.owner_symbol_id = row[0]
        cls.adapter = SQIAdapter(DB / "brpc.db", COMMITS["brpc"])

    @classmethod
    def tearDownClass(cls):
        cls.adapter.close()

    def test_unresolved_rows_returned_verbatim(self):
        envelope = self.adapter.symbol_references(self.owner_symbol_id)
        statuses = {row["status"] for row in envelope["data"]}
        self.assertIn("unresolved", statuses)
        raw = next(row for row in envelope["data"] if row["status"] == "unresolved")
        self.assertIn(raw.get("resolved_symbol_id"), ("", None))  # verbatim, unrewritten
        self.assertGreater(
            envelope["result_meta"]["status_counts"].get("unresolved", 0), 0)
        ok, errors = validate_envelope(envelope)
        self.assertTrue(ok, errors)

    def test_status_filter_returns_only_that_status(self):
        envelope = self.adapter.symbol_references(self.owner_symbol_id,
                                                  status="unresolved")
        self.assertTrue(envelope["data"])
        for row in envelope["data"]:
            self.assertEqual(row["status"], "unresolved")

    def test_reference_rows_carry_file_path(self):
        """Agent-facing enrichment: file_id hashes must be accompanied by the
        repo-relative path (frozen T03 requires file-and-line reporting)."""
        gt = json.loads((REPO / "experiments" / "query_interface_v1" / "tasks"
                         / "SQI-T03.json").read_text(encoding="utf-8"))
        with SQIAdapter(DB / "rocksdb.db", COMMITS["rocksdb"]) as adapter:
            envelope = adapter.symbol_references(gt["ground_truth"]["symbol_id"])
        rows = [row for row in envelope["data"]
                if row.get("resolved_symbol_id") == gt["ground_truth"]["symbol_id"]]
        self.assertEqual(len(rows), 6)
        for row in rows:
            self.assertTrue(row.get("file_path"), row)
            self.assertFalse(str(row["file_path"]).startswith("file:"))
            self.assertLess(len(row["file_path"]), 200)


class TestImpactFrontierBoundaries(unittest.TestCase):
    """7. shard-level frontier only; no symbol-level derivation."""

    @classmethod
    def setUpClass(cls):
        cls.adapter = SQIAdapter(DB / "rocksdb.db", COMMITS["rocksdb"])
        # T04 frozen budget: full 49-shard frontier fits (rows <= 50), while
        # the 1031 boundary edge ids are a budgeted listing
        cls.envelope = cls.adapter.impact_frontier(
            ["db", "file"], threshold=8,
            budget={"max_evidence": 50, "max_symbols": 20, "max_edges": 50,
                    "max_sections": 10})

    @classmethod
    def tearDownClass(cls):
        cls.adapter.close()

    def test_matches_recomputed_expectation(self):
        meta = self.envelope["result_meta"]
        self.assertEqual(meta["frontier_size"], 49)
        self.assertTrue(meta["wide_impact"])
        self.assertEqual(meta["boundary_edges_total"], 1031)
        # the aggregate must stay exact even when the listing is budgeted
        listed = sum(len(row["boundary_edge_ids"]) for row in self.envelope["data"])
        self.assertEqual(meta["boundary_edge_ids_returned"], listed)
        self.assertEqual(meta["boundary_edge_ids_omitted"], 1031 - listed)
        total_edges = sum(row["boundary_edge_count"] for row in self.envelope["data"])
        self.assertEqual(total_edges, 1031)

    def test_rows_are_shard_level_only(self):
        allowed = {"id", "shard_path", "changed_shard_path", "boundary_edge_count",
                   "boundary_edge_ids", "boundary_edge_ids_omitted"}
        for row in self.envelope["data"]:
            self.assertTrue(set(row.keys()) <= allowed, row.keys())
            self.assertTrue(str(row["id"]).startswith("shard:"))

    def test_evidence_is_shard_relation_only(self):
        self.assertTrue(self.envelope["evidence"])
        for item in self.envelope["evidence"]:
            self.assertEqual(item["kind"], "SHARD_RELATION")

    def test_symbol_level_fields_absent_from_envelope(self):
        allowed_row_keys = {"id", "shard_path", "changed_shard_path",
                            "boundary_edge_count", "boundary_edge_ids",
                            "boundary_edge_ids_omitted"}
        for row in self.envelope["data"]:
            self.assertTrue(set(row.keys()) <= allowed_row_keys, row.keys())
        for item in self.envelope["evidence"]:
            self.assertFalse(str(item.get("source_id", "")).startswith("symbol:"))
            self.assertFalse(str(item.get("target_id", "")).startswith("symbol:"))
        self.assertNotIn("qualified_name", json.dumps(self.envelope["data"]))
        self.assertNotIn("signature", json.dumps(self.envelope["data"]))


class TestSourceVerificationPolicy(unittest.TestCase):
    """8. every envelope carries the frozen S8 verification policy; semantic
    assertion classes can never be marked directly trustworthy."""

    def test_policy_present_and_frozen(self):
        with SQIAdapter(DB / "aria2.db", COMMITS["aria2"]) as adapter:
            envelope = adapter.symbol_lookup("DownloadEngine")
        policy = envelope["source_verification_policy"]
        self.assertTrue(REQUIRED_SOURCE_CLASSES.issubset(
            set(policy["requires_source_verification"])))
        for forbidden in REQUIRED_SOURCE_CLASSES:
            self.assertNotIn(forbidden, policy["direct_trust"])

    def test_validator_rejects_incomplete_policy(self):
        envelope = TestProvenanceMismatch._valid_envelope(self)
        # fresh dict: the module-level policy constant must never be mutated
        envelope["source_verification_policy"] = {
            **envelope["source_verification_policy"],
            "requires_source_verification": []}
        errors = semantic_errors(envelope)
        self.assertTrue(any("S8" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

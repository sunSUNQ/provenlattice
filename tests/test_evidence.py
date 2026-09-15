from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from provenlattice.evidence import (
    Evidence, EvidenceBundle, QueryBudget, evidence_id, parse_evidence_citations,
    rank_evidence,
)
from provenlattice.graph import full_index
from provenlattice.knowledge import index_knowledge
from provenlattice.query import GraphQuery


FIXTURE = Path(__file__).parent / "fixture_knowledge"


def sample(kind: str, name: str, *, status: str = "resolved", direct: bool = True,
           confidence: float = 1.0, distance: int = 1, boundary: bool = False) -> Evidence:
    return Evidence.create(
        kind=kind, source_id=f"source:{name}", relation="RELATES_TO",
        target_id=f"target:{name}", repository="repo:test", commit="C1", generation=1,
        provenance="test", confidence=confidence, source_path="src/test.cpp",
        start_line=1, end_line=2, summary=name, fact_id=f"fact:{name}",
        metadata={"resolution_status": status, "direct": direct, "distance": distance,
                  "boundary_relevant": boundary},
    )


class EvidenceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)
        index_knowledge(self.root, self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_id_is_stable_across_commit_generation_and_query_order(self) -> None:
        first = Evidence.create(
            kind="CODE_DEFINITION", source_id="file:one", relation="DEFINES",
            target_id="symbol:one", repository="repo:test", commit="C1", generation=1,
            provenance="tree_sitter_syntax", confidence=1.0, source_path="src/one.cpp",
            start_line=10, end_line=20, summary="one", fact_id="symbol:one",
        )
        second = Evidence.create(
            kind="CODE_DEFINITION", source_id="file:one", relation="DEFINES",
            target_id="symbol:one", repository="repo:test", commit="C2", generation=99,
            provenance="tree_sitter_syntax", confidence=1.0, source_path="src/one.cpp",
            start_line=10, end_line=20, summary="one", fact_id="symbol:one",
        )
        self.assertEqual(first.evidence_id, second.evidence_id)
        self.assertEqual(first.evidence_id, evidence_id(
            "CODE_DEFINITION", "repo:test", "file:one", "DEFINES", "symbol:one",
            "symbol:one"))

    def test_ranking_and_bundle_are_deterministic_and_bounded(self) -> None:
        values = [
            sample("REFERENCE", "unresolved", status="unresolved", confidence=1.0),
            sample("REFERENCE", "indirect", direct=False, confidence=1.0),
            sample("REFERENCE", "low", confidence=0.5),
            sample("REFERENCE", "boundary", boundary=True),
            sample("REFERENCE", "direct", confidence=1.0),
        ]
        expected = [item.evidence_id for item in rank_evidence(values)]
        self.assertEqual(expected, [item.evidence_id for item in rank_evidence(reversed(values))])
        self.assertEqual(expected[0], sample("REFERENCE", "boundary", boundary=True).evidence_id)
        budget = QueryBudget(max_evidence=3, max_symbols=2, max_edges=2, max_sections=1)
        first = EvidenceBundle.create(
            anchor="A", intent="explain_symbol", summary="summary",
            primary_evidence=values[:2], supporting_evidence=values[2:],
            related_entities=[{"id": "1"}, {"id": "2"}, {"id": "3"}],
            uncertainties=[], generation=1, budget=budget,
        )
        second = EvidenceBundle.create(
            anchor="A", intent="explain_symbol", summary="summary",
            primary_evidence=reversed(values[:2]), supporting_evidence=reversed(values[2:]),
            related_entities=[{"id": "1"}, {"id": "2"}, {"id": "3"}],
            uncertainties=[], generation=1, budget=budget,
        )
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertLessEqual(len(first.evidence_ids), 3)
        self.assertLessEqual(len(first.related_entities), 2)

    def test_task_profile_assigns_roles_suppresses_unresolved_and_honors_role_budgets(self) -> None:
        document = sample("DOCUMENT_SECTION", "document")
        link = sample("CROSS_LAYER_LINK", "link")
        code = sample("CODE_DEFINITION", "code")
        unresolved = sample("CROSS_LAYER_LINK", "candidate", status="ambiguous")
        bundle = EvidenceBundle.create(
            anchor="document", intent="find_related_code", summary="summary",
            primary_evidence=[document, link, code], supporting_evidence=[unresolved],
            related_entities=[], uncertainties=[], generation=1,
            budget=QueryBudget(max_evidence=8, max_primary=1, max_supporting=1, max_total=2),
            profile="document_to_code",
        )
        self.assertEqual(len(bundle.primary_evidence), 1)
        self.assertEqual(len(bundle.supporting_evidence), 1)
        self.assertEqual(bundle.primary_evidence[0].metadata["bundle_role"], "PRIMARY")
        self.assertNotIn(unresolved.evidence_id, bundle.evidence_ids)
        self.assertEqual(bundle.suppressed_evidence_ids, (unresolved.evidence_id,))
        self.assertEqual(bundle.to_dict()["profile"], "document_to_code")

    def test_structured_queries_are_deterministic_bounded_and_traceable(self) -> None:
        with GraphQuery(self.database) as query:
            first = query.explain_symbol(
                "storage.StorageRecovery.retry", max_evidence=4, max_symbols=2,
                max_edges=2, max_sections=1)
            second = query.explain_symbol(
                "storage.StorageRecovery.retry", max_evidence=4, max_symbols=2,
                max_edges=2, max_sections=1)
            self.assertEqual(first["query_id"], second["query_id"])
            self.assertEqual(first["returned_evidence_ids"], second["returned_evidence_ids"])
            self.assertEqual(first["bundle"], second["bundle"])
            self.assertLessEqual(first["returned_evidence_count"], 4)
            self.assertLessEqual(len(first["bundle"]["related_entities"]), 2)
            for item_id in first["returned_evidence_ids"]:
                traced = query.trace_evidence(item_id)
                self.assertEqual(traced["returned_evidence_ids"], [item_id])

            primary = first["bundle"]["primary_evidence"]
            supporting = first["bundle"]["supporting_evidence"]
            document_sections = [item for item in primary
                                 if item["kind"] == "DOCUMENT_SECTION"]
            cross_layer_links = [item for item in supporting
                                 if item["kind"] == "CROSS_LAYER_LINK"]
            self.assertEqual(len(document_sections), 1)
            self.assertEqual(len(cross_layer_links), 1)
            self.assertEqual(document_sections[0]["target_id"],
                             cross_layer_links[0]["source_id"])

            candidates = query.find_related_code("REQ-RECOVERY-001", max_evidence=10)
            candidate_id = next(
                item["evidence_id"] for item in candidates["bundle"]["supporting_evidence"]
                if item["metadata"].get("resolution_status") != "resolved"
            )
            self.assertEqual(query.trace_evidence(candidate_id)["returned_evidence_ids"],
                             [candidate_id])

    def test_citation_parser_accepts_only_contract_ids_and_preserves_order(self) -> None:
        first = sample("CALL_RELATION", "call").evidence_id
        second = sample("DOCUMENT_SECTION", "doc").evidence_id
        text = f"Evidence Used:\n- {first}\n- invalid\n- {second}\n- {first}"
        self.assertEqual(parse_evidence_citations(text), [first, second])


if __name__ == "__main__":
    unittest.main()

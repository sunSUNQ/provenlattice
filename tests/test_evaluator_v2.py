from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path


evaluator = importlib.import_module("experiments.retrieval-v2.evaluator-v2.evaluator")


def task(groups, *, exact=("E-CODE-000000000000000000000001",), alternatives=(), supporting=(), invalid=()):
    return {"required_evidence_ids": list(exact), "acceptable_alternative_ids": list(alternatives),
            "supporting_evidence_ids": list(supporting), "invalid_evidence_ids": list(invalid),
            "expected_paths": ["src/a.cpp"], "required_concepts":[{"concept_id":"c", "groups":groups}]}


class GroundTruthV2Tests(unittest.TestCase):
    def event(self, *ids):
        return {"evidence_ids": list(ids), "viewed_evidence_ids": list(ids), "used_evidence_ids": list(ids)}

    def test_e1_exact_required(self):
        eid = "E-CODE-000000000000000000000001"
        result = evaluator.evaluate_v2(task([{"mode":"ANY_OF", "evidence":[{"evidence_id":eid}]}],), "src/a.cpp", [self.event(eid)])
        self.assertTrue(result["task_success"]); self.assertEqual(result["exact_evidence_recall"], 1.0)

    def test_e2_valid_alternative(self):
        alt = "E-CODE-000000000000000000000002"
        result = evaluator.evaluate_v2(task([{"mode":"ANY_OF", "evidence":[{"evidence_id":alt}]}], exact=(), alternatives=(alt,)), "src/a.cpp", [self.event(alt)])
        self.assertTrue(result["task_success"]); self.assertEqual(result["citation_classifications"][alt], "SUPPORTED_ALTERNATIVE")

    def test_e3_supporting_only_does_not_cover_required(self):
        support = "E-CODE-000000000000000000000003"
        result = evaluator.evaluate_v2(task([{"mode":"ANY_OF", "evidence":[{"evidence_id":"E-CODE-000000000000000000000004"}]}], exact=(), supporting=(support,)), "src/a.cpp", [self.event(support)])
        self.assertFalse(result["task_success"]); self.assertEqual(result["concept_recall"], 0.0)

    def test_e4_distractor_is_invalid(self):
        bad = "E-CODE-000000000000000000000005"
        result = evaluator.evaluate_v2(task([{"mode":"ANY_OF", "evidence":[{"evidence_id":bad}]}], exact=(), invalid=(bad,)), "src/a.cpp", [self.event(bad)])
        self.assertFalse(result["task_success"]); self.assertEqual(result["invalid_evidence_count"], 1)

    def test_e5_unknown_is_unknown(self):
        unknown = "E-CODE-000000000000000000000006"
        result = evaluator.evaluate_v2(task([], exact=()), "src/a.cpp", [], known_evidence_ids=set())
        result = evaluator.evaluate_v2(task([], exact=()), f"Evidence Used: {unknown}", [], known_evidence_ids=set())
        self.assertEqual(result["unsupported_citation_count"], 1)

    def test_e6_fragment_is_not_a_filesystem_path(self):
        self.assertEqual(evaluator.canonicalize_path("docs/foo.md#section-a"), "docs/foo.md")
        self.assertEqual(evaluator.canonicalize_document_anchor("docs/foo.md#Section A"), "docs/foo.md#section-a")

    def test_e7_windows_posix_equivalent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(evaluator.canonicalize_path(str(root / "src" / "a.cpp"), root), "src/a.cpp")
            self.assertEqual(evaluator.canonicalize_path("src\\a.cpp", root), "src/a.cpp")

    def test_e8_multiple_valid_paths_any_of(self):
        a, b = "E-CODE-000000000000000000000007", "E-CODE-000000000000000000000008"
        result = evaluator.evaluate_v2(task([{"mode":"ANY_OF", "evidence":[{"evidence_id":a},{"evidence_id":b}]}], exact=(), alternatives=(a,b)), "src/a.cpp", [self.event(b)])
        self.assertTrue(result["task_success"])

    def test_e9_partial_all_of_fails(self):
        a, b = "E-CODE-000000000000000000000009", "E-CODE-000000000000000000000010"
        result = evaluator.evaluate_v2(task([{"mode":"ALL_OF", "evidence":[{"evidence_id":a},{"evidence_id":b}]}], exact=(), alternatives=(a,b)), "src/a.cpp", [self.event(a)])
        self.assertFalse(result["task_success"]); self.assertEqual(result["concept_recall"], 0.0)

    def test_e10_invalid_format_is_unknown_or_invalid_not_supported(self):
        result = evaluator.evaluate_v2(task([], exact=()), "Evidence Used: E-NOT-A-VALID-ID", [], known_evidence_ids=set())
        self.assertEqual(result["unsupported_citation_count"], 1); self.assertNotIn("SUPPORTED_EXACT", result["citation_classifications"].values())


if __name__ == "__main__":
    unittest.main()

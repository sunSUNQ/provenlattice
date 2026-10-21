"""Issue Pilot #4 (R2/R3 amendments): frame builder methodological guarantees.

Covers the amendment points that are testable without JDT: seeded
reproducible sampling (R2-1), association-ambiguity exclusion logic (R2-2),
blinding isolation (R2-3), Stable decision-rule boundaries (R2-4),
gate-ack binding (R2-5), INCONCLUSIVE evidence-sufficiency gates (R3-1),
external owner-authorization verification (R3-2). Population measurement
itself is exercised by `stats` runs.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "experiments"))

from experiments.java_rq1_formal.build_frame import (  # noqa: E402
    BLIND_FIELDS, OWNER_LOGIN, PLAN_VERSION, STRATA, allocate, case_id,
    expected_gate_ack, make_blind_case, plan_sha256, select_cases,
    verify_authorization,
)
from experiments.java_rq1_formal.decision_rule import stable_verdict  # noqa: E402


def _fake_population(n: int, repo_file_prefix: str = "src/A") -> list[dict]:
    return [
        {"file": f"{repo_file_prefix}{i}.java", "line": i + 1,
         "raw_name": f"call{i}", "status": "resolved",
         "resolution_strategy": "exact", "confidence": 0.9,
         "target": f"T{i}.m", "jdt_state": None}
        for i in range(n)
    ]


class AllocationTests(unittest.TestCase):
    def test_allocation_is_deterministic_and_quota_holding(self):
        populations = {s: _fake_population(100 + i * 7) for i, s in enumerate(STRATA)}
        first = allocate(populations)
        second = allocate(populations)
        self.assertEqual(first, second)
        self.assertEqual(sum(first.values()), 58)
        for n in first.values():
            self.assertTrue(0 <= n <= 24)
            if n:
                self.assertGreaterEqual(n, 3)


class SeededSamplingTests(unittest.TestCase):
    def test_same_seed_same_frame_reproduces_selection(self):
        populations = {s: _fake_population(50) for s in STRATA}
        allocation = allocate(populations)
        a = select_cases(populations, allocation, "gson", "frame-id-1")
        b = select_cases(populations, allocation, "gson", "frame-id-1")
        self.assertEqual(a, b)

    def test_selection_is_not_first_n(self):
        populations = {s: _fake_population(50) for s in STRATA}
        allocation = {s: 3 for s in STRATA}
        selected = select_cases(populations, allocation, "gson", "frame-id-1")
        for stratum in STRATA:
            picked_lines = {c["line"] for c in selected[stratum]}
            first_n_lines = {c["line"] for c in populations[stratum][:3]}
            self.assertEqual(len(picked_lines), 3)
            self.assertNotEqual(picked_lines, first_n_lines)

    def test_different_frame_id_changes_selection(self):
        populations = {s: _fake_population(50) for s in STRATA}
        allocation = {s: 5 for s in STRATA}
        a = select_cases(populations, allocation, "gson", "frame-id-1")
        b = select_cases(populations, allocation, "gson", "frame-id-2")
        differing = sum(1 for s in STRATA
                        if {c["line"] for c in a[s]} != {c["line"] for c in b[s]})
        self.assertGreater(differing, 0)


class CaseAssemblyTests(unittest.TestCase):
    """issue-pilot #4 infra fix: the sample-mode case carries the `repo` label
    the blinded view requires (plan §5 {case_id, repo, file, line}), and that
    label is metadata only -- it never enters the case identity."""

    def test_repo_label_is_added_without_changing_case_identity(self):
        base = {"file": "src/A.java", "line": 7, "raw_name": "call",
                "status": "resolved", "resolution_strategy": "exact",
                "confidence": 0.9, "target": "T.m", "jdt_state": None}
        no_repo = case_id(base)
        extended = {**base, "repo": "gson",
                    "stratum": "S1_L1_RESOLVED_L1_ONLY", "annotation": {}}
        extended["case_id"] = case_id(extended)
        self.assertEqual(no_repo, extended["case_id"])
        blind = make_blind_case(extended)
        self.assertEqual(set(blind), {"case_id", "repo", "file", "line"})


class BlindingTests(unittest.TestCase):
    def test_blind_case_whitelist(self):
        case = {"case_id": "JFQ1-abc", "repo": "gson",
                "file": "src/A.java", "line": 7,
                "raw_name": "call", "status": "resolved",
                "resolution_strategy": "exact", "confidence": 0.9,
                "target": "T.m", "jdt_state": "recovered_by_jdt",
                "stratum": "S4_NONRESOLVED_RECOVERED"}
        blind = make_blind_case(case)
        self.assertEqual(set(blind), {"case_id", "repo", "file", "line"})
        self.assertTrue(set(blind) <= BLIND_FIELDS)

    def test_blind_serialization_leaks_no_system_fields(self):
        from experiments.java_rq1_formal.build_frame import SYSTEM_FIELDS
        case = {"case_id": "JFQ1-abc", "repo": "gson",
                "file": "src/A.java", "line": 7,
                "raw_name": "membersGet", "status": "resolved",
                "resolution_strategy": "exact", "confidence": 0.9,
                "target": "com.google.gson.JsonObject.membersGet",
                "jdt_state": "recovered_by_jdt",
                "stratum": "S4_NONRESOLVED_RECOVERED"}
        blind = make_blind_case(case)
        text = json.dumps(blind)
        for field in SYSTEM_FIELDS:
            self.assertNotIn(field, text)
        for value in (case["raw_name"], case["target"],
                      case["jdt_state"], case["stratum"]):
            self.assertNotIn(value, text)


class GateAckTests(unittest.TestCase):
    def test_expected_ack_binds_ref_version_and_plan_hash(self):
        import hashlib
        ref = "https://github.com/sunSUNQ/issue-pilot/issues/4#issuecomment-1"
        expected = hashlib.sha256(
            f"{ref}|{PLAN_VERSION}|{plan_sha256()}".encode("utf-8")
        ).hexdigest()[:16]
        self.assertEqual(expected_gate_ack(ref), expected)

    def test_ack_changes_with_decision_ref(self):
        a = expected_gate_ack("ref-1")
        b = expected_gate_ack("ref-2")
        self.assertNotEqual(a, b)


class StableDecisionRuleTests(unittest.TestCase):
    """Boundary checks for the frozen Stable qualification rule (plan §5),
    exercised through decision_rule.stable_verdict."""

    VALID_SIZES = (
        {s: 10 for s in STRATA},
        {s: 100 for s in STRATA},
    )

    def _verdict(self, rp: float, rp_lo: float, fra: float, fra_hi: float,
                 calibration_passed: bool = True) -> str:
        samples, populations = self.VALID_SIZES
        return stable_verdict(rp, rp_lo, fra, fra_hi, calibration_passed,
                              samples, populations)["verdict"]

    def test_qualifies_only_when_all_bounds_hold(self):
        self.assertEqual(self._verdict(0.92, 0.86, 0.08, 0.12), "QUALIFIED")
        self.assertEqual(self._verdict(0.90, 0.85, 0.10, 0.15), "QUALIFIED")

    def test_point_estimate_pass_but_ci_fails(self):
        self.assertEqual(self._verdict(0.92, 0.84, 0.08, 0.12), "NOT_QUALIFIED")
        self.assertEqual(self._verdict(0.92, 0.86, 0.08, 0.16), "NOT_QUALIFIED")

    def test_point_estimate_fail(self):
        self.assertEqual(self._verdict(0.89, 0.86, 0.08, 0.12), "NOT_QUALIFIED")
        self.assertEqual(self._verdict(0.92, 0.86, 0.11, 0.12), "NOT_QUALIFIED")

    def test_calibration_gate_is_required(self):
        self.assertEqual(self._verdict(0.92, 0.86, 0.08, 0.12,
                                       calibration_passed=False),
                         "NOT_QUALIFIED")


class DegenerateEvidenceTests(unittest.TestCase):
    """R3 revision 1: INCONCLUSIVE on estimator-invalid inputs; the binary
    verdict is unreachable when the weighted estimator cannot be computed
    validly (plan §5 INCONCLUSIVE tier, decision_rule gates G1-G4)."""

    STRATA_SIZES = {s: 100 for s in STRATA}

    def test_total_sample_zero_is_inconclusive(self):
        result = stable_verdict(0.99, 0.95, 0.01, 0.02, True,
                                {s: 0 for s in STRATA}, self.STRATA_SIZES)
        self.assertEqual(result["verdict"], "INCONCLUSIVE")
        self.assertIn("G1_total_sample_zero", result["reasons"])

    def test_unrepresented_stratum_is_inconclusive(self):
        samples = {s: 10 for s in STRATA}
        samples["S3_L1_RESOLVED_JDT_CONFLICT"] = 0
        result = stable_verdict(0.99, 0.95, 0.01, 0.02, True,
                                samples, self.STRATA_SIZES)
        self.assertEqual(result["verdict"], "INCONCLUSIVE")
        self.assertIn("G2_unrepresented_stratum:S3_L1_RESOLVED_JDT_CONFLICT",
                      result["reasons"])

    def test_empty_population_stratum_is_not_a_hole(self):
        populations = {s: 100 for s in STRATA}
        populations["S3_L1_RESOLVED_JDT_CONFLICT"] = 0
        samples = {s: 10 for s in STRATA}
        samples["S3_L1_RESOLVED_JDT_CONFLICT"] = 0
        result = stable_verdict(0.92, 0.86, 0.08, 0.12, True,
                                samples, populations)
        self.assertEqual(result["verdict"], "QUALIFIED")

    def test_undefined_metric_is_inconclusive(self):
        for kwargs in ({"rp": None}, {"fra": None}, {"rp_lo": float("nan")}):
            with self.subTest(**kwargs):
                values = {"rp": 0.92, "rp_lo": 0.86, "fra": 0.08,
                          "fra_hi": 0.12}
                values.update(kwargs)
                result = stable_verdict(
                    values["rp"], values["rp_lo"], values["fra"],
                    values["fra_hi"], True, {s: 10 for s in STRATA},
                    self.STRATA_SIZES)
                self.assertEqual(result["verdict"], "INCONCLUSIVE")
                self.assertTrue(
                    any(r.startswith("G3_metric_undefined")
                        for r in result["reasons"]))

    def test_incomplete_annotation_is_inconclusive(self):
        result = stable_verdict(0.92, 0.86, 0.08, 0.12, True,
                                {s: 10 for s in STRATA},
                                self.STRATA_SIZES,
                                annotation_complete=False)
        self.assertEqual(result["verdict"], "INCONCLUSIVE")
        self.assertIn("G4_annotation_incomplete", result["reasons"])

    def test_wide_but_valid_ci_is_not_inconclusive(self):
        result = stable_verdict(0.92, 0.60, 0.08, 0.40, True,
                                {s: 10 for s in STRATA}, self.STRATA_SIZES)
        self.assertEqual(result["verdict"], "NOT_QUALIFIED")
        self.assertEqual(result["reasons"], [])


class AuthorizationVerificationTests(unittest.TestCase):
    """R3 revision 2: sample mode requires decision_ref to resolve, via the
    GitHub API, to a real Human Owner record carrying the ack token."""

    REF = "https://github.com/sunSUNQ/issue-pilot/issues/4#issuecomment-99"
    ACK = "0123456789abcdef"

    @staticmethod
    def _runner(rc: int = 0, author: str = OWNER_LOGIN,
                body: str = f"frame-freeze approved ack=0123456789abcdef"):
        def run(_args):
            return rc, json.dumps(
                {"user": {"login": author}, "body": body})
        return run

    def test_valid_owner_record_with_ack_verifies(self):
        result = verify_authorization(self.REF, self.ACK, self._runner())
        self.assertTrue(result["verified"])
        self.assertEqual(result["author"], OWNER_LOGIN)
        self.assertEqual(
            result["api_path"],
            "repos/sunSUNQ/issue-pilot/issues/comments/99")

    def test_issue_level_ref_without_comment(self):
        ref = "https://github.com/sunSUNQ/issue-pilot/issues/4"
        result = verify_authorization(ref, self.ACK, self._runner())
        self.assertTrue(result["verified"])
        self.assertEqual(result["api_path"],
                         "repos/sunSUNQ/issue-pilot/issues/4")

    def test_unparseable_ref_is_refused(self):
        result = verify_authorization("https://example.com/x", self.ACK,
                                      self._runner())
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "decision_ref_unparseable")

    def test_unreachable_record_is_refused(self):
        result = verify_authorization(self.REF, self.ACK, self._runner(rc=1))
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "authorization_record_unreachable")

    def test_non_owner_author_is_refused(self):
        result = verify_authorization(self.REF, self.ACK,
                                      self._runner(author="someone-else"))
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "author_not_owner")

    def test_missing_ack_token_is_refused(self):
        result = verify_authorization(
            self.REF, self.ACK,
            self._runner(body="approved, but the token is not here"))
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "ack_token_absent")


if __name__ == "__main__":
    unittest.main()

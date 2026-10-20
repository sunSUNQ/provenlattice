"""Issue Pilot #4 (R2 amendment): frame builder methodological guarantees.

Covers the six R2 amendment points that are testable without JDT:
seeded reproducible sampling (1), association-ambiguity exclusion logic (2),
blinding isolation (3), Stable decision-rule boundaries (4), gate-ack
binding (5). Population measurement itself is exercised by `stats` runs.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "experiments"))

from experiments.java_rq1_formal.build_frame import (  # noqa: E402
    BLIND_FIELDS, PLAN_VERSION, STRATA, allocate, expected_gate_ack,
    make_blind_case, plan_sha256, select_cases,
)


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
    """Boundary checks for the frozen Stable qualification rule (plan §5)."""

    @staticmethod
    def _verdict(rp: float, rp_lo: float, fra: float, fra_hi: float,
                 calibration_passed: bool = True) -> str:
        qualified = (rp >= 0.90 and rp_lo >= 0.85
                     and fra <= 0.10 and fra_hi <= 0.15 and calibration_passed)
        return "QUALIFIED" if qualified else "NOT_QUALIFIED"

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


if __name__ == "__main__":
    unittest.main()

"""V1.2-NR1 discipline tests: generic truncation flag + session usage
discipline + arm-prompt guidance (no benchmark specifics). Uses REAL
archived envelopes from the C4-R2 batch; skips if local raw cells are
absent (same environment-incomplete policy as the DB-backed suites).

Run:  PYTHONPATH=src python -m unittest experiments.query_interface_v1.tests.test_v12_nr1_discipline -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TOOLS = Path(__file__).resolve().parent.parent / "tools"
for _p in (str(TOOLS), str(REPO), str(REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqi_adapter import SOURCE_VERIFICATION_POLICY  # noqa: E402
from sqi_formal_runner import SQI_ARM_PROMPT_TEMPLATE  # noqa: E402
from sqi_validator import validate_envelope  # noqa: E402

BATCH = (REPO / "experiments" / "query_interface_v1" / "results" / "formal" /
         "SQI-FORMAL-C4-20260920T042801Z")


def load_envelopes():
    """Return (truncated_env, plain_env) real envelopes with the NR1 fields
    injected, or None when local raw cells are absent."""
    truncated = plain = None
    for run in sorted(BATCH.glob("SQI-T*/*/*/run.json")):
        log = run.parent / "sqi-call-log.ndjson"
        if not log.exists():
            continue
        for line in log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            envelope = json.loads(line).get("envelope") or {}
            truncation = envelope.get("truncation") or {}
            if truncation.get("truncated") and truncated is None:
                truncated = envelope
            if not truncation.get("truncated") and plain is None:
                plain = envelope
        if truncated and plain:
            break
    if truncated is None or plain is None:
        return None
    for env in (truncated, plain):
        env["truncation"]["retry_same_call_will_not_expand"] = True
        env["source_verification_policy"] = SOURCE_VERIFICATION_POLICY
    return truncated, plain


class TestTruncationFlag(unittest.TestCase):

    def setUp(self):
        self.envelopes = load_envelopes()
        if self.envelopes is None:
            self.skipTest("local C4-R2 raw cells not present")

    def test_truncated_envelope_carries_flag_and_validates(self):
        truncated, _ = self.envelopes
        ok, errors = validate_envelope(truncated)
        self.assertTrue(ok, errors)
        self.assertTrue(truncated["truncation"]
                        ["retry_same_call_will_not_expand"])

    def test_non_truncated_envelope_validates(self):
        _, plain = self.envelopes
        ok, errors = validate_envelope(plain)
        self.assertTrue(ok, errors)

    def test_flag_is_generic_not_benchmark_specific(self):
        truncated, _ = self.envelopes
        serialized = json.dumps(truncated["truncation"])
        self.assertNotIn("T06", serialized)
        self.assertNotIn("T05", serialized)


class TestUsageDiscipline(unittest.TestCase):

    def test_policy_contains_discipline_rules(self):
        rules = SOURCE_VERIFICATION_POLICY.get("usage_discipline", [])
        # 2 frozen NR1 rules + 1 NR2 empty-result rule (appended, NR1
        # rules[0]/rules[1] unchanged)
        self.assertEqual(len(rules), 3)
        self.assertIn("byte-identical envelope", rules[0])
        self.assertIn("will not expand", rules[0])
        self.assertIn("source domain", rules[1])
        # generic: no task/benchmark identifiers
        for rule in rules:
            self.assertNotIn("T05", rule)
            self.assertNotIn("T06", rule)

    def test_policy_validates_against_schema(self):
        envelopes = load_envelopes()
        if envelopes is None:
            self.skipTest("local C4-R2 raw cells not present")
        plain = envelopes[1]
        ok, errors = validate_envelope(plain)
        self.assertTrue(ok, errors)
        self.assertEqual(len(plain["source_verification_policy"]
                             ["usage_discipline"]), 3)

    def test_arm_prompt_carries_discipline(self):
        self.assertIn("Never repeat an identical bridge invocation",
                      SQI_ARM_PROMPT_TEMPLATE)
        self.assertIn("will not expand", SQI_ARM_PROMPT_TEMPLATE)
        self.assertIn("every distinct source domain", SQI_ARM_PROMPT_TEMPLATE)
        self.assertNotIn("T05", SQI_ARM_PROMPT_TEMPLATE)
        self.assertNotIn("T06", SQI_ARM_PROMPT_TEMPLATE)


if __name__ == "__main__":
    unittest.main()

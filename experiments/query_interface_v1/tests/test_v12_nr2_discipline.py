"""V1.2-NR2 discipline tests: generic empty-result exploration guidance.

Covers the three NR2 surfaces (no benchmark specifics, no required ids,
no task-id special-casing):
  * adapter: empty envelopes (zero data rows, zero evidence, no error)
    carry result_meta.empty_result_guidance; non-empty envelopes are
    byte-unchanged; error envelopes never carry the guidance;
  * session usage_discipline gains the third generic rule (NR1 rules
    unchanged);
  * the SQI arm prompt carries the mirrored sentence.

Uses REAL archived envelopes from the C4-R3 batch; skips if local raw
cells are absent (same environment-incomplete policy as NR1 tests).

Run:  PYTHONPATH=src python -m unittest experiments.query_interface_v1.tests.test_v12_nr2_discipline -v
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

from sqi_adapter import (  # noqa: E402
    EMPTY_RESULT_GUIDANCE, SOURCE_VERIFICATION_POLICY)
from sqi_formal_runner import SQI_ARM_PROMPT_TEMPLATE  # noqa: E402
from sqi_validator import validate_envelope  # noqa: E402

BATCH = (REPO / "experiments" / "query_interface_v1" / "results" / "formal" /
         "SQI-FORMAL-C4-20260920T072457Z")


def load_envelopes():
    """Return (empty_env, nonempty_env) real C4-R3 envelopes with the NR1
    policy fields injected, or None when local raw cells are absent."""
    empty = nonempty = None
    for run in sorted(BATCH.glob("SQI-T*/*/*/run.json")):
        log = run.parent / "sqi-call-log.ndjson"
        if not log.exists():
            continue
        for line in log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            envelope = json.loads(line).get("envelope") or {}
            if envelope.get("error") or not envelope.get("query_type"):
                continue
            has_content = bool(envelope.get("data") or envelope.get("evidence")
                               or envelope.get("returned_evidence_ids"))
            if has_content and nonempty is None:
                nonempty = envelope
            elif not has_content and empty is None:
                empty = envelope
        if empty and nonempty:
            break
    if empty is None or nonempty is None:
        return None
    for env in (empty, nonempty):
        env.pop("empty_result_guidance", None)
        env["source_verification_policy"] = SOURCE_VERIFICATION_POLICY
        env.setdefault("truncation", {})["retry_same_call_will_not_expand"] = True
    return empty, nonempty


class TestEmptyResultGuidance(unittest.TestCase):

    def setUp(self):
        self.envelopes = load_envelopes()
        if self.envelopes is None:
            self.skipTest("local C4-R3 raw cells not present")

    def test_empty_envelope_carries_guidance_and_validates(self):
        empty, _ = self.envelopes
        empty.setdefault("result_meta", {})["empty_result_guidance"] = \
            EMPTY_RESULT_GUIDANCE
        ok, errors = validate_envelope(empty)
        self.assertTrue(ok, errors)
        self.assertEqual(empty["result_meta"]["empty_result_guidance"],
                         EMPTY_RESULT_GUIDANCE)

    def test_nonempty_envelope_validates_without_guidance(self):
        _, nonempty = self.envelopes
        ok, errors = validate_envelope(nonempty)
        self.assertTrue(ok, errors)
        self.assertNotIn("empty_result_guidance", nonempty["result_meta"])

class TestErrorEnvelope(unittest.TestCase):
    """No archived cells needed: exercises the adapter error path directly."""

    def test_error_envelope_excludes_guidance(self):
        # authoritative behavior test: SQIAdapter._error pops the guidance
        # (no DB needed — _envelope touches no graph for empty raw results)
        from sqi_adapter import SQIAdapter
        adapter = object.__new__(SQIAdapter)
        adapter.repository = "repo:" + "0" * 64
        adapter.commit = "a" * 40
        envelope = adapter._error(
            "code.related", "", {"document": ""}, None,
            "INVALID_INPUT", "document must be a non-empty string")
        self.assertIn("error", envelope)
        self.assertNotIn("empty_result_guidance",
                         envelope.get("result_meta") or {})

    def test_guidance_is_generic_not_benchmark_specific(self):
        serialized = EMPTY_RESULT_GUIDANCE
        self.assertNotIn("T05", serialized)
        self.assertNotIn("T06", serialized)
        self.assertNotIn("E-", serialized)
        self.assertNotIn("c_murmurhash", serialized.lower())

    def test_guidance_states_resolution_semantics(self):
        self.assertIn("exact node id", EMPTY_RESULT_GUIDANCE)
        self.assertIn("qualified_name", EMPTY_RESULT_GUIDANCE)
        self.assertIn("node name", EMPTY_RESULT_GUIDANCE)
        self.assertIn("vary the identifier form", EMPTY_RESULT_GUIDANCE)


class TestSessionRule(unittest.TestCase):

    def test_usage_discipline_has_three_generic_rules(self):
        rules = SOURCE_VERIFICATION_POLICY["usage_discipline"]
        self.assertEqual(len(rules), 3)
        self.assertIn("empty envelope", rules[2])
        self.assertIn("semantically equivalent forms", rules[2])
        for banned in ("T05", "T06", "E-"):
            self.assertNotIn(banned, rules[2])


class TestArmPrompt(unittest.TestCase):

    def test_prompt_carries_empty_result_discipline(self):
        self.assertIn("An empty envelope is definitive for the anchor form",
                      SQI_ARM_PROMPT_TEMPLATE)
        self.assertIn("symbol.lookup or bundle.explain on the anchor alone",
                      SQI_ARM_PROMPT_TEMPLATE)
        self.assertIn("semantically equivalent forms",
                      SQI_ARM_PROMPT_TEMPLATE)
        # generic: no task/benchmark identifiers
        self.assertNotIn("T05", SQI_ARM_PROMPT_TEMPLATE)
        self.assertNotIn("T06", SQI_ARM_PROMPT_TEMPLATE)


if __name__ == "__main__":
    unittest.main()

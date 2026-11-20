"""Tests for the Agent/Skill API V1 (Issue #86, acceptance matrix M1-M8).

These tests never run the engine: the resolution / forwarding cases drive the
wrapped ``adapter.analyze_*`` against a stubbed ``query_defect`` source and the
real captured fixtures (mirroring ``test_evidence_registry.py``). They never
import the skill, never touch GT/Prompt/Scorer, and never modify the GATE-0 or
IR V1 modules.
"""

import copy
import json
import unittest
from pathlib import Path
from unittest import mock

from provenlattice.evidence_projection import adapter, constants as C, ir, registry
from provenlattice.evidence_projection import skill_api

FIXTURES = Path(__file__).resolve().parent.parent / "src" / "provenlattice" \
    / "evidence_projection" / "fixtures"
DOCS = Path(__file__).resolve().parent.parent / "docs" \
    / "skill-interface-requirements.md"
SKILL_API_SOURCE = Path(skill_api.__file__).read_text(encoding="utf-8")

_CONCURRENCY_NOT_PROJECTED = {
    "thread_context", "parallel_feasibility", "common_locks",
    "spawn_join", "interprocedural_path",
}


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def serialize(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def source_ok(result: dict) -> dict:
    return {"status": C.ST_OK, "result": result, "error": None, "reason": None}


def _race_src():
    return source_ok({"candidates": [load("race_candidate.json")]})


def _double_free_src():
    return source_ok({"candidates": [load("double_free_candidate.json")]})


class ManifestTruthfulnessTests(unittest.TestCase):
    """M1: the manifest is truthful and organised per defect_type."""

    def test_manifest_version_and_defect_types(self):
        manifest = skill_api.list_skill_capabilities()
        self.assertEqual(manifest["manifest_version"], skill_api.MANIFEST_VERSION)
        self.assertEqual(sorted(manifest["defect_types"]),
                         ["double_free", "race_condition"])

    def test_manifest_defect_types_match_registry(self):
        manifest = skill_api.list_skill_capabilities()
        reg_types = [c["defect_type"]
                     for c in registry.REGISTRY.list_projector_capabilities()]
        self.assertEqual(sorted(manifest["defect_types"]), reg_types)

    def test_manifest_projector_version_read_from_registry(self):
        manifest = skill_api.list_skill_capabilities()
        for defect_type, block in manifest["defect_types"].items():
            self.assertEqual(
                block["projector_version"],
                registry.REGISTRY.get_projector(defect_type).projector_version)

    def test_race_project_facts_only_shared_accesses(self):
        manifest = skill_api.list_skill_capabilities()
        race = manifest["defect_types"]["race_condition"]
        self.assertEqual(sorted(race["projected_facts"]), ["shared_accesses"])

    def test_race_not_projected_facts_are_five_produced_not_projected(self):
        manifest = skill_api.list_skill_capabilities()
        race = manifest["defect_types"]["race_condition"]
        self.assertEqual(set(race["not_projected_facts"]),
                         _CONCURRENCY_NOT_PROJECTED)
        for fact in race["not_projected_facts"].values():
            self.assertEqual(fact["status"], "produced_not_projected")
            self.assertTrue(fact.get("source"))
            self.assertTrue(fact.get("limitations"))

    def test_race_not_produced_facts_is_happens_before_only(self):
        manifest = skill_api.list_skill_capabilities()
        race = manifest["defect_types"]["race_condition"]
        self.assertEqual(sorted(race["not_produced_facts"]), ["happens_before"])
        self.assertEqual(race["not_produced_facts"]["happens_before"]["status"],
                         "not_produced")

    def test_double_free_projects_release_sites_and_no_concurrency_facts(self):
        manifest = skill_api.list_skill_capabilities()
        df = manifest["defect_types"]["double_free"]
        # double_free is a memory-safety defect: its projected fact type is
        # release_sites (not shared_accesses), and it carries none of the
        # concurrency not_projected / not_produced facts.
        self.assertEqual(sorted(df["projected_facts"]), ["release_sites"])
        self.assertEqual(df["not_projected_facts"], {})
        self.assertEqual(df["not_produced_facts"], {})

    def test_projected_facts_vs_evidence_are_distinguished(self):
        manifest = skill_api.list_skill_capabilities()
        race = manifest["defect_types"]["race_condition"]
        self.assertEqual(sorted(race["projected_facts"]), ["shared_accesses"])
        self.assertEqual(sorted(race["projected_evidence"]),
                         ["evidence_locations", "supporting_locations"])

    def test_supporting_location_fields_are_13(self):
        manifest = skill_api.list_skill_capabilities()
        fields = manifest["defect_types"]["race_condition"] \
            ["projected_evidence"]["supporting_locations"]["fields"]
        self.assertEqual(len(fields), 13)
        self.assertEqual(fields, list(skill_api.SUPPORTING_LOCATION_FIELDS))

    def test_evidence_location_fields_are_9(self):
        manifest = skill_api.list_skill_capabilities()
        fields = manifest["defect_types"]["race_condition"] \
            ["projected_evidence"]["evidence_locations"]["fields"]
        self.assertEqual(len(fields), 9)
        self.assertEqual(fields, list(skill_api.EVIDENCE_LOCATION_FIELDS))

    def test_anchor_class_and_semantic_role_enums(self):
        manifest = skill_api.list_skill_capabilities()
        ev = manifest["defect_types"]["race_condition"]["projected_evidence"]
        self.assertEqual(ev["supporting_locations"]["anchor_class"],
                         list(skill_api.ANCHOR_CLASSES))
        self.assertEqual(ev["supporting_locations"]["semantic_role"],
                         list(skill_api.SEMANTIC_ROLES))


class EvidenceResolutionTests(unittest.TestCase):
    """M2: resolve_evidence composes Registry -> adapter -> IR and validates."""

    def _resolve(self, defect_type, src):
        with mock.patch.object(adapter, "query_defect",
                               side_effect=lambda *a, **k: copy.deepcopy(src)):
            return skill_api.resolve_evidence(
                "repo", "graph.db", defect_type=defect_type)

    def test_race_resolution_is_valid_ir(self):
        evidence = self._resolve("race_condition", _race_src())
        self.assertEqual(ir.validate_evidence_ir_v1(evidence), [])
        self.assertEqual(evidence["ir_schema_version"], ir.IR_SCHEMA_VERSION)
        self.assertEqual(evidence["run"]["projector_version"], ir.PROJECTOR_VERSION)

    def test_double_free_resolution_is_valid_ir(self):
        evidence = self._resolve("double_free", _double_free_src())
        self.assertEqual(ir.validate_evidence_ir_v1(evidence), [])
        self.assertEqual(evidence["run"]["projector_version"], ir.PROJECTOR_VERSION)

    def test_run_projector_version_is_frozen_not_applicable(self):
        evidence = self._resolve("race_condition", _race_src())
        self.assertEqual(evidence["run"]["projector_version"], "NOT_APPLICABLE")
        # never overwritten by the Registry projector_version ("1")
        self.assertNotEqual(evidence["run"]["projector_version"],
                            registry.REGISTRY.get_projector("race_condition")
                            .projector_version)


class FailClosedTests(unittest.TestCase):
    """M3: unknown defect / analyze exception / IR validation failure all fail
    closed, never returning an invalid IR."""

    def test_unknown_defect_type_is_rejected(self):
        with self.assertRaises(registry.UnknownDefectTypeError):
            skill_api.resolve_evidence("repo", "graph.db",
                                       defect_type="nonexistent")

    def test_analyze_exception_propagates_verbatim(self):
        class Boom:
            def analyze(self, *a, **k):
                raise RuntimeError("boom")

        with mock.patch.object(registry.REGISTRY, "get_projector",
                               return_value=Boom()):
            with self.assertRaises(RuntimeError):
                skill_api.resolve_evidence("repo", "graph.db",
                                           defect_type="race_condition")

    def test_ir_validation_failure_raises(self):
        with mock.patch.object(adapter, "query_defect",
                               side_effect=lambda *a, **k: copy.deepcopy(_race_src())), \
             mock.patch.object(ir, "validate_evidence_ir_v1",
                               return_value=["boom"]):
            with self.assertRaises(skill_api.EvidenceIRValidationError):
                skill_api.resolve_evidence("repo", "graph.db",
                                           defect_type="race_condition")


class ForwardingTests(unittest.TestCase):
    """M4: target_symbols / **kwargs forwarded verbatim; run_context to IR only."""

    @staticmethod
    def _fake_projector(capture, return_bundle):
        def fake_analyze(case_workdir, database, target_symbols=(), **kwargs):
            capture.update(case_workdir=case_workdir, database=database,
                           target_symbols=target_symbols, kwargs=kwargs)
            return return_bundle
        return registry.AdapterProjector("race_condition", "1", fake_analyze)

    def test_target_symbols_and_kwargs_forwarded(self):
        captured = {}
        fake = self._fake_projector(captured, load("race_factbundle_v2_1.json"))
        with mock.patch.object(registry.REGISTRY, "get_projector",
                               return_value=fake):
            skill_api.resolve_evidence(
                "repo", "graph.db", defect_type="race_condition",
                target_symbols=("a", "b"), extra=1)
        self.assertEqual(captured["target_symbols"], ("a", "b"))
        self.assertEqual(captured["kwargs"], {"extra": 1})

    def test_run_context_goes_to_ir_only(self):
        captured = {}
        fake = self._fake_projector(captured, load("race_factbundle_v2_1.json"))
        with mock.patch.object(registry.REGISTRY, "get_projector",
                               return_value=fake):
            evidence = skill_api.resolve_evidence(
                "repo", "graph.db", defect_type="race_condition",
                run_context={"code_revision": "abc123"})
        self.assertNotIn("run_context", captured["kwargs"])
        self.assertEqual(evidence["run"]["code_revision"], "abc123")


class DocsConsistencyTests(unittest.TestCase):
    """M5: the skill requirements document matches the manifest (M1)."""

    def test_docs_declare_13_fields_and_7_facts(self):
        text = DOCS.read_text(encoding="utf-8")
        for field in skill_api.SUPPORTING_LOCATION_FIELDS:
            self.assertIn(field, text)
        for fact in ("shared_accesses", "thread_context", "parallel_feasibility",
                     "common_locks", "spawn_join", "happens_before",
                     "interprocedural_path"):
            self.assertIn(fact, text)
        self.assertIn("produced_not_projected", text)
        self.assertIn("not_produced", text)


class ScopeTests(unittest.TestCase):
    """M6 + M8: skill_api imports only the evidence_projection package + stdlib."""

    ALLOWED_IMPORT_PREFIXES = ("from __future__", "from typing", "from .")

    def test_skill_api_imports_are_scoped(self):
        for line in SKILL_API_SOURCE.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                self.assertTrue(
                    any(stripped.startswith(p)
                        for p in self.ALLOWED_IMPORT_PREFIXES),
                    "unexpected import: " + stripped)

    def test_skill_api_does_not_import_engine_or_skill(self):
        for token in ("defect_query", "analysis_concurrency",
                      "prompt", "scorer", "SKILL.md"):
            self.assertNotIn("import " + token, SKILL_API_SOURCE)


class DeterminismTests(unittest.TestCase):
    """M7: outputs are byte-stable across repeated calls."""

    def test_manifest_is_deterministic(self):
        self.assertEqual(serialize(skill_api.list_skill_capabilities()),
                         serialize(skill_api.list_skill_capabilities()))

    def test_resolution_is_deterministic(self):
        src = _race_src()
        with mock.patch.object(adapter, "query_defect",
                               side_effect=lambda *a, **k: copy.deepcopy(src)):
            a = skill_api.resolve_evidence("repo", "graph.db",
                                           defect_type="race_condition")
            b = skill_api.resolve_evidence("repo", "graph.db",
                                           defect_type="race_condition")
        self.assertEqual(serialize(a), serialize(b))


if __name__ == "__main__":
    unittest.main()
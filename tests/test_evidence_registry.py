"""Tests for the Projector Registry V1 (Issue #83, acceptance matrix M1-M10).

These tests never run the engine: the forwarding-consistency / determinism
cases drive the wrapped ``adapter.analyze_*`` against a stubbed ``query_defect``
source and the real captured fixtures, and the extensibility cases use a
test-only projector on an independent ``Registry()`` (never the production
global ``REGISTRY``).
"""

import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest import mock

from provenlattice.evidence_projection import adapter, constants as C, ir, registry

FIXTURES = Path(__file__).resolve().parent.parent / "src" / "provenlattice" \
    / "evidence_projection" / "fixtures"
SCHEMA = Path(__file__).resolve().parent.parent / "src" / "provenlattice" \
    / "evidence_projection" / "schema" / "factbundle_v2_1.schema.json"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def serialize(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_ok(result: dict) -> dict:
    return {"status": C.ST_OK, "result": result, "error": None, "reason": None}


def fake_analyze(case_workdir, database, target_symbols=(), **kwargs):
    """A test-only projector body (never wired to the engine)."""
    return {"api_version": "v1.1", "status": "ok", "defect_type": "test_only",
            "case_workdir": case_workdir, "database": database,
            "target_symbols": list(target_symbols)}


class BuiltinRegistrationTests(unittest.TestCase):
    """M1: module load registers the seven production projectors."""

    def test_production_registry_has_seven_builtins(self):
        caps = registry.REGISTRY.list_projector_capabilities()
        self.assertEqual([c["defect_type"] for c in caps],
                         ["double_free", "lock_order", "mismatched_free",
                          "null_flow", "race_condition", "resource_lifetime",
                          "use_after_free"])
        self.assertEqual(len(caps), 7)

    def test_builtin_projector_versions(self):
        for cap in registry.REGISTRY.list_projector_capabilities():
            self.assertEqual(cap["projector_version"],
                             registry.PROJECTOR_MECHANISM_VERSION)

    def test_builtins_wrap_gate0_entries(self):
        race = registry.REGISTRY.get_projector("race_condition")
        df = registry.REGISTRY.get_projector("double_free")
        self.assertEqual(race._analyze, adapter.analyze_shared_access)
        self.assertEqual(df._analyze, adapter.analyze_double_free)
        expected = {
            "lock_order": adapter.analyze_lock_order,
            "resource_lifetime": adapter.analyze_resource_lifetime,
            "use_after_free": adapter.analyze_use_after_free,
            "null_flow": adapter.analyze_null_flow,
            "mismatched_free": adapter.analyze_mismatched_free,
        }
        for defect_type, entry in expected.items():
            self.assertEqual(
                registry.REGISTRY.get_projector(defect_type)._analyze, entry)


class FailClosedTests(unittest.TestCase):
    """M2 + M3: duplicate / unknown defect_type are rejected, never silent."""

    def test_duplicate_registration_is_rejected(self):
        r = registry.Registry()
        r.register_projector(registry.AdapterProjector("d1", "1", fake_analyze))
        with self.assertRaises(registry.DuplicateDefectTypeError):
            r.register_projector(registry.AdapterProjector("d1", "1", fake_analyze))

    def test_duplicate_does_not_overwrite(self):
        r = registry.Registry()
        r.register_projector(registry.AdapterProjector("d1", "1", fake_analyze))
        with self.assertRaises(registry.DuplicateDefectTypeError):
            r.register_projector(registry.AdapterProjector("d1", "9", fake_analyze))
        self.assertEqual(r.get_projector("d1").projector_version, "1")

    def test_unknown_defect_type_is_rejected(self):
        with self.assertRaises(registry.UnknownDefectTypeError):
            registry.REGISTRY.get_projector("nonexistent")

    def test_fresh_registry_has_no_placeholders(self):
        r = registry.Registry()
        self.assertEqual(r.list_projector_capabilities(), [])
        with self.assertRaises(registry.UnknownDefectTypeError):
            r.get_projector("anything")


class CapabilityTests(unittest.TestCase):
    """M4: capability discovery has the required fields, sorted by defect_type."""

    def test_capability_fields_and_order(self):
        caps = registry.REGISTRY.list_projector_capabilities()
        self.assertEqual([set(c) for c in caps],
                         [{"defect_type", "projector_version"}] * 7)
        types = [c["defect_type"] for c in caps]
        self.assertEqual(types, sorted(types))

    def test_capability_stability_on_repeat(self):
        a = registry.REGISTRY.list_projector_capabilities()
        b = registry.REGISTRY.list_projector_capabilities()
        self.assertEqual(a, b)


class ForwardingConsistencyTests(unittest.TestCase):
    """M5 + M9: registry.analyze byte/Hash-equals direct adapter.analyze_*."""

    def _run_race(self, entry, candidate_fixture):
        cand = load(candidate_fixture)
        src = source_ok({"candidates": [cand]})
        with mock.patch.object(adapter, "query_defect",
                               side_effect=lambda *a, **k: copy.deepcopy(src)):
            if entry == "race_condition":
                direct = adapter.analyze_shared_access("repo", "graph.db")
            else:
                direct = adapter.analyze_double_free("repo", "graph.db")
            via = registry.REGISTRY.analyze(entry, "repo", "graph.db")
        return direct, via

    def test_race_forwarding_equals_direct(self):
        direct, via = self._run_race("race_condition", "race_candidate.json")
        self.assertEqual(serialize(direct), serialize(via))
        self.assertEqual(sha256(serialize(direct)), sha256(serialize(via)))

    def test_double_free_forwarding_equals_direct(self):
        direct, via = self._run_race("double_free", "double_free_candidate.json")
        self.assertEqual(serialize(direct), serialize(via))
        self.assertEqual(sha256(serialize(direct)), sha256(serialize(via)))

    def test_deterministic_repeat(self):
        cand = load("race_candidate.json")
        src = source_ok({"candidates": [cand]})
        with mock.patch.object(adapter, "query_defect",
                               side_effect=lambda *a, **k: copy.deepcopy(src)):
            a = registry.REGISTRY.analyze("race_condition", "repo", "graph.db")
            b = registry.REGISTRY.analyze("race_condition", "repo", "graph.db")
        self.assertEqual(serialize(a), serialize(b))
        self.assertEqual(sha256(serialize(a)), sha256(serialize(b)))


class VersionSemanticsTests(unittest.TestCase):
    """M6: projector_version / projection_version / IR run.projector_version."""

    def test_projector_version_is_the_mechanism_version(self):
        self.assertEqual(registry.PROJECTOR_MECHANISM_VERSION, "1")
        for cap in registry.REGISTRY.list_projector_capabilities():
            self.assertEqual(cap["projector_version"], "1")

    def test_projector_version_distinct_from_projection_version(self):
        p = registry.REGISTRY.get_projector("race_condition")
        self.assertEqual(p.projector_version, "1")
        self.assertNotEqual(p.projector_version, "factbundle-projection-v2.1")

    def test_ir_run_projector_version_frozen_not_applicable(self):
        # IR V1 is frozen: run.projector_version stays NOT_APPLICABLE and is
        # not overwritten by the registry.
        bundle = load("race_factbundle_v2_1.json")
        evidence = ir.factbundle_v2_1_to_ir(bundle)
        self.assertEqual(evidence["run"]["projector_version"], "NOT_APPLICABLE")
        self.assertEqual(ir.PROJECTOR_VERSION, "NOT_APPLICABLE")

    def test_registry_does_not_touch_projection_version(self):
        cand = load("race_candidate.json")
        with mock.patch.object(adapter, "query_defect",
                               return_value=source_ok({"candidates": [cand]})):
            via = registry.REGISTRY.analyze("race_condition", "repo", "graph.db")
        self.assertEqual(via["projection_version"], "factbundle-projection-v2.1")


class ReadOnlyMetadataTests(unittest.TestCase):
    """Metadata is frozen; analyze forwards args verbatim and returns as-is."""

    def test_metadata_is_read_only(self):
        p = registry.AdapterProjector("d1", "1", fake_analyze)
        with self.assertRaises(AttributeError):
            p.defect_type = "other"
        with self.assertRaises(AttributeError):
            p.projector_version = "2"

    def test_analyze_forwards_verbatim_and_returns_as_is(self):
        captured = {}

        def fake(case_workdir, database, target_symbols=(), **kwargs):
            captured.update(case_workdir=case_workdir, database=database,
                            target_symbols=target_symbols, kwargs=kwargs)
            return {"ok": True}

        p = registry.AdapterProjector("d1", "1", fake)
        result = p.analyze("wd", "db", ("a", "b"), extra=1)
        self.assertEqual(captured["target_symbols"], ("a", "b"))  # not truncated
        self.assertEqual(captured["kwargs"], {"extra": 1})          # not rewritten
        self.assertEqual(result, {"ok": True})                      # returned as-is

    def test_register_deep_copies(self):
        r = registry.Registry()
        p = registry.AdapterProjector("d1", "1", fake_analyze)
        r.register_projector(p)
        self.assertIsNot(r.get_projector("d1"), p)
        self.assertEqual(r.get_projector("d1").defect_type, "d1")


class ExtensibilityTests(unittest.TestCase):
    """M7 + M8 + M10: third projector on an independent Registry(), isolated."""

    def test_register_third_projector_without_touching_registry_body(self):
        # no registry.py source change: just call register_projector
        r = registry.Registry()
        r.register_projector(registry.AdapterProjector("test_only", "1", fake_analyze))
        caps = r.list_projector_capabilities()
        self.assertEqual(caps, [{"defect_type": "test_only",
                                 "projector_version": "1"}])

    def test_production_registry_not_polluted(self):
        types = [c["defect_type"]
                 for c in registry.REGISTRY.list_projector_capabilities()]
        self.assertNotIn("test_only", types)
        self.assertEqual(types, ["double_free", "lock_order", "mismatched_free",
                                 "null_flow", "race_condition",
                                 "resource_lifetime", "use_after_free"])

    def test_test_only_not_in_production_schema_enum(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        enum = schema["properties"]["defect_type"]["enum"]
        self.assertNotIn("test_only", enum)
        self.assertEqual(set(enum), {
            "race_condition", "double_free", "lock_order",
            "resource_lifetime", "use_after_free", "null_flow",
            "mismatched_free",
        })

    def test_scope_controlled(self):
        # The production REGISTRY exposes the seven production defect types;
        # a separate Registry() is fully independent.
        independent = registry.Registry()
        independent.register_projector(
            registry.AdapterProjector("test_only", "1", fake_analyze))
        self.assertEqual(len(registry.REGISTRY.list_projector_capabilities()), 7)
        self.assertEqual(len(independent.list_projector_capabilities()), 1)


if __name__ == "__main__":
    unittest.main()
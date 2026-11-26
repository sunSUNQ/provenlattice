"""Generic fact projection for the five new defect types.

These tests use the same qualification fixtures as ``test_final_qualification``
so the positive/negative semantics are known, and assert the projector's
candidate/evidence binding rather than the detector's precision.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from provenlattice.evidence_projection import adapter, ir, projection, registry
from provenlattice.evidence_projection import skill_api
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


FIXTURES = {
    "lock_order": {
        "entry": adapter.C.ENTRY_LOCK_ORDER,
        "positive": """#include <pthread.h>
pthread_mutex_t lock_a, lock_b;
void *thread1(void *arg) {
    pthread_mutex_lock(&lock_a);
    pthread_mutex_lock(&lock_b);
    pthread_mutex_unlock(&lock_b);
    pthread_mutex_unlock(&lock_a);
    return 0;
}
void *thread2(void *arg) {
    pthread_mutex_lock(&lock_b);
    pthread_mutex_lock(&lock_a);
    pthread_mutex_unlock(&lock_a);
    pthread_mutex_unlock(&lock_b);
    return 0;
}
int main(void) {
    pthread_t t1, t2;
    pthread_create(&t1, 0, thread1, 0);
    pthread_create(&t2, 0, thread2, 0);
    pthread_join(t1, 0);
    pthread_join(t2, 0);
    return 0;
}
""",
        "negative": """#include <pthread.h>
pthread_mutex_t lock_a, lock_b;
void *safe1(void *arg) {
    pthread_mutex_lock(&lock_a);
    pthread_mutex_lock(&lock_b);
    pthread_mutex_unlock(&lock_b);
    pthread_mutex_unlock(&lock_a);
    return 0;
}
void *safe2(void *arg) {
    pthread_mutex_lock(&lock_a);
    pthread_mutex_lock(&lock_b);
    pthread_mutex_unlock(&lock_b);
    pthread_mutex_unlock(&lock_a);
    return 0;
}
int main(void) {
    pthread_t t1, t2;
    pthread_create(&t1, 0, safe1, 0);
    pthread_create(&t2, 0, safe2, 0);
    pthread_join(t1, 0);
    pthread_join(t2, 0);
    return 0;
}
""",
        "fact_types": {"LOCK"},
    },
    "resource_lifetime": {
        "entry": adapter.C.ENTRY_RESOURCE_LIFETIME,
        "positive": """#include <stdlib.h>
int leak_pos(int n) {
    char *p = malloc(64);
    if (!p) return -1;
    if (n > 0) { return n; }
    free(p);
    return 0;
}
""",
        "negative": """#include <stdlib.h>
int leak_neg(int n) {
    char *p = malloc(64);
    if (!p) return -1;
    free(p);
    return n;
}
""",
        "fact_types": {"ALLOC", "RELEASE"},
    },
    "use_after_free": {
        "entry": adapter.C.ENTRY_USE_AFTER_FREE,
        "positive": """#include <stdlib.h>
int uaf_pos(int n) {
    int *p = malloc(sizeof(int));
    if (!p) return -1;
    free(p);
    return *p;
}
""",
        "negative": """#include <stdlib.h>
int uaf_neg(int n) {
    int *p = malloc(sizeof(int));
    if (!p) return -1;
    *p = n;
    free(p);
    p = malloc(sizeof(int));
    if (!p) return -1;
    *p = n + 1;
    free(p);
    return n;
}
""",
        "fact_types": {"RELEASE", "DEREFERENCE"},
    },
    "null_flow": {
        "entry": adapter.C.ENTRY_NULL_FLOW,
        "positive": """#include <stdlib.h>
int null_pos(int n) {
    int *p = NULL;
    if (n) { *p = n; }
    return 0;
}
""",
        "negative": """#include <stdlib.h>
int null_neg(int n) {
    char *p = malloc(64);
    if (!p) return -1;
    *p = 1;
    free(p);
    return n;
}
""",
        "fact_types": {"WRITE", "DEREFERENCE"},
    },
    "mismatched_free": {
        "entry": adapter.C.ENTRY_MISMATCHED_FREE,
        "positive": """#include <stdlib.h>
int mf_pos(int n) {
    int *p = g_malloc(sizeof(int));
    if (!p) return -1;
    free(p);
    return n;
}
""",
        "negative": """#include <stdlib.h>
int mf_neg(int n) {
    int *p = malloc(sizeof(int));
    if (!p) return -1;
    free(p);
    return n;
}
""",
        "fact_types": {"ALLOC", "RELEASE"},
    },
}


class GenericProjectionBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.database = Path(self.temp.name) / "graph.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self, source: str) -> None:
        (self.root / "src").mkdir(parents=True, exist_ok=True)
        (self.root / "src" / "t.c").write_text(source, encoding="utf-8")
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("defect",), database=self.database)

    def analyze(self, defect_type: str) -> dict:
        entry = FIXTURES[defect_type]["entry"]
        return getattr(adapter, entry)(self.root, self.database)


class GenericProjectionTests(GenericProjectionBase):
    def test_positive_bundle_binds_and_validates(self) -> None:
        for defect_type, spec in FIXTURES.items():
            with self.subTest(defect_type=defect_type):
                self.build(spec["positive"])
                bundle = self.analyze(defect_type)
                self.assertEqual(bundle["status"], "ok", bundle.get("reason"))
                self.assertIn("candidate_facts", bundle["facts"])
                self.assertEqual(
                    adapter.validate_bundle_v2(spec["entry"], bundle), [])
                coverage = bundle["location_coverage"]
                self.assertGreaterEqual(coverage["candidates"], 1)
                self.assertEqual(coverage["unlocated_candidates"], [])
                self.assertGreaterEqual(coverage["located_facts"], 1)
                self.assertEqual(
                    coverage["located_facts"], coverage["total_facts"])
                self.assertGreaterEqual(
                    coverage["located_supporting_locations"], 1)
                for entry in bundle["facts"]["candidate_facts"]["value"]:
                    self.assertTrue(entry["candidate_key"])
                    self.assertTrue(entry["evidence_id"])
                    self.assertTrue(entry["facts"])
                    fact_types = {fact["fact_type"] for fact in entry["facts"]}
                    self.assertTrue(
                        fact_types & spec["fact_types"],
                        (defect_type, fact_types),
                    )
                    for fact in entry["facts"]:
                        self.assertTrue(fact["file"])
                        self.assertGreater(fact["line"], 0)
                        self.assertTrue(fact["event_id"])
                        self.assertTrue(fact["source_fact_id"])

    def test_positive_ir_v1_is_valid(self) -> None:
        for defect_type, spec in FIXTURES.items():
            with self.subTest(defect_type=defect_type):
                self.build(spec["positive"])
                bundle = self.analyze(defect_type)
                evidence = ir.factbundle_v2_1_to_ir(
                    bundle,
                    run_context={"engine_version": "1.7.0",
                                 "code_revision": "test",
                                 "db_snapshot_identity": "test"},
                )
                self.assertEqual(ir.validate_evidence_ir_v1(evidence), [])
                self.assertGreaterEqual(len(evidence["facts"]), 1)
                self.assertGreaterEqual(len(evidence["locations"]), 1)
                self.assertEqual(evidence["claims"], [])
                self.assertEqual(evidence["relations"], [])

    def test_negative_fixture_projects_nothing(self) -> None:
        for defect_type, spec in FIXTURES.items():
            with self.subTest(defect_type=defect_type):
                self.build(spec["negative"])
                bundle = self.analyze(defect_type)
                self.assertEqual(bundle["status"], "empty")
                self.assertEqual(
                    bundle["facts"]["candidate_facts"]["value"], [])
                self.assertEqual(bundle["supporting_locations"], [])
                self.assertEqual(
                    bundle["location_coverage"]["candidates"], 0)
                self.assertEqual(
                    adapter.validate_bundle_v2(spec["entry"], bundle), [])

    def test_registry_has_seven_projectors(self) -> None:
        caps = registry.REGISTRY.list_projector_capabilities()
        self.assertEqual(len(caps), 7)
        self.assertEqual(
            {cap["defect_type"] for cap in caps},
            {"race_condition", "double_free", "lock_order",
             "resource_lifetime", "use_after_free", "null_flow",
             "mismatched_free"},
        )

    def test_manifest_lists_generic_projectors(self) -> None:
        manifest = skill_api.list_skill_capabilities()
        for defect_type in FIXTURES:
            self.assertIn(defect_type, manifest["defect_types"])
            self.assertTrue(
                manifest["defect_types"][defect_type]["projected_facts"])

    def test_resolve_evidence_ir_v1_for_each_generic_type(self) -> None:
        for defect_type, spec in FIXTURES.items():
            with self.subTest(defect_type=defect_type):
                self.build(spec["positive"])
                evidence = skill_api.resolve_evidence(
                    self.root, self.database,
                    defect_type=defect_type, ir_version="1")
                self.assertEqual(ir.validate_evidence_ir_v1(evidence), [])
                self.assertGreaterEqual(len(evidence["facts"]), 1)


class UseAfterFreeBindingTests(GenericProjectionBase):
    def test_shared_release_is_allowed_for_uaf(self) -> None:
        self.build(FIXTURES["use_after_free"]["positive"])
        bundle = self.analyze("use_after_free")
        self.assertEqual(adapter.validate_bundle_v2(
            adapter.C.ENTRY_USE_AFTER_FREE, bundle), [])
        # Two UAF candidates legitimately cite the same RELEASE fact.
        release_owners = {}
        for pc in bundle["evidence_locations"]:
            for fact in pc["access_rows"]:
                if fact["access_type"] == "RELEASE":
                    release_owners.setdefault(
                        fact["source_fact_id"], set()).add(
                            pc["candidate_key"])
        self.assertTrue(any(len(owners) > 1
                            for owners in release_owners.values()))

    def test_strict_binding_still_rejects_shared_release(self) -> None:
        self.build(FIXTURES["use_after_free"]["positive"])
        bundle = self.analyze("use_after_free")
        problems = projection.assert_candidate_binding(
            bundle, allow_shared_release=False)
        self.assertTrue(any("RELEASE fact" in p for p in problems), problems)


class GenericFactsAreAdditiveTests(unittest.TestCase):
    def test_existing_entries_keep_their_fact_blocks(self) -> None:
        # The generic block must never replace the frozen race/double-free
        # blocks. This is a structural check on the adapter's block chooser.
        self.assertEqual(
            adapter._facts_block(adapter.C.ENTRY_SHARED_ACCESS, []) ,
            {"shared_accesses": {"value": []}},
        )
        self.assertEqual(
            adapter._facts_block(adapter.C.ENTRY_DOUBLE_FREE, []),
            {"release_sites": {"value": []}},
        )
        self.assertEqual(
            adapter._facts_block(adapter.C.ENTRY_LOCK_ORDER, []),
            {"candidate_facts": {"value": []}},
        )


class SharedReleasePolicyTests(unittest.TestCase):
    """Generic lifetime defects may share a RELEASE fact; double_free may not."""

    @staticmethod
    def _candidate(evidence_id: str) -> dict:
        return {
            "defect_key": "4.1",
            "query": "resource_lifetime",
            "subject": {"name": "p", "identity": "symbol:abc#local:p",
                        "owner_symbol_id": "symbol:abc"},
            "anchor": "event:e1",
            "discriminator": evidence_id,
            "resolution_status": "resolved",
            "confidence": 0.6,
            "facts": [
                {"event": "ALLOC", "point": "event:e1",
                 "source": "src/t.c:1-1", "method": "f"},
                {"event": "RELEASE", "point": "event:e2",
                 "source": "src/t.c:2-2", "method": "f"},
            ],
            "metadata": {"anchor_span": {
                "relative_path": "src/t.c", "start_line": 1, "end_line": 1}},
            "evidence_id": evidence_id,
        }

    def test_resource_lifetime_shared_release_is_allowed(self) -> None:
        source = {
            "status": "ok",
            "result": {"candidates": [self._candidate("E-DEFECT-a"),
                                      self._candidate("E-DEFECT-b")]},
            "error": None,
            "reason": None,
        }
        with mock.patch.object(adapter, "query_defect", return_value=source):
            bundle = adapter.analyze_resource_lifetime("repo", "db")
        self.assertEqual(adapter.validate_bundle_v2(
            adapter.C.ENTRY_RESOURCE_LIFETIME, bundle), [])


class GenericRegistryForwardingTests(unittest.TestCase):
    """Registry.analyze forwards byte-identically to each direct entry."""

    @staticmethod
    def _candidate(defect_type: str) -> dict:
        return {
            "defect_key": "x",
            "query": defect_type,
            "subject": {
                "name": "p",
                "identity": "symbol:abc#local:p",
                "owner_symbol_id": "symbol:abc",
            },
            "anchor": "event:e1",
            "discriminator": "d",
            "resolution_status": "resolved",
            "confidence": 0.6,
            "facts": [
                {"event": "ALLOC", "point": "event:e1",
                 "source": "src/t.c:1-1", "method": "f"},
                {"event": "RELEASE", "point": "event:e2",
                 "source": "src/t.c:2-2", "method": "f"},
            ],
            "metadata": {"anchor_span": {
                "relative_path": "src/t.c", "start_line": 1, "end_line": 1}},
            "evidence_id": "E-DEFECT-x",
        }

    def test_generic_entry_forwards_query_knobs(self) -> None:
        source = {
            "status": "ok",
            "result": {"candidates": [self._candidate("resource_lifetime")]},
            "error": None,
            "reason": None,
        }
        with mock.patch.object(adapter, "query_defect",
                               return_value=source) as query:
            adapter.analyze_resource_lifetime(
                "repo", "db", max_candidates=50, max_paths=16)
        self.assertEqual(query.call_args.kwargs["max_candidates"], 50)
        self.assertEqual(query.call_args.kwargs["max_paths"], 16)
        self.assertEqual(query.call_args.kwargs["defect_type"],
                         "resource_lifetime")
        self.assertEqual(query.call_args.kwargs["database"], "db")

    def test_generic_event_types_are_allowed(self) -> None:
        candidate = self._candidate("resource_lifetime")
        candidate["facts"].extend([
            {"event": "THROW", "point": "event:e3",
             "source": "src/t.c:3-3", "method": "f"},
            {"event": "THREAD_JOIN", "point": "event:e4",
             "source": "src/t.c:4-4", "method": "f"},
        ])
        source = {"status": "ok", "result": {"candidates": [candidate]},
                  "error": None, "reason": None}
        with mock.patch.object(adapter, "query_defect", return_value=source):
            bundle = adapter.analyze_resource_lifetime("repo", "db")
        self.assertEqual(adapter.validate_bundle_v2(
            adapter.C.ENTRY_RESOURCE_LIFETIME, bundle), [])
        types = {fact["fact_type"]
                 for entry in bundle["facts"]["candidate_facts"]["value"]
                 for fact in entry["facts"]}
        self.assertIn("THROW", types)
        self.assertIn("THREAD_JOIN", types)

    def test_forwarding_and_determinism(self) -> None:
        for defect_type, spec in FIXTURES.items():
            with self.subTest(defect_type=defect_type):
                source = {
                    "status": "ok",
                    "result": {"candidates": [self._candidate(defect_type)]},
                    "error": None,
                    "reason": None,
                }
                with mock.patch.object(adapter, "query_defect",
                                       return_value=source):
                    direct = getattr(adapter, spec["entry"])("repo", "db")
                    via = registry.REGISTRY.analyze(
                        defect_type, "repo", "db")
                    via_again = registry.REGISTRY.analyze(
                        defect_type, "repo", "db")
                direct_text = json.dumps(direct, sort_keys=True,
                                         ensure_ascii=False)
                via_text = json.dumps(via, sort_keys=True, ensure_ascii=False)
                again_text = json.dumps(via_again, sort_keys=True,
                                        ensure_ascii=False)
                self.assertEqual(direct_text, via_text)
                self.assertEqual(via_text, again_text)
                self.assertEqual(
                    adapter.validate_bundle_v2(spec["entry"], via), [])


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the L3 deterministic capability planner (GRAPH_CAPABILITY_PLANNER_V1).

Covers the minimal contract from issue-pilot #23 and
docs/concurrency-profile-capability-planner-requirements-v1.md section 6:
recursive dependency expansion, (capability, language, scope) deduplication,
language/maturity/optional-runtime checks, build/reuse/query_only/skip
decisions, partial/stale/unsupported/not_built status expression, budget
exhaustion and byte-stable deterministic output (plan id + ordering).
"""

import unittest

from provenlattice.analysis import ANALYZER_VERSIONS, CAPABILITY_CONTRACT
from provenlattice.planner import (
    DECISION_BUILD,
    DECISION_QUERY_ONLY,
    DECISION_REUSE,
    DECISION_SKIP,
    STATUS_NOT_BUILT,
    STATUS_PARTIAL,
    STATUS_STALE,
    STATUS_UNSUPPORTED,
    PlannerRequest,
    plan_capabilities,
)


def freshness_from(mapping):
    def provider(analyzer_id):
        return mapping.get(analyzer_id, {"fresh": False, "reason": None})

    return provider


class RecursiveExpansionTests(unittest.TestCase):
    def test_defect_expands_full_dependency_chain(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("defect",), language="cpp"))
        self.assertEqual(
            [item.capability_id for item in plan.items],
            ["events", "sparse_cfg", "sparse_dfg", "defect"],
        )

    def test_dependencies_are_deduplicated_across_requests(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("sparse_dfg", "sparse_cfg"), language="cpp"))
        self.assertEqual(
            [item.capability_id for item in plan.items],
            ["events", "sparse_cfg", "sparse_dfg"],
        )

    def test_duplicate_requested_capabilities_are_coalesced(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("defect", "defect", "sparse_dfg"), language="cpp"))
        self.assertEqual(
            [item.capability_id for item in plan.items],
            ["events", "sparse_cfg", "sparse_dfg", "defect"],
        )


class LanguageMaturityRuntimeTests(unittest.TestCase):
    def test_unsupported_language_fails_closed(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("events",), language="java"))
        item = plan.items[0]
        self.assertEqual(item.status, STATUS_UNSUPPORTED)
        self.assertEqual(item.decision, DECISION_SKIP)
        self.assertEqual(item.reason, "unsupported_language")

    def test_partial_capability_reports_partial_status(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("events",), language="cpp"))
        item = plan.items[0]
        self.assertEqual(item.status, STATUS_PARTIAL)
        self.assertEqual(item.decision, DECISION_BUILD)
        self.assertEqual(item.maturity, "partially_implemented")

    def test_minimum_maturity_gate_skips_partial(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("events",), language="cpp",
                           minimum_maturity="implemented"))
        item = plan.items[0]
        self.assertEqual(item.decision, DECISION_SKIP)
        self.assertEqual(item.reason, "below_minimum_maturity")

    def test_defect_is_query_only(self):
        plan = plan_capabilities(PlannerRequest(capabilities=("defect",), language="cpp"))
        defect = plan.items[-1]
        self.assertEqual(defect.decision, DECISION_QUERY_ONLY)
        self.assertEqual(defect.reason, None)
        self.assertEqual(defect.analyzer_ids, ())

    def test_optional_runtime_unavailable_fails_closed(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("semantic_java",), language="java"))
        item = plan.items[0]
        self.assertEqual(item.decision, DECISION_SKIP)
        self.assertEqual(item.status, STATUS_UNSUPPORTED)
        self.assertEqual(item.reason, "optional_runtime_unavailable:jdk+jdt")

    def test_optional_runtime_available_enables_query_only(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("semantic_java",), language="java",
                           available_runtimes=("jdk+jdt",)))
        item = plan.items[0]
        self.assertEqual(item.decision, DECISION_QUERY_ONLY)
        self.assertEqual(item.status, "current")


class UnimplementedCapabilityTests(unittest.TestCase):
    def test_unregistered_capability_fails_closed(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("bogus",), language="cpp"))
        item = plan.items[0]
        self.assertEqual(item.status, STATUS_UNSUPPORTED)
        self.assertEqual(item.decision, DECISION_SKIP)
        self.assertEqual(item.reason, "capability_unregistered")
        self.assertEqual(item.cost_class, "unknown")

    def test_registered_but_unimplemented_reports_not_built(self):
        CAPABILITY_CONTRACT["future_capability"] = {
            "status": "registered", "languages": ("cpp",), "depends_on": (),
            "cost_class": "low", "analyzer_ids": (), "planned_integration": None,
        }
        self.addCleanup(CAPABILITY_CONTRACT.pop, "future_capability")
        plan = plan_capabilities(
            PlannerRequest(capabilities=("future_capability",), language="cpp"))
        item = plan.items[0]
        self.assertEqual(item.status, STATUS_NOT_BUILT)
        self.assertEqual(item.decision, DECISION_SKIP)
        self.assertEqual(item.reason, "registered_not_implemented")


class FreshnessDecisionTests(unittest.TestCase):
    def test_fresh_analyzers_reuse(self):
        provider = freshness_from({
            "events:cpp": {"fresh": True},
            "sparse_cfg:cpp": {"fresh": True},
            "sparse_dfg:cpp": {"fresh": True},
        })
        plan = plan_capabilities(
            PlannerRequest(capabilities=("sparse_dfg",), language="cpp"),
            freshness=provider)
        self.assertEqual(plan.items[1].decision, DECISION_REUSE)
        self.assertEqual(plan.items[1].status, "current")
        self.assertEqual(plan.items[0].decision, DECISION_REUSE)
        self.assertEqual(plan.items[0].status, STATUS_PARTIAL)

    def test_stale_analyzer_builds_with_stale_status(self):
        provider = freshness_from({
            "events:cpp": {"fresh": False, "reason": None},
            "sparse_cfg:cpp": {"fresh": False, "reason": "source_hash_changed"},
            "sparse_dfg:cpp": {"fresh": False, "reason": None},
        })
        plan = plan_capabilities(
            PlannerRequest(capabilities=("sparse_dfg",), language="cpp"),
            freshness=provider)
        cfg = next(i for i in plan.items if i.capability_id == "sparse_cfg")
        self.assertEqual(cfg.decision, DECISION_BUILD)
        self.assertEqual(cfg.status, STATUS_STALE)
        self.assertEqual(cfg.reason, "source_hash_changed")

    def test_first_build_reports_not_built_reason(self):
        provider = freshness_from({
            "events:cpp": {"fresh": False, "reason": "not_built"},
        })
        plan = plan_capabilities(
            PlannerRequest(capabilities=("events",), language="cpp"),
            freshness=provider)
        self.assertEqual(plan.items[0].decision, DECISION_BUILD)
        self.assertEqual(plan.items[0].reason, "not_built")


class BudgetTests(unittest.TestCase):
    def test_budget_exhaustion_skips_remaining_builds(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("sparse_dfg",), language="cpp",
                           budgets={"high": 2}))
        decisions = {item.capability_id: item.decision for item in plan.items}
        self.assertEqual(decisions["events"], DECISION_BUILD)
        self.assertEqual(decisions["sparse_cfg"], DECISION_BUILD)
        self.assertEqual(decisions["sparse_dfg"], DECISION_SKIP)
        dfg = next(i for i in plan.items if i.capability_id == "sparse_dfg")
        self.assertEqual(dfg.reason, "budget_exhausted:high")


class DeterminismTests(unittest.TestCase):
    def test_same_request_yields_identical_plan(self):
        request = PlannerRequest(capabilities=("defect",), language="cpp",
                                 scenario_ids=("concurrency.non_atomic_incdec",))
        first = plan_capabilities(request)
        second = plan_capabilities(request)
        self.assertEqual(first.plan_id, second.plan_id)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_different_language_yields_different_plan_id(self):
        a = plan_capabilities(PlannerRequest(capabilities=("defect",), language="cpp"))
        b = plan_capabilities(PlannerRequest(capabilities=("defect",), language="java"))
        self.assertNotEqual(a.plan_id, b.plan_id)

    def test_plan_id_is_auditable_hex_digest(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("defect",), language="cpp"))
        self.assertTrue(plan.plan_id.startswith("plan-"))
        self.assertEqual(len(plan.plan_id), len("plan-") + 32)

    def test_optimizable_requests_zero_changes_to_iteration_order(self):
        # Ordering is topological + lexicographic and stable regardless of the
        # order names are requested in.
        a = plan_capabilities(
            PlannerRequest(capabilities=("sparse_dfg", "defect"), language="cpp"))
        b = plan_capabilities(
            PlannerRequest(capabilities=("defect", "sparse_dfg"), language="cpp"))
        self.assertEqual(
            [item.capability_id for item in a.items],
            [item.capability_id for item in b.items],
        )


class DependencyFailClosedTests(unittest.TestCase):
    def test_dependent_skipped_when_dependency_unsupported(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("sparse_cfg",), language="java"))
        items = {item.capability_id: item for item in plan.items}
        self.assertEqual(items["events"].decision, DECISION_SKIP)
        self.assertEqual(items["events"].reason, "unsupported_language")
        self.assertEqual(items["events"].status, STATUS_UNSUPPORTED)
        cfg = items["sparse_cfg"]
        self.assertEqual(cfg.decision, DECISION_SKIP)
        self.assertEqual(cfg.status, STATUS_UNSUPPORTED)
        self.assertEqual(cfg.reason, "dependency_unsupported:events")

    def test_query_time_dependent_skipped_when_dependency_unavailable(self):
        CAPABILITY_CONTRACT["query_parent"] = {
            "status": "implemented", "languages": ("cpp",),
            "depends_on": ("missing_dep",), "cost_class": "high",
            "analyzer_ids": (), "query_time": True,
        }
        self.addCleanup(CAPABILITY_CONTRACT.pop, "query_parent", None)
        plan = plan_capabilities(
            PlannerRequest(capabilities=("query_parent",), language="cpp"))
        items = {item.capability_id: item for item in plan.items}
        self.assertEqual(items["missing_dep"].status, STATUS_UNSUPPORTED)
        parent = items["query_parent"]
        self.assertEqual(parent.decision, DECISION_SKIP)
        self.assertEqual(parent.status, STATUS_UNSUPPORTED)
        self.assertEqual(parent.reason, "dependency_unsupported:missing_dep")

    def test_healthy_dependency_chain_remains_plannable(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("sparse_dfg",), language="cpp"))
        decisions = [item.decision for item in plan.items]
        self.assertNotIn(DECISION_SKIP, decisions)
        self.assertEqual(decisions[-1], DECISION_BUILD)


class PlanIdentityTests(unittest.TestCase):
    def test_query_time_change_alters_plan_id(self):
        def plan_with(query_time):
            CAPABILITY_CONTRACT["demo_q"] = {
                "status": "implemented", "languages": ("cpp",),
                "depends_on": (), "cost_class": "low",
                "analyzer_ids": ("cfg:cpp",), "query_time": query_time,
            }
            self.addCleanup(CAPABILITY_CONTRACT.pop, "demo_q", None)
            return plan_capabilities(
                PlannerRequest(capabilities=("demo_q",), language="cpp"))

        self.assertNotEqual(plan_with(False).plan_id, plan_with(True).plan_id)

    def test_optional_runtime_change_alters_plan_id(self):
        def plan_with(optional_runtime):
            CAPABILITY_CONTRACT["demo_r"] = {
                "status": "implemented", "languages": ("java",),
                "depends_on": (), "cost_class": "low",
                "analyzer_ids": ("cfg:java",), "optional_runtime": optional_runtime,
            }
            self.addCleanup(CAPABILITY_CONTRACT.pop, "demo_r", None)
            return plan_capabilities(
                PlannerRequest(capabilities=("demo_r",), language="java",
                               available_runtimes=("jdk+jdt",)))

        self.assertNotEqual(plan_with(None).plan_id, plan_with("jdk+jdt").plan_id)

    def test_analyzer_version_change_alters_plan_id(self):
        analyzer = "sparse_cfg:java"
        original = ANALYZER_VERSIONS[analyzer]
        self.addCleanup(ANALYZER_VERSIONS.__setitem__, analyzer, original)
        before = plan_capabilities(
            PlannerRequest(capabilities=("sparse_cfg",), language="java"))
        ANALYZER_VERSIONS[analyzer] = original + 1
        after = plan_capabilities(
            PlannerRequest(capabilities=("sparse_cfg",), language="java"))
        self.assertNotEqual(before.plan_id, after.plan_id)


class CrossLanguageAnalyzerTests(unittest.TestCase):
    def test_unsupported_language_item_has_no_foreign_analyzers(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("events",), language="java"))
        item = plan.items[0]
        self.assertEqual(item.decision, DECISION_SKIP)
        self.assertEqual(item.reason, "unsupported_language")
        self.assertEqual(item.analyzer_ids, ())

    def test_unregistered_capability_has_no_analyzers(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("bogus",), language="cpp"))
        self.assertEqual(plan.items[0].analyzer_ids, ())


class ItemShapeTests(unittest.TestCase):
    def test_every_plan_item_carries_required_fields(self):
        plan = plan_capabilities(
            PlannerRequest(capabilities=("defect",), language="cpp",
                           scope="src", scenario_ids=("concurrency.shared_state_race",)))
        required = {
            "capability_id", "language", "scope", "scenario_ids", "analyzer_ids",
            "maturity", "dependencies", "decision", "reason", "status", "cost_class",
        }
        for item in plan.items:
            self.assertTrue(required <= set(item.to_dict()), item.to_dict())
        self.assertEqual(plan.items[0].scope, "src")
        self.assertEqual(plan.items[0].scenario_ids, ("concurrency.shared_state_race",))


if __name__ == "__main__":
    unittest.main()
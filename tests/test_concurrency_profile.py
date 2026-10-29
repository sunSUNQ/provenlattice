"""S6 concurrency Profile Registry and L5 integration tests (Parent #28).

Freezes the concurrency-v1 Profile declaration, the single Planner-plan-to-scenario
execution adapter, the Candidate-to-L4-Evidence conversion, the per-scenario
five-state propagation (current/partial/unsupported/stale/not_built) and the
evidence source-file provenance. The default CLI/MCP behavior must stay unchanged.
"""

import tempfile
import unittest
from pathlib import Path

from provenlattice.concurrency_profile import (
    CONCURRENCY_PROFILE_ID,
    CONCURRENCY_V1,
    PROFILES,
    _merge_scenario_state,
    get_profile,
    run_concurrency_profile,
)
from provenlattice.graph import full_index


def write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


class ProfileRegistryTests(unittest.TestCase):
    def test_concurrency_v1_declares_frozen_fields(self):
        profile = get_profile(CONCURRENCY_PROFILE_ID)
        self.assertIsNotNone(profile)
        for field in ("profile_id", "profile_version", "query_set_version",
                      "scenario_ids", "requested_scope", "language_policy",
                      "minimum_maturity", "budgets", "required_capabilities",
                      "optional_capabilities", "evidence_policy"):
            self.assertIn(field, profile)

    def test_profile_declares_all_five_scenarios(self):
        self.assertEqual(
            CONCURRENCY_V1["scenario_ids"],
            ("non_atomic_incdec", "bool_flag_race", "shared_state_race",
             "lock_pairing", "lock_discipline"),
        )

    def test_unknown_profile_is_none(self):
        self.assertIsNone(get_profile("does-not-exist"))
        self.assertEqual(set(PROFILES), {CONCURRENCY_PROFILE_ID})


class RaceProfileTests(unittest.TestCase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "int g_count;\n"
        "_Bool g_flag;\n"
        "void *worker(void *a) { g_count++; return 0; }\n"
        "void updater(void) { g_count += 1; }\n"
        "void set(void) { g_flag = 1; }\n"
        "void get(void) { int x = g_flag; (void)x; }\n"
    )

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        write(self.root, "src/a.c", self.FIXTURE)
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def result(self) -> dict:
        return run_concurrency_profile(self.root, database=self.database, scope="src")

    def test_returns_profile_and_version(self):
        result = self.result()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["profile"]["profile_id"], "concurrency-v1")
        self.assertEqual(result["profile"]["profile_version"], "1")
        self.assertIn("plan", result)

    def test_race_scenarios_are_current(self):
        scenarios = self.result()["scenarios"]
        self.assertEqual(scenarios["non_atomic_incdec"]["status"], "current")
        self.assertEqual(scenarios["bool_flag_race"]["status"], "current")
        self.assertEqual(scenarios["shared_state_race"]["status"], "current")
        self.assertEqual(scenarios["non_atomic_incdec"]["candidate_count"], 1)

    def test_lock_scenarios_are_partial_not_built(self):
        # lock scenarios consume the `events` capability, which carries
        # level-0 vocabulary events only and is frozen partially_implemented;
        # the scenario must reflect that, never fold it silently to not_built.
        scenarios = self.result()["scenarios"]
        self.assertEqual(scenarios["lock_pairing"]["status"], "partial")
        self.assertEqual(scenarios["lock_discipline"]["status"], "partial")
        self.assertEqual(scenarios["lock_pairing"]["capability"], "events")

    def test_candidates_are_converted_to_l4_evidence(self):
        result = self.result()
        self.assertTrue(result["evidence"])
        for item in result["evidence"]:
            self.assertEqual(item["kind"], "DEFECT_CANDIDATE")
            self.assertIn("scenario_id", item["metadata"])
            self.assertIn("candidate_state", item["metadata"])

    def test_evidence_carries_source_file_path(self):
        items = [i for i in self.result()["evidence"] if i["source_path"]]
        self.assertTrue(items)
        for item in items:
            self.assertEqual(item["source_path"], "src/a.c")
            self.assertIn("src/a.c", item["metadata"]["related_files"])


class LockProfileTests(unittest.TestCase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t mtx;\n"
        "void unpaired(void) { pthread_mutex_lock(&mtx); }\n"
    )

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        write(self.root, "src/a.c", self.FIXTURE)
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_lock_pairing_is_partial_for_unpaired_acquire(self):
        scenario = run_concurrency_profile(
            self.root, database=self.database, scope="src")["scenarios"]["lock_pairing"]
        self.assertEqual(scenario["status"], "partial")
        self.assertGreaterEqual(scenario["candidate_count"], 1)
        # The candidate's evidence keeps the real source path.
        evidence = run_concurrency_profile(
            self.root, database=self.database, scope="src")["evidence"]
        pairing = [i for i in evidence if i["metadata"]["scenario_id"] == "lock_pairing"]
        self.assertTrue(pairing)
        self.assertEqual(pairing[0]["source_path"], "src/a.c")


class UnsupportedLanguageTests(unittest.TestCase):
    def test_python_scope_reports_unsupported(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name) / "repo"
        write(root, "src/a.py", "def f():\n    pass\n")
        database = Path(temp.name) / "graph.db"
        full_index(root, database)
        try:
            result = run_concurrency_profile(root, database=database, scope="src")
        finally:
            temp.cleanup()
        for scenario_id in ("non_atomic_incdec", "lock_pairing"):
            self.assertEqual(result["scenarios"][scenario_id]["status"], "unsupported")


class FiveStateMergeTests(unittest.TestCase):
    def test_capability_state_is_preserved(self):
        for status in ("current", "partial", "stale", "unsupported", "not_built"):
            merged, reason = _merge_scenario_state(status, {"available": ["a.c"]})
            self.assertEqual(merged, status)
            self.assertIsNone(reason)

    def test_file_unsupported_dominates_current_capability(self):
        merged, reason = _merge_scenario_state("current", {"unsupported": ["a.py"]})
        self.assertEqual(merged, "unsupported")
        self.assertEqual(reason, "file_state_dominates")

    def test_file_stale_dominates_partial_capability(self):
        merged, _ = _merge_scenario_state("partial", {"stale": ["a.c"]})
        self.assertEqual(merged, "stale")

    def test_most_severe_file_state_wins(self):
        merged, _ = _merge_scenario_state(
            "current", {"stale": ["a.c"], "not_built": ["b.c"], "unsupported": ["c.py"]})
        self.assertEqual(merged, "not_built")

    def test_available_files_do_not_change_state(self):
        merged, _ = _merge_scenario_state("current", {"available": ["a.c", "b.c"]})
        self.assertEqual(merged, "current")


class NotBuiltTests(unittest.TestCase):
    def test_unindexed_repo_reports_not_built(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name) / "repo"
        write(root, "src/a.c", "int g; void f(void) { g++; }\n")
        database = Path(temp.name) / "graph.db"
        try:
            result = run_concurrency_profile(root, database=database, scope="src")
        finally:
            temp.cleanup()
        self.assertEqual(result["status"], "not_built")


class UnknownProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        (self.root / "src").mkdir(parents=True)
        write(self.root, "src/a.c", "int g; void f(void) { g++; }\n")
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_unknown_profile_reports_unknown(self):
        result = run_concurrency_profile(
            self.root, "nope", database=self.database, scope="src")
        self.assertEqual(result["status"], "unknown_profile")


class CliCompatTests(unittest.TestCase):
    def test_existing_defect_command_unchanged(self):
        from provenlattice.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["defect", ".", "--type", "race_condition"])
        self.assertEqual(args.command, "defect")
        self.assertEqual(args.type, "race_condition")

    def test_concurrency_profile_entry_is_explicit(self):
        from provenlattice.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["concurrency-profile", ".", "--scope", "src"])
        self.assertEqual(args.command, "concurrency-profile")
        self.assertEqual(args.profile, "concurrency-v1")


if __name__ == "__main__":
    unittest.main()
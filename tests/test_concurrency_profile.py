"""S6 concurrency Profile Registry and L5 integration tests (Parent #28).

Freezes the concurrency-v1 Profile declaration, the single Planner-plan-to-scenario
execution adapter, the Candidate-to-L4-Evidence conversion, and the per-scenario
current/not_built states. The default CLI/MCP behavior must stay unchanged.
"""

import tempfile
import unittest
from pathlib import Path

from provenlattice.concurrency_profile import (
    CONCURRENCY_PROFILE_ID,
    CONCURRENCY_V1,
    PROFILES,
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

    def test_lock_scenarios_reported_not_built_without_locks(self):
        scenarios = self.result()["scenarios"]
        self.assertEqual(scenarios["lock_pairing"]["status"], "not_built")
        self.assertEqual(scenarios["lock_discipline"]["status"], "not_built")

    def test_candidates_are_converted_to_l4_evidence(self):
        result = self.result()
        self.assertTrue(result["evidence"])
        for item in result["evidence"]:
            self.assertEqual(item["kind"], "DEFECT_CANDIDATE")
            self.assertIn("scenario_id", item["metadata"])
            self.assertIn("candidate_state", item["metadata"])


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

    def test_lock_pairing_is_current_for_unpaired_acquire(self):
        scenarios = run_concurrency_profile(
            self.root, database=self.database, scope="src")["scenarios"]
        self.assertEqual(scenarios["lock_pairing"]["status"], "current")
        self.assertGreaterEqual(scenarios["lock_pairing"]["candidate_count"], 1)


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
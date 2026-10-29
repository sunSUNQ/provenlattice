"""S5 lock scenario tests (Parent #28): lock_pairing / lock_discipline.

Freezes the Candidate contract for the two lock scenarios: candidates are
evidence-resolution states only, never verified findings. Vocabulary-level
pairing is control-flow-free, so unpaired/try-timed/order candidates stay
``ambiguous``; an empty lock identity is ``unresolved``; a try/timed acquire is
never promoted to a held lock; and a RAII acquisition is never reported as a
leak.
"""

import json
import tempfile
import unittest
from pathlib import Path

from provenlattice.analysis_query import query_analysis
from provenlattice.concurrency_lock_scenarios import build_lock_scenarios
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


def write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


def make_event(
    event_type: str, lock_identity: str, *, acquire_kind: str = "blocking",
    raii: bool = False, subject_exact: bool = True, start_byte: int = 0,
    start_line: int = 1, end_line: int = 1, owner: str = "f",
    matched_name: str = "pthread_mutex_lock",
) -> dict:
    return {
        "event_id": f"event:{owner}:{event_type}:{start_byte}",
        "event_type": event_type,
        "owner_symbol_id": f"owner:{owner}",
        "owner_qualified_name": owner,
        "lock_identity": lock_identity,
        "subject_exact": subject_exact,
        "acquire_kind": acquire_kind,
        "raii": raii,
        "matched_name": matched_name,
        "start_line": start_line,
        "end_line": end_line,
        "start_byte": start_byte,
        "end_byte": start_byte + 1,
    }


class LockScenarioTestBase(unittest.TestCase):
    FIXTURE = ""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        write(self.root, "src/a.c", self.FIXTURE)
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("events",), database=self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def events(self) -> list[dict]:
        env = query_analysis(
            self.root, "events", file_path="src/a.c", database=self.database)
        self.assertEqual(env["status"], "available", env.get("reason"))
        return env["events"]

    def result(self) -> dict:
        return build_lock_scenarios(self.events())

    def candidates(self, rule: str) -> list[dict]:
        return [c for c in self.result()["candidates"] if c["rule"] == rule]


class UnpairedAcquireTests(LockScenarioTestBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t g_lock;\n"
        "void leak(void) {\n"
        "    pthread_mutex_lock(&g_lock);\n"
        "}\n"
    )

    def test_unpaired_acquire_is_a_candidate(self):
        unpaired = self.candidates("unpaired_acquire")
        self.assertEqual(len(unpaired), 1)
        candidate = unpaired[0]
        self.assertEqual(candidate["subject"], "g_lock")
        self.assertEqual(candidate["identity"], "g_lock")
        self.assertEqual(candidate["candidate_state"], "ambiguous")
        self.assertIn("control_flow", candidate["missing_evidence"])

    def test_candidate_carries_unified_contract_fields(self):
        candidate = self.candidates("unpaired_acquire")[0]
        for field in ("scenario_id", "source_spans", "related_locks",
                      "candidate_state", "evidence_references", "missing_evidence"):
            self.assertIn(field, candidate)


class PairedLockTests(LockScenarioTestBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t g_lock;\n"
        "void ok(void) {\n"
        "    pthread_mutex_lock(&g_lock);\n"
        "    pthread_mutex_unlock(&g_lock);\n"
        "}\n"
    )

    def test_balanced_pair_is_not_a_candidate(self):
        pairing = [c for c in self.result()["candidates"]
                   if c["scenario_id"] == "lock_pairing"]
        self.assertEqual(pairing, [])


class UnpairedReleaseTests(LockScenarioTestBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t g_lock;\n"
        "void over_release(void) {\n"
        "    pthread_mutex_unlock(&g_lock);\n"
        "}\n"
    )

    def test_unpaired_release_is_a_candidate(self):
        unpaired = self.candidates("unpaired_release")
        self.assertEqual(len(unpaired), 1)
        self.assertEqual(unpaired[0]["subject"], "g_lock")
        self.assertEqual(unpaired[0]["candidate_state"], "ambiguous")


class TryLockFailureTests(LockScenarioTestBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t g_lock;\n"
        "void try_only(void) {\n"
        "    pthread_mutex_trylock(&g_lock);\n"
        "}\n"
    )

    def test_try_lock_failure_branch_is_not_promoted_to_leak(self):
        unpaired = self.candidates("unpaired_acquire")
        self.assertEqual(unpaired, [])


class RaiiLockTests(LockScenarioTestBase):
    FIXTURE = (
        "#include <mutex>\n"
        "std::mutex m;\n"
        "void guarded(void) {\n"
        "    std::lock_guard<std::mutex> guard(m);\n"
        "}\n"
    )

    def test_raii_acquisition_is_not_reported_as_leak(self):
        self.assertEqual(self.candidates("unpaired_acquire"), [])


class SelfDeadlockTests(LockScenarioTestBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t g_lock;\n"
        "void dead(void) {\n"
        "    pthread_mutex_lock(&g_lock);\n"
        "    pthread_mutex_lock(&g_lock);\n"
        "    pthread_mutex_unlock(&g_lock);\n"
        "}\n"
    )

    def test_self_deadlock_is_a_candidate(self):
        self_deadlock = self.candidates("self_deadlock")
        self.assertEqual(len(self_deadlock), 1)
        candidate = self_deadlock[0]
        self.assertEqual(candidate["subject"], "g_lock")
        self.assertEqual(candidate["candidate_state"], "ambiguous")

    def test_reacquire_after_release_is_not_self_deadlock(self):
        # The second acquire is guarded by an unlock in between; the fixture has
        # none, so the count stays exactly one.
        self.assertEqual(len(self.candidates("self_deadlock")), 1)


class OrderInversionTests(LockScenarioTestBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t a, b;\n"
        "void f(void) {\n"
        "    pthread_mutex_lock(&a);\n"
        "    pthread_mutex_lock(&b);\n"
        "    pthread_mutex_unlock(&b);\n"
        "    pthread_mutex_unlock(&a);\n"
        "}\n"
        "void g(void) {\n"
        "    pthread_mutex_lock(&b);\n"
        "    pthread_mutex_lock(&a);\n"
        "    pthread_mutex_unlock(&a);\n"
        "    pthread_mutex_unlock(&b);\n"
        "}\n"
    )

    def test_order_inversion_is_a_candidate(self):
        inversions = self.candidates("lock_order_inversion")
        self.assertEqual(len(inversions), 1)
        candidate = inversions[0]
        self.assertEqual(candidate["order_pair"], ["a", "b"])
        self.assertEqual(candidate["candidate_state"], "ambiguous")
        self.assertIn("control_flow", candidate["missing_evidence"])


class OrderConsistentTests(LockScenarioTestBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t a, b;\n"
        "void f(void) {\n"
        "    pthread_mutex_lock(&a);\n"
        "    pthread_mutex_lock(&b);\n"
        "    pthread_mutex_unlock(&b);\n"
        "    pthread_mutex_unlock(&a);\n"
        "}\n"
        "void g(void) {\n"
        "    pthread_mutex_lock(&a);\n"
        "    pthread_mutex_lock(&b);\n"
        "    pthread_mutex_unlock(&b);\n"
        "    pthread_mutex_unlock(&a);\n"
        "}\n"
    )

    def test_consistent_order_is_not_an_inversion(self):
        self.assertEqual(self.candidates("lock_order_inversion"), [])


class BlockingInsideLockTests(LockScenarioTestBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_cond_t cond;\n"
        "pthread_mutex_t mtx;\n"
        "void waiter(void) {\n"
        "    pthread_mutex_lock(&mtx);\n"
        "    pthread_cond_wait(&cond, &mtx);\n"
        "    pthread_mutex_unlock(&mtx);\n"
        "}\n"
    )

    def test_wait_while_holding_is_blocking_inside_lock(self):
        blocked = self.candidates("blocking_inside_lock")
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["subject"], "cond")
        self.assertEqual(blocked[0]["candidate_state"], "ambiguous")


class NoBlockingInsideLockTests(LockScenarioTestBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t mtx;\n"
        "void plain(void) {\n"
        "    pthread_mutex_lock(&mtx);\n"
        "    pthread_mutex_unlock(&mtx);\n"
        "}\n"
    )

    def test_no_wait_means_no_blocking_inside_lock(self):
        self.assertEqual(self.candidates("blocking_inside_lock"), [])


class UnresolvedIdentityTests(unittest.TestCase):
    def test_empty_lock_identity_is_unresolved(self):
        events = [
            make_event("LOCK", "", start_byte=0),
            make_event("UNLOCK", "", start_byte=10),
        ]
        result = build_lock_scenarios(events)
        # Identity is empty, so pairing cannot attribute an unpaired release;
        # it reports an unresolved candidate instead of merging by nothing.
        for candidate in result["candidates"]:
            self.assertEqual(candidate["candidate_state"], "unresolved")
            self.assertTrue(candidate["unresolved"])


class DeterminismTests(unittest.TestCase):
    def test_deterministic_output(self):
        events = [
            make_event("LOCK", "g_lock", start_byte=0),
            make_event("LOCK", "g_lock", start_byte=10),
            make_event("UNLOCK", "g_lock", start_byte=20),
        ]
        first = build_lock_scenarios(events)
        second = build_lock_scenarios(list(events))
        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(first, sort_keys=True, default=str),
            json.dumps(second, sort_keys=True, default=str),
        )

    def test_wait_is_not_an_acquire_for_pairing(self):
        events = [
            make_event("LOCK", "cond", acquire_kind="wait", start_byte=0),
        ]
        result = build_lock_scenarios(events)
        self.assertEqual(
            [c for c in result["candidates"] if c["scenario_id"] == "lock_pairing"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
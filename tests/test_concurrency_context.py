"""S2 Thread / Shared State (Parent #28): concurrency_context facts.

Freezes the fail-closed fact contract for S4/S5:

1. a spawn→join pair is emitted only when the thread-handle identity is
   provably the same object; the events layer does not stamp a handle on
   THREAD_JOIN, so pairing is refused and `thread_handle_identity` is reported;
2. MAY_PARALLEL is a candidate (status ambiguous), keyed by S1's stable
   `subject_decl` identity, carrying its access events, spans and exactness;
3. an unresolved identity (unknown storage, no subject_decl) is marked
   `unresolved` and never merged with a different object by display name;
4. the capability is C/C++ only and preserves the sparse_cfg statuses.
"""

import json
import tempfile
import unittest
from pathlib import Path

from provenlattice.analysis import CAPABILITY_CONTRACT
from provenlattice.analysis_concurrency_context import (
    build_concurrency_context,
    query_concurrency_context,
)
from provenlattice.analysis_query import query_analysis
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


def write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


class ConcurrencyContextTestBase(unittest.TestCase):
    FIXTURE = ""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        write(self.root, "src/a.c", self.FIXTURE)
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("sparse_cfg",), database=self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def events(self) -> list[dict]:
        env = query_analysis(
            self.root, "sparse_cfg", file_path="src/a.c", database=self.database)
        self.assertEqual(env["status"], "available", env.get("reason"))
        return env["events"]

    def context(self) -> dict:
        return build_concurrency_context(self.events())


class SpawnJoinIdentityTests(ConcurrencyContextTestBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "int g_shared;\n"
        "void *worker(void *arg) { g_shared++; return 0; }\n"
        "void two_threads(void) {\n"
        "    pthread_t a, b;\n"
        "    pthread_create(&a, NULL, worker, NULL);\n"
        "    pthread_create(&b, NULL, worker, NULL);\n"
        "    pthread_join(a, NULL);\n"
        "    pthread_join(b, NULL);\n"
        "}\n"
        "void touch(void) { g_shared = 1; }\n"
    )

    def test_spawns_carry_handle_and_entry(self):
        ctx = self.context()
        self.assertEqual(ctx["thread_entry_points"], ["worker"])
        handles = sorted(s["handle"] for s in ctx["spawns"])
        self.assertEqual(handles, ["a", "b"])

    def test_no_pairing_without_join_handle_identity(self):
        # Two threads are spawned and joined in the same method, but THREAD_JOIN
        # carries no handle, so pairing by owner+order would merge two different
        # threads. The honest answer is: no pair, `thread_handle_identity`
        # missing evidence, and the capability gap is reported.
        ctx = self.context()
        self.assertEqual(ctx["spawn_join_pairs"], [])
        self.assertIn("thread_handle_identity", ctx["missing_evidence"])
        self.assertTrue(ctx["capability_gaps"])

    def test_may_parallel_is_a_candidate_keyed_by_identity(self):
        ctx = self.context()
        shared = next(
            subject for subject in ctx["may_parallel"]
            if subject["subject"] == "g_shared"
        )
        self.assertEqual(shared["identity"], "global:g_shared")
        self.assertEqual(shared["status"], "ambiguous")
        self.assertFalse(shared["unresolved"])
        self.assertEqual(shared["owners"], ["touch", "worker"])
        self.assertEqual(shared["thread_entry_owners"], ["worker"])
        # accesses carry event ids, spans and exactness
        for access in shared["accesses"]:
            self.assertIn("event_id", access)
            self.assertIn("start_byte", access)
            self.assertIn("exact", access)

    def test_deterministic_output(self):
        events = self.events()
        first = build_concurrency_context(events)
        second = build_concurrency_context(list(events))
        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(first, sort_keys=True),
            json.dumps(second, sort_keys=True),
        )


class UnrelatedAccessTests(ConcurrencyContextTestBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "int g_shared;\n"
        "int g_single;\n"
        "void *worker(void *arg) { return 0; }\n"
        "void spawner(void) { pthread_t t; pthread_create(&t, NULL, worker, NULL); }\n"
        "void touch_shared(void) { g_shared++; }\n"
        "void touch_both(void) { g_shared = 2; g_single = 3; }\n"
    )

    def test_single_owner_subject_is_not_a_candidate(self):
        # g_single is written by exactly one method; the presence of a spawn in
        # the file must not promote it to a MAY_PARALLEL candidate.
        ctx = self.context()
        subjects = {subject["subject"] for subject in ctx["may_parallel"]}
        self.assertIn("g_shared", subjects)
        self.assertNotIn("g_single", subjects)


class UnresolvedIdentityTests(ConcurrencyContextTestBase):
    FIXTURE = (
        "void a(void) { g_undeclared++; }\n"
        "void b(void) { g_undeclared = 2; }\n"
    )

    def test_unknown_identity_is_marked_unresolved(self):
        ctx = self.context()
        candidates = [
            subject for subject in ctx["may_parallel"]
            if subject["subject"] == "g_undeclared"
        ]
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0]["unresolved"])
        self.assertIsNone(candidates[0]["identity"])
        self.assertIn("unresolved_identity", ctx["missing_evidence"])


class CapabilityRegistrationTests(unittest.TestCase):
    def test_concurrency_context_is_c_cpp_query_time(self):
        record = CAPABILITY_CONTRACT["concurrency_context"]
        self.assertEqual(record["languages"], ("c", "cpp"))
        self.assertEqual(record["depends_on"], ("events", "sparse_cfg"))
        self.assertTrue(record.get("query_time"))
        self.assertEqual(record["status"], "partially_implemented")


class UnsupportedLanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        write(self.root, "src/a.py", "def a():\n    return 1\n")
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_python_reports_unsupported(self):
        result = query_concurrency_context(
            self.root, file_path="src/a.py", database=self.database)
        self.assertEqual(result["status"], "unsupported")


class MissingStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        write(self.root, "src/a.c", "int g; void f(void) { g++; }\n")
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_not_built_preserved(self):
        # sparse_cfg was never materialized for this file, so the context query
        # must surface not_built rather than fabricating facts.
        result = query_concurrency_context(
            self.root, file_path="src/a.c", database=self.database)
        self.assertEqual(result["status"], "not_built")


if __name__ == "__main__":
    unittest.main()
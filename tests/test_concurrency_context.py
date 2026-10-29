"""S2 Thread / Shared State (Parent #28): concurrency_context facts.

Freezes the finite, provable synchronization-order fact contract that S4/S5
will consume: same-method spawn-before-join ordering, cross-method MAY_PARALLEL
candidates over shared subjects, and honest missing evidence. The capability is
C/C++ only and never promises a complete happens-before.
"""

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

    def context(self) -> dict:
        env = query_analysis(
            self.root, "sparse_cfg", file_path="src/a.c", database=self.database)
        self.assertEqual(env["status"], "available", env.get("reason"))
        return build_concurrency_context(env["events"])


class SpawnJoinTests(ConcurrencyContextTestBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "int g_shared;\n"
        "void *worker(void *arg) { g_shared++; return 0; }\n"
        "void start_then_join(void) { pthread_t t; "
        "pthread_create(&t, NULL, worker, NULL); pthread_join(t, NULL); }\n"
        "void start_only(void) { pthread_t t; "
        "pthread_create(&t, NULL, worker, NULL); }\n"
        "void touch(void) { g_shared = 1; }\n"
    )

    def test_same_method_spawn_before_join_is_recorded(self):
        ctx = self.context()
        self.assertEqual(ctx["thread_entry_points"], ["worker"])
        self.assertEqual(ctx["spawn_points"], 2)
        self.assertEqual(ctx["join_points"], 1)
        pairs = ctx["spawn_before_join"]
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["owner"], "start_then_join")
        self.assertEqual(pairs[0]["thread_function"], "worker")

    def test_cross_method_may_parallel_candidate(self):
        ctx = self.context()
        shared = next(
            subject for subject in ctx["may_parallel"]
            if subject["subject"] == "g_shared"
        )
        self.assertEqual(shared["storage"], "global")
        self.assertEqual(shared["owners"], ["touch", "worker"])
        self.assertTrue(ctx["may_parallel_decided"])

    def test_spawn_without_join_is_honest_missing_evidence(self):
        ctx = self.context()
        self.assertIn("spawn_without_join", ctx["missing_evidence"])


class NoSpawnTests(ConcurrencyContextTestBase):
    FIXTURE = (
        "int g_shared;\n"
        "void a(void) { g_shared++; }\n"
        "void b(void) { g_shared = 2; }\n"
    )

    def test_no_spawn_points_is_not_decided(self):
        ctx = self.context()
        self.assertEqual(ctx["spawn_points"], 0)
        self.assertFalse(ctx["may_parallel_decided"])
        # the shared subject is still a candidate, but no spawn orders it
        shared = next(
            subject for subject in ctx["may_parallel"]
            if subject["subject"] == "g_shared"
        )
        self.assertEqual(shared["owners"], ["a", "b"])


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


if __name__ == "__main__":
    unittest.main()
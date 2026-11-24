"""Position- and reachability-scoped ``cross_function_call`` limitations."""

import tempfile
import unittest
from pathlib import Path

from provenlattice.analysis_concurrency_context import query_access_lockset
from provenlattice.analysis_query import query_analysis
from provenlattice.concurrency_lock_scenarios import (
    _flow_successor, _threaded_dataflow, build_access_lockset,
)
from provenlattice.defect_query import query_defect_candidates
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


def write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


class CrossFunctionCallScopeBase(unittest.TestCase):
    FIXTURES: dict[str, str] = {}
    FIXTURE = ""
    TARGET = "src/a.c"
    ANALYZE_SCOPE = "src"
    FEATURES = ("events", "sparse_cfg")

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        fixtures = self.FIXTURES or {self.TARGET: self.FIXTURE}
        for relative, source in fixtures.items():
            write(self.root, relative, source)
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)
        analyze_scope(
            self.root, self.ANALYZE_SCOPE, self.FEATURES,
            database=self.database,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def lockset(self) -> dict:
        result = query_access_lockset(
            self.root, file_path=self.TARGET, database=self.database)
        self.assertEqual(result["status"], "available", result.get("reason"))
        return result

    def accesses(self, subject: str = "shared") -> list[dict]:
        return [
            record for record in self.lockset()["access_locksets"]
            if record["subject"] == subject and record["event_type"] == "WRITE"
        ]


class ResolvedLeafTests(CrossFunctionCallScopeBase):
    FIXTURES = {"src/a.c": (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void reach_error(void) {}\n"
        "void __VERIFIER_assert(int condition) {\n"
        "    if (!condition) { reach_error(); }\n"
        "}\n"
        "void first(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    __VERIFIER_assert(1);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
        "void second(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )}

    def test_transitive_lock_free_harness_does_not_limit_accesses(self) -> None:
        records = self.accesses()
        self.assertEqual(len(records), 3)
        for record in records:
            self.assertEqual(record["held_locks"], ["global:m"])
            self.assertEqual(record["limitation"], [])

    def test_same_lock_relation_survives_harness_call(self) -> None:
        same = [
            relation for relation in self.lockset()["relations"]
            if relation["relation"] == "SAME_LOCK"
            and relation["subject"] == "global:shared"
        ]
        self.assertTrue(any(
            set(relation["owners"]) == {"first", "second"}
            for relation in same
        ))


class TransitiveLockTests(CrossFunctionCallScopeBase):
    FIXTURES = {"src/a.c": (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void inner(void) {\n"
        "    pthread_mutex_unlock(&m);\n"
        "    pthread_mutex_lock(&m);\n"
        "}\n"
        "void middle(void) { inner(); }\n"
        "void worker(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    middle();\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )}

    def test_only_hold_interval_crossing_call_is_limited(self) -> None:
        records = self.accesses()
        self.assertEqual(
            [record["limitation"] for record in records],
            [[], ["cross_function_call"], []],
        )
        self.assertEqual(
            [record["held_locks"] for record in records],
            [["global:m"], ["global:m"], ["global:m"]],
        )
        self.assertTrue(all(
            record["candidate_state"] == "ambiguous" for record in records))


class OpaqueCallAssertions:
    def test_opaque_call_is_positional(self) -> None:
        records = self.accesses()
        self.assertEqual(
            [record["limitation"] for record in records],
            [[], ["cross_function_call"], []],
        )
        self.assertEqual(records[1]["held_locks"], ["global:m"])
        self.assertEqual(records[1]["candidate_state"], "ambiguous")


class UnresolvedCallTests(OpaqueCallAssertions, CrossFunctionCallScopeBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void opaque(void);\n"
        "void worker(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    opaque();\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )


class IndirectCallTests(OpaqueCallAssertions, CrossFunctionCallScopeBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void worker(void (*callback)(void)) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    callback();\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )


class CppLegacyIndirectCallTests(OpaqueCallAssertions, CrossFunctionCallScopeBase):
    TARGET = "src/a.cc"
    FIXTURE = (
        "#include <mutex>\n"
        "std::mutex m;\n"
        "int shared;\n"
        "void callback(void) {}\n"
        "void worker(void (*callback)(void)) {\n"
        "    m.lock();\n"
        "    shared++;\n"
        "    callback();\n"
        "    shared++;\n"
        "    m.unlock();\n"
        "    m.lock();\n"
        "    shared++;\n"
        "    m.unlock();\n"
        "}\n"
    )


class NestedReceiverCallTests(CrossFunctionCallScopeBase):
    FIXTURES = {"src/a.cc": (
        "#include <mutex>\n"
        "std::mutex m;\n"
        "int shared;\n"
        "std::mutex& get_mutex(void);\n"
        "void worker(void) {\n"
        "    m.lock();\n"
        "    shared++;\n"
        "    get_mutex().lock();\n"
        "    shared++;\n"
        "    m.unlock();\n"
        "    m.lock();\n"
        "    shared++;\n"
        "    m.unlock();\n"
        "}\n"
    )}
    TARGET = "src/a.cc"

    def test_inner_receiver_call_is_not_hidden_by_outer_lock_span(self) -> None:
        records = self.accesses()
        self.assertEqual(
            ["cross_function_call" in record["limitation"] for record in records],
            [False, True, False],
        )
    def test_legacy_receiver_classification_stays_start_byte_based(self) -> None:
        cfg = query_analysis(
            self.root, "sparse_cfg", file_path=self.TARGET, database=self.database)
        events = query_analysis(
            self.root, "events", file_path=self.TARGET, database=self.database)
        legacy = build_access_lockset(
            cfg["events"], cfg["edges"], events["events"])
        records = [
            record for record in legacy["access_locksets"]
            if record["subject"] == "shared" and record["event_type"] == "WRITE"
        ]
        self.assertTrue(all(
            "cross_function_call" not in record["limitation"]
            for record in records
        ))


class SameLineCallTests(OpaqueCallAssertions, CrossFunctionCallScopeBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void left(void) {}\n"
        "void right(void) {}\n"
        "void worker(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    left(); right();\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )


class SameLineAccessAfterCallTests(OpaqueCallAssertions, CrossFunctionCallScopeBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void opaque(void);\n"
        "void worker(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    opaque(); shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )


class SameLineSecondCallArgumentTests(OpaqueCallAssertions, CrossFunctionCallScopeBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void opaque(void);\n"
        "void consume(int value) {}\n"
        "void worker(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    opaque(); consume(shared++);\n"
        "    pthread_mutex_unlock(&m);\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )


class LegacyCallInputTests(CrossFunctionCallScopeBase):
    FIXTURE = UnresolvedCallTests.FIXTURE

    def test_omitted_additive_input_retains_method_level_limitation(self) -> None:
        cfg = query_analysis(
            self.root, "sparse_cfg", file_path="src/a.c", database=self.database)
        events = query_analysis(
            self.root, "events", file_path="src/a.c", database=self.database)
        legacy = build_access_lockset(
            cfg["events"], cfg["edges"], events["events"])
        records = [
            record for record in legacy["access_locksets"]
            if record["subject"] == "shared" and record["event_type"] == "WRITE"
        ]
        self.assertEqual(
            [record["limitation"] for record in records],
            [["cross_function_call"]] * 3,
        )

        positional = build_access_lockset(
            cfg["events"], cfg["edges"], events["events"], call_callees={})
        records = [
            record for record in positional["access_locksets"]
            if record["subject"] == "shared" and record["event_type"] == "WRITE"
        ]
        self.assertEqual(
            [record["limitation"] for record in records],
            [[], ["cross_function_call"], []],
        )


class LegacyByteSpanCompatibilityTests(CrossFunctionCallScopeBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m; int shared;\n"
        "void worker(void){pthread_mutex_lock(&m); shared++; pthread_mutex_unlock(&m);}\n"
    )

    def build(self, **additive_inputs) -> dict:
        cfg = query_analysis(
            self.root, "sparse_cfg", file_path="src/a.c", database=self.database)
        events = query_analysis(
            self.root, "events", file_path="src/a.c", database=self.database)
        return build_access_lockset(
            cfg["events"], cfg["edges"], events["events"], **additive_inputs)

    def test_omitted_call_input_retains_legacy_lockset_and_relation(self) -> None:
        legacy = self.build()
        records = [
            record for record in legacy["access_locksets"]
            if record["subject"] == "shared" and record["event_type"] == "WRITE"
        ]
        self.assertEqual([record["held_locks"] for record in records], [[]])
        self.assertTrue(any(
            relation["relation"] == "DIFFERENT_LOCK"
            and relation["subject"] == "global:shared"
            for relation in legacy["relations"]
        ))


class ReacquireWithoutReleaseTests(CrossFunctionCallScopeBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void opaque(void);\n"
        "void worker(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    opaque();\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )

    def test_reacquire_without_release_does_not_clear_taint(self) -> None:
        self.assertEqual(
            [record["limitation"] for record in self.accesses()],
            [["cross_function_call"]],
        )


class MayFailReacquireTests(CrossFunctionCallScopeBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void opaque(void);\n"
        "void try_worker(void) {\n"
        "    pthread_mutex_trylock(&m);\n"
        "    opaque();\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
        "void timed_worker(void) {\n"
        "    pthread_mutex_timedlock(&m, 0);\n"
        "    opaque();\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )

    def test_successful_may_fail_acquire_makes_blocking_reacquire_nested(self) -> None:
        records = self.accesses()
        self.assertEqual(len(records), 2)
        for record in records:
            with self.subTest(owner=record["owner"]):
                self.assertEqual(record["held_locks"], ["global:m"])
                self.assertEqual(record["limitation"], ["cross_function_call"])


class CallArgumentTests(CrossFunctionCallScopeBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void opaque(int value);\n"
        "void worker(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    opaque(shared++);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )

    def test_argument_access_precedes_its_own_opaque_call(self) -> None:
        self.assertEqual(
            [record["limitation"] for record in self.accesses()],
            [[], ["cross_function_call"]],
        )


class NestedCallArgumentTests(CrossFunctionCallScopeBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void opaque(int value);\n"
        "void consume(int value);\n"
        "void worker(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    consume(opaque(shared++));\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )

    def test_nested_argument_observes_inner_call_input_not_outer_call(self) -> None:
        self.assertEqual(
            [record["limitation"] for record in self.accesses()],
            [[], ["cross_function_call"]],
        )


class SiblingCallEvaluationTests(CrossFunctionCallScopeBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "int inner(int value);\n"
        "int opaque(void);\n"
        "int consume2(int left, int right);\n"
        "void left_source_order(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    consume2(inner(shared++), opaque());\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
        "void right_source_order(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    consume2(opaque(), inner(shared++));\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )

    def test_opaque_sibling_may_precede_argument_on_either_side(self) -> None:
        records = self.accesses()
        self.assertEqual(len(records), 2)
        self.assertTrue(all(
            record["limitation"] == ["cross_function_call"]
            for record in records
        ))


class PositionalControlFlowTests(CrossFunctionCallScopeBase):
    FIXTURES = {"src/a.c": (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void opaque(void);\n"
        "void outside_lock(void) {\n"
        "    opaque();\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
        "void branch(int condition) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    if (condition) {\n"
        "        shared++;\n"
        "        opaque();\n"
        "    }\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )}

    def test_call_outside_lock_does_not_pollute_later_acquisition(self) -> None:
        record = next(
            record for record in self.accesses()
            if record["owner"] == "outside_lock"
        )
        self.assertEqual(record["held_locks"], ["global:m"])
        self.assertEqual(record["limitation"], [])

    def test_may_taint_joins_branches_without_touching_before_call(self) -> None:
        records = [
            record for record in self.accesses()
            if record["owner"] == "branch"
        ]
        self.assertEqual(
            [record["limitation"] for record in records],
            [[], ["cross_function_call"]],
        )


class BranchMayHoldTests(CrossFunctionCallScopeBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void opaque(void);\n"
        "void worker(int condition) {\n"
        "    if (condition) {\n"
        "        pthread_mutex_lock(&m);\n"
        "    }\n"
        "    opaque();\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )

    def test_lock_held_on_one_call_path_still_generates_taint(self) -> None:
        self.assertEqual(
            [record["limitation"] for record in self.accesses()],
            [["cross_function_call"]],
        )


class RaiiCallTests(CrossFunctionCallScopeBase):
    FIXTURES = {"src/a.cc": (
        "#include <mutex>\n"
        "std::mutex m;\n"
        "int shared;\n"
        "void opaque(void);\n"
        "void worker(void) {\n"
        "    std::lock_guard<std::mutex> guard(m);\n"
        "    shared++;\n"
        "    opaque();\n"
        "    shared++;\n"
        "}\n"
    )}
    TARGET = "src/a.cc"

    def test_raii_interval_is_limited_only_after_opaque_call(self) -> None:
        records = self.accesses()
        self.assertEqual(
            [record["limitation"] for record in records],
            [[], ["cross_function_call"]],
        )
        self.assertTrue(all(
            record["held_locks"] == ["global:m"] for record in records))


class RaiiNestedInExplicitTests(CrossFunctionCallScopeBase):
    FIXTURES = {"src/a.cc": (
        "#include <mutex>\n"
        "std::recursive_mutex m;\n"
        "int shared;\n"
        "void opaque(void);\n"
        "void worker(void) {\n"
        "    m.lock();\n"
        "    opaque();\n"
        "    {\n"
        "        std::lock_guard<std::recursive_mutex> guard(m);\n"
        "        shared++;\n"
        "    }\n"
        "    m.unlock();\n"
        "}\n"
    )}
    TARGET = "src/a.cc"

    def test_inner_raii_does_not_clear_explicit_outer_interval(self) -> None:
        self.assertEqual(
            [record["limitation"] for record in self.accesses()],
            [["cross_function_call"]],
        )


class ExplicitUnlockInsideRaiiTests(CrossFunctionCallScopeBase):
    FIXTURES = {"src/a.cc": (
        "#include <mutex>\n"
        "std::recursive_mutex m;\n"
        "int shared;\n"
        "void opaque(void);\n"
        "void worker(void) {\n"
        "    std::lock_guard<std::recursive_mutex> guard(m);\n"
        "    opaque();\n"
        "    m.lock();\n"
        "    m.unlock();\n"
        "    shared++;\n"
        "}\n"
    )}
    TARGET = "src/a.cc"

    def test_inner_unlock_preserves_outer_raii_interval(self) -> None:
        self.assertEqual(
            [record["limitation"] for record in self.accesses()],
            [["cross_function_call"]],
        )


class ExplicitLockAfterRaiiScopeTests(CrossFunctionCallScopeBase):
    FIXTURES = {"src/a.cc": (
        "#include <mutex>\n"
        "std::mutex m;\n"
        "int shared;\n"
        "void opaque(void);\n"
        "void worker(void) {\n"
        "    {\n"
        "        std::lock_guard<std::mutex> guard(m);\n"
        "        opaque();\n"
        "    }\n"
        "    m.lock();\n"
        "    shared++;\n"
        "    m.unlock();\n"
        "}\n"
    )}
    TARGET = "src/a.cc"

    def test_explicit_interval_after_raii_scope_starts_clean(self) -> None:
        self.assertEqual(
            [record["limitation"] for record in self.accesses()], [[]])


class CrossFileLeafTests(CrossFunctionCallScopeBase):
    FIXTURES = {
        "src/a.c": (
            "#include <pthread.h>\n"
            "pthread_mutex_t m;\n"
            "int shared;\n"
            "void worker(void) {\n"
            "    pthread_mutex_lock(&m);\n"
            "    shared++;\n"
            "    helper();\n"
            "    shared++;\n"
            "    pthread_mutex_unlock(&m);\n"
            "}\n"
        ),
        "src/helper.c": "void helper(void) {}\n",
    }

    def test_current_cross_file_leaf_body_is_lock_free(self) -> None:
        self.assertEqual(
            [record["limitation"] for record in self.accesses()], [[], []])


class MissingCrossFileBodyTests(CrossFunctionCallScopeBase):
    FIXTURES = {
        **CrossFileLeafTests.FIXTURES,
        "src/a.c": CrossFileLeafTests.FIXTURES["src/a.c"].replace(
            "helper();", "another_helper();"),
        "lib/unbuilt.c": "void another_helper(void) {}\n",
    }

    def test_unavailable_callee_body_stays_fail_closed(self) -> None:
        self.assertEqual(
            [record["limitation"] for record in self.accesses()],
            [[], ["cross_function_call"]],
        )


class LockFreeCycleTests(CrossFunctionCallScopeBase):
    FIXTURES = {"src/a.c": (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void ping(void);\n"
        "void pong(void);\n"
        "void ping(void) { pong(); }\n"
        "void pong(void) { ping(); }\n"
        "void worker(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    ping();\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )}

    def test_fully_resolved_lock_free_cycle_is_not_opaque(self) -> None:
        self.assertEqual(
            [record["limitation"] for record in self.accesses()], [[], []])


class FlowSuccessorTests(unittest.TestCase):
    THREADED = {
        "z_outer": {
            "event_type": "CALL", "start_line": 2, "end_line": 2,
            "start_byte": 100, "end_byte": 150,
        },
        "a_inner": {
            "event_type": "CALL", "start_line": 2, "end_line": 2,
            "start_byte": 100, "end_byte": 120,
        },
    }

    def test_access_before_same_start_calls_uses_inner_successor(self) -> None:
        access = {
            "start_line": 1, "end_line": 1, "start_byte": 80, "end_byte": 90,
        }
        self.assertEqual(_flow_successor(access, self.THREADED), "a_inner")

    def test_nested_argument_uses_innermost_containing_call(self) -> None:
        access = {
            "start_line": 2, "end_line": 2, "start_byte": 105, "end_byte": 110,
        }
        self.assertEqual(_flow_successor(access, self.THREADED), "a_inner")
    def test_legacy_mode_retains_id_tie_break(self) -> None:
        threaded = {
            "a_outer": self.THREADED["z_outer"],
            "z_inner": self.THREADED["a_inner"],
        }
        access = {
            "start_line": 1, "end_line": 1, "start_byte": 80, "end_byte": 90,
        }
        self.assertEqual(_flow_successor(access, threaded), "z_inner")
        self.assertEqual(
            _flow_successor(access, threaded, byte_spans=False), "a_outer")


class DataflowConvergenceTests(unittest.TestCase):
    def test_taint_propagates_beyond_one_thousand_reverse_order_nodes(self) -> None:
        count = 1005
        chain = [f"{100000 - index:06d}" for index in range(count)]
        threaded = {
            event_id: {
                "event_id": event_id,
                "event_type": (
                    "LOCK" if index == 0 else "CALL" if index == 1 else "CHECK"
                ),
                "start_line": index + 1,
                "start_byte": index * 10,
            }
            for index, event_id in enumerate(chain)
        }
        edges = [
            {"src_id": source, "dst_id": destination}
            for source, destination in zip(chain, chain[1:])
        ]
        lock_facts = {
            chain[0]: {
                "lock_identity": "m",
                "subject_exact": True,
                "acquire_kind": "blocking",
                "raii": False,
            }
        }
        held, _, tainted, _ = _threaded_dataflow(
            threaded, edges, lock_facts,
            opaque_calls=frozenset({chain[1]}),
        )
        self.assertEqual(held[chain[-1]], frozenset({"m"}))
        self.assertEqual(tainted[chain[-1]], frozenset({"m"}))


class MetamorphicTests(unittest.TestCase):
    SOURCES = (
        (
            "#include <pthread.h>\n"
            "pthread_mutex_t m;\n"
            "int shared;\n"
            "void terminal(void) {}\n"
            "void check(int condition) { if (condition) { terminal(); } }\n"
            "void worker(void) {\n"
            "    pthread_mutex_lock(&m);\n"
            "    shared++;\n"
            "    check(1);\n"
            "    shared++;\n"
            "    pthread_mutex_unlock(&m);\n"
            "}\n"
        ),
        (
            "#include <pthread.h>\n"
            "pthread_mutex_t renamed_lock;\n"
            "int renamed_shared;\n"
            "/* renamed and reformatted, with the same call graph */\n"
            "void renamed_terminal(void) {\n"
            "}\n"
            "void renamed_check(int renamed_condition) {\n"
            "    if (renamed_condition) {\n"
            "        renamed_terminal();\n"
            "    }\n"
            "}\n"
            "void renamed_worker(void) {\n"
            "    pthread_mutex_lock(&renamed_lock);\n"
            "    renamed_shared++;\n"
            "    renamed_check(1);\n"
            "    renamed_shared++;\n"
            "    pthread_mutex_unlock(&renamed_lock);\n"
            "}\n"
        ),
    )

    def query(self, source: str) -> tuple[list[list[str]], list[str]]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            database = Path(temporary) / "graph.db"
            write(root, "src/a.c", source)
            full_index(root, database)
            analyze_scope(root, "src", ("events", "sparse_cfg"), database=database)
            bundle = query_access_lockset(root, file_path="src/a.c", database=database)
            subject = "renamed_shared" if "renamed_shared" in source else "shared"
            records = sorted(
                (record for record in bundle["access_locksets"]
                 if record["subject"] == subject and record["event_type"] == "WRITE"),
                key=lambda record: record["start_byte"] if "start_byte" in record
                else record["start_line"],
            )
            return (
                [record["limitation"] for record in records],
                [relation["relation"] for relation in bundle["relations"]
                 if relation["relation"] == "SAME_LOCK"],
            )

    def test_rename_comment_and_format_changes_preserve_semantics(self) -> None:
        first = self.query(self.SOURCES[0])
        second = self.query(self.SOURCES[1])
        self.assertEqual(first[0], [[], []])
        self.assertEqual(first[0], second[0])
        self.assertTrue(first[1])
        self.assertEqual(len(first[1]), len(second[1]))


class DefectQueryWiringTests(CrossFunctionCallScopeBase):
    """The race query, not just the lockset producer, consumes the new inputs."""

    FEATURES = ("events", "sparse_cfg", "sparse_dfg")
    FIXTURES = {"src/a.c": (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void reach_error(void) {}\n"
        "void check(int condition) { if (!condition) { reach_error(); } }\n"
        "void first(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    check(1);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
        "void second(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
        "void *t1(void *a) { first(); return 0; }\n"
        "void *t2(void *a) { second(); return 0; }\n"
        "void start(void) {\n"
        "    pthread_t a, b;\n"
        "    pthread_create(&a, 0, t1, 0);\n"
        "    pthread_create(&b, 0, t2, 0);\n"
        "    pthread_join(a, 0);\n"
        "    pthread_join(b, 0);\n"
        "}\n"
    )}

    def race_result(self) -> dict:
        result = query_defect_candidates(
            self.root, defect_type="race_condition", database=self.database)
        self.assertEqual(result["status"], "available", result.get("reason"))
        return result

    def test_race_query_excludes_same_lock_across_lock_free_call(self) -> None:
        result = self.race_result()
        self.assertEqual(result["candidates"], [])
        self.assertGreaterEqual(
            result["coverage"].get("disqualified_same_lock", 0), 1)

    def test_race_query_keeps_candidate_for_opaque_call(self) -> None:
        source = self.FIXTURES["src/a.c"].replace(
            "void reach_error(void) {}",
            "void reach_error(void) {}\nvoid opaque(int);",
        ).replace("check(1);", "opaque(1);")
        write(self.root, "src/a.c", source)
        full_index(self.root, self.database)
        analyze_scope(
            self.root, "src", self.FEATURES, database=self.database)
        result = self.race_result()
        self.assertTrue(result["candidates"])
        self.assertEqual(
            result["coverage"].get("disqualified_same_lock", 0), 0)


class CrossFileExplicitPrototypeTests(CrossFunctionCallScopeBase):
    """A caller-local prototype resolves to the definition in another file."""

    FIXTURES = {
        "src/a.c": (
            "#include <pthread.h>\n"
            "pthread_mutex_t m;\n"
            "int shared;\n"
            "void helper(void);\n"
            "void first(void) {\n"
            "    pthread_mutex_lock(&m);\n"
            "    shared++;\n"
            "    helper();\n"
            "    shared++;\n"
            "    pthread_mutex_unlock(&m);\n"
            "}\n"
            "void second(void) {\n"
            "    pthread_mutex_lock(&m);\n"
            "    shared++;\n"
            "    pthread_mutex_unlock(&m);\n"
            "}\n"
        ),
        "src/helper.c": "void helper(void) {}\n",
    }

    def test_explicit_prototype_follows_cross_file_definition(self) -> None:
        records = self.accesses()
        self.assertTrue(records)
        self.assertTrue(all(not record["limitation"] for record in records))
        self.assertTrue(any(
            relation["relation"] == "SAME_LOCK"
            and relation["subject"] == "global:shared"
            for relation in self.lockset()["relations"]
        ))


class MissingDefinitionTests(CrossFunctionCallScopeBase):
    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void helper(void);\n"
        "void first(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    helper();\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
        "void second(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )

    def test_declaration_without_definition_stays_fail_closed(self) -> None:
        self.assertTrue(any(
            "cross_function_call" in record["limitation"]
            for record in self.accesses()
        ))


class AmbiguousDefinitionTests(CrossFunctionCallScopeBase):
    FIXTURES = {
        "src/a.c": MissingDefinitionTests.FIXTURE,
        "src/one.c": "void helper(void) {}\n",
        "src/two.c": "void helper(void) {}\n",
    }

    def test_two_definitions_stay_fail_closed(self) -> None:
        self.assertTrue(any(
            "cross_function_call" in record["limitation"]
            for record in self.accesses()
        ))


class SameLineKnownCallTests(CrossFunctionCallScopeBase):
    """A known vocabulary call must not make its line ambiguous."""

    FIXTURE = (
        "#include <pthread.h>\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void helper(void) {}\n"
        "void first(void) {\n"
        "    pthread_mutex_lock(&m); helper();\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
        "void second(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )

    def test_same_line_lock_and_helper_keeps_helper_lock_free(self) -> None:
        records = self.accesses()
        self.assertTrue(records)
        self.assertTrue(all(
            "cross_function_call" not in record["limitation"]
            for record in records
        ))

    def test_same_line_lock_and_helper_keeps_the_held_lock(self) -> None:
        # The unlock and its known CALL share one span; the access must still
        # observe the state before the unlock, independent of event-id order.
        records = self.accesses()
        self.assertTrue(records)
        for record in records:
            self.assertEqual(record["held_locks"], ["global:m"])
        self.assertTrue(any(
            relation["relation"] == "SAME_LOCK"
            and relation["subject"] == "global:shared"
            for relation in self.lockset()["relations"]
        ))


class CrossFileStaticCollisionTests(CrossFunctionCallScopeBase):
    """An external prototype must not follow a static same-name definition."""

    FIXTURES = {
        "src/a.c": CrossFileExplicitPrototypeTests.FIXTURES["src/a.c"],
        "src/helper.c": "static void helper(void) {}\n",
    }

    def test_static_definition_is_not_bound_to_external_prototype(self) -> None:
        self.assertTrue(any(
            "cross_function_call" in record["limitation"]
            for record in self.accesses()
        ))


class CrossFileSignatureNormalizationTests(CrossFunctionCallScopeBase):
    """Parameter names differ between prototype and definition; types match."""

    FIXTURES = {
        "src/a.c": (
            "#include <pthread.h>\n"
            "pthread_mutex_t m;\n"
            "int shared;\n"
            "void helper(int);\n"
            "void first(void) {\n"
            "    pthread_mutex_lock(&m);\n"
            "    shared++;\n"
            "    helper(1);\n"
            "    shared++;\n"
            "    pthread_mutex_unlock(&m);\n"
            "}\n"
            "void second(void) {\n"
            "    pthread_mutex_lock(&m);\n"
            "    shared++;\n"
            "    pthread_mutex_unlock(&m);\n"
            "}\n"
        ),
        "src/helper.c": "void helper(int value) {}\n",
    }

    def test_parameter_names_do_not_block_the_definition_follow(self) -> None:
        records = self.accesses()
        self.assertTrue(records)
        self.assertTrue(all(not record["limitation"] for record in records))


class SameLineArrowKnownCallTests(CrossFunctionCallScopeBase):
    """A known member call spelled with `->` must not make its line ambiguous."""

    FIXTURE = (
        "#include <pthread.h>\n"
        "typedef struct { void (*lock)(void); } Ops;\n"
        "Ops *ops;\n"
        "pthread_mutex_t m;\n"
        "int shared;\n"
        "void helper(void) {}\n"
        "void first(void) {\n"
        "    pthread_mutex_lock(&m); ops->lock(); helper();\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
        "void second(void) {\n"
        "    pthread_mutex_lock(&m);\n"
        "    shared++;\n"
        "    pthread_mutex_unlock(&m);\n"
        "}\n"
    )

    def test_arrow_known_call_is_filtered_before_ambiguity(self) -> None:
        records = self.accesses()
        self.assertTrue(records)
        self.assertTrue(all(
            "cross_function_call" not in record["limitation"]
            for record in records
        ))


class FlowSuccessorTieBreakTests(unittest.TestCase):
    THREADED = {
        "aaa": {
            "event_type": "CALL", "start_line": 4, "end_line": 4,
            "start_byte": 30, "end_byte": 40,
        },
        "zzz": {
            "event_type": "UNLOCK", "start_line": 4, "end_line": 4,
            "start_byte": 30, "end_byte": 40,
        },
    }
    ACCESS = {
        "start_line": 3, "end_line": 3, "start_byte": 21, "end_byte": 24,
    }

    def test_cfg_rank_beats_event_id_for_same_span(self) -> None:
        self.assertEqual(
            _flow_successor(
                self.ACCESS, self.THREADED,
                cfg_rank={"zzz": 0, "aaa": 1},
            ),
            "zzz",
        )

    def test_swapping_the_event_ids_does_not_change_the_cfg_choice(self) -> None:
        swapped = {"aaa": self.THREADED["zzz"], "zzz": self.THREADED["aaa"]}
        self.assertEqual(
            _flow_successor(
                self.ACCESS, swapped,
                cfg_rank={"aaa": 0, "zzz": 1},
            ),
            "aaa",
        )

    def test_no_rank_retains_the_legacy_id_tie_break(self) -> None:
        self.assertEqual(_flow_successor(self.ACCESS, self.THREADED), "aaa")


class SameSpanEventIdOrderTests(unittest.TestCase):
    """Pure producer: swapping same-span node ids must not move the lock state."""

    OWNER = "owner"
    FILE = "file"

    def _inputs(self, unlock_id: str, known_id: str):
        def point(event_id, event_type, start, end, line, annotations=None):
            return {
                "event_id": event_id, "event_type": event_type,
                "owner_symbol_id": self.OWNER,
                "owner_qualified_name": "worker",
                "file_id": self.FILE,
                "start_line": line, "end_line": line,
                "start_byte": start, "end_byte": end,
                "annotations": annotations or {},
            }
        lock = {
            "subject_decl": "global:m", "subject_storage": "global",
            "subject_exact": "true", "acquire_kind": "blocking",
            "raii": "false",
        }
        shared = {
            "subject_decl": "global:shared", "subject_storage": "global",
            "subject": "shared",
        }
        events = [
            point("e_lock", "LOCK", 1, 10, 1, dict(lock)),
            point("e_opaque", "CALL", 11, 20, 2),
            point(unlock_id, "UNLOCK", 30, 39, 4, dict(lock)),
            point(known_id, "CALL", 30, 39, 4),
            point("e_access", "WRITE", 21, 24, 3, shared),
        ]
        edges = [
            {"src_id": "e_lock", "dst_id": "e_opaque",
             "kind": "CONTROL_REACHES",
             "payload": {"owner_symbol_id": self.OWNER}},
            {"src_id": "e_opaque", "dst_id": unlock_id,
             "kind": "CONTROL_REACHES",
             "payload": {"owner_symbol_id": self.OWNER}},
            {"src_id": unlock_id, "dst_id": known_id,
             "kind": "CONTROL_REACHES",
             "payload": {"owner_symbol_id": self.OWNER}},
        ]
        lock_facts = [
            {"event_id": "e_lock", "event_type": "LOCK",
             "subject_exact": True, "acquire_kind": "blocking", "raii": False},
            {"event_id": unlock_id, "event_type": "UNLOCK",
             "subject_exact": True, "acquire_kind": "blocking", "raii": False},
        ]
        return events, edges, lock_facts

    def _record(self, unlock_id: str, known_id: str) -> dict:
        events, edges, lock_facts = self._inputs(unlock_id, known_id)
        result = build_access_lockset(
            events, edges, lock_facts,
            call_callees={}, lock_free_callees=(),
        )
        records = [
            record for record in result["access_locksets"]
            if record["event_type"] == "WRITE"
        ]
        self.assertEqual(len(records), 1)
        return records[0]

    def test_id_order_does_not_move_the_observation_point(self) -> None:
        first = self._record("z_unlock", "a_known")
        second = self._record("a_unlock", "z_known")
        for record in (first, second):
            self.assertEqual(record["held_locks"], ["global:m"])
            self.assertEqual(record["limitation"], ["cross_function_call"])


class EntrySelectionTests(unittest.TestCase):
    THREADED = {
        "z_first_call": {
            "event_type": "CALL", "start_line": 6,
            "start_byte": 101, "end_byte": 123,
        },
        "m_lock": {
            "event_type": "LOCK", "start_line": 6,
            "start_byte": 101, "end_byte": 123,
        },
        "a_later_call": {
            "event_type": "CALL", "start_line": 6,
            "start_byte": 125, "end_byte": 133,
        },
    }
    EDGES = [
        {"src_id": "z_first_call", "dst_id": "m_lock"},
        {"src_id": "m_lock", "dst_id": "a_later_call"},
    ]
    LOCK_FACTS = {
        "m_lock": {
            "lock_identity": "m", "subject_exact": True,
            "acquire_kind": "blocking", "raii": False,
        },
    }

    def test_entry_is_the_first_source_point_not_the_lowest_event_id(self) -> None:
        # `a_later_call` sorts first by id; attaching the synthetic entry to it
        # meets its held set with the empty entry and erases the lock.
        held, _, _, _ = _threaded_dataflow(
            self.THREADED, self.EDGES, self.LOCK_FACTS, source_entry=True)
        self.assertEqual(held["a_later_call"], frozenset({"m"}))


if __name__ == "__main__":
    unittest.main()

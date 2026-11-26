"""M9 (issue-pilot #81): local definite assignment / uninitialized use.

Pins the contract the query promises over the #84 facts
(`docs/c-local-declaration-access-v1.md`):

* a local read with no prior definition is a definite uninitialized candidate;
* a local pointer dereferenced before assignment is a candidate, but the
  `unknown_write_through` coverage the dereference itself publishes makes the
  state explicit `unknown`, never a definite claim;
* declaration initialization, a prior assignment, and both if/else arms
  assigned produce no candidate;
* one assigned arm is `maybe_uninitialized`, with the uncovered path recorded;
* an early return keeps the fall-through read uninitialized while the in-arm
  read is initialized;
* static zero initialization, parameters, and unreachable uses produce no
  candidate;
* macro/goto/loop/conditional/unknown-write-through coverage is explicit
  `unknown` (or a coverage count), never silent safety;
* same-spelled shadowed locals join by the scoped declaration token;
* the query is registered in QUERY_NAMES / the memory category, deterministic,
  and a pure reader.
"""

import json
import tempfile
import unittest
from pathlib import Path

from provenlattice import defect
from provenlattice.analysis_query import query_analysis
from provenlattice.defect_query import (
    CATEGORY_QUERIES,
    SUPPORTED_DEFECT_QUERIES,
    query_defect_candidates,
)
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


def write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


class UninitializedUseBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.database = Path(self.temp.name) / "graph.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self, source: str) -> None:
        write(self.root, "src/a.c", source)
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("defect",), database=self.database)

    def query(self, **kwargs) -> dict:
        return query_defect_candidates(
            self.root, database=self.database, **kwargs)

    def candidates(self, source: str, **kwargs) -> list[dict]:
        self.build(source)
        env = self.query(defect_type=defect.UNINITIALIZED_USE, **kwargs)
        self.assertEqual(env["status"], "available")
        return env["candidates"]

    def only(self, source: str, **kwargs) -> tuple[dict, dict]:
        self.build(source)
        env = self.query(defect_type=defect.UNINITIALIZED_USE, **kwargs)
        self.assertEqual(env["status"], "available")
        self.assertEqual(len(env["candidates"]), 1, env["candidates"])
        return env["candidates"][0], env


class DefiniteTests(UninitializedUseBase):
    def test_uninitialized_scalar_read_is_definite(self) -> None:
        candidate, env = self.only("int f(void) { int x; return x; }\n")
        self.assertEqual(candidate["query"], defect.UNINITIALIZED_USE)
        self.assertEqual(candidate["defect_key"], defect.UNINITIALIZED_USE_KEY)
        self.assertEqual(candidate["metadata"]["state"], "uninitialized")
        self.assertEqual(candidate["resolution_status"], "resolved")
        self.assertEqual(candidate["confidence"], 0.5)
        self.assertEqual(candidate["subject"]["name"], "x")
        self.assertEqual(candidate["subject"]["kind"], "local_object")
        self.assertTrue(candidate["subject"]["identity"].startswith("local:"))
        self.assertEqual(
            [fact["event"] for fact in candidate["facts"]],
            ["DECLARATION", "READ"],
        )
        self.assertEqual(candidate["missing_evidence"], [])
        self.assertTrue(candidate["paths"])
        self.assertEqual(
            candidate["metadata"]["path_outcomes"],
            [{"context": "entry", "outcome": "uncovered"}],
        )
        self.assertTrue(candidate["source_evidence"])
        self.assertGreaterEqual(
            env["coverage"]["uninitialized_uses"], 1)

    def test_pointer_dereference_is_explicit_unknown_coverage(self) -> None:
        # `*p = 1` reads the pointer itself; the write-through it performs also
        # marks the method's #84 coverage unknown. The candidate must exist,
        # but it must not be presented as a definite uninitialized claim.
        candidate, env = self.only("void f(void) { int *p; *p = 1; }\n")
        self.assertEqual(candidate["metadata"]["state"], "unknown")
        self.assertEqual(candidate["resolution_status"], "ambiguous")
        self.assertEqual(candidate["subject"]["kind"], "local_pointer")
        self.assertEqual(candidate["metadata"]["use_direction"], "DEREFERENCE")
        self.assertIn(
            "unknown_write_through",
            candidate["metadata"]["coverage_reasons"],
        )
        self.assertNotEqual(candidate["metadata"]["state"], "uninitialized")
        self.assertIn("coverage_unknown_write_through", candidate["missing_evidence"])
        self.assertGreaterEqual(
            env["coverage"]["uninitialized_uses_coverage_unknown"], 1)

    def test_read_modify_write_is_a_use(self) -> None:
        candidate, _ = self.only("int f(void) { int x; x += 1; return x; }\n")
        # The READ and WRITE share the target's span; the paired read still
        # precedes the definition, so it is uninitialized.
        self.assertEqual(candidate["metadata"]["state"], "uninitialized")

    def test_function_pointer_call_reads_an_uninitialized_pointer(self) -> None:
        candidate, _ = self.only(
            "void f(void) { void (*fp)(void); fp(); }\n")
        self.assertEqual(candidate["subject"]["name"], "fp")
        self.assertEqual(candidate["metadata"]["state"], "uninitialized")


class SafeShapeTests(UninitializedUseBase):
    def test_initialized_declaration_is_safe(self) -> None:
        self.assertEqual(
            self.candidates("int f(void) { int x = 1; return x; }\n"), [])

    def test_prior_assignment_is_safe(self) -> None:
        self.assertEqual(
            self.candidates("int f(void) { int x; x = 1; return x; }\n"), [])

    def test_both_branches_assigned_is_safe(self) -> None:
        self.assertEqual(
            self.candidates(
                "int f(int n) { int x; if (n) { x = 1; } else { x = 2; } "
                "return x; }\n"),
            [],
        )

    def test_early_return_arm_is_safe(self) -> None:
        self.assertEqual(
            self.candidates(
                "int f(int n) { int x; if (n) { return 0; } x = 1; "
                "return x; }\n"),
            [],
        )

    def test_static_zero_initialized_is_safe(self) -> None:
        self.assertEqual(
            self.candidates("int f(void) { static int x; return x; }\n"), [])

    def test_parameter_is_not_in_the_population(self) -> None:
        self.assertEqual(
            self.candidates("int f(int x) { return x; }\n"), [])

    def test_unreachable_use_is_not_a_use(self) -> None:
        self.assertEqual(
            self.candidates(
                "int f(void) { int x; return 0; x = 1; return x; }\n"),
            [],
        )


class PathTests(UninitializedUseBase):
    def test_one_assigned_arm_is_maybe_uninitialized(self) -> None:
        candidate, _ = self.only(
            "int f(int n) { int x; if (n) { x = 1; } return x; }\n")
        self.assertEqual(candidate["metadata"]["state"], "maybe_uninitialized")
        self.assertEqual(candidate["resolution_status"], "ambiguous")
        self.assertIn("path_coverage_incomplete", candidate["missing_evidence"])
        outcomes = {
            item["outcome"] for item in candidate["metadata"]["path_outcomes"]
        }
        self.assertEqual(outcomes, {"covered", "uncovered"})

    def test_early_return_fall_through_read_is_definite(self) -> None:
        candidate, _ = self.only(
            "int f(int n) { int x; if (n) { x = 1; return x; } return x; }\n")
        # Only the fall-through read is uninitialized; the read inside the
        # taken arm has its own definition.
        self.assertEqual(candidate["metadata"]["state"], "uninitialized")
        self.assertEqual(
            candidate["metadata"]["contexts"],
            [{"entry": False, "event_type": "BRANCH",
              "flags": ["branch=false"], "ordinal": 0}],
        )

    def test_else_read_with_true_arm_assignment_is_definite(self) -> None:
        candidate, _ = self.only(
            "int f(int n) { int x; if (n) { x = 1; } else { return x; } "
            "return x; }\n")
        self.assertEqual(candidate["metadata"]["state"], "uninitialized")
        self.assertEqual(
            candidate["metadata"]["contexts"][0]["flags"], ["branch=false"])

    def test_shadowed_locals_join_by_declaration_token(self) -> None:
        source = "int f(void) { int x = 0; { int x; return x; } }\n"
        candidates = self.build_candidates(source)
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["subject"]["name"], "x")
        # The outer `x = 0` is initialized; the candidate must be the inner
        # declaration, which the scoped token distinguishes by byte offset.
        self.assertTrue(candidate["subject"]["identity"].startswith("local:"))
        self.assertTrue(candidate["subject"]["identity"].endswith(
            f":x:{source.index('int x;')}"))

    def build_candidates(self, source: str) -> list[dict]:
        self.build(source)
        env = self.query(defect_type=defect.UNINITIALIZED_USE)
        self.assertEqual(env["status"], "available")
        return env["candidates"]


class CoverageTests(UninitializedUseBase):
    def test_macro_coverage_is_explicit_unknown(self) -> None:
        candidate, env = self.only(
            "#define M 1\nint f(void) { int x; int y = M; return x; }\n")
        self.assertEqual(candidate["metadata"]["state"], "unknown")
        self.assertIn("macro", candidate["metadata"]["coverage_reasons"])
        self.assertIn("coverage_macro", candidate["missing_evidence"])
        self.assertGreaterEqual(
            env["coverage"]["uninitialized_uses_coverage_unknown"], 1)

    def test_loop_coverage_is_explicit_unknown(self) -> None:
        candidate, _ = self.only(
            "int f(int n) { int x; while (n) { x = 1; n = 0; } return x; }\n")
        self.assertEqual(candidate["metadata"]["state"], "unknown")
        self.assertIn("unsupported_loop", candidate["metadata"]["coverage_reasons"])

    def test_goto_coverage_is_explicit_unknown(self) -> None:
        candidate, _ = self.only(
            "int f(int c) { int x; if (c) { goto done; } done: return x; }\n")
        self.assertEqual(candidate["metadata"]["state"], "unknown")
        self.assertIn("goto", candidate["metadata"]["coverage_reasons"])

    def test_partial_parse_coverage_is_explicit_unknown(self) -> None:
        candidate, _ = self.only(
            "int f(void) { int x; if (x { return x; } }\n")
        self.assertEqual(candidate["metadata"]["state"], "unknown")
        self.assertIn("partial_parse", candidate["metadata"]["coverage_reasons"])

    def test_initialized_use_in_unknown_coverage_is_counted_not_silent(self) -> None:
        self.build(
            "#define M 1\nint f(void) { int x; x = 1; int y = M; return x; }\n")
        env = self.query(defect_type=defect.UNINITIALIZED_USE)
        self.assertEqual(env["status"], "available")
        self.assertEqual(env["candidates"], [])
        self.assertGreaterEqual(
            env["coverage"]["uninitialized_uses_coverage_unknown"], 1)


class RegistrationTests(UninitializedUseBase):
    def test_query_is_registered(self) -> None:
        self.assertIn(defect.UNINITIALIZED_USE, defect.QUERY_NAMES)
        self.assertIn(defect.UNINITIALIZED_USE, SUPPORTED_DEFECT_QUERIES)
        self.assertIn(
            (defect.UNINITIALIZED_USE, {}), CATEGORY_QUERIES["memory"])

    def test_memory_category_consumes_the_query(self) -> None:
        self.build("int f(void) { int x; return x; }\n")
        env = self.query(category="memory")
        self.assertEqual(env["status"], "available")
        self.assertTrue(any(
            candidate["query"] == defect.UNINITIALIZED_USE
            for candidate in env["candidates"]))

    def test_all_consumes_the_query(self) -> None:
        self.build("int f(void) { int x; return x; }\n")
        env = self.query()
        self.assertTrue(any(
            candidate["query"] == defect.UNINITIALIZED_USE
            for candidate in env["candidates"]))

    def test_deterministic_output(self) -> None:
        self.build("int f(int n) { int x; if (n) { x = 1; } return x; }\n")
        first = self.query(defect_type=defect.UNINITIALIZED_USE)
        second = self.query(defect_type=defect.UNINITIALIZED_USE)
        self.assertEqual(
            json.dumps(first["candidates"], sort_keys=True),
            json.dumps(second["candidates"], sort_keys=True),
        )

    def test_subject_filter(self) -> None:
        source = "int f(void) { int x; int y; return x + y; }\n"
        self.build(source)
        env = self.query(defect_type=defect.UNINITIALIZED_USE, subject="x")
        self.assertTrue(env["candidates"])
        self.assertTrue(all(
            candidate["subject"]["name"] == "x"
            for candidate in env["candidates"]))
        env = self.query(defect_type=defect.UNINITIALIZED_USE, subject="z")
        self.assertEqual(env["candidates"], [])

    def test_budget_reports_population_without_candidates(self) -> None:
        self.build("int f(void) { int x; return x; }\n")
        env = self.query(defect_type=defect.UNINITIALIZED_USE, max_candidates=0)
        self.assertEqual(env["candidates"], [])
        self.assertGreaterEqual(env["coverage"]["uninitialized_definite"], 1)

    def test_query_writes_no_rows(self) -> None:
        import sqlite3
        from contextlib import closing

        self.build("int f(void) { int x; return x; }\n")

        def counts() -> tuple[int, int, int, int]:
            with closing(sqlite3.connect(self.database)) as connection:
                return tuple(
                    int(connection.execute(
                        f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    for table in (
                        "analysis_nodes", "analysis_edges", "nodes", "edges")
                )

        before = counts()
        self.query(defect_type=defect.UNINITIALIZED_USE)
        self.assertEqual(counts(), before)

    def test_direct_run_reads_raw_query_analysis_events(self) -> None:
        write(self.root, "src/a.c", "int f(void) { int x; return x; }\n")
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("sparse_cfg",), database=self.database)
        env = query_analysis(
            self.root, "sparse_cfg", file_path="src/a.c",
            database=self.database)
        self.assertEqual(env["status"], "available")
        result = defect.run(
            defect.UNINITIALIZED_USE, env["events"], env["edges"])
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(
            result.candidates[0].metadata["state"], "uninitialized")


class ConditionalWriteTests(UninitializedUseBase):
    def test_logical_and_write_is_maybe(self) -> None:
        candidate, _ = self.only(
            "int f(int n) { int x; if (n && (x = 1)) { } return x; }\n")
        self.assertEqual(candidate["metadata"]["state"], "maybe_uninitialized")
        self.assertEqual(candidate["resolution_status"], "ambiguous")
        self.assertIn("path_coverage_incomplete", candidate["missing_evidence"])

    def test_initializer_logical_and_write_is_maybe(self) -> None:
        candidate, _ = self.only(
            "int f(int n) { int x; int y = (n && (x = 1)); return x; }\n")
        self.assertEqual(candidate["metadata"]["state"], "maybe_uninitialized")
        self.assertIn("path_coverage_incomplete", candidate["missing_evidence"])

    def test_pointer_guard_write_is_maybe(self) -> None:
        # `p && (x = 1)` is a CHECK condition (not a BRANCH); the write inside
        # it must not be an unconditional definition.
        candidate, _ = self.only(
            "int f(int n, int *p) { int x; if (p && (x = 1)) { } return x; }\n")
        self.assertEqual(candidate["metadata"]["state"], "maybe_uninitialized")
        self.assertIn("path_coverage_incomplete", candidate["missing_evidence"])

    def test_negated_pointer_guard_write_is_maybe(self) -> None:
        candidate, _ = self.only(
            "int f(int n, int *p) { int x; if (!p && (x = 1)) { } return x; }\n")
        self.assertEqual(candidate["metadata"]["state"], "maybe_uninitialized")


class BareConditionCoverageTests(UninitializedUseBase):
    def test_bare_if_condition_is_counted_not_silent(self) -> None:
        self.build(
            "int f(int n) { int x; if (x) { return 1; } return 0; }\n")
        env = self.query(defect_type=defect.UNINITIALIZED_USE)
        self.assertEqual(env["status"], "available")
        self.assertEqual(env["candidates"], [])
        self.assertGreaterEqual(
            env["coverage"]["uninitialized_bare_condition_reads"], 1)

    def test_bare_pointer_condition_is_counted_not_silent(self) -> None:
        # A pointer bare condition is published as CHECK, not BRANCH; without
        # counting CHECK expressions the gap would read as analyzed-and-safe.
        self.build(
            "int f(void) { int *p; if (p) { return 1; } return 0; }\n")
        env = self.query(defect_type=defect.UNINITIALIZED_USE)
        self.assertEqual(env["status"], "available")
        self.assertEqual(env["candidates"], [])
        self.assertGreaterEqual(
            env["coverage"]["uninitialized_bare_condition_reads"], 1)
        self.assertIn(
            "MISSING_INPUT_LOCAL_ACCESS_BARE_CONDITION",
            env["coverage"]["uninitialized_missing_evidence"])

    def test_bare_pointer_condition_return_is_counted(self) -> None:
        self.build(
            "int f(void) { int *p; if (p) return 1; return 0; }\n")
        env = self.query(defect_type=defect.UNINITIALIZED_USE)
        self.assertEqual(env["candidates"], [])
        self.assertGreaterEqual(
            env["coverage"]["uninitialized_bare_condition_reads"], 1)


class KnownFalseNegativeTests(UninitializedUseBase):
    def test_self_initializer_read_is_a_known_fn(self) -> None:
        # `int x = x;` reads x before initialization, but the declaration's
        # initializer is published as a definition and the initializer read is
        # not a separate access fact. V1 keeps the known FN rather than
        # guessing; the docs and capability matrix record it.
        self.assertEqual(
            self.candidates("int f(void) { int x = x; return x; }\n"), [])


class SyntheticFailClosedTests(unittest.TestCase):
    TOKEN = "local:src/a.c:f:x:1"

    @staticmethod
    def _position() -> dict:
        return {
            "predecessors": [], "entry": True, "status": "reachable",
            "coverage_status": "complete", "coverage_reasons": [],
        }

    @staticmethod
    def _event(kind: str, start: int, end: int, annotations: dict) -> dict:
        return {
            "event_type": kind, "event_id": f"event:{kind}:{start}",
            "owner_symbol_id": "symbol:f", "owner_qualified_name": "f",
            "relative_path": "src/a.c", "start_line": 1, "end_line": 1,
            "start_byte": start, "end_byte": end, "matched_name": "x",
            "annotations": annotations,
        }

    def _events(self, *, storage_class: str = "automatic",
                write_target: str = "direct") -> list[dict]:
        declaration = {
            "declaration": self.TOKEN, "decl": "local:x", "kind": "scalar",
            "storage": "local", "storage_class": storage_class, "type": "int",
            "initialized": False, "status": "supported",
            "coverage_status": "complete", "coverage_reasons": [],
        }
        access = {
            "declaration": self.TOKEN, "direction": "READ", "target": "direct",
            "status": "supported", "coverage_status": "complete",
            "coverage_reasons": [],
        }
        write = {
            "declaration": self.TOKEN, "direction": "WRITE",
            "target": write_target, "status": "supported",
            "coverage_status": "complete", "coverage_reasons": [],
        }
        position = self._position()
        return [
            self._event("DECLARATION", 1, 2, {
                "local_declaration_v1": declaration,
                "control_position_v1": position,
            }),
            self._event("WRITE", 10, 12, {
                "local_access_v1": write,
                "control_position_v1": position,
            }),
            self._event("READ", 20, 21, {
                "local_access_v1": access,
                "control_position_v1": position,
            }),
        ]

    def test_missing_storage_class_is_unknown(self) -> None:
        result = defect.uninitialized_use(
            self._events(storage_class=""), [])
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.metadata["state"], "unknown")
        self.assertIn(
            "storage_class_unknown", candidate.metadata["coverage_reasons"])

    def test_empty_write_target_makes_the_use_unknown(self) -> None:
        # A write whose target kind is missing is not a provable direct
        # definition; treating it as "not a definition" would claim the use is
        # definitely uninitialized. The missing value must downgrade the use to
        # explicit unknown instead.
        result = defect.uninitialized_use(
            self._events(write_target=""), [])
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.metadata["state"], "unknown")
        self.assertIn(
            "write_target_missing", candidate.metadata["coverage_reasons"])


if __name__ == "__main__":
    unittest.main()

"""Issue-pilot #139: unevaluated operands publish no runtime access facts.

Pins the producer contract in ``docs/unevaluated-operand-facts-v1.md``:

* C/C++ ``sizeof``, C11/C++ ``_Alignof``/``alignof``, C++ ``decltype``,
  ``noexcept``, and ``requires`` operands produce no READ/WRITE/DEREFERENCE
  points and no ``memory_access_v1``/``buffer_extent_v1`` value facts;
* the evaluated bound of a VLA type inside ``sizeof`` remains a real read;
* ``noexcept`` is an operator only in C++; in C it is an ordinary function;
* vocabulary CALL identity is retained for a call spelled inside an
  unevaluated operand, while its memory-API facts and ``arguments`` annotation
  are not published;
* address computation (``&a[i]``) is not an unevaluated operand and keeps its
  structural DEREFERENCE point (without a value-access fact).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from provenlattice.analysis import ANALYZER_VERSIONS
from provenlattice.analysis_query import query_analysis
from provenlattice.defect_query import query_defect_candidates
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


class UnevaluatedOperandFactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.database = Path(self.temp.name) / "graph.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self, source: str, relative_path: str = "src/facts.c") -> dict:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("sparse_cfg",), database=self.database)
        env = query_analysis(
            self.root, "sparse_cfg", file_path=relative_path, database=self.database
        )
        self.assertEqual(env["status"], "available", env.get("reason"))
        return env

    @staticmethod
    def annotations(event: dict) -> dict:
        return event.get("annotations", {})

    def events(
        self, env: dict, event_type: str, owner: str | None = None
    ) -> list[dict]:
        return [
            event for event in env["events"]
            if event["event_type"] == event_type
            and (owner is None or event["owner_qualified_name"] == owner)
        ]

    def named(
        self, env: dict, event_type: str, matched_name: str, owner: str | None = None
    ) -> list[dict]:
        return [
            event for event in self.events(env, event_type, owner)
            if event["matched_name"] == matched_name
        ]

    def local_reads(self, env: dict, owner: str, name: str = "n") -> list[dict]:
        return [
            event for event in self.events(env, "READ", owner)
            if "local_access_v1" in self.annotations(event)
            and event["matched_name"] == name
        ]

    def test_c_sizeof_assignment_and_read_publish_no_events(self) -> None:
        env = self.build(
            "int sizeof_assignment(void) {\n"
            "    int x;\n"
            "    sizeof(x = 1);\n"
            "    return x;\n"
            "}\n"
            "int sizeof_read(void) {\n"
            "    int x;\n"
            "    return sizeof x;\n"
            "}\n"
        )
        self.assertEqual(self.named(env, "WRITE", "x", "sizeof_assignment"), [])
        # The return is a real read; the sizeof operand is not.
        self.assertEqual(
            len(self.named(env, "READ", "x", "sizeof_assignment")), 1
        )
        self.assertEqual(self.named(env, "READ", "x", "sizeof_read"), [])

    def test_nested_parenthesized_and_call_operands_are_unevaluated(self) -> None:
        env = self.build(
            "int consume(int, int *);\n"
            "void nested(void) {\n"
            "    int x;\n"
            "    int *a = 0;\n"
            "    sizeof((x = 1));\n"
            "    sizeof(sizeof(x = 1));\n"
            "    sizeof(consume(x = 1, a[2]));\n"
            "}\n"
        )
        self.assertEqual(self.named(env, "WRITE", "x", "nested"), [])
        self.assertEqual(self.named(env, "DEREFERENCE", "a[2]", "nested"), [])

    def test_sizeof_subscript_and_pointer_dereference_publish_no_points(self) -> None:
        env = self.build(
            "void sizeof_shapes(char *a, char **p) {\n"
            "    sizeof(a[2]);\n"
            "    sizeof(*p);\n"
            "    sizeof(int[4]);\n"
            "}\n"
        )
        self.assertEqual(self.named(env, "DEREFERENCE", "a[2]"), [])
        self.assertEqual(self.named(env, "DEREFERENCE", "*p"), [])
        self.assertEqual(self.events(env, "DEREFERENCE"), [])
        for event in env["events"]:
            annotations = self.annotations(event)
            self.assertNotIn("memory_access_v1", annotations, event)
            self.assertNotIn("buffer_extent_v1", annotations, event)

    def test_address_of_keeps_structural_point_without_access_fact(self) -> None:
        env = self.build(
            "void address_of(char *a) {\n"
            "    char *p = &a[1];\n"
            "    (void)p;\n"
            "}\n"
        )
        points = self.named(env, "DEREFERENCE", "a[1]", "address_of")
        self.assertEqual(len(points), 1, points)
        annotations = self.annotations(points[0])
        self.assertNotIn("memory_access_v1", annotations)
        self.assertIn("buffer_extent_v1", annotations)

    def test_global_and_member_accesses_inside_sizeof_publish_no_events(self) -> None:
        env = self.build(
            "int g;\n"
            "struct S { int x; };\n"
            "void unevaluated_storage(struct S *s) {\n"
            "    sizeof(g = 1);\n"
            "    sizeof(s->x = 1);\n"
            "}\n"
        )
        self.assertEqual(self.named(env, "WRITE", "g"), [])
        self.assertEqual(self.named(env, "WRITE", "s->x"), [])
        self.assertEqual(self.named(env, "DEREFERENCE", "s->x"), [])

    def test_cpp_alignof_decltype_noexcept_and_requires_are_unevaluated(self) -> None:
        env = self.build(
            "int alignof_operand(void) {\n"
            "    int x;\n"
            "    return (int)alignof(decltype(x = 1));\n"
            "}\n"
            "int decltype_operand(void) {\n"
            "    int x;\n"
            "    using T = decltype((x = 1));\n"
            "    return (int)sizeof(T);\n"
            "}\n"
            "int noexcept_operand(void) {\n"
            "    int x;\n"
            "    return noexcept(x = 1) ? 0 : 1;\n"
            "}\n"
            "bool requires_operand(void) {\n"
            "    int x;\n"
            "    return requires { x = 1; };\n"
            "}\n",
            relative_path="src/facts.cpp",
        )
        for owner in (
            "alignof_operand", "decltype_operand",
            "noexcept_operand", "requires_operand",
        ):
            with self.subTest(owner=owner):
                self.assertEqual(self.named(env, "WRITE", "x", owner), [])
                self.assertEqual(self.named(env, "READ", "x", owner), [])

    def test_c_noexcept_is_an_ordinary_call_and_evaluates_arguments(self) -> None:
        env = self.build(
            "int noexcept(int);\n"
            "int c_noexcept(void) {\n"
            "    int x;\n"
            "    return noexcept(x = 1);\n"
            "}\n"
        )
        writes = self.named(env, "WRITE", "x", "c_noexcept")
        self.assertEqual(len(writes), 1, writes)
        self.assertEqual(len(self.events(env, "CALL", "c_noexcept")), 1)

    def test_cpp_noexcept_keeps_call_identity_but_no_runtime_access(self) -> None:
        env = self.build(
            "int cpp_noexcept(void) {\n"
            "    int x;\n"
            "    return noexcept(x = 1) ? 0 : 1;\n"
            "}\n",
            relative_path="src/facts.cpp",
        )
        self.assertEqual(self.named(env, "WRITE", "x", "cpp_noexcept"), [])
        self.assertEqual(len(self.events(env, "CALL", "cpp_noexcept")), 1)

    def test_sizeof_user_call_keeps_call_identity_without_argument_facts(self) -> None:
        env = self.build(
            "int consume(int, int *);\n"
            "void sizeof_call(int *a) {\n"
            "    int x;\n"
            "    sizeof(consume((x = 3), a[2]));\n"
            "}\n"
        )
        calls = self.events(env, "CALL", "sizeof_call")
        self.assertEqual(len(calls), 1, calls)
        self.assertNotIn("arguments", self.annotations(calls[0]))
        self.assertEqual(self.named(env, "WRITE", "x", "sizeof_call"), [])
        self.assertEqual(self.named(env, "DEREFERENCE", "a[2]", "sizeof_call"), [])

    def test_sizeof_memory_call_drops_memory_facts(self) -> None:
        env = self.build(
            "void *memcpy(void *, const void *, unsigned long);\n"
            "void sizeof_memcpy(char *d, char *s, int n) {\n"
            "    sizeof(memcpy(d, s, n));\n"
            "}\n"
        )
        calls = self.events(env, "CALL", "sizeof_memcpy")
        self.assertEqual(len(calls), 1, calls)
        annotations = self.annotations(calls[0])
        self.assertNotIn("memory_access_v1", annotations)
        self.assertNotIn("buffer_extent_v1", annotations)
        self.assertNotIn("arguments", annotations)

    def test_sizeof_vla_bound_is_evaluated(self) -> None:
        env = self.build(
            "int sizeof_vla_bound(void) {\n"
            "    int n = 2;\n"
            "    return (int)sizeof(int[n]);\n"
            "}\n"
            "int nested_sizeof_vla_bound(void) {\n"
            "    int n = 2;\n"
            "    return (int)sizeof(sizeof(int[n]));\n"
            "}\n"
            "int evaluated_nested_sizeof_vla_bound(void) {\n"
            "    int n = 2;\n"
            "    return (int)sizeof(int[sizeof(int[n])]);\n"
            "}\n"
            "int sizeof_pointer_to_vla(void) {\n"
            "    int n = 2;\n"
            "    return (int)sizeof(int (*)[n]);\n"
            "}\n"
            "int sizeof_vla_of_pointers(void) {\n"
            "    int n = 2;\n"
            "    return (int)sizeof(int *[n]);\n"
            "}\n"
        )
        expected = {
            "sizeof_vla_bound": 1,
            "nested_sizeof_vla_bound": 0,
            "evaluated_nested_sizeof_vla_bound": 1,
            "sizeof_pointer_to_vla": 0,
            "sizeof_vla_of_pointers": 1,
        }
        for owner, count in expected.items():
            with self.subTest(owner=owner):
                self.assertEqual(len(self.local_reads(env, owner)), count)

    def test_evaluated_array_bound_keeps_its_dereference(self) -> None:
        env = self.build(
            "void vla_bound(char *a) {\n"
            "    char b[a[2]];\n"
            "    (void)b;\n"
            "}\n"
        )
        points = self.named(env, "DEREFERENCE", "a[2]", "vla_bound")
        self.assertEqual(len(points), 1, points)
        self.assertIn("memory_access_v1", self.annotations(points[0]))

    def test_analyzer_version_advances(self) -> None:
        self.assertEqual(ANALYZER_VERSIONS["sparse_cfg:cpp"], 14)
        self.assertEqual(ANALYZER_VERSIONS["sparse_dfg:cpp"], 4)

    def test_facts_are_deterministic(self) -> None:
        source = (
            "int f(void) {\n"
            "    int x;\n"
            "    sizeof(x = 1);\n"
            "    return x;\n"
            "}\n"
        )
        first = self.build(source)
        snapshot = [
            (event["event_type"], event["ordinal"], event["matched_name"],
             json.dumps(self.annotations(event), sort_keys=True))
            for event in first["events"]
        ]
        second = self.build(source)
        self.assertEqual(
            snapshot,
            [
                (event["event_type"], event["ordinal"], event["matched_name"],
                 json.dumps(self.annotations(event), sort_keys=True))
                for event in second["events"]
            ],
        )


class UnevaluatedOperandUninitializedUseTests(unittest.TestCase):
    """End-to-end F6 shape through the M9 query (producer half only).

    #137 owns the query-side fail-closed behavior; these assertions pin the
    observable outcome the producer fix must make possible.
    """

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.database = Path(self.temp.name) / "graph.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def query(self, source: str) -> dict:
        path = self.root / "src/a.c"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("defect",), database=self.database)
        result = query_defect_candidates(
            self.root, defect_type="uninitialized_use", database=self.database
        )
        self.assertEqual(result["status"], "available", result.get("reason"))
        return result

    def test_sizeof_assignment_does_not_initialize_the_read(self) -> None:
        result = self.query(
            "int f(void) { int x; sizeof(x = 1); return x; }\n"
        )
        self.assertEqual(len(result["candidates"]), 1, result["candidates"])
        coverage = result["coverage"]
        self.assertEqual(coverage["uninitialized_uses_initialized"], 0)
        self.assertEqual(coverage["uninitialized_uses"], 1)

    def test_sizeof_read_is_not_a_use(self) -> None:
        result = self.query("int f(void) { int x; return sizeof x; }\n")
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["coverage"]["uninitialized_uses"], 0)

    def test_sizeof_read_does_not_displace_a_later_initializer(self) -> None:
        result = self.query(
            "int f(void) { int x; sizeof(x); x = 1; return x; }\n"
        )
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["coverage"]["uninitialized_uses_initialized"], 1)


if __name__ == "__main__":
    unittest.main()

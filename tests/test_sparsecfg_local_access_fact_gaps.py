from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from provenlattice.analysis_query import query_analysis
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


class SparseCfgLocalAccessFactGapTests(unittest.TestCase):
    """Focused integration coverage for local-access fact boundary cases."""

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
        analyze_scope(
            self.root, "src", ("sparse_cfg",), database=self.database
        )
        env = query_analysis(
            self.root,
            "sparse_cfg",
            file_path=relative_path,
            database=self.database,
        )
        self.assertEqual(env["status"], "available", env.get("reason"))
        return env

    @staticmethod
    def annotations(event: dict) -> dict:
        return event.get("annotations", {})

    @staticmethod
    def fact(event: dict, key: str) -> dict:
        encoded = event.get("annotations", {}).get(key)
        if encoded is None:
            raise AssertionError(f"missing {key} on {event['event_type']}: {event}")
        value = json.loads(encoded)
        if encoded != json.dumps(value, sort_keys=True, separators=(",", ":")):
            raise AssertionError(f"non-canonical {key}: {encoded}")
        return value

    def events(self, env: dict, event_type: str, owner: str) -> list[dict]:
        return [
            event
            for event in env["events"]
            if event["event_type"] == event_type
            and event["owner_qualified_name"] == owner
        ]

    def declaration(self, env: dict, owner: str, name: str = "x") -> dict:
        matches = [
            event
            for event in self.events(env, "DECLARATION", owner)
            if event["matched_name"] == name
        ]
        self.assertEqual(len(matches), 1, (owner, name, matches))
        return matches[0]

    def local_events(
        self, env: dict, owner: str, event_type: str, name: str = "x"
    ) -> list[dict]:
        matches = []
        for event in self.events(env, event_type, owner):
            if "local_access_v1" not in self.annotations(event):
                continue
            access = self.fact(event, "local_access_v1")
            if access["direction"] == event_type and event["matched_name"] == name:
                matches.append(event)
        return matches

    def local_event(
        self, env: dict, owner: str, event_type: str, name: str = "x"
    ) -> dict:
        matches = self.local_events(env, owner, event_type, name)
        self.assertEqual(len(matches), 1, (owner, event_type, name, matches))
        return matches[0]

    def assert_linked(self, access_event: dict, declaration_event: dict) -> dict:
        access = self.fact(access_event, "local_access_v1")
        declaration = self.fact(declaration_event, "local_declaration_v1")
        self.assertEqual(access["declaration"], declaration["declaration"])
        self.assertEqual(access["target"], "direct")
        self.assertEqual(access["direction"], access_event["event_type"])
        return access

    def assert_unknown(self, event: dict, reason: str) -> dict:
        declaration = self.fact(event, "local_declaration_v1")
        self.assertEqual(declaration["coverage_status"], "unknown")
        self.assertIn(reason, declaration["coverage_reasons"])
        return declaration

    @staticmethod
    def event_identity(event: dict) -> tuple[str, int]:
        return event["event_type"], event["ordinal"]

    def evaluation_predecessor(self, event: dict) -> dict:
        position = self.fact(event, "control_position_v1")
        predecessor = position["evaluation_predecessor"]
        self.assertIsNotNone(predecessor, position)
        return predecessor

    def assert_condition_declaration(
        self, env: dict, owner: str, initializer: str
    ) -> None:
        declaration_event = self.declaration(env, owner, "x")
        declaration = self.fact(declaration_event, "local_declaration_v1")
        self.assertTrue(declaration["initialized"])
        self.assertEqual(declaration["initializer"], "expression")
        self.assertEqual(declaration["initializer_expression"], initializer)

        write = self.local_event(env, owner, "WRITE", "x")
        read = self.local_event(env, owner, "READ", "x")
        self.assert_linked(write, declaration_event)
        self.assert_linked(read, declaration_event)

        condition_declaration = self.declaration(env, owner, "c")
        condition_read = self.local_event(env, owner, "READ", "c")
        self.assert_linked(condition_read, condition_declaration)

    def test_bare_if_condition_publishes_declaration_linked_read(self) -> None:
        env = self.build(
            "int bare_condition(void) {\n"
            "    int x = 0;\n"
            "    if (x) { return 1; }\n"
            "    return 0;\n"
            "}\n"
            "int renamed_condition(void) {\n"
            "    int value = 0;\n"
            "    if\n"
            "    (\n"
            "        value\n"
            "    )\n"
            "    {\n"
            "        return 1;\n"
            "    }\n"
            "    return 0;\n"
            "}\n"
        )
        for owner, name in (
            ("bare_condition", "x"),
            ("renamed_condition", "value"),
        ):
            with self.subTest(owner=owner):
                declaration = self.declaration(env, owner, name)
                read = self.local_event(env, owner, "READ", name)
                access = self.assert_linked(read, declaration)
                self.assertEqual(access["status"], "supported")
                position = self.fact(read, "control_position_v1")
                self.assertEqual(position["status"], "reachable")
                self.assertEqual(position["coverage_status"], "complete")

    def test_short_circuit_rhs_write_is_not_entry_or_complete(self) -> None:
        env = self.build(
            "int short_circuit(int n) {\n"
            "    int x;\n"
            "    n && (x = 1);\n"
            "    return x;\n"
            "}\n"
        )
        declaration = self.declaration(env, "short_circuit")
        write = self.local_event(env, "short_circuit", "WRITE")
        # Method-wide unknown access coverage is an accepted fail-closed result.
        self.assert_linked(write, declaration)
        position = self.fact(write, "control_position_v1")
        self.assertFalse(position["entry"], position)
        self.assertNotEqual(position["coverage_status"], "complete", position)

    def test_short_circuit_rhs_dereference_has_unknown_position(self) -> None:
        env = self.build(
            "void short_circuit_dereference(int n) {\n"
            "    int *p = 0;\n"
            "    if (n && *p) { }\n"
            "}\n"
        )
        dereference = self.local_event(
            env, "short_circuit_dereference", "DEREFERENCE", "*p"
        )
        access = self.fact(dereference, "local_access_v1")
        self.assertEqual(access["coverage_status"], "unknown")
        self.assertIn("unsupported_short_circuit", access["coverage_reasons"])
        position = self.fact(dereference, "control_position_v1")
        self.assertFalse(position["entry"], position)
        self.assertEqual(position["predecessors"], [], position)
        self.assertEqual(position["status"], "unknown", position)

    def test_nested_assignment_accesses_have_evaluation_predecessors(self) -> None:
        env = self.build(
            "int nested_assignment(void) {\n"
            "    int x;\n"
            "    int y;\n"
            "    y = (x = y);\n"
            "    return 0;\n"
            "}\n"
        )
        rhs_read = self.local_event(env, "nested_assignment", "READ", "y")
        inner_write = self.local_event(env, "nested_assignment", "WRITE", "x")
        outer_write = self.local_event(env, "nested_assignment", "WRITE", "y")
        declarations = {
            name: self.declaration(env, "nested_assignment", name)
            for name in ("x", "y")
        }
        self.assert_linked(rhs_read, declarations["y"])
        self.assert_linked(inner_write, declarations["x"])
        self.assert_linked(outer_write, declarations["y"])

        # Identities, never source spans or ordinal ordering, express
        # RHS READ y -> WRITE x -> outer WRITE y. The initial RHS read may
        # legitimately begin at the method-entry position.
        self.assertIsNone(
            self.fact(rhs_read, "control_position_v1")["evaluation_predecessor"]
        )
        second = self.evaluation_predecessor(inner_write)
        self.assertEqual(
            (second["event_type"], second["ordinal"]),
            self.event_identity(rhs_read),
        )
        third = self.evaluation_predecessor(outer_write)
        self.assertEqual(
            (third["event_type"], third["ordinal"]),
            self.event_identity(inner_write),
        )

    def test_evaluation_predecessor_keeps_distinct_control_positions(self) -> None:
        env = self.build(
            "int f(void);\n"
            "int g(void);\n"
            "int independent_branches(int c, int d) {\n"
            "    int x;\n"
            "    int y;\n"
            "    if (c) { x = f(); }\n"
            "    if (d) { y = g(); }\n"
            "    return 0;\n"
            "}\n"
        )
        first = self.local_event(env, "independent_branches", "WRITE", "x")
        second = self.local_event(env, "independent_branches", "WRITE", "y")
        first_position = self.fact(first, "control_position_v1")
        second_position = self.fact(second, "control_position_v1")
        self.assertIsNone(first_position["evaluation_predecessor"])
        self.assertIsNone(second_position["evaluation_predecessor"])
        first_call = first_position["predecessors"][0]
        second_call = second_position["predecessors"][0]
        self.assertEqual((first_call["event_type"], second_call["event_type"]), ("CALL", "CALL"))
        self.assertNotEqual(first_call["ordinal"], second_call["ordinal"])
        self.assertNotEqual(first_position["predecessors"], second_position["predecessors"])

    def test_cpp_if_init_statement_publishes_heading_declaration_and_accesses(self) -> None:
        env = self.build(
            "int if_init_statement(void) {\n"
            "    int c = 1;\n"
            "    if (int x = 1; c) { return x; }\n"
            "    return 0;\n"
            "}\n",
            relative_path="src/facts.cpp",
        )
        self.assert_condition_declaration(env, "if_init_statement", "1")

    def test_cpp_new_constructor_pointer_arguments_fail_closed(self) -> None:
        env = self.build(
            "struct B { B(int *); };\n"
            "void new_address(void) {\n"
            "    int x;\n"
            "    new B(&x);\n"
            "}\n"
            "void new_pointer(void) {\n"
            "    int x;\n"
            "    int *p = &x;\n"
            "    new B(p);\n"
            "}\n",
            relative_path="src/facts.cpp",
        )
        for owner in ("new_address", "new_pointer"):
            with self.subTest(owner=owner):
                self.assert_unknown(
                    self.declaration(env, owner, "x"), "unknown_write_through"
                )

    def test_c_sizeof_operands_publish_no_v1_accesses(self) -> None:
        env = self.build(
            "int sizeof_assignment(void) {\n"
            "    int x;\n"
            "    return (int)sizeof(x = 1);\n"
            "}\n"
            "int renamed_sizeof_assignment(void) {\n"
            "    int value;\n"
            "    return (int) sizeof\n"
            "    (\n"
            "        value = 1\n"
            "    );\n"
            "}\n"
            "int sizeof_read(void) {\n"
            "    int x;\n"
            "    return (int)sizeof(x);\n"
            "}\n"
        )
        actual = {
            (owner, event_type): [
                event["event_id"]
                for event in self.local_events(env, owner, event_type, name)
            ]
            for owner, name in (
                ("sizeof_assignment", "x"),
                ("renamed_sizeof_assignment", "value"),
                ("sizeof_read", "x"),
            )
            for event_type in ("READ", "WRITE")
        }
        self.assertEqual(actual, {key: [] for key in actual})

    def test_c_sizeof_vla_bound_evaluation_boundary(self) -> None:
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
            "int sizeof_parenthesized_vla(void) {\n"
            "    int n = 2;\n"
            "    return (int)sizeof(int ([n]));\n"
            "}\n"
            "int sizeof_parenthesized_vla_of_pointers(void) {\n"
            "    int n = 2;\n"
            "    return (int)sizeof(int (*[n]));\n"
            "}\n"
            "int sizeof_vla_of_function_pointers(void) {\n"
            "    int n = 2;\n"
            "    return (int)sizeof(int (*[n])(void));\n"
            "}\n"
        )
        for owner, expected_reads in (
            ("sizeof_vla_bound", 1),
            ("nested_sizeof_vla_bound", 0),
            ("evaluated_nested_sizeof_vla_bound", 1),
            ("sizeof_pointer_to_vla", 0),
            ("sizeof_vla_of_pointers", 1),
            ("sizeof_parenthesized_vla", 1),
            ("sizeof_parenthesized_vla_of_pointers", 1),
            ("sizeof_vla_of_function_pointers", 1),
        ):
            with self.subTest(owner=owner):
                declaration = self.declaration(env, owner, "n")
                reads = self.local_events(env, owner, "READ", "n")
                self.assertEqual(len(reads), expected_reads, reads)
                for read in reads:
                    access = self.assert_linked(read, declaration)
                    self.assertEqual(access["status"], "supported")
                    self.assertEqual(access["coverage_status"], "complete")

    def test_cpp_unevaluated_operands_publish_no_v1_accesses(self) -> None:
        env = self.build(
            "int alignof_operand(void) {\n"
            "    int x;\n"
            "    return (int)alignof(decltype(x = 1));\n"
            "}\n"
            "int decltype_operand(void) {\n"
            "    int x;\n"
            "    using T = decltype(x = 1);\n"
            "    return (int)sizeof(T);\n"
            "}\n"
            "int noexcept_operand(void) {\n"
            "    int x;\n"
            "    return noexcept(x = 1) ? 0 : 1;\n"
            "}\n"
            "int requires_operand(void) {\n"
            "    int x;\n"
            "    bool b = requires { x = 1; };\n"
            "    return b ? 0 : 1;\n"
            "}\n",
            relative_path="src/facts.cpp",
        )
        actual = {
            (owner, event_type): [
                event["event_id"]
                for event in self.local_events(env, owner, event_type)
            ]
            for owner in (
                "alignof_operand",
                "decltype_operand",
                "noexcept_operand",
                "requires_operand",
            )
            for event_type in ("READ", "WRITE")
        }
        self.assertEqual(actual, {key: [] for key in actual})

    def test_unevaluated_legacy_pointer_writes_publish_no_events(self) -> None:
        env = self.build(
            "void legacy_unevaluated_writes(void) {\n"
            "    int *p = nullptr;\n"
            "    int *q = nullptr;\n"
            "    sizeof(q = p);\n"
            "    sizeof(p = nullptr);\n"
            "}\n",
            relative_path="src/facts.cpp",
        )
        writes = self.events(env, "WRITE", "legacy_unevaluated_writes")
        alias = [
            event for event in writes
            if self.annotations(event).get("alias_source") == "p"
            and event["matched_name"] == "q"
        ]
        self.assertEqual(alias, [])
        # Only the declaration initializer is a runtime null write. The same
        # spelling inside sizeof is not evaluated and publishes no event.
        null = [
            event for event in writes
            if self.annotations(event).get("null_source") == "true"
            and event["matched_name"] == "p"
        ]
        self.assertEqual(len(null), 1, writes)
        # The declaration initializer is a real runtime write and keeps its V1
        # local-access fact; the same spelling inside sizeof is gone.
        self.assertIn("local_access_v1", self.annotations(null[0]))
        self.assertEqual(self.annotations(null[0]).get("subject_storage"), "local")

    def test_cpp_condition_declaration_publishes_initializer_and_accesses(self) -> None:
        env = self.build(
            "int condition_declaration(void) {\n"
            "    int c = 1;\n"
            "    if (int x = c) { return x; }\n"
            "    return 0;\n"
            "}\n",
            relative_path="src/facts.cpp",
        )
        self.assert_condition_declaration(env, "condition_declaration", "c")

    def test_cpp_range_for_keeps_unresolved_declaration_and_read_facts(self) -> None:
        env = self.build(
            "void use(int);\n"
            "void range_for(void) {\n"
            "    int values[2] = {1, 2};\n"
            "    for (int x : values) { use(x); }\n"
            "}\n",
            relative_path="src/facts.cpp",
        )
        declaration_event = self.declaration(env, "range_for", "x")
        declaration = self.assert_unknown(declaration_event, "unsupported_loop")
        self.assertEqual(declaration["status"], "unsupported")
        self.assertEqual(declaration["declaration"], "")
        self.assertIn("unresolved_declaration", declaration["coverage_reasons"])
        reads = self.local_events(env, "range_for", "READ", "x")
        self.assertGreaterEqual(len(reads), 1)
        for read in reads:
            access = self.assert_linked(read, declaration_event)
            self.assertEqual(access["status"], "unsupported")
            self.assertEqual(access["declaration"], "")
            self.assertEqual(access["coverage_status"], "unknown")
            self.assertIn("unsupported_loop", access["coverage_reasons"])
            self.assertIn("unresolved_declaration", access["coverage_reasons"])
            position = self.fact(read, "control_position_v1")
            self.assertEqual(position["status"], "unknown")

    def test_cpp_range_for_bare_condition_keeps_unresolved_read(self) -> None:
        env = self.build(
            "void range_for_bare_condition(void) {\n"
            "    int values[1] = {};\n"
            "    for (int x : values) { if (x) { } }\n"
            "}\n",
            relative_path="src/facts.cpp",
        )
        declaration = self.declaration(env, "range_for_bare_condition", "x")
        read = self.local_event(env, "range_for_bare_condition", "READ", "x")
        access = self.assert_linked(read, declaration)
        self.assertEqual(access["status"], "unsupported")
        self.assertEqual(access["declaration"], "")
        self.assertEqual(access["coverage_status"], "unknown")
        self.assertIn("unsupported_loop", access["coverage_reasons"])
        self.assertIn("unresolved_declaration", access["coverage_reasons"])
        position = self.fact(read, "control_position_v1")
        self.assertEqual(position["status"], "unknown")
        self.assertFalse(position["entry"])

    def test_cpp_range_for_keeps_nested_shadow_declaration_identity(self) -> None:
        env = self.build(
            "void use(int);\n"
            "void range_for_shadow(void) {\n"
            "    int values[1] = {};\n"
            "    for (int x : values) {\n"
            "        { int x = 7; use(x); }\n"
            "    }\n"
            "}\n",
            relative_path="src/facts.cpp",
        )
        declarations = [
            event for event in self.events(env, "DECLARATION", "range_for_shadow")
            if event["matched_name"] == "x"
        ]
        self.assertEqual(len(declarations), 2, declarations)
        unresolved = [
            event for event in declarations
            if not self.fact(event, "local_declaration_v1")["declaration"]
        ]
        resolved = [
            event for event in declarations
            if self.fact(event, "local_declaration_v1")["declaration"]
        ]
        self.assertEqual(len(unresolved), 1, declarations)
        self.assertEqual(len(resolved), 1, declarations)
        read = self.local_event(env, "range_for_shadow", "READ", "x")
        access = self.assert_linked(read, resolved[0])
        self.assertEqual(access["status"], "supported")
        self.assertNotEqual(
            access["declaration"],
            self.fact(unresolved[0], "local_declaration_v1")["declaration"],
        )


if __name__ == "__main__":
    unittest.main()

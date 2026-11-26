from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from provenlattice.analysis_query import query_analysis
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


FIXTURE = r"""#define MACRO_VALUE 1
void unknown_write(void *);
int uninitialized(void) {
    int x;
    return x;
}
int initialized(void) {
    int x = 1;
    return x;
}
int assigned(void) {
    int x;
    x = 1;
    return x;
}
int both_branches(int c) {
    int x;
    if (c) { x = 1; } else { x = 2; }
    return x;
}
int one_branch(int c) {
    int x;
    if (c) { x = 1; }
    return x;
}
int early_return(int c) {
    int x;
    if (c) { return 0; }
    x = 1;
    return x;
}
int shadowed(void) {
    int x = 0;
    { int x; return x; }
}
int pointer_dereference(void) {
    int *p;
    *p = 1;
    return 0;
}
int macro_use(void) {
    int x;
    x = MACRO_VALUE;
    return x;
}
int goto_use(int c) {
    int x;
    if (c) { goto done; }
    x = 1;
done:
    return x;
}
int loop_use(int c) {
    int x = 0;
    while (c) { x = 1; c = 0; }
    return x;
}
int unknown_write_through(void) {
    int x;
    unknown_write(&x);
    return x;
}
int unknown_pointer_argument(void) {
    int x;
    int *p = &x;
    unknown_write(p);
    return x;
}
int unreachable_after_return(void) {
    int x;
    return 0;
    x = 1;
    return x;
}
int switch_use(int c) {
    int x = 0;
    switch (c) { case 1: x = 1; break; default: x = 2; }
    return x;
}
int conditional_use(int c) {
    int x = 0;
    c ? x = 1 : x = 2;
    return x;
}
int function_pointer_call(void) {
    int (*fp)(void);
    fp();
    return 0;
}
int storage_and_unsupported(void) {
    static int s;
    int array[2];
    struct Box { int value; } box;
    return s;
}
"""


class LocalDeclarationAccessFactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.database = Path(self.temp.name) / "graph.db"
        self.relative_path = "src/facts.c"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(
        self, source: str = FIXTURE, features=("sparse_cfg",),
        relative_path: str = "src/facts.c",
    ) -> dict:
        self.relative_path = relative_path
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", features, database=self.database)
        return self.env()

    def env(self) -> dict:
        env = query_analysis(
            self.root, "sparse_cfg", file_path=self.relative_path, database=self.database
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
            event for event in env["events"]
            if event["event_type"] == event_type
            and event["owner_qualified_name"] == owner
        ]

    def declaration(self, env: dict, owner: str, name: str = "x") -> dict:
        matches = [
            event for event in self.events(env, "DECLARATION", owner)
            if event["matched_name"] == name
        ]
        self.assertEqual(len(matches), 1, (owner, name, matches))
        return matches[0]

    def local_events(self, env: dict, owner: str, event_type: str, name: str = "x") -> list[dict]:
        matches = []
        for event in self.events(env, event_type, owner):
            if "local_access_v1" not in self.annotations(event):
                continue
            access = self.fact(event, "local_access_v1")
            if access["direction"] == event_type and event["matched_name"] == name:
                matches.append(event)
        return matches

    def assert_complete(self, event: dict) -> dict:
        declaration = self.fact(event, "local_declaration_v1")
        self.assertEqual(declaration["coverage_status"], "complete")
        self.assertEqual(declaration["coverage_reasons"], [])
        return declaration

    def assert_unknown(self, event: dict, reason: str) -> dict:
        declaration = self.fact(event, "local_declaration_v1")
        self.assertEqual(declaration["coverage_status"], "unknown")
        self.assertIn(reason, declaration["coverage_reasons"])
        return declaration

    def test_declaration_initializer_and_direct_access_goldens(self) -> None:
        env = self.build()
        uninitialized = self.assert_complete(self.declaration(env, "uninitialized"))
        initialized = self.assert_complete(self.declaration(env, "initialized"))
        assigned = self.assert_complete(self.declaration(env, "assigned"))
        self.assertFalse(uninitialized["initialized"])
        self.assertTrue(initialized["initialized"])
        self.assertFalse(assigned["initialized"])
        for declaration in (uninitialized, initialized, assigned):
            self.assertEqual(declaration["status"], "supported")
            self.assertEqual(declaration["kind"], "scalar")
            self.assertEqual(declaration["storage_class"], "automatic")
            self.assertTrue(declaration["declaration"].startswith("local:src/facts.c:"))

        self.assertEqual(self.local_events(env, "uninitialized", "WRITE"), [])
        self.assertEqual(len(self.local_events(env, "uninitialized", "READ")), 1)
        self.assertEqual(len(self.local_events(env, "initialized", "WRITE")), 1)
        self.assertEqual(len(self.local_events(env, "assigned", "WRITE")), 1)
        for owner in ("uninitialized", "initialized", "assigned"):
            declaration = self.declaration(env, owner)
            declaration_id = self.fact(declaration, "local_declaration_v1")["declaration"]
            for event_type in ("READ", "WRITE"):
                for access in self.local_events(env, owner, event_type):
                    fact = self.fact(access, "local_access_v1")
                    self.assertEqual(fact["declaration"], declaration_id)
                    self.assertEqual(fact["target"], "direct")
                    self.assertEqual(fact["status"], "supported")
                    self.assertNotIn("subject", self.annotations(access))

    def test_if_else_and_single_branch_positions_are_distinguishable(self) -> None:
        env = self.build()
        both_writes = self.local_events(env, "both_branches", "WRITE")
        self.assertEqual(len(both_writes), 2)
        both_flags = {
            tuple(self.fact(event, "control_position_v1")["predecessors"][0]["flags"])
            for event in both_writes
        }
        self.assertEqual(both_flags, {("branch=true",), ("branch=false",)})

        one_write = self.local_events(env, "one_branch", "WRITE")
        self.assertEqual(len(one_write), 1)
        write_position = self.fact(one_write[0], "control_position_v1")
        self.assertEqual(write_position["predecessors"][0]["flags"], ["branch=true"])
        read = self.local_events(env, "one_branch", "READ")[0]
        read_position = self.fact(read, "control_position_v1")
        self.assertEqual(
            {tuple(item["flags"]) for item in read_position["predecessors"]},
            {("branch=true",), ("branch=false",)},
        )

        published = {
            (event["event_type"], event["ordinal"])
            for event in self.events(env, "BRANCH", "one_branch")
        }
        for predecessor in read_position["predecessors"]:
            self.assertIn(
                (predecessor["event_type"], predecessor["ordinal"]), published
            )

    def test_early_return_removes_unreachable_assignment_path(self) -> None:
        env = self.build()
        write = self.local_events(env, "early_return", "WRITE")[0]
        read = self.local_events(env, "early_return", "READ")[0]
        for event in (write, read):
            position = self.fact(event, "control_position_v1")
            self.assertEqual(position["status"], "reachable")
            self.assertEqual(len(position["predecessors"]), 1)
            self.assertEqual(position["predecessors"][0]["flags"], ["branch=false"])

    def test_shadowed_locals_use_declaration_identity_not_spelling(self) -> None:
        env = self.build()
        declarations = self.events(env, "DECLARATION", "shadowed")
        self.assertEqual(len(declarations), 2)
        identities = {
            self.fact(event, "local_declaration_v1")["declaration"]
            for event in declarations
        }
        self.assertEqual(len(identities), 2)
        read = self.local_events(env, "shadowed", "READ")[0]
        read_identity = self.fact(read, "local_access_v1")["declaration"]
        inner = max(
            identities,
            key=lambda identity: int(identity.rsplit(":", 1)[1]),
        )
        self.assertEqual(read_identity, inner)

    def test_local_dereference_is_fact_but_write_through_is_unknown(self) -> None:
        env = self.build()
        declaration = self.declaration(env, "pointer_dereference", "p")
        self.assert_unknown(declaration, "unknown_write_through")
        dereference = self.events(env, "DEREFERENCE", "pointer_dereference")
        self.assertEqual(len(dereference), 1)
        access = self.fact(dereference[0], "local_access_v1")
        self.assertEqual(access["direction"], "DEREFERENCE")
        self.assertEqual(access["status"], "supported")
        self.assertEqual(
            access["declaration"],
            self.fact(declaration, "local_declaration_v1")["declaration"],
        )
        # A DEREFERENCE is already a threaded control point. New local
        # READ/WRITE/DECLARATION facts must remain off all existing CFG edges.
        local_edgeless = [
            event for event in env["events"]
            if event["event_type"] == "DECLARATION"
            or "local_access_v1" in self.annotations(event)
            and event["event_type"] in {"READ", "WRITE"}
        ]
        edgeless_ids = {event["event_id"] for event in local_edgeless}
        self.assertTrue(edgeless_ids)
        for edge in env["edges"]:
            self.assertNotIn(edge["src_id"], edgeless_ids)
            self.assertNotIn(edge["dst_id"], edgeless_ids)

    def test_local_function_pointer_callee_is_a_read(self) -> None:
        env = self.build()
        declaration = self.assert_complete(self.declaration(env, "function_pointer_call", "fp"))
        self.assertEqual(declaration["kind"], "pointer")
        reads = self.local_events(env, "function_pointer_call", "READ", "fp")
        self.assertEqual(len(reads), 1)
        access = self.fact(reads[0], "local_access_v1")
        self.assertEqual(access["status"], "supported")
        self.assertEqual(access["declaration"], declaration["declaration"])
        self.assertEqual(reads[0]["annotations"].get("is_indirect"), "true")

    def test_macro_goto_loop_and_unknown_call_coverage(self) -> None:
        env = self.build()
        self.assert_unknown(self.declaration(env, "macro_use"), "macro")
        self.assert_unknown(self.declaration(env, "goto_use"), "goto")
        self.assert_unknown(self.declaration(env, "loop_use"), "unsupported_loop")
        self.assert_unknown(
            self.declaration(env, "unknown_write_through"), "unknown_write_through"
        )
        self.assert_unknown(
            self.declaration(env, "unknown_pointer_argument"), "unknown_write_through"
        )
        self.assert_unknown(
            self.declaration(env, "switch_use"), "unsupported_conditional"
        )
        self.assert_unknown(
            self.declaration(env, "conditional_use"), "unsupported_conditional"
        )
        for owner in ("macro_use", "goto_use", "loop_use", "unknown_write_through"):
            read = self.local_events(env, owner, "READ")[0]
            self.assertEqual(self.fact(read, "local_access_v1")["coverage_status"], "unknown")
            self.assertEqual(self.fact(read, "control_position_v1")["status"], "unknown")

    def test_unreachable_is_distinct_from_unknown_coverage(self) -> None:
        env = self.build()
        declaration = self.assert_complete(self.declaration(env, "unreachable_after_return"))
        self.assertEqual(declaration["coverage_reasons"], [])
        for event_type in ("WRITE", "READ"):
            access = self.local_events(env, "unreachable_after_return", event_type)[0]
            position = self.fact(access, "control_position_v1")
            self.assertEqual(position["status"], "unreachable")
            self.assertEqual(position["coverage_status"], "complete")
            self.assertFalse(position["entry"])
            self.assertEqual(position["predecessors"], [])

    def test_partial_parse_is_explicit_unknown(self) -> None:
        env = self.build("int broken(void) { int x; x = ; return x; }\n")
        declaration = self.declaration(env, "broken")
        self.assert_unknown(declaration, "partial_parse")
        self.assertEqual(env["coverage"]["analysis_status"], "degraded")

    def test_static_zero_initialization_and_unsupported_objects(self) -> None:
        env = self.build()
        static = self.assert_complete(
            self.declaration(env, "storage_and_unsupported", "s")
        )
        self.assertEqual(static["storage_class"], "static")
        self.assertTrue(static["initialized"])
        self.assertTrue(static["zero_initialized"])
        static_read = self.local_events(env, "storage_and_unsupported", "READ", "s")[0]
        static_access = self.fact(static_read, "local_access_v1")
        self.assertEqual(static_access["declaration"], static["declaration"])
        self.assertEqual(static_access["status"], "supported")
        self.assertIn("subject", static_read["annotations"])
        self.assertEqual(
            self.fact(static_read, "control_position_v1")["coverage_status"],
            "complete",
        )
        array = self.fact(
            self.declaration(env, "storage_and_unsupported", "array"),
            "local_declaration_v1",
        )
        box = self.fact(
            self.declaration(env, "storage_and_unsupported", "box"),
            "local_declaration_v1",
        )
        self.assertEqual(array["status"], "unsupported")
        self.assertEqual(box["status"], "unsupported")

    def test_static_declarator_names_keep_only_legacy_reads(self) -> None:
        env = self.build(
            "void f(void) {\n"
            "    static int *p;\n"
            "    static int (*fp)(void);\n"
            "}\n"
        )
        for name in ("p", "fp"):
            self.assert_complete(self.declaration(env, "f", name))
            reads = [
                event for event in self.events(env, "READ", "f")
                if event["matched_name"] == name
            ]
            self.assertEqual(len(reads), 1)
            self.assertIn("subject", reads[0]["annotations"])
            self.assertNotIn("local_access_v1", reads[0]["annotations"])
            self.assertNotIn("control_position_v1", reads[0]["annotations"])
            self.assertEqual(self.local_events(env, "f", "READ", name), [])

    def test_reference_and_constructor_write_through_are_unknown(self) -> None:
        env = self.build(
            "struct B { B(int *); };\n"
            "int reference_write(void) {\n"
            "    int x;\n"
            "    int &r = x;\n"
            "    r = 1;\n"
            "    return x;\n"
            "}\n"
            "int constructor_address(void) {\n"
            "    int x;\n"
            "    B b(&x);\n"
            "    return x;\n"
            "}\n"
            "int constructor_brace(void) {\n"
            "    int x;\n"
            "    B b{&x};\n"
            "    return x;\n"
            "}\n"
            "int constructor_pointer(void) {\n"
            "    int x;\n"
            "    int *p = &x;\n"
            "    B b(p);\n"
            "    return x;\n"
            "}\n",
            relative_path="src/facts.cpp",
        )
        for owner in (
            "reference_write", "constructor_address", "constructor_brace",
            "constructor_pointer",
        ):
            declaration = self.assert_unknown(
                self.declaration(env, owner, "x"), "unknown_write_through"
            )
            read = self.local_events(env, owner, "READ", "x")[0]
            access = self.fact(read, "local_access_v1")
            self.assertEqual(access["declaration"], declaration["declaration"])
            self.assertEqual(access["coverage_status"], "unknown")
        reference = self.fact(
            self.declaration(env, "reference_write", "r"), "local_declaration_v1"
        )
        self.assertEqual(reference["status"], "unsupported")

    def test_cpp_initialization_forms_and_lambda_coverage(self) -> None:
        env = self.build(
            "struct Box { int value; };\n"
            "void cpp_forms(void) {\n"
            "    int direct(1);\n"
            "    int empty{};\n"
            "    int braces{1};\n"
            "    int assigned = 2;\n"
            "    thread_local int tls;\n"
            "    int prototype(void);\n"
            "    Box box;\n"
            "    [&] { direct = 2; }();\n"
            "}\n",
            relative_path="src/facts.cpp",
        )
        direct = self.fact(
            self.declaration(env, "cpp_forms", "direct"), "local_declaration_v1"
        )
        empty = self.fact(
            self.declaration(env, "cpp_forms", "empty"), "local_declaration_v1"
        )
        braces = self.fact(
            self.declaration(env, "cpp_forms", "braces"), "local_declaration_v1"
        )
        assigned = self.fact(
            self.declaration(env, "cpp_forms", "assigned"), "local_declaration_v1"
        )
        box = self.fact(
            self.declaration(env, "cpp_forms", "box"), "local_declaration_v1"
        )
        tls = self.fact(
            self.declaration(env, "cpp_forms", "tls"), "local_declaration_v1"
        )
        for fact in (direct, braces, assigned):
            self.assertTrue(fact["initialized"])
            self.assertEqual(fact["initializer"], "expression")
            self.assertFalse(fact["zero_initialized"])
            self.assertIsNotNone(fact["initializer_expression"])
            self.assertIsNotNone(fact["initializer_start_byte"])
        self.assertTrue(empty["initialized"])
        self.assertTrue(empty["zero_initialized"])
        self.assertEqual(empty["initializer"], "zero_initialized")
        self.assertEqual(box["status"], "unsupported")
        self.assertIsNone(box["initialized"])
        self.assertEqual(box["initializer"], "unknown")
        self.assertEqual(tls["storage_class"], "thread_local")
        self.assertTrue(tls["initialized"])
        self.assertTrue(tls["zero_initialized"])
        self.assertIn("unsupported_lambda", direct["coverage_reasons"])
        self.assertEqual(
            {event["matched_name"] for event in self.events(env, "DECLARATION", "cpp_forms")},
            {"direct", "empty", "braces", "assigned", "tls", "box"},
        )

    def test_default_index_does_not_materialize_local_facts(self) -> None:
        path = self.root / "src/facts.c"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("int f(void) { int x; return x; }\n", encoding="utf-8")
        full_index(self.root, self.database)
        missing = query_analysis(
            self.root, "sparse_cfg", file_path="src/facts.c", database=self.database
        )
        self.assertEqual(missing["status"], "not_built")
        with closing(sqlite3.connect(self.database)) as connection:
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_nodes'"
            ).fetchone()
            count = 0 if table is None else connection.execute(
                "SELECT COUNT(*) FROM analysis_nodes WHERE feature='sparse_cfg:cpp'"
            ).fetchone()[0]
        self.assertEqual(count, 0)
        analyze_scope(self.root, "src", ("sparse_cfg",), database=self.database)
        self.assertEqual(len(self.events(self.env(), "DECLARATION", "f")), 1)

    def test_rematerialization_is_byte_stable_and_old_version_is_stale(self) -> None:
        first = self.build()
        canonical = json.dumps(first["events"], sort_keys=True, separators=(",", ":"))
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "UPDATE analysis_state SET feature_version=9 WHERE feature='sparse_cfg:cpp'"
            )
            connection.commit()
        stale = query_analysis(
            self.root, "sparse_cfg", file_path="src/facts.c", database=self.database
        )
        self.assertEqual(stale["status"], "stale")
        analyze_scope(self.root, "src", ("sparse_cfg",), database=self.database)
        second = self.env()
        self.assertEqual(
            json.dumps(second["events"], sort_keys=True, separators=(",", ":")),
            canonical,
        )


if __name__ == "__main__":
    unittest.main()

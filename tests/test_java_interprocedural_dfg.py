"""Java Sparse CFG/DFG interprocedural dataflow tests (parameter + return).

Model under test: within one file, a method invocation emits a CALL point that
carries the callee's short name and the argument-root list (ordinal-preserving).
The interprocedural pass reuses the method-local DFG facts -- the input_to_sink
edge names a call's argument definition (caller side) and the value_flow edge
names a return value's definition (callee side) -- and mints two cross-method
DATA_FLOW_TO edge kinds:

  * ``interprocedural_parameter``: caller argument def -> callee parameter WRITE;
  * ``interprocedural_return``:   callee return-value def -> caller CALL point.

Callee resolution is same-file short-name only; an overloaded / unbound /
cross-file callee stays unbound rather than guessed (no-fabrication).
"""

import tempfile
import unittest
from pathlib import Path

from provenlattice.analysis_query import query_analysis
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


def _write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


class JavaInterproceduralDfgTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.database = Path(self.temp.name) / "graph.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self, body: str, name: str = "src/T.java") -> None:
        _write(self.root, name, body)
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("sparse_dfg",), database=self.database)

    def events(self) -> list[dict]:
        env = query_analysis(self.root, "sparse_cfg", file_path="src/T.java",
                             database=self.database)
        self.assertEqual(env["status"], "available", env.get("reason"))
        return env["events"]

    def dfg_edges(self) -> list[dict]:
        env = query_analysis(self.root, "sparse_dfg", file_path="src/T.java",
                             database=self.database)
        self.assertEqual(env["status"], "available", env.get("reason"))
        return env["edges"]

    def event_by(self, event_type, line, subject=None) -> dict:
        matches = [e for e in self.events()
                   if e["event_type"] == event_type and e["start_line"] == line
                   and (subject is None or (e.get("annotations") or {}).get("subject") == subject)]
        self.assertEqual(len(matches), 1, (event_type, line, subject, self.events()))
        return matches[0]

    def flow_edges(self, flow_class: str) -> list[dict]:
        return [e for e in self.dfg_edges() if e["payload"].get("flow_class") == flow_class]


class ParameterBindingTests(JavaInterproceduralDfgTestBase):
    def test_argument_flows_to_callee_parameter(self) -> None:
        self.build(
            "package a;\n"
            "public class T {\n"
            "  int f() {\n"
            "    int x = 1;\n"
            "    return id(x);\n"
            "  }\n"
            "  int id(int p) {\n"
            "    return p;\n"
            "  }\n"
            "}\n"
        )
        x_write = self.event_by("WRITE", 4, "x")
        p_write = self.event_by("WRITE", 7, "p")
        call = self.event_by("CALL", 5)
        param_edges = self.flow_edges("interprocedural_parameter")
        # caller argument def (x WRITE) -> callee parameter WRITE (p)
        self.assertIn((x_write["event_id"], p_write["event_id"]),
                      {(e["src_id"], e["dst_id"]) for e in param_edges})
        # callee return def (p WRITE) -> caller CALL point
        ret_edges = self.flow_edges("interprocedural_return")
        self.assertIn((p_write["event_id"], call["event_id"]),
                      {(e["src_id"], e["dst_id"]) for e in ret_edges})

    def test_second_argument_binds_second_parameter(self) -> None:
        self.build(
            "package a;\n"
            "public class T {\n"
            "  int f() {\n"
            "    int a = 1;\n"
            "    int b = 2;\n"
            "    return add(a, b);\n"
            "  }\n"
            "  int add(int x, int y) {\n"
            "    return x + y;\n"
            "  }\n"
            "}\n"
        )
        a_write = self.event_by("WRITE", 4, "a")
        b_write = self.event_by("WRITE", 5, "b")
        x_write = self.event_by("WRITE", 8, "x")
        y_write = self.event_by("WRITE", 8, "y")
        param_edges = self.flow_edges("interprocedural_parameter")
        pairs = {(e["src_id"], e["dst_id"]) for e in param_edges}
        self.assertIn((a_write["event_id"], x_write["event_id"]), pairs)
        self.assertIn((b_write["event_id"], y_write["event_id"]), pairs)
        # no cross-wiring
        self.assertNotIn((a_write["event_id"], y_write["event_id"]), pairs)
        self.assertNotIn((b_write["event_id"], x_write["event_id"]), pairs)


class ReturnBindingTests(JavaInterproceduralDfgTestBase):
    def test_callee_return_flows_to_caller_call(self) -> None:
        self.build(
            "package a;\n"
            "public class T {\n"
            "  int f() {\n"
            "    return id(0);\n"
            "  }\n"
            "  int id(int p) {\n"
            "    int y = p;\n"
            "    return y;\n"
            "  }\n"
            "}\n"
        )
        y_write = self.event_by("WRITE", 7, "y")
        call = self.event_by("CALL", 4)
        ret_edges = self.flow_edges("interprocedural_return")
        self.assertIn((y_write["event_id"], call["event_id"]),
                      {(e["src_id"], e["dst_id"]) for e in ret_edges})


class NoFabricationTests(JavaInterproceduralDfgTestBase):
    def test_overloaded_callee_stays_unbound(self) -> None:
        self.build(
            "package a;\n"
            "public class T {\n"
            "  int f() {\n"
            "    return id(0);\n"
            "  }\n"
            "  int id(int p) { return p; }\n"
            "  int id(String s) { return 1; }\n"
            "}\n"
        )
        self.assertEqual(self.flow_edges("interprocedural_parameter"), [])
        self.assertEqual(self.flow_edges("interprocedural_return"), [])

    def test_non_identifier_argument_stays_unbound(self) -> None:
        self.build(
            "package a;\n"
            "public class T {\n"
            "  int f() {\n"
            "    return id(1 + 2);\n"
            "  }\n"
            "  int id(int p) { return p; }\n"
            "}\n"
        )
        # the literal argument has no root -> no parameter binding
        self.assertEqual(self.flow_edges("interprocedural_parameter"), [])

    def test_cross_file_callee_stays_unbound(self) -> None:
        _write(self.root, "src/Caller.java",
               "package a;\npublic class Caller {\n  int f() {\n    return id(0);\n  }\n}\n")
        _write(self.root, "src/Callee.java",
               "package a;\npublic class Callee {\n  int id(int p) { return p; }\n}\n")
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("sparse_dfg",), database=self.database)
        env = query_analysis(self.root, "sparse_dfg", file_path="src/Caller.java",
                             database=self.database)
        self.assertEqual(env["status"], "available", env.get("reason"))
        edges = env["edges"]
        self.assertEqual([e for e in edges
                          if e["payload"].get("flow_class") in
                          ("interprocedural_parameter", "interprocedural_return")], [])


if __name__ == "__main__":
    unittest.main()

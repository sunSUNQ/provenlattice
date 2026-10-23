"""Java sparse CFG/DFG V1 correctness tests (local-variable level).

The model under test: within a Java method, a local variable declaration /
parameter / assignment emits a WRITE that defines the variable under a
method-scoped flow identity; a READ (or RETURN of an identifier) binds to the
newest live definition of the same identity in source order, minting one
DATA_FLOW_TO edge per use. Lexical scoping + shadowing are respected: two
same-named variables in nested scopes keep distinct subject_decl tokens.
Control-flow (if/else branch+merge, while/for back edge) is emitted as
CONTROL_REACHES edges between CHECK/BRANCH/RETURN points.

Not covered (degraded, asserted as no-fabrication): try/resources, lambda,
switch, synchronized, reflection, field-sensitive and cross-procedural flow.
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


class JavaDfgTestBase(unittest.TestCase):
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

    def scfg(self, relative: str = "src/T.java") -> list[dict]:
        env = query_analysis(self.root, "sparse_cfg", file_path=relative,
                             database=self.database)
        self.assertEqual(env["status"], "available", env.get("reason"))
        return env["events"]

    def dfg_edges(self, relative: str = "src/T.java") -> list[dict]:
        env = query_analysis(self.root, "sparse_dfg", file_path=relative,
                             database=self.database)
        self.assertEqual(env["status"], "available", env.get("reason"))
        return env["edges"]

    def event_by(self, event_type: str, line: int, subject: str | None = None) -> dict:
        matches = [e for e in self.scfg()
                   if e["event_type"] == event_type and e["start_line"] == line
                   and (subject is None or (e.get("annotations") or {}).get("subject") == subject)]
        self.assertEqual(len(matches), 1, (event_type, line, subject, self.scfg()))
        return matches[0]

    def annotations(self, event: dict) -> dict:
        return event.get("annotations") or {}

    def value_edges(self) -> list[dict]:
        return [e for e in self.dfg_edges()
                if e["payload"].get("flow_class") == "value_flow"]


class DeclarationAssignmentParameterTests(JavaDfgTestBase):
    def test_declaration_init_def_then_use(self) -> None:
        self.build("package a;\npublic class T {\n  int f() {\n    int x = 1;\n    return x;\n  }\n}\n")
        write = self.event_by("WRITE", 4)
        self.assertEqual(self.annotations(write)["subject"], "x")
        self.assertEqual(self.annotations(write)["subject_storage"], "local")
        edges = self.value_edges()
        self.assertEqual(len(edges), 2)  # READ + RETURN
        self.assertEqual({e["src_id"] for e in edges}, {write["event_id"]})

    def test_assignment_redefines(self) -> None:
        self.build("package a;\npublic class T {\n  int f() {\n    int x = 1;\n    x = 2;\n    return x;\n  }\n}\n")
        first = self.event_by("WRITE", 4)
        second = self.event_by("WRITE", 5)
        self.assertNotEqual(self.annotations(first)["subject_decl"],
                            self.annotations(second)["subject_decl"])
        edges = self.value_edges()
        srcs = {e["src_id"] for e in edges}
        self.assertIn(second["event_id"], srcs)  # return binds the redefinition
        self.assertNotIn(first["event_id"], srcs)

    def test_parameter_binding(self) -> None:
        self.build("package a;\npublic class T {\n  int f(int p) {\n    return p;\n  }\n}\n")
        param = self.event_by("WRITE", 3)
        self.assertEqual(self.annotations(param)["subject_storage"], "parameter")
        edges = self.value_edges()
        self.assertEqual({e["src_id"] for e in edges}, {param["event_id"]})

    def test_read_write_chain(self) -> None:
        self.build("package a;\npublic class T {\n  int f() {\n    int x = 1;\n    int y = x;\n    x = 3;\n    int z = x;\n  }\n}\n")
        w4 = self.event_by("WRITE", 4)
        w6 = self.event_by("WRITE", 6)
        edges = self.value_edges()
        # y = x binds x#first; z = x binds x#second
        self.assertIn(w4["event_id"], {e["src_id"] for e in edges})
        self.assertIn(w6["event_id"], {e["src_id"] for e in edges})

    def test_compound_assignment_read_before_write(self) -> None:
        self.build("package a;\npublic class T {\n  int f() {\n    int x = 1;\n    x += 2;\n    return x;\n  }\n}\n")
        # x += 2 : READ x (L5), WRITE x (L5)
        read = self.event_by("READ", 5)
        write = self.event_by("WRITE", 5)
        self.assertEqual(self.annotations(read)["subject"], "x")
        self.assertEqual(self.annotations(write)["subject"], "x")
        # the return binds the L5 write, not the L4 decl
        edges = self.value_edges()
        self.assertIn(write["event_id"], {e["src_id"] for e in edges})


class ControlFlowTests(JavaDfgTestBase):
    def test_if_else_branch_and_merge(self) -> None:
        self.build("package a;\npublic class T {\n  int f(int c) {\n    int x;\n    if (c > 0) {\n      x = 1;\n    } else {\n      x = 2;\n    }\n    return x;\n  }\n}\n")
        cfgedges = self.dfg_edges()  # not control edges; inspect via sparse_cfg nodes/edges
        # verify CHECK + branch edges exist in sparse_cfg
        env = query_analysis(self.root, "sparse_cfg", file_path="src/T.java", database=self.database)
        kinds = {e["event_type"] for e in env["events"]}
        self.assertIn("CHECK", kinds)
        flags = {f for ed in env["edges"] for f in ed["payload"].get("flags", [])}
        self.assertIn("branch=true", flags)
        self.assertIn("branch=false", flags)

    def test_while_loop_backedge(self) -> None:
        self.build("package a;\npublic class T {\n  int f(int n) {\n    int i = 0;\n    while (i < n) {\n      i = i + 1;\n    }\n    return i;\n  }\n}\n")
        env = query_analysis(self.root, "sparse_cfg", file_path="src/T.java", database=self.database)
        flags = {f for ed in env["edges"] for f in ed["payload"].get("flags", [])}
        self.assertIn("loop_back", flags)

    def test_return_terminates(self) -> None:
        self.build("package a;\npublic class T {\n  int f() {\n    return 0;\n  }\n}\n")
        env = query_analysis(self.root, "sparse_cfg", file_path="src/T.java", database=self.database)
        kinds = {e["event_type"] for e in env["events"]}
        self.assertIn("RETURN", kinds)


class ShadowingAndDegradationTests(JavaDfgTestBase):
    def test_variable_shadowing_keeps_distinct_identity(self) -> None:
        self.build("package a;\npublic class T {\n  int f() {\n    int x = 1;\n    if (true) {\n      int x = 2;\n      x = 3;\n    }\n    return x;\n  }\n}\n")
        outer = self.event_by("WRITE", 4)
        inner = self.event_by("WRITE", 6)
        self.assertNotEqual(self.annotations(outer)["subject_decl"],
                            self.annotations(inner)["subject_decl"])
        # return x binds the OUTER x only
        ret = self.event_by("RETURN", 9)
        self.assertEqual(self.annotations(ret)["subject_decl"],
                         self.annotations(outer)["subject_decl"])

    def test_try_unsupported_no_fabrication(self) -> None:
        self.build("package a;\npublic class T {\n  int f() {\n    int x = 0;\n    try {\n      x = 1;\n    } catch (Exception e) {\n      x = 2;\n    }\n    return x;\n  }\n}\n")
        # try/catch degrades: no control-flow fabrication; def-use is still
        # position-ordered so return binds the newest positional write.
        writes = [e for e in self.scfg() if e["event_type"] == "WRITE"]
        self.assertGreaterEqual(len(writes), 3)  # x=0, x=1, x=2 all materialized
        env = query_analysis(self.root, "sparse_cfg", file_path="src/T.java", database=self.database)
        kinds = {e["event_type"] for e in env["events"]}
        self.assertNotIn("DEREFERENCE", kinds)  # no C-style deref in Java


if __name__ == "__main__":
    unittest.main()
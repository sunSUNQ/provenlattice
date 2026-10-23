"""Java Sparse CFG/DFG field dataflow tests (this.field / obj.field).

V2 field support: a bindable `field_access` (receiver is `this` or a known
local) emits a field READ/WRITE whose flow identity is:
  - `this.field` -> (subject=field, storage=field, decl=field:<owner>:field);
  - `obj.field`  -> (subject=obj, storage=obj's storage, member="field",
    decl=obj's local declaration).

Requirements covered: correct def-use for supported fields; distinct objects'
fields do NOT merge without alias evidence; local-variable shadowing is not
conflated with fields; unsupported receivers (method-call / nested / array /
unresolved) degrade without fabricating a dependency.
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


class JavaFieldDfgTestBase(unittest.TestCase):
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

    def find(self, event_type, line, subject, member=None) -> dict:
        matches = []
        for e in self.events():
            a = e.get("annotations") or {}
            if (e["event_type"] == event_type and e["start_line"] == line
                    and a.get("subject") == subject
                    and (member is None or a.get("subject_member") == member)):
                matches.append(e)
        self.assertEqual(len(matches), 1, (event_type, line, subject, member))
        return matches[0]

    def ann(self, event) -> dict:
        return event.get("annotations") or {}


class FieldReadWriteTests(JavaFieldDfgTestBase):
    def test_this_field_def_use(self) -> None:
        self.build("package a;\npublic class T {\n  int f;\n  int m() {\n    this.f = 1;\n    return this.f;\n  }\n}\n")
        write = self.find("WRITE", 5, "f")
        read = self.find("READ", 6, "f")
        self.assertEqual(self.ann(write)["subject_storage"], "field")
        self.assertEqual(self.ann(write)["subject_decl"], self.ann(read)["subject_decl"])
        self.assertIn(write["event_id"], {e["src_id"] for e in self.dfg_edges()})

    def test_obj_field_def_use(self) -> None:
        self.build("package a;\npublic class T {\n  int m(Foo obj) {\n    obj.f = 1;\n    return obj.f;\n  }\n}\nclass Foo { int f; }\n")
        write = self.find("WRITE", 4, "obj", member="f")
        read = self.find("READ", 5, "obj", member="f")
        self.assertEqual(self.ann(write)["subject_decl"], self.ann(read)["subject_decl"])
        self.assertIn(write["event_id"], {e["src_id"] for e in self.dfg_edges()})


class ObjectDistinctionTests(JavaFieldDfgTestBase):
    def test_distinct_objects_do_not_merge(self) -> None:
        self.build("package a;\npublic class T {\n  int m(Foo a, Foo b) {\n    a.f = 1;\n    b.f = 2;\n    return a.f;\n  }\n}\nclass Foo { int f; }\n")
        write_a = self.find("WRITE", 4, "a", member="f")
        write_b = self.find("WRITE", 5, "b", member="f")
        read_a = self.find("READ", 6, "a", member="f")
        self.assertNotEqual(self.ann(write_a)["subject_decl"], self.ann(write_b)["subject_decl"])
        # return a.f binds ONLY a.f's write, not b.f's
        edges = self.dfg_edges()
        self.assertIn(write_a["event_id"], {e["src_id"] for e in edges})
        self.assertNotIn(write_b["event_id"], {e["src_id"] for e in edges})
        self.assertEqual(read_a["event_id"], next(e["dst_id"] for e in edges if e["src_id"] == write_a["event_id"]))


class ShadowingTests(JavaFieldDfgTestBase):
    def test_local_vs_field_not_conflated(self) -> None:
        self.build("package a;\npublic class T {\n  int f;\n  int m() {\n    int f = 0;\n    this.f = 1;\n    return f;\n  }\n}\n")
        local_write = self.find("WRITE", 5, "f")  # local f
        field_write = self.find("WRITE", 6, "f")  # this.f
        self.assertEqual(self.ann(local_write)["subject_storage"], "local")
        self.assertEqual(self.ann(field_write)["subject_storage"], "field")
        self.assertNotEqual(self.ann(local_write)["subject_decl"], self.ann(field_write)["subject_decl"])
        # return f binds the LOCAL f, not this.f
        edges = self.dfg_edges()
        self.assertIn(local_write["event_id"], {e["src_id"] for e in edges})
        self.assertNotIn(field_write["event_id"], {e["src_id"] for e in edges})


class BranchTests(JavaFieldDfgTestBase):
    def test_field_write_in_branches_merges_positionally(self) -> None:
        self.build("package a;\npublic class T {\n  int f;\n  int m(boolean c) {\n    if (c) {\n      this.f = 1;\n    } else {\n      this.f = 2;\n    }\n    return this.f;\n  }\n}\n")
        write1 = self.find("WRITE", 6, "f")
        write2 = self.find("WRITE", 8, "f")
        read = self.find("READ", 10, "f")
        # position-order: the return binds the newest write (write2)
        self.assertIn(write2["event_id"], {e["src_id"] for e in self.dfg_edges()})
        # both writes carry the same field identity
        self.assertEqual(self.ann(write1)["subject_decl"], self.ann(write2)["subject_decl"])


class DegradationTests(JavaFieldDfgTestBase):
    def test_method_call_receiver_degrades(self) -> None:
        self.build("package a;\npublic class T {\n  int m(Foo obj) {\n    getObj().f = 1;\n    return getObj().f;\n  }\n  Foo getObj() { return null; }\n}\nclass Foo { int f; }\n")
        # no field WRITE/READ with a "field" identity should be emitted
        field_events = [e for e in self.events()
                        if (e.get("annotations") or {}).get("subject_member") == "f"]
        self.assertEqual(field_events, [])

    def test_nested_field_access_degrades(self) -> None:
        self.build("package a;\npublic class T {\n  int m(Foo obj) {\n    obj.inner.f = 1;\n    return obj.inner.f;\n  }\n}\nclass Foo { Bar inner; }\nclass Bar { int f; }\n")
        field_events = [e for e in self.events()
                        if (e.get("annotations") or {}).get("subject_member") in ("f", "inner.f")]
        self.assertEqual(field_events, [])

    def test_compound_field_assignment(self) -> None:
        self.build("package a;\npublic class T {\n  int m(Foo obj) {\n    obj.f += 1;\n    return obj.f;\n  }\n}\nclass Foo { int f; }\n")
        read = self.find("READ", 4, "obj", member="f")
        write = self.find("WRITE", 4, "obj", member="f")
        self.assertIn(write["event_id"], {e["src_id"] for e in self.dfg_edges()})


if __name__ == "__main__":
    unittest.main()
"""S1 Access Semantics V1 (Parent #28): C/C++ READ/WRITE/RMW access facts.

Freezes the access fact contract that concurrency consumers (S2/S4) will read:
- a plain assignment `x = y` is WRITE-only;
- a compound assignment (`x += y`, `x -= 2`) and an update (`x++`, `--x`)
  publish both READ and WRITE of the written subject (read-modify-write);
- local variables are excluded from cross-thread access pairing;
- an atomic operation keeps its ATOMIC (synchronized) classification and is not
  turned into a non-atomic WRITE;
- an unresolved identity is published as storage ``unknown``, never upgraded to
  a resolved subject.
"""

import tempfile
import unittest
from pathlib import Path

from provenlattice.analysis_query import query_analysis
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


def write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


class AccessSemanticsTestBase(unittest.TestCase):
    FIXTURE: str = ""

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

    def accesses(self, owner: str, event_type: str | None = None,
                 subject: str | None = None) -> list[dict]:
        matched = []
        for event in self.events():
            if event.get("owner_qualified_name") != owner:
                continue
            if event_type is not None and event["event_type"] != event_type:
                continue
            if subject is not None and event.get("annotations", {}).get("subject") != subject:
                continue
            matched.append(event)
        return matched

    def access_types(self, owner: str, subject: str) -> list[str]:
        return sorted(event["event_type"] for event in self.accesses(owner, subject=subject))


class RmwAccessTests(AccessSemanticsTestBase):
    FIXTURE = (
        "int g_count;\n"
        "int g_flag;\n"
        "void inc(void) { g_count++; }\n"
        "void dec(void) { --g_count; }\n"
        "void add(int n) { g_count += n; }\n"
        "void sub(void) { g_count -= 2; }\n"
        "void assign(int v) { g_count = v; }\n"
        "void toggle(void) { g_flag = !g_flag; }\n"
        "void local_rmw(void) { int local = 0; local++; }\n"
    )

    def test_postfix_increment_is_read_modify_write(self):
        self.assertEqual(self.access_types("inc", "g_count"), ["READ", "WRITE"])

    def test_prefix_decrement_is_read_modify_write(self):
        self.assertEqual(self.access_types("dec", "g_count"), ["READ", "WRITE"])

    def test_compound_add_is_read_modify_write(self):
        self.assertEqual(self.access_types("add", "g_count"), ["READ", "WRITE"])

    def test_compound_sub_is_read_modify_write(self):
        self.assertEqual(self.access_types("sub", "g_count"), ["READ", "WRITE"])

    def test_plain_assignment_is_write_only(self):
        self.assertEqual(self.access_types("assign", "g_count"), ["WRITE"])

    def test_bool_flag_read_and_write(self):
        self.assertEqual(self.access_types("toggle", "g_flag"), ["READ", "WRITE"])

    def test_local_variable_is_not_published(self):
        self.assertEqual(self.accesses("local_rmw", subject="local"), [])


class AtomicAccessTests(AccessSemanticsTestBase):
    FIXTURE = (
        "#include <stdatomic.h>\n"
        "atomic_int g_atomic;\n"
        "void op(void) { atomic_fetch_add(&g_atomic, 1); }\n"
    )

    def test_atomic_op_stays_classified_atomic(self):
        events = self.events()
        atomics = [event for event in events if event["event_type"] == "ATOMIC"]
        self.assertEqual(len(atomics), 1)
        self.assertEqual(atomics[0]["matched_via"], "calls")
        self.assertEqual(atomics[0]["annotations"]["subject"], "g_atomic")

    def test_atomic_op_does_not_become_a_non_atomic_write(self):
        writes = [
            event for event in self.events()
            if event["event_type"] == "WRITE"
            and event.get("annotations", {}).get("subject") == "g_atomic"
        ]
        self.assertEqual(writes, [])


class UnresolvedIdentityTests(AccessSemanticsTestBase):
    FIXTURE = "void use(void) { g_undeclared++; }\n"

    def test_undeclared_subject_is_unknown_rmw(self):
        # `g_undeclared` has no declaration in this file: it is still a
        # read-modify-write, but its storage stays `unknown` and is never
        # upgraded to a fake resolved identity.
        accesses = self.accesses("use", subject="g_undeclared")
        self.assertEqual(sorted(event["event_type"] for event in accesses), ["READ", "WRITE"])
        for event in accesses:
            self.assertEqual(event["annotations"]["subject_storage"], "unknown")


if __name__ == "__main__":
    unittest.main()
"""G2b-1 (issue-pilot #99): query-time pointer target sets.

Pins the read-only derivation contract:

* a two-arm conditional of address-of targets produces a multiple-candidate
  set, never one arm;
* a single address-of assignment produces one unique candidate;
* direct field access is not a pointer-target access;
* any unknown assignment makes the whole pointer unknown (no partial set);
* a parameter pointer has no call-site binding here and stays unknown;
* ``p->field`` and ``(*p).field`` compose the same candidate identity;
* a bare ``*p`` keeps target-level candidates with ``member_unresolved``;
* the query writes nothing and is deterministic.
"""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from provenlattice.deref_resolution import (
    POINTER_MULTIPLE,
    POINTER_UNIQUE,
    POINTER_UNKNOWN,
    query_pointer_targets,
)
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


def write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


class PointerTargetSetBase(unittest.TestCase):
    FIXTURE: str = ""
    FILENAME: str = "src/a.c"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        write(self.root, self.FILENAME, self.FIXTURE)
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("sparse_cfg",), database=self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def result(self) -> dict:
        return query_pointer_targets(
            self.root, self.FILENAME, database=self.database)

    def records(self) -> list[dict]:
        result = self.result()
        self.assertEqual(result["status"], "available", result.get("reason"))
        return result["pointer_targets"]

    def only(self) -> dict:
        records = self.records()
        self.assertEqual(len(records), 1, records)
        return records[0]


CONDITIONAL = """\
struct S { int datum; };
struct S s1;
struct S s2;
void f(int cond) {
    struct S *p = cond ? &s1 : &s2;
    p->datum = 1;
}
"""


class ConditionalTargetSetTests(PointerTargetSetBase):
    FIXTURE = CONDITIONAL

    def test_two_arms_become_a_multiple_candidate_set(self) -> None:
        record = self.only()
        self.assertEqual(record["status"], "available")
        self.assertEqual(record["candidates"],
                         ["global:s1#datum", "global:s2#datum"])
        self.assertEqual(record["resolution"], POINTER_MULTIPLE)
        self.assertFalse(record["subject_exact"])
        self.assertIn("conditional_pointer_source", record["limitations"])

    def test_dereferenced_member_matches_arrow_member(self) -> None:
        self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        write(self.root, self.FILENAME, CONDITIONAL.replace(
            "p->datum = 1;", "(*p).datum = 1;"))
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("sparse_cfg",), database=self.database)
        record = self.only()
        self.assertEqual(record["candidates"],
                         ["global:s1#datum", "global:s2#datum"])
        self.assertEqual(record["resolution"], POINTER_MULTIPLE)


class UniqueTargetSetTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
void g(void) {
    struct S *q = &s1;
    q->datum = 2;
}
"""

    def test_one_address_of_is_unique(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], ["global:s1#datum"])
        self.assertEqual(record["resolution"], POINTER_UNIQUE)
        self.assertFalse(record["subject_exact"])


class BareDereferenceTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
void g(void) {
    struct S *q = &s1;
    *q = 1;
}
"""

    def test_target_level_candidate_is_marked_unresolved(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], ["global:s1"])
        self.assertEqual(record["resolution"], POINTER_UNIQUE)
        self.assertIn("member_unresolved", record["limitations"])


class NegativeTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
void h(void) {
    s1.datum = 3;
}
"""

    def test_direct_field_access_is_not_derived(self) -> None:
        self.assertEqual(self.records(), [])


class UnknownTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
void f(void) {
    struct S *p = &s1;
    p = other;
    p->datum = 1;
}
"""

    def test_unknown_assignment_clears_the_whole_set(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], [])
        self.assertEqual(record["resolution"], POINTER_UNKNOWN)
        self.assertIn("pointer_source_unsupported", record["limitations"])


class ParameterTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
void f(struct S *p) {
    p->datum = 1;
}
"""

    def test_parameter_without_callsite_is_unknown(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], [])
        self.assertEqual(record["resolution"], POINTER_UNKNOWN)
        self.assertIn("parameter_without_callsite", record["limitations"])


class FileStaticTargetTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
static struct S s1;
void f(void) {
    struct S *p = &s1;
    p->datum = 1;
}
"""

    def test_file_static_keeps_its_storage_token(self) -> None:
        record = self.only()
        self.assertEqual(len(record["candidates"]), 1)
        candidate = record["candidates"][0]
        self.assertTrue(candidate.startswith("file_static:"), candidate)
        self.assertTrue(candidate.endswith("#datum"), candidate)


class DeformationTests(unittest.TestCase):
    RENAMED = """\
/* a comment moves the lines */
struct Node { int value; };
struct Node left;
struct Node right;
void work(int flag) {
    struct Node *target = flag ? (&right) : (&left);
    target->value = 1;
}
"""

    def _candidates(self, source: str) -> list[str]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            write(root, "src/a.c", source)
            database = Path(temporary) / "graph.db"
            full_index(root, database)
            analyze_scope(root, "src", ("sparse_cfg",), database=database)
            result = query_pointer_targets(root, "src/a.c", database=database)
        self.assertEqual(result["status"], "available", result.get("reason"))
        self.assertEqual(len(result["pointer_targets"]), 1)
        return result["pointer_targets"][0]["candidates"]

    def test_rename_parentheses_and_arm_swap_preserve_the_set(self) -> None:
        original = self._candidates(CONDITIONAL)
        deformed = self._candidates(self.RENAMED)
        self.assertEqual(original, ["global:s1#datum", "global:s2#datum"])
        self.assertEqual(deformed, ["global:left#value", "global:right#value"])


class LValueTargetTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
struct S s2;
void f(void) {
    struct S *p = &s1;
    (0, p) = &s2;
    p->datum = 1;
}
"""

    def test_comma_lvalue_is_a_second_binding(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], ["global:s1#datum", "global:s2#datum"])
        self.assertEqual(record["resolution"], POINTER_MULTIPLE)


class ConditionalLValueTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
struct S s2;
void f(int cond) {
    struct S *p = &s1;
    (cond ? p : p) = &s2;
    p->datum = 1;
}
"""

    def test_conditional_lvalue_naming_one_pointer_is_a_binding(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], ["global:s1#datum", "global:s2#datum"])
        self.assertEqual(record["resolution"], POINTER_MULTIPLE)


class AmbiguousLValueTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
struct S s2;
struct S s3;
void f(int cond) {
    struct S *p = &s1;
    struct S *q = &s3;
    (cond ? p : q) = &s2;
    p->datum = 1;
}
"""

    def test_ambiguous_lvalue_fails_closed(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], [])
        self.assertEqual(record["resolution"], POINTER_UNKNOWN)
        self.assertIn("ambiguous_lvalue_target", record["limitations"])


class GotoTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
void f(int cond) {
    struct S *p;
    if (cond) goto skip;
    p = &s1;
skip:
    p->datum = 1;
}
"""

    def test_goto_bypass_fails_closed(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], [])
        self.assertEqual(record["resolution"], POINTER_UNKNOWN)
        self.assertIn("goto_control_flow_unmodelled", record["limitations"])


class TypedefArrayTargetTests(PointerTargetSetBase):
    FIXTURE = """\
typedef int A[2];
A a;
void f(void) {
    int (*p)[2] = &a;
    (*p)[0] = 1;
}
"""

    def test_typedef_array_target_is_unknown(self) -> None:
        records = self.records()
        self.assertTrue(records)
        for record in records:
            self.assertEqual(record["resolution"], POINTER_UNKNOWN)
            self.assertEqual(record["candidates"], [])
            self.assertIn("target_array_unsupported", record["limitations"])


class StructArrayMemberTargetTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int a[2]; };
struct S s;
void f(void) {
    int (*p)[2] = &s.a;
    (*p)[0] = 1;
}
"""

    def test_struct_array_member_target_is_unknown(self) -> None:
        records = self.records()
        self.assertTrue(records)
        for record in records:
            self.assertEqual(record["resolution"], POINTER_UNKNOWN)
            self.assertEqual(record["candidates"], [])
            self.assertIn("target_array_unsupported", record["limitations"])


class ScalarMemberTargetTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s;
void f(void) {
    int *p = &s.datum;
    *p = 1;
}
"""

    def test_scalar_member_target_is_allowed(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], ["global:s#datum"])
        self.assertEqual(record["resolution"], POINTER_UNIQUE)


class ConditionalFirstAssignmentTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
void f(int cond) {
    struct S *p;
    if (cond) p = &s1;
    p->datum = 1;
}
"""

    def test_conditional_first_assignment_is_unknown(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], [])
        self.assertEqual(record["resolution"], POINTER_UNKNOWN)
        self.assertIn("conditional_assignment", record["limitations"])


class ShadowedPointerIdentityTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
struct S s2;
void f(void) {
    struct S *p = &s1;
    {
        struct S *p = &s2;
        p->datum = 1;
    }
    p->datum = 2;
}
"""

    def test_shadowed_pointers_get_declaration_level_identities(self) -> None:
        records = self.records()
        self.assertEqual(len(records), 2, records)
        by_candidate = {
            record["candidates"][0]: record for record in records
        }
        inner = by_candidate["global:s2#datum"]
        outer = by_candidate["global:s1#datum"]
        self.assertNotEqual(
            inner["pointer_identity"], outer["pointer_identity"],
            records,
        )


class ArrayTargetTests(PointerTargetSetBase):
    FIXTURE = """\
int a[2];
void f(void) {
    int (*p)[2] = &a;
    (*p)[0] = 1;
}
"""

    def test_array_target_is_unknown(self) -> None:
        records = self.records()
        self.assertTrue(records)
        for record in records:
            self.assertEqual(record["resolution"], POINTER_UNKNOWN)
            self.assertEqual(record["candidates"], [])
            self.assertIn("target_array_unsupported", record["limitations"])


class ParenthesizedAssignmentTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
struct S s2;
void f(void) {
    struct S *p = &s1;
    (p) = &s2;
    p->datum = 1;
}
"""

    def test_parenthesized_assignment_is_a_second_binding(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], ["global:s1#datum", "global:s2#datum"])
        self.assertEqual(record["resolution"], POINTER_MULTIPLE)
        self.assertIn("flow_insensitive_assignment_union", record["limitations"])


class DoubleParenthesizedAssignmentTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
struct S s2;
void f(void) {
    struct S *p = &s1;
    ((p)) = &s2;
    p->datum = 1;
}
"""

    def test_double_parentheses_are_unwrapped(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], ["global:s1#datum", "global:s2#datum"])
        self.assertEqual(record["resolution"], POINTER_MULTIPLE)


class ParenthesizedUpdateTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
void f(void) {
    struct S *p = &s1;
    (p)++;
    p->datum = 1;
}
"""

    def test_parenthesized_update_clears_the_set(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], [])
        self.assertEqual(record["resolution"], POINTER_UNKNOWN)
        self.assertIn("pointer_assignment_unsupported", record["limitations"])


class ParenthesizedConditionalAssignmentTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
struct S s2;
struct S s3;
void f(int cond) {
    struct S *p = &s1;
    (p) = cond ? &s2 : &s3;
    p->datum = 1;
}
"""

    def test_parenthesized_conditional_assignment_is_complete(self) -> None:
        record = self.only()
        self.assertEqual(
            record["candidates"],
            ["global:s1#datum", "global:s2#datum", "global:s3#datum"],
        )
        self.assertEqual(record["resolution"], POINTER_MULTIPLE)


class AccessBeforeAssignmentTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
void f(void) {
    struct S *p;
    p->datum = 0;
    p = &s1;
    p->datum = 1;
}
"""

    def test_access_before_the_first_assignment_is_unknown(self) -> None:
        records = sorted(self.records(), key=lambda record: record["start_byte"])
        self.assertEqual(len(records), 2, records)
        self.assertEqual(records[0]["resolution"], POINTER_UNKNOWN)
        self.assertEqual(records[0]["candidates"], [])
        self.assertIn("access_before_assignment", records[0]["limitations"])
        self.assertEqual(records[1]["resolution"], POINTER_UNIQUE)
        self.assertEqual(records[1]["candidates"], ["global:s1#datum"])


class UpdateExpressionTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
void f(void) {
    struct S *p = &s1;
    p++;
    p->datum = 1;
}
"""

    def test_pointer_update_clears_the_set(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], [])
        self.assertEqual(record["resolution"], POINTER_UNKNOWN)
        self.assertIn("pointer_assignment_unsupported", record["limitations"])


class AddressEscapeTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
void use(struct S **p);
void f(void) {
    struct S *p = &s1;
    use(&p);
    p->datum = 1;
}
"""

    def test_taken_pointer_address_clears_the_set(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], [])
        self.assertEqual(record["resolution"], POINTER_UNKNOWN)
        self.assertIn("pointer_address_escapes", record["limitations"])


class MultipleKnownAssignmentsTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
struct S s2;
void f(void) {
    struct S *p = &s1;
    p = &s2;
    p->datum = 1;
}
"""

    def test_known_assignments_are_a_union_with_a_limitation(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], ["global:s1#datum", "global:s2#datum"])
        self.assertEqual(record["resolution"], POINTER_MULTIPLE)
        self.assertIn("flow_insensitive_assignment_union", record["limitations"])


class NestedMemberTests(PointerTargetSetBase):
    FIXTURE = """\
struct Inner { int datum; };
struct S { struct Inner inner; };
struct S s1;
void f(void) {
    struct S *p = &s1;
    p->inner.datum = 1;
}
"""

    def test_nested_member_uses_the_published_pointer_access(self) -> None:
        # The DEREFERENCE the walker publishes is `p->inner`; the trailing
        # `.datum` is a direct field access on that object, not a second
        # pointer-target access.  The candidate is therefore `s1#inner`.
        record = self.only()
        self.assertEqual(record["candidates"], ["global:s1#inner"])
        self.assertEqual(record["expression"], "p->inner")


class SubscriptMemberTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum[2]; };
struct S s1;
void f(void) {
    struct S *p = &s1;
    p->datum[0] = 1;
}
"""

    def test_subscript_member_stays_target_level(self) -> None:
        records = self.records()
        subscripted = [
            record for record in records
            if record["expression"] == "p->datum[0]"
        ]
        self.assertEqual(len(subscripted), 1, records)
        record = subscripted[0]
        self.assertEqual(record["candidates"], ["global:s1"])
        self.assertIn("member_path_unresolved", record["limitations"])


class NestedConditionalTests(PointerTargetSetBase):
    FIXTURE = """\
struct S { int datum; };
struct S s1;
struct S s2;
struct S s3;
void f(int a, int b) {
    struct S *p = a ? &s1 : (b ? &s2 : &s3);
    p->datum = 1;
}
"""

    def test_nested_conditional_fails_closed(self) -> None:
        record = self.only()
        self.assertEqual(record["candidates"], [])
        self.assertEqual(record["resolution"], POINTER_UNKNOWN)
        self.assertIn("conditional_arm_unsupported", record["limitations"])


class PureReaderTests(PointerTargetSetBase):
    FIXTURE = CONDITIONAL

    def _counts(self) -> tuple[int, int, int, int]:
        with closing(sqlite3.connect(self.database)) as connection:
            analysis_nodes = connection.execute(
                "SELECT COUNT(*) FROM analysis_nodes").fetchone()[0]
            analysis_edges = connection.execute(
                "SELECT COUNT(*) FROM analysis_edges").fetchone()[0]
            nodes = connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edges = connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return int(analysis_nodes), int(analysis_edges), int(nodes), int(edges)

    def test_query_writes_nothing(self) -> None:
        before = self._counts()
        self.records()
        self.assertEqual(self._counts(), before)

    def test_deterministic_output(self) -> None:
        first = json.dumps(self.result(), sort_keys=True)
        second = json.dumps(self.result(), sort_keys=True)
        self.assertEqual(first, second)


class StatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_not_built_preserved(self) -> None:
        write(self.root, "src/a.c", "int g; void f(void) { g++; }\n")
        database = Path(self.temp.name) / "graph.db"
        full_index(self.root, database)
        result = query_pointer_targets(self.root, "src/a.c", database=database)
        self.assertEqual(result["status"], "not_built")
        self.assertEqual(result["pointer_targets"], [])

    def test_stale_source_hash_fails_closed(self) -> None:
        write(self.root, "src/a.c", CONDITIONAL)
        database = Path(self.temp.name) / "graph.db"
        full_index(self.root, database)
        analyze_scope(self.root, "src", ("sparse_cfg",), database=database)
        with closing(sqlite3.connect(database)) as connection:
            connection.execute(
                "UPDATE file_state SET source_hash='deadbeef' WHERE path='src/a.c'")
            connection.commit()
        result = query_pointer_targets(self.root, "src/a.c", database=database)
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["pointer_targets"], [])

    def test_python_reports_unsupported(self) -> None:
        write(self.root, "src/a.py", "def a():\n    return 1\n")
        database = Path(self.temp.name) / "graph.db"
        full_index(self.root, database)
        result = query_pointer_targets(self.root, "src/a.py", database=database)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["pointer_targets"], [])


if __name__ == "__main__":
    unittest.main()

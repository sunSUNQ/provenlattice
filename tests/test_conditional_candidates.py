"""G2b (issue-pilot#97): conditional-pointer candidate facts.

Freezes the Option 1 + representation B contract:

* a conditional pointer binding (`p = cond ? &a : &b`) stamps the additive
  `subject_candidates_v1` annotation on the later accesses through `p`;
* the candidates are the declared identities of the two arms, with the access
  member path composed (`p->datum` -> `global:a#datum`);
* lock receivers are stamped the same way;
* the annotation is candidate-only (`confidence="may"`), never must-alias or
  definite points-to;
* an unconditional binding produces no candidates; an unresolved arm, a second
  binding, a taken address, an enclosing control construct or two arms naming
  one object fail closed (`unknown` / no annotation);
* the reader is pure, deterministic and never changes an existing event id or
  edge.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from provenlattice.analysis_query import query_analysis
from provenlattice.conditional_candidates import (
    STATUS_CANDIDATE,
    STATUS_UNKNOWN,
    STATUS_UNRESOLVED,
    build_conditional_candidates,
    query_conditional_candidates,
)
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


def write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


class ConditionalCandidatesTestBase(unittest.TestCase):
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

    def events(self) -> list[dict]:
        env = query_analysis(
            self.root, "sparse_cfg", file_path=self.FILENAME,
            database=self.database,
        )
        self.assertEqual(env["status"], "available", env.get("reason"))
        return env["events"]

    def bundle(self) -> dict:
        return build_conditional_candidates(self.events())

    def query(self) -> dict:
        result = query_conditional_candidates(
            self.root, self.FILENAME, database=self.database)
        self.assertEqual(result["status"], "available", result.get("reason"))
        return result

    @staticmethod
    def candidate_keys(result: dict) -> list[tuple]:
        return sorted(
            (
                record["event_type"],
                tuple(
                    (item["decl"], item["member"], item["arm"])
                    for item in record["candidates"]
                ),
                record["status"],
                record["limitation"],
            )
            for record in result["candidates"]
        )


CONDITIONAL_FIXTURE = (
    "#include <pthread.h>\n"
    "struct S { pthread_mutex_t m; int datum; };\n"
    "struct S s1;\n"
    "struct S s2;\n"
    "int cond;\n"
    "void f(void) {\n"
    "    struct S *p = cond ? &s1 : &s2;\n"
    "    p->datum = 1;\n"
    "    pthread_mutex_lock(&p->m);\n"
    "    pthread_mutex_unlock(&p->m);\n"
    "}\n"
)


class PositiveCandidateTests(ConditionalCandidatesTestBase):
    FIXTURE = CONDITIONAL_FIXTURE

    def test_member_access_carries_both_candidates(self):
        records = [
            record for record in self.bundle()["candidates"]
            if record["event_type"] == "DEREFERENCE"
            and any(item["member"] == "datum" for item in record["candidates"])
        ]
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["status"], STATUS_CANDIDATE)
        self.assertEqual(record["confidence"], "may")
        self.assertEqual(record["limitation"], "")
        self.assertEqual(
            {(item["decl"], item["member"]) for item in record["candidates"]},
            {("global:s1", "datum"), ("global:s2", "datum")},
        )

    def test_lock_receiver_carries_both_candidates(self):
        records = [
            record for record in self.bundle()["candidates"]
            if record["event_type"] in {"LOCK", "UNLOCK"}
        ]
        self.assertTrue(records)
        for record in records:
            self.assertEqual(record["status"], STATUS_CANDIDATE)
            self.assertEqual(
                {(item["decl"], item["member"]) for item in record["candidates"]},
                {("global:s1", "m"), ("global:s2", "m")},
            )

    def test_existing_annotations_are_preserved(self):
        event = next(
            event for event in self.events()
            if event["event_type"] == "DEREFERENCE"
            and event["annotations"].get("subject") == "p"
        )
        annotations = event["annotations"]
        self.assertIn("expression", annotations)
        self.assertEqual(annotations["subject_decl"], "local:p")
        self.assertIn("subject_candidates_v1", annotations)
        self.assertIn("local_access_v1", annotations)

    def test_query_reader_reports_the_records(self):
        result = self.query()
        self.assertEqual(result["status"], "available")
        self.assertGreater(result["provenance"]["candidate_record_count"], 0)
        self.assertEqual(
            result["provenance"]["candidate_count"],
            sum(len(record["candidates"]) for record in result["candidates"]),
        )
        for record in result["candidates"]:
            self.assertEqual(record["confidence"], "may")

    def test_deterministic_output(self):
        first = json.dumps(self.bundle(), sort_keys=True)
        second = json.dumps(self.bundle(), sort_keys=True)
        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(self.query(), sort_keys=True),
            json.dumps(self.query(), sort_keys=True),
        )


class UnconditionalTests(ConditionalCandidatesTestBase):
    FIXTURE = (
        "struct S { int datum; };\n"
        "struct S s1;\n"
        "void f(void) { struct S *p = &s1; p->datum = 1; }\n"
    )

    def test_no_candidates_without_a_conditional_binding(self):
        self.assertEqual(self.bundle()["candidates"], [])


class UnknownArmTests(ConditionalCandidatesTestBase):
    FIXTURE = (
        "struct S { int datum; };\n"
        "struct S s1;\n"
        "int cond;\n"
        "struct S *maybe(void);\n"
        "void f(void) { struct S *p = cond ? &s1 : maybe(); p->datum = 1; }\n"
    )

    def test_unresolved_arm_fails_closed(self):
        records = self.bundle()["candidates"]
        self.assertTrue(records)
        for record in records:
            self.assertEqual(record["status"], STATUS_UNKNOWN)
            self.assertEqual(record["candidates"], [])
            self.assertEqual(record["limitation"], "arm_unresolved")


class MultipleBindingTests(ConditionalCandidatesTestBase):
    FIXTURE = (
        "struct S { int datum; };\n"
        "struct S s1;\n"
        "struct S s2;\n"
        "int cond;\n"
        "void f(void) {\n"
        "    struct S *p = cond ? &s1 : &s2;\n"
        "    p = &s1;\n"
        "    p->datum = 1;\n"
        "}\n"
    )

    def test_second_binding_fails_closed(self):
        records = self.bundle()["candidates"]
        self.assertTrue(records)
        for record in records:
            self.assertEqual(record["status"], STATUS_UNKNOWN)
            self.assertEqual(record["limitation"], "binding_not_unique")


class ConditionalBindingTests(ConditionalCandidatesTestBase):
    FIXTURE = (
        "struct S { int datum; };\n"
        "struct S s1;\n"
        "struct S s2;\n"
        "int cond;\n"
        "int flag;\n"
        "void f(void) {\n"
        "    if (flag) {\n"
        "        struct S *p = cond ? &s1 : &s2;\n"
        "        p->datum = 1;\n"
        "    }\n"
        "}\n"
    )

    def test_binding_inside_control_fails_closed(self):
        records = self.bundle()["candidates"]
        self.assertTrue(records)
        for record in records:
            self.assertEqual(record["status"], STATUS_UNKNOWN)
            self.assertEqual(record["limitation"], "conditional_binding")


class AddressEscapeTests(ConditionalCandidatesTestBase):
    FIXTURE = (
        "struct S { int datum; };\n"
        "struct S s1;\n"
        "struct S s2;\n"
        "int cond;\n"
        "void use(struct S **p);\n"
        "void f(void) {\n"
        "    struct S *p = cond ? &s1 : &s2;\n"
        "    use(&p);\n"
        "    p->datum = 1;\n"
        "}\n"
    )

    def test_taken_address_fails_closed(self):
        records = self.bundle()["candidates"]
        self.assertTrue(records)
        for record in records:
            self.assertEqual(record["status"], STATUS_UNKNOWN)
            self.assertEqual(record["limitation"], "address_escapes")


class TwoConditionalBindingsTests(ConditionalCandidatesTestBase):
    FIXTURE = (
        "struct S { int datum; };\n"
        "struct S s1;\n"
        "struct S s2;\n"
        "int cond;\n"
        "int cond2;\n"
        "void f(void) {\n"
        "    struct S *p = cond ? &s1 : &s2;\n"
        "    p = cond2 ? &s1 : &s2;\n"
        "    p->datum = 1;\n"
        "}\n"
    )

    def test_two_conditional_bindings_fail_closed(self):
        records = self.bundle()["candidates"]
        self.assertTrue(records)
        for record in records:
            self.assertEqual(record["status"], STATUS_UNKNOWN)
            self.assertEqual(record["limitation"], "multiple_conditional_bindings")


class NonPointerConditionalTests(ConditionalCandidatesTestBase):
    FIXTURE = (
        "struct S { int datum; };\n"
        "struct S s1;\n"
        "struct S s2;\n"
        "int cond;\n"
        "void f(void) {\n"
        "    long x = cond ? (long)&s1 : (long)&s2;\n"
        "    x = 3;\n"
        "}\n"
    )

    def test_non_pointer_target_is_not_this_shape(self):
        self.assertEqual(self.bundle()["candidates"], [])


class ValueConditionalTests(ConditionalCandidatesTestBase):
    FIXTURE = (
        "int cond;\n"
        "void f(void) {\n"
        "    int x = cond ? 1 : 2;\n"
        "    x = 3;\n"
        "}\n"
    )

    def test_value_conditional_is_not_this_shape(self):
        self.assertEqual(self.bundle()["candidates"], [])


class SameTargetTests(ConditionalCandidatesTestBase):
    FIXTURE = (
        "struct S { int datum; };\n"
        "struct S s1;\n"
        "int cond;\n"
        "void f(void) { struct S *p = cond ? &s1 : &s1; p->datum = 1; }\n"
    )

    def test_two_arms_naming_one_object_publish_nothing(self):
        self.assertEqual(self.bundle()["candidates"], [])


class DeformationTests(unittest.TestCase):
    ORIGINAL = (
        "struct S { int datum; };\n"
        "struct S s1;\n"
        "struct S s2;\n"
        "int cond;\n"
        "void f(void) {\n"
        "    struct S *p = cond ? &s1 : &s2;\n"
        "    p->datum = 1;\n"
        "}\n"
    )
    RENAMED = (
        "// renaming the pointer and the function changes no identity\n"
        "\n"
        "struct S { int datum; };\n"
        "struct S s1;\n"
        "struct S s2;\n"
        "int cond;\n"
        "void g(void) {\n"
        "    struct S *q = cond ? &s1 : &s2;\n"
        "    q->datum = 1;\n"
        "}\n"
    )
    SWAPPED = (
        "struct S { int datum; };\n"
        "struct S s1;\n"
        "struct S s2;\n"
        "int cond;\n"
        "void f(void) {\n"
        "    struct S *p = cond ? &s2 : &s1;\n"
        "    p->datum = 1;\n"
        "}\n"
    )

    def _keys(self, fixture: str) -> list[tuple]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            write(root, "src/a.c", fixture)
            database = Path(temporary) / "graph.db"
            full_index(root, database)
            analyze_scope(root, "src", ("sparse_cfg",), database=database)
            result = query_conditional_candidates(
                root, "src/a.c", database=database)
        return sorted(
            (
                record["status"],
                record["limitation"],
                tuple(
                    (item["decl"], item["member"])
                    for item in record["candidates"]
                ),
            )
            for record in result["candidates"]
        )

    def test_pointer_and_function_rename_does_not_change_candidates(self):
        self.assertEqual(self._keys(self.RENAMED), self._keys(self.ORIGINAL))

    def test_swapping_arms_does_not_change_the_candidate_set(self):
        original = {
            item
            for record in build_keys(self.ORIGINAL)
            for item in record
        }
        swapped = {
            item
            for record in build_keys(self.SWAPPED)
            for item in record
        }
        self.assertEqual(swapped, original)


def build_keys(fixture: str) -> list[list[tuple[str, str]]]:
    """Candidate `(decl, member)` pairs per record, for deformation tests."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "repo"
        write(root, "src/a.c", fixture)
        database = Path(temporary) / "graph.db"
        full_index(root, database)
        analyze_scope(root, "src", ("sparse_cfg",), database=database)
        result = query_conditional_candidates(
            root, "src/a.c", database=database)
    return [
        [(item["decl"], item["member"]) for item in record["candidates"]]
        for record in result["candidates"]
        if record["status"] == STATUS_CANDIDATE
    ]


class ReaderFailClosedTests(unittest.TestCase):
    def _event(self, raw: str | None = None, **annotations) -> dict:
        payload = dict(annotations)
        if raw is not None:
            payload["subject_candidates_v1"] = raw
        return {
            "event_id": "event:test",
            "event_type": "DEREFERENCE",
            "owner_qualified_name": "f",
            "annotations": payload,
        }

    def test_malformed_annotation_is_unresolved(self):
        result = build_conditional_candidates([self._event("{not json")])
        self.assertEqual(result["candidates"][0]["status"], STATUS_UNRESOLVED)
        self.assertEqual(result["candidates"][0]["candidates"], [])
        self.assertIn("candidates_malformed", result["missing_evidence"])

    def test_candidate_with_fewer_than_two_targets_is_unresolved(self):
        raw = json.dumps({
            "version": 1,
            "status": "candidate",
            "candidates": [{"decl": "global:s1"}],
        })
        result = build_conditional_candidates([self._event(raw)])
        self.assertEqual(result["candidates"][0]["status"], STATUS_UNRESOLVED)
        self.assertIn("candidates_underflow", result["missing_evidence"])

    def test_confidence_is_never_upgraded(self):
        raw = json.dumps({
            "version": 1,
            "status": "candidate",
            "confidence": "must",
            "candidates": [
                {"decl": "global:s1"},
                {"decl": "global:s2"},
            ],
        })
        result = build_conditional_candidates([self._event(raw)])
        self.assertEqual(result["candidates"][0]["confidence"], "may")


class StatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_not_built_preserved(self):
        write(self.root, "src/a.c",
              "struct S { int x; }; void f(void) { struct S s; s.x = 1; }\n")
        database = Path(self.temp.name) / "graph.db"
        full_index(self.root, database)
        result = query_conditional_candidates(
            self.root, "src/a.c", database=database)
        self.assertEqual(result["status"], "not_built")
        self.assertEqual(result["candidates"], [])

    def test_python_reports_unsupported(self):
        write(self.root, "src/a.py", "def f():\n    return 1\n")
        database = Path(self.temp.name) / "graph.db"
        full_index(self.root, database)
        result = query_conditional_candidates(
            self.root, "src/a.py", database=database)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["candidates"], [])

    def test_stale_source_hash_fails_closed(self):
        write(self.root, "src/a.c", CONDITIONAL_FIXTURE)
        database = Path(self.temp.name) / "graph.db"
        full_index(self.root, database)
        analyze_scope(self.root, "src", ("sparse_cfg",), database=database)
        with closing(sqlite3.connect(database)) as connection:
            connection.execute(
                "UPDATE file_state SET source_hash='deadbeef' WHERE path='src/a.c'")
            connection.commit()
        result = query_conditional_candidates(
            self.root, "src/a.c", database=database)
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["candidates"], [])


class PureReaderTests(ConditionalCandidatesTestBase):
    FIXTURE = CONDITIONAL_FIXTURE

    def test_reader_writes_no_rows(self):
        before = self._counts()
        self.query()
        self.assertEqual(self._counts(), before)

    def _counts(self) -> tuple[int, int]:
        with closing(sqlite3.connect(self.database)) as connection:
            nodes = connection.execute(
                "SELECT COUNT(*) FROM analysis_nodes").fetchone()[0]
            edges = connection.execute(
                "SELECT COUNT(*) FROM analysis_edges").fetchone()[0]
        return int(nodes), int(edges)


if __name__ == "__main__":
    unittest.main()

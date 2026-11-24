"""B2 out_of_bounds_write (M5/M6/M8) over the frozen #82/#94 facts.

The query is a pure reader: every fixture below exercises facts the sparse-CFG
producer already published (`buffer_extent_v1`, `memory_access_v1`). No test
asserts on source text parsing, and none hardcodes a benchmark identity.
"""

import tempfile
import unittest
from pathlib import Path

from provenlattice.defect_query import query_defect_candidates
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


def write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


DECLARED = r"""
void touch(void) {
    char buf[4];
    buf[4] = 0;
}
"""

BOUNDS_MATRIX = r"""
void touch(void) {
    char buf[4];
    int a[4];
    int i = 0;
    buf[0] = 0;
    buf[3] = 0;
    a[i] = 0;
    a[-1] = 0;
}
"""

RMW = r"""
void touch(void) {
    int a[4];
    a[4] += 1;
}
"""

HEAP = r"""
#include <stdlib.h>
void char_heap(void) {
    char *p = malloc(4);
    p[4] = 0;
}
void int_heap(void) {
    int *q = malloc(16);
    q[5] = 0;
}
"""

MEMORY_API = r"""
#include <string.h>
void over(void) {
    char dst[4];
    memset(dst, 0, 8);
}
void exact(void) {
    char dst[4];
    memset(dst, 0, 4);
}
"""

READ_DIRECTION = r"""
#include <stdlib.h>
void touch(void) {
    char *p = malloc(4);
    char v = p[4];
    (void)v;
}
"""

UNEVALUATED = r"""
void touch(void) {
    char buf[4];
    int a = (int)sizeof(buf[4]);
    char *p = &buf[4];
    (void)a;
    (void)p;
}
"""

INTERVENING_RELEASE = r"""
#include <stdlib.h>
void touch(void) {
    char *p = malloc(4);
    free(p);
    p[4] = 0;
}
"""

REALLOCATION = r"""
#include <stdlib.h>
void touch(void) {
    char *p = malloc(4);
    p = malloc(8);
    p[4] = 0;
}
"""

UNKNOWN_ALIAS = r"""
void touch(void *p) {
    p[4] = 0;
}
"""

RENAMED = r"""
void run(void) {
    char buffer[8];
    buffer[8] = 1;
}
"""


class OutOfBoundsWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.database = Path(self.temp.name) / "graph.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self, body: str, name: str = "src/t.c") -> None:
        write(self.root, name, body)
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("defect",), database=self.database)

    def query(self, defect_type: str = "out_of_bounds_write", **kwargs) -> dict:
        return query_defect_candidates(
            self.root, defect_type=defect_type, database=self.database, **kwargs)

    def candidates(self, defect_type: str = "out_of_bounds_write") -> list[dict]:
        env = self.query(defect_type)
        self.assertEqual(env["status"], "available", env.get("reason"))
        return [
            candidate for candidate in env["candidates"]
            if candidate["query"] == "out_of_bounds_write"
        ]

    def test_declared_array_write_is_a_candidate(self) -> None:
        self.build(DECLARED)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["defect_key"], "oob_write")
        self.assertEqual(candidate["resolution_status"], "resolved")
        self.assertEqual(candidate["metadata"]["facets"], ["M8", "M5"])
        self.assertEqual(candidate["metadata"]["index"], 4)
        self.assertEqual(candidate["metadata"]["extent"], 4)
        self.assertEqual(candidate["subject"]["name"], "buf")
        self.assertTrue(candidate["evidence_id"].startswith("E-DEFECT-"))
        self.assertTrue(candidate["source_evidence"])
        self.assertIn("extent", " ".join(
            fact.get("kind", "") for fact in candidate["facts"]))

    def test_valid_dynamic_and_negative_indices_are_coverage(self) -> None:
        self.build(BOUNDS_MATRIX)
        env = self.query()
        candidates = [c for c in env["candidates"]
                      if c["query"] == "out_of_bounds_write"]
        self.assertEqual(candidates, [])
        exclusions = env["coverage"]["exclusions"]
        self.assertGreaterEqual(exclusions.get("valid", 0), 2)
        self.assertGreaterEqual(exclusions.get("dynamic_index", 0), 1)
        self.assertGreaterEqual(exclusions.get("negative_index_not_constant", 0), 1)

    def test_read_modify_write_counts_as_a_write_direction(self) -> None:
        self.build(RMW)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["metadata"]["access"], "READ_MODIFY_WRITE")
        self.assertEqual(candidates[0]["metadata"]["facets"], ["M8", "M5"])

    def test_heap_char_is_a_candidate_and_non_char_is_unit_mismatch(self) -> None:
        self.build(HEAP)
        env = self.query()
        candidates = [c for c in env["candidates"]
                      if c["query"] == "out_of_bounds_write"]
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["subject"]["name"], "p")
        self.assertEqual(candidate["metadata"]["facets"], ["M8", "M6"])
        self.assertTrue(candidate["metadata"]["allocation_point"])
        self.assertEqual(candidate["metadata"]["reach"], "reachable")
        self.assertGreaterEqual(env["coverage"]["exclusions"].get("unit_mismatch", 0), 1)

    def test_memory_api_length_over_extent_is_a_candidate(self) -> None:
        self.build(MEMORY_API)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["metadata"]["facets"], ["M8", "M5"])
        self.assertEqual(candidate["metadata"]["index"], 8)
        self.assertEqual(candidate["metadata"]["extent"], 4)
        self.assertEqual(candidate["metadata"]["unit"], "bytes")

    def test_read_direction_is_not_reported(self) -> None:
        self.build(READ_DIRECTION)
        env = self.query()
        self.assertEqual(
            [c for c in env["candidates"] if c["query"] == "out_of_bounds_write"],
            [])
        self.assertGreaterEqual(
            env["coverage"]["exclusions"].get("read_direction", 0), 1)

    def test_unevaluated_and_address_of_are_not_accesses(self) -> None:
        self.build(UNEVALUATED)
        self.assertEqual(self.candidates(), [])

    def test_intervening_release_is_not_judged_as_bounds(self) -> None:
        self.build(INTERVENING_RELEASE)
        env = self.query(confidence_gate=None)
        self.assertEqual(
            [c for c in env["candidates"] if c["query"] == "out_of_bounds_write"],
            [])
        self.assertGreaterEqual(
            env["coverage"]["exclusions"].get("intervening_release", 0), 1)

    def test_reallocation_uses_the_latest_extent(self) -> None:
        self.build(REALLOCATION)
        env = self.query()
        self.assertEqual(
            [c for c in env["candidates"] if c["query"] == "out_of_bounds_write"],
            [])
        self.assertGreaterEqual(env["coverage"]["exclusions"].get("valid", 0), 1)

    def test_unknown_alias_is_not_judged(self) -> None:
        self.build(UNKNOWN_ALIAS)
        env = self.query(confidence_gate=None)
        self.assertEqual(
            [c for c in env["candidates"] if c["query"] == "out_of_bounds_write"],
            [])

    def test_memory_category_and_all_include_the_query(self) -> None:
        self.build(DECLARED)
        for kwargs in ({"category": "memory"}, {"defect_type": "all"}):
            env = query_defect_candidates(
                self.root, database=self.database, **kwargs)
            self.assertEqual(env["status"], "available")
            queries = {candidate["query"] for candidate in env["candidates"]}
            self.assertIn("out_of_bounds_write", queries, kwargs)

    def test_renaming_and_repeat_are_deterministic(self) -> None:
        self.build(RENAMED)
        first = self.candidates()
        second = self.candidates()
        self.assertEqual(len(first), 1)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["subject"]["name"], "buffer")

    def test_candidate_introduces_no_other_query_regression(self) -> None:
        self.build(DECLARED)
        env = self.query("out_of_bounds_write")
        bundles = {bundle["candidate_id"] for bundle in env["evidence_bundles"]}
        for candidate in env["candidates"]:
            self.assertIn(candidate["evidence_id"], bundles)


if __name__ == "__main__":
    unittest.main()

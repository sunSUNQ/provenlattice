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

SHADOWED_OUTER_OOB = r"""
#include <stdlib.h>
void touch(int c) {
    char *p = malloc(4);
    if (c) { char *p = malloc(8); p[4] = 0; }
    p[4] = 0;
}
"""

SHADOWED_INNER_OOB = r"""
#include <stdlib.h>
void touch(int c) {
    char *p = malloc(8);
    if (c) { char *p = malloc(4); p[4] = 0; }
    p[4] = 0;
}
"""

CROSS_TU_A = r"""
#include <stdlib.h>
static void f(void) {
    char *p = malloc(4);
    p[4] = 0;
}
"""

CROSS_TU_B = r"""
#include <stdlib.h>
static void f(void) {
    char *p = malloc(8);
    p[4] = 0;
}
"""

PLAIN_REASSIGNMENT = r"""
#include <stdlib.h>
void touch(char *q) {
    char *p = malloc(4);
    p = q;
    p[4] = 0;
}
"""

BRANCH_ALLOCATION = r"""
#include <stdlib.h>
void touch(int c) {
    char *p = malloc(4);
    if (c) { p = malloc(8); }
    p[4] = 0;
}
"""

CONDITIONAL_RELEASE = r"""
#include <stdlib.h>
void touch(int c) {
    char *p = malloc(4);
    if (c) { free(p); return; }
    p[4] = 0;
}
"""

HEAP_MEMORY_API = r"""
#include <stdlib.h>
#include <string.h>
void over(void) {
    char *p = malloc(4);
    memset(p, 0, 8);
}
void exact(void) {
    char *p = malloc(8);
    memcpy(p, "ab", 4);
}
"""

BUDGETED_PATH = r"""
#include <stdlib.h>
void sink(void) { }
void touch(void) {
    char *p = malloc(4);
    sink();
    sink();
    p[4] = 0;
}
"""

SELF_WRITE_POINTERS = r"""
#include <stdlib.h>
char *g;

void by_parameter(char *p) {
    p = malloc(4);
    p[4] = 0;
}

void by_global(void) {
    g = malloc(4);
    g[4] = 0;
}
"""

CONDITIONAL_REBINDING = r"""
#include <stdlib.h>
void touch(char *q, int c) {
    char *p = malloc(4);
    if (c) { p = q; }
    p[4] = 0;
}
"""

SHADOW_SCOPE_EXIT = r"""
#include <stdlib.h>
void touch(void) {
    char *p;
    { char *p; p = malloc(4); p[3] = 0; }
    p = malloc(8);
    p[8] = 0;
}
"""

MULTI_ALLOCATION_BUDGET = r"""
#include <stdlib.h>
void sink(void) { }
void touch(int c) {
    char *p;
    if (c) { p = malloc(8); }
    else { p = malloc(4); sink(); sink(); }
    p[4] = 0;
}
"""

SAMELINE_REBINDING = r"""
#include <stdlib.h>
void touch(char *q) {
    char *p = malloc(4); p = q;
    p[4] = 0;
}
"""

NON_BARE_REBINDING = r"""
#include <stdlib.h>
void touch(char *q) {
    char *p = malloc(4);
    p = q + 1;
    p[4] = 0;
}
"""

MERGE_REBINDING = r"""
#include <stdlib.h>
void sink(void) { }
void touch(char *q, int c) {
    char *p = malloc(4);
    if (c) { sink(); }
    p = q;
    p[4] = 0;
}
"""

NESTED_CONDITIONAL_REBINDING = r"""
#include <stdlib.h>
void sink(void) { }
void touch(char *q, int c) {
    char *p = malloc(4);
    if (c) { sink(); p = q; }
    p[4] = 0;
}
"""

JOINT_REBINDING = r"""
#include <stdlib.h>
void touch(char *q, char *r, int c) {
    char *p = malloc(4);
    if (c) { p = q; } else { p = r; }
    p[4] = 0;
}
"""

CHECK_GUARD_REBINDING = r"""
#include <stdlib.h>
void touch(char *q, int *guard) {
    char *p = malloc(4);
    if (guard) { p = q; }
    p[4] = 0;
}
"""

REBINDING_BUDGET = r"""
#include <stdlib.h>
void touch(char *q, int c) {
    char *p = malloc(4);
    if (c) { p = q; }
    p[4] = 0;
}
"""

INNER_SHADOW_RELEASE = r"""
#include <stdlib.h>
void touch(void) {
    char *p = malloc(4);
    { char *p = malloc(8); free(p); }
    p[4] = 0;
}
"""

SHADOW_RELEASE = r"""
#include <stdlib.h>
void touch(void) {
    char *p = malloc(4);
    { char *p = malloc(8); p[0] = 0; }
    free(p);
    p[4] = 0;
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

    def test_valid_dynamic_and_negative_indices(self) -> None:
        self.build(BOUNDS_MATRIX)
        env = self.query()
        candidates = [c for c in env["candidates"]
                      if c["query"] == "out_of_bounds_write"]
        # #104 publishes negative constant indices, so `a[-1]` is a candidate.
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["metadata"]["index"], -1)
        self.assertEqual(candidates[0]["metadata"]["extent"], 4)
        exclusions = env["coverage"]["exclusions"]
        self.assertGreaterEqual(exclusions.get("valid", 0), 2)
        self.assertGreaterEqual(exclusions.get("dynamic_index", 0), 1)

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

    def test_shadowed_pointers_do_not_share_extents(self) -> None:
        for body, expected_extent in (
            (SHADOWED_OUTER_OOB, 4),
            (SHADOWED_INNER_OOB, 4),
        ):
            with self.subTest(body=body[:40]):
                self.setUp()
                self.build(body)
                candidates = self.candidates()
                self.assertEqual(len(candidates), 1)
                self.assertEqual(candidates[0]["metadata"]["extent"], expected_extent)
                self.tearDown()

    def test_cross_translation_unit_static_functions_are_isolated(self) -> None:
        write(self.root, "src/a.c", CROSS_TU_A)
        write(self.root, "src/b.c", CROSS_TU_B)
        full_index(self.root, self.database)
        analyze_scope(self.root, "src", ("defect",), database=self.database)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]["metadata"]["anchor_span"]["relative_path"], "src/a.c")
        self.assertEqual(candidates[0]["metadata"]["extent"], 4)

    def test_plain_reassignment_kills_the_old_allocation(self) -> None:
        self.build(PLAIN_REASSIGNMENT)
        env = self.query(confidence_gate=None)
        self.assertEqual(
            [c for c in env["candidates"] if c["query"] == "out_of_bounds_write"],
            [])
        self.assertGreaterEqual(
            env["coverage"]["exclusions"].get("reassigned", 0), 1)

    def test_branch_allocation_still_proves_the_shorter_path(self) -> None:
        self.build(BRANCH_ALLOCATION)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["metadata"]["extent"], 4)
        self.assertTrue(candidates[0]["paths"])

    def test_conditional_release_does_not_hide_the_free_path(self) -> None:
        self.build(CONDITIONAL_RELEASE)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["metadata"]["extent"], 4)

    def test_heap_memory_api_uses_the_allocation_extent(self) -> None:
        self.build(HEAP_MEMORY_API)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["metadata"]["facets"], ["M8", "M6"])
        self.assertEqual(candidate["metadata"]["index"], 8)
        self.assertEqual(candidate["metadata"]["extent"], 4)

    def test_path_budget_downgrades_reachability(self) -> None:
        self.build(BUDGETED_PATH)
        constrained = self.query(max_hops=1, max_paths=1)
        limited = [c for c in constrained["candidates"]
                   if c["query"] == "out_of_bounds_write"]
        self.assertEqual(len(limited), 1)
        self.assertEqual(limited[0]["resolution_status"], "ambiguous")
        self.assertEqual(limited[0]["paths"], [])
        self.assertTrue(any("budget" in item
                            for item in limited[0]["missing_evidence"]))
        unrestricted = [c for c in self.query()["candidates"]
                        if c["query"] == "out_of_bounds_write"]
        self.assertEqual(len(unrestricted), 1)
        self.assertEqual(unrestricted[0]["resolution_status"], "resolved")
        self.assertTrue(unrestricted[0]["paths"])

    def test_parameter_and_global_self_writes_are_not_rebindings(self) -> None:
        self.build(SELF_WRITE_POINTERS)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 2)
        self.assertEqual(
            sorted(candidate["metadata"]["extent"] for candidate in candidates),
            [4, 4])
        for candidate in candidates:
            self.assertEqual(candidate["resolution_status"], "resolved")
            self.assertNotIn(
                "nearest same-identity",
                " ".join(candidate["missing_evidence"]))

    def test_conditional_rebinding_keeps_the_unbound_path(self) -> None:
        self.build(CONDITIONAL_REBINDING)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["metadata"]["extent"], 4)

    def test_shadow_scope_exit_joins_the_outer_allocation(self) -> None:
        self.build(SHADOW_SCOPE_EXIT)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["metadata"]["extent"], 8)
        self.assertEqual(candidates[0]["metadata"]["index"], 8)

    def test_multi_allocation_budget_keeps_the_truncated_smaller_extent(self) -> None:
        self.build(MULTI_ALLOCATION_BUDGET)
        constrained = self.query(max_hops=2, max_paths=1)
        limited = [c for c in constrained["candidates"]
                   if c["query"] == "out_of_bounds_write"]
        self.assertEqual(len(limited), 1)
        self.assertEqual(limited[0]["resolution_status"], "ambiguous")
        self.assertEqual(limited[0]["metadata"]["extent"], 4)
        self.assertEqual(limited[0]["paths"], [])
        self.assertTrue(any("budget" in item
                            for item in limited[0]["missing_evidence"]))
        unrestricted = [c for c in self.query()["candidates"]
                        if c["query"] == "out_of_bounds_write"]
        self.assertEqual(len(unrestricted), 1)
        self.assertEqual(unrestricted[0]["resolution_status"], "resolved")
        self.assertEqual(unrestricted[0]["metadata"]["extent"], 4)

    def test_same_line_rebinding_still_kills_the_allocation(self) -> None:
        self.build(SAMELINE_REBINDING)
        env = self.query(confidence_gate=None)
        self.assertEqual(
            [c for c in env["candidates"] if c["query"] == "out_of_bounds_write"],
            [])
        self.assertGreaterEqual(
            env["coverage"]["exclusions"].get("reassigned", 0), 1)

    def test_non_bare_rebinding_still_kills_the_allocation(self) -> None:
        self.build(NON_BARE_REBINDING)
        env = self.query(confidence_gate=None)
        self.assertEqual(
            [c for c in env["candidates"] if c["query"] == "out_of_bounds_write"],
            [])
        self.assertGreaterEqual(
            env["coverage"]["exclusions"].get("reassigned", 0), 1)

    def test_unconditional_rebinding_after_a_merge_kills_the_allocation(self) -> None:
        self.build(MERGE_REBINDING)
        env = self.query(confidence_gate=None)
        self.assertEqual(
            [c for c in env["candidates"] if c["query"] == "out_of_bounds_write"],
            [])
        self.assertGreaterEqual(
            env["coverage"]["exclusions"].get("reassigned", 0), 1)

    def test_conditional_rebinding_after_a_call_keeps_the_other_path(self) -> None:
        self.build(NESTED_CONDITIONAL_REBINDING)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["metadata"]["extent"], 4)
        self.assertEqual(candidates[0]["metadata"]["index"], 4)

    def test_shadow_release_scope_is_an_explicit_uncertainty(self) -> None:
        # The fact layer publishes no scoped identity for a release, so a free
        # under a shadowed name cannot be attributed to one declaration. The
        # three-state answer is an ambiguous candidate with an explicit
        # limitation -- neither a resolved finding nor a silent drop.
        self.build(SHADOW_RELEASE)
        env = self.query(confidence_gate=None)
        accesses = [
            c for c in env["candidates"] if c["query"] == "out_of_bounds_write"
        ]
        self.assertEqual(len(accesses), 1)
        self.assertEqual(accesses[0]["resolution_status"], "ambiguous")
        self.assertTrue(any(
            "released declaration" in item
            for item in accesses[0]["missing_evidence"]))


    def test_joint_rebindings_on_all_arms_kill_the_allocation(self) -> None:
        self.build(JOINT_REBINDING)
        env = self.query(confidence_gate=None)
        self.assertEqual(
            [c for c in env["candidates"] if c["query"] == "out_of_bounds_write"],
            [])
        self.assertGreaterEqual(
            env["coverage"]["exclusions"].get("reassigned", 0), 1)

    def test_check_guard_rebinding_keeps_the_other_arm(self) -> None:
        self.build(CHECK_GUARD_REBINDING)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["metadata"]["extent"], 4)

    def test_rebinding_budget_downgrades_instead_of_excluding(self) -> None:
        self.build(REBINDING_BUDGET)
        constrained = self.query(max_hops=1, max_paths=1)
        limited = [c for c in constrained["candidates"]
                   if c["query"] == "out_of_bounds_write"]
        self.assertEqual(len(limited), 1)
        self.assertEqual(limited[0]["resolution_status"], "ambiguous")
        self.assertTrue(any("budget" in item
                            for item in limited[0]["missing_evidence"]))

    def test_inner_shadow_release_is_scope_ambiguous(self) -> None:
        self.build(INNER_SHADOW_RELEASE)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["resolution_status"], "ambiguous")
        self.assertTrue(any(
            "released declaration" in item
            for item in candidates[0]["missing_evidence"]))


if __name__ == "__main__":
    unittest.main()

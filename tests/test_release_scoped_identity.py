"""#138 tests: additive `subject_decl_scoped` on RELEASE.

The observation behind the issue: `char *p = malloc(4); { char *p = malloc(8);
free(p); } p[4] = 0;` and `... { char *p = malloc(8); ... } free(p); p[4] = 0;`
publish the same RELEASE/CALL facts. The frame-blind `subject_decl` reads
`local:p` for both the inner and the outer declaration, so a consumer cannot
tell which object was released.

The contract under test:

* `subject_decl` is unchanged (`local:p` for both shadowed declarations).
* `subject_decl_scoped` is the declaration index's scope-qualified token --
  the same spelling the access facts already carry as
  `memory_access_v1.object.scoped_decl` -- so the release and the access of the
  same declaration join on one identity.
* An unresolvable release name stays unknown: no guessed token, no annotation.
* The scoped token is additive: event ids, ordinals and ordering are untouched.
"""

import json
import tempfile
import unittest
from pathlib import Path

from provenlattice.analysis_query import query_analysis
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


SHADOW_BOTH_DIRECTIONS = """\
#include <stdlib.h>
void inner_free(void) {
    char *p = malloc(4);
    {
        char *p = malloc(8);
        free(p);
    }
    p[4] = 0;
}
void outer_free(void) {
    char *p = malloc(4);
    {
        char *p = malloc(8);
        p[0] = 0;
    }
    free(p);
    p[4] = 0;
}
void no_shadow(void) {
    char *p = malloc(4);
    free(p);
    p[4] = 0;
}
"""

UNRESOLVED_AND_UNSCOPED = """\
#include <stdlib.h>
int global_buffer;
void unresolved(void) {
    free(undeclared_var);
}
void global_release(void) {
    free(global_buffer);
}
"""

STATEMENT_HEAD_SHADOWS = """\
#include <stdlib.h>
void for_init_shadow(void) {
    char *p = malloc(4);
    for (char *p = malloc(8); p; p = 0) {
        free(p);
    }
    free(p);
    p[4] = 0;
}
void if_init_shadow(void) {
    char *p = malloc(4);
    if (char *p = malloc(8)) {
        free(p);
    }
    free(p);
    p[4] = 0;
}
void while_init_shadow(void) {
    char *p = malloc(4);
    while (char *p = malloc(8)) {
        free(p);
        break;
    }
    free(p);
    p[4] = 0;
}
void switch_init_shadow(void) {
    char *p = malloc(4);
    switch (char *p = malloc(8)) {
    default:
        free(p);
        break;
    }
    free(p);
    p[4] = 0;
}
"""

OUT_OF_LINE_MEMBER = """\
#include <stdlib.h>
struct S { char *p; };
void S::m(void) {
    free(p);
}
"""


def _materialize(source: str) -> tuple[str, list[dict]]:
    """Run the real pipeline and return (normalized source, events)."""
    normalized = "\n".join(source.strip().splitlines()) + "\n"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        path = root / "src" / "a.cpp"
        path.parent.mkdir(parents=True)
        path.write_bytes(normalized.encode())
        database = Path(td) / "graph.db"
        full_index(root, database)
        analyze_scope(root, "src", ("sparse_cfg",), database=database)
        env = query_analysis(
            root, "sparse_cfg", file_path="src/a.cpp", database=database
        )
    assert env["status"] == "available", env.get("reason")
    return normalized, env["events"]


def _release(events: list[dict], function: str) -> dict:
    matches = [
        event for event in events
        if event["event_type"] == "RELEASE"
        and event["owner_qualified_name"] == function
    ]
    assert len(matches) == 1, (function, len(matches))
    return matches[0]


def _releases(events: list[dict], function: str) -> list[dict]:
    """All RELEASE events of one function, in source order."""
    return sorted(
        (
            event for event in events
            if event["event_type"] == "RELEASE"
            and event["owner_qualified_name"] == function
        ),
        key=lambda event: event["start_byte"],
    )


def _access(events: list[dict], function: str, matched: str) -> dict:
    matches = [
        event for event in events
        if event["event_type"] == "DEREFERENCE"
        and event["owner_qualified_name"] == function
        and event["matched_name"] == matched
    ]
    assert len(matches) == 1, (function, matched, len(matches))
    return matches[0]


class ReleaseScopedIdentityTests(unittest.TestCase):
    """The additive scoped identity on RELEASE."""

    def test_both_shadow_directions_get_their_own_declaration(self) -> None:
        source, events = _materialize(SHADOW_BOTH_DIRECTIONS)
        outer_in_inner = source.index("char *p = malloc(4)")
        inner = source.index("char *p = malloc(8)")
        outer_in_outer = source.index(
            "char *p = malloc(4)", source.index("void outer_free")
        )
        inner_in_outer = source.index(
            "char *p = malloc(8)", source.index("void outer_free")
        )

        # `free(p)` inside the block releases the inner declaration, while the
        # later `p[4]` access names the outer one: the two must not collapse.
        inner_event = _release(events, "inner_free")
        self.assertEqual(inner_event["annotations"]["subject_decl"], "local:p")
        self.assertEqual(
            inner_event["annotations"]["subject_decl_scoped"],
            f"local:src/a.cpp:inner_free:p:{inner}",
        )
        inner_access = _access(events, "inner_free", "p[4]")
        access_object = json.loads(
            inner_access["annotations"]["memory_access_v1"]
        )["object"]
        self.assertEqual(
            access_object["scoped_decl"],
            f"local:src/a.cpp:inner_free:p:{outer_in_inner}",
        )
        self.assertNotEqual(
            inner_event["annotations"]["subject_decl_scoped"],
            access_object["scoped_decl"],
        )

        # `free(p)` after the block releases the outer declaration, and the
        # access of that same pointer carries the identical scoped token.
        outer_event = _release(events, "outer_free")
        self.assertEqual(outer_event["annotations"]["subject_decl"], "local:p")
        self.assertEqual(
            outer_event["annotations"]["subject_decl_scoped"],
            f"local:src/a.cpp:outer_free:p:{outer_in_outer}",
        )
        outer_access = _access(events, "outer_free", "p[4]")
        outer_object = json.loads(
            outer_access["annotations"]["memory_access_v1"]
        )["object"]
        self.assertEqual(
            outer_object["scoped_decl"],
            f"local:src/a.cpp:outer_free:p:{outer_in_outer}",
        )
        self.assertEqual(
            outer_event["annotations"]["subject_decl_scoped"],
            outer_object["scoped_decl"],
        )
        # The inner declaration exists and is distinct: the token is not just
        # echoing the access.
        self.assertNotEqual(
            outer_object["scoped_decl"],
            f"local:src/a.cpp:outer_free:p:{inner_in_outer}",
        )

    def test_no_shadow_keeps_one_identity(self) -> None:
        source, events = _materialize(SHADOW_BOTH_DIRECTIONS)
        declaration = source.index(
            "char *p = malloc(4)", source.index("void no_shadow")
        )
        release = _release(events, "no_shadow")
        self.assertEqual(release["annotations"]["subject_decl"], "local:p")
        self.assertEqual(
            release["annotations"]["subject_decl_scoped"],
            f"local:src/a.cpp:no_shadow:p:{declaration}",
        )
        access = _access(events, "no_shadow", "p[4]")
        object_fact = json.loads(access["annotations"]["memory_access_v1"])["object"]
        self.assertEqual(
            release["annotations"]["subject_decl_scoped"],
            object_fact["scoped_decl"],
        )

    def test_unresolved_release_stays_unknown_and_global_keeps_spelling(self) -> None:
        _source, events = _materialize(UNRESOLVED_AND_UNSCOPED)
        unresolved = _release(events, "unresolved")
        self.assertNotIn("subject_decl_scoped", unresolved["annotations"])
        self.assertEqual(unresolved["annotations"]["subject_from"], "argument")

        global_release = _release(events, "global_release")
        self.assertEqual(global_release["annotations"]["subject_decl"], "global:global_buffer")
        # Unambiguous storage classes keep the existing spelling.
        self.assertEqual(
            global_release["annotations"]["subject_decl_scoped"], "global:global_buffer"
        )

    def test_statement_head_shadows_release_the_right_declaration(self) -> None:
        source, events = _materialize(STATEMENT_HEAD_SHADOWS)
        for function in (
            "for_init_shadow", "if_init_shadow",
            "while_init_shadow", "switch_init_shadow",
        ):
            start = source.index(f"void {function}")
            outer = source.index("char *p = malloc(4)", start)
            inner = source.index("char *p = malloc(8)", start)
            releases = _releases(events, function)
            self.assertEqual(len(releases), 2, function)
            # The release inside the statement names the heading declaration;
            # the release after it names the outer one again. Reusing the
            # heading declaration after its statement would name an object the
            # release cannot reach.
            self.assertEqual(
                releases[0]["annotations"]["subject_decl_scoped"],
                f"local:src/a.cpp:{function}:p:{inner}",
                function,
            )
            self.assertEqual(
                releases[1]["annotations"]["subject_decl_scoped"],
                f"local:src/a.cpp:{function}:p:{outer}",
                function,
            )
            self.assertNotEqual(
                releases[0]["annotations"]["subject_decl_scoped"],
                releases[1]["annotations"]["subject_decl_scoped"],
                function,
            )
            access = _access(events, function, "p[4]")
            object_fact = json.loads(
                access["annotations"]["memory_access_v1"]
            )["object"]
            self.assertEqual(
                releases[1]["annotations"]["subject_decl_scoped"],
                object_fact["scoped_decl"],
                function,
            )

    def test_out_of_line_member_release_keeps_field_identity(self) -> None:
        _source, events = _materialize(OUT_OF_LINE_MEMBER)
        release = _release(events, "S.m")
        self.assertEqual(release["annotations"]["subject_decl"], "field:S:p")
        self.assertEqual(
            release["annotations"]["subject_decl_scoped"], "field:S:p"
        )

    def test_scoped_annotation_is_purely_additive(self) -> None:
        _source, events = _materialize(SHADOW_BOTH_DIRECTIONS)
        releases = [e for e in events if e["event_type"] == "RELEASE"]
        self.assertEqual([e["ordinal"] for e in releases], [0, 0, 0])
        self.assertEqual(
            {e["owner_qualified_name"] for e in releases},
            {"inner_free", "outer_free", "no_shadow"},
        )
        self.assertTrue(all(e["event_id"].startswith("event:") for e in releases))
        self.assertEqual(len({e["event_id"] for e in releases}), len(releases))
        # The new key is actually published where a declaration resolves.
        self.assertTrue(
            all("subject_decl_scoped" in e["annotations"] for e in releases)
        )
        # Only RELEASE carries the new key; ALLOC identity is untouched.
        for event in events:
            if event["event_type"] == "ALLOC":
                self.assertNotIn("subject_decl_scoped", event["annotations"])


if __name__ == "__main__":
    unittest.main()

"""I1-A semantic event correctness tests (level-0 vocabulary events).

Covers the eight required verification areas: CALL vs call semantics,
ALLOC/RELEASE binding, LOCK/UNLOCK provenance, C/C++ differences, same-name /
local / macro / single-line scenarios, stable identity, incremental freshness,
and malformed-parse degradation -- plus default-index isolation and reuse.
"""

import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import sqlite3

from provenlattice.analysis_query import query_analysis
from provenlattice.graph import full_index
from provenlattice.incremental import incremental_update
from provenlattice.orchestrator import analyze_scope


def write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


class EventsTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.database = Path(self.temp.name) / "graph.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build_index(self) -> None:
        full_index(self.root, self.database)

    def analyze_events(self) -> dict:
        return analyze_scope(self.root, "src", ("events",), database=self.database)

    def events(self, relative: str) -> list[dict]:
        env = query_analysis(self.root, "events", file_path=relative,
                             database=self.database)
        self.assertEqual(env["status"], "available", env.get("reason"))
        self.assertEqual(env["coverage"].get("level"), "level0")
        return env["events"]

    def events_of_type(self, relative: str, event_type: str) -> list[dict]:
        return [e for e in self.events(relative) if e["event_type"] == event_type]


class CallVsCallSemanticsTests(EventsTestBase):
    SOURCES = {
        "src/calls.c": (
            "void target01(void) {}\n"
            "void caller01(void) { target01(); }\n"
            "typedef int (*handler01_t)(int);\n"
            "int run01(handler01_t h, int x) { return h(x); }\n"
            "void mystery01(void);\n"
            "void caller02(void) { mystery01(); }\n"
        ),
    }

    def setUp(self) -> None:
        super().setUp()
        for relative, value in self.SOURCES.items():
            write(self.root, relative, value)
        self.build_index()
        self.analyze_events()

    def test_call_events_bound_to_real_symbols(self) -> None:
        calls = self.events_of_type("src/calls.c", "CALL")
        # target01, h(x) indirect, mystery01 -- one CALL per call expression
        self.assertEqual(len(calls), 3)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT id, name FROM nodes WHERE kind='Function'").fetchall()
        symbol_ids = {r["name"]: r["id"] for r in rows}
        owner_names = {e["owner_qualified_name"] for e in calls}
        self.assertIn("caller01", owner_names)
        self.assertIn("run01", owner_names)
        self.assertIn("caller02", owner_names)
        for event in calls:
            self.assertTrue(event["owner_symbol_id"].startswith("symbol:"))
            self.assertIn(event["owner_symbol_id"], set(symbol_ids.values()))

    def test_call_events_do_not_claim_resolution(self) -> None:
        # The event layer records what the source spells; direct/indirect/
        # unresolved classification stays the call-semantics layer's job.
        # The indirect call `h(x)` must produce a CALL event carrying only
        # the syntactic fact, never a resolved target claim.
        run_calls = [e for e in self.events_of_type("src/calls.c", "CALL")
                     if e["owner_qualified_name"] == "run01"]
        self.assertEqual(len(run_calls), 1)
        self.assertEqual(run_calls[0]["matched_via"], "syntax")
        self.assertEqual(run_calls[0]["matched_name"], "call_expression")
        self.assertNotIn("resolved", run_calls[0]["matched_name"])
        # and the call-kind classification still lives in the reference layer
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            kinds = {
                r["raw_name"]: json.loads(r["metadata"]).get("call_kind")
                for r in connection.execute(
                    "SELECT raw_name, metadata FROM raw_references "
                    "WHERE reference_type='CALLS'")
            }
        self.assertEqual(kinds.get("h"), "indirect")
        self.assertEqual(kinds.get("target01"), "direct")

    def test_unresolved_call_still_yields_event(self) -> None:
        calls = [e for e in self.events_of_type("src/calls.c", "CALL")
                 if e["owner_qualified_name"] == "caller02"]
        self.assertEqual(len(calls), 1)


class AllocReleaseTests(EventsTestBase):
    def setUp(self) -> None:
        super().setUp()
        write(self.root, "src/res.c",
              "#include <stdlib.h>\n"
              "int res01(void) {\n"
              "    char *p = malloc(64);\n"
              "    char *q = calloc(8, 4);\n"
              "    free(p);\n"
              "    free(p);\n"
              "    free(q);\n"
              "    return 0;\n"
              "}\n")
        self.build_index()
        self.analyze_events()

    def test_alloc_release_recognized_and_bound(self) -> None:
        allocs = self.events_of_type("src/res.c", "ALLOC")
        releases = self.events_of_type("src/res.c", "RELEASE")
        # the query returns events in id order; ordinals carry source order
        self.assertEqual(sorted(a["matched_name"] for a in allocs),
                         ["calloc", "malloc"])
        self.assertEqual(len(releases), 3)
        self.assertEqual({r["matched_name"] for r in releases}, {"free"})
        self.assertEqual({a["owner_qualified_name"] for a in allocs}, {"res01"})
        self.assertEqual({r["owner_qualified_name"] for r in releases}, {"res01"})
        by_name = {a["matched_name"]: a for a in allocs}
        self.assertEqual(by_name["malloc"]["ordinal"], 0)
        self.assertEqual(by_name["calloc"]["ordinal"], 1)
        self.assertEqual(sorted(r["ordinal"] for r in releases), [0, 1, 2])

    def test_lines_point_at_the_source(self) -> None:
        source = (self.root / "src" / "res.c").read_text(encoding="utf-8").splitlines()
        for event in self.events("src/res.c"):
            if event["matched_via"] == "syntax":
                # a syntax-axis event names the node type, not a source token
                continue
            text = source[event["start_line"] - 1]
            self.assertIn(event["matched_name"], text)


class LockProvenanceTests(EventsTestBase):
    def setUp(self) -> None:
        super().setUp()
        write(self.root, "src/lock.c",
              "#include <pthread.h>\n"
              "pthread_mutex_t g_lock;\n"
              "int guarded01(int n) {\n"
              "    pthread_mutex_lock(&g_lock);\n"
              "    n += 1;\n"
              "    pthread_mutex_unlock(&g_lock);\n"
              "    return n;\n"
              "}\n")
        self.build_index()
        self.analyze_events()

    def test_lock_unlock_provenance(self) -> None:
        locks = self.events_of_type("src/lock.c", "LOCK")
        unlocks = self.events_of_type("src/lock.c", "UNLOCK")
        self.assertEqual([l["matched_name"] for l in locks], ["pthread_mutex_lock"])
        self.assertEqual([u["matched_name"] for u in unlocks], ["pthread_mutex_unlock"])
        for event in locks + unlocks:
            self.assertEqual(event["matched_via"], "calls")
            self.assertEqual(event["owner_qualified_name"], "guarded01")
            # the span points into the guarded function body, lines 4 and 6
            self.assertIn(event["start_line"], (4, 6))
            self.assertEqual(event["start_line"], event["end_line"])

    def test_ambiguous_keyword_is_flagged_not_resolved(self) -> None:
        write(self.root, "src/amb.c",
              "void wait01(void);\n"
              "int waiter01(int n) { WaitForSingleObject(wait01(), 1); return n; }\n")
        incremental_update(self.root, self.database)
        self.analyze_events()
        events = [e for e in self.events("src/amb.c")
                  if e["matched_name"] == "WaitForSingleObject"]
        self.assertEqual(len(events), 2)  # LOCK + THREAD_JOIN both claim it
        self.assertEqual({e["event_type"] for e in events}, {"LOCK", "THREAD_JOIN"})
        self.assertEqual([e["flags"] for e in events],
                         [["ambiguous_keyword"], ["ambiguous_keyword"]])


class CppDifferenceTests(EventsTestBase):
    def setUp(self) -> None:
        super().setUp()
        write(self.root, "src/raii.cc",
              "#include <thread>\n"
              "#include <mutex>\n"
              "void body01(void) {}\n"
              "int counter01 = 0;\n"
              "void spawner01(void) {\n"
              "    std::thread t(body01);\n"
              "    t.join();\n"
              "    counter01 += 1;\n"
              "}\n"
              "int lockstep01(void) {\n"
              "    std::mutex m;\n"
              "    std::lock_guard<std::mutex> guard(m);\n"
              "    return counter01;\n"
              "}\n")
        self.build_index()
        self.analyze_events()

    def test_cpp_raii_and_threads(self) -> None:
        spawns = self.events_of_type("src/raii.cc", "THREAD_SPAWN")
        joins = self.events_of_type("src/raii.cc", "THREAD_JOIN")
        locks = self.events_of_type("src/raii.cc", "LOCK")
        self.assertEqual(len(spawns), 1)
        # the qualified axis matches on the canonical spelling (:: -> .)
        self.assertEqual(spawns[0]["matched_name"], "std.thread")
        self.assertEqual(spawns[0]["matched_via"], "qualified")
        self.assertEqual(len(joins), 1)
        self.assertEqual(joins[0]["matched_name"], "join")
        # RAII acquisition is the construction site: no lock call in the body
        self.assertEqual(len(locks), 1)
        self.assertEqual(locks[0]["matched_name"], "std.lock_guard")

    def test_python_files_are_out_of_scope(self) -> None:
        write(self.root, "src/mod.py", "def f01():\n    return 1\n")
        self.build_index()
        result = self.analyze_events()
        self.assertIn(
            "src/mod.py",
            result["features"]["events"]["skipped"]["unsupported_language"])


class IdentityScenariosTests(EventsTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.body = (
            "#include <stdlib.h>\n"
            "int one01(int n) { int local01 = n; char *p = malloc(8); free(p); return local01; }\n"
            "int two01(int n) { return n; }\n"
        )
        write(self.root, "src/collapse.c", self.body)
        self.build_index()
        self.analyze_events()

    def test_single_line_function_binds_correct_owner(self) -> None:
        allocs = self.events_of_type("src/collapse.c", "ALLOC")
        self.assertEqual(len(allocs), 1)
        self.assertEqual(allocs[0]["owner_qualified_name"], "one01")

    def test_macro_invocation_is_a_syntactic_call_only(self) -> None:
        # `CALL13(foo13, 1)` parses as a call_expression, so the syntax axis
        # proposes a CALL event -- the same conservative fact the PR layer
        # records. The event carries no callee resolution; a macro invocation
        # and a real call are indistinguishable at this layer, and claiming
        # otherwise would be a name-only guess.
        write(self.root, "src/macro.c",
              "#define CALL13(fn, val) fn(val)\n"
              "void foo13(int x) { }\n"
              "void caller13(void) { CALL13(foo13, 1); }\n")
        incremental_update(self.root, self.database)
        self.analyze_events()
        calls = self.events_of_type("src/macro.c", "CALL")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["matched_via"], "syntax")
        self.assertEqual(calls[0]["matched_name"], "call_expression")

    def test_event_ids_survive_moving_a_function(self) -> None:
        before = {e["event_type"] + str(e["ordinal"]): e["event_id"]
                  for e in self.events("src/collapse.c")}
        # swap the two functions in the file (same symbols, new lines)
        write(self.root, "src/collapse.c",
              "#include <stdlib.h>\n"
              "int two01(int n) { return n; }\n"
              "int one01(int n) { int local01 = n; char *p = malloc(8); free(p); return local01; }\n")
        incremental_update(self.root, self.database)
        self.analyze_events()
        after = {e["event_type"] + str(e["ordinal"]): e["event_id"]
                 for e in self.events("src/collapse.c")}
        self.assertEqual(after, before)

    def test_repeat_builds_are_deterministic(self) -> None:
        first = [e["event_id"] for e in self.events("src/collapse.c")]
        result = self.analyze_events()
        self.assertEqual(result["features"]["events"]["reused"], ["src/collapse.c"])
        second = [e["event_id"] for e in self.events("src/collapse.c")]
        self.assertEqual(first, second)


class FreshnessTests(EventsTestBase):
    def setUp(self) -> None:
        super().setUp()
        write(self.root, "src/fresh.c",
              "#include <stdlib.h>\n"
              "int f01(int n) { char *p = malloc(16); free(p); return n; }\n")
        self.build_index()
        self.analyze_events()

    def test_incremental_edit_extends_events(self) -> None:
        self.assertEqual(len(self.events_of_type("src/fresh.c", "ALLOC")), 1)
        write(self.root, "src/fresh.c",
              "#include <stdlib.h>\n"
              "int f01(int n) { char *p = malloc(16); free(p); return n; }\n"
              "int g01(int n) { char *q = malloc(32); free(q); return n; }\n")
        incremental_update(self.root, self.database)
        result = self.analyze_events()
        self.assertEqual(result["features"]["events"]["materialized"], ["src/fresh.c"])
        allocs = self.events_of_type("src/fresh.c", "ALLOC")
        self.assertEqual(len(allocs), 2)
        self.assertEqual({a["owner_qualified_name"] for a in allocs}, {"f01", "g01"})

    def test_source_hash_change_invalidates_cache(self) -> None:
        # insert a comment line so the function (and its event span) moves;
        # a stale cache would keep reporting the old line
        write(self.root, "src/fresh.c",
              "#include <stdlib.h>\n"
              "/* moved down one line */\n"
              "int f01(int n) { char *p = malloc(16); free(p); return n; }\n")
        incremental_update(self.root, self.database)
        env = query_analysis(self.root, "events", file_path="src/fresh.c",
                             database=self.database)
        self.assertEqual(env["status"], "stale")
        result = self.analyze_events()
        self.assertEqual(result["features"]["events"]["materialized"], ["src/fresh.c"])
        allocs = self.events_of_type("src/fresh.c", "ALLOC")
        self.assertEqual(len(allocs), 1)
        self.assertEqual(allocs[0]["start_line"], 3)


class MalformedParseTests(EventsTestBase):
    def setUp(self) -> None:
        super().setUp()
        write(self.root, "src/broken.c",
              "#include <stdlib.h>\n"
              "int good01(int n) { char *p = malloc(8); free(p); return n; }\n"
              "int broken01(int n) { char *q = malloc(16) free(q); return n; }\n")
        self.build_index()
        result = self.analyze_events()
        self._result = result

    def test_partial_parse_degrades_and_still_extracts(self) -> None:
        self.assertEqual(self._result["status"], "complete")
        events = self.events("src/broken.c")
        types = {e["event_type"] for e in events}
        self.assertIn("ALLOC", types)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT s.metadata FROM analysis_state s JOIN files f "
                "ON f.file_id=s.file_id WHERE f.path='src/broken.c' "
                "AND s.feature='events:cpp'").fetchone()
        metadata = json.loads(row["metadata"])
        self.assertEqual(metadata["analysis_status"], "degraded")


class DefaultIsolationTests(EventsTestBase):
    def test_default_index_produces_no_events(self) -> None:
        write(self.root, "src/plain.c",
              "#include <stdlib.h>\n"
              "int p01(int n) { char *p = malloc(8); free(p); return n; }\n")
        self.build_index()
        with closing(sqlite3.connect(self.database)) as connection:
            tables = {r[0] for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("semantic_events", tables)
        self.assertNotIn("semantic_edges", tables)
        self.assertNotIn("analysis_state", tables)
        env = query_analysis(self.root, "events", file_path="src/plain.c",
                             database=self.database)
        self.assertEqual(env["status"], "not_built")
        self.assertEqual(env["reason"], "analysis_not_built")

    def test_repeat_request_reuses_cache(self) -> None:
        write(self.root, "src/plain.c",
              "#include <stdlib.h>\n"
              "int p01(int n) { char *p = malloc(8); free(p); return n; }\n")
        self.build_index()
        first = self.analyze_events()
        self.assertEqual(first["features"]["events"]["materialized"], ["src/plain.c"])
        second = self.analyze_events()
        self.assertEqual(second["features"]["events"]["reused"], ["src/plain.c"])
        self.assertEqual(second["features"]["events"]["materialized"], [])


if __name__ == "__main__":
    unittest.main()

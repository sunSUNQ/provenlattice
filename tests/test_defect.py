"""Stage 4 acceptance: the typed defect queries over the sparse graph.

Every test here drives the *published* artifacts -- `graph.build_graph` output
for the synthetic cases, `full_index` for the fixture and the query layer --
because the publisher is what a user's database contains. A test that agreed
with a private reimplementation while the publisher disagreed would be worse
than no test.

The three-state vocabulary these tests use is the graph's, never the model's:
`resolved` / `ambiguous` / `unresolved` say what the *graph* decided about a
decisive relation, and they are never silently upgraded. What an AI judge
concludes (`confirmed` / `likely` / `insufficient evidence` / `rejected`) lives
only in the review sheet's annotation block, and no test here asserts on it.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from tests.test_sparsecfg import publish
except ImportError:  # `unittest discover -s tests` puts the directory on sys.path.
    from test_sparsecfg import publish

from experiments.defect_v1 import build_review

from provenlattice import cli, defect
from provenlattice.evidence import parse_evidence_citations
from provenlattice.graph import full_index
from provenlattice.overlay import OverlayStore
from provenlattice.query import GraphQuery
from provenlattice.sparsecfg import leaked_allocations, materialize_points, unreleased_resources
from provenlattice.storage import SQLiteStorage

REPO = "defect-repo"
FIXTURE = "tests/fixture_knowledge"


def annotations_by_type(events, edges) -> dict[str, list[dict]]:
    """Published point metadata keyed by event type, in event-id order.

    Built from `materialize_points` rather than from the events directly, so
    the tests read the same view the queries read -- a key that exists on the
    event but not in the point record would be invisible to every query.
    """
    table: dict[str, list[dict]] = {}
    for point_id, info in sorted(materialize_points(events, edges).items()):
        table.setdefault(info["event_type"], []).append({"point": point_id, **info})
    return table


def only(table: dict[str, list[dict]], event_type: str) -> dict:
    rows = table.get(event_type, [])
    assert len(rows) == 1, f"expected one {event_type}, got {len(rows)}"
    return rows[0]


def _event(event_id: str, owner: str, subject: str, line: int) -> dict:
    """One hand-built event row, as the queries receive it from SQLite.

    Ids are chosen rather than hashed because a test that needs a particular
    ordering of ids cannot get one out of a content hash. `metadata` stays JSON
    text, which is what the pipeline reads back.
    """
    return {
        "event_id": event_id, "event_type": "ALLOC", "owner_symbol_id": owner,
        "file_id": "file:unit", "ordinal": 1, "start_line": line, "end_line": line,
        "matched_name": "malloc", "matched_via": "calls", "flags": "",
        "metadata": json.dumps({
            "subject": subject, "subject_from": "assignment",
            "subject_exact": "true", "relative_path": "src/unit.cpp",
        }),
    }


def fixture_graph(test: unittest.TestCase):
    """The fixture through the real publisher, read back from SQLite.

    Events come from the database rather than from `build_graph`'s return
    value on purpose: the queries have to work on what a user's database
    holds, and the two differ in exactly the places that bite -- metadata is
    JSON text on the way in and a dict on the way out, and the exit ids only
    exist as edge endpoints.

    Returns `(events, edges, names)`, where `names` is the symbol-id to
    qualified-name table the events do not carry (identity is a hash, so a
    pure function cannot recover a name from it).
    """
    holder = tempfile.TemporaryDirectory()
    test.addCleanup(holder.cleanup)
    database = Path(holder.name) / "fixture.db"
    full_index(FIXTURE, database, repository_id_override="fixture")
    with SQLiteStorage(database) as storage:
        repo_id = storage.repository()["repo_id"]
        names = {
            row["id"]: row["qualified_name"]
            for row in storage.connection.execute(
                "SELECT id, qualified_name FROM nodes WHERE repo_id = ?", (repo_id,)
            )
        }
        return storage.semantic_events(repo_id), storage.semantic_edges(repo_id), names


class AnnotationChannelTests(unittest.TestCase):
    """The subject channel stage 4 widened: without these keys the typed
    queries have nothing to pair on. Stage 3 annotated ALLOC/RELEASE/CALL
    only, and every lock, spawn and return point carried an empty subject."""

    def publish_source(self, source: str):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return publish(Path(holder.name), "src/unit.cpp", source)

    def test_lock_subject_comes_from_the_first_argument(self) -> None:
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "void f() { pthread_mutex_lock(&g_index_lock); }\n"
        )
        lock = only(annotations_by_type(events, edges), "LOCK")
        self.assertEqual(lock["subject"], "g_index_lock")
        self.assertEqual(lock["subject_from"], "argument")

    def test_member_call_subject_comes_from_the_receiver(self) -> None:
        """`g_pool_lock.lock()` has no arguments at all, so the only name the
        source offers is the object the call is made on."""
        events, edges = self.publish_source(
            "#include <mutex>\n"
            "void f() { g_pool_lock.lock(); }\n"
        )
        lock = only(annotations_by_type(events, edges), "LOCK")
        self.assertEqual(lock["subject"], "g_pool_lock")
        self.assertEqual(lock["subject_from"], "receiver")

    def test_raii_declaration_subject_is_the_constructor_argument(self) -> None:
        """The subject is the mutex, not the handle: `guard` is a local whose
        identity is worthless to a lock-order query."""
        events, edges = self.publish_source(
            "#include <mutex>\n"
            "void f() { std::lock_guard<std::mutex> guard{g_pool_lock}; }\n"
        )
        lock = only(annotations_by_type(events, edges), "LOCK")
        self.assertEqual(lock["subject"], "g_pool_lock")
        self.assertEqual(lock["subject_from"], "raii")
        self.assertEqual(lock["raii"], "true")

    def test_the_parenthesised_raii_spelling_is_no_longer_a_gap(self) -> None:
        """`guard(m)` -- the spelling real C++ mostly writes -- reaches the CFG.

        It used to be the stage 4 registered gap: the declaration parses as a
        function declaration (the most-vexing-parse), so the symbol extractor
        promoted it to its own one-line Function symbol, the statement stopped
        belonging to the enclosing method, and the lock was attributed to a
        symbol that is not a function. The extractor now reads a declaration
        inside a body as the variable it is, so the lock belongs to `f` and the
        mutex is the constructor argument.
        """
        events, edges = self.publish_source(
            "#include <mutex>\n"
            "void f() { std::lock_guard<std::mutex> guard(g_pool_lock); }\n"
        )
        lock = only(annotations_by_type(events, edges), "LOCK")
        self.assertEqual(lock["subject"], "g_pool_lock")
        self.assertEqual(lock["subject_from"], "raii")
        self.assertEqual(lock["raii"], "true")
        # The point is inside `f`'s control flow, not stranded on a phantom:
        # stage 4's version of this test asserted the opposite.
        self.assertTrue([edge for edge in edges if edge.src_event_id == lock["point"]])

    def test_a_raii_argument_that_is_an_expression_is_not_a_phantom(self) -> None:
        """`guard(p->m)` parses as an ordinary declaration -- the most-vexing-
        parse needs a bare name to happen at all -- so it never was a phantom.
        It was still subject-less, because the initialiser is an
        `argument_list` and only `initializer_list` was unwrapped."""
        events, edges = self.publish_source(
            "#include <mutex>\n"
            "void f(Context *ctx) { std::lock_guard<std::mutex> guard(ctx->ctx_mutex); }\n"
        )
        lock = only(annotations_by_type(events, edges), "LOCK")
        self.assertEqual(lock["subject"], "ctx")
        self.assertEqual(lock["subject_from"], "raii")
        # A member path: `ctx` names the struct that holds the lock, not the
        # lock, so the subject is not the whole designation.
        self.assertEqual(lock["subject_exact"], "false")

    def test_a_two_declarator_raii_statement_claims_no_subject(self) -> None:
        """`a{m}, b{n}` acquires twice; naming one argument for both points
        would be a guess about which handle a lock point refers to. The RAII
        fact itself is still recorded, because that is what keeps the
        incomplete-cleanup query quiet about destructor-released locks."""
        events, edges = self.publish_source(
            "#include <mutex>\n"
            "void f() { std::lock_guard<std::mutex> a{m}, b{n}; }\n"
        )
        table = annotations_by_type(events, edges)
        self.assertEqual(len(table["LOCK"]), 2)
        for lock in table["LOCK"]:
            self.assertEqual(lock["subject"], "")
            self.assertEqual(lock["raii"], "true")

    def test_an_unbound_new_allocation_claims_no_subject(self) -> None:
        """`sink.emplace_back(new X(k));` binds nothing, and `k` is a different
        object from the allocation. Taking the constructor's first argument
        would attribute the candidate to `k` and call the identity resolved --
        which is what this rule did until a review sheet showed a leak
        candidate whose subject was `GGML_TYPE_F32`."""
        events, edges = self.publish_source(
            "#include <vector>\n"
            "void f(std::vector<X*> &sink, int k) { sink.emplace_back(new X(k)); }\n"
            "X *g(int k) { return new X(k); }\n"
        )
        table = annotations_by_type(events, edges)
        self.assertEqual(len(table["ALLOC"]), 2)
        for alloc in table["ALLOC"]:
            self.assertEqual(alloc["subject"], "")
            self.assertEqual(alloc["subject_from"], "")

    def test_a_bound_new_allocation_still_names_its_target(self) -> None:
        """The rule above must not fire when the source does name the object:
        `X *p = new X(k);` binds `p`, and that is the allocation's identity."""
        events, edges = self.publish_source(
            "#include <vector>\n"
            "void f(int k) { X *p = new X(k); }\n"
        )
        alloc = only(annotations_by_type(events, edges), "ALLOC")
        self.assertEqual(alloc["subject"], "p")
        self.assertEqual(alloc["subject_from"], "assignment")

    def test_a_name_that_is_a_path_root_is_recorded_as_inexact(self) -> None:
        """`&g_index_lock` names the lock; `&index->slot_locks[i]` names the
        struct that holds an array of them. Both recover a name, and only the
        first one identifies an object, so the annotation says which."""
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "void f(HNSW *index, int i) {\n"
            "  pthread_mutex_lock(&g_index_lock);\n"
            "  pthread_mutex_unlock(&g_index_lock);\n"
            "  pthread_mutex_lock(&index->slot_locks[i]);\n"
            "  pthread_mutex_unlock(&index->slot_locks[i]);\n"
            "}\n"
        )
        table = annotations_by_type(events, edges)
        self.assertEqual(
            [(row["subject"], row["subject_exact"]) for row in table["LOCK"]],
            [("g_index_lock", "true"), ("index", "false")],
        )

    def test_an_assignment_to_a_field_is_recorded_as_inexact(self) -> None:
        """The same distinction on the binding side: `p = malloc(n)` binds the
        name `p`, `s->buf = malloc(n)` binds a field of `s`, and two calls
        through the same parameter would otherwise share the name `s`."""
        events, edges = self.publish_source(
            "#include <stdlib.h>\n"
            "void f(struct S *s) {\n"
            "  char *p = (char *)malloc(8);\n"
            "  s->buf = (char *)malloc(8);\n"
            "  free(p);\n"
            "}\n"
        )
        table = annotations_by_type(events, edges)
        self.assertEqual(
            [(row["subject"], row["subject_exact"]) for row in table["ALLOC"]],
            [("p", "true"), ("s", "false")],
        )

    def test_return_subject_names_the_returned_value_only(self) -> None:
        """`return buffer;` hands the resource to the caller; `return -1;`
        names nothing. The difference is the whole reason the subject is
        recorded -- and it is what keeps an ordinary early return from reading
        as an ownership transfer."""
        events, edges = self.publish_source(
            "#include <stdlib.h>\n"
            "char *give(char *buffer) {\n"
            "  return buffer;\n"
            "}\n"
            "int fail(void) {\n"
            "  return -1;\n"
            "}\n"
            "int zero(void) {\n"
            "  return 0;\n"
            "}\n"
        )
        table = annotations_by_type(events, edges)
        subjects = sorted(row["subject"] for row in table["RETURN"])
        self.assertEqual(subjects, ["", "", "buffer"])

    def test_thread_spawn_records_target_and_thread_function(self) -> None:
        """The entry point sits in the third argument of `pthread_create`, and
        the table that says so is positional: a spawn whose name is absent from
        it gets no thread function rather than a guess."""
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "void *worker(void *);\n"
            "int f(pthread_t *handle) {\n"
            "  return pthread_create(handle, NULL, worker, NULL);\n"
            "}\n"
        )
        spawn = only(annotations_by_type(events, edges), "THREAD_SPAWN")
        self.assertEqual(spawn["subject"], "handle")
        self.assertEqual(spawn["subject_from"], "argument")
        self.assertEqual(spawn["thread_function"], "worker")

    def test_thread_spawn_of_a_qualified_type_names_the_declared_handle(self) -> None:
        """`std::thread t{fn};` is a declaration, not a call: the handle is the
        declared name and the entry point is the constructor argument."""
        events, edges = self.publish_source(
            "#include <thread>\n"
            "void *fn(void *);\n"
            "void f() { std::thread t{fn}; }\n"
        )
        spawn = only(annotations_by_type(events, edges), "THREAD_SPAWN")
        self.assertEqual(spawn["subject"], "t")
        self.assertEqual(spawn["thread_function"], "fn")

    def test_the_parenthesised_thread_declaration_is_no_longer_a_gap(self) -> None:
        """Same most-vexing-parse as the RAII gap above, and it falls to the
        same fix: the declaration binds `t` and the entry point is the
        constructor argument, exactly as in the brace spelling."""
        events, edges = self.publish_source(
            "#include <thread>\n"
            "void *fn(void *);\n"
            "void f() { std::thread t(fn); }\n"
        )
        spawn = only(annotations_by_type(events, edges), "THREAD_SPAWN")
        self.assertEqual(spawn["subject"], "t")
        self.assertEqual(spawn["thread_function"], "fn")

    def test_an_unknown_spawn_gets_no_thread_function(self) -> None:
        """A spawn whose argument position is unknown must not guess: a wrong
        edge is worse than a missing one, and `run_task(a, b)` says nothing
        about which argument is the entry point."""
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "void f() { run_task(alpha, beta); }\n"
        )
        table = annotations_by_type(events, edges)
        self.assertNotIn("THREAD_SPAWN", table)

    def test_leaked_allocations_is_the_alloc_spelling_of_unreleased_resources(self) -> None:
        """The stage 3 function survives the generalisation unchanged: same
        walk, same arguments, same answer."""
        source = (
            "#include <stdlib.h>\n"
            "int leak(void) {\n"
            "  char *buffer = (char *)malloc(256);\n"
            "  if (!buffer) { return -1; }\n"
            "  return 0;\n"
            "}\n"
            "int clean(void) {\n"
            "  char *buffer = (char *)malloc(256);\n"
            "  free(buffer);\n"
            "  return 0;\n"
            "}\n"
        )
        events, edges = self.publish_source(source)
        points = materialize_points(events, edges)
        old, old_truncated = leaked_allocations(edges, points)
        new, new_truncated = unreleased_resources(edges, points)
        self.assertEqual(old_truncated, new_truncated)
        self.assertEqual(
            [(path.points, path.types) for path in old],
            [(path.points, path.types) for path in new],
        )
        self.assertEqual(len(old), 1)


class DeclarationIdentityTests(unittest.TestCase):
    """Stage 4.5: a subject name is not an object.

    The annotation channel carried a *name* -- `n`, `index`, `g_pool_lock` --
    and every query joined on it, which is what made the race query return
    557,315 candidates for redis-50: two methods that each declare `int n` are
    two variables, and joining on the spelling says they are one. These tests
    cover the keys that replace the spelling with a declaration identity, and
    they read them the way the queries do, through `materialize_points`.
    """

    def publish_source(self, source: str):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return publish(Path(holder.name), "src/unit.cpp", source)

    def test_storage_class_separates_the_places_a_name_can_live(self) -> None:
        """One name, four objects: the parameter, the local, the file static
        and the global. The identity token has to tell them apart, because
        `int n` in one method and `int n` in another is the whole of the race
        query's false-positive population."""
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "static pthread_mutex_t g_static;\n"
            "pthread_mutex_t g_global;\n"
            "void f(pthread_mutex_t n) {\n"
            "  static pthread_mutex_t cache;\n"
            "  pthread_mutex_t local;\n"
            "  pthread_mutex_lock(&n);\n"
            "  pthread_mutex_lock(&local);\n"
            "  pthread_mutex_lock(&cache);\n"
            "  pthread_mutex_lock(&g_static);\n"
            "  pthread_mutex_lock(&g_global);\n"
            "}\n"
        )
        by_name = {row["subject"]: row for row in annotations_by_type(events, edges)["LOCK"]}
        self.assertEqual(
            [(name, by_name[name]["subject_storage"], by_name[name]["subject_decl"])
             for name in ("n", "local", "cache", "g_static", "g_global")],
            [
                ("n", "parameter", "parameter:n"),
                ("local", "local", "local:local"),
                ("cache", "function_static", "function_static:cache"),
                # A file static is per-file; a global is not. Two files that
                # mention the same global are naming the same object, and
                # splitting it by path would invent two objects where the
                # program has one -- so the static's token carries the path and
                # the global's does not.
                ("g_static", "file_static", "file_static:src/unit.cpp:g_static"),
                ("g_global", "global", "global:g_global"),
            ],
        )

    def test_a_reference_parameter_is_a_parameter(self) -> None:
        """The declarator shapes a parameter can arrive in.

        tree-sitter-cpp leaves a `reference_declarator`'s name unfielded --
        `Ctx & ctx` is `&` then `ctx` with no `declarator` field, where
        `Ctx * p` carries one -- so a walk that reads only the field drops
        every reference parameter. A reference is the ordinary way to pass a
        context object in C++, so the drop lands on exactly the names the race
        query reads: in llama.cpp it left `ctx` undeclared in 1,454 events,
        which the spelling fallback then merged into one subject across 401
        methods. This pins all five shapes, because the value of the test is
        that they agree.
        """
        events, edges = self.publish_source(
            "struct Ctx { pthread_mutex_t m; };\n"
            "void by_value(Ctx ctx) { pthread_mutex_lock(&ctx.m); }\n"
            "void by_pointer(Ctx *ctx) { pthread_mutex_lock(&ctx->m); }\n"
            "void by_reference(Ctx &ctx) { pthread_mutex_lock(&ctx.m); }\n"
            "void by_const_reference(const Ctx &ctx) { pthread_mutex_lock(&ctx.m); }\n"
            "void by_rvalue(Ctx &&ctx) { pthread_mutex_lock(&ctx.m); }\n"
        )
        table = annotations_by_type(events, edges)
        self.assertEqual(
            sorted(
                (row["start_line"], row["subject_storage"], row["subject_decl"], row["subject_type"])
                for row in table["LOCK"] if row["subject"] == "ctx"
            ),
            [
                (2, "parameter", "parameter:ctx", "Ctx"),
                (3, "parameter", "parameter:ctx", "Ctx"),
                (4, "parameter", "parameter:ctx", "Ctx"),
                (5, "parameter", "parameter:ctx", "Ctx"),
                (6, "parameter", "parameter:ctx", "Ctx"),
            ],
        )

    def test_a_local_is_resolved_at_the_position_it_is_used(self) -> None:
        """Position sensitivity, which is what makes the index a declaration
        index rather than a name table: `use(n)` inside the inner block reads
        the inner `int n`, and the one after it reads the parameter."""
        events, edges = self.publish_source(
            "void use(int n);\n"
            "void f(int n) {\n"
            "  { int n = 1; use(n); }\n"
            "  use(n);\n"
            "}\n"
        )
        table = annotations_by_type(events, edges)
        calls = [row for row in table["CALL"] if row["subject"] == "n"]
        self.assertEqual(
            [(row["start_line"], row["subject_decl"]) for row in calls],
            [(3, "local:n"), (4, "parameter:n")],
        )

    def test_a_member_path_keeps_two_locks_of_one_struct_apart(self) -> None:
        """The redis-50 shape: `index->slot_locks[i]` and `index->global_lock`
        share a root and share a type, and they are different locks. The path
        is kept as source text, so `slot_locks[0]` and `slot_locks[1]` stay
        apart too -- collapsing them to the member name would report an array
        of locks as one lock acquired twice."""
        events, edges = self.publish_source(
            "struct HNSW { pthread_mutex_t global_lock; pthread_mutex_t slot_locks[8]; };\n"
            "void f(HNSW *index, int i) {\n"
            "  pthread_mutex_lock(&index->global_lock);\n"
            "  pthread_mutex_lock(&index->slot_locks[i]);\n"
            "  pthread_mutex_lock(&index->slot_locks[i + 1]);\n"
            "}\n"
        )
        table = annotations_by_type(events, edges)
        # Source order, not id order: `annotations_by_type` sorts by the
        # hashed point id, which is stable but arbitrary.
        locks = sorted(table["LOCK"], key=lambda row: row["start_line"])
        self.assertEqual(
            [(row["subject_member"], row["subject_exact"]) for row in locks],
            # The path is source text with the whitespace removed, so `i + 1`
            # and `i+1` are one identity: a token that changes when someone
            # reformats an expression splits one object into two candidates.
            [("global_lock", "false"), ("slot_locks[i]", "false"), ("slot_locks[i+1]", "false")],
        )
        # All three hang off the one declared root, which is what the identity
        # is built from: `parameter:index#global_lock` and
        # `parameter:index#slot_locks[i]` are two objects, and both are capped
        # at `ambiguous` downstream because a member path is not a declaration.
        self.assertEqual({row["subject_decl"] for row in table["LOCK"]}, {"parameter:index"})

    def test_a_field_of_this_is_the_field_and_not_the_token_this(self) -> None:
        """`this->m_` and a bare `m_` inside a method are the same object, and
        neither is named `this`: the token would join every field of every
        class into one identity."""
        events, edges = self.publish_source(
            "struct Ctx {\n"
            "  pthread_mutex_t m_;\n"
            "  void a() { this->m_.lock(); }\n"
            "  void b() { m_.lock(); }\n"
            "};\n"
        )
        table = annotations_by_type(events, edges)
        self.assertEqual(
            [(row["subject"], row["subject_decl"], row["subject_storage"]) for row in table["LOCK"]],
            [("m_", "field:Ctx:m_", "field"), ("m_", "field:Ctx:m_", "field")],
        )
        self.assertTrue(all(row["subject_exact"] == "true" for row in table["LOCK"]))

    def test_a_name_the_file_does_not_declare_is_kept_as_unknown(self) -> None:
        """A macro, an enum constant, a global declared in a header this parser
        never sees. `unknown` is an answer and not a failure -- and the
        candidate must survive it: a cross-file global is the most important
        shared state a race query can see, so dropping it would lose the
        finding to save a number."""
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "void f(void) { pthread_mutex_lock(&g_total); }\n"
        )
        row = only(annotations_by_type(events, edges), "LOCK")
        self.assertEqual(row["subject"], "g_total")
        self.assertEqual(row["subject_storage"], "unknown")
        self.assertEqual(row["subject_decl"], "")

    def test_a_call_records_every_argument_not_only_the_first(self) -> None:
        """`RedisModule_SetKeyMeta(cls, key, new_str)` hands the resource over
        as the third argument. Recording only the first made the hand-off
        invisible, so the leak query called the allocation still-owned."""
        events, edges = self.publish_source(
            "void f(void *cls, void *key) {\n"
            "  char *buffer = (char *)malloc(8);\n"
            "  RedisModule_SetKeyMeta(cls, key, buffer);\n"
            "}\n"
        )
        table = annotations_by_type(events, edges)
        hand_off = [row for row in table["CALL"] if "\x1f" in row["arguments"]]
        self.assertEqual(len(hand_off), 1)
        self.assertEqual(hand_off[0]["arguments"].split("\x1f"), ["cls", "key", "buffer"])

    def test_a_later_argument_hand_off_caps_the_leak(self) -> None:
        """The stage 4 adjudication this closes: `RedisModule_SetKeyMeta(cls,
        key, buffer)` hands the resource over as its *third* argument, and a
        query that reads only the first one reported the allocation still-owned
        -- `resolved`, a false positive with the highest confidence the band
        has. The hand-off is now visible, and it caps rather than clears: a
        callee's ownership contract is still not in the graph.

        The second method is the falsification half: a local nobody passes
        anywhere stays `resolved`, so the cap is the hand-off and not the
        allocation."""
        events, edges = self.publish_source(
            "void f(void *cls, void *key) {\n"
            "  char *buffer = (char *)malloc(8);\n"
            "  RedisModule_SetKeyMeta(cls, key, buffer);\n"
            "}\n"
            "void g(void) {\n"
            "  char *plain = (char *)malloc(8);\n"
            "}\n"
        )
        result = defect.resource_lifetime(events, edges)
        by_name = {candidate.subject["name"]: candidate for candidate in result.candidates}
        self.assertEqual(sorted(by_name), ["buffer", "plain"])
        self.assertEqual(by_name["plain"].resolution_status, defect.RESOLVED)
        self.assertEqual(by_name["buffer"].resolution_status, defect.AMBIGUOUS)
        self.assertEqual(
            [fact["fact"] for fact in by_name["buffer"].uncertain_facts],
            ["OWNERSHIP_TRANSFER"],
        )
        self.assertIn("matched by spelling", by_name["buffer"].uncertain_facts[0]["detail"])

    def test_an_anonymous_allocation_is_identified_by_its_site(self) -> None:
        """`new X(k)` binds no name, so there is no name to resolve -- but it
        does have an identity, and the identity is the allocation site. That is
        what turns the candidate from *identity unknown* into *ownership
        unknown*, which is a question the ownership stage can act on."""
        events, edges = self.publish_source(
            "void f(int k) { sink(new X(k)); }\n"
            "void g(int k) { sink(new X(k)); }\n"
        )
        table = annotations_by_type(events, edges)
        sites = [row["subject_site"] for row in table["ALLOC"]]
        self.assertEqual(len(sites), 2)
        self.assertTrue(all(site for site in sites))
        self.assertNotEqual(sites[0], sites[1])
        self.assertEqual([row["subject"] for row in table["ALLOC"]], ["", ""])

    def test_the_identity_does_not_move_when_the_file_shifts(self) -> None:
        """The token is a declaration, not a position: inserting a blank line
        at the top of the file may not create a new object, or every candidate
        id would churn on every reformat."""
        source = (
            "static pthread_mutex_t g_pool_lock;\n"
            "void f(HNSW *index) {\n"
            "  pthread_mutex_lock(&g_pool_lock);\n"
            "  pthread_mutex_lock(&index->global_lock);\n"
            "}\n"
        )
        before, edges = self.publish_source(source)
        after, _ = self.publish_source("\n\n" + source)
        keys = ("subject", "subject_decl", "subject_storage", "subject_type",
                "subject_member", "subject_exact")
        self.assertEqual(
            [tuple(row[key] for key in keys) for row in annotations_by_type(before, edges)["LOCK"]],
            [tuple(row[key] for key in keys) for row in annotations_by_type(after, edges)["LOCK"]],
        )

    def test_the_identity_keys_do_not_collide_with_the_transport_keys(self) -> None:
        """`graph.py` splats the annotations *after* the file and shard keys,
        so a new key named `relative_path` would silently overwrite the file a
        point belongs to -- no error, no failing query, just the wrong path on
        every candidate."""
        events, edges = self.publish_source(
            "void f(HNSW *index) { pthread_mutex_lock(&index->global_lock); }\n"
        )
        lock = only(annotations_by_type(events, edges), "LOCK")
        self.assertEqual(lock["relative_path"], "src/unit.cpp")
        self.assertTrue(lock["file_id"])
        for key in ("subject_decl", "subject_storage", "subject_type",
                    "subject_member", "subject_site", "arguments"):
            self.assertIn(key, lock)


    def test_a_qualifier_macro_does_not_swallow_the_parameter(self) -> None:
        """`type * QUALIFIER name`, which neither grammar can parse.

        A macro between the `*` and the name is how C spells a restrict
        qualifier portably, and both grammars recover the same way: the macro
        becomes the declarator and the real name is pushed into an error node
        beside it. Read literally, `float * GGML_RESTRICT s` declares a
        parameter named `GGML_RESTRICT` and loses `s` -- which is the shape of
        every ggml kernel's output parameter, and therefore the name a race
        query is most likely to be reading when it looks at one. llama.cpp has
        2,148 of them and redis-50 has none.

        Both halves are pinned, because the recovery is only sound if it is
        narrow: the qualified parameter keeps its real name, and the plain
        pointer parameter beside it is untouched. The pair is the grammar's own
        error shape, so this is reading the parse back rather than guessing at
        C.

        The leading `int n` is not decoration. The recovery needs the parameter
        list to survive, and whether it does depends on the type of the first
        parameter: with a primitive type the function still parses and the
        error stays inside the list, while a type_identifier first makes the
        grammar read the whole function as a variable declaration and there is
        no list left to read. That second shape is the one function the
        recovery cannot reach; see the stage 4.5 record.
        """
        events, edges = self.publish_source(
            "void qualified(int n, pthread_mutex_t * GGML_RESTRICT m,\n"
            "                pthread_mutex_t *plain) {\n"
            "  pthread_mutex_lock(m);\n"
            "  pthread_mutex_lock(plain);\n"
            "}\n"
        )
        table = annotations_by_type(events, edges)["LOCK"]
        self.assertEqual(
            sorted((row["subject"], row["subject_storage"], row["subject_decl"])
                   for row in table),
            [
                ("m", "parameter", "parameter:m"),
                ("plain", "parameter", "parameter:plain"),
            ],
        )
        # The macro is a qualifier, not a name: nothing may be declared under
        # it, or the graph carries a parameter that does not exist.
        self.assertEqual(
            [row["subject"] for row in table if row["subject"] == "GGML_RESTRICT"], []
        )


class ResourceLifetimeTests(unittest.TestCase):
    """4.1 (memory leak) and the lock half of 4.6, one walk with two spellings.

    Every assertion here is about what the *graph* resolved, never about
    whether the code has a bug: a `resolved` candidate says the graph answered
    every decisive relation, and it says nothing about whether the leak is
    real.
    """

    def publish_source(self, source: str):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return publish(Path(holder.name), "src/unit.cpp", source)

    def test_the_fixture_leak_is_one_resolved_candidate(self) -> None:
        events, edges, names = fixture_graph(self)
        result = defect.resource_lifetime(events, edges, names=names)

        self.assertEqual(result.query, "resource_lifetime")
        self.assertEqual(result.keys, ("4.1", "4.6"))
        leaks = [candidate for candidate in result.candidates if candidate.defect_key == "4.1"]
        self.assertEqual(len(leaks), 1)
        leak = leaks[0]
        self.assertEqual(leak.subject["name"], "buffer")
        self.assertEqual(leak.subject["method"], "storage.load_index")
        self.assertEqual(leak.resolution_status, defect.RESOLVED)
        self.assertEqual(leak.confidence, 0.6)
        self.assertEqual(leak.uncertain_facts, ())

        # The path is what makes the candidate a candidate: an acquisition that
        # reaches the method's exit without releasing. Asserting both ends
        # rather than just the length, because either end alone is satisfiable
        # by the wrong path.
        self.assertEqual(len(leak.paths), 1)
        path = leak.paths[0]
        self.assertEqual(path["types"][0], "ALLOC")
        self.assertEqual(path["points"][-1], leak.metadata["exit_point"])
        self.assertTrue(leak.metadata["exit_point"].startswith("cfg-exit:"))

    def test_a_released_allocation_produces_no_candidate(self) -> None:
        """The falsification half: the same shape with a `free` on every path
        is not a candidate. Without this, a query that reported every
        allocation would pass the test above."""
        events, edges = self.publish_source(
            "#include <stdlib.h>\n"
            "int clean(void) {\n"
            "  char *buffer = (char *)malloc(256);\n"
            "  if (!buffer) { return -1; }\n"
            "  free(buffer);\n"
            "  return 0;\n"
            "}\n"
        )
        result = defect.resource_lifetime(events, edges)
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.truncated, False)
        self.assertEqual(result.coverage["acquire_points"], 1)
        self.assertEqual(result.coverage["candidates"], 0)

    def test_an_anonymous_new_allocation_is_ambiguous_not_unresolved(self) -> None:
        """An unbound `new` has no *name* but it does have an identity, and the
        identity is the allocation site -- that is what "this object" means for
        a value never bound to a variable.

        Stage 4 reported this `unresolved` with `SUBJECT_UNRESOLVED`, which said
        "the graph cannot attribute this candidate". It can: the missing fact
        is not which allocation this is, it is who owns the object. That is a
        question the ownership stage can act on, and reporting it as an absent
        identity hid it behind a word that means the graph failed.
        """
        events, edges = self.publish_source(
            "#include <vector>\n"
            "void f(std::vector<X*> &sink, int k) { sink.emplace_back(new X(k)); }\n"
        )
        result = defect.resource_lifetime(events, edges)
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.defect_key, "4.1")
        # Still no name: it really does not have one.
        self.assertEqual(candidate.subject["name"], "")
        self.assertTrue(candidate.subject["identity"].startswith("site:"))
        self.assertEqual(candidate.resolution_status, defect.AMBIGUOUS)
        self.assertEqual(candidate.confidence, 0.4)
        self.assertEqual(
            [fact["fact"] for fact in candidate.uncertain_facts], ["OWNERSHIP_UNKNOWN"]
        )

    def test_the_fixture_error_path_lock_is_one_resolved_candidate(self) -> None:
        """4.6's material on the fixture: `resize_pool` locks, allocates, and
        returns early when the allocation fails. The early return is what makes
        it a 4.6 candidate, and it is exactly the shape mode A excludes.

        Stage 4.5's one loosening shows here. The subject still comes from a
        receiver -- a name for an expression, not for the object -- but the
        receiver's declaration is in the file and says `std::mutex`, so the
        question stage 4 could not answer ("is this name a lock or a struct
        that holds one?") now has an answer. `pool->lock()` on an `HNSW *`
        still gets the old cap; only a declared mutex is lifted.
        """
        events, edges, names = fixture_graph(self)
        result = defect.resource_lifetime(events, edges, names=names)

        locks = [candidate for candidate in result.candidates if candidate.defect_key == "4.6"]
        self.assertEqual(len(locks), 1)
        lock = locks[0]
        self.assertEqual(lock.subject["name"], "g_pool_lock")
        self.assertEqual(lock.subject["method"], "storage.resize_pool")
        self.assertEqual(lock.subject["kind"], "lock")
        self.assertEqual(lock.resolution_status, defect.RESOLVED)
        self.assertEqual(lock.confidence, 0.6)

        facts = {fact["event"]: fact for fact in lock.facts}
        self.assertEqual(facts["LOCK"]["subject_from"], "receiver")
        self.assertEqual(lock.subject["type"], "mutex")
        self.assertEqual(lock.subject["storage"], "file_static")
        self.assertNotIn("LOCK_IDENTITY", [fact["fact"] for fact in lock.uncertain_facts])

        # And the leak this method also has is *not* a 4.1 candidate: the only
        # early return sits inside the null guard, where the allocation failed.
        self.assertEqual(
            [c.subject["name"] for c in result.candidates if c.defect_key == "4.1"],
            ["buffer"],
        )

    def test_a_member_named_lock_on_a_weak_ptr_is_not_a_lock(self) -> None:
        """`pipeline.lock()` on a `std::weak_ptr` returns a `shared_ptr`.

        The vocabulary matches the member name and the receiver is a smart
        pointer, so stage 4 reported a lock that was never taken. The declared
        type is what separates the two, and the discrimination is inside one
        file: the mutex next door is still a candidate, and it is `resolved`
        because its own declaration says what it is."""
        events, edges = self.publish_source(
            "#include <memory>\n"
            "#include <mutex>\n"
            "static std::mutex g_pool_lock;\n"
            "void guarded(std::weak_ptr<Ctx> pipeline) { pipeline.lock(); }\n"
            "void real_lock(void) { g_pool_lock.lock(); }\n"
        )
        result = defect.resource_lifetime(events, edges)
        locks = [candidate for candidate in result.candidates if candidate.defect_key == "4.6"]
        self.assertEqual([candidate.subject["name"] for candidate in locks], ["g_pool_lock"])
        self.assertEqual(locks[0].resolution_status, defect.RESOLVED)
        self.assertEqual(result.coverage["non_mutex_lock_points"], 1)
        # The lock-order walk sees the same universe, and the excluded point is
        # not an identity failure either: the graph answered, and the answer was
        # "this is not a lock".
        order = defect.lock_order(events, edges)
        self.assertEqual(order.coverage["non_mutex_lock_points"], 1)
        self.assertEqual(order.coverage["lock_points"], 1)
        self.assertEqual(order.coverage["unidentified_lock_points"], 0)

    def test_a_receiver_of_unknown_type_is_kept_and_capped(self) -> None:
        """The falsification half of the exclusion: a type the graph has not
        seen as a mutex is not evidence of anything.

        `pool->lock()` on an `HNSW *` is a genuine acquisition as far as the
        graph can tell -- a class wrapping a mutex behind `.lock()` is ordinary
        -- so it stays a candidate and carries the stage 4 cap. Excluding it
        would drop findings; the exclusion list is one entry long for this
        reason."""
        events, edges = self.publish_source(
            "struct HNSW { void lock(); };\n"
            "void f(HNSW *pool) { pool->lock(); }\n"
        )
        result = defect.resource_lifetime(events, edges)
        locks = [candidate for candidate in result.candidates if candidate.defect_key == "4.6"]
        self.assertEqual([candidate.subject["name"] for candidate in locks], ["pool"])
        self.assertEqual(locks[0].resolution_status, defect.AMBIGUOUS)
        self.assertEqual(locks[0].subject["type"], "HNSW")
        self.assertIn("LOCK_IDENTITY", [fact["fact"] for fact in locks[0].uncertain_facts])
        self.assertEqual(result.coverage["non_mutex_lock_points"], 0)

    def test_raii_locks_are_excluded_from_the_lock_walk(self) -> None:
        """`snapshot` has a LOCK and no UNLOCK, so the naive walk reports it.
        Its release is a destructor at scope exit -- a fact the CFG cannot see,
        and a false positive the query is allowed to drop because it can name
        the reason."""
        events, edges, names = fixture_graph(self)
        result = defect.resource_lifetime(events, edges, names=names)

        self.assertEqual(result.coverage["excluded_raii_locks"], 1)
        anchors = {candidate.anchor for candidate in result.candidates}
        snapshot_lock = [
            info for point_id, info in materialize_points(events, edges).items()
            if info["event_type"] == "LOCK" and info.get("raii") == "true"
        ]
        self.assertEqual(len(snapshot_lock), 1)
        self.assertNotIn(
            next(point_id for point_id, info in materialize_points(events, edges).items()
                 if info.get("raii") == "true"),
            anchors,
        )

    def test_returning_the_resource_caps_the_candidate_at_ambiguous(self) -> None:
        """`return buffer;` may hand ownership to the caller, so the graph can
        no longer say the resource was never released. `return -1;` names
        nothing and must not trigger the same doubt -- if it did, every leak in
        the repository would be downgraded and the state would carry no
        information."""
        events, edges = self.publish_source(
            "#include <stdlib.h>\n"
            "char *keep(void) {\n"
            "  char *buffer = (char *)malloc(256);\n"
            "  if (!buffer) { return NULL; }\n"
            "  return buffer;\n"
            "}\n"
            "int drop(void) {\n"
            "  char *buffer = (char *)malloc(256);\n"
            "  if (!buffer) { return -1; }\n"
            "  return -1;\n"
            "}\n"
        )
        result = defect.resource_lifetime(events, edges)
        # Keyed by the anchor's line rather than by method name: no names table
        # was supplied, so the subject's `method` is empty by design (identity
        # is a hash, and a pure function cannot invent a name from it).
        by_line = {
            candidate.metadata["anchor_span"]["start_line"]: candidate
            for candidate in result.candidates
        }
        self.assertEqual(sorted(by_line), [3, 8])

        kept = by_line[3]
        self.assertEqual(kept.subject["method"], "")
        self.assertEqual(kept.resolution_status, defect.AMBIGUOUS)
        self.assertIn("RETURN_TRANSFER", [fact["fact"] for fact in kept.uncertain_facts])
        transfer = next(f for f in kept.uncertain_facts if f["fact"] == "RETURN_TRANSFER")
        self.assertEqual(transfer["source"], "src/unit.cpp:5-5")

        dropped = by_line[8]
        self.assertEqual(dropped.resolution_status, defect.RESOLVED)
        self.assertEqual(dropped.uncertain_facts, ())

    def test_the_lock_half_can_be_switched_off(self) -> None:
        """`include_locks=False` is the mode A-only walk. It exists because the
        two modes have different disqualifiers, and a caller that only wants
        4.1 should not have to filter 4.6 candidates out afterwards."""
        events, edges, names = fixture_graph(self)
        only_allocations = defect.resource_lifetime(events, edges, names=names, include_locks=False)

        self.assertEqual(only_allocations.keys, ("4.1",))
        self.assertEqual(only_allocations.coverage["excluded_raii_locks"], 0)
        self.assertEqual(
            only_allocations.coverage["acquire_points"],
            sum(
                1 for info in materialize_points(events, edges).values()
                if info["event_type"] == "ALLOC"
            ),
        )
        self.assertEqual(
            [(c.subject["name"], c.resolution_status) for c in only_allocations.candidates],
            [("buffer", defect.RESOLVED)],
        )


class LockOrderTests(unittest.TestCase):
    """1.3 (inversion) and 1.4 (a lock taken twice without a release).

    The CFG's job here is narrow and worth stating: acquisition order is the
    method's lexical order, and the graph is asked only whether the first lock
    is *still held* when the second is taken. A pair whose only connection
    runs through a release is not a pair.
    """

    def publish_source(self, source: str):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return publish(Path(holder.name), "src/unit.cpp", source)

    def test_the_fixture_inversion_is_one_resolved_candidate(self) -> None:
        events, edges, names = fixture_graph(self)
        result = defect.lock_order(events, edges, names=names)

        self.assertEqual(result.query, "lock_order")
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.defect_key, "1.3")
        self.assertEqual(candidate.resolution_status, defect.RESOLVED)
        self.assertEqual(candidate.confidence, 0.7)

        # The pair is ordered as taken, not as sorted: the name is what the
        # candidate is about, and sorting it would make both directions of the
        # same inversion print identically.
        self.assertEqual(candidate.subject["locks"], ["g_index_lock", "g_log_lock"])
        self.assertEqual(candidate.subject["name"], "g_index_lock|g_log_lock")
        self.assertEqual(candidate.subject["method"], "storage.reindex")

        # Both sides, each with its own holding path. One side alone is not an
        # inversion, and a candidate carrying one path would not show it.
        facts = {(fact["side"], fact["role"]): fact for fact in candidate.facts}
        self.assertEqual(
            sorted({fact["method"] for fact in candidate.facts}),
            ["storage.flush_log", "storage.reindex"],
        )
        self.assertEqual(
            [(side, role, facts[(side, role)]["lock"], facts[(side, role)]["source"])
             for side, role in (("a", "first"), ("a", "second"), ("b", "first"), ("b", "second"))],
            [
                ("a", "first", "g_index_lock", "src/resource.cpp:48-48"),
                ("a", "second", "g_log_lock", "src/resource.cpp:49-49"),
                ("b", "first", "g_log_lock", "src/resource.cpp:56-56"),
                ("b", "second", "g_index_lock", "src/resource.cpp:57-57"),
            ],
        )
        self.assertTrue(all(fact["holding_confirmed"] for fact in candidate.facts))
        self.assertEqual(len(candidate.paths), 2)

        # Concurrency is the one thing the graph cannot answer, and it says so
        # on every 1.3 candidate rather than in a footnote.
        self.assertEqual(
            [fact["fact"] for fact in candidate.uncertain_facts], ["MAY_PARALLEL"]
        )
        self.assertEqual(candidate.uncertain_facts[0]["status"], defect.AMBIGUOUS)
        self.assertTrue(
            any("execution context" in line for line in candidate.missing_evidence)
        )

    def test_the_result_does_not_depend_on_input_order(self) -> None:
        """A candidate whose id moves when SQLite returns rows in a different
        order cannot be cited or adjudicated twice. Reversing both inputs is
        the cheapest way to catch an accidental dependence on iteration
        order."""
        events, edges, names = fixture_graph(self)
        forward = defect.lock_order(events, edges, names=names)
        backward = defect.lock_order(list(reversed(events)), list(reversed(edges)), names=names)
        self.assertEqual(
            [candidate.to_dict() for candidate in forward.candidates],
            [candidate.to_dict() for candidate in backward.candidates],
        )
        self.assertEqual(forward.coverage, backward.coverage)

    def test_a_repository_without_spawns_has_no_inversions(self) -> None:
        """Two methods taking the same locks in opposite orders is only a
        deadlock if something can run them at once. With no THREAD_SPAWN point
        anywhere, the graph can say they cannot -- the one form of
        `MAY_PARALLEL resolved = false` it can produce -- so the candidates are
        dropped and counted instead of reported as ambiguous."""
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "void first(void) {\n"
            "  pthread_mutex_lock(&a);\n"
            "  pthread_mutex_lock(&b);\n"
            "  pthread_mutex_unlock(&b);\n"
            "  pthread_mutex_unlock(&a);\n"
            "}\n"
            "void second(void) {\n"
            "  pthread_mutex_lock(&b);\n"
            "  pthread_mutex_lock(&a);\n"
            "  pthread_mutex_unlock(&a);\n"
            "  pthread_mutex_unlock(&b);\n"
            "}\n"
        )
        result = defect.lock_order(events, edges)
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.coverage["disqualified_no_threads"], 1)
        self.assertEqual(result.coverage["inverted_pairs"], 1)
        self.assertEqual(result.coverage["spawn_points"], 0)

    def test_a_second_acquisition_without_a_release_is_a_self_deadlock(self) -> None:
        """1.4: the same lock taken twice with nothing releasing it in between.
        `unlock` then `lock` again is not the pattern, and neither is a second
        acquisition the graph cannot show is reached while the lock is held."""
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "pthread_mutex_t m;\n"
            "void twice(void) {\n"
            "  pthread_mutex_lock(&m);\n"
            "  pthread_mutex_lock(&m);\n"
            "  pthread_mutex_unlock(&m);\n"
            "}\n"
            "void alternating(void) {\n"
            "  pthread_mutex_lock(&m);\n"
            "  pthread_mutex_unlock(&m);\n"
            "  pthread_mutex_lock(&m);\n"
            "  pthread_mutex_unlock(&m);\n"
            "}\n"
        )
        result = defect.lock_order(events, edges)
        self.assertEqual([candidate.defect_key for candidate in result.candidates], ["1.4"])
        candidate = result.candidates[0]
        self.assertEqual(candidate.subject["name"], "m")
        self.assertEqual(candidate.subject["identity"], "global:m")
        self.assertEqual(candidate.metadata["anchor_span"]["start_line"], 4)
        self.assertEqual(candidate.resolution_status, defect.RESOLVED)
        self.assertTrue(all(fact["holding_confirmed"] for fact in candidate.facts))

        # A recursive mutex makes this legal, which is a fact about the mutex
        # the graph does not hold -- so it is named rather than assumed away.
        self.assertIn(
            "MUTEX_RECURSIVE", [fact["fact"] for fact in candidate.uncertain_facts]
        )
        self.assertIn("PTHREAD_MUTEX_RECURSIVE", candidate.missing_evidence[0])
        self.assertEqual(result.coverage["reentrant_acquires"], 1)
        self.assertEqual(result.coverage["lock_points"], 4)


    def test_two_locks_named_by_the_same_root_are_not_a_self_deadlock(self) -> None:
        """The redis-50 shape, found by reading a generated review sheet:
        `pthread_mutex_trylock(&index->slot_locks[i])` and
        `pthread_rwlock_rdlock(&index->global_lock)` both recover the name
        `index`, and stage 4 called the pair a re-entrant acquisition of one
        lock. They are two locks behind one name. The member path is part of
        the identity, so the two are two objects and there is no re-entrant
        acquisition left to report -- the candidate is gone rather than
        capped, which is the strongest form of the fix."""
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "int slot(HNSW *index) {\n"
            "  pthread_mutex_lock(&index->slot_locks[0]);\n"
            "  pthread_rwlock_rdlock(&index->global_lock);\n"
            "  pthread_rwlock_unlock(&index->global_lock);\n"
            "  pthread_mutex_unlock(&index->slot_locks[0]);\n"
            "  return 0;\n"
            "}\n"
        )
        result = defect.lock_order(events, edges)
        self.assertEqual([candidate.defect_key for candidate in result.candidates], [])

    def test_the_same_member_path_twice_is_still_a_self_deadlock(self) -> None:
        """The falsification half of the rule above: separating the paths must
        not separate a lock from itself. `slot_locks[0]` acquired twice without
        a release is one object taken twice, and the array is not what makes it
        two -- the *index* is."""
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "int slot(HNSW *index) {\n"
            "  pthread_mutex_lock(&index->slot_locks[0]);\n"
            "  pthread_mutex_lock(&index->slot_locks[0]);\n"
            "  pthread_mutex_unlock(&index->slot_locks[0]);\n"
            "  return 0;\n"
            "}\n"
        )
        result = defect.lock_order(events, edges)
        self.assertEqual([candidate.defect_key for candidate in result.candidates], ["1.4"])
        candidate = result.candidates[0]
        self.assertEqual(candidate.subject["name"], "index")
        self.assertIn("#slot_locks[0]", candidate.subject["identity"])
        # A path is not a plain designation, so the object is known and the
        # *element* is not: capped, never resolved.
        self.assertEqual(candidate.resolution_status, defect.AMBIGUOUS)
        self.assertIn("SUBJECT_PATH", [fact["fact"] for fact in candidate.uncertain_facts])

    def test_a_plain_global_lock_is_still_a_resolved_self_deadlock(self) -> None:
        """The falsification half of the declaration gate: `&g_lock` is the
        whole designation of a declared mutex, so it must stay `resolved`."""
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "pthread_mutex_t g_lock;\n"
            "void twice(void) {\n"
            "  pthread_mutex_lock(&g_lock);\n"
            "  pthread_mutex_lock(&g_lock);\n"
            "  pthread_mutex_unlock(&g_lock);\n"
            "}\n"
        )
        result = defect.lock_order(events, edges)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].subject["identity"], "global:g_lock")
        self.assertEqual(result.candidates[0].resolution_status, defect.RESOLVED)
        self.assertNotIn(
            "SUBJECT_PATH", [fact["fact"] for fact in result.candidates[0].uncertain_facts]
        )

    def test_a_lock_the_file_never_declares_is_capped_not_resolved(self) -> None:
        """A mutex declared in a header this parser does not read.

        The graph can see two acquisitions of one spelling and cannot see that
        they are one object, because the declaration is in a file it never
        looked at. Stage 4 called that resolved; the identity rule calls it
        ambiguous, and the candidate survives -- the conservative direction,
        since a cross-file lock is exactly the shared state worth reporting."""
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "void twice(void) {\n"
            "  pthread_mutex_lock(&g_lock);\n"
            "  pthread_mutex_lock(&g_lock);\n"
            "  pthread_mutex_unlock(&g_lock);\n"
            "}\n"
        )
        result = defect.lock_order(events, edges)
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.subject["identity"], "name:g_lock")
        self.assertEqual(candidate.resolution_status, defect.AMBIGUOUS)
        self.assertIn("IDENTITY_UNKNOWN", [fact["fact"] for fact in candidate.uncertain_facts])


class RaceConditionTests(unittest.TestCase):
    """1.1, the query where stage 4's falsifiability question gets its answer.

    Every candidate it produces is `ambiguous`, by construction and not by
    accident: MAY_PARALLEL is not a relation the graph holds, and the access
    kind is a syntactic proxy standing in for READ/WRITE events that do not
    exist. The tests below pin both the candidates it does find and the ones
    it cannot -- a shared variable that never reaches an event-bearing
    expression produces nothing at all, which is the recall limit the stage
    record states rather than hides.
    """

    def publish_source(self, source: str):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return publish(Path(holder.name), "src/unit.cpp", source)

    def test_a_write_and_a_read_across_two_methods_is_ambiguous(self) -> None:
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "#include <stdlib.h>\n"
            "static int *g_total;\n"
            "void *worker(void *arg) {\n"
            "  g_total = (int *)malloc(64);\n"
            "  return NULL;\n"
            "}\n"
            "int main(void) {\n"
            "  pthread_t handle;\n"
            "  pthread_create(&handle, NULL, worker, NULL);\n"
            "  free(g_total);\n"
            "  return 0;\n"
            "}\n"
        )
        result = defect.race_condition(events, edges)
        self.assertEqual(result.coverage["subjects_multi_method"], 1)
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.defect_key, "1.1")
        self.assertEqual(candidate.subject["name"], "g_total")
        self.assertEqual(candidate.resolution_status, defect.AMBIGUOUS)
        self.assertEqual(candidate.confidence, 0.5)
        self.assertEqual(candidate.paths, ())

        # Both sides are named as writes, which is what the syntactic proxy
        # sees: `malloc` allocates and `free` releases, and neither fact says
        # anything about reading or writing the pointee.
        self.assertEqual(
            sorted(candidate.metadata["access_kinds"].values()), ["write", "write"]
        )
        self.assertIn("write vs write", candidate.uncertain_facts[-1]["detail"])

        # Concurrency is named as the undecidable thing it is, with the
        # strongest reason the spawn points support: one method starts a thread.
        may_parallel = next(f for f in candidate.uncertain_facts if f["fact"] == "MAY_PARALLEL")
        self.assertEqual(may_parallel["status"], defect.AMBIGUOUS)
        self.assertEqual(may_parallel["detail"], "one of the methods starts a thread")

    def test_two_reads_are_not_a_race(self) -> None:
        """The one reliable filter left without READ/WRITE: if neither side
        binds the name, neither can be the writer. It is the reason a shared
        pointer checked for null in two methods does not fill the review sheet."""
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "#include <stdlib.h>\n"
            "static int *g_ptr;\n"
            "void *worker(void *arg) {\n"
            "  if (!g_ptr) { return NULL; }\n"
            "  return NULL;\n"
            "}\n"
            "int main(void) {\n"
            "  pthread_t handle;\n"
            "  pthread_create(&handle, NULL, worker, NULL);\n"
            "  if (!g_ptr) { return -1; }\n"
            "  return 0;\n"
            "}\n"
        )
        result = defect.race_condition(events, edges)
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.coverage["subjects_multi_method"], 1)
        self.assertEqual(result.coverage["read_read_pairs"], 1)

    def test_the_fixture_yields_no_race_candidates(self) -> None:
        """Not a shortcoming of the query: no name in the fixture is touched by
        two methods, so there is nothing to pair. The coverage block carries
        the denominators, which is what makes the zero readable as "nothing to
        find" rather than "the query did not run"."""
        events, edges, names = fixture_graph(self)
        result = defect.race_condition(events, edges, names=names)

        self.assertEqual(result.candidates, ())
        self.assertEqual(result.coverage["subjects_multi_method"], 0)
        self.assertGreater(result.coverage["subjects_considered"], 0)
        self.assertEqual(result.coverage["spawn_points"], 1)
        self.assertEqual(result.coverage["resolved_thread_functions"], 1)
        self.assertTrue(result.coverage["may_parallel_decided"])
        self.assertEqual(result.coverage["candidates"], 0)

    def test_one_shared_lock_on_both_sides_disqualifies(self) -> None:
        """Two methods that both hold `g_lock` around their access are not a
        race candidate -- this is the matrix's own disqualifying evidence, and
        it is decidable because domination is a control-flow question. The
        protection has to be *proved*: a lock taken somewhere in the method
        leaves the candidate standing."""
        protected = self.publish_source(
            "#include <pthread.h>\n"
            "#include <stdlib.h>\n"
            "static int *g_total;\n"
            "static pthread_mutex_t g_lock;\n"
            "void *worker(void *arg) {\n"
            "  pthread_mutex_lock(&g_lock);\n"
            "  g_total = (int *)malloc(64);\n"
            "  pthread_mutex_unlock(&g_lock);\n"
            "  return NULL;\n"
            "}\n"
            "int main(void) {\n"
            "  pthread_t handle;\n"
            "  pthread_create(&handle, NULL, worker, NULL);\n"
            "  pthread_mutex_lock(&g_lock);\n"
            "  free(g_total);\n"
            "  pthread_mutex_unlock(&g_lock);\n"
            "  return 0;\n"
            "}\n"
        )
        events, edges = protected
        result = defect.race_condition(events, edges)
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.coverage["disqualified_same_lock"], 1)

        # The falsification of the falsifier: drop one side's lock and the
        # candidate comes back, with the protected side reported as resolved
        # and the unprotected one as ambiguous.
        half = self.publish_source(
            "#include <pthread.h>\n"
            "#include <stdlib.h>\n"
            "static int *g_total;\n"
            "static pthread_mutex_t g_lock;\n"
            "void *worker(void *arg) {\n"
            "  g_total = (int *)malloc(64);\n"
            "  return NULL;\n"
            "}\n"
            "int main(void) {\n"
            "  pthread_t handle;\n"
            "  pthread_create(&handle, NULL, worker, NULL);\n"
            "  pthread_mutex_lock(&g_lock);\n"
            "  free(g_total);\n"
            "  pthread_mutex_unlock(&g_lock);\n"
            "  return 0;\n"
            "}\n"
        )
        events, edges = half
        partial = defect.race_condition(events, edges)
        self.assertEqual(len(partial.candidates), 1)
        protections = [
            fact for fact in partial.candidates[0].uncertain_facts
            if fact["fact"] == "PROTECTED_BY"
        ]
        self.assertEqual(
            sorted(fact["status"] for fact in protections),
            [defect.AMBIGUOUS, defect.RESOLVED],
        )
        self.assertEqual(partial.candidates[0].confidence, 0.4)

    def test_every_race_bundle_names_the_read_write_gap(self) -> None:
        """The DFG's decisive contribution has to travel with the candidate,
        not sit in a design document: a reader deciding whether this is a real
        race is told, on every bundle, that the access kind is a syntactic
        proxy and that a plain `counter++` produces no event at all."""
        events, edges = self.publish_source(
            "#include <pthread.h>\n"
            "#include <stdlib.h>\n"
            "static int *g_total;\n"
            "void *worker(void *arg) {\n"
            "  g_total = (int *)malloc(64);\n"
            "  return NULL;\n"
            "}\n"
            "int main(void) {\n"
            "  pthread_t handle;\n"
            "  pthread_create(&handle, NULL, worker, NULL);\n"
            "  free(g_total);\n"
            "  return 0;\n"
            "}\n"
        )
        result = defect.race_condition(events, edges)
        self.assertTrue(result.candidates)
        for candidate in result.candidates:
            first = candidate.missing_evidence[0]
            self.assertIn("READ/WRITE", first)
            self.assertIn("counter++", first)
            self.assertEqual(len(candidate.missing_evidence), 4)

    def test_the_pair_is_the_identity_not_the_larger_owner(self) -> None:
        """The anchor is the smaller *point* id and the discriminator has to
        identify the pair on its own, because the two orderings are unrelated:
        point ids are content hashes and so are owner ids, so the side an
        anchor came from can hold either owner id.

        Naming only the larger owner gave every pair that shared an anchor the
        same discriminator, and since the citation is built from (anchor,
        discriminator), the same evidence id: on redis-50, 889 distinct
        candidates minted one. The graph is hand-built here rather than
        published, because the collision needs the anchor's owner to be the
        larger one and no source text can promise a hash order.
        """
        events = [
            _event("event:001", "symbol:zz", "c", 10),
            _event("event:100", "symbol:aa", "c", 20),
            _event("event:200", "symbol:mm", "c", 30),
        ]
        names = {"symbol:aa": "A.a", "symbol:mm": "M.m", "symbol:zz": "Z.z"}
        result = defect.race_condition(events, [], names=names)

        self.assertEqual(len(result.candidates), 3)
        identities = {
            (candidate.defect_key, candidate.anchor, candidate.discriminator)
            for candidate in result.candidates
        }
        self.assertEqual(len(identities), 3)
        for candidate in result.candidates:
            # The subject's method and its owner are the anchor's, as they are
            # on the other two queries; the pair is named in the discriminator.
            self.assertEqual(
                candidate.subject["owner_symbol_id"],
                "symbol:zz" if candidate.anchor == "event:001" else
                "symbol:aa" if candidate.anchor == "event:100" else "symbol:mm",
            )
            self.assertEqual(candidate.subject["method"], names[candidate.subject["owner_symbol_id"]])
            pair = set(candidate.metadata["access_kinds"])
            self.assertEqual(len(pair), 2)
            self.assertIn(candidate.subject["owner_symbol_id"], pair)
            for owner in pair:
                self.assertIn(owner, candidate.discriminator)

        # What the collision actually cost: a citation is built from (anchor,
        # discriminator), so the two pairs sharing one were also one citable
        # candidate, and a review sheet that cites it would be citing both.
        citations = {
            defect.candidate_evidence(
                candidate, repository="repo:x", commit="0" * 40, generation=1
            ).evidence_id
            for candidate in result.candidates
        }
        self.assertEqual(len(citations), 3)


class DispatchTests(unittest.TestCase):
    """`run` and `query_for`: the two ways a caller names a query, and the
    difference between a bad request and an empty answer."""

    def test_run_dispatches_to_the_named_query(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        events, edges = publish(
            Path(holder.name), "src/unit.cpp",
            "#include <stdlib.h>\n"
            "int leak(void) {\n"
            "  char *buffer = (char *)malloc(256);\n"
            "  if (!buffer) { return -1; }\n"
            "  return 0;\n"
            "}\n",
        )
        for name, function in (
            (defect.RESOURCE_LIFETIME, defect.resource_lifetime),
            (defect.LOCK_ORDER, defect.lock_order),
            (defect.RACE_CONDITION, defect.race_condition),
        ):
            self.assertEqual(
                [c.to_dict() for c in defect.run(name, events, edges).candidates],
                [c.to_dict() for c in function(events, edges).candidates],
            )

    def test_an_unknown_query_names_the_known_ones(self) -> None:
        with self.assertRaises(ValueError) as caught:
            defect.run("race", [], [])
        self.assertIn("unknown defect query", str(caught.exception))
        self.assertIn("race_condition", str(caught.exception))

    def test_query_for_maps_a_key_to_its_query(self) -> None:
        self.assertEqual(defect.query_for("4.1"), defect.RESOURCE_LIFETIME)
        self.assertEqual(defect.query_for("4.6"), defect.RESOURCE_LIFETIME)
        self.assertEqual(defect.query_for("1.3"), defect.LOCK_ORDER)
        self.assertEqual(defect.query_for("1.4"), defect.LOCK_ORDER)
        self.assertEqual(defect.query_for("1.1"), defect.RACE_CONDITION)

    def test_an_unexpanded_key_is_an_error_rather_than_an_empty_result(self) -> None:
        """A query that ran and found nothing has answered a good question; a
        key with no query has not been asked one. Returning an empty result
        would make the two indistinguishable, and the coverage report's whole
        job is to keep them apart."""
        for key in ("4.2", "3.1", "9.1"):
            with self.assertRaises(ValueError) as caught:
                defect.query_for(key)
            self.assertIn("not expanded", str(caught.exception))
        with self.assertRaises(ValueError):
            defect.query_for("99.9")


class CandidateEvidenceTests(unittest.TestCase):
    """The citable form: `E-DEFECT-...` ids, the §15 bundle, and the two
    properties everything downstream depends on -- determinism and the fact
    that a candidate's identity survives reformatting."""

    def publish_source(self, source: str):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return publish(Path(holder.name), "src/unit.cpp", source)

    def every_candidate(self):
        """One candidate of each of the three shapes, from the fixture and from
        synthetic sources: 4.1 resolved, 4.6 ambiguous, 1.3 resolved, 1.1
        ambiguous. A bundle test that only ever saw a resolved candidate would
        not be testing the interesting half."""
        events, edges, names = fixture_graph(self)
        fixture = [
            *defect.resource_lifetime(events, edges, names=names).candidates,
            *defect.lock_order(events, edges, names=names).candidates,
        ]
        synthetic = (
            "#include <pthread.h>\n"
            "#include <stdlib.h>\n"
            "static int *g_total;\n"
            "void *worker(void *arg) {\n"
            "  g_total = (int *)malloc(64);\n"
            "  return NULL;\n"
            "}\n"
            "int main(void) {\n"
            "  pthread_t handle;\n"
            "  pthread_create(&handle, NULL, worker, NULL);\n"
            "  free(g_total);\n"
            "  return 0;\n"
            "}\n"
        )
        events, edges = self.publish_source(synthetic)
        return [*fixture, *defect.race_condition(events, edges).candidates]

    def test_the_bundle_carries_the_design_doc_members(self) -> None:
        """Design doc §15's shape, member for member. A reader comparing a
        bundle against the document should meet the same block first."""
        candidates = self.every_candidate()
        self.assertTrue(candidates)
        for candidate in candidates:
            bundle = defect.candidate_bundle(
                candidate, evidence_id="E-DEFECT-" + "0" * 24, generation=7
            ).to_dict()
            for member in (
                "defect_type", "defect_key", "subject", "facts", "uncertain_facts",
                "paths", "source_evidence", "missing_evidence",
            ):
                self.assertIn(member, bundle, candidate.defect_key)
            self.assertEqual(bundle["defect_key"], candidate.defect_key)
            self.assertEqual(bundle["defect_type"], candidate.query)
            self.assertEqual(bundle["resolution_status"], candidate.resolution_status)
            self.assertEqual(bundle["candidate_id"], "E-DEFECT-" + "0" * 24)
            self.assertEqual(bundle["generation"], 7)

            # JSON-native: the bundle goes straight into a query result and out
            # through the CLI without a second conversion pass.
            json.dumps(bundle)

    def test_every_candidate_becomes_a_citable_evidence_id(self) -> None:
        candidates = self.every_candidate()
        ids = []
        for candidate in candidates:
            evidence = defect.candidate_evidence(
                candidate, repository=REPO, commit="c0ffee", generation=3
            )
            self.assertEqual(evidence.kind, "DEFECT_CANDIDATE")
            self.assertTrue(evidence.evidence_id.startswith("E-DEFECT-"))
            self.assertEqual(parse_evidence_citations(evidence.evidence_id), [evidence.evidence_id])
            self.assertEqual(evidence.source_id, candidate.anchor)
            self.assertEqual(evidence.relation, candidate.defect_key)
            self.assertEqual(evidence.metadata["resolution_status"], candidate.resolution_status)
            ids.append(evidence.evidence_id)

        # Distinct candidates get distinct ids. The relation carries the defect
        # key precisely so that a 4.1 and a 4.6 candidate anchored on the same
        # event -- which the fixture has -- do not collide.
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreater(len(ids), len({candidate.anchor for candidate in candidates}) - 1)

    def test_the_candidate_identity_survives_reformatting(self) -> None:
        """Prepending a blank line shifts every line number in the file. Every
        id, anchor and discriminator must be unchanged: a candidate whose name
        moves when the file is reindented cannot be cited, diffed, or
        adjudicated twice."""
        events, edges, names = fixture_graph(self)
        before = [
            *defect.resource_lifetime(events, edges, names=names).candidates,
            *defect.lock_order(events, edges, names=names).candidates,
        ]

        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        copy = Path(holder.name) / "fixture_knowledge"
        shutil.copytree(FIXTURE, copy)
        source = copy / "src" / "resource.cpp"
        source.write_text("\n\n" + source.read_text(encoding="utf-8"), encoding="utf-8")

        database = Path(holder.name) / "shifted.db"
        full_index(copy, database, repository_id_override="fixture")
        with SQLiteStorage(database) as storage:
            repo_id = storage.repository()["repo_id"]
            shifted_names = {
                row["id"]: row["qualified_name"]
                for row in storage.connection.execute(
                    "SELECT id, qualified_name FROM nodes WHERE repo_id = ?", (repo_id,)
                )
            }
            shifted = [
                *defect.resource_lifetime(
                    storage.semantic_events(repo_id), storage.semantic_edges(repo_id),
                    names=shifted_names,
                ).candidates,
                *defect.lock_order(
                    storage.semantic_events(repo_id), storage.semantic_edges(repo_id),
                    names=shifted_names,
                ).candidates,
            ]

        def identity(candidate):
            return (
                candidate.defect_key, candidate.anchor, candidate.discriminator,
                candidate.subject["name"], candidate.resolution_status,
                defect.candidate_evidence(
                    candidate, repository="fixture", commit="c0ffee", generation=1
                ).evidence_id,
            )

        self.assertEqual([identity(c) for c in before], [identity(c) for c in shifted])
        # The spans move, and that is the one thing allowed to: they are
        # citations for a human, not identity.
        self.assertNotEqual(
            [c.source_evidence for c in before], [c.source_evidence for c in shifted]
        )

    def test_the_three_states_are_never_silently_upgraded(self) -> None:
        """A decisive fact the graph could not settle forces the candidate to
        be ambiguous. The `decisive` flag is what makes this checkable: a
        non-decisive uncertainty (MAY_PARALLEL on an inversion) does not cap
        the status, because it is a different question from the one the
        candidate answers."""
        candidates = self.every_candidate()
        self.assertTrue(candidates)
        for candidate in candidates:
            blocking = [
                fact for fact in candidate.uncertain_facts
                if fact["decisive"] and fact["status"] != defect.RESOLVED
            ]
            if blocking:
                self.assertNotEqual(
                    candidate.resolution_status, defect.RESOLVED,
                    f"{candidate.defect_key} resolved with decisive {blocking}",
                )
            for fact in candidate.uncertain_facts:
                self.assertIn(fact["status"], {"ambiguous", "unresolved"})

        # And the distinction is exercised, not just declared: the fixture's
        # inversion is resolved while carrying an undecidable MAY_PARALLEL.
        inversion = [
            candidate for candidate in candidates
            if candidate.defect_key == "1.3" and candidate.resolution_status == defect.RESOLVED
        ]
        self.assertTrue(inversion)
        may_parallel = next(
            fact for fact in inversion[0].uncertain_facts if fact["fact"] == "MAY_PARALLEL"
        )
        self.assertFalse(may_parallel["decisive"])

    def test_source_evidence_is_a_relative_span_and_nothing_else(self) -> None:
        candidates = self.every_candidate()
        for candidate in candidates:
            self.assertTrue(candidate.source_evidence, candidate.defect_key)
            for citation in candidate.source_evidence:
                path, _, span = citation.rpartition(":")
                self.assertTrue(span.count("-") == 1, citation)
                start, _, end = span.partition("-")
                self.assertTrue(start.isdigit() and end.isdigit(), citation)
                self.assertNotIn(":", path)
                self.assertNotIn("\\", path)
                self.assertFalse(Path(path).is_absolute(), citation)

    def test_candidate_evidence_metadata_is_what_ranking_reads(self) -> None:
        """`rank_evidence` orders bundles by four metadata keys. They have to be
        present and of the right type, or ranking silently treats every
        candidate as equal."""
        events, edges, names = fixture_graph(self)
        for candidate in defect.resource_lifetime(events, edges, names=names).candidates:
            metadata = defect.candidate_evidence(
                candidate, repository=REPO, commit="c0ffee", generation=1
            ).metadata
            self.assertIn(metadata["resolution_status"], {"resolved", "ambiguous", "unresolved"})
            self.assertIs(metadata["direct"], True)
            self.assertEqual(metadata["distance"], 0)
            self.assertIs(metadata["boundary_relevant"], False)


class QueryLayerTests(unittest.TestCase):
    """The layer between `defect.py` and a caller: storage read, evidence
    ranking, the citation ids, and the one caveat the query cannot compute.

    `defect.py` itself is a pure function of `(events, edges)` and is covered
    above; everything here is the part that is not pure, so it is tested
    against a real database rather than against the functions directly.
    """

    def query(self, **kwargs) -> GraphQuery:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        database = Path(holder.name) / "fixture.db"
        full_index(FIXTURE, database, repository_id_override="fixture")
        query = GraphQuery(database, **kwargs)
        self.addCleanup(query.close)
        return query

    def test_candidates_are_positionally_aligned_with_the_evidence(self) -> None:
        """`data["candidates"][i]` and `evidence[i]` must describe the same
        thing. The query layer gets this by ordering candidates *by* the
        ranked list rather than by re-deriving the same order, so the test
        checks the outcome, not the mechanism."""
        result = self.query().get_defect_candidates(defect_type="all")
        for key in ("query_id", "query_type", "graph_generation", "query_time_ms",
                    "returned_evidence_ids", "returned_evidence_count", "bundle_size", "data"):
            self.assertIn(key, result)
        candidates = result["data"]["candidates"]
        self.assertEqual(result["returned_evidence_count"], len(candidates))
        self.assertEqual(
            result["returned_evidence_ids"],
            [candidate["candidate_id"] for candidate in candidates],
        )
        self.assertEqual(result["data"]["defect_keys"], ["1.3", "4.1", "4.6"])
        # Coverage is per query, and it holds the denominators the precision
        # number will be read against -- not just the numerator.
        coverage = result["data"]["coverage"]
        self.assertEqual(coverage["resource_lifetime"]["candidates"], 2)
        self.assertEqual(coverage["lock_order"]["lock_points"], 6)
        self.assertEqual(coverage["race_condition"]["subjects_considered"], 26)
        self.assertFalse(result["data"]["truncated"])

    def test_defect_type_accepts_a_key_a_query_name_and_all(self) -> None:
        query = self.query()
        self.assertEqual(query.get_defect_candidates(defect_type="4.1")["data"]["defect_keys"], ["4.1"])
        # One query can serve two keys, so the key form is what filters and
        # the query form is what runs: asking for the query name gets both.
        by_query = query.get_defect_candidates(defect_type="resource_lifetime")
        self.assertEqual(by_query["data"]["defect_keys"], ["4.1", "4.6"])
        self.assertEqual(list(by_query["data"]["coverage"]), ["resource_lifetime"])
        self.assertEqual(query.get_races()["data"]["defect_keys"], [])
        self.assertEqual(
            query.get_lock_order()["data"]["coverage"]["lock_order"]["candidates"], 1
        )

    def test_a_key_filter_is_applied_before_the_candidate_cap(self) -> None:
        """Asking for 4.6 with a cap of one must return the 4.6 candidate.

        The filter used to run after the query had already truncated, so a
        request for a key whose candidates sort late got the *other* key's
        truncated prefix and then filtered it to nothing. On `llama.cpp` that
        made `--type 4.6` return zero candidates while the same database's
        coverage block said thirty existed -- an empty answer and a false one.
        """
        result = self.query().get_defect_candidates(defect_type="4.6", max_candidates=1)
        self.assertEqual(result["data"]["defect_keys"], ["4.6"])
        self.assertEqual(result["returned_evidence_count"], 1)
        # And the flag describes the requested population: one candidate out of
        # one is not a truncation, however many 4.1 candidates exist.
        self.assertFalse(result["data"]["truncated"])

    def test_a_key_with_no_query_is_a_bad_request_not_an_empty_answer(self) -> None:
        """4.2 is in the matrix and has no query. Returning zero candidates
        would make "not implemented" and "ran and found nothing" identical in
        the one report that has to tell them apart."""
        query = self.query()
        with self.assertRaises(ValueError) as caught:
            query.get_defect_candidates(defect_type="4.2")
        self.assertIn("not expanded", str(caught.exception))
        with self.assertRaises(ValueError):
            query.get_defect_candidates(defect_type="9.9")

    def test_semantic_events_carry_no_evidence_of_their_own(self) -> None:
        """Events are the queries' input, not evidence for a defect. An
        `E-CODE-` id on a raw event would let a citation point at a fact that
        asserts nothing."""
        query = self.query()
        result = query.get_semantic_events(event_type="LOCK")
        events = result["data"]["events"]
        self.assertEqual(len(events), 6)
        self.assertEqual(result["evidence"], [])
        self.assertFalse(result["data"]["truncated"])
        self.assertTrue(all(event["event_type"] == "LOCK" for event in events))
        self.assertEqual({event["event_type"] for event in events}, {"LOCK"})
        self.assertEqual(len({event["owner_symbol_id"] for event in events}), 4)

        # The limit is a real cap and the result says when it bit.
        self.assertTrue(query.get_semantic_events(event_type="LOCK", limit=2)["data"]["truncated"])

        # The file filter reads the persisted relative path, and the owner
        # filter accepts either the symbol id or the name that was matched.
        path = events[0]["metadata"]["relative_path"]
        by_file = query.get_semantic_events(event_type="LOCK", file=path)["data"]["events"]
        self.assertEqual([event["event_id"] for event in by_file],
                         [event["event_id"] for event in events])
        owner = events[0]["owner_symbol_id"]
        by_owner = query.get_semantic_events(event_type="LOCK", owner=owner)["data"]["events"]
        self.assertTrue(by_owner)
        self.assertTrue(all(event["owner_symbol_id"] == owner for event in by_owner))

        # Edges are opt-in and only those touching a selected event.
        with_edges = query.get_semantic_events(event_type="LOCK", include_edges=True)
        ids = {event["event_id"] for event in with_edges["data"]["events"]}
        edges = with_edges["data"]["edges"]
        self.assertTrue(edges)
        for edge in edges:
            self.assertTrue(edge["src_event_id"] in ids or edge["dst_event_id"] in ids)
        self.assertNotIn("edges", result["data"])

    def test_an_active_overlay_is_declared_rather_than_silently_ignored(self) -> None:
        """The semantic tables are read from the base snapshot, so an overlay
        makes every candidate a statement about a graph the user is not
        looking at. The gap has to travel with the answer."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        database = Path(holder.name) / "fixture.db"
        full_index(FIXTURE, database, repository_id_override="fixture")
        with SQLiteStorage(database) as storage:
            repository = storage.repository()
        overlay = OverlayStore.create(
            Path(holder.name) / "session.db", overlay_type="SESSION",
            repository_id=repository["repo_id"], base_commit="c0ffee",
            base_generation=int(repository["current_generation"]),
        )
        self.addCleanup(overlay.close)
        with GraphQuery(database, session_overlay=overlay) as query:
            result = query.get_defect_candidates(defect_type="all")

        self.assertTrue(result["data"]["candidates"])
        for candidate in result["data"]["candidates"]:
            self.assertTrue(
                any("base snapshot" in line for line in candidate["missing_evidence"]),
                candidate["candidate_id"],
            )
        for coverage in result["data"]["coverage"].values():
            self.assertEqual(coverage["semantic_overlay"], "base_snapshot_only")

        # And with no overlay the caveat is absent. A line that appeared
        # unconditionally would be boilerplate, and a reader would stop
        # treating it as information.
        plain = self.query().get_defect_candidates(defect_type="all")
        self.assertNotIn("semantic_overlay", plain["data"]["coverage"]["lock_order"])
        for candidate in plain["data"]["candidates"]:
            self.assertFalse(
                any("base snapshot" in line for line in candidate["missing_evidence"])
            )

    def test_a_defect_citation_traces_back_to_its_candidate(self) -> None:
        """`E-DEFECT-` ids appear in reports; the loop only closes if the id
        resolves back to the candidate that produced it, without a table."""
        query = self.query()
        result = query.get_defect_candidates(defect_type="all")
        self.assertTrue(result["returned_evidence_ids"])
        for evidence_id in result["returned_evidence_ids"]:
            self.assertEqual(parse_evidence_citations(evidence_id), [evidence_id])
            traced = query.trace_evidence(evidence_id)
            self.assertEqual(traced["returned_evidence_ids"], [evidence_id])
            bundle = traced["bundle"]
            self.assertEqual(bundle["primary_evidence"][0]["kind"], "DEFECT_CANDIDATE")
            self.assertEqual(bundle["primary_evidence"][0]["evidence_id"], evidence_id)
            self.assertEqual(bundle["uncertainties"], [])
            # The candidate's own subject leads the related entities, and its
            # facts follow verbatim -- a leak fact carries `event`/`subject`
            # where a lock-order fact carries `lock`/`side`, so a projection
            # onto a common subset would drop what a reader came for.
            self.assertIn("name", bundle["related_entities"][0])
            facts = bundle["related_entities"][1:]
            self.assertTrue(facts)
            for fact in facts:
                self.assertIn("point", fact)
                self.assertIn("source", fact)

        missing = query.trace_evidence("E-DEFECT-" + "f" * 24)
        self.assertEqual(missing["returned_evidence_ids"], [])
        self.assertEqual(missing["bundle"]["uncertainties"], ["unknown evidence ID"])


class CliTests(unittest.TestCase):
    """The command-line surface, which is how stage 4's acceptance runs were
    produced -- so it has to be tested as a command, not only as a function."""

    def run_cli(self, *argv: str) -> dict:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cli.main([*argv, "--json"])
        self.assertEqual(code, 0)
        return json.loads(buffer.getvalue())

    def test_defect_list_answers_the_falsifiability_question_without_a_database(self) -> None:
        """`--list` is a fact about the matrix and the vocabulary, so it is
        answered before a graph is opened. Pointing it at a database that does
        not exist is what proves that."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        missing = str(Path(holder.name) / "no-such.db")
        matrix = self.run_cli("defect", "--list", "--database", missing)
        by_key = {row["key"]: row for row in matrix["patterns"]}
        self.assertEqual(len(by_key), 10)
        self.assertEqual(matrix["queries"], list(defect.QUERY_NAMES))
        # The pair that is stage 4's answer in checkable form: confirmation
        # cannot run, candidate generation can.
        self.assertFalse(by_key["1.1"]["coverable_now"])
        self.assertTrue(by_key["1.1"]["candidate_coverable_now"])
        self.assertEqual(by_key["1.1"]["missing_events"], ["READ", "WRITE"])
        # An unexpanded pattern says so rather than claiming coverage.
        self.assertFalse(by_key["4.2"]["expanded"])
        self.assertIsNone(by_key["4.2"]["query"])

    def test_the_defect_command_prints_the_same_envelope_as_the_query_layer(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        database = str(Path(holder.name) / "fixture.db")
        full_index(FIXTURE, database, repository_id_override="fixture")
        result = self.run_cli("defect", "--type", "4.1", "--database", database)
        self.assertEqual(result["data"]["defect_keys"], ["4.1"])
        self.assertEqual(result["returned_evidence_count"], 1)
        self.assertEqual(
            result["returned_evidence_ids"],
            [candidate["candidate_id"] for candidate in result["data"]["candidates"]],
        )
        with GraphQuery(database) as query:
            self.assertEqual(
                result["returned_evidence_ids"],
                query.get_defect_candidates(defect_type="4.1")["returned_evidence_ids"],
            )

    def test_events_command_prints_the_raw_layer_and_its_edges(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        database = str(Path(holder.name) / "fixture.db")
        full_index(FIXTURE, database, repository_id_override="fixture")
        result = self.run_cli("events", "--type", "LOCK", "--edges", "--database", database)
        events = result["data"]["events"]
        self.assertEqual(len(events), 6)
        self.assertEqual(result["evidence"], [])
        ids = {event["event_id"] for event in events}
        for edge in result["data"]["edges"]:
            self.assertTrue(edge["src_event_id"] in ids or edge["dst_event_id"] in ids)

    def test_a_bad_type_is_a_usage_error_and_an_unexpanded_one_is_not(self) -> None:
        """Two different failures. A typo never reaches the graph; a matrix key
        with no query does, and gets the message that says why."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                cli.main(["defect", "--type", "4.11"])
        self.assertEqual(caught.exception.code, 2)
        with self.assertRaises(ValueError) as caught:
            cli.run(argparse.Namespace(
                command="defect", database=None, json=False, list=False,
                type="4.2", subject=None, max_hops=64, max_paths=8, max_candidates=20,
            ))
        self.assertIn("not expanded", str(caught.exception))

    def test_redirected_json_is_utf8_whatever_the_console_encoding_is(self) -> None:
        """The acceptance runs redirect this output into artifacts. Encoding
        them in the console's locale would make the file unreadable to the
        tool that wrote it, on exactly the machines that need it."""
        environment = dict(os.environ, PYTHONPATH="src", PYTHONIOENCODING="cp936")
        completed = subprocess.run(
            [sys.executable, "-m", "provenlattice.cli", "defect", "--list", "--json"],
            cwd=Path(__file__).resolve().parent.parent, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        )
        payload = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(len(payload["patterns"]), 10)
        self.assertTrue(any(not row["name"].isascii() for row in payload["patterns"]))


class ReviewSheetTests(unittest.TestCase):
    """The review package stage 4's acceptance runs are recorded from.

    It is a measurement instrument, so the two things it has to get right are
    reproducibility (the same database and seed give the same sheet) and
    arithmetic (precision is computed from the verdicts, never typed).
    """

    def build(self, directory: Path, **overrides) -> dict:
        database = directory / "fixture.db"
        if not database.is_file():
            full_index(FIXTURE, database, repository_id_override="fixture")
        arguments = {
            "databases": {"fixture": database}, "types": ["4.1", "4.6", "1.3", "1.1"],
            "sample": 20, "seed": "test-seed", "workspace": Path(__file__).resolve().parent.parent,
        }
        arguments.update(overrides)
        return build_review.build_review(**arguments)

    def test_the_sheet_records_a_population_and_a_sample_for_every_stratum(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        package = self.build(Path(holder.name))
        by_stratum = {(item["defect_key"], item["resolution_status"]): item
                      for item in package["availability"]}
        # 4.6 is `resolved` on the fixture since stage 4.5: the lock's subject
        # is a receiver, and the receiver's declaration says `std::mutex`.
        self.assertEqual(set(by_stratum), {("1.3", "resolved"), ("4.1", "resolved"),
                                           ("4.6", "resolved")})
        for item in by_stratum.values():
            self.assertEqual(item["population_N"], 1)
            self.assertEqual(item["sample_n"], 1)
        # 1.1 is requested and has no candidates at all. It appears in no
        # stratum, and the coverage block is where a reader finds out why.
        self.assertNotIn(("1.1", "ambiguous"), by_stratum)
        self.assertEqual(package["coverage"]["fixture"]["race_condition"]["subjects_multi_method"], 0)
        # Every case is citable and carries the blank verdict block, including
        # the two fields that answer the acceptance question.
        for case in package["cases"]:
            self.assertTrue(parse_evidence_citations(case["candidate_id"]))
            self.assertEqual(case["annotation"]["verdict"], "PENDING")
            self.assertIsNone(case["annotation"]["is_true_positive"])
            self.assertIsNone(case["annotation"]["needs_dfg"])
            self.assertTrue(case["missing_evidence"])
            self.assertEqual(case["source_spans"], [item["span"] for item in case["source_snippets"]])

    def test_the_sheet_is_byte_identical_on_a_second_run(self) -> None:
        """Nothing in the package may vary between runs -- not a timestamp,
        not a duration, not a dict order. Two builds of the same database
        under the same seed are compared as bytes, which is the only
        comparison that catches an added `time.time()`."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        first, second = Path(holder.name) / "a", Path(holder.name) / "b"
        for output in (first, second):
            output.mkdir()
            package = self.build(Path(holder.name))
            (output / "defect_review.json").write_text(
                json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8")
            (output / "defect_review.md").write_text(build_review._render(package), encoding="utf-8")
        for name in ("defect_review.json", "defect_review.md"):
            self.assertEqual(
                (first / name).read_bytes(), (second / name).read_bytes(), name
            )

    def test_the_sampling_spreads_across_strata_rather_than_filling_from_one(self) -> None:
        """With three strata and a target of two, a sampler that took the first
        two candidates would report on one family twice and leave the others
        unmeasured."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        package = self.build(Path(holder.name), sample=2)
        self.assertEqual(len(package["cases"]), 2)
        strata = {(case["defect_key"], case["resolution_status"]) for case in package["cases"]}
        self.assertEqual(len(strata), 2)

    def test_the_sample_target_is_spent_across_repositories_not_per_repository(self) -> None:
        """The sheet is one adjudication. Sampling per repository would make its
        size a function of how many `--database` flags were passed, which is a
        property of the command line and not of the code being reviewed."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        database = Path(holder.name) / "fixture.db"
        full_index(FIXTURE, database, repository_id_override="fixture")
        package = build_review.build_review(
            databases={"alpha": database, "beta": database},
            types=["4.1", "4.6", "1.3", "1.1"], sample=3, seed="test-seed",
            workspace=Path(__file__).resolve().parent.parent,
        )
        # The same database twice, so the two repositories have the same six
        # strata with material: a per-repository sampler returns six cases.
        self.assertEqual(len(package["availability"]), 6)
        self.assertEqual(len(package["cases"]), 3)
        # ... and the quota is spread, not spent on whichever repository sorts
        # first: three cases out of six strata reach both of them.
        self.assertEqual({case["repository"] for case in package["cases"]}, {"alpha", "beta"})
        # Truncation is a per-query fact, so a stratum is not flagged by
        # another query's limit -- and the two truncations are kept apart,
        # because one says the sample is a prefix and the other only says the
        # walk behind the candidates stopped early.
        for source in package["sources"]:
            self.assertEqual(sorted(source["limits"]), ["lock_order", "race_condition",
                                                        "resource_lifetime"])
            for item in source["limits"].values():
                self.assertEqual(item, {"recall_truncated": False, "population_capped": False})
        for item in package["availability"]:
            self.assertFalse(item["population_truncated"])
            self.assertFalse(item["recall_truncated"])
        # The reviewed code is identified by revision, not just by a path: the
        # index records no commit, so the sheet asks the repository itself.
        for source in package["sources"]:
            self.assertRegex(source["repository_commit"], r"^[0-9a-f]{40}$|^unknown$")
            self.assertIn(source["repository_dirty"], (True, False, None))

    def test_dirtiness_is_about_the_reviewed_code_not_the_index(self) -> None:
        """The tool writes its index inside the repository it indexed, so a
        plain `git status` reports every run as dirty and the column stops
        saying anything -- which is the one thing it is there for. The artifact
        directory is excluded; an edit to the code is not."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        (root / "unit.c").write_bytes(b"int main(void) { return 0; }\n")
        for argv in (
            ("init",), ("add", "unit.c"),
            ("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-m", "init"),
        ):
            build_review._git(root, *argv)
        self.assertRegex(build_review._git(root, "rev-parse", "HEAD"), r"^[0-9a-f]{40}$")
        database = root / ".provenlattice" / "codegraph.db"
        database.parent.mkdir()
        database.write_bytes(b"")

        commit, dirty = build_review._repository_state(root, "", database)
        self.assertRegex(commit, r"^[0-9a-f]{40}$")
        self.assertFalse(dirty)

        (root / "unit.c").write_bytes(b"int main(void) { return 1; }\n")
        self.assertTrue(build_review._repository_state(root, "", database)[1])

    def test_sources_come_from_where_the_tree_is_now_not_where_it_was_indexed(self) -> None:
        """The database records the root it indexed, and that path is a
        default rather than an authority: a tree that moved after indexing is
        still the tree the graph describes, and reading the recorded path would
        turn every snippet into a missing one -- the sheet would still look
        complete and would no longer carry the material the verdict needs.
        `--root` says where the sources are, and the row records both paths so
        a reader can see the sheet's snippets came from an override."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        directory = Path(holder.name)
        database = directory / "fixture.db"
        if not database.is_file():
            full_index(FIXTURE, database, repository_id_override="fixture")
        # A copy of the database whose recorded root no longer exists: what a
        # moved or renamed checkout leaves behind.
        moved_database = directory / "moved.db"
        shutil.copyfile(database, moved_database)
        gone = directory / "gone"
        # `with sqlite3.connect(...)` commits and does not close, and a
        # connection left open holds a Windows lock on the file.
        with contextlib.closing(sqlite3.connect(moved_database)) as connection:
            connection.execute("UPDATE repositories SET root_path = ?", (str(gone),))
            connection.commit()

        def build(**overrides) -> dict:
            arguments = {
                "databases": {"fixture": moved_database}, "types": ["4.1", "4.6"],
                "sample": 20, "seed": "test-seed",
                "workspace": Path(__file__).resolve().parent.parent,
            }
            arguments.update(overrides)
            return build_review.build_review(**arguments)

        without = build()
        self.assertEqual(len(without["cases"]), 2)
        for case in without["cases"]:
            self.assertFalse(without["sources"][0]["root_available"])
            self.assertTrue(case["source_spans"])
            for snippet in case["source_snippets"]:
                self.assertIsNone(snippet["text"])

        moved = directory / "moved"
        shutil.copytree(Path(FIXTURE) / "src", moved / "src")
        with_override = build(roots={"fixture": moved})
        source = with_override["sources"][0]
        self.assertTrue(source["root_available"])
        self.assertTrue(source["root_override"])
        self.assertEqual(source["root_path"], str(gone))
        self.assertEqual(source["root_path_used"], str(moved))
        self.assertEqual(len(with_override["cases"]), 2)
        for case in with_override["cases"]:
            self.assertEqual(case["source_spans"],
                             [item["span"] for item in case["source_snippets"]])
            for snippet in case["source_snippets"]:
                self.assertIsNotNone(snippet["text"], snippet["span"])
                path, _, line_range = snippet["span"].partition(":")
                first, _, last = line_range.partition("-")
                lines = (moved / path).read_text(encoding="utf-8").splitlines()
                cited = [line.strip() for line in lines[int(first) - 1 : int(last)]]
                cited = [line for line in cited if line]
                self.assertTrue(cited, snippet["span"])
                for line in cited:
                    self.assertIn(line, snippet["text"])

    def test_a_recall_limit_is_not_reported_as_a_population_floor(self) -> None:
        """`max_paths` stopping the walk and this script's own cap both leave
        candidates unfound, but only the second makes the sample a sorted
        prefix of the population. A stratum that reported the first as the
        second would tell its reader that 24 candidates are a floor of a
        million, which is a different and much worse claim."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        real = defect.run

        def stopped_early(query, events, edges, **kwargs):
            return dataclasses.replace(real(query, events, edges, **kwargs), truncated=True)

        with mock.patch.object(defect, "run", stopped_early):
            package = self.build(Path(holder.name))
        self.assertTrue(package["availability"])
        for item in package["availability"]:
            self.assertTrue(item["recall_truncated"])
            self.assertFalse(item["population_truncated"])
        for source in package["sources"]:
            for limits in source["limits"].values():
                self.assertEqual(limits, {"recall_truncated": True, "population_capped": False})

    def test_precision_is_computed_from_the_verdicts(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        package = self.build(Path(holder.name))
        # One true positive, one false positive, one left pending -- and the
        # pending one must not be counted as either. Cases are picked by key
        # rather than by position, so the assertions are about the arithmetic
        # and not about the sampling order.
        by_key = {case["defect_key"]: case for case in package["cases"]}
        by_key["1.3"]["annotation"].update(is_true_positive=True, needs_dfg=True)
        by_key["4.1"]["annotation"].update(is_true_positive=False, reason="already freed")
        sheet = Path(holder.name) / "filled.json"
        sheet.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
        summary = build_review.summarize(sheet)
        overall = summary["overall"]
        self.assertEqual((overall["n"], overall["tp"], overall["fp"], overall["pending"]), (3, 1, 1, 1))
        self.assertEqual(overall["precision"], 0.5)
        self.assertEqual(overall["needs_dfg"], 1)
        judged = {row["defect_key"]: row for row in summary["strata"]}
        self.assertEqual(judged["1.3"]["precision"], 1.0)
        self.assertEqual(judged["4.1"]["precision"], 0.0)
        # A stratum with no verdicts reports "no answer", not zero precision.
        self.assertIsNone(judged["4.6"]["precision"])
        self.assertIn("already freed", build_review._format(summary) + json.dumps(summary))

    def test_a_reviewed_case_with_no_judgment_is_uncertain_not_pending(self) -> None:
        """`REVIEWED` with `is_true_positive` left null means the annotator
        looked and the sheet did not carry what the decision needed. Counting
        that as `pending` would report a finished adjudication as an unfinished
        one, and the baseline would be quoted against a denominator that still
        claims work to do."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        package = self.build(Path(holder.name))
        by_key = {case["defect_key"]: case for case in package["cases"]}
        by_key["1.3"]["annotation"].update(
            verdict="REVIEWED", failure_reason="insufficient_context",
            notes="needs the callee's contract",
        )
        by_key["4.1"]["annotation"].update(
            verdict="REVIEWED", is_true_positive=False, failure_reason="identity",
        )
        by_key["4.6"]["annotation"].update(
            verdict="REVIEWED", is_true_positive=False, failure_reason="not_a_reason",
        )
        sheet = Path(holder.name) / "filled.json"
        sheet.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
        summary = build_review.summarize(sheet)
        overall = summary["overall"]
        self.assertEqual(
            (overall["n"], overall["tp"], overall["fp"], overall["uncertain"], overall["pending"]),
            (3, 0, 2, 1, 0),
        )
        # Uncertain cases are outside the denominator, exactly as pending ones
        # are: the two are different findings, and neither is evidence of a
        # wrong candidate.
        self.assertEqual(overall["precision"], 0.0)
        self.assertEqual(overall["failure_reasons"]["insufficient_context"], 1)
        self.assertEqual(overall["failure_reasons"]["identity"], 1)
        # A value outside the taxonomy is counted rather than dropped -- a typo
        # that vanished would silently shrink the tally the sheet exists for.
        self.assertEqual(overall["failure_reasons"]["not_a_reason"], 1)
        rendered = build_review._format(summary)
        self.assertIn("| uncertain |", rendered)
        self.assertIn("not_a_reason *(not in the taxonomy)*", rendered)
        # Every reason the taxonomy names is printed, zeros included: an
        # all-zero row says the verdicts did not use it, which is worth seeing
        # before the number is quoted.
        for failure in build_review.FAILURE_REASONS:
            self.assertIn(f"| {failure} |", rendered)

    def test_the_reading_copy_renders_the_recorded_verdict_not_the_prompt(self) -> None:
        """The JSON is the record and the Markdown is derived from it. A reading
        copy that still asked `is_true_positive` = ____ beside a case that has
        been judged would report a finished adjudication as an open one."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        package = self.build(Path(holder.name))
        self.assertIn("`is_true_positive` = ____", build_review._render(package))
        case = package["cases"][0]
        case["annotation"].update(
            verdict="REVIEWED", is_true_positive=False, failure_reason="ownership",
            needs_dfg=False, missing_capability="RAII", confidence=0.9,
            reason="freed by the destructor at tools/x.cpp:12", annotator="a human",
            notes="none",
        )
        for other in package["cases"][1:]:
            other["annotation"].update(verdict="REVIEWED", is_true_positive=False)
        rendered = build_review._render(package)
        # A sheet with every case judged has no blanks left to fill.
        self.assertNotIn("____", rendered)
        self.assertIn("Verdict (recorded in `defect_review.json`):", rendered)
        self.assertIn(f"- `verdict`: `{case['annotation']['verdict']}`", rendered)
        self.assertIn("- `is_true_positive`: `false` — **false positive**", rendered)
        self.assertIn("- `failure_reason`: `ownership`", rendered)
        self.assertIn("- `needs_dfg`: `false`", rendered)
        self.assertIn("- `confidence`: `0.9`", rendered)
        self.assertIn("freed by the destructor at tools/x.cpp:12", rendered)
        self.assertIn("- `annotator`: `a human`", rendered)
        # The reading copy is derived, so rendering it twice is the same copy.
        self.assertEqual(rendered, build_review._render(package))
        # A recorded reason cites code, so it contains backticks. A single
        # delimiter would be closed by the first one and the rest of the line
        # would render as prose, so the delimiter is lengthened and the value
        # padded -- without the padding the content's own backticks merge into
        # the delimiter and no span forms at all.
        case["annotation"]["reason"] = "`free` at tools/x.cpp:12"
        self.assertIn("- `reason`: `` `free` at tools/x.cpp:12 ``",
                      build_review._render(package))

    def test_an_uncertain_verdict_reads_as_uncertain_not_as_false(self) -> None:
        """`REVIEWED` with `is_true_positive` left null is a verdict of its own.
        Rendered as a false positive it would libel the candidate; rendered as
        the blank prompt it would look like work still to do."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        package = self.build(Path(holder.name))
        package["cases"][0]["annotation"].update(
            verdict="REVIEWED", failure_reason="insufficient_context",
            reason="the callee is not in this repository",
        )
        for other in package["cases"][1:]:
            other["annotation"].update(verdict="REVIEWED", is_true_positive=True)
        rendered = build_review._render(package)
        self.assertIn("- `is_true_positive`: `null` — **uncertain**", rendered)
        self.assertIn("- `is_true_positive`: `true` — **true positive**", rendered)
        self.assertNotIn("**false positive**", rendered)
        self.assertNotIn("____", rendered)
        self.assertIn("- `failure_reason`: `insufficient_context`", rendered)
        # The uncertain case's unrecorded fields read as `null`, not as blanks:
        # the field was left empty on purpose and the copy says so.
        self.assertIn("- `needs_dfg`: `null`", rendered)
        self.assertIn("- `confidence`: `null`", rendered)

    def test_the_reading_copy_is_refreshed_from_the_record_without_a_database(self) -> None:
        """Filling in verdicts must not require rebuilding the sheet: the build
        path would re-sample and reset every annotation to `PENDING`."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        package = self.build(Path(holder.name))
        package["cases"][0]["annotation"].update(
            verdict="REVIEWED", is_true_positive=True, needs_dfg=False,
        )
        sheet = Path(holder.name) / "defect_review.json"
        sheet.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
        stderr, stdout = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["build_review.py", "--render", str(sheet)]), \
                contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            self.assertEqual(build_review.main(), 0)
        copy = sheet.with_suffix(".md")
        self.assertTrue(copy.is_file())
        self.assertEqual(copy.read_text(encoding="utf-8"), build_review._render(package))
        self.assertIn("**true positive**", copy.read_text(encoding="utf-8"))
        # The database is not an input here, and a path that is not a sheet is
        # an error rather than an empty reading copy.
        for argv in (["--render", str(sheet), "--database", "x=y"],
                     ["--render", str(Path(holder.name) / "absent.json")]):
            with mock.patch.object(sys, "argv", ["build_review.py", *argv]), \
                    contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit):
                    build_review.main()

    def test_a_rebuild_refuses_to_discard_recorded_verdicts(self) -> None:
        """Re-sampling is cheap and adjudication is not, so the destructive
        command is the one that has to ask."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        output = Path(holder.name)
        package = self.build(output)
        package["cases"][0]["annotation"].update(verdict="REVIEWED", is_true_positive=False)
        sheet = output / "defect_review.json"
        sheet.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
        before = sheet.read_bytes()
        stderr, stdout = io.StringIO(), io.StringIO()
        argv = ["build_review.py", "--database", f"fixture={output / 'fixture.db'}",
                "--type", "4.1", "--output", str(output)]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(stderr), \
                contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit):
                build_review.main()
        self.assertIn("recorded verdict", stderr.getvalue())
        self.assertEqual(sheet.read_bytes(), before)
        # `--overwrite` is the way to say it on purpose.
        with mock.patch.object(sys, "argv", argv + ["--overwrite"]), \
                contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            self.assertEqual(build_review.main(), 0)
        self.assertNotEqual(sheet.read_bytes(), before)
        self.assertEqual(
            json.loads(sheet.read_text(encoding="utf-8"))["cases"][0]["annotation"]["verdict"],
            "PENDING",
        )


if __name__ == "__main__":
    unittest.main()

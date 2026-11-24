"""G1 ATOMIC facts: `_Atomic` objects and Verifier atomic blocks (issue-pilot#89).

The producer under test lives in `analysis_c_frontend.collect_atomic_facts` and
`analysis_c_scfg`'s ATOMIC point injection. The consumers (`defect.py`'s
`_touches_atomically` and `concurrency_race_scenarios.atomic_subjects`) are
frozen and are exercised here only through the public defect query.

Fixtures are synthetic and spelling-independent: the invariance test rewrites
every user name and the formatting, and the rule must not care.
"""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from provenlattice.defect_query import query_defect_candidates
from provenlattice.graph import full_index
from provenlattice.orchestrator import analyze_scope


def write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


def _atomic_nodes(database: Path) -> list[dict]:
    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute(
            "SELECT payload FROM analysis_nodes "
            "WHERE feature='sparse_cfg:cpp' AND kind='ATOMIC' "
            "ORDER BY analysis_node_id"
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def _state(database: Path) -> dict:
    with closing(sqlite3.connect(database)) as connection:
        row = connection.execute(
            "SELECT metadata FROM analysis_state WHERE feature='sparse_cfg:cpp'"
        ).fetchone()
    return json.loads(row[0]) if row else {}


def _materialize(body: str) -> tuple[list[dict], dict, dict]:
    """Build one fixture; return (ATOMIC payloads, race envelope, state)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        database = Path(tmp) / "graph.db"
        write(root, "src/t.c", body)
        full_index(root, database)
        analyze_scope(root, "src", ("defect",), database=database)
        nodes = _atomic_nodes(database)
        state = _state(database)
        env = query_defect_candidates(
            root, defect_type="race_condition", database=database)
        assert env["status"] == "available", env.get("reason")
        return nodes, env, state


def _annotations(payload: dict) -> dict:
    return payload.get("annotations") or {}


def _subjects(nodes: list[dict]) -> set[str]:
    return {_annotations(node).get("subject", "") for node in nodes}


ATOMIC_TYPE = r"""
#include <pthread.h>
_Atomic int g_counter = 0;
void *bump(void *arg) {
    g_counter++;
    return NULL;
}
void start(void) {
    pthread_t t;
    pthread_create(&t, NULL, bump, NULL);
    g_counter = 2;
    pthread_join(t, NULL);
}
"""

PLAIN_TYPE = r"""
#include <pthread.h>
int g_counter = 0;
void *bump(void *arg) {
    g_counter++;
    return NULL;
}
void start(void) {
    pthread_t t;
    pthread_create(&t, NULL, bump, NULL);
    g_counter = 2;
    pthread_join(t, NULL);
}
"""

PAIRED_BLOCKS = r"""
#include <pthread.h>
int g_value = 0;
void *bump(void *arg) {
    __VERIFIER_atomic_begin();
    g_value++;
    __VERIFIER_atomic_end();
    return NULL;
}
void start(void) {
    pthread_t t;
    pthread_create(&t, NULL, bump, NULL);
    __VERIFIER_atomic_begin();
    g_value = 2;
    __VERIFIER_atomic_end();
    pthread_join(t, NULL);
}
"""

UNPAIRED_BLOCK = r"""
#include <pthread.h>
int g_value = 0;
void *bump(void *arg) {
    __VERIFIER_atomic_begin();
    g_value++;
    return NULL;
}
void start(void) {
    pthread_t t;
    pthread_create(&t, NULL, bump, NULL);
    g_value = 2;
    pthread_join(t, NULL);
}
"""

NESTED_BLOCK = r"""
#include <pthread.h>
int g_value = 0;
void *bump(void *arg) {
    __VERIFIER_atomic_begin();
    __VERIFIER_atomic_begin();
    g_value++;
    __VERIFIER_atomic_end();
    __VERIFIER_atomic_end();
    return NULL;
}
void start(void) {
    pthread_t t;
    pthread_create(&t, NULL, bump, NULL);
    g_value = 2;
    pthread_join(t, NULL);
}
"""

CONDITIONAL_END = r"""
#include <pthread.h>
int g_value = 0;
void *bump(void *arg) {
    __VERIFIER_atomic_begin();
    if (arg) __VERIFIER_atomic_end();
    g_value++;
    __VERIFIER_atomic_end();
    return NULL;
}
void start(void) {
    pthread_t t;
    pthread_create(&t, NULL, bump, NULL);
    g_value = 2;
    pthread_join(t, NULL);
}
"""

TYPEDEF_ALIAS = r"""
#include <pthread.h>
typedef _Atomic int atomic_int;
atomic_int g_counter = 0;
void *bump(void *arg) {
    g_counter++;
    return NULL;
}
void start(void) {
    pthread_t t;
    pthread_create(&t, NULL, bump, NULL);
    g_counter = 2;
    pthread_join(t, NULL);
}
"""

ATOMIC_TYPE_SPECIFIER = r"""
#include <pthread.h>
_Atomic(int) g_flag;
void *bump(void *arg) {
    g_flag = 1;
    return NULL;
}
void start(void) {
    pthread_t t;
    pthread_create(&t, NULL, bump, NULL);
    g_flag = 2;
    pthread_join(t, NULL);
}
"""

VOID_ALIAS = r"""
_Atomic int g_value;
void touch(void *p) {
    *(int *)p = 1;
}
"""

RECOVERED_WITH_INITIALIZER = r"""
int y = 0;
_Atomic(int) x = y;
void bump(void) {
    y = 1;
    x = 2;
}
"""

STRUCT_WITH_ATOMIC_FIELD = r"""
typedef struct { _Atomic int a; int b; } S;
S s;
void touch(void) {
    s.a = 1;
    s.b = 2;
}
"""

ATOMIC_POINTER_OBJECT = r"""
_Atomic(int *) p;
int *q;
void touch(void) {
    p = q;
    *p = 1;
}
"""

CONDITIONAL_BLOCK = r"""
int g_value = 0;
void touch(int c) {
    if (c) __VERIFIER_atomic_begin();
    g_value++;
    __VERIFIER_atomic_end();
}
"""

SIZEOF_OPERAND = r"""
_Atomic int g_value = 0;
int size(void) {
    return sizeof(g_value);
}
"""

SHADOWED_TYPEDEF = r"""
typedef _Atomic int T;
void touch(void) {
    typedef int T;
    T x;
    x = 1;
}
"""

MACRO_ALIAS = r"""
#define AI _Atomic int
AI g;
void touch(void) { g = 1; }
"""

MACRO_TYPE_SPECIFIER_ALIAS = r"""
#define AI _Atomic(int)
AI g;
void touch(void) { g = 1; }
"""

COMMENT_FAKE_TYPEDEF = r"""
typedef int T;
/* typedef _Atomic(int) T; */
T g;
void touch(void) { g = 1; }
"""

INACTIVE_IF0_TYPEDEF = r"""
#define T int
#if 0
#define T _Atomic int
#endif
T g;
void touch(void) { g = 1; }
"""

STRING_FAKE_TYPEDEF = r"""
typedef int T;
const char *text = "typedef _Atomic(int) T;";
T g;
void touch(void) { g = 1; }
"""

FUNCTION_LIKE_MACRO = r"""
typedef int T;
#define T(x) _Atomic int
T g;
void touch(void) { g = 1; }
"""

MACRO_REDEFINED_AFTER_USE = r"""
#define U _Atomic int
#define T U
#undef U
#define U int
T g;
void touch(void) { g = 1; }
"""

SUFFIXED_IDENTIFIER = r"""
typedef int MY_Atomic;
#define T MY_Atomic
T g;
void touch(void) { g = 1; }
"""

CONTINUED_POINTER_MACRO = r"""
#define P _Atomic int \
    *
P p;
int *q;
void touch(void) {
    p = q;
    *p = 1;
}
"""

UNDEF_DOES_NOT_HIDE_TYPEDEF = r"""
typedef _Atomic int T;
#undef T
T g;
void touch(void) { g = 1; }
"""

ARRAY_DECAY = r"""
_Atomic int a[2];
int *p;
void touch(void) { p = a; }
"""

ADDRESS_OF_ELEMENT = r"""
int a[2];
void touch(void) {
    __VERIFIER_atomic_begin();
    &a[0];
    __VERIFIER_atomic_end();
}
"""

GENERIC_IN_VLA_EXTENT = r"""
int n;
void touch(void) {
    __VERIFIER_atomic_begin();
    sizeof(int[_Generic(n, int: 1, default: 2)]);
    __VERIFIER_atomic_end();
}
"""

NESTED_ATOMIC_MEMBER = r"""
struct Inner { _Atomic int x; };
struct Outer { struct Inner inner; };
struct Outer o;
void touch(void) { o.inner.x = 1; }
"""

BRACED_RECOVERED_ARRAY = r"""
_Atomic(int) a[2] = {0};
void touch(void) { a[0] = 1; }
"""

PAREN_RECOVERED_TYPEDEF = r"""
typedef _Atomic(int) (T);
T g;
void touch(void) { g = 1; }
"""

PAREN_RECOVERED_POINTER_TYPEDEF = r"""
typedef _Atomic(int) (*P);
P p;
int *q;
void touch(void) {
    p = q;
    *p = 1;
}
"""

UNKNOWN_ALIAS_TO_ATOMIC_ARRAY = r"""
_Atomic int a[2];
void touch(void *q) { *(int *)q = 1; }
"""

TYPEDEF_TYPE_SPECIFIER_ALIAS = r"""
typedef _Atomic(int) AI;
AI g;
void touch(void) { g = 1; }
"""

TYPEDEF_MULTI_DECLARATOR = r"""
typedef _Atomic int T, U;
U g;
void touch(void) { g = 1; }
"""

RECOVERED_MULTI_DECLARATOR = r"""
_Atomic(int) x = 0, y = 0;
void touch(void) {
    x = 1;
    y = 2;
}
"""

RECOVERED_POINTER = r"""
_Atomic(int) *p;
int *q;
void touch(void) {
    p = q;
    *p = 1;
}
"""

RECOVERED_ARRAY = r"""
_Atomic(int) a[2];
void touch(void) {
    a[0] = 1;
}
"""

INITIALIZER_READ = r"""
void touch(void) {
    _Atomic int x;
    int y = x;
    (void)y;
}
"""

INITIALIZER_READ_IN_BLOCK = r"""
int x;
void touch(void) {
    __VERIFIER_atomic_begin();
    int y = x;
    __VERIFIER_atomic_end();
    (void)y;
}
"""

GENERIC_CONTROL = r"""
_Atomic int g_value;
int pick(void) {
    return _Generic(g_value, int: 0, default: 1);
}
"""

CAST_SUBSCRIPT_ALIAS = r"""
_Atomic int g_value;
void touch(void *p) {
    ((int *)p)[0] = 1;
}
"""

TYPEDEF_ATOMIC_POINTER_OBJECT = r"""
typedef _Atomic(int *) P;
P p;
int *q;
void touch(void) {
    p = q;
    *p = 1;
}
"""

TYPEDEF_POINTER_TO_ATOMIC = r"""
typedef _Atomic int *P;
P p;
int *q;
void touch(void) {
    p = q;
    *p = 1;
}
"""

MACRO_POINTER_TO_ATOMIC = r"""
#define P _Atomic int *
P p;
int *q;
void touch(void) {
    p = q;
    *p = 1;
}
"""

RECOVERED_TYPEDEF_SCOPE = r"""
typedef int T;
void touch(void) {
    { typedef _Atomic(int) T; T x; x = 1; }
    T y;
    y = 2;
}
"""

MACRO_REDEFINITION = r"""
#define AI int
AI plain;
#undef AI
#define AI _Atomic int
AI atomic;
void touch(void) {
    plain = 1;
    atomic = 2;
}
"""

VLA_BOUND = r"""
void touch(void) {
    _Atomic int n;
    int a[n];
    (void)a;
}
"""

VLA_SIZEOF_BOUND = r"""
void touch(void) {
    _Atomic int n;
    sizeof(int[n]);
}
"""

POINTER_ARITHMETIC = r"""
_Atomic int *p;
void touch(void) {
    *(p + 1) = 1;
}
"""

RENAMED_REFORMATTED = r"""
#include <pthread.h>

_Atomic long long aa=0;

void* bb(void* unused)
{
  aa++;
  return 0;
}

void cc(void)
{
  pthread_t hh;
  pthread_create(&hh,0,bb,0);
  aa=2;
  pthread_join(hh,0);
}
"""


class AtomicEventTests(unittest.TestCase):
    def test_atomic_type_emits_atomic_points(self) -> None:
        nodes, env, _state = _materialize(ATOMIC_TYPE)
        self.assertTrue(nodes, "an _Atomic object must publish ATOMIC points")
        self.assertEqual(_subjects(nodes), {"g_counter"})
        for node in nodes:
            self.assertEqual(
                _annotations(node).get("atomic_source"), "type_qualifier")
            self.assertIn(
                _annotations(node).get("atomic_access"),
                {"READ", "WRITE", "READ_MODIFY_WRITE"})
        races = [c for c in env["candidates"] if c["query"] == "race_condition"]
        self.assertEqual(races, [], "both sides are atomic and must be excluded")

    def test_plain_int_is_not_atomic(self) -> None:
        nodes, env, _state = _materialize(PLAIN_TYPE)
        self.assertEqual(nodes, [])
        races = [c for c in env["candidates"] if c["query"] == "race_condition"]
        self.assertEqual(len(races), 1)

    def test_paired_atomic_blocks_emit_atomic_points(self) -> None:
        nodes, env, _state = _materialize(PAIRED_BLOCKS)
        self.assertTrue(nodes)
        self.assertEqual(_subjects(nodes), {"g_value"})
        for node in nodes:
            self.assertEqual(
                _annotations(node).get("atomic_source"), "atomic_block")
        races = [c for c in env["candidates"] if c["query"] == "race_condition"]
        self.assertEqual(races, [], "both accesses are inside paired blocks")

    def test_unpaired_block_is_a_limitation_not_a_fact(self) -> None:
        nodes, env, state = _materialize(UNPAIRED_BLOCK)
        self.assertEqual(nodes, [])
        self.assertTrue(any(
            limit.startswith("atomic_block_unpaired_begin")
            for limit in state.get("atomic_limitations", ())))
        races = [c for c in env["candidates"] if c["query"] == "race_condition"]
        self.assertEqual(len(races), 1)

    def test_nested_block_is_a_limitation_not_a_fact(self) -> None:
        nodes, env, state = _materialize(NESTED_BLOCK)
        self.assertEqual(nodes, [])
        self.assertTrue(any(
            limit.startswith("atomic_block_nested")
            for limit in state.get("atomic_limitations", ())))
        races = [c for c in env["candidates"] if c["query"] == "race_condition"]
        self.assertEqual(len(races), 1)

    def test_typedef_alias_resolves_to_the_atomic_type(self) -> None:
        nodes, _env, _state = _materialize(TYPEDEF_ALIAS)
        self.assertTrue(nodes)
        self.assertEqual(_subjects(nodes), {"g_counter"})

    def test_atomic_type_specifier_spelling_is_recovered(self) -> None:
        nodes, _env, _state = _materialize(ATOMIC_TYPE_SPECIFIER)
        self.assertTrue(nodes, "the C11 _Atomic(type) spelling must be recovered")
        self.assertEqual(_subjects(nodes), {"g_flag"})
        self.assertEqual(
            _annotations(nodes[0]).get("atomic_source"), "type_specifier")

    def test_access_through_void_alias_is_not_atomic(self) -> None:
        nodes, _env, state = _materialize(VOID_ALIAS)
        self.assertEqual(nodes, [], "an unresolved alias must stay unknown")
        self.assertTrue(
            any(
                limit.startswith("atomic_alias_unresolved")
                for limit in state.get("atomic_limitations", ())
            ),
            "the unresolved alias must be an explicit limitation",
        )

    def test_recovered_initializer_is_not_a_declaration(self) -> None:
        nodes, _env, _state = _materialize(RECOVERED_WITH_INITIALIZER)
        self.assertEqual(_subjects(nodes), {"x"})

    def test_atomic_field_does_not_make_the_aggregate_atomic(self) -> None:
        nodes, _env, _state = _materialize(STRUCT_WITH_ATOMIC_FIELD)
        pairs = {
            (
                _annotations(node).get("subject", ""),
                _annotations(node).get("subject_member", ""),
            )
            for node in nodes
        }
        self.assertEqual(pairs, {("s", "a")})

    def test_dereferencing_an_atomic_pointer_is_not_atomic(self) -> None:
        nodes, _env, state = _materialize(ATOMIC_POINTER_OBJECT)
        self.assertTrue(nodes)
        self.assertEqual(_subjects(nodes), {"p"})
        self.assertEqual(
            {_annotations(node).get("expression", "") for node in nodes}, {"p"})
        self.assertFalse(any(
            limit.startswith("atomic_alias_unresolved")
            for limit in state.get("atomic_limitations", ())))

    def test_conditional_begin_is_a_limitation(self) -> None:
        nodes, _env, state = _materialize(CONDITIONAL_BLOCK)
        self.assertEqual(nodes, [])
        self.assertTrue(any(
            limit.startswith("atomic_block_conditional")
            for limit in state.get("atomic_limitations", ())))

    def test_conditional_end_invalidates_the_outer_pair(self) -> None:
        nodes, _env, state = _materialize(CONDITIONAL_END)
        self.assertEqual(nodes, [])
        self.assertTrue(any(
            limit.startswith("atomic_block_conditional")
            for limit in state.get("atomic_limitations", ())))

    def test_sizeof_operand_is_not_an_access(self) -> None:
        nodes, _env, _state = _materialize(SIZEOF_OPERAND)
        self.assertEqual(nodes, [])

    def test_shadowed_typedef_is_not_atomic(self) -> None:
        nodes, _env, _state = _materialize(SHADOWED_TYPEDEF)
        self.assertEqual(nodes, [])

    def test_macro_alias_of_atomic_type(self) -> None:
        nodes, _env, _state = _materialize(MACRO_ALIAS)
        self.assertEqual(_subjects(nodes), {"g"})

    def test_macro_alias_of_type_specifier(self) -> None:
        nodes, _env, _state = _materialize(MACRO_TYPE_SPECIFIER_ALIAS)
        self.assertEqual(_subjects(nodes), {"g"})

    def test_comment_is_not_a_typedef(self) -> None:
        nodes, _env, _state = _materialize(COMMENT_FAKE_TYPEDEF)
        self.assertEqual(nodes, [])

    def test_inactive_if0_is_not_a_macro(self) -> None:
        nodes, _env, _state = _materialize(INACTIVE_IF0_TYPEDEF)
        self.assertEqual(nodes, [])

    def test_string_literal_is_not_a_typedef(self) -> None:
        nodes, _env, _state = _materialize(STRING_FAKE_TYPEDEF)
        self.assertEqual(nodes, [])

    def test_function_like_macro_is_not_an_object_alias(self) -> None:
        nodes, _env, _state = _materialize(FUNCTION_LIKE_MACRO)
        self.assertEqual(nodes, [])

    def test_macro_is_resolved_at_the_use_site(self) -> None:
        nodes, _env, _state = _materialize(MACRO_REDEFINED_AFTER_USE)
        self.assertEqual(nodes, [])

    def test_atomic_substring_in_identifier_is_not_a_qualifier(self) -> None:
        nodes, _env, _state = _materialize(SUFFIXED_IDENTIFIER)
        self.assertEqual(nodes, [])

    def test_continued_pointer_macro_keeps_pointee_kind(self) -> None:
        nodes, _env, _state = _materialize(CONTINUED_POINTER_MACRO)
        self.assertTrue(nodes)
        self.assertEqual(
            {_annotations(node).get("expression", "") for node in nodes},
            {"*p"})

    def test_undef_does_not_hide_typedef(self) -> None:
        nodes, _env, _state = _materialize(UNDEF_DOES_NOT_HIDE_TYPEDEF)
        self.assertEqual(_subjects(nodes), {"g"})

    def test_array_decay_is_not_an_element_access(self) -> None:
        nodes, _env, _state = _materialize(ARRAY_DECAY)
        self.assertEqual(nodes, [])

    def test_address_of_element_is_not_an_access(self) -> None:
        nodes, _env, _state = _materialize(ADDRESS_OF_ELEMENT)
        self.assertEqual(nodes, [])

    def test_generic_control_inside_vla_extent_is_unevaluated(self) -> None:
        nodes, _env, _state = _materialize(GENERIC_IN_VLA_EXTENT)
        self.assertEqual(nodes, [])

    def test_nested_member_is_an_explicit_limitation(self) -> None:
        nodes, _env, state = _materialize(NESTED_ATOMIC_MEMBER)
        self.assertEqual(nodes, [])
        self.assertTrue(any(
            limit.startswith("atomic_member_chain_unsupported")
            for limit in state.get("atomic_limitations", ())))

    def test_braced_initializer_does_not_hide_recovered_array(self) -> None:
        nodes, _env, _state = _materialize(BRACED_RECOVERED_ARRAY)
        self.assertEqual(_subjects(nodes), {"a"})

    def test_parenthesized_recovered_typedef(self) -> None:
        nodes, _env, _state = _materialize(PAREN_RECOVERED_TYPEDEF)
        self.assertEqual(_subjects(nodes), {"g"})

    def test_parenthesized_recovered_pointer_typedef(self) -> None:
        nodes, _env, _state = _materialize(PAREN_RECOVERED_POINTER_TYPEDEF)
        self.assertTrue(nodes)
        self.assertEqual(
            {_annotations(node).get("expression", "") for node in nodes},
            {"*p"})

    def test_unknown_alias_to_atomic_array_is_a_limitation(self) -> None:
        nodes, _env, state = _materialize(UNKNOWN_ALIAS_TO_ATOMIC_ARRAY)
        self.assertEqual(nodes, [])
        self.assertTrue(any(
            limit.startswith("atomic_alias_unresolved")
            for limit in state.get("atomic_limitations", ())))

    def test_typedef_of_type_specifier(self) -> None:
        nodes, _env, _state = _materialize(TYPEDEF_TYPE_SPECIFIER_ALIAS)
        self.assertEqual(_subjects(nodes), {"g"})

    def test_multiple_declarators_in_a_typedef(self) -> None:
        nodes, _env, _state = _materialize(TYPEDEF_MULTI_DECLARATOR)
        self.assertEqual(_subjects(nodes), {"g"})

    def test_recovered_multiple_declarators(self) -> None:
        nodes, _env, _state = _materialize(RECOVERED_MULTI_DECLARATOR)
        self.assertEqual(_subjects(nodes), {"x", "y"})

    def test_recovered_pointer_to_atomic_object(self) -> None:
        nodes, _env, _state = _materialize(RECOVERED_POINTER)
        self.assertTrue(nodes)
        self.assertEqual(
            {_annotations(node).get("expression", "") for node in nodes},
            {"*p"},
        )

    def test_recovered_array_of_atomic_elements(self) -> None:
        nodes, _env, _state = _materialize(RECOVERED_ARRAY)
        self.assertTrue(nodes)
        self.assertEqual(_subjects(nodes), {"a"})

    def test_initializer_read_is_a_real_access(self) -> None:
        nodes, _env, _state = _materialize(INITIALIZER_READ)
        self.assertEqual(_subjects(nodes), {"x"})

    def test_initializer_read_in_atomic_block(self) -> None:
        nodes, _env, _state = _materialize(INITIALIZER_READ_IN_BLOCK)
        self.assertTrue(nodes)
        self.assertEqual(
            {_annotations(node).get("atomic_source") for node in nodes},
            {"atomic_block"},
        )

    def test_generic_control_expression_is_not_an_access(self) -> None:
        nodes, _env, _state = _materialize(GENERIC_CONTROL)
        self.assertEqual(nodes, [])

    def test_cast_subscript_alias_records_a_limitation(self) -> None:
        nodes, _env, state = _materialize(CAST_SUBSCRIPT_ALIAS)
        self.assertEqual(nodes, [])
        self.assertTrue(any(
            limit.startswith("atomic_alias_unresolved")
            for limit in state.get("atomic_limitations", ())))

    def test_typedef_of_atomic_pointer_object(self) -> None:
        nodes, _env, _state = _materialize(TYPEDEF_ATOMIC_POINTER_OBJECT)
        self.assertEqual(
            {_annotations(node).get("expression", "") for node in nodes},
            {"p"},
        )

    def test_typedef_of_pointer_to_atomic(self) -> None:
        nodes, _env, _state = _materialize(TYPEDEF_POINTER_TO_ATOMIC)
        self.assertEqual(
            {_annotations(node).get("expression", "") for node in nodes},
            {"*p"},
        )

    def test_macro_of_pointer_to_atomic(self) -> None:
        nodes, _env, _state = _materialize(MACRO_POINTER_TO_ATOMIC)
        self.assertEqual(
            {_annotations(node).get("expression", "") for node in nodes},
            {"*p"},
        )

    def test_recovered_typedef_respects_block_scope(self) -> None:
        nodes, _env, _state = _materialize(RECOVERED_TYPEDEF_SCOPE)
        self.assertEqual(_subjects(nodes), {"x"})

    def test_macro_redefinition_is_position_aware(self) -> None:
        nodes, _env, _state = _materialize(MACRO_REDEFINITION)
        self.assertEqual(_subjects(nodes), {"atomic"})

    def test_vla_bound_is_a_real_read(self) -> None:
        nodes, _env, _state = _materialize(VLA_BOUND)
        self.assertEqual(_subjects(nodes), {"n"})

    def test_vla_sizeof_bound_is_a_real_read(self) -> None:
        nodes, _env, _state = _materialize(VLA_SIZEOF_BOUND)
        self.assertEqual(_subjects(nodes), {"n"})

    def test_pointer_arithmetic_dereference_is_atomic(self) -> None:
        nodes, _env, _state = _materialize(POINTER_ARITHMETIC)
        self.assertTrue(nodes)
        self.assertEqual(
            {_annotations(node).get("expression", "") for node in nodes},
            {"*(p + 1)"},
        )

    def test_renaming_and_formatting_do_not_change_the_result(self) -> None:
        nodes, env, _state = _materialize(RENAMED_REFORMATTED)
        self.assertTrue(nodes)
        self.assertEqual(_subjects(nodes), {"aa"})
        races = [c for c in env["candidates"] if c["query"] == "race_condition"]
        self.assertEqual(races, [])

    def test_atomic_points_are_deterministic(self) -> None:
        first, _env, _state = _materialize(ATOMIC_TYPE)
        second, _env, _state = _materialize(ATOMIC_TYPE)
        shape = lambda nodes: sorted(
            (node.get("ordinal"), _annotations(node).get("subject", ""),
             _annotations(node).get("atomic_source", ""),
             _annotations(node).get("atomic_access", ""))
            for node in nodes
        )
        self.assertEqual(shape(first), shape(second))


if __name__ == "__main__":
    unittest.main()

"""PL171-CWD-P0 detector rules — V2 contract GATE-1 matrix (9 scenarios).

Freezes the Issue #72 V2 candidate-level rule reconciliation against synthetic
fixtures, one per gate scenario from the frozen contract §5:

1. pre-thread access in a >=2-access candidate -> trimmed, candidate kept
2. pre-thread trim leaves <2 accesses          -> candidate dropped
3. post-join pair, all-other-guarded           -> filtered
4. post-join pair, other access NOT guarded    -> NOT filtered
5. exclusive same-mutex (mutex/mutex)          -> filtered
6. read-lock vs write-lock                     -> NOT filtered
7. malformed lock section (lost unlock)        -> NOT filtered
8. different lock object                       -> NOT filtered
9. no-lock race                                -> kept

Scenario 1 also asserts the *trim*: the pre-spawn access is removed from the
candidate's access set, not the whole pair dropped.
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


def _races(body: str, filename: str = "src/t.c") -> list[dict]:
    """Build the upstream chain for one fixture and return race candidates."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        database = Path(tmp) / "graph.db"
        write(root, filename, body)
        full_index(root, database)
        analyze_scope(root, "src", ("defect",), database=database)
        env = query_defect_candidates(
            root, defect_type="race_condition", database=database)
        assert env["status"] == "available", env.get("reason")
        return [c for c in env["candidates"] if c["query"] == "race_condition"]


def _owner_accesses(candidate: dict, owner: str) -> list[dict]:
    """The access events of one side, by method name."""
    return [
        access for access in candidate["evidence_v2"]["access"]
        if access["owner"] == owner
    ]


# 1. PAIR-01 trim keeps a >=2-access candidate: the pre-spawn write (line 10)
# is trimmed; the post-spawn write (line 12) and the worker write (line 5) remain.
TRIM_KEEP = r"""
#include <pthread.h>
int shared = 0;
void *worker(void *arg) {
    shared = 1;
    return NULL;
}
void starter(void) {
    pthread_t t;
    shared = 2;
    pthread_create(&t, NULL, worker, NULL);
    shared = 3;
    pthread_join(t, NULL);
}
"""

# 2. PAIR-01 trim leaves <2 accesses (the starter's only access is pre-spawn):
# the pair is dropped.
TRIM_DROP = r"""
#include <pthread.h>
int shared = 0;
void *worker(void *arg) {
    shared = 1;
    return NULL;
}
void starter(void) {
    pthread_t t;
    shared = 2;
    pthread_create(&t, NULL, worker, NULL);
    pthread_join(t, NULL);
}
"""

# 3. PAIR-05: a post-join access with the other access (the worker's write)
# correctly guarded by a mutex -> the candidate is a false positive, filtered.
POST_JOIN_GUARDED = r"""
#include <pthread.h>
pthread_mutex_t m = PTHREAD_MUTEX_INITIALIZER;
int shared = 0;
void *worker(void *arg) {
    pthread_mutex_lock(&m);
    shared = 1;
    pthread_mutex_unlock(&m);
    return NULL;
}
void starter(void) {
    pthread_t t;
    pthread_create(&t, NULL, worker, NULL);
    pthread_join(t, NULL);
    shared = 2;
}
"""

# 4. PAIR-05: a post-join access with the other access unguarded -> NOT all-
# other-guarded, so the pair is kept (the excluded cross-lifetime over-fire).
POST_JOIN_UNGUARDED = r"""
#include <pthread.h>
int shared = 0;
void *worker(void *arg) {
    shared = 1;
    return NULL;
}
void starter(void) {
    pthread_t t;
    pthread_create(&t, NULL, worker, NULL);
    pthread_join(t, NULL);
    shared = 2;
}
"""

# 5. PAIR-02: a plain mutex held (and released) around both touches.
MUTEX_MUTEX = r"""
#include <pthread.h>
pthread_mutex_t m = PTHREAD_MUTEX_INITIALIZER;
int shared = 0;
void *writer(void *arg) {
    pthread_mutex_lock(&m);
    shared = 1;
    pthread_mutex_unlock(&m);
    return NULL;
}
void *reader(void *arg) {
    pthread_mutex_lock(&m);
    int v = shared;
    pthread_mutex_unlock(&m);
    return (void *)(long)v;
}
"""

# 6. PAIR-06: a read lock and a write lock on one rwlock do not exclude each
# other, and a read lock does not cover a write -- the pair must stay.
RD_VS_WR = r"""
#include <pthread.h>
pthread_rwlock_t g_lck = PTHREAD_RWLOCK_INITIALIZER;
int shared = 0;
void *bad(void *arg) {
    pthread_rwlock_rdlock(&g_lck);
    shared = 1;
    pthread_rwlock_unlock(&g_lck);
    return NULL;
}
void *good(void *arg) {
    pthread_rwlock_wrlock(&g_lck);
    shared = 2;
    pthread_rwlock_unlock(&g_lck);
    return (void *)(long)shared;
}
"""

# 7. PAIR-02: an end whose lock is not released on every path is not a
# well-formed closed section, so the pair must stay.
MALFORMED_SECTION = r"""
#include <pthread.h>
pthread_mutex_t m = PTHREAD_MUTEX_INITIALIZER;
int shared = 0;
void *writer(void *arg) {
    pthread_mutex_lock(&m);
    shared = 1;
    return NULL;
}
void *reader(void *arg) {
    pthread_mutex_lock(&m);
    int v = shared;
    pthread_mutex_unlock(&m);
    return (void *)(long)v;
}
"""

# 8. Different lock objects must not merge into one SAME_LOCK discharge.
DIFFERENT_LOCK = r"""
#include <pthread.h>
pthread_mutex_t lock_a = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t lock_b = PTHREAD_MUTEX_INITIALIZER;
int shared = 0;
void *writer(void *arg) {
    pthread_mutex_lock(&lock_a);
    shared = 42;
    pthread_mutex_unlock(&lock_a);
    return NULL;
}
void *reader(void *arg) {
    pthread_mutex_lock(&lock_b);
    int v = shared;
    pthread_mutex_unlock(&lock_b);
    return (void *)(long)v;
}
"""

# 9. An unguarded write vs an unguarded read is still a race.
NO_LOCK = r"""
int shared = 0;
void *incr(void *arg) { shared++; return NULL; }
void *read(void *arg) { return (void *)(long)shared; }
"""

# Regression (PAIR-01 trim): the spawner's only access is pre-spawn (trimmed to
# empty) while the worker has two accesses. The pair must be dropped cleanly --
# a cross-method race needs an access on each side -- and must not crash the
# detector (the `_race_candidate` anchor indexes points_a[0]).
FULLY_TRIMMED_SPAWNER = r"""
#include <pthread.h>
int shared = 0;
void *worker(void *arg) {
    shared = 1;
    shared = 2;
    return NULL;
}
void starter(void) {
    pthread_t t;
    shared = 10;
    pthread_create(&t, NULL, worker, NULL);
    pthread_join(t, NULL);
}
"""


class PL171P0V2DetectorTests(unittest.TestCase):
    """GATE-1 unit matrix for the Issue #72 V2 candidate-level rules."""

    def test_01_pre_thread_access_trimmed_kept(self):
        races = _races(TRIM_KEEP)
        self.assertEqual(len(races), 1)
        # The pre-spawn write is trimmed OUT of the candidate, not the pair
        # dropped: the starter side now carries only its post-spawn access.
        starter_accesses = _owner_accesses(races[0], "starter")
        self.assertEqual(len(starter_accesses), 1)
        self.assertEqual(starter_accesses[0]["source_span"], [12, 12])

    def test_02_pre_thread_trim_leaves_no_pair(self):
        self.assertEqual(_races(TRIM_DROP), [])

    def test_03_post_join_all_other_guarded_filtered(self):
        self.assertEqual(_races(POST_JOIN_GUARDED), [])

    def test_04_post_join_unguarded_peer_kept(self):
        self.assertEqual(len(_races(POST_JOIN_UNGUARDED)), 1)

    def test_05_mutex_mutex_same_lock_filtered(self):
        self.assertEqual(_races(MUTEX_MUTEX), [])

    def test_06_read_lock_vs_write_lock_kept(self):
        self.assertEqual(len(_races(RD_VS_WR)), 1)

    def test_07_malformed_lock_section_kept(self):
        self.assertEqual(len(_races(MALFORMED_SECTION)), 1)

    def test_08_different_lock_object_kept(self):
        self.assertEqual(len(_races(DIFFERENT_LOCK)), 1)

    def test_09_no_lock_race_kept(self):
        self.assertEqual(len(_races(NO_LOCK)), 1)

    def test_10_spawner_fully_trimmed_dropped(self):
        # The spawner's only access is pre-spawn; the worker keeps two. Trim
        # empties the spawner side, so the pair must be dropped without crashing.
        self.assertEqual(_races(FULLY_TRIMMED_SPAWNER), [])


if __name__ == "__main__":
    unittest.main()
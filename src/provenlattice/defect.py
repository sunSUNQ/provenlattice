"""Typed defect queries over the sparse semantic graph (stage 4, appendix B.4).

Three queries answer the three patterns the matrix grades A and the stage 3
graph can feed today: `resource_lifetime` (4.1 leaks and the lock half of 4.6),
`lock_order` (1.3 inversions and 1.4 self-deadlock) and `race_condition` (1.1).

Everything here is a pure function over the two published tables --
`(events, edges)` in, `DefectQueryResult` out -- exactly like the pattern
functions in `sparsecfg`. No tree-sitter, no SQLite, no repository. That is
what lets the acceptance harness drive the queries from a read-only connection
and lets the tests drive them from objects with no database at all.

**The three-state contract.** `resolution_status` is what the *graph* resolved
about a decisive relation, and it is never upgraded silently:

* `resolved`   -- every relation the decisive predicate needs is in the graph,
                  and no subject on the decisive path is unresolved;
* `ambiguous`  -- the predicate holds on the graph, but at least one input is a
                  name-level proxy rather than a resolved identity;
* `unresolved` -- the predicate holds but a required identity is empty, so the
                  candidate cannot be attributed at all.

None of these is a verdict about the code. A model's `confirmed` / `likely` /
`insufficient evidence` / `rejected` lives only in the review sheet's
annotation block; a query that produced a `resolved` candidate has decided
nothing about whether the defect is real.

**What this stage deliberately does not do.** READ and WRITE events do not
exist (level 1, awaiting the DFG), so `race_condition` classifies accesses by a
syntactic proxy and can never resolve MAY_PARALLEL; its candidates are all
`ambiguous` by construction, and a shared variable that never appears in an
event-bearing expression (`counter++`) produces no candidate at all. Lock
identity is a name, so a member lock (`m.lock()`) can never resolve to an
object. Every one of those limits is stated in the candidate's own
`missing_evidence`, not just in this docstring.
"""

from __future__ import annotations

import inspect
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Collection, Iterable, Mapping, Sequence

from .contracts import FUNCTION_STATIC_STORAGE, ContractTable
from .evidence import DefectEvidenceBundle, Evidence
from .models import (
    STORAGE_FIELD, STORAGE_FILE_STATIC, STORAGE_FUNCTION_STATIC, STORAGE_GLOBAL,
    STORAGE_LOCAL, STORAGE_PARAMETER, STORAGE_UNKNOWN,
)
from .semantics.vocabulary import load_defect_patterns
from .sparsecfg import (
    ARGUMENT_SEPARATOR,
    ControlPath,
    build_adjacency,
    find_paths,
    materialize_points,
    unreleased_resources,
)

RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
UNRESOLVED = "unresolved"

# How many elimination records travel in the coverage block. The *count* is
# never capped -- only the records -- because a coverage block that grows with
# the finding count stops being a coverage block.
#
# Set high enough not to bind on the acceptance repositories: llama.cpp's 742
# candidates eliminate on the order of 120, and the acceptance protocol draws
# its adjudication sample from the full list, so a cap of twenty would silently
# truncate the sampling frame. It is still a bound, so a million-line repository
# cannot put an unbounded list into a coverage block.
DISQUALIFIED_EVIDENCE_CAP = 500

RESOURCE_LIFETIME = "resource_lifetime"
LOCK_ORDER = "lock_order"
RACE_CONDITION = "race_condition"
QUERY_NAMES = (RESOURCE_LIFETIME, LOCK_ORDER, RACE_CONDITION)

# Confidence is a *band*, not a measurement: it says which of the three states
# the candidate landed in and how much of the pattern's decisive predicate the
# graph could answer, nothing more. Two runs of the same query give the same
# number because the number is a lookup, not an estimate.
RESOURCE_CONFIDENCE = {RESOLVED: 0.6, AMBIGUOUS: 0.4, UNRESOLVED: 0.2}
LOCK_ORDER_CONFIDENCE = {RESOLVED: 0.7, AMBIGUOUS: 0.4}
SELF_DEADLOCK_CONFIDENCE = {RESOLVED: 0.6, AMBIGUOUS: 0.3}
RACE_CONFIDENCE = {0: 0.5, 1: 0.4, 2: 0.3}

# Acquisitions that can return without acquiring. Under one of these, "the lock
# is held on the error path" is not a fact the graph can assert, so any
# candidate that depends on it is capped at `ambiguous` rather than reported as
# resolved. Spelled out rather than pattern-matched on "try": `WaitForSingleObject`
# and `pthread_mutex_timedlock` belong here and contain no `try` at all.
NON_BLOCKING_ACQUIRES = frozenset({
    "pthread_mutex_trylock", "pthread_mutex_timedlock", "pthread_spin_trylock",
    "pthread_rwlock_tryrdlock", "pthread_rwlock_trywrlock",
    "mtx_trylock", "sem_trywait", "sem_timedwait",
    "TryEnterCriticalSection", "WaitForSingleObject", "WaitForMultipleObjects",
    "try_lock", "try_lock_shared",
})

# The declared types that are a mutex, as the last identifier of the spelling
# (`type_token` has already dropped the namespace and the template arguments, so
# `std::mutex` arrives as `mutex` and `std::shared_mutex` as `shared_mutex`).
# A set and not a substring test: `pool_mutex_holder` contains `mutex` and is
# not one, and a token that a name can accidentally contain is not evidence.
_MUTEX_TYPES = frozenset({
    "mutex", "recursive_mutex", "timed_mutex", "shared_mutex", "shared_timed_mutex",
    "pthread_mutex_t", "pthread_rwlock_t", "pthread_spinlock_t",
    "CRITICAL_SECTION", "SRWLOCK", "GMutex", "GRWLock",
})

# The declared types whose member named `lock` is *known* to be something else.
# Deliberately one entry: `std::weak_ptr::lock()` returns a `shared_ptr` and is
# the standard library's only same-named non-acquisition. The list stays this
# short because the failure directions are not symmetric -- excluding a type the
# graph merely has not seen as a mutex would drop genuine acquisitions, and a
# class that wraps a mutex behind `.lock()` is ordinary (`pool->lock()` where
# `pool` is `HNSW *` must not be excluded). `shared_ptr` and `unique_ptr` are
# not listed: they define no `lock` member at all, so a match on those spellings
# would be a user type, and a spelling is not a type.
_NON_LOCK_RECEIVER_TYPES = frozenset({"weak_ptr"})

# The event types whose subject can name shared *data*. LOCK/UNLOCK/ATOMIC are
# synchronization facilities rather than the data they guard, and are subtracted
# from this set rather than added to it.
RACE_SUBJECT_EVENTS = frozenset({"ALLOC", "RELEASE", "CALL", "DEREFERENCE", "CHECK", "RETURN"})
# The access events (stage 5A). They join the subject index -- an access with a
# subject is a touch of shared data like any other -- but never the protection
# test: `_blocked_by_lock` asks the control-flow graph whether a lock dominates
# an access, and an access event has no position in that graph (see
# `_EDGELESS_EVENT_TYPES` in `sparsecfg.py`). Two indexes per subject, two roles.
RACE_ACCESS_EVENTS = frozenset({"READ", "WRITE"})
SYNCHRONIZATION_EVENTS = frozenset({"LOCK", "UNLOCK", "ATOMIC"})

_MISSING_CALLEE_CONTRACT = (
    "the ownership contract of a callee: whether a function the resource is "
    "passed to takes ownership, borrows it, or frees it"
)
_MISSING_RAII = (
    "RAII and smart pointers: `unique_ptr<T> p(new T)` is an ALLOC with no "
    "RELEASE in the graph, so every owning smart pointer reads as a leak"
)
# Retired in stage 4.5. The gap it registered -- `std::lock_guard<T> lock(m);`
# parsed as a function declaration and promoted to a symbol of its own, so only
# the brace spelling reached the graph with a lock identity -- was measured on a
# real C++ repository and is now closed at the source: the most-vexing-parse is
# demoted rather than promoted, and both spellings carry the mutex's identity.
# What remains of RAII recall is the guard-to-mutex binding below, which is a
# different gap with a different owner (the ownership stage).
_MISSING_GUARD_BINDING = (
    "the guard-to-mutex binding: `std::unique_lock<T> g(m)` releases through "
    "`g`, and `g.unlock()` is an operation on the guard, not on `m`, so a walk "
    "that joins on the mutex's identity cannot see the release"
)
_MISSING_ALIASING = (
    "aliasing and reassignment: `q = p; free(q)`, `free(p); p = NULL` and "
    "`p = realloc(p, n)` are all invisible without a data-flow graph"
)
_MISSING_RELEASE_IN_CALLEE = (
    "a release performed inside a callee: the graph only sees RELEASE points "
    "in the method it walked"
)
_MISSING_ERROR_PATH = (
    "whether the error path is reachable in practice: the graph reports the "
    "path exists, not that the input reaches it"
)
_MISSING_DESTRUCTOR = (
    "whether a destructor or another path releases the lock first"
)
_MISSING_RECURSIVE = (
    "whether the mutex is recursive: under PTHREAD_MUTEX_RECURSIVE a second "
    "acquisition by the same thread is legal, and the graph does not hold the "
    "mutex's type"
)
_MISSING_THREADS = (
    "the execution context: whether the two methods can run concurrently at "
    "all -- nothing in the graph orders them"
)
_MISSING_LOCK_ALIAS = (
    "lock aliasing: two expressions naming the same mutex (`&s->m` and `s->m`) "
    "are two names here, and one name is one lock"
)
_MISSING_TRY_PATH = (
    "the failure path of a non-blocking acquisition: a try-lock that fails "
    "leaves the lock unheld and the graph cannot tell the two arms apart"
)
_MISSING_CONCURRENCY = (
    "whether the two contexts really run concurrently: MAY_PARALLEL is "
    "undecidable from spawn points alone"
)
_MISSING_LOCK_GUARDS = (
    "whether the lock actually guards this variable: holding a lock near an "
    "access is not the same as the lock protecting the data"
)
_MISSING_WEAK_CONSISTENCY = (
    "whether the variable tolerates weak consistency (a statistics counter "
    "may be allowed to race by design)"
)


@dataclass(frozen=True, slots=True)
class Candidate:
    """One defect candidate: a subject, the graph facts behind it, and the
    status the graph reached about them.

    `discriminator` is deterministic and carries no line number -- identity has
    to survive reformatting, because a candidate whose id moves when the file
    is reindented cannot be cited, diffed or adjudicated twice.

    Every entry in `uncertain_facts` carries a `decisive` flag, and the flag is
    what makes `resolution_status` checkable rather than rhetorical: a
    *decisive* fact that is ambiguous forces the candidate to be ambiguous too.
    A fact that is uncertain but not decisive does not -- MAY_PARALLEL is
    always undecidable and a lock-order inversion is still `resolved`, because
    concurrency is a separate question from whether the two orders exist. The
    distinction is the difference between "the graph could not answer what this
    candidate is about" and "the graph answered, and this is the part of the
    world it cannot speak to".
    """

    defect_key: str
    query: str
    subject: dict[str, Any]
    anchor: str
    discriminator: str
    resolution_status: str
    confidence: float
    facts: tuple[dict[str, Any], ...] = ()
    uncertain_facts: tuple[dict[str, Any], ...] = ()
    paths: tuple[dict[str, Any], ...] = ()
    source_evidence: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def sort_key(self) -> tuple:
        return (self.defect_key, self.anchor, self.discriminator)

    def to_dict(self) -> dict[str, Any]:
        return {
            "defect_key": self.defect_key,
            "query": self.query,
            "subject": dict(self.subject),
            "anchor": self.anchor,
            "discriminator": self.discriminator,
            "resolution_status": self.resolution_status,
            "confidence": self.confidence,
            "facts": [dict(fact) for fact in self.facts],
            "uncertain_facts": [dict(fact) for fact in self.uncertain_facts],
            "paths": [dict(path) for path in self.paths],
            "source_evidence": list(self.source_evidence),
            "missing_evidence": list(self.missing_evidence),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class DefectQueryResult:
    query: str
    candidates: tuple[Candidate, ...]
    coverage: dict[str, Any]
    truncated: bool = False

    @property
    def keys(self) -> tuple[str, ...]:
        """The defect keys this result actually produced candidates for."""
        return tuple(sorted({candidate.defect_key for candidate in self.candidates}))


def query_for(defect_key: str) -> str:
    """Which query produces candidates for a matrix key.

    An unexpanded key is an error, not an empty result: a caller asking for a
    pattern the pipeline cannot attack has made a bad request, while a query
    that ran and found nothing has answered a good one.
    """
    for pattern in load_defect_patterns():
        if pattern.key == defect_key:
            if not pattern.query:
                raise ValueError(
                    f"defect pattern {defect_key} has no query; it is not expanded yet"
                )
            return pattern.query
    raise ValueError(f"unknown defect pattern: {defect_key}")


def run(query: str, events: Iterable[Any], edges: Iterable[Any], **kwargs: Any) -> DefectQueryResult:
    """Dispatch by name, passing each query only the parameters it accepts.

    The queries have deliberately different knobs: `max_paths` bounds a walk,
    and `race_condition` performs no walk -- a race candidate is a pair of
    accesses, so there is no path to cap. Filtering here rather than at every
    call site means a caller can offer the full parameter set without knowing
    which query uses which, and the signature remains the single source of
    truth about what each query honours.
    """
    functions: dict[str, Callable[..., DefectQueryResult]] = {
        RESOURCE_LIFETIME: resource_lifetime,
        LOCK_ORDER: lock_order,
        RACE_CONDITION: race_condition,
    }
    try:
        function = functions[query]
    except KeyError:
        raise ValueError(
            f"unknown defect query: {query!r}; known: {', '.join(QUERY_NAMES)}"
        ) from None
    accepted = set(inspect.signature(function).parameters)
    return function(events, edges, **{k: v for k, v in kwargs.items() if k in accepted})


# ----------------------------------------------------------------------
# shared reading of the published graph


def _identity(info: Mapping[str, Any], *, identity: bool = True) -> str:
    """The object a point names, as one string (stage 4.5).

    Stage 4 joined on `subject`, the *spelling* of a name: `int n` in one
    method and `int n` in another were one object, and the race query returned
    557,315 candidates for redis-50 because of it -- every one a pair of
    same-named locals. The declaration index now records which declaration a
    name resolves to, so the join can be on the object instead.

    The token is assembled here rather than in the parser because the
    repository id does not exist at parse time -- the same reason `PointKey`
    carries the owner triple instead of a symbol id.

    Order matters. A declared identity comes before a type, because `decl`
    separates `p->lock` from `q->lock` while a type only says they are the same
    kind of thing; joining on the type would *raise* the candidate count, since
    two objects of one type would take turns displacing each other in the
    lock-order `held` list.

    Every fallback ends at `name:<spelling>` and never at nothing. An old row
    written before this stage has no `subject_decl`, and a candidate dropped
    silently is a finding lost -- the one failure a review tool cannot have.

    `identity=False` returns the bare name, which reproduces the stage 4 join
    exactly. That is what makes the before/after comparison readable: it
    isolates the *extraction* changes from the identity changes.
    """
    name = info.get("subject", "")
    if not identity:
        return name
    decl = info.get("subject_decl", "")
    if decl:
        member = info.get("subject_member", "")
        if info.get("subject_storage", "") in _METHOD_LOCAL_STORAGES:
            # A local, a parameter and a function static belong to the method
            # that declares them, so two methods that each declare `int n` are
            # two objects by construction. The owner id carries the signature,
            # so two overloads do not merge either -- which the declaration
            # token alone cannot express, since it is built from the name.
            base = f"{info.get('owner_symbol_id', '')}#{decl}"
        else:
            base = decl
        return f"{base}#{member}" if member else base
    site = info.get("subject_site", "")
    if site:
        # An anonymous allocation: no name to resolve, but an identity all the
        # same -- the site. Two `new X(k)` in one loop are the same site and the
        # same object; two in different methods are different objects.
        return f"site:{site}"
    return f"name:{name}" if name else ""


# The storages whose object is created by the declaration itself, so the
# declaring method is part of the identity. A field belongs to its class and a
# file static to its file -- both already inside the declaration token -- and a
# global has external linkage, so the same one named in two files is one
# object and adding a path would invent two.
_METHOD_LOCAL_STORAGES = frozenset({
    STORAGE_LOCAL, STORAGE_PARAMETER, STORAGE_FUNCTION_STATIC,
})


def _identity_display(info: Mapping[str, Any]) -> str:
    """The spelling a human reads, which is what `--subject` still filters on."""
    return info.get("subject", "")


def _identity_cap(info: Mapping[str, Any], *, identity: bool = True) -> dict[str, Any] | None:
    """The named reason this point's identity cannot carry `resolved`, or None.

    Four ways an identity is a proxy rather than an object, and they are kept
    apart because they are four different claims about the code:

    * a member path (`index` in `&index->slot_locks[i]`) -- the same type with
      two objects gives one token, so the name identifies a path;
    * an allocation site -- the graph knows *which* allocation this is and not
      who owns it, which is a question the ownership stage can act on;
    * a name the file does not declare -- a macro, an enum constant, a global
      from a header this parser never sees. `unknown` is an answer, and the
      candidate stays, capped, because a cross-file global is the most
      important shared state a race query can see;
    * `subject_exact == "false"` without a member path -- `arr[i]`, where the
      subscript is what makes the name a proxy and the member path is empty.
      This one has to be tested separately and not inferred from the path:
      `arr[i]` has no member and is still not an object.

    With `identity=False` only the last test applies, which is the stage 4 gate
    exactly.
    """
    if info.get("subject_exact") == "false":
        return {
            "fact": "SUBJECT_PATH",
            "detail": (
                "the name is the root of a longer expression (`s` in `s->buf`), so "
                "the same name elsewhere may be a different object"
            ),
        }
    if not identity:
        return None
    if info.get("subject_member"):
        return {
            "fact": "SUBJECT_PATH",
            "detail": (
                "the name is a member path (`slot_locks[i]`), and two objects of "
                "one type that share a member name share this token"
            ),
        }
    if info.get("subject_site"):
        return {
            "fact": "OWNERSHIP_UNKNOWN",
            "detail": (
                "an anonymous allocation is identified by its allocation site; "
                "what the graph does not know is who owns the object"
            ),
        }
    if not info.get("subject_decl"):
        return {
            "fact": "IDENTITY_UNKNOWN",
            "detail": (
                "no declaration of this name in this file, so the identity falls "
                "back to the spelling -- a macro, an enum constant, or a global "
                "declared in a header the parser does not read"
            ),
        }
    return None


def _lock_receiver_class(info: Mapping[str, Any]) -> str:
    """What the declared type says about a lock match: `mutex`, `non_mutex`, `unknown`, or "".

    Asked only when the match came from a *name* -- a member call
    (`g_pool_lock.lock()`), an assignment (`pl = pipeline.lock()`), or a RAII
    declaration (`lock_guard<mutex> g(m)`). When the vocabulary matched an API
    call instead (`pthread_mutex_lock(&pool)`), the callee is the evidence and
    the argument's declared type is a struct that merely contains a mutex, so
    classifying on it would exclude every real acquisition.

    An empty type is `unknown` and not a rejection: the name may be declared in
    a header this parser never reads, and "the graph cannot tell" has never been
    grounds for dropping a candidate in this query.
    """
    if info.get("subject_from") not in {"receiver", "assignment", "raii"}:
        return ""
    token = info.get("subject_type", "")
    if not token:
        return "unknown"
    if token in _MUTEX_TYPES:
        return "mutex"
    if token in _NON_LOCK_RECEIVER_TYPES:
        return "non_mutex"
    return "unknown"


def _lock_identity_cap(info: Mapping[str, Any], *, identity: bool = True) -> dict[str, Any] | None:
    """Why this lock cannot carry `resolved`, or None -- the stage 4.5 loosening.

    Stage 4 capped every lock recovered from a receiver or a declaration, and
    the reason was good: the subject of `g_pool_lock.lock()` is an expression,
    and nothing distinguished it from `pool->lock()`, where the name is a struct
    that may merely contain a mutex. Stage 4.5 answers the question with the
    declaration -- the subject now carries the type it was declared with -- so
    the cap is lifted in exactly one case: the identity is a plain declaration
    (no member path, no site, storage known) *and* the declared type is a known
    mutex. This is the only loosening the stage allows, and every other lock
    lands where stage 4 put it.

    `identity=False` reproduces stage 4's gate exactly, including the case it
    got wrong: an assigned subject (`pl = pipeline.lock()`) was never capped,
    because the assignment rule runs before the receiver rule. That column
    exists to isolate the extraction changes, so it must not carry the new rule.
    """
    source = info.get("subject_from", "")
    if not identity:
        if source in {"receiver", "raii"}:
            return {
                "fact": "LOCK_IDENTITY",
                "detail": (
                    "the lock was recovered from a receiver or a declaration, so the "
                    "name identifies an expression, not the object it names"
                ),
            }
        return None
    if source not in {"receiver", "raii", "assignment"}:
        return None
    if _lock_receiver_class(info) == "mutex":
        return None
    return {
        "fact": "LOCK_IDENTITY",
        "detail": (
            "the lock was recovered from a receiver or a declaration and its "
            "declared type is not a known mutex, so the name identifies an "
            "expression rather than the object it names"
        ),
    }


def _wanted(defect_key: str, defect_keys: Collection[str] | None) -> bool:
    """Whether a candidate for this matrix key was asked for.

    The filter lives inside the queries rather than after them because
    truncation happens inside the queries. A caller that asks for 4.6 and gets
    the first `max_candidates` rows of 4.1 filtered afterwards has not asked for
    4.6 at all: on `llama.cpp` the `--type 4.6` request returned zero candidates
    while the same database's coverage block said thirty existed.
    """
    return defect_keys is None or defect_key in defect_keys


def _non_lock_points(points: Mapping[str, Mapping[str, Any]]) -> frozenset[str]:
    """LOCK and UNLOCK points whose declared type says they are not mutexes.

    `vk_pipeline pl = pipeline.lock();` on a `std::weak_ptr` is the shape this
    exists for: the vocabulary matched a member named `lock`, the receiver is a
    smart pointer, and there is no lock in the program. These points are removed
    from the lock universe and counted, rather than kept and capped -- a capped
    candidate is a finding a person has to read, and this one is not a finding.
    """
    return frozenset(
        point_id
        for point_id, info in points.items()
        if info["event_type"] in {"LOCK", "UNLOCK"} and _lock_receiver_class(info) == "non_mutex"
    )


def _transfer_reading(
    info: Mapping[str, Any], name: str, identity_key: str, *, identity: bool = True
) -> str:
    """How this call hands the resource over, or "" if it does not.

    Two readings, and they are not equally good. When the call's own subject is
    the resource, the match is exact: `f(p)` is the resource, resolved to the
    same declaration. When the resource is a later argument the match is by
    spelling, because `arguments` holds root identifiers and the query has no
    declaration index to resolve them with -- so a same-named argument in an
    unrelated call on the path would also count.

    The second reading is kept anyway. It is the only way a later-argument
    hand-off is visible at all, and its failure direction is a candidate capped
    at `ambiguous` rather than a candidate reported `resolved` -- the same
    direction the first-argument rule has always had. The reading is named in
    the fact's detail so a reader can tell the two apart.
    """
    if info.get("subject_from") == "assignment":
        # The CALL row sharing the allocation's own expression
        # (`p = malloc(n)`) is the allocation itself wearing its syntax-axis
        # name; counting it would make every allocation in the repository
        # ambiguous.
        return ""
    if _identity(info, identity=identity) == identity_key and info.get("subject_from") == "argument":
        return "as the call's own subject"
    if not name:
        return ""
    # Not gated on `identity`: recording every argument is an *extraction*
    # change, and the column that isolates extraction (`identity=False`) has to
    # show it. An old row has no `arguments` key at all, so the split yields a
    # single empty string that no real name equals -- which is what keeps the
    # new code reading an old database identical to the old code reading it.
    arguments = info.get("arguments", "").split(ARGUMENT_SEPARATOR)
    if name in arguments:
        return f"as an argument named {name!r}, matched by spelling"
    return ""


def _method_name(info: Mapping[str, Any], names: Mapping[str, str] | None) -> str:
    """The owning symbol's qualified name, when the caller supplied a table.

    The events table stores `owner_symbol_id`, not the name -- identity is a
    hash by design (appendix B.2.1), so a pure function cannot recover a name
    from it. Callers that have the `nodes` table read it and pass it in; a
    caller that does not gets an empty string rather than a made-up name.
    """
    if not names:
        return ""
    return names.get(str(info.get("owner_symbol_id", "")), "")


def _span(info: Mapping[str, Any]) -> str:
    return f"{info.get('relative_path', '')}:{info.get('start_line', 0)}-{info.get('end_line', 0)}"


def _citable(point_id: str, points: Mapping[str, Mapping[str, Any]]) -> bool:
    """Whether a point is an operation in the source rather than an endpoint.

    The synthetic exit has no file and no line -- it is where control flow
    left, not something anyone wrote -- so it belongs in a path's point
    sequence and not in a fact list or a citation.
    """
    info = points.get(point_id)
    return info is not None and bool(info.get("relative_path"))


def _uncertain(fact: str, *, decisive: bool, status: str = AMBIGUOUS, **detail: Any) -> dict[str, Any]:
    """One named uncertainty.

    `decisive` says whether this fact is part of the predicate the candidate is
    about. A decisive fact that is ambiguous forces the candidate's own status
    to be ambiguous; a non-decisive one rides along as context. Every query
    that emits an uncertainty states which it is, because "the graph could not
    answer this candidate's question" and "the graph answered, and here is what
    it cannot speak to" are different claims that read identically without it.
    """
    return {"fact": fact, "status": status, "decisive": decisive, **detail}


def _point_fact(point_id: str, info: Mapping[str, Any], names: Mapping[str, str] | None) -> dict[str, Any]:
    return {
        "event": info["event_type"],
        "method": _method_name(info, names),
        "point": point_id,
        "subject": info.get("subject", ""),
        "subject_from": info.get("subject_from", ""),
        "matched_name": info.get("matched_name", ""),
        "source": _span(info),
    }


def _source_evidence(points: Iterable[str], table: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    """`path:line-line` per point, deduplicated in path order, never absolute."""
    seen: dict[str, None] = {}
    for point_id in points:
        if not _citable(point_id, table):
            continue
        seen.setdefault(_span(table[point_id]), None)
    return tuple(seen)


def _points_by_type(points: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for info in points.values():
        counts[info["event_type"]] = counts.get(info["event_type"], 0) + 1
    return dict(sorted(counts.items()))


def _count_caps(
    points: Mapping[str, Mapping[str, Any]],
    event_types: Collection[str],
    *,
    identity: bool = True,
) -> dict[str, int]:
    """How many points of each type carry an identity that cannot resolve.

    The count is by *reason*, not by type, because the reasons are four
    different claims about the code and a total would hide which one the stage
    actually moved. It is also the honest denominator for the acceptance table:
    "how many lock points does the graph now hold an identity for" is this
    count subtracted from the number of points with a subject.
    """
    counts: dict[str, int] = {}
    for info in points.values():
        if info["event_type"] not in event_types or not _identity(info, identity=identity):
            continue
        cap = _identity_cap(info, identity=identity)
        if cap is not None:
            counts[cap["fact"]] = counts.get(cap["fact"], 0) + 1
    return dict(sorted(counts.items()))


def _by_owner(points: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for point_id, info in points.items():
        owners.setdefault(str(info.get("owner_symbol_id", "")), []).append(point_id)
    return {owner: sorted(ids) for owner, ids in owners.items()}


def _reverse_adjacency(
    adjacency: Mapping[str, list[tuple[str, str, frozenset[str]]]]
) -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = {}
    for src, neighbours in adjacency.items():
        for _edge_id, dst, _flags in neighbours:
            reverse.setdefault(dst, []).append(src)
    return {node: sorted(set(sources)) for node, sources in reverse.items()}


def _closure(
    start: str, adjacency: Mapping[str, list[tuple[str, str, frozenset[str]]]], max_hops: int
) -> set[str]:
    """Every point reachable from `start`, breadth-first, capped at `max_hops`."""
    reached: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    seen = {start}
    while queue:
        current, hops = queue.popleft()
        if hops >= max_hops:
            continue
        for _edge_id, dst, _flags in adjacency.get(current, ()):
            if dst in seen:
                continue
            seen.add(dst)
            reached.add(dst)
            queue.append((dst, hops + 1))
    return reached


def _ancestors(
    start: str, reverse: Mapping[str, list[str]], max_hops: int
) -> set[str]:
    """Every point that can reach `start`, breadth-first, capped at `max_hops`."""
    reached: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    seen = {start}
    while queue:
        current, hops = queue.popleft()
        if hops >= max_hops:
            continue
        for src in reverse.get(current, ()):
            if src in seen:
                continue
            seen.add(src)
            reached.add(src)
            queue.append((src, hops + 1))
    return reached


def _holds_before(
    adjacency: Mapping[str, list[tuple[str, str, frozenset[str]]]],
    points: Mapping[str, Mapping[str, Any]],
    first: str,
    second: str,
    lock: str,
    unlocks: Mapping[str, frozenset[str]],
    max_hops: int,
) -> bool:
    """Is `lock` still held when `second` is reached from `first`?

    Holding is defined by what would end it: a path that reaches `second`
    without passing through an UNLOCK of the same lock. Blocking the unlock
    points is the whole test -- if the only ways from the first acquisition to
    the second run through a release, the lock was not held.
    """
    paths, _truncated = find_paths(
        adjacency,
        points,
        starts={first},
        is_target=lambda info: info is points[second],
        blocked_points=unlocks.get(lock, frozenset()),
        max_hops=max_hops,
        max_paths=1,
    )
    return bool(paths)


def _acquisition_path(
    adjacency: Mapping[str, list[tuple[str, str, frozenset[str]]]],
    points: Mapping[str, Mapping[str, Any]],
    first: str,
    second: str,
    lock: str,
    unlocks: Mapping[str, frozenset[str]],
    max_hops: int,
    max_paths: int,
) -> tuple[dict[str, Any], ...]:
    """The paths that show the first lock still held at the second.

    Bounded by `max_paths` because this is evidence a human reads, and the
    holding *test* is separate (`_holds_before`, which needs one path to
    answer yes). Recording every path would bloat the bundle without changing
    the answer.
    """
    paths, _truncated = find_paths(
        adjacency,
        points,
        starts={first},
        is_target=lambda info: info is points[second],
        blocked_points=unlocks.get(lock, frozenset()),
        max_hops=max_hops,
        max_paths=max_paths,
    )
    return tuple(path.to_dict() for path in paths)


# ----------------------------------------------------------------------
# 4.1 + 4.6 -- resource lifetime


def resource_lifetime(
    events: Iterable[Any],
    edges: Iterable[Any],
    *,
    subject: str | None = None,
    max_hops: int = 64,
    max_paths: int = 8,
    max_candidates: int = 20,
    include_locks: bool = True,
    names: Mapping[str, str] | None = None,
    identity: bool = True,
    defect_keys: Collection[str] | None = None,
    contracts: ContractTable | None = None,
) -> DefectQueryResult:
    """A resource acquired and never released on a path to the method's exit.

    Two modes share one walk. Mode A is matrix 4.1 (`ALLOC`/`RELEASE`), where
    the null guard of a failed allocation is excluded: `if (!p) return -1;` is
    not a leak. Mode B is the lock half of 4.6 (`LOCK`/`UNLOCK`), where the same
    exclusion is exactly wrong -- a failed lock is one of the error paths 4.6
    exists to report -- and where RAII acquisitions are excluded instead,
    because their release is a destructor the CFG cannot see.

    `resolved` requires that no name on the decisive path could have moved the
    resource elsewhere: a call that takes it as an argument, or a `return p;`
    that hands it to the caller, both cap the candidate at `ambiguous`.
    """
    points = materialize_points(events, edges)
    adjacency = build_adjacency(edges)
    raii_locks = frozenset(
        point_id
        for point_id, info in points.items()
        if info["event_type"] == "LOCK" and info.get("raii") == "true"
    )
    non_lock_points = _non_lock_points(points)
    groups: dict[tuple[str, str], list[ControlPath]] = {}
    truncated = False

    alloc_paths, alloc_truncated = unreleased_resources(
        edges, points, max_hops=max_hops, max_paths=max_paths
    )
    truncated = truncated or alloc_truncated
    for path in alloc_paths:
        groups.setdefault(("4.1", path.points[0]), []).append(path)

    lock_paths: list[ControlPath] = []
    if include_locks:
        lock_paths, lock_truncated = unreleased_resources(
            edges, points,
            acquire="LOCK", release="UNLOCK",
            exclude_null_guard=False, excluded=raii_locks | non_lock_points,
            max_hops=max_hops, max_paths=max_paths,
        )
        truncated = truncated or lock_truncated
        for path in lock_paths:
            groups.setdefault(("4.6", path.points[0]), []).append(path)

    candidates: list[Candidate] = []
    eliminations: list[dict[str, Any]] = []
    contract_covered = 0
    for (defect_key, anchor), paths in sorted(groups.items()):
        if not _wanted(defect_key, defect_keys):
            continue
        acquire = points[anchor]
        if subject is not None and _identity_display(acquire) != subject:
            continue
        covered = contracts is not None and _contracts_cover(paths, points, contracts)
        candidate = _lifetime_candidate(
            defect_key, anchor, acquire, paths, points, names, identity=identity,
            contracts=contracts, contracts_cover=covered, eliminations=eliminations,
        )
        if candidate is not None:
            candidates.append(candidate)
            contract_covered += 1 if covered else 0

    candidates.sort(key=Candidate.sort_key)
    truncated = truncated or len(candidates) > max_candidates
    coverage = {
        "acquire_points": sum(
            1 for info in points.values() if info["event_type"] == "ALLOC"
        ) + (sum(1 for info in points.values() if info["event_type"] == "LOCK") if include_locks else 0),
        "subjects": len({info.get("subject", "") for info in points.values()
                         if info["event_type"] in {"ALLOC", "LOCK"} and info.get("subject")}),
        "subjects_by_identity": len({
            _identity(info, identity=identity) for info in points.values()
            if info["event_type"] in {"ALLOC", "LOCK"} and _identity(info, identity=identity)
        }),
        "identity_resolved_points": sum(
            1 for info in points.values()
            if info["event_type"] in {"ALLOC", "LOCK"} and _identity(info) and not _identity_cap(info)
        ),
        # Rows written before this stage, or names the file does not declare:
        # they keep producing candidates on the spelling, which is why the
        # fallback exists. Counted so a reader can see how much of a result is
        # identity-backed and how much is a name.
        "identity_legacy_points": sum(
            1 for info in points.values()
            if info["event_type"] in {"ALLOC", "LOCK"} and _identity(info)
            and not info.get("subject_decl") and not info.get("subject_site")
        ),
        "allocation_sites": sum(
            1 for info in points.values() if info.get("subject_site")
        ),
        # Both sides of the stage 5C column. A reader comparing against a
        # pre-5C run needs the denominator: 55 → 42 is a fall in recall unless
        # the eliminated 13 are counted next to it.
        "candidates_before_elimination": len(candidates) + len(eliminations),
        "candidates": len(candidates),
        "candidates_by_key": _count_by_key(candidates),
        # Only counts when the lock walk ran: a coverage block describes the
        # work that happened, and mode A excludes nothing.
        "excluded_raii_locks": len(raii_locks) if include_locks else 0,
        # A member named `lock` on a type that is known not to be a mutex. Not a
        # finding and not a gap: a fact about the vocabulary, counted so the
        # number of LOCK events and the number of locks stay separable.
        "non_mutex_lock_points": len(non_lock_points) if include_locks else 0,
        "paths": len(alloc_paths) + len(lock_paths),
        "include_locks": include_locks,
        "max_hops": max_hops,
        "max_paths": max_paths,
        "semantic_points": len(points),
        "semantic_edges": sum(len(item) for item in adjacency.values()),
        "points_by_type": _points_by_type(points),
        **_contract_coverage(contracts, eliminations, contract_covered),
    }
    return DefectQueryResult(
        query=RESOURCE_LIFETIME, candidates=tuple(candidates[:max_candidates]),
        coverage=coverage, truncated=truncated,
    )


def _owner_ruling(
    defect_key: str, acquire: Mapping[str, Any], contracts: ContractTable
) -> dict[str, str] | None:
    """Rules that answer "who owns this now", for a resource.

    Mode B is excluded, and that is a measured decision rather than a stylistic
    one: on redis-50 seven of the twenty lock candidates keep their mutex in a
    file static, and holding a global mutex until the function returns is
    exactly what 4.6 exists to report. Shared storage makes a lock *more*
    reportable, not less, so storage and wrapper ownership are 4.1 rules only.
    """
    if defect_key != "4.1":
        return None
    storage = str(acquire.get("subject_storage", ""))
    if storage in contracts.storages:
        if storage == FUNCTION_STATIC_STORAGE:
            return {
                "reason": "STORAGE_OWNER_FUNCTION_STATIC",
                "provenance": f"graph:storage:{storage}",
                "detail": (
                    "the allocation is kept in a function-static slot, which outlives this "
                    "frame; whether a later call overwrites that slot without freeing it "
                    "first is not visible from one method"
                ),
            }
        return {
            "reason": "STORAGE_OWNER",
            "provenance": f"graph:storage:{storage}",
            "detail": (
                f"the allocation is kept in a {storage} slot, so it belongs to that owner "
                f"rather than to this frame"
            ),
        }
    type_token = str(acquire.get("subject_type", ""))
    if type_token and contracts.is_wrapper(type_token):
        return {
            "reason": "RAII_WRAPPER_TYPE",
            "provenance": f"declared:wrapper:{type_token}",
            "detail": (
                f"the allocation is held in {type_token}, which frees it on every path out "
                f"of the scope, including exception unwinding"
            ),
        }
    return None


def _pair_ruling(
    defect_key: str, acquire: Mapping[str, Any], contracts: ContractTable
) -> dict[str, str] | None:
    """The release obligation of a lock, when the callee hands it to the caller.

    Mode A is excluded: a resource has no acquire/release pairing whose
    obligation could be handed over.
    """
    if defect_key != "4.6":
        return None
    owner = str(acquire.get("owner_symbol_id", ""))
    if not owner or not contracts.caller_owns(owner):
        return None
    return {
        "reason": "PAIR_CALLER_OWNS",
        "provenance": f"inferred:pair:{contracts.pair_labels.get(owner, owner)}",
        "detail": (
            "this method is the acquire half of an acquire/release pair, so it returns with "
            "the lock held by contract and the release belongs to the caller"
        ),
    }


def _handover_reading(
    info: Mapping[str, Any], name: str, contracts: ContractTable
) -> dict[str, Any] | None:
    """How this call takes ownership of `name`, or None if it does not.

    The match is at the ordinal the contract names, and by spelling, because
    `arguments` holds root identifiers and the query has no declaration index to
    resolve them with. Both halves have to hold -- the call must carry at least
    that many arguments, and the name in that position must be this one -- so a
    shorter call or a same-shaped call to a different variable is not a hand-off.
    """
    if info.get("subject_from") == "assignment":
        # The CALL row sharing the allocation's own expression (`p = malloc(n)`)
        # is the allocation wearing its syntax-axis name, not a hand-off.
        return None
    callee = contracts.callee(info)
    if not callee:
        return None
    ordinals = contracts.consuming_ordinals(callee)
    if not ordinals:
        return None
    arguments = str(info.get("arguments", "")).split(ARGUMENT_SEPARATOR)
    for ordinal in ordinals:
        if ordinal < len(arguments) and arguments[ordinal] == name:
            return {
                "callee": callee,
                "ordinal": ordinal,
                "declared": callee in contracts.sinks,
            }
    return None


def _consumes_ruling(
    paths: Sequence[ControlPath],
    points: Mapping[str, Mapping[str, Any]],
    name: str,
    contracts: ContractTable,
) -> dict[str, str] | None:
    """Every path hands the resource to a callee that takes ownership.

    Every path, not any. The candidate exists because a path reaches the exit
    with no release, so a path that neither releases nor hands the resource over
    is still a leak: a call on one branch does not cover the other.
    """
    if not name or not paths:
        return None
    example: dict[str, Any] | None = None
    covered = 0
    for path in paths:
        for point_id in path.points[1:]:
            info = points.get(point_id)
            if info is None or info["event_type"] != "CALL":
                continue
            reading = _handover_reading(info, name, contracts)
            if reading:
                if example is None:
                    example = reading
                covered += 1
                break
    if example is None or covered != len(paths):
        return None
    return {
        "reason": "DECLARED_CONSUMES" if example["declared"] else "INFERRED_CONSUMES",
        "provenance": (
            f"{'declared' if example['declared'] else 'inferred'}"
            f":consumes:{example['callee']}"
        ),
        "detail": (
            f"every path passes this name to {example['callee']} as argument "
            f"{example['ordinal']}, which takes ownership of it"
        ),
    }


def _return_ruling(
    paths: Sequence[ControlPath],
    points: Mapping[str, Mapping[str, Any]],
    identity_key: str,
    *,
    identity: bool = True,
) -> dict[str, str] | None:
    """Every path returns the resource to the caller.

    Every path, for the same reason as `_consumes_ruling` -- and this gate is
    load-bearing rather than decorative. On llama.cpp three candidates return
    the resource on one path and leak it on another, which is the shape of a
    real defect; requiring only *a* transfer would have deleted all three.
    """
    if not identity_key or not paths:
        return None
    returning = 0
    for path in paths:
        for point_id in path.points[1:]:
            info = points.get(point_id)
            if info is None or info["event_type"] != "RETURN":
                continue
            if _identity(info, identity=identity) == identity_key:
                returning += 1
                break
    if returning != len(paths):
        return None
    return {
        "reason": "RETURN_TRANSFER",
        "provenance": "graph:return",
        "detail": (
            "every path out of this method returns the resource to the caller, so the "
            "release obligation leaves with it"
        ),
    }


def _contracts_cover(
    paths: Sequence[ControlPath],
    points: Mapping[str, Mapping[str, Any]],
    contracts: ContractTable,
) -> bool:
    """Whether every call on these paths is to a callee whose contract is known.

    "Known" means the callee is in the declared table or was inferred to consume
    an argument -- not merely that the call joined to a name. A joined call to a
    callee nobody has a contract for is still an unknown contract, and the
    missing-evidence line has to keep saying so. No calls at all is also not
    coverage: nothing was answered, so nothing is dropped.
    """
    calls = 0
    for path in paths:
        for point_id in path.points[1:]:
            info = points.get(point_id)
            if info is None or info["event_type"] != "CALL":
                continue
            calls += 1
            if not contracts.has_contract(contracts.callee(info)):
                return False
    return calls > 0


def _elimination_record(
    ruling: Mapping[str, str],
    defect_key: str,
    anchor: str,
    acquire: Mapping[str, Any],
    names: Mapping[str, str] | None,
) -> dict[str, Any]:
    """One eliminated candidate, with everything needed to audit the ruling.

    An elimination nobody can check is indistinguishable from a bug, so the
    record carries the same span and method a candidate would have cited, plus
    the `provenance` that says whether the ruling came off the graph, out of the
    declared table, or from a rule applied to the graph.
    """
    return {
        "reason": ruling["reason"],
        "provenance": ruling["provenance"],
        "detail": ruling["detail"],
        "defect_key": defect_key,
        "anchor": anchor,
        "subject": _identity_display(acquire),
        "subject_identity": _identity(acquire),
        # The candidate's own discriminator, so a reader can line an elimination
        # up against a run that did not eliminate it. Note that a discriminator
        # is not unique -- `parseOptions` allocates into the same file static at
        # eight lines -- so the difference between two runs is a lower bound on
        # the eliminations, not a count of them.
        "discriminator": f"{_identity(acquire)}|{acquire.get('owner_symbol_id', '')}",
        "storage": acquire.get("subject_storage", ""),
        "type": acquire.get("subject_type", ""),
        "method": _method_name(acquire, names),
        "span": _span(acquire),
    }


def _lifetime_candidate(
    defect_key: str,
    anchor: str,
    acquire: Mapping[str, Any],
    paths: Sequence[ControlPath],
    points: Mapping[str, Mapping[str, Any]],
    names: Mapping[str, str] | None,
    *,
    identity: bool = True,
    contracts: ContractTable | None = None,
    contracts_cover: bool = False,
    eliminations: list[dict[str, Any]] | None = None,
) -> Candidate | None:
    name = _identity_display(acquire)
    identity_key = _identity(acquire, identity=identity)
    is_lock = defect_key == "4.6"

    # Stage 5C's two path-independent rulings come first: they are facts about
    # where the resource is kept and whose obligation it is, so if either holds
    # there is nothing for the walk to add.
    if contracts is not None:
        ruling = _owner_ruling(defect_key, acquire, contracts) or _pair_ruling(
            defect_key, acquire, contracts
        )
        if ruling is not None:
            if eliminations is not None:
                eliminations.append(
                    _elimination_record(ruling, defect_key, anchor, acquire, names)
                )
            return None

    uncertain: list[dict[str, Any]] = []
    missing = [
        _MISSING_CALLEE_CONTRACT,
        _MISSING_RAII,
        _MISSING_ALIASING,
        _MISSING_RELEASE_IN_CALLEE,
    ]
    if is_lock:
        missing.extend([_MISSING_ERROR_PATH, _MISSING_DESTRUCTOR, _MISSING_GUARD_BINDING])
    if contracts is not None and contracts_cover:
        # Every call on these paths goes to a callee whose contract is known,
        # and none of them took the resource -- otherwise this candidate would
        # already have been eliminated. So the two lines that say "a callee
        # might own this" have been answered for this candidate and stop
        # claiming otherwise. `_MISSING_RAII` deliberately stays: a type that is
        # absent from the wrapper table is not evidence that it does not own.
        missing = [item for item in missing if item not in (
            _MISSING_CALLEE_CONTRACT, _MISSING_RELEASE_IN_CALLEE,
        )]

    status = RESOLVED if identity_key else UNRESOLVED
    if not identity_key:
        uncertain.append(_uncertain(
            "SUBJECT_UNRESOLVED", decisive=True,
            detail="the acquisition names no target, so the candidate cannot be attributed",
        ))
    else:
        cap = _identity_cap(acquire, identity=identity)
        if cap is not None:
            # The name identifies a path, a site or a spelling rather than the
            # object, which is the definition of a name-level proxy -- so the
            # candidate cannot be `resolved`.
            uncertain.append(_uncertain(
                cap["fact"], decisive=True, detail=cap["detail"],
                point=anchor, source=_span(acquire),
            ))
            status = AMBIGUOUS

    path_points: list[str] = []
    for path in paths:
        for point_id in path.points:
            if point_id not in path_points:
                path_points.append(point_id)

    for point_id in path_points[1:]:
        info = points.get(point_id)
        if info is None or not identity_key:
            continue
        event_type = info["event_type"]
        if event_type == "CALL" and not is_lock:
            # Tested before the identity guard, and deliberately: the call that
            # hands the resource over need not *name* it as its subject.
            # `RedisModule_SetKeyMeta(cls, key, buffer)` passes the allocation
            # as its third argument, so a call whose own subject is `cls` is
            # still the hand-off -- and reading only the first argument, which
            # is what stage 4 did, called that allocation still-owned.
            how = _transfer_reading(info, name, identity_key, identity=identity)
            if how:
                uncertain.append(_uncertain(
                    "OWNERSHIP_TRANSFER", decisive=True,
                    detail=f"this name is passed to a callee, which may take ownership ({how})",
                    point=point_id, source=_span(info),
                ))
                status = AMBIGUOUS if status == RESOLVED else status
            continue
        if _identity(info, identity=identity) != identity_key:
            continue
        if event_type == "RETURN":
            uncertain.append(_uncertain(
                "RETURN_TRANSFER", decisive=True,
                detail="the method returns this name, so ownership may leave with the caller",
                point=point_id, source=_span(info),
            ))
            status = AMBIGUOUS if status == RESOLVED else status

    # The path-dependent rulings. Each needs *every* path to show the transfer,
    # so they run after the walk rather than inside it: the walk dedups points
    # across paths, and a fact that holds on one path says nothing about the
    # other.
    if contracts is not None and not is_lock:
        ruling = _consumes_ruling(paths, points, name, contracts) or _return_ruling(
            paths, points, identity_key, identity=identity
        )
        if ruling is not None:
            if eliminations is not None:
                eliminations.append(
                    _elimination_record(ruling, defect_key, anchor, acquire, names)
                )
            return None

    if is_lock:
        lock_cap = _lock_identity_cap(acquire, identity=identity)
        if lock_cap is not None:
            uncertain.append(_uncertain(
                lock_cap["fact"], decisive=True, detail=lock_cap["detail"],
                point=anchor, source=_span(acquire),
            ))
            status = AMBIGUOUS if status == RESOLVED else status
        if acquire.get("matched_name") in NON_BLOCKING_ACQUIRES:
            uncertain.append(_uncertain(
                "BLOCKING_ACQUIRE", decisive=True,
                detail="the acquisition can fail without acquiring",
                point=anchor, source=_span(acquire),
            ))
            status = AMBIGUOUS if status == RESOLVED else status

    facts = tuple(
        _point_fact(point_id, points[point_id], names)
        for point_id in path_points
        if _citable(point_id, points)
    )
    return Candidate(
        defect_key=defect_key,
        query=RESOURCE_LIFETIME,
        subject={
            "kind": "lock" if is_lock else "allocation",
            "name": name,
            # The object, next to the spelling. The discriminator is built from
            # this and not from the name, so two objects that share a spelling
            # in one method mint two evidence ids rather than one.
            "identity": identity_key,
            "storage": acquire.get("subject_storage", ""),
            "type": acquire.get("subject_type", ""),
            "method": _method_name(acquire, names),
            "owner_symbol_id": acquire.get("owner_symbol_id", ""),
        },
        anchor=anchor,
        discriminator=f"{identity_key}|{acquire.get('owner_symbol_id', '')}",
        resolution_status=status,
        confidence=RESOURCE_CONFIDENCE[status],
        facts=facts,
        uncertain_facts=tuple(uncertain),
        paths=tuple(path.to_dict() for path in paths),
        source_evidence=_source_evidence(path_points, points),
        missing_evidence=tuple(missing),
        metadata={
            "exit_point": paths[0].points[-1] if paths else "",
            "anchor_span": {
                "relative_path": acquire.get("relative_path", ""),
                "start_line": acquire.get("start_line", 0),
                "end_line": acquire.get("end_line", 0),
            },
            "methods": [_method_name(acquire, names)] if _method_name(acquire, names) else [],
        },
    )


def _contract_coverage(
    contracts: ContractTable | None,
    eliminations: Sequence[Mapping[str, Any]],
    contract_covered: int,
) -> dict[str, Any]:
    """The stage 5C half of the coverage block, in one place.

    The keys are present even when no contract table was passed, with zero and
    empty values, so a comparison column has one schema rather than two. Every
    elimination is counted by reason; the records themselves are capped at
    `DISQUALIFIED_EVIDENCE_CAP`, which is set above the acceptance repositories'
    elimination counts so the sampling frame stays whole.

    A second, independent view of the same set is the diff between a run with a
    contract table and one without: `candidates_before_elimination` minus
    `candidates`, matched on `discriminator`. It carries no reason, which is why
    the records exist, but it is what makes the count checkable.
    """
    by_reason: dict[str, int] = {}
    for record in eliminations:
        reason = str(record.get("reason", ""))
        by_reason[reason] = by_reason.get(reason, 0) + 1
    table = contracts.coverage if contracts is not None else {}
    joined = int(table.get("call_points_with_callee", 0))
    contracted = int(table.get("call_points_with_contract", 0))
    return {
        "contracts_available": contracts is not None,
        "disqualified": dict(sorted(by_reason.items())),
        "disqualified_evidence": [dict(record) for record in eliminations[:DISQUALIFIED_EVIDENCE_CAP]],
        "disqualified_total": len(eliminations),
        "pairs_inferred": list(table.get("pairs_inferred", [])),
        "contract_anchoring_rejected": list(table.get("contract_anchoring_rejected", [])),
        "call_points_with_callee": joined,
        "call_points_unjoined": int(table.get("call_points_unjoined", 0)),
        "function_effects_declared": int(table.get("summaries_declared", 0)),
        "function_effects_inferred": int(table.get("summaries_inferred", 0)),
        # A joined call to a callee nobody has a contract for. Counted apart
        # from the unjoined ones because the two gaps have different fixes: one
        # is an extraction join, the other is corpus knowledge.
        "function_effects_unknown": max(0, joined - contracted),
        # Candidates that survived with every call on their paths contracted.
        # This is the missing-evidence conditioning made countable: it is how
        # much of the result the contract layer can now speak to in full.
        "candidates_with_known_callee_contract": contract_covered,
    }


def _count_by_key(candidates: Sequence[Candidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.defect_key] = counts.get(candidate.defect_key, 0) + 1
    return dict(sorted(counts.items()))


# ----------------------------------------------------------------------
# 1.3 + 1.4 -- lock order


def lock_order(
    events: Iterable[Any],
    edges: Iterable[Any],
    *,
    subject: str | None = None,
    max_hops: int = 64,
    max_paths: int = 8,
    max_candidates: int = 20,
    names: Mapping[str, str] | None = None,
    identity: bool = True,
    defect_keys: Collection[str] | None = None,
) -> DefectQueryResult:
    """Lock acquisitions in one order in one method and the opposite order in
    another, plus the self-deadlock shape of acquiring one lock twice.

    Acquisition order is the method's LOCK points by `ordinal`, which is source
    order by construction. That is a *lexical* order: under branches and loops
    the real order can differ, and the CFG is used for the one thing it can
    decide -- whether the first lock is still held when the second is taken.
    Holding is tested by blocking the UNLOCK points of the first lock, so a
    pair whose only connection runs through a release is not a pair.

    Inversions are indexed by the lock pair rather than by method pairs: with
    M methods taking locks, comparing every method with every other is M^2
    walks, while grouping the (first, second) pairs a method produces and
    looking up the reverse key visits each real inversion once.

    Every 1.3 candidate carries MAY_PARALLEL as `ambiguous` -- whether the two
    methods can run concurrently is not a fact the graph holds. When the
    repository contains no THREAD_SPAWN point at all, that uncertainty becomes
    a disqualification instead: nothing in the graph can run these methods at
    the same time, so the candidates are dropped and counted rather than
    reported as ambiguous.
    """
    points = materialize_points(events, edges)
    adjacency = build_adjacency(edges)
    non_lock_points = _non_lock_points(points)
    locks_by_method = _locks_by_method(points, excluded=non_lock_points)
    unlocks_by_subject = _unlocks_by_subject(points, identity=identity)
    # The identity is what the walk is about; the spelling is what a human
    # reads. Keeping them in two maps rather than one is the point of the
    # stage: `index->slot_locks[i]` and `index->global_lock` are two locks with
    # two identities and one root, and `--subject` still filters on the root a
    # person would type.
    display: dict[str, str] = {}

    pairs_by_key: dict[tuple[str, str], dict[str, tuple[str, str]]] = {}
    reentrant: list[tuple[str, str, str, str]] = []
    unidentified = 0
    for owner, entries in sorted(locks_by_method.items()):
        held: list[tuple[str, str]] = []
        for point_id, info in entries:
            name = _identity(info, identity=identity)
            if not name:
                unidentified += 1
                continue
            display.setdefault(name, _identity_display(info))
            if info["event_type"] == "UNLOCK":
                held = [(held_name, held_id) for held_name, held_id in held if held_name != name]
                continue
            if any(held_name == name for held_name, _ in held):
                first = next(held_id for held_name, held_id in held if held_name == name)
                reentrant.append((owner, first, point_id, name))
            else:
                for held_name, held_id in reversed(held):
                    pairs_by_key.setdefault((held_name, name), {})[owner] = (held_id, point_id)
                held.append((name, point_id))

    spawns = [point_id for point_id, info in points.items() if info["event_type"] == "THREAD_SPAWN"]
    candidates: list[Candidate] = []
    disqualified_no_threads = 0
    inversion_pairs = sorted(pairs_by_key) if _wanted("1.3", defect_keys) else ()
    for (first_lock, second_lock) in inversion_pairs:
        if first_lock >= second_lock:
            continue
        reverse = pairs_by_key.get((second_lock, first_lock))
        if not reverse:
            continue
        for owner_a, (a_first, a_second) in sorted(pairs_by_key[(first_lock, second_lock)].items()):
            for owner_b, (b_first, b_second) in sorted(reverse.items()):
                if owner_a == owner_b:
                    continue
                candidate = _lock_order_candidate(
                    first_lock, second_lock, owner_a, owner_b,
                    (a_first, a_second), (b_first, b_second),
                    points, adjacency, unlocks_by_subject, max_hops, max_paths, names,
                    display=display, identity=identity,
                )
                if subject is not None and candidate.subject["name"] != subject:
                    continue
                if not spawns:
                    disqualified_no_threads += 1
                    continue
                candidates.append(candidate)

    reentrant_candidates = sorted(reentrant) if _wanted("1.4", defect_keys) else ()
    for owner, first, second, lock_identity in reentrant_candidates:
        candidate = _self_deadlock_candidate(
            owner, first, second, lock_identity, points, adjacency, unlocks_by_subject,
            max_hops, max_paths, names, display=display, identity=identity,
        )
        if subject is not None and candidate.subject["name"] != subject:
            continue
        candidates.append(candidate)

    candidates.sort(key=Candidate.sort_key)
    truncated = len(candidates) > max_candidates
    coverage = {
        "methods_with_locks": len(locks_by_method),
        "lock_points": sum(
            1 for point_id, info in points.items()
            if info["event_type"] == "LOCK" and point_id not in non_lock_points
        ),
        # A member named `lock` on a type that is known not to be a mutex
        # (`std::weak_ptr`). Counted here as well as in the lifetime query,
        # because it is a fact about the vocabulary and not about either walk.
        "non_mutex_lock_points": len(non_lock_points),
        "unidentified_lock_points": unidentified,
        "lock_identities": len(display),
        # Counted over the points that are locks. A `weak_ptr::lock()` point is
        # excluded here for the same reason it is excluded from the walk: it has
        # no lock identity to be resolved or legacy about, and counting it as
        # identity-less would read as a coverage failure in a place where the
        # graph answered correctly.
        "identity_resolved_lock_points": sum(
            1 for point_id, info in points.items()
            if info["event_type"] in {"LOCK", "UNLOCK"} and point_id not in non_lock_points
            and _identity(info) and not _identity_cap(info)
        ),
        "identity_legacy_lock_points": sum(
            1 for point_id, info in points.items()
            if info["event_type"] in {"LOCK", "UNLOCK"} and point_id not in non_lock_points
            and _identity(info)
            and not info.get("subject_decl") and not info.get("subject_site")
        ),
        "lock_identity_caps": _count_caps(
            {point_id: info for point_id, info in points.items() if point_id not in non_lock_points},
            {"LOCK", "UNLOCK"}, identity=identity,
        ),
        "lock_pairs": sum(len(owners) for owners in pairs_by_key.values()),
        "inverted_pairs": sum(
            1 for (first, second) in pairs_by_key
            if first < second and (second, first) in pairs_by_key
        ),
        "reentrant_acquires": len(reentrant),
        "spawn_points": len(spawns),
        "candidates": len(candidates),
        "candidates_by_key": _count_by_key(candidates),
        "disqualified_no_threads": disqualified_no_threads,
        "max_hops": max_hops,
        "semantic_points": len(points),
        "semantic_edges": sum(len(item) for item in adjacency.values()),
        "points_by_type": _points_by_type(points),
    }
    return DefectQueryResult(
        query=LOCK_ORDER, candidates=tuple(candidates[:max_candidates]),
        coverage=coverage, truncated=truncated,
    )


def _locks_by_method(
    points: Mapping[str, Mapping[str, Any]], *, excluded: Collection[str] = ()
) -> dict[str, list[tuple[str, Mapping[str, Any]]]]:
    """LOCK and UNLOCK points per method, in acquisition order.

    Ordered by `start_line`, not by `ordinal`. Ordinal counts within
    `(owner, event_type)`, so LOCK ordinals and UNLOCK ordinals are two
    independent counters -- sorting the two types together by ordinal
    interleaves them and destroys the acquisition sequence (a method locking
    `a` then `b` and unlocking `b` then `a` would read as lock a, unlock b,
    lock b, unlock a). Source position is the only key that orders the two
    types against each other, and it is the honest one: acquisition order
    *is* a fact about where the calls are written.

    Two acquisitions on one line tie and fall back to the point id. That
    ordering is arbitrary but deterministic, and it is the same approximation
    the query's docstring already registers.

    `excluded` holds the points that are not acquisitions at all -- a member
    named `lock` on a type known not to be a mutex. They leave the sequence
    entirely rather than being capped downstream: they are not locks that the
    graph is unsure about, they are not locks.
    """
    grouped: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for point_id, info in points.items():
        if info["event_type"] not in {"LOCK", "UNLOCK"} or point_id in excluded:
            continue
        grouped.setdefault(str(info.get("owner_symbol_id", "")), []).append((point_id, info))
    return {
        owner: sorted(entries, key=lambda item: (item[1].get("start_line", 0), item[0]))
        for owner, entries in grouped.items()
    }


def _unlocks_by_subject(
    points: Mapping[str, Mapping[str, Any]], *, identity: bool = True
) -> dict[str, frozenset[str]]:
    """Unlock points per lock identity.

    Keyed by identity and not by spelling, because this map is what decides
    whether a lock is still held: a method that locks `index->a` and unlocks
    `index->b` holds the first one, and a name-keyed map would say it released
    it -- turning a real inversion into a pair that never overlaps.
    """
    unlocks: dict[str, set[str]] = {}
    for point_id, info in points.items():
        if info["event_type"] != "UNLOCK":
            continue
        key = _identity(info, identity=identity)
        if key:
            unlocks.setdefault(key, set()).add(point_id)
    return {name: frozenset(ids) for name, ids in unlocks.items()}


def _lock_order_candidate(
    first_lock: str,
    second_lock: str,
    owner_a: str,
    owner_b: str,
    side_a: tuple[str, str],
    side_b: tuple[str, str],
    points: Mapping[str, Mapping[str, Any]],
    adjacency: Mapping[str, list[tuple[str, str, frozenset[str]]]],
    unlocks: Mapping[str, frozenset[str]],
    max_hops: int,
    max_paths: int,
    names: Mapping[str, str] | None,
    *,
    display: Mapping[str, str] | None = None,
    identity: bool = True,
) -> Candidate:
    display = display or {}

    def _display_of(key: str) -> str:
        return display.get(key, key)

    sides = ((owner_a, first_lock, second_lock, side_a), (owner_b, second_lock, first_lock, side_b))
    facts: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    confirmed_both = True
    named_both = True
    exact_both = True
    for owner, first_key, second_key, (first_point, second_point) in sides:
        confirmed = _holds_before(
            adjacency, points, first_point, second_point, first_key, unlocks, max_hops
        )
        confirmed_both = confirmed_both and confirmed
        for role, lock_key, point_id in (
            ("first", first_key, first_point), ("second", second_key, second_point)
        ):
            info = points[point_id]
            facts.append({
                "side": "a" if owner == owner_a else "b",
                "role": role,
                "method": _method_name(info, names),
                "method_symbol_id": owner,
                "lock": display.get(lock_key, _identity_display(info)),
                "lock_identity": lock_key,
                # What the declaration said about this lock's type, which is
                # what decides whether the identity above may carry `resolved`.
                # Empty for a lock the vocabulary matched by API name: the
                # callee is the evidence there, not the argument's type.
                "lock_type": _lock_receiver_class(info),
                "point": point_id,
                "source": _span(info),
                "holding_confirmed": confirmed,
            })
            if _lock_identity_cap(info, identity=identity) is not None:
                named_both = False
            if _identity_cap(info, identity=identity) is not None:
                exact_both = False
        if confirmed:
            for path in _acquisition_path(
                adjacency, points, first_point, second_point, first_key, unlocks,
                max_hops, max_paths,
            ):
                paths.append({"side": "a" if owner == owner_a else "b", **path})
        else:
            uncertain.append(_uncertain(
                "HOLDING_CONFIRMED", decisive=True,
                detail=(
                    "no path from the first acquisition to the second avoids "
                    "releasing the first lock, so the two may not overlap"
                ),
                method=_method_name(points[first_point], names),
                lock=display.get(first_key, _identity_display(points[first_point])),
            ))
    if not named_both:
        uncertain.append(_uncertain(
            "LOCK_IDENTITY", decisive=True,
            detail=(
                "at least one lock was recovered from a receiver or a declaration "
                "whose declared type is not a known mutex"
            ),
        ))
    if not exact_both:
        # Two locks in one method ordered `index->a` then `index->b` are two
        # different objects named by the same root, and the inversion the graph
        # sees between them is between two names, not between two locks.
        uncertain.append(_uncertain(
            "SUBJECT_PATH", decisive=True,
            detail=(
                "at least one lock's identity is a path, a site or a spelling "
                "rather than a declaration, so two different locks can share it"
            ),
        ))
    for _owner, _first, _second, (first_point, second_point) in sides:
        for point_id in (first_point, second_point):
            if points[point_id].get("matched_name") in NON_BLOCKING_ACQUIRES:
                uncertain.append(_uncertain(
                    "BLOCKING_ACQUIRE", decisive=True,
                    detail="a non-blocking acquisition can fail without acquiring",
                    point=point_id, source=_span(points[point_id]),
                ))
    # Not decisive: whether the two methods can run at once is a separate
    # question from whether the two orders exist, and the graph answers the
    # second one. Marking it decisive would force every inversion to ambiguous
    # and the status would stop distinguishing anything.
    uncertain.append(_uncertain(
        "MAY_PARALLEL", decisive=False,
        detail="whether these two methods can run concurrently is not in the graph",
    ))

    status = RESOLVED if confirmed_both and named_both and exact_both else AMBIGUOUS
    anchor_owner = min(owner_a, owner_b)
    anchor = side_a[0] if anchor_owner == owner_a else side_b[0]
    other_owner = owner_b if anchor_owner == owner_a else owner_a
    return Candidate(
        defect_key="1.3",
        query=LOCK_ORDER,
        subject={
            "kind": "lock_pair",
            # The spellings a person would type, and the identities the walk
            # actually used. Two locks can share a spelling (`index->a` in one
            # method, `index->a` in another) and not share an identity.
            "name": f"{_display_of(first_lock)}|{_display_of(second_lock)}",
            "locks": [_display_of(first_lock), _display_of(second_lock)],
            "identities": [first_lock, second_lock],
            "method": _method_name(points[anchor], names),
            "owner_symbol_id": anchor_owner,
        },
        anchor=anchor,
        discriminator=f"{first_lock}|{second_lock}|{other_owner}",
        resolution_status=status,
        confidence=LOCK_ORDER_CONFIDENCE[status],
        facts=tuple(facts),
        uncertain_facts=tuple(uncertain),
        paths=tuple(paths),
        source_evidence=_source_evidence(
            [side_a[0], side_a[1], side_b[0], side_b[1]], points
        ),
        missing_evidence=(
            _MISSING_THREADS, _MISSING_LOCK_ALIAS, _MISSING_TRY_PATH, _MISSING_GUARD_BINDING,
        ),
        metadata={
            "methods": [
                name for name in (
                    _method_name(points[side_a[0]], names), _method_name(points[side_b[0]], names)
                ) if name
            ],
            "anchor_span": {
                "relative_path": points[anchor].get("relative_path", ""),
                "start_line": points[anchor].get("start_line", 0),
                "end_line": points[anchor].get("end_line", 0),
            },
            "exit_point": "",
        },
    )


def _self_deadlock_candidate(
    owner: str,
    first: str,
    second: str,
    lock_identity: str,
    points: Mapping[str, Mapping[str, Any]],
    adjacency: Mapping[str, list[tuple[str, str, frozenset[str]]]],
    unlocks: Mapping[str, frozenset[str]],
    max_hops: int,
    max_paths: int,
    names: Mapping[str, str] | None,
    *,
    display: Mapping[str, str] | None = None,
    identity: bool = True,
) -> Candidate:
    display = display or {}
    name = display.get(lock_identity, _identity_display(points[first]))
    confirmed = _holds_before(adjacency, points, first, second, lock_identity, unlocks, max_hops)
    lock_cap = _lock_identity_cap(points[first], identity=identity)
    cap = _identity_cap(points[first], identity=identity)
    status = RESOLVED if confirmed and lock_cap is None and cap is None else AMBIGUOUS
    # A recursive mutex is not decisive: it can exonerate the candidate, but
    # it does not stop the graph answering whether the same lock was taken
    # twice while held, which is what this candidate is about.
    uncertain: list[dict[str, Any]] = [_uncertain(
        "MUTEX_RECURSIVE", decisive=False,
        detail=(
            "a recursive mutex (PTHREAD_MUTEX_RECURSIVE) makes a second "
            "acquisition by the same thread legal"
        ),
    )]
    if not confirmed:
        uncertain.append(_uncertain(
            "HOLDING_CONFIRMED", decisive=True,
            detail="no path reaches the second acquisition without releasing the lock",
        ))
    if lock_cap is not None:
        uncertain.append(_uncertain(
            lock_cap["fact"], decisive=True, detail=lock_cap["detail"],
        ))
    if cap is not None:
        # `pthread_mutex_trylock(&index->slot_locks[i])` and
        # `pthread_rwlock_rdlock(&index->global_lock)` share the root `index`,
        # and a re-entrant acquisition of one lock is what 1.4 reports. The
        # member path in the identity keeps them apart; what it cannot do is
        # prove the object, so the candidate stays capped.
        uncertain.append(_uncertain(
            cap["fact"], decisive=True, detail=cap["detail"],
            point=first, source=_span(points[first]),
        ))
    paths: list[dict[str, Any]] = []
    if confirmed:
        paths.extend(
            _acquisition_path(adjacency, points, first, second, name, unlocks, max_hops, max_paths)
        )
    facts = tuple(
        {
            "side": "single",
            "role": role,
            "method": _method_name(points[point_id], names),
            "method_symbol_id": owner,
            "lock": name,
            "point": point_id,
            "source": _span(points[point_id]),
            "holding_confirmed": confirmed,
        }
        for role, point_id in (("first", first), ("second", second))
    )
    return Candidate(
        defect_key="1.4",
        query=LOCK_ORDER,
        subject={
            "kind": "lock",
            "name": name,
            "identity": lock_identity,
            "storage": points[first].get("subject_storage", ""),
            "type": points[first].get("subject_type", ""),
            "method": _method_name(points[first], names),
            "owner_symbol_id": owner,
        },
        anchor=first,
        discriminator=f"{lock_identity}|{owner}",
        resolution_status=status,
        confidence=SELF_DEADLOCK_CONFIDENCE[status],
        facts=facts,
        uncertain_facts=tuple(uncertain),
        paths=tuple(paths),
        source_evidence=_source_evidence([first, second], points),
        # The recursive-mutex gap leads for 1.4: it is the one fact that would
        # turn this candidate from a defect into correct code, and it is the
        # fact the graph is furthest from holding.
        missing_evidence=(
            _MISSING_RECURSIVE, _MISSING_THREADS, _MISSING_LOCK_ALIAS, _MISSING_TRY_PATH,
        ),
        metadata={
            "methods": [
                method for method in (_method_name(points[first], names),) if method
            ],
            "anchor_span": {
                "relative_path": points[first].get("relative_path", ""),
                "start_line": points[first].get("start_line", 0),
                "end_line": points[first].get("end_line", 0),
            },
            "exit_point": "",
        },
    )


# ----------------------------------------------------------------------
# 1.1 -- shared-data race


def race_condition(
    events: Iterable[Any],
    edges: Iterable[Any],
    *,
    subject: str | None = None,
    max_hops: int = 64,
    max_candidates: int = 20,
    names: Mapping[str, str] | None = None,
    identity: bool = True,
    defect_keys: Collection[str] | None = None,
) -> DefectQueryResult:
    """One object touched by two methods, at least one touch a write, where the
    graph cannot show the two touches are ordered or protected.

    This query is where the stage's falsifiability question is answered, and
    the answer is visible in its output rather than in a footnote: every
    candidate is `ambiguous`, because MAY_PARALLEL is not a relation the graph
    holds. Since stage 5A the access kind is a fact when the walker saw the
    access (READ/WRITE events) and a syntactic proxy only when it did not --
    the candidate's `access` metadata says which, per side, and `decided=False`
    marks the proxy. A shared variable that appears only in plain statements
    (`counter++`, `s->flag = true`) now produces an event; what is still lost
    is the access with no recoverable subject at all.

    The filters that remain are the ones a sparse graph can actually decide:
    an object that is only ever read on both sides is dropped, two methods that
    both hold the same resolved lock are dropped, and two methods that both
    touch the object atomically are dropped.

    What the candidates are grouped by is the *object* and not the spelling,
    which is the whole of stage 4.5's effect here: `int n` in one method and
    `int n` in another are two variables, so they cannot be a race, and the
    557,315 candidates this query returned for redis-50 -- every one of them a
    pair of same-named locals in two methods -- were pairs of objects that had
    nothing to do with each other. A name the file does not declare is grouped
    by spelling, exactly as before, because a cross-file global is the most
    important shared state this query can see.
    """
    points = materialize_points(events, edges)
    adjacency = build_adjacency(edges)
    reverse = _reverse_adjacency(adjacency)
    methods_index = _method_index(points, reverse, identity=identity)

    # The synchronization facilities, by identity. Subtracting them by spelling
    # is what stage 4 did, and it subtracted too much: the LOCK subject and the
    # race subject were both the root of a member path (`index`), so a lock on
    # `index->slot_locks[0]` read as proof that `index->field` was protected.
    # The root set below is measured rather than applied -- see the coverage key
    # it feeds -- because "a lock on the object a member path starts from
    # protects every member of it" is a policy, not a fact.
    synchronization: set[str] = set()
    synchronization_roots: set[str] = set()
    for info in points.values():
        if info["event_type"] in SYNCHRONIZATION_EVENTS and info.get("subject"):
            key = _identity(info, identity=identity)
            synchronization.add(key)
            synchronization_roots.add(key.split("#")[0])

    by_subject: dict[str, dict[str, list[str]]] = {}
    display: dict[str, str] = {}
    considered = 0
    root_matched = 0
    by_storage: Counter = Counter()
    subject_events = RACE_SUBJECT_EVENTS | RACE_ACCESS_EVENTS
    for point_id, info in sorted(points.items()):
        name = info.get("subject", "")
        if not name or info["event_type"] not in subject_events:
            continue
        considered += 1
        by_storage[info.get("subject_storage") or STORAGE_UNKNOWN] += 1
        key = _identity(info, identity=identity)
        display.setdefault(key, name)
        if key in synchronization:
            continue
        if key.split("#")[0] in synchronization_roots:
            root_matched += 1
        by_subject.setdefault(key, {}).setdefault(
            str(info.get("owner_symbol_id", "")), []
        ).append(point_id)

    access_events = 0
    access_events_by_storage: Counter = Counter()
    for info in points.values():
        if info["event_type"] in RACE_ACCESS_EVENTS:
            access_events += 1
            access_events_by_storage[info.get("subject_storage") or STORAGE_UNKNOWN] += 1

    spawns = [point_id for point_id, info in points.items() if info["event_type"] == "THREAD_SPAWN"]
    joins = [point_id for point_id, info in points.items() if info["event_type"] == "THREAD_JOIN"]
    thread_functions = {
        info.get("thread_function", "")
        for info in points.values()
        if info.get("thread_function")
    }

    spawn_index = _spawn_index(points)

    candidates: list[Candidate] = []
    read_read_pairs = 0
    disqualified_atomic = 0
    disqualified_same_lock = 0
    access_decided_pairs = 0
    access_proxy_pairs = 0
    multi_method = 0
    multi_method_by_storage: Counter = Counter()
    storage_of_identity: dict[str, str] = {}
    for point_id, info in sorted(points.items()):
        if info.get("subject") and info["event_type"] in subject_events:
            storage_of_identity.setdefault(
                _identity(info, identity=identity),
                info.get("subject_storage") or STORAGE_UNKNOWN,
            )
    for key, methods in sorted(by_subject.items()):
        if len(methods) < 2:
            continue
        multi_method += 1
        multi_method_by_storage[storage_of_identity.get(key, STORAGE_UNKNOWN)] += 1
        name = display[key]
        # `--subject` still filters on the spelling. It is the entry point a
        # person types, and it was never a promise about which object they
        # meant; the candidate's identity is what says that.
        if subject is not None and name != subject:
            continue
        # Everything the pair loop asks about one side depends on that side
        # alone: the access kind (and whether it was decided or is a proxy),
        # whether the name is touched atomically, and which lock gates it.
        # Computing them inside the pair loop made the cost of a name quadratic
        # in the number of methods touching it, and on a real repository that
        # is the whole query's runtime.
        #
        # `_protection` takes only the method's control-flow points. An access
        # event has no position in the graph, so domination is untestable for
        # it and feeding it in would read as "not gated" -- which would strip
        # `resolved` from subjects the graph has genuinely proven protected.
        # The access events ride in the same list for kind and evidence.
        sides: dict[str, tuple[str, bool, bool, dict]] = {}

        def cf_points(point_ids: list[str]) -> list[str]:
            return [
                point_id for point_id in point_ids
                if points[point_id]["event_type"] not in RACE_ACCESS_EVENTS
            ]

        def side(owner: str) -> tuple[str, bool, bool, dict]:
            if owner not in sides:
                point_ids = methods[owner]
                kind, decided = _access_kind(points, point_ids)
                sides[owner] = (
                    kind, decided,
                    _touches_atomically(points, point_ids, key, identity=identity),
                    _protection(
                        methods_index[owner], points, adjacency, cf_points(point_ids), max_hops,
                        identity=identity,
                    ),
                )
            return sides[owner]

        method_list = sorted(methods)
        for index, owner_a in enumerate(method_list):
            for owner_b in method_list[index + 1:]:
                kind_a, decided_a, atomic_a, protection_a = side(owner_a)
                kind_b, decided_b, atomic_b, protection_b = side(owner_b)
                if kind_a == "read" and kind_b == "read":
                    read_read_pairs += 1
                    continue
                if atomic_a and atomic_b:
                    disqualified_atomic += 1
                    continue
                if (
                    protection_a["status"] == RESOLVED
                    and protection_b["status"] == RESOLVED
                    and protection_a["lock"] == protection_b["lock"]
                ):
                    disqualified_same_lock += 1
                    continue
                # A pair is decided only when *both* sides read real access
                # events; one proxy side makes the whole pair's kind claim a
                # proxy claim, and the split has to say so.
                if decided_a and decided_b:
                    access_decided_pairs += 1
                else:
                    access_proxy_pairs += 1
                candidates.append(
                    _race_candidate(
                        name, key, owner_a, owner_b, methods[owner_a], methods[owner_b],
                        kind_a, kind_b, decided_a, decided_b,
                        protection_a, protection_b, points, names,
                        spawn_index,
                    )
                )

    candidates.sort(key=Candidate.sort_key)
    truncated = len(candidates) > max_candidates
    coverage = {
        "subjects_considered": considered,
        "subjects_multi_method": multi_method,
        # The denominator the stage's headline number has to be read against.
        # A multi-method subject is what a race candidate is made of, and the
        # storage class says what kind of object it is: a `local` or a
        # `parameter` cannot appear in two methods under a declaration
        # identity -- that is the whole of the 1.1 reduction -- so whatever is
        # left is `field`, `file_static`, `global`, or a name this file never
        # declares. Without this breakdown "817 subjects survived" is a number
        # with no explanation attached.
        "subjects_by_storage": dict(sorted(by_storage.items())),
        "multi_method_subjects_by_storage": dict(sorted(multi_method_by_storage.items())),
        "synchronization_subjects": len(synchronization),
        # The counterweight to `subjects_multi_method`, and the number that says
        # how much of the stage's 1.1 reduction is the identity and how much is
        # this subtraction. Under a name join the two sets overlapped by
        # spelling; under an identity join they are two sets of objects, and the
        # overlap is a fact worth counting rather than assuming.
        "synchronization_subjects_matched_by_identity": len(
            synchronization & set(by_subject)
        ),
        # What the loose policy would have removed -- a race on `index->field`
        # counts as protected because a lock somewhere is on `index->something`.
        # Reported and *not* applied: the lock is on a different member, and a
        # policy that quietens real races is not one this query adopts without
        # a number in front of it.
        "synchronization_subjects_matched_by_root": root_matched,
        "read_read_pairs": read_read_pairs,
        # The access layer's own accounting. `access_events` is every READ/WRITE
        # row the database holds -- the denominator for how much of the pair
        # space the layer covers. `access_proxy_pairs` is the part of the
        # candidate space still decided by the syntactic proxy; it should fall
        # as the layer fills in, and it must never be reported as zero unless
        # it really is.
        "access_events": access_events,
        "access_events_by_storage": dict(sorted(access_events_by_storage.items())),
        "access_decided_pairs": access_decided_pairs,
        "access_proxy_pairs": access_proxy_pairs,
        # The unknown-storage bucket mixes cross-file globals (the valuable
        # subjects) with names the declaration index cannot resolve (type
        # names, macro arguments). Reporting how many candidates stand on each
        # is what keeps that mixture visible instead of buried in a total.
        "candidates_by_identity_storage": dict(sorted(
            Counter(
                storage_of_identity.get(candidate.subject["identity"], STORAGE_UNKNOWN)
                for candidate in candidates
            ).items()
        )),
        "disqualified_atomic_both_sides": disqualified_atomic,
        "disqualified_same_lock": disqualified_same_lock,
        "spawn_points": len(spawns),
        "join_points": len(joins),
        "resolved_thread_functions": len(thread_functions),
        "may_parallel_decided": bool(spawns),
        "candidates": len(candidates),
        "candidates_by_key": _count_by_key(candidates),
        "max_hops": max_hops,
        "semantic_points": len(points),
        "semantic_edges": sum(len(item) for item in adjacency.values()),
        "points_by_type": _points_by_type(points),
    }
    return DefectQueryResult(
        query=RACE_CONDITION, candidates=tuple(candidates[:max_candidates]),
        coverage=coverage, truncated=truncated,
    )


def _access_kind(
    points: Mapping[str, Mapping[str, Any]], point_ids: Sequence[str]
) -> tuple[str, bool]:
    """The access kind of one side, and whether the answer was really decided.

    Stage 5A made READ/WRITE events, so the kind is a fact when the walker saw
    the access: any WRITE makes the side a write, otherwise a seen access makes
    it a read. When the side has no access event at all -- a database built
    before 5A, or a subject whose every touch sits in an expression the walker
    did not visit -- the syntactic proxy answers, and the returned flag says
    so. The flag is load-bearing: the candidate's metadata reports which sides
    are facts, and the coverage split counts proxy pairs rather than letting
    them pass silently as decided ones.
    """
    decided = False
    for point_id in point_ids:
        info = points[point_id]
        if info["event_type"] not in RACE_ACCESS_EVENTS:
            continue
        decided = True
        if info["event_type"] == "WRITE":
            return "write", True
    if decided:
        return "read", True
    # The proxy: the only signal that a touch mutates, on a database with no
    # access events, is that the source assigned to it, allocated it, or
    # released it.
    for point_id in point_ids:
        info = points[point_id]
        if info["event_type"] in {"ALLOC", "RELEASE"} or info.get("subject_from") == "assignment":
            return "write", False
    return "read", False


def _touches_atomically(
    points: Mapping[str, Mapping[str, Any]],
    point_ids: Sequence[str],
    identity_key: str,
    *,
    identity: bool = True,
) -> bool:
    return any(
        points[point_id]["event_type"] == "ATOMIC"
        and _identity(points[point_id], identity=identity) == identity_key
        for point_id in point_ids
    )


def _method_index(
    points: Mapping[str, Mapping[str, Any]],
    reverse: Mapping[str, list[str]],
    *,
    identity: bool = True,
) -> dict[str, dict[str, Any]]:
    """Per-method facts the protection test needs, computed once.

    The race query asks "does one lock gate this access" for every (subject,
    method) pair, and each ask walks the method. Indexing the method's points,
    its entry points and its unlock points once turns a per-pair cost into a
    per-method one -- which is what keeps the pair loop affordable on a
    repository with thousands of methods.

    Entry points are the method's points with no predecessor inside the
    method: edges are intra-owner, so "no incoming edge" is exactly "control
    flow can start here".
    """
    owners: dict[str, list[str]] = {}
    for point_id, info in points.items():
        owners.setdefault(str(info.get("owner_symbol_id", "")), []).append(point_id)

    index: dict[str, dict[str, Any]] = {}
    for owner, point_ids in owners.items():
        owned = set(point_ids)
        entries = sorted(
            point_id for point_id in point_ids
            if not (set(reverse.get(point_id, ())) & owned)
        )
        locks = sorted(
            point_id for point_id in point_ids if points[point_id]["event_type"] == "LOCK"
        )
        unlocks: dict[str, set[str]] = {}
        for point_id in point_ids:
            info = points[point_id]
            if info["event_type"] == "UNLOCK" and info.get("subject"):
                unlocks.setdefault(_identity(info, identity=identity), set()).add(point_id)
        index[owner] = {
            "points": sorted(point_ids),
            "entries": entries,
            "locks": locks,
            "unlocks": {name: frozenset(ids) for name, ids in unlocks.items()},
        }
    return index


def _blocked_by_lock(
    adjacency: Mapping[str, list[tuple[str, str, frozenset[str]]]],
    points: Mapping[str, Mapping[str, Any]],
    entries: Sequence[str],
    target: str,
    lock_point: str,
    max_hops: int,
) -> bool:
    """Does every path from the method's entries to `target` go through
    `lock_point`?

    This is domination, and the definition is the test: block the lock and ask
    whether the target is still reachable. The ancestor-set formulation is the
    one that looks right and is not -- a point before the lock is always an
    ancestor of an access after it, so "all ancestors are inside the lock's
    closure" is never true for a lock taken mid-method.
    """
    paths, _truncated = find_paths(
        adjacency, points,
        starts=entries,
        is_target=lambda info: info is points[target],
        blocked_points=(lock_point,),
        max_hops=max_hops,
        max_paths=1,
    )
    return not paths


def _protection(
    method: Mapping[str, Any],
    points: Mapping[str, Mapping[str, Any]],
    adjacency: Mapping[str, list[tuple[str, str, frozenset[str]]]],
    accesses: Sequence[str],
    max_hops: int,
    *,
    identity: bool = True,
) -> dict[str, Any]:
    """Whether one lock dominates every access of a name inside one method.

    `resolved` means a single LOCK point gates every access -- blocking it
    disconnects the access from the method's entry -- and is still held when
    the access happens. That is the only form of "protected" the graph can
    prove: a lock merely taken somewhere in the method says nothing.

    `ambiguous` means locks exist but none gates the access. `unresolved` means
    the method holds a lock whose subject could not be recovered, so what it
    guards is unknown -- which is a different claim from knowing it guards
    nothing.

    The method's own LOCK points are what get tested, not the subject's: a
    lock's subject is the mutex, never the data it guards, so a method that
    locks `g_lock` around `g_total` has no LOCK point carrying `g_total`.

    Two approximations are real and named in `missing_evidence`: a lock taken
    by a callee is invisible here, and so is a lock the caller already holds.
    """
    lock_points = method["locks"]
    if not lock_points:
        return {"status": AMBIGUOUS, "lock": "", "display": "", "detail": "no lock in this method"}
    if not accesses:
        # Stage 5A: an access event has no position in the control-flow graph,
        # so no lock can be tested against it. This must not fall through to
        # the `all(...)` below -- `all` over an empty sequence is True, and a
        # subject whose only touches are plain writes (`counter++`) would read
        # as gated by every lock in the method: a false `resolved` with the
        # confidence bump to match, on exactly the population the access layer
        # added. "Nothing can be said" is the honest status, and it is
        # `ambiguous`, not `unresolved` -- the lock subjects are fine; it is
        # the access that has nothing for the test to reach.
        return {
            "status": AMBIGUOUS, "lock": "", "display": "",
            "detail": "the access has no control-flow point, so nothing can be "
                      "said about what gates it",
        }

    for lock_point in lock_points:
        lock_key = _identity(points[lock_point], identity=identity)
        if not lock_key:
            continue
        if all(
            _blocked_by_lock(
                adjacency, points, method["entries"], access, lock_point, max_hops
            )
            and _holds_before(
                adjacency, points, lock_point, access, lock_key,
                method["unlocks"], max_hops,
            )
            for access in accesses
        ):
            # `lock` is the identity, because the caller compares two sides'
            # protections to decide whether both hold *the same* lock. `display`
            # is what the fact prints: a reader is owed the spelling.
            return {
                "status": RESOLVED, "lock": lock_key, "detail": "",
                "display": points[lock_point].get("subject", ""),
            }

    if any(not points[point_id].get("subject") for point_id in lock_points):
        return {
            "status": UNRESOLVED, "lock": "", "display": "",
            "detail": "a lock with no recoverable subject",
        }
    reachable = [
        lock_point
        for lock_point in lock_points
        if any(access in _closure(lock_point, adjacency, max_hops) for access in accesses)
    ]
    return {
        "status": AMBIGUOUS,
        "lock": _identity(points[reachable[0]], identity=identity) if reachable else "",
        "display": points[reachable[0]].get("subject", "") if reachable else "",
        # The detail has to match what was actually established: when no lock
        # reaches any access there is no reachability claim to retract.
        "detail": (
            "a lock reaches the access but does not gate it" if reachable
            else "no lock in this method reaches the access"
        ),
    }


def _access_summary(
    points: Mapping[str, Mapping[str, Any]],
    point_ids: Sequence[str],
    kind: str,
    decided: bool,
) -> dict[str, Any]:
    """One side's access evidence: the kind, whether it is a fact, and the
    event ids that say so.

    `writer_event` / `reader_event` are what the acceptance's evidence bundle
    quotes -- an id with a span, not a re-derivation. Empty when the side has
    no access event, which is exactly when `decided` is False and the kind is
    the syntactic proxy's answer.
    """
    writer = reader = ""
    for point_id in sorted(point_ids):
        event_type = points[point_id]["event_type"]
        if event_type == "WRITE" and not writer:
            writer = point_id
        elif event_type == "READ" and not reader:
            reader = point_id
    return {"kind": kind, "decided": decided, "writer_event": writer, "reader_event": reader}


def _race_candidate(
    name: str,
    identity_key: str,
    owner_a: str,
    owner_b: str,
    points_a: Sequence[str],
    points_b: Sequence[str],
    kind_a: str,
    kind_b: str,
    decided_a: bool,
    decided_b: bool,
    protection_a: Mapping[str, Any],
    protection_b: Mapping[str, Any],
    points: Mapping[str, Mapping[str, Any]],
    names: Mapping[str, str] | None,
    spawn_index: Mapping[str, Any],
) -> Candidate:
    protected = sum(
        1 for protection in (protection_a, protection_b) if protection["status"] == RESOLVED
    )
    anchor = min(points_a[0], points_b[0])
    facts = tuple(
        _point_fact(point_id, points[point_id], names)
        for point_id in sorted({*points_a, *points_b})
        if points[point_id]["event_type"] != "LOCK"
    )
    uncertain = [
        _uncertain(
            "MAY_PARALLEL", decisive=True,
            detail=_may_parallel_detail(spawn_index, owner_a, owner_b, names),
        ),
        _uncertain(
            "PROTECTED_BY", decisive=True, status=protection_a["status"],
            method=_method_name(points[points_a[0]], names),
            lock=protection_a["display"], detail=protection_a["detail"],
        ),
        _uncertain(
            "PROTECTED_BY", decisive=True, status=protection_b["status"],
            method=_method_name(points[points_b[0]], names),
            lock=protection_b["display"], detail=protection_b["detail"],
        ),
        _uncertain(
            "ACCESS_KIND", decisive=True,
            detail=(
                f"access kind from READ/WRITE events: {kind_a} vs {kind_b}"
                if decided_a and decided_b
                else f"write/read decided syntactically: {kind_a} vs {kind_b}"
            ),
        ),
    ]
    return Candidate(
        defect_key="1.1",
        query=RACE_CONDITION,
        subject={
            "kind": "shared_name",
            "name": name,
            "identity": identity_key,
            "method": _method_name(points[anchor], names),
            "owner_symbol_id": str(points[anchor].get("owner_symbol_id", "")),
        },
        anchor=anchor,
        # Both methods, canonically ordered, because the anchor does not say
        # which side it came from: it is the smaller *point* id, and point ids
        # are content hashes with no relation to the owner ids. Naming only the
        # larger owner -- which is often not the anchor's side -- gave every
        # pair that shared an anchor the same discriminator, and with it the
        # same evidence id: on redis-50, 889 distinct candidates minted one
        # citation. The pair is the candidate, so the pair is the name.
        #
        # Built from the identity rather than the spelling for the same reason:
        # `int n` in `f` and `int n` in `g` was a candidate on redis-50 and is
        # two variables here, so the id has to move with the object.
        discriminator=f"{identity_key}|{min(owner_a, owner_b)}|{max(owner_a, owner_b)}",
        resolution_status=AMBIGUOUS,
        confidence=RACE_CONFIDENCE[protected],
        facts=facts,
        uncertain_facts=tuple(uncertain),
        paths=(),
        source_evidence=_source_evidence(sorted({*points_a, *points_b}), points),
        # The READ/WRITE half of the evidence is no longer missing: the events
        # exist and are cited in `facts` and `metadata["access"]`. What is
        # missing is the relation side -- whether the contexts can run
        # concurrently, whether the lock actually guards the object, whether
        # the object tolerates the race -- which is the DFG's (stage 5B).
        missing_evidence=(
            _MISSING_CONCURRENCY, _MISSING_LOCK_GUARDS, _MISSING_WEAK_CONSISTENCY,
        ),
        metadata={
            "methods": [
                item for item in (
                    _method_name(points[points_a[0]], names),
                    _method_name(points[points_b[0]], names),
                ) if item
            ],
            "anchor_span": {
                "relative_path": points[anchor].get("relative_path", ""),
                "start_line": points[anchor].get("start_line", 0),
                "end_line": points[anchor].get("end_line", 0),
            },
            "exit_point": "",
            # `access_kinds` keeps its original shape ({owner: kind}) for the
            # consumers it already has; `access` is the stage 5A widening --
            # per side, whether the kind is a fact, and which events say so.
            "access_kinds": {owner_a: kind_a, owner_b: kind_b},
            "access": {
                owner_a: _access_summary(points, points_a, kind_a, decided_a),
                owner_b: _access_summary(points, points_b, kind_b, decided_b),
            },
        },
    )


def _short_name(qualified_name: str) -> str:
    return qualified_name.rsplit(".", 1)[-1] if qualified_name else ""


def _spawn_index(points: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Which methods start which thread entry points, read once per query.

    Rebuilding this per candidate made the query's cost the product of its
    candidate count and the repository's point count.
    """
    entry_of: dict[str, set[str]] = {}
    entries: set[str] = set()
    for info in points.values():
        if info["event_type"] != "THREAD_SPAWN":
            continue
        function = info.get("thread_function", "")
        if not function:
            continue
        entry_of.setdefault(str(info.get("owner_symbol_id", "")), set()).add(function)
        entries.add(function)
    return {"entry_of": entry_of, "entries": entries}


def _may_parallel_detail(
    spawn_index: Mapping[str, Any],
    owner_a: str,
    owner_b: str,
    names: Mapping[str, str] | None,
) -> str:
    """The strongest true statement about concurrency the spawn points support.

    The status is `ambiguous` either way -- a spawn point is not a schedule --
    but the *reason* is worth distinguishing, because "one method starts the
    other" is a much shorter leap to a real race than "threads exist somewhere
    in this repository". Matching a spawn's entry point to a method needs the
    names table: the spawn records the identifier as written, and a method is
    a symbol id, so without names the two cannot be lined up and the weakest
    reason is the honest one.
    """
    entry_of, all_entries = spawn_index["entry_of"], spawn_index["entries"]

    short_a = _short_name((names or {}).get(owner_a, ""))
    short_b = _short_name((names or {}).get(owner_b, ""))
    if short_b and short_b in entry_of.get(owner_a, ()):
        return f"this method starts {short_b}, which owns the other access"
    if short_a and short_a in entry_of.get(owner_b, ()):
        return f"the other method starts {short_a}"
    if short_a and short_b and {short_a, short_b} <= all_entries:
        return "both methods are thread entry points"
    if entry_of.get(owner_a) or entry_of.get(owner_b):
        return "one of the methods starts a thread"
    return "the repository starts threads somewhere, so neither method is ordered"


# ----------------------------------------------------------------------
# evidence


def candidate_evidence(
    candidate: Candidate,
    *,
    repository: str,
    commit: str,
    generation: int,
) -> Evidence:
    """The citable form of a candidate: one `E-DEFECT-...` id per candidate.

    `relation` carries the defect key rather than a constant. Two candidates
    anchored on the same event -- a 4.1 leak and a 4.6 unreleased lock on the
    same statement -- are different findings, and an id that ignored that would
    give them the same name.
    """
    span = candidate.metadata.get("anchor_span", {})
    start_line = span.get("start_line") or None
    end_line = span.get("end_line") or None
    methods = candidate.metadata.get("methods") or []
    return Evidence.create(
        kind="DEFECT_CANDIDATE",
        source_id=candidate.anchor,
        relation=candidate.defect_key,
        target_id=candidate.metadata.get("exit_point", ""),
        repository=repository,
        commit=commit,
        generation=generation,
        provenance="sparse_cfg",
        confidence=candidate.confidence,
        source_path=span.get("relative_path") or None,
        start_line=start_line,
        end_line=end_line,
        summary=(
            f"{candidate.defect_key} {candidate.query} candidate on "
            f"{candidate.subject.get('name', '')!r} ({candidate.resolution_status})"
        ),
        fact_id=candidate.discriminator,
        metadata={
            "defect_key": candidate.defect_key,
            "query": candidate.query,
            "resolution_status": candidate.resolution_status,
            "direct": True,
            "distance": 0,
            "boundary_relevant": False,
            "methods": list(methods),
        },
    )


def candidate_bundle(
    candidate: Candidate,
    *,
    evidence_id: str,
    generation: int,
    extra_missing: Iterable[str] = (),
) -> DefectEvidenceBundle:
    """The design doc §15 bundle for one candidate.

    `extra_missing` is where the caller states a gap it knows about and the
    query cannot: an active overlay, for instance, means every candidate here
    was computed against the base snapshot.
    """
    return DefectEvidenceBundle(
        defect_type=candidate.query,
        defect_key=candidate.defect_key,
        subject=dict(candidate.subject),
        facts=candidate.facts,
        uncertain_facts=candidate.uncertain_facts,
        paths=candidate.paths,
        source_evidence=candidate.source_evidence,
        missing_evidence=tuple([*candidate.missing_evidence, *extra_missing]),
        candidate_id=evidence_id,
        anchor=candidate.anchor,
        resolution_status=candidate.resolution_status,
        confidence=candidate.confidence,
        generation=generation,
    )

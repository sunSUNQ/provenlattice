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

import bisect
import inspect
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Collection, Iterable, Mapping, Sequence

from .evidence import DefectEvidenceBundle, Evidence
from .models import (
    STORAGE_FIELD, STORAGE_FILE_STATIC, STORAGE_FUNCTION_STATIC, STORAGE_GLOBAL,
    STORAGE_LOCAL, STORAGE_PARAMETER, STORAGE_UNKNOWN,
)
from .semantics.vocabulary import load_defect_patterns
from .sparsecfg import (
    ARGUMENT_SEPARATOR,
    BRANCH_FALSE,
    BRANCH_TRUE,
    SUBJECT_FROM_ASSIGNMENT,
    SUBJECT_FROM_RECEIVER,
    ControlPath,
    build_adjacency,
    find_paths,
    materialize_points,
)
# `_flow_key` is the data-flow graph's own notion of "the same object", and the
# stage 6 queries ask the same question it answers: which definition kills which
# live value. It is imported rather than re-derived from `_FLOW_FIELDS` because
# two definitions of one identity drift, and the drift would show up as a
# query that silently stops finding an intervening definition.
from .sparsedfg import (
    DATA_FLOW_TO,
    DEF_EVENTS,
    USE_EVENTS,
    _flow_key,
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
# Stage 6's four DFG-consuming queries. Each answers one matrix key except
# `taint_path`, which answers none (see `TAINT_KEY`).
NULL_FLOW = "null_flow"
USE_AFTER_FREE = "use_after_free"
DOUBLE_FREE = "double_free"
TAINT_PATH = "taint_path"
ERROR_HANDLING = "error_handling"
# I2A: two of the eight queries are ported; QUERY_NAMES is the honest
# dispatch surface until the rest join in later phases.
# I2B1 adds use_after_free (three of eight).
QUERY_NAMES = (
    NULL_FLOW, USE_AFTER_FREE, DOUBLE_FREE,
)

# The matrix keys the stage 6 queries answer. `taint_path` has no matrix family:
# `defect-evidence-matrix-v1.md` puts a taint analysis outside V2 (:286), and
# the roadmap asked for the registered minimum anyway. The key below is a
# *name* and not a matrix number, which is why `defect_patterns.toml` carries no
# row for it -- a key that looks like `3.1` and is not one would be worse than
# no key at all, so the query is addressed by its query name and nothing else.
NULL_FLOW_KEY = "3.1"
USE_AFTER_FREE_KEY = "4.3"
DOUBLE_FREE_KEY = "4.2"

USE_AFTER_FREE_CONFIDENCE = {RESOLVED: 0.5, AMBIGUOUS: 0.3, UNRESOLVED: 0.1}

# Confidence is a *band*, not a measurement: it says which of the three states
# the candidate landed in and how much of the pattern's decisive predicate the
# graph could answer, nothing more. Two runs of the same query give the same
# number because the number is a lookup, not an estimate.
# The stage 6 bands, and the taint band is deliberately the lowest in the file:
# a null flow and a double free are DFG facts with a CFG elimination test
# behind them, while a taint path is two declared names and a def-use edge with
# no sanitiser model at all. The number is not a measurement of how often the
# candidate is right; it is a statement of how much of the pattern's predicate
# the graph could answer, and for taint that is very little.
NULL_FLOW_CONFIDENCE = {RESOLVED: 0.5, AMBIGUOUS: 0.3, UNRESOLVED: 0.1}
DOUBLE_FREE_CONFIDENCE = {RESOLVED: 0.5, AMBIGUOUS: 0.3, UNRESOLVED: 0.1}
# Two states, not three, and the absence of `unresolved` is a fact about the
# query rather than an omission: its source population is *defined* as the calls
# whose stored value has a resolved declaration, so there is no candidate left
# to call unattributable. The band is the second lowest in the file because the
# predicate is an approximation -- the graph cannot read `fd == -1`, so "was the
# result examined" is answered by "did control branch afterwards".

# The flow classes stage 5B mints. Spelled as constants because three of the
# four queries select on them and a typo would silently return nothing.
NULL_TO_DEREF = "null_to_deref"
ALLOC_TO_USE = "alloc_to_use"
FREE_TO_USE = "free_to_use"
INPUT_TO_SINK = "input_to_sink"

# The two CHECK polarities. `polarity` is only ever written for a comparison
# whose other operand is the null literal (`sparsecfg` sets it nowhere else), so
# `fd == -1` and `ret != 0` are not CHECK points at all -- which is why the
# error-handling query cannot use this vocabulary and walks branches instead.
NULL_POLARITIES = frozenset({"true_when_null", "true_when_non_null"})

# The three answers a reachability question can have. `unknown` is the one that
# matters: a WRITE point has no position in the control-flow graph, so a flow
# edge sourced at one has nothing to search from, and every caller treats that
# as "cannot eliminate" rather than as "unreachable".
REACHABLE = "reachable"
DISJOINT = "disjoint"
REACH_UNKNOWN = "unknown"

# Acquisitions that can return without acquiring. Under one of these, "the lock
# is held on the error path" is not a fact the graph can assert, so any
# candidate that depends on it is capped at `ambiguous` rather than reported as
# resolved. Spelled out rather than pattern-matched on "try": `WaitForSingleObject`
# and `pthread_mutex_timedlock` belong here and contain no `try` at all.

# The declared types that are a mutex, as the last identifier of the spelling
# (`type_token` has already dropped the namespace and the template arguments, so
# `std::mutex` arrives as `mutex` and `std::shared_mutex` as `shared_mutex`).
# A set and not a substring test: `pool_mutex_holder` contains `mutex` and is
# not one, and a token that a name can accidentally contain is not evidence.

# The declared types whose member named `lock` is *known* to be something else.
# Deliberately one entry: `std::weak_ptr::lock()` returns a `shared_ptr` and is
# the standard library's only same-named non-acquisition. The list stays this
# short because the failure directions are not symmetric -- excluding a type the
# graph merely has not seen as a mutex would drop genuine acquisitions, and a
# class that wraps a mutex behind `.lock()` is ordinary (`pool->lock()` where
# `pool` is `HNSW *` must not be excluded). `shared_ptr` and `unique_ptr` are
# not listed: they define no `lock` member at all, so a match on those spellings
# would be a user type, and a spelling is not a type.

# The event types whose subject can name shared *data*. LOCK/UNLOCK/ATOMIC are
# synchronization facilities rather than the data they guard, and are subtracted
# from this set rather than added to it.
# The access events (stage 5A). They join the subject index -- an access with a
# subject is a touch of shared data like any other -- but never the protection
# test: `_blocked_by_lock` asks the control-flow graph whether a lock dominates
# an access, and an access event has no position in that graph (see
# `_EDGELESS_EVENT_TYPES` in `sparsecfg.py`). Two indexes per subject, two roles.
# C's thread-local objects (C11 §7.5): `errno` is a thread-local lvalue, so two
# methods touching it can never be a cross-method race no matter how the graph
# pairs them. Stage 5B's tuning ruling: exempted at *pairing* time only -- the
# access events stay in the graph (deleting true events would be lying about
# what the source does), the query just declines to pair on them. The count is
# reported, not hidden, and the list is closed pending evidence: the only other
# C/POSIX thread-local object is `h_errno`, which the corpora did not show.

# Retired in stage 4.5. The gap it registered -- `std::lock_guard<T> lock(m);`
# parsed as a function declaration and promoted to a symbol of its own, so only
# the brace spelling reached the graph with a lock identity -- was measured on a
# real C++ repository and is now closed at the source: the most-vexing-parse is
# demoted rather than promoted, and both spellings carry the mutex's identity.
# What remains of RAII recall is the guard-to-mutex binding below, which is a
# different gap with a different owner (the ownership stage).
# The one declaration the stage 6 review sheet named and the graph did not
# already carry (cases 16 and 17). An arm that ends in `abort()`, `assert()`, or
# a project's own failure macro ends there: it cannot reach what follows the
# branch, so two arms that are in fact exclusive do not both fall through. The
# graph holds a method's control flow, not the calling convention of the calls
# inside it, so the arm reads as falling through and the pair reads as
# reachable. Declared on the three queries whose verdict turns on that question
# -- double_free, the lock branch of resource_lifetime, and null_flow, whose own
# docstring already names this limit as the reason its middle state is
# `ambiguous`. The wording says "the conventions the graph does not hold" rather
# than "the graph does not model noreturn" on purpose: modelling the standard
# ones is a future change, and a project's own macros are the part no vocabulary
# closes. This line stays true across it.
_MISSING_NORETURN = (
    "the noreturn conventions the graph does not hold: an arm that ends in "
    "`abort`, `assert`, or a project's own failure macro does not return, so it "
    "cannot reach what follows the branch -- the graph holds the control flow "
    "and not the call's calling convention, and the arm reads as falling "
    "through, which leaves two mutually exclusive arms looking both reachable"
)
_MISSING_NULLABILITY = (
    "which calls can return NULL: the graph sees the allocation and the "
    "dereference, and whether this call's failure path is reachable at all is "
    "an API contract the AI side holds"
)
_MISSING_PARTIAL_GUARD = (
    "whether a guard covers every route to the dereference: the graph can say "
    "the null arm still reaches it, not whether some check upstream already "
    "excluded null on the paths that matter"
)
_MISSING_NULL_CONVENTION = (
    "the repository's release convention: whether a release leaves the pointer "
    "dangling or nulls it, which decides whether the second release is a double "
    "free or a legal `free(NULL)`"
)
_MISSING_ALIAS_PRECISION = (
    "whether two names really address one object: the alias annotation is a "
    "same-statement copy fact, so a pair joined through it is a candidate and "
    "not an identity"
)
_MISSING_ALIASING = (
    "aliasing and reassignment: `q = p; free(q)`, `free(p); p = NULL` and "
    "`p = realloc(p, n)` are all invisible without a data-flow graph"
)
_MISSING_FREE_WRAPPER = (
    "what a release wrapper does: whether it nulls the caller's pointer, "
    "whether it releases the whole object, and whether it releases at all"
)
_MISSING_USE_KIND = (
    "whether the use reads the pointer value or the pointee: `if (p)` after a "
    "release compares a dangling value, and the graph does not separate the "
    "two readings"
)
# UAF composition elimination records (I2B1, from PR #1 stage 5B)
_CALL_INTERVENING_DEF = {
    "reason": "CALL_INTERVENING_DEF",
    "provenance": "graph:flow_key",
    "detail": (
        "the identity is defined again between the release and the call, so the "
        "value the call uses is not the released one"
    ),
}
_CALL_MEMBER_MISMATCH = {
    "reason": "CALL_MEMBER_MISMATCH",
    "provenance": "graph:subject_member",
    "detail": (
        "the released object is a member path and the call's first argument is a "
        "provably different member of the same root, which is a different object"
    ),
}
_CALL_PATH_DISJOINT = {
    "reason": "CALL_PATH_DISJOINT",
    "provenance": "graph:control_reaches",
    "detail": (
        "the release cannot reach the call on the control-flow graph, so the call "
        "does not execute after the release on any path"
    ),
}
_USE_IS_RELEASE = {
    "reason": "USE_IS_RELEASE",
    "provenance": "graph:control_reaches",
    "detail": (
        "the call releases an object aliasing the one already released, which is "
        "matrix 4.2's question rather than this one"
    ),
}
_USE_READS_POINTER_VALUE = {
    "reason": "USE_READS_POINTER_VALUE",
    "provenance": "graph:event_type",
    "detail": (
        "the use is a null comparison, which reads the pointer's value rather "
        "than the object it pointed at"
    ),
}


def _statement_key(info: Mapping[str, Any]) -> tuple[str, str, int]:
    return (
        str(info.get("file_id", "")),
        str(info.get("owner_symbol_id", "")),
        int(info.get("start_line", 0) or 0),
    )
# Matrix 9.1's own "AI-required Semantics" column says this one out loud: which
# APIs must have their return value checked is API semantics, not a graph fact.
# It is also what keeps the candidate population honest -- a call whose result
# is a pointer to a fresh object has no failure to check, and only the API
# contract can say which calls those are. The query's job is to put the *stored
# and unexamined* calls in front of a reader, not to decide which of them
# mattered.


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


# The two structures every query reads off the published graph, named so the
# eight signatures that take them stay readable. Both are pure functions of
# `(events, edges)`, and neither is written to after construction -- see
# `_published_graph` for what that buys.
Points = dict[str, dict[str, Any]]
Adjacency = dict[str, list[tuple[str, str, frozenset[str]]]]


def run(
    query: str,
    events: Iterable[Any],
    edges: Iterable[Any],
    *,
    points: Points | None = None,
    adjacency: Adjacency | None = None,
    **kwargs: Any,
) -> DefectQueryResult:
    """Dispatch by name, passing each query only the parameters it accepts.

    The queries have deliberately different knobs: `max_paths` bounds a walk,
    and `race_condition` performs no walk -- a race candidate is a pair of
    accesses, so there is no path to cap. Filtering here rather than at every
    call site means a caller can offer the full parameter set without knowing
    which query uses which, and the signature remains the single source of
    truth about what each query honours.

    `points` and `adjacency` are the one pair every query shares. A caller
    running all eight -- `GraphQuery.get_defect_candidates(defect_type="all")`
    does -- builds them once and hands them in; a caller running one leaves
    them `None` and that query builds its own pair, which is what a test
    driving a single query directly has always done.
    """
    # I2A: two of the eight queries are ported; I2B1 adds use_after_free
    # (three of eight). The rest join in later phases and must never be
    # dispatched before they exist.
    functions: dict[str, Callable[..., DefectQueryResult]] = {
        NULL_FLOW: null_flow,
        USE_AFTER_FREE: use_after_free,
        DOUBLE_FREE: double_free,
    }
    try:
        function = functions[query]
    except KeyError:
        raise ValueError(
            f"unknown defect query: {query!r}; known: {', '.join(QUERY_NAMES)}"
        ) from None
    accepted = set(inspect.signature(function).parameters)
    supplied = {k: v for k, v in kwargs.items() if k in accepted}
    if "points" in accepted:
        supplied["points"] = points if points is not None else materialize_points(events, edges)
    if "adjacency" in accepted:
        supplied["adjacency"] = adjacency if adjacency is not None else build_adjacency(edges)
    return function(events, edges, **supplied)


# ----------------------------------------------------------------------
# shared reading of the published graph


def _published_graph(
    events: Iterable[Any], edges: Iterable[Any],
    points: Points | None, adjacency: Adjacency | None,
) -> tuple[Points, Adjacency]:
    """Whatever the caller already built, or build it now.

    One pair of structures can serve every query in a call because neither is
    written to after construction: a query reads `points` for an event's facts
    and walks `adjacency`, and the caches that *do* fill up as queries run --
    `_Reachability`'s reached-sets and breadth-first trees -- keep their state
    in objects of their own.

    Building them per query instead cost a `materialize_points` and a
    `build_adjacency` per query on the same `(events, edges)`, ten of each for
    one `all` run, and that redundancy was the bulk of its wall clock on the
    acceptance corpora.
    """
    if points is None:
        points = materialize_points(events, edges)
    if adjacency is None:
        adjacency = build_adjacency(edges)
    return points, adjacency


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

    Stage 5B adds one rung between `decl` and the fallbacks: an unknown root
    with a member path keeps the member (`name:server#io_threads_num`). Two
    fields of an object whose type nothing can resolve are still two objects;
    without this rung they collapsed into `name:server`, which once merged 765
    member paths of redis-50 into a single race bucket (92% of the 5A candidate
    growth). The member is part of the spelling the source itself wrote, so
    root+member is a weaker claim than `decl` but a strictly sharper one than
    the bare root.

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
    member = info.get("subject_member", "")
    if member and name:
        # The unknown-root rung: no declaration resolved, but the access
        # itself spells out which member it touches.
        return f"name:{name}#{member}"
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






def _wanted(defect_key: str, defect_keys: Collection[str] | None) -> bool:
    """Whether a candidate for this matrix key was asked for.

    The filter lives inside the queries rather than after them because
    truncation happens inside the queries. A caller that asks for 4.6 and gets
    the first `max_candidates` rows of 4.1 filtered afterwards has not asked for
    4.6 at all: on `llama.cpp` the `--type 4.6` request returned zero candidates
    while the same database's coverage block said thirty existed.
    """
    return defect_keys is None or defect_key in defect_keys






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




def _by_owner(points: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for point_id, info in points.items():
        owners.setdefault(str(info.get("owner_symbol_id", "")), []).append(point_id)
    return {owner: sorted(ids) for owner, ids in owners.items()}












# ----------------------------------------------------------------------
# 4.1 + 4.6 -- resource lifetime














def _edge_field(edge: Any, name: str) -> Any:
    """Read a field from a `SemanticEdge` object or its row, like the CFG
    loader's own field reader."""
    if isinstance(edge, dict):
        return edge[name]
    return getattr(edge, name)










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






def _count_by_key(candidates: Sequence[Candidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.defect_key] = counts.get(candidate.defect_key, 0) + 1
    return dict(sorted(counts.items()))


# ----------------------------------------------------------------------
# 1.3 + 1.4 -- lock order
















# ----------------------------------------------------------------------
# 1.1 -- shared-data race
























# ----------------------------------------------------------------------
# stage 6 -- the DFG-consuming queries (3.1, 4.3, 4.2, and taint)
#
# Four queries, one shared question. Stage 5B minted the data-flow edges and
# nothing consumed them but the contracts layer; these four read them directly,
# and each one's decisive test is a control-flow question asked *about* a flow
# edge: can the definition reach the use at all, and does anything stand
# between them that makes the pair legitimate.
#
# The elimination discipline is the one stage 5C set: a candidate is removed
# only when a graph fact proves the pattern cannot hold, and a question the
# graph cannot answer leaves the candidate standing with the question named in
# its `missing_evidence`. `_Reachability` below is what makes the first half of
# that affordable; the second half is why every query here has a state called
# `ambiguous` and a coverage block that counts what it declined to decide.


class _Reachability:
    """Node reachability over the control-flow graph, memoised per source.

    `find_paths` enumerates *paths*: every queue entry carries its own visited
    set, because two genuinely different ways round a loop are two facts. That
    is the right instrument for an evidence path and the wrong one for an
    unreachability question -- the search cannot collapse the exponential set
    of routes into one node visit, and a `max_hops=4096` call on the acceptance
    corpora never returned. What the eliminations below ask is the node
    question ("can this release reach this use at all"), which is one
    breadth-first pass per source, exact at any depth, and memoised because one
    source is asked about many targets.

    `state` answers in three values and the third is not a detail. A point with
    no position in the control-flow graph has nothing to search from and nothing
    to be found; `REACH_UNKNOWN` says exactly that, and every caller reads it as
    "cannot eliminate" rather than as "unreachable".

    Reading it the other way is not hypothetical, and it happened twice. A first
    cut eliminated all 52 of redis-50's null-flow candidates by treating the
    structural `false` on the flow edge as a verdict. Then the target side
    turned out to have the same shape: READ and WRITE points are in *no*
    control-flow edge at all (`_EDGELESS_EVENT_TYPES`), so "is this node in the
    graph" answers no for every one of them, and a query reading that as
    "unreachable" eliminates them structurally. On llama.cpp-69 that is 27 of
    the 47 `free_to_use` edges -- and a read through a released pointer is the
    defect the query exists to find, so the mistake deletes findings.
    """

    def __init__(
        self,
        adjacency: Mapping[str, list[tuple[str, str, frozenset[str]]]],
        points: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self._adjacency = adjacency
        self._points = points
        self._reached: dict[str, frozenset[str]] = {}
        # The breadth-first tree per source, kept only for the sources a route
        # was actually asked about. `from_` answers the node question and pays
        # no memory for predecessors; an elimination is the common case and it
        # never asks for a route.
        self._trees: dict[str, dict[str, tuple[str, str]]] = {}
        # Every point the control-flow graph mentions, as a source or as a
        # destination. Membership is the test for "this point has a position",
        # and it is read off the graph rather than off a list of event types:
        # the list lives in the walker and a second copy here would drift.
        self._nodes: frozenset[str] = frozenset(
            set(adjacency)
            | {dst for neighbours in adjacency.values() for _e, dst, _f in neighbours}
        )

    def has_position(self, point_id: str) -> bool:
        return point_id in self._nodes

    def from_(self, source: str) -> frozenset[str]:
        """Every point reachable from `source`, in one pass, computed once."""
        reached = self._reached.get(source)
        if reached is None:
            seen: set[str] = set()
            queue: deque[str] = deque([source])
            while queue:
                for _edge_id, dst, _flags in self._adjacency.get(queue.popleft(), ()):
                    if dst not in seen:
                        seen.add(dst)
                        queue.append(dst)
            reached = frozenset(seen)
            self._reached[source] = reached
        return reached

    def route(self, source: str, target: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """One shortest route from `source` to `target`, as points and edges.

        Read off the scan's own breadth-first tree rather than searched for,
        which is `error_handling`'s precedent (`_branch_scan`/`_route`): every
        point the walk entered has exactly one predecessor, so following them
        back is linear, and the route *is* the route the verdict was decided
        along -- it cannot disagree with `state`.

        Empty when there is no route to record, and that is not a verdict.
        A source with no control-flow position, a target the graph never
        mentions, and a pair `state` calls `disjoint` all land here; the
        question "are these connected" is `state`'s and is answered there.

        This is what `find_paths` used to do for the four flow queries, and it
        is the reason they were slow rather than the reason they were wrong:
        that helper enumerates simple paths with a per-path visited set and
        caps only what it *returns*, so a pair with fewer than `max_paths`
        routes between it -- including a pair with none -- drains its queue and
        pays for every route inside `max_hops`.
        """
        if source not in self._adjacency or target not in self._nodes:
            return (), ()
        tree = self._trees.get(source)
        if tree is None:
            tree = {}
            seen = {source}
            queue: deque[str] = deque([source])
            while queue:
                current = queue.popleft()
                for edge_id, dst, _flags in self._adjacency.get(current, ()):
                    if dst not in seen:
                        seen.add(dst)
                        tree[dst] = (current, edge_id)
                        queue.append(dst)
            self._trees[source] = tree
        if target not in tree:
            return (), ()
        route_points = [target]
        route_edges: list[str] = []
        cursor = target
        while cursor != source:
            step = tree.get(cursor)
            if step is None:  # unreachable by construction; reported as no route
                return (), ()
            cursor, edge_id = step
            route_edges.append(edge_id)
            route_points.append(cursor)
        route_points.reverse()
        route_edges.reverse()
        return tuple(route_points), tuple(route_edges)

    def state(self, source: str, target: str) -> str:
        """`reachable`, `disjoint`, or `unknown` when the graph cannot say.

        The two `unknown` clauses are different facts and both mean "do not
        eliminate". A source with no outgoing edge is a point the walker does
        not step through -- a WRITE, or a node the graph only ever arrives at --
        so there is nothing to search from. A target the graph never mentions
        has no position to be reached.
        """
        if source not in self._adjacency or target not in self._nodes:
            return REACH_UNKNOWN
        return REACHABLE if target in self.from_(source) else DISJOINT

    def null_side_reaches(self, check: str, target: str) -> bool:
        """Whether the check's *null* arm can still reach `target`.

        The seeding is `unchecked_dereferences`' own, read in the opposite
        direction: `if (p == NULL)` leaves through the true branch when the
        subject is null and `if (p != NULL)` through the false one, which is
        what `polarity` records. Callers pass only points whose polarity is one
        of the two null spellings -- a comparison against anything else is not
        a CHECK point at all.

        A target with no position in the graph answers True, which reads oddly
        until you look at what the caller does with it: the answer is used to
        *eliminate* the candidate as already guarded, and a question the graph
        cannot answer must not eliminate anything.
        """
        if target not in self._nodes:
            return True
        info = self._points.get(check, {})
        wanted = "branch=true" if info.get("polarity") == "true_when_null" else "branch=false"
        for _edge_id, dst, flags in self._adjacency.get(check, ()):
            if wanted in flags and (dst == target or target in self.from_(dst)):
                return True
        return False


def _alias_groups(points: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, frozenset[str]]]:
    """owner -> {root: roots the annotation ties to it}, in one pass.

    The `alias` annotation is a semicolon-joined list of the roots a bare copy
    joined (`q = p` stamps both ends), and it is per *owner* because two
    methods can each have a `p` and a `q` that have nothing to do with each
    other. Grouping in one pass is not a micro-optimisation: a per-owner
    builder that rescans every point is O(owners x points), which on
    llama.cpp-69 is two thousand owners against two hundred thousand points.
    The first version of the stage 6 probe never returned.
    """
    groups: dict[str, dict[str, set[str]]] = {}
    for point_id in sorted(points):
        info = points[point_id]
        annotation = str(info.get("alias", ""))
        subject = str(info.get("subject", ""))
        if not annotation or not subject:
            continue
        owner = str(info.get("owner_symbol_id", ""))
        for other in annotation.split(";"):
            if not other or other == subject:
                continue
            group = groups.setdefault(owner, {})
            group.setdefault(subject, set()).add(other)
            group.setdefault(other, set()).add(subject)
    return {
        owner: {root: frozenset(roots) for root, roots in group.items()}
        for owner, group in groups.items()
    }


def _alias_closure(
    group: Mapping[str, frozenset[str]], root: str
) -> frozenset[str]:
    """Every spelling the copy annotation ties to `root`, transitively.

    Takes *one owner's* group, not the owner-keyed table: the first version took
    the table and looked the owner up itself, and both callers passed the group
    they had already looked up, so every closure came back as the bare root and
    neither `double_free`'s alias pairing nor `use_after_free`'s alias-expanded
    call composition ever fired. The corpora did not show it -- no release pair
    in either one is joined by the annotation -- and a fixture did. The shape
    is narrowed to the one callers actually hold so it cannot be passed wrong.

    Includes `root` itself, so a caller can ask "is this spelling one of them"
    without a separate equality test. An unknown root closes to just the root,
    which is the honest answer: no annotation joined it to anything.
    """
    links = group
    seen = {root}
    stack = [root]
    while stack:
        for other in links.get(stack.pop(), ()):
            if other not in seen:
                seen.add(other)
                stack.append(other)
    return frozenset(seen)


def _flow_edges(edges: Iterable[Any]) -> list[tuple[str, str, Mapping[str, Any]]]:
    """`(src, dst, metadata)` for every DATA_FLOW_TO row, in edge order.

    In edge order rather than sorted, because the order is the writer's and the
    queries below sort what they build. The metadata is where `flow_class`,
    `via`, `via_copies` and `arg_root` live -- the facts that make an edge a
    candidate for one pattern and not another.
    """
    rows: list[tuple[str, str, Mapping[str, Any]]] = []
    for edge in edges:
        if _edge_field(edge, "relation") != DATA_FLOW_TO:
            continue
        rows.append((
            str(_edge_field(edge, "src_event_id")),
            str(_edge_field(edge, "dst_event_id")),
            _edge_field(edge, "metadata") or {},
        ))
    return rows


def _position(info: Mapping[str, Any]) -> tuple[int, str, int]:
    """A point's source order inside its method.

    Line first, because a reader's intuition is the written order; then the
    event type and the per-(owner, type) ordinal, which is what orders two
    points on one line (`free(p); free(q);`). This is for *deciding* order
    inside one method and never for a discriminator: a line number moves when
    the file is reindented, and an id that moves cannot be cited twice.
    """
    return (
        int(info.get("start_line", 0) or 0),
        str(info.get("event_type", "")),
        int(info.get("ordinal", 0) or 0),
    )


def _step(info: Mapping[str, Any]) -> str:
    """`TYPE:ordinal`, a stable name for a point inside its method.

    Ordinal is a per-(owner, event type) source-order counter, so this moves
    when a point moves and not when the file is reindented -- the property a
    discriminator needs, and the reason no discriminator here carries a line
    number.
    """
    return f"{info.get('event_type', '')}:{int(info.get('ordinal', 0) or 0)}"




def _record_elimination(
    ruling: Mapping[str, str],
    defect_key: str,
    anchor: str,
    info: Mapping[str, Any],
    names: Mapping[str, str] | None,
    by_reason: Counter,
    records: list[dict[str, Any]],
) -> None:
    """Count one elimination by reason and keep its record, up to the cap.

    The count has to be complete -- a coverage block whose totals move with the
    cap is not a coverage block -- while the records are the sampling frame,
    and `DISQUALIFIED_EVIDENCE_CAP` is set above the acceptance corpora's
    counts so the frame stays whole there.
    """
    by_reason[str(ruling["reason"])] += 1
    if len(records) < DISQUALIFIED_EVIDENCE_CAP:
        records.append(_elimination_record(ruling, defect_key, anchor, info, names))


def _disqualification_coverage(
    by_reason: Mapping[str, int], records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """The elimination half of a stage 6 coverage block.

    The same three keys the contracts layer uses, so the eight queries have one
    schema and a comparison column does not need a per-query reader.
    """
    return {
        "disqualified": dict(sorted(by_reason.items())),
        "disqualified_evidence": [dict(record) for record in records],
        "disqualified_total": sum(by_reason.values()),
    }


def _flow_path(
    reach: _Reachability,
    points: Mapping[str, Mapping[str, Any]],
    source: str,
    target: str,
    max_hops: int,
    max_paths: int,
) -> tuple[tuple[dict[str, Any], ...], bool]:
    """The evidence path from `source` to `target`, and whether it was cut short.

    One route, read off the reachability scan's own breadth-first tree, so the
    evidence and the verdict are the same fact stated twice rather than two
    searches that could disagree. A source with no control-flow position yields
    nothing here rather than an error: it is a fact about the graph, not a
    failure.

    This used to hand the two ends to `find_paths`. Measured on redis-50, the
    four queries that call this spent 163 of 177 seconds inside that helper --
    387 calls, 36 million `is_target` invocations -- for evidence nothing
    reads: `paths` is not part of `Candidate.sort_key`, so no candidate moves
    when it changes, and `state` decides the eliminations either way.

    Both ceilings survive, read the way the walk's own `_branch_scan` reads
    them: a route longer than `max_hops` is not recorded, and `max_paths` still
    bounds how many routes are. Dropping the first was measured and rejected --
    it recorded an 85-hop route on llama.cpp-69 where the enumeration had
    recorded none, which is evidence the caller never asked to pay for. What is
    recorded now is always a prefix of what was recorded before, which is what
    makes the candidate-zero-move gate exact rather than approximate.

    `truncated` is kept in the return shape and is now always False: the route
    either fits the ceiling or is not recorded, so there is no enumeration left
    to cut short. The key it feeds (`metadata["paths_truncated"]`) has no
    consumer, and dropping it would change a published schema for no gain.
    """
    if max_paths <= 0:
        return (), False
    route_points, route_edges = reach.route(source, target)
    if not route_points or len(route_edges) > max_hops:
        return (), False
    return ((
        {
            "points": list(route_points),
            "types": [
                points.get(point_id, {}).get("event_type", "") for point_id in route_points
            ],
            "edges": list(route_edges),
        },
    ), False)


_PATH_DISJOINT = {
    "reason": "PATH_DISJOINT",
    "provenance": "graph:control_reaches",
    "detail": (
        "the definition cannot reach this use on the control-flow graph, so the "
        "two are not on one path and the pattern cannot hold"
    ),
}
_GUARDED = {
    "reason": "GUARDED",
    "provenance": "graph:null_side",
    "detail": (
        "every check on this identity has a null arm that cannot reach the "
        "dereference, so the dereference runs only when the value is non-null"
    ),
}
_MEMBER_MISMATCH = {
    "reason": "MEMBER_MISMATCH",
    "provenance": "graph:subject_member",
    "detail": (
        "the two releases name different members of the same root, and a member "
        "is part of the object"
    ),
}
_INTERVENING_DEF = {
    "reason": "INTERVENING_DEF",
    "provenance": "graph:flow_key",
    "detail": (
        "the identity is defined again between the two releases, so the second "
        "release is of a new value"
    ),
}


def null_flow(
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
    points: Points | None = None,
    adjacency: Adjacency | None = None,
) -> DefectQueryResult:
    """Matrix 3.1: a null value reaching a dereference.

    Two sources, because C spells the pattern two ways. `null_to_deref` is the
    literal -- `p = NULL; *p`, or a chain of copies ending in one. The second is
    `alloc_to_use` whose use is a DEREFERENCE, which is the far more common
    shape: `p = malloc(n); *p` with the failure path never checked. On
    llama.cpp-69 that second source is 618 of the 626 edges.

    Two facts eliminate a candidate. A dereference the definition cannot reach
    is not this definition's dereference (`p = malloc(); if (err) return; *p`
    puts the two on different arms). And a dereference that only executes on the
    non-null side of a check is the checked pattern, not the defect -- that test
    is `unchecked_dereferences` read backwards, seeding from each check's null
    arm instead of looking for dereferences beyond it.

    The middle state is where most candidates land, and the reason is a
    modelling limit rather than a doubt about the code: a check on the identity
    that does *not* eliminate the candidate leaves it `ambiguous` even when the
    null arm still reaches the dereference, because that arm may leave the
    function through a call the graph cannot call `noreturn`. Only "no check at
    all on this identity" is `resolved`.
    """
    points, adjacency = _published_graph(events, edges, points, adjacency)
    reach = _Reachability(adjacency, points)
    checks_by_owner: dict[str, list[str]] = {}
    for point_id in sorted(points):
        info = points[point_id]
        if (info["event_type"] == "CHECK" and info.get("subject")
                and info.get("polarity") in NULL_POLARITIES):
            checks_by_owner.setdefault(str(info.get("owner_symbol_id", "")), []).append(point_id)

    population: Counter = Counter()
    states: Counter = Counter()
    by_reason: Counter = Counter()
    records: list[dict[str, Any]] = []
    candidates: list[Candidate] = []
    wanted = _wanted(NULL_FLOW_KEY, defect_keys)
    for source_id, target_id, metadata in _flow_edges(edges):
        target = points.get(target_id)
        if target is None:
            continue
        flow_class = str(metadata.get("flow_class", ""))
        if flow_class == NULL_TO_DEREF:
            kind = NULL_TO_DEREF
        elif flow_class == ALLOC_TO_USE and target["event_type"] == "DEREFERENCE":
            kind = "alloc_to_deref"
        else:
            continue
        population[kind] += 1
        if not wanted or (subject is not None and _identity_display(target) != subject):
            continue
        state = reach.state(source_id, target_id)
        if state == DISJOINT:
            _record_elimination(
                _PATH_DISJOINT, NULL_FLOW_KEY, target_id, target, names, by_reason, records
            )
            continue
        identity_key = _identity(target, identity=identity)
        owner = str(target.get("owner_symbol_id", ""))
        checks = [
            check_id for check_id in checks_by_owner.get(owner, ())
            if identity_key and _identity(points[check_id], identity=identity) == identity_key
        ]
        if checks and not any(reach.null_side_reaches(check_id, target_id) for check_id in checks):
            _record_elimination(
                _GUARDED, NULL_FLOW_KEY, target_id, target, names, by_reason, records
            )
            continue

        uncertain: list[dict[str, Any]] = []
        if not identity_key:
            status = UNRESOLVED
            uncertain.append(_uncertain(
                "SUBJECT_UNRESOLVED", decisive=True,
                detail="the dereference names no target, so the candidate cannot be attributed",
            ))
        else:
            status = RESOLVED
            cap = _identity_cap(target, identity=identity)
            if cap is not None:
                uncertain.append(_uncertain(
                    cap["fact"], decisive=True, detail=cap["detail"],
                    point=target_id, source=_span(target),
                ))
                status = AMBIGUOUS
            if tuple(metadata.get("via_copies", ()) or ()):
                uncertain.append(_uncertain(
                    "ALIAS_PATH", decisive=True,
                    detail=(
                        "the value reached this dereference through a copy, so the "
                        "identity is a same-statement join and not a proof of one object"
                    ),
                    point=target_id, source=_span(target),
                ))
                status = AMBIGUOUS
            if checks:
                uncertain.append(_uncertain(
                    "PARTIAL_GUARD", decisive=True,
                    detail=(
                        "a check on this identity exists but its null arm still reaches "
                        "the dereference, so some route to it is unguarded"
                    ),
                    point=checks[0], source=_span(points[checks[0]]),
                ))
                status = AMBIGUOUS
            if state == REACH_UNKNOWN:
                uncertain.append(_uncertain(
                    "REACH_UNKNOWN", decisive=True,
                    detail=(
                        "the definition has no position in the control-flow graph (a "
                        "write is not an operation the walker steps through), so the "
                        "graph cannot say the dereference runs after it"
                    ),
                    point=source_id,
                    source=_span(points[source_id]) if source_id in points else "",
                ))
                status = AMBIGUOUS

        states[status] += 1
        paths, truncated = _flow_path(
            reach, points, source_id, target_id, max_hops, max_paths
        )
        source_info = points.get(source_id, {})
        steps = [source_id, target_id]
        candidates.append(Candidate(
            defect_key=NULL_FLOW_KEY,
            query=NULL_FLOW,
            subject={
                "kind": "dereference",
                "name": _identity_display(target),
                "identity": identity_key,
                "storage": target.get("subject_storage", ""),
                "type": target.get("subject_type", ""),
                "member": target.get("subject_member", ""),
                "method": _method_name(target, names),
                "owner_symbol_id": owner,
            },
            anchor=target_id,
            discriminator=(
                f"{identity_key or 'anonymous'}|{owner}|"
                f"{_step(source_info)}|{_step(target)}"
            ),
            resolution_status=status,
            confidence=NULL_FLOW_CONFIDENCE[status],
            facts=tuple(
                _point_fact(point_id, points[point_id], names)
                for point_id in steps if _citable(point_id, points)
            ),
            uncertain_facts=tuple(uncertain),
            paths=paths,
            source_evidence=_source_evidence(steps, points),
            missing_evidence=(
                _MISSING_NULLABILITY, _MISSING_PARTIAL_GUARD, _MISSING_NORETURN,
            ),
            metadata={
                "flow_class": kind,
                "definition": {
                    "point": source_id,
                    "event": source_info.get("event_type", ""),
                    "source": _span(source_info) if source_info else "",
                    "via_copies": list(metadata.get("via_copies", ()) or ()),
                    "via": list(metadata.get("via", ()) or ()),
                },
                "reach": state,
                "path_recorded": bool(paths),
                "paths_truncated": truncated,
                "anchor_span": {
                    "relative_path": target.get("relative_path", ""),
                    "start_line": target.get("start_line", 0),
                    "end_line": target.get("end_line", 0),
                },
                "methods": [item for item in [_method_name(target, names)] if item],
                "exit_point": "",
            },
        ))

    candidates.sort(key=Candidate.sort_key)
    truncated = len(candidates) > max_candidates
    coverage = {
        "population": dict(sorted(population.items())),
        "states": dict(sorted(states.items())),
        "candidates": len(candidates),
        "candidates_by_key": _count_by_key(candidates),
        "check_points": sum(len(ids) for ids in checks_by_owner.values()),
        "max_hops": max_hops,
        "semantic_points": len(points),
        "semantic_edges": sum(len(item) for item in adjacency.values()),
        "points_by_type": _points_by_type(points),
        **_disqualification_coverage(by_reason, records),
    }
    return DefectQueryResult(
        query=NULL_FLOW, candidates=tuple(candidates[:max_candidates]),
        coverage=coverage, truncated=truncated,
    )








def double_free(
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
    points: Points | None = None,
    adjacency: Adjacency | None = None,
) -> DefectQueryResult:
    """Matrix 4.2: two releases of the same object on one path.

    This query reads no flow edge, because stage 5B mints none between two
    releases -- there is no def-use relation between a release and a release.
    It pairs RELEASE points inside one method instead, which is the same
    grouping the walker used to mint them.

    Two facts eliminate a pair, and one rule catches both shapes of the first.
    A definition of the identity between the releases means the second release
    is of a new value: `free(p); p = malloc(n); free(p)` is legal, and so is
    `free(p); p = NULL; free(p)`, since freeing null is defined behaviour. The
    second fact is reachability, and it is what makes the matrix's
    "disqualifying: mutually exclusive branches" true without a branch flag
    anywhere: two arms of a branch have no control path between them, so
    `if (x) free(p); else free(p);` produces no candidate at all.

    The member path is part of the identity here, and the corpus is why:
    adlist.c frees `node->value` on one line and `node` on the next, two
    different objects that share a root. A pair whose members differ is not a
    double free, and `subject_member` is what says so.
    """
    points, adjacency = _published_graph(events, edges, points, adjacency)
    reach = _Reachability(adjacency, points)
    by_owner = _by_owner(points)
    alias_groups = _alias_groups(points)
    population: Counter = Counter()
    states: Counter = Counter()
    by_reason: Counter = Counter()
    records: list[dict[str, Any]] = []
    candidates: list[Candidate] = []
    wanted = _wanted(DOUBLE_FREE_KEY, defect_keys)

    for owner in sorted(by_owner):
        point_ids = by_owner[owner]
        groups = alias_groups.get(owner, {})
        releases = [
            point_id for point_id in point_ids
            if points[point_id]["event_type"] == "RELEASE" and points[point_id].get("subject")
        ]
        if len(releases) < 2:
            continue
        definitions: dict[tuple[str, ...], list[tuple[int, str, int]]] = {}
        for point_id in point_ids:
            info = points[point_id]
            if info["event_type"] in DEF_EVENTS:
                definitions.setdefault(_flow_key(info), []).append(_position(info))
        for positions in definitions.values():
            positions.sort()
        positions_of = {point_id: _position(points[point_id]) for point_id in releases}
        ordered = sorted(releases, key=lambda point_id: positions_of[point_id])
        for index, first_id in enumerate(ordered):
            first = points[first_id]
            roots = _alias_closure(groups, str(first["subject"]))
            first_position = positions_of[first_id]
            between = definitions.get(_flow_key(first), ())
            for second_id in ordered[index + 1:]:
                second = points[second_id]
                second_position = positions_of[second_id]
                if second_position <= first_position:
                    continue
                population["same-owner-pair"] += 1
                if str(second["subject"]) not in roots:
                    continue
                population["same-identity-pair"] += 1
                if not wanted or (subject is not None and _identity_display(second) != subject):
                    continue
                if str(first.get("subject_member", "")) != str(second.get("subject_member", "")):
                    _record_elimination(
                        _MEMBER_MISMATCH, DOUBLE_FREE_KEY, second_id, second,
                        names, by_reason, records,
                    )
                    continue
                state = reach.state(first_id, second_id)
                if state == DISJOINT:
                    _record_elimination(
                        _PATH_DISJOINT, DOUBLE_FREE_KEY, second_id, second,
                        names, by_reason, records,
                    )
                    continue
                index_after = bisect.bisect_right(between, first_position)
                if index_after < len(between) and between[index_after] < second_position:
                    _record_elimination(
                        _INTERVENING_DEF, DOUBLE_FREE_KEY, second_id, second,
                        names, by_reason, records,
                    )
                    continue
                status = _release_pair_status(
                    first, second, state, identity=identity
                )
                states[status] += 1
                candidates.append(_double_free_candidate(
                    first_id, second_id, first, second, points, names, status,
                    identity=identity, reach=reach, max_hops=max_hops,
                    max_paths=max_paths, reach_state=state,
                ))

    candidates.sort(key=Candidate.sort_key)
    truncated = len(candidates) > max_candidates
    coverage = {
        "population": dict(sorted(population.items())),
        "states": dict(sorted(states.items())),
        "candidates": len(candidates),
        "candidates_by_key": _count_by_key(candidates),
        "max_hops": max_hops,
        "semantic_points": len(points),
        "semantic_edges": sum(len(item) for item in adjacency.values()),
        "points_by_type": _points_by_type(points),
        **_disqualification_coverage(by_reason, records),
    }
    return DefectQueryResult(
        query=DOUBLE_FREE, candidates=tuple(candidates[:max_candidates]),
        coverage=coverage, truncated=truncated,
    )


def _release_pair_status(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    state: str,
    *,
    identity: bool,
) -> str:
    """The state two releases of one root can carry.

    `resolved` needs all three of: both points declare an object, the two
    declarations are the *same* object, and the graph confirmed the first can
    reach the second. A pair joined only through the copy annotation is a
    candidate and not an identity, so it is `ambiguous`; so is a pair whose
    reachability question the graph could not answer at all. Either side
    without a declaration cannot be attributed, which is `unresolved` -- and on
    llama.cpp-69 that is most of the population, because a range-for loop
    variable and a lambda capture are released without a declaration identity.
    """
    first_key = _identity(first, identity=identity)
    second_key = _identity(second, identity=identity)
    if not first_key or not second_key:
        return UNRESOLVED
    if not (first.get("subject_decl") and second.get("subject_decl")):
        return UNRESOLVED
    if first_key != second_key:
        return AMBIGUOUS
    if _identity_cap(first, identity=identity) or _identity_cap(second, identity=identity):
        return AMBIGUOUS
    if state != REACHABLE:
        return AMBIGUOUS
    return RESOLVED


def _double_free_candidate(
    first_id: str,
    second_id: str,
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    points: Mapping[str, Mapping[str, Any]],
    names: Mapping[str, str] | None,
    status: str,
    *,
    identity: bool,
    reach: _Reachability,
    max_hops: int,
    max_paths: int,
    reach_state: str,
) -> Candidate:
    """One double-free candidate, anchored on the *second* release.

    The second release is the defect -- the first was legitimate -- so the
    anchor, the subject and the citation are the second point's, and the first
    travels in the facts and the metadata as its antecedent.
    """
    identity_key = _identity(second, identity=identity)
    owner = str(second.get("owner_symbol_id", ""))
    paths, truncated = _flow_path(reach, points, first_id, second_id, max_hops, max_paths)
    uncertain: list[dict[str, Any]] = []
    if not identity_key:
        uncertain.append(_uncertain(
            "SUBJECT_UNRESOLVED", decisive=True,
            detail="the release names no target, so the candidate cannot be attributed",
        ))
    elif not (first.get("subject_decl") and second.get("subject_decl")):
        uncertain.append(_uncertain(
            "IDENTITY_UNKNOWN", decisive=True,
            detail=(
                "a release on this path names no declaration, so the two releases "
                "are joined by spelling rather than by object"
            ),
            point=second_id, source=_span(second),
        ))
    elif identity_key != _identity(first, identity=identity):
        uncertain.append(_uncertain(
            "ALIAS_PAIR", decisive=True,
            detail=(
                "the two releases are joined through a same-statement copy "
                "annotation, which is a candidate-level alias and not an identity"
            ),
            point=first_id, source=_span(first),
        ))
    else:
        cap = _identity_cap(second, identity=identity)
        if cap is not None:
            uncertain.append(_uncertain(
                cap["fact"], decisive=True, detail=cap["detail"],
                point=second_id, source=_span(second),
            ))
    if reach_state == REACH_UNKNOWN:
        uncertain.append(_uncertain(
            "REACH_UNKNOWN", decisive=True,
            detail=(
                "the first release has no position in the control-flow graph, so "
                "the graph cannot say the second runs after it"
            ),
            point=first_id, source=_span(first),
        ))
    steps = [first_id, second_id]
    return Candidate(
        defect_key=DOUBLE_FREE_KEY,
        query=DOUBLE_FREE,
        subject={
            "kind": "release",
            "name": _identity_display(second),
            "identity": identity_key,
            "storage": second.get("subject_storage", ""),
            "type": second.get("subject_type", ""),
            "member": second.get("subject_member", ""),
            "method": _method_name(second, names),
            "owner_symbol_id": owner,
        },
        anchor=second_id,
        discriminator=(
            f"{identity_key or 'anonymous'}|{owner}|{_step(first)}|{_step(second)}"
        ),
        resolution_status=status,
        confidence=DOUBLE_FREE_CONFIDENCE[status],
        facts=tuple(
            _point_fact(point_id, points[point_id], names)
            for point_id in steps if _citable(point_id, points)
        ),
        uncertain_facts=tuple(uncertain),
        paths=paths,
        source_evidence=_source_evidence(steps, points),
        missing_evidence=(
            _MISSING_NULL_CONVENTION, _MISSING_ALIAS_PRECISION, _MISSING_NORETURN,
        ),
        metadata={
            "first_release": {
                "point": first_id,
                "source": _span(first),
                "subject": first.get("subject", ""),
                "declared": bool(first.get("subject_decl")),
            },
            "second_release": {
                "point": second_id,
                "source": _span(second),
                "subject": second.get("subject", ""),
                "declared": bool(second.get("subject_decl")),
            },
            "reach": reach_state,
            "path_recorded": bool(paths),
            "paths_truncated": truncated,
            "anchor_span": {
                "relative_path": second.get("relative_path", ""),
                "start_line": second.get("start_line", 0),
                "end_line": second.get("end_line", 0),
            },
            "methods": [item for item in [_method_name(second, names)] if item],
            "exit_point": "",
        },
    )


















# ----------------------------------------------------------------------
# D5: error_handling (matrix 9.1)


# The three verdicts one forward walk from a call can reach, plus the two the
# elimination records use.


# A call whose every spelled name is one the *compiler* resolves -- a vector
# intrinsic or a `__builtin_*` -- is pure computation: its result is a value,
# not a status, and "was the result checked" has no reading for it. The
# stage-6 ruling on matrix 9.1's idx 27 says exactly that
# (`ggml/src/ggml-cpu/arch/x86/repack.cpp:1646`,
# `iacc_1 = _mm256_add_epi16(iacc_1, _mm256_maddubs_epi16(...))`).
#
# The rule is "**every** name the line spells", not "any", and that is the
# whole of its safety argument: `x = f(_mm256_add_epi16(a, b))` spells `f` as
# well, so the line keeps its candidate -- a real call with a real failure mode
# is never dropped because an intrinsic shares its line. Measured on the frozen
# corpora, "any" would have taken those with it. A line that spells no name at
# all is kept too: absence of a reference row is not evidence of a builtin.
#
# The reference layer is the only place a spelled name exists -- a CALL point
# carries `matched_name`, which is the *node type* (`call_expression`), not the
# callee -- so this reads `raw_references` the way the taint query does, and
# the query layer hands the rows in.
















# The window ceiling is the frozen T2 rule. It is a fact about the verdict, not
# a tuning knob: a walk that stops early reads "no branch found yet" where the
# rule reads "checked", so a caller's smaller ceiling would manufacture
# candidates. On llama.cpp-69, the delivery layer's 64-hop default -- tuned for
# the evidence-path walks of the six sibling queries -- turned 6,189 windows
# into spurious candidates that the frozen rule eliminates. Callers may raise
# the ceiling; they may not lower it.




def use_after_free(
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
    points: Points | None = None,
    adjacency: Adjacency | None = None,
) -> DefectQueryResult:
    """Matrix 4.3: a use of an object after the same identity was released.

    Two halves, and the second exists because the first is nearly empty.
    Stage 5B's `free_to_use` edges are minted in *source order* and are
    path-blind -- `live_free` is never cleared, so a release on one arm pairs
    with a use on another -- and on the acceptance corpora almost every such
    edge connects no path at all: 11 of 11 on redis-50, 46 of 47 on
    llama.cpp-69, and the two sampled by hand were `free(x); return;` cleanup
    arms. The reachability test is therefore not a refinement here; it is what
    separates the flow class from a UAF.

    The second half is the shape 5B does not mint an edge for at all:
    `free(p); sink(p)`. A CALL is not a USE event (stage 3's registered gap), so
    the release kills the live definition and the argument path finds nothing.
    The composition here closes that at query time: for every release, every
    call in the same method whose argument roots include a spelling the copy
    annotation ties to the released root, positioned after it, reachable from
    it, with no redefinition of the identity in between.

    Every candidate from that composition is `ambiguous`, and the reason is
    structural: `_root_identifier` strips `&`, so `f(p)` and `f(&p)` are the
    same fact here, and one of them passes the object out while the other only
    reads it. On redis-50 this composition is not a corner case -- it is the
    bulk of the result, because the corpus's dominant shape is a callee that
    re-allocates through a pointer argument (`len = redisFormatCommand(&cmd,
    ...)`), which no fact in the graph distinguishes from a use.
    """
    points, adjacency = _published_graph(events, edges, points, adjacency)
    reach = _Reachability(adjacency, points)
    population: Counter = Counter()
    states: Counter = Counter()
    by_reason: Counter = Counter()
    records: list[dict[str, Any]] = []
    candidates: list[Candidate] = []
    wanted = _wanted(USE_AFTER_FREE_KEY, defect_keys)

    for source_id, target_id, metadata in _flow_edges(edges):
        if str(metadata.get("flow_class", "")) != FREE_TO_USE:
            continue
        target = points.get(target_id)
        if target is None:
            continue
        population["edge"] += 1
        if not wanted or (subject is not None and _identity_display(target) != subject):
            continue
        state = reach.state(source_id, target_id)
        if state == DISJOINT:
            _record_elimination(
                _PATH_DISJOINT, USE_AFTER_FREE_KEY, target_id, target, names, by_reason, records
            )
            continue
        if target["event_type"] == "CHECK":
            _record_elimination(
                _USE_READS_POINTER_VALUE, USE_AFTER_FREE_KEY, target_id, target,
                names, by_reason, records,
            )
            continue
        status = _use_status(
            target, metadata, state, identity=identity, escaping=target["event_type"] == "RETURN"
        )
        candidate = _use_candidate(
            source_id, target_id, target, points, names, status, identity=identity,
            reach=reach, max_hops=max_hops, max_paths=max_paths,
            flow_class=FREE_TO_USE, composition=False,
        )
        states[status] += 1
        candidates.append(candidate)

    # The query-time composition: `free(p); sink(p)`, which 5B mints no edge
    # for. Grouped per owner because the alias annotation and the point ids are
    # method-local, and built in one pass for the reason `_alias_groups` gives.
    by_owner = _by_owner(points)
    alias_groups = _alias_groups(points)
    releases_by_statement: dict[tuple[str, str, int], list[str]] = {}
    for point_id in sorted(points):
        info = points[point_id]
        if info["event_type"] == "RELEASE" and info.get("subject"):
            releases_by_statement.setdefault(_statement_key(info), []).append(point_id)
    for owner in sorted(by_owner):
        point_ids = by_owner[owner]
        groups = alias_groups.get(owner, {})
        releases = [
            point_id for point_id in point_ids
            if points[point_id]["event_type"] == "RELEASE" and points[point_id].get("subject")
        ]
        if not releases:
            continue
        calls_by_root: dict[str, list[tuple[str, int]]] = {}
        definitions: dict[tuple[str, ...], list[tuple[int, str, int]]] = {}
        for point_id in point_ids:
            info = points[point_id]
            if info["event_type"] == "CALL" and info.get("arguments"):
                for index, argument in enumerate(str(info["arguments"]).split(ARGUMENT_SEPARATOR)):
                    if argument:
                        calls_by_root.setdefault(argument, []).append((point_id, index))
            elif info["event_type"] in DEF_EVENTS:
                definitions.setdefault(_flow_key(info), []).append(_position(info))
        for positions in definitions.values():
            positions.sort()
        for release_id in releases:
            release = points[release_id]
            roots = _alias_closure(groups, str(release["subject"]))
            release_position = _position(release)
            release_member = str(release.get("subject_member", ""))
            between = definitions.get(_flow_key(release), ())
            matching: dict[str, list[int]] = {}
            for root in sorted(roots):
                for call_id, index in calls_by_root.get(root, ()):
                    matching.setdefault(call_id, []).append(index)
            for call_id in sorted(matching):
                call = points[call_id]
                call_position = _position(call)
                if call_position <= release_position:
                    continue
                population["call-composition"] += 1
                if not wanted or (subject is not None and _identity_display(call) != subject):
                    continue
                # A member-expression release is eliminated only when the one
                # argument whose member is recoverable proves a different
                # object. `subject_member` describes the true first argument
                # exactly when `subject_from` is `argument` -- for an assignment
                # right-hand side the subject is the *target*, so
                # `len = redisFormatCommand(&cmd, ...)` has subject `len`.
                if (release_member and sorted(matching[call_id]) == [0]
                        and call.get("subject_from") == "argument"
                        and str(call.get("subject_member", "")) != release_member):
                    _record_elimination(
                        _CALL_MEMBER_MISMATCH, USE_AFTER_FREE_KEY, call_id, call,
                        names, by_reason, records,
                    )
                    continue
                # `free(p); free(q)` with `q` aliasing `p` is matrix 4.2's
                # question. The test is graph-only: a release call has a RELEASE
                # point on its own statement, so a call that shares a statement
                # with a release of an aliasing root is a release and not a use.
                if any(
                    str(points[other].get("subject", "")) in roots
                    for other in releases_by_statement.get(_statement_key(call), ())
                ):
                    _record_elimination(
                        _USE_IS_RELEASE, USE_AFTER_FREE_KEY, call_id, call,
                        names, by_reason, records,
                    )
                    continue
                if reach.state(release_id, call_id) == DISJOINT:
                    _record_elimination(
                        _CALL_PATH_DISJOINT, USE_AFTER_FREE_KEY, call_id, call,
                        names, by_reason, records,
                    )
                    continue
                index_after = bisect.bisect_right(between, release_position)
                if index_after < len(between) and between[index_after] < call_position:
                    _record_elimination(
                        _CALL_INTERVENING_DEF, USE_AFTER_FREE_KEY, call_id, call,
                        names, by_reason, records,
                    )
                    continue
                candidates.append(_use_candidate(
                    release_id, call_id, call, points, names, AMBIGUOUS,
                    identity=identity, reach=reach, max_hops=max_hops,
                    max_paths=max_paths, flow_class=FREE_TO_USE,
                    composition=True, reach_state=reach.state(release_id, call_id),
                ))
                states[AMBIGUOUS] += 1

    candidates.sort(key=Candidate.sort_key)
    truncated = len(candidates) > max_candidates
    coverage = {
        "population": dict(sorted(population.items())),
        "states": dict(sorted(states.items())),
        "candidates": len(candidates),
        "candidates_by_key": _count_by_key(candidates),
        "call_composition_candidates": sum(
            1 for candidate in candidates
            if candidate.metadata.get("use_from") == "call-composition"
        ),
        "max_hops": max_hops,
        "semantic_points": len(points),
        "semantic_edges": sum(len(item) for item in adjacency.values()),
        "points_by_type": _points_by_type(points),
        **_disqualification_coverage(by_reason, records),
    }
    return DefectQueryResult(
        query=USE_AFTER_FREE, candidates=tuple(candidates[:max_candidates]),
        coverage=coverage, truncated=truncated,
    )


def _use_status(
    target: Mapping[str, Any],
    metadata: Mapping[str, Any],
    state: str,
    *,
    identity: bool,
    escaping: bool,
) -> str:
    """The state a use can carry, given what the graph answered about it.

    `escaping` is the RETURN case: a method that returns a dangling pointer has
    handed the decision to its caller, which is a real finding and not one this
    graph can call resolved. The copy hop and the unanswerable reachability
    question are the same caps the null-flow query applies, for the same
    reason: both are name-level joins rather than proofs of one object.
    """
    if not _identity(target, identity=identity):
        return UNRESOLVED
    if _identity_cap(target, identity=identity) is not None:
        return AMBIGUOUS
    if tuple(metadata.get("via_copies", ()) or ()):
        return AMBIGUOUS
    if state == REACH_UNKNOWN or escaping:
        return AMBIGUOUS
    return RESOLVED


def _use_candidate(
    release_id: str,
    use_id: str,
    use: Mapping[str, Any],
    points: Mapping[str, Mapping[str, Any]],
    names: Mapping[str, str] | None,
    status: str,
    *,
    identity: bool,
    reach: _Reachability,
    max_hops: int,
    max_paths: int,
    flow_class: str,
    composition: bool,
    reach_state: str = "",
) -> Candidate:
    """One UAF candidate, from either half of the query.

    The subject is the *use*, because that is where the defect happens: the
    release is a legitimate operation and the finding is that something ran
    after it. The release is carried in the facts and the metadata so a reader
    can see both ends without opening the graph.
    """
    identity_key = _identity(use, identity=identity)
    owner = str(use.get("owner_symbol_id", ""))
    release = points.get(release_id, {})
    paths, truncated = _flow_path(reach, points, release_id, use_id, max_hops, max_paths)
    uncertain: list[dict[str, Any]] = []
    if not identity_key:
        uncertain.append(_uncertain(
            "SUBJECT_UNRESOLVED", decisive=True,
            detail="the use names no target, so the candidate cannot be attributed",
        ))
    else:
        cap = _identity_cap(use, identity=identity)
        if cap is not None:
            uncertain.append(_uncertain(
                cap["fact"], decisive=True, detail=cap["detail"],
                point=use_id, source=_span(use),
            ))
    if composition:
        uncertain.append(_uncertain(
            "USE_KIND_UNKNOWN", decisive=True,
            detail=(
                "the use is a call argument, and the graph does not distinguish "
                "passing the pointer (`f(p)`) from passing its address (`f(&p)`)"
            ),
            point=use_id, source=_span(use),
        ))
    elif use["event_type"] == "RETURN":
        uncertain.append(_uncertain(
            "ESCAPING_USE", decisive=True,
            detail="the use returns the released pointer to the caller",
            point=use_id, source=_span(use),
        ))
    if reach_state == REACH_UNKNOWN:
        uncertain.append(_uncertain(
            "REACH_UNKNOWN", decisive=True,
            detail=(
                "the release has no position in the control-flow graph, so the "
                "graph cannot say the use runs after it"
            ),
            point=release_id,
            source=_span(release) if release else "",
        ))
    steps = [release_id, use_id]
    return Candidate(
        defect_key=USE_AFTER_FREE_KEY,
        query=USE_AFTER_FREE,
        subject={
            "kind": "use-after-release",
            "name": _identity_display(use),
            "identity": identity_key,
            "storage": use.get("subject_storage", ""),
            "type": use.get("subject_type", ""),
            "member": use.get("subject_member", ""),
            "method": _method_name(use, names),
            "owner_symbol_id": owner,
        },
        anchor=use_id,
        discriminator=(
            f"{identity_key or 'anonymous'}|{owner}|{_step(release)}|{_step(use)}"
        ),
        resolution_status=status,
        confidence=USE_AFTER_FREE_CONFIDENCE[status],
        facts=tuple(
            _point_fact(point_id, points[point_id], names)
            for point_id in steps if _citable(point_id, points)
        ),
        uncertain_facts=tuple(uncertain),
        paths=paths,
        source_evidence=_source_evidence(steps, points),
        missing_evidence=(_MISSING_USE_KIND, _MISSING_FREE_WRAPPER, _MISSING_ALIASING),
        metadata={
            "flow_class": flow_class,
            "use_from": "call-composition" if composition else "flow-edge",
            "release": {
                "point": release_id,
                "source": _span(release) if release else "",
                "subject": release.get("subject", ""),
            },
            "reach": reach_state,
            "path_recorded": bool(paths),
            "paths_truncated": truncated,
            "anchor_span": {
                "relative_path": use.get("relative_path", ""),
                "start_line": use.get("start_line", 0),
                "end_line": use.get("end_line", 0),
            },
            "methods": [item for item in [_method_name(use, names)] if item],
            "exit_point": "",
        },
    )



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

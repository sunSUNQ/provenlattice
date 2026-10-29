"""concurrency_context (S2): finite, provable thread synchronization facts.

A query-time reader over the events/sparse_cfg rows. It converts the
THREAD_SPAWN/THREAD_JOIN vocabulary events and the READ/WRITE access facts into
a reusable, honest bundle that the S4/S5 scenario rules will consume:

* ``thread_entry_points`` -- the thread functions the graph saw a spawn for;
* ``spawn_before_join`` -- same-method spawn→join ordering (program order), the
  only happens-before subset the graph can assert without a thread identity;
* ``may_parallel`` -- shared, non-local subjects touched by two or more methods,
  expressed as a MAY_PARALLEL *candidate*, never a resolved race;
* ``missing_evidence`` -- the facts the graph cannot assert, named honestly.

This capability deliberately does not promise a complete happens-before or a
memory model, and it never upgrades an unproven MAY_PARALLEL into a resolved
fact.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .analysis_query import query_analysis
from .models import (
    STORAGE_FIELD,
    STORAGE_FILE_STATIC,
    STORAGE_FUNCTION_STATIC,
    STORAGE_GLOBAL,
    STORAGE_UNKNOWN,
)

# The storage classes whose subject can name genuinely shared, cross-thread
# state. `local` and `parameter` are frame-scoped and cannot be half of a
# cross-method pair, so they are subtracted rather than enumerated.
SHARED_STORAGES = frozenset({
    STORAGE_FIELD, STORAGE_FILE_STATIC, STORAGE_FUNCTION_STATIC,
    STORAGE_GLOBAL, STORAGE_UNKNOWN,
})

_ACCESS_EVENT_TYPES = frozenset({"READ", "WRITE"})


def _annotations(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return event.get("annotations") or {}


def _owner(event: Mapping[str, Any]) -> str:
    return event.get("owner_qualified_name") or event.get("owner_symbol_id") or ""


def _position(event: Mapping[str, Any]) -> int:
    return int(event.get("start_byte") or 0)


def build_concurrency_context(events: Iterable[Mapping[str, Any]]) -> dict:
    """Build the concurrency_context bundle from sparse_cfg events.

    ``events`` is the ``env["events"]`` list of a ``sparse_cfg`` query: each item
    carries ``event_type``, an owner identity and, for vocabulary events, the
    ``annotations`` (``subject``, ``subject_storage``, ``thread_function``).
    The function is pure and deterministic: the same events yield the same
    bundle, keys in stable order.
    """
    events = list(events)
    spawns: list[Mapping[str, Any]] = []
    joins: list[Mapping[str, Any]] = []
    entry_points: set[str] = set()
    for event in events:
        event_type = event.get("event_type")
        if event_type == "THREAD_SPAWN":
            spawns.append(event)
            thread_function = _annotations(event).get("thread_function", "")
            if thread_function:
                entry_points.add(thread_function)
        elif event_type == "THREAD_JOIN":
            joins.append(event)

    joins_by_owner: dict[str, list[Mapping[str, Any]]] = {}
    for join in joins:
        joins_by_owner.setdefault(_owner(join), []).append(join)

    spawn_before_join: list[dict[str, Any]] = []
    for spawn in spawns:
        owner = _owner(spawn)
        for join in joins_by_owner.get(owner, []):
            # Program order within one method is the only ordering the graph
            # can assert without a thread identity: the spawn statement runs
            # before the join statement, so the spawned work is joined here.
            if _position(spawn) < _position(join):
                spawn_before_join.append({
                    "owner": owner,
                    "thread_function": _annotations(spawn).get("thread_function", ""),
                    "spawn": spawn.get("event_id"),
                    "join": join.get("event_id"),
                })

    owners_by_subject: dict[str, set[str]] = {}
    storage_of_subject: dict[str, str] = {}
    for event in events:
        if event.get("event_type") not in _ACCESS_EVENT_TYPES:
            continue
        annotations = _annotations(event)
        subject = annotations.get("subject")
        if not subject:
            continue
        storage = annotations.get("subject_storage") or STORAGE_UNKNOWN
        if storage not in SHARED_STORAGES:
            continue
        owners_by_subject.setdefault(subject, set()).add(_owner(event))
        storage_of_subject.setdefault(subject, storage)

    may_parallel = [
        {
            "subject": subject,
            "storage": storage_of_subject[subject],
            "owners": sorted(owners),
        }
        for subject, owners in sorted(owners_by_subject.items())
        if len(owners) >= 2
    ]

    missing_evidence: set[str] = set()
    spawn_owners = {_owner(spawn) for spawn in spawns}
    join_owners = {_owner(join) for join in joins}
    if spawn_owners - join_owners:
        missing_evidence.add("spawn_without_join")
    for spawn in spawns:
        if not _annotations(spawn).get("thread_function"):
            missing_evidence.add("spawn_without_thread_function")

    return {
        "thread_entry_points": sorted(entry_points),
        "spawn_points": len(spawns),
        "join_points": len(joins),
        "spawn_before_join": spawn_before_join,
        "may_parallel": may_parallel,
        "may_parallel_decided": bool(spawns),
        "missing_evidence": sorted(missing_evidence),
    }


def query_concurrency_context(
    repo, file_path: str | None = None, database=None,
) -> dict:
    """Read one file's sparse_cfg facts and build its concurrency_context.

    Python/Java and unbuilt/stale files fall through to the sparse_cfg query's
    own honest status (``unsupported`` / ``not_built`` / ``stale``) -- this
    capability is C/C++ only and never fabricates a context where its inputs are
    absent.
    """
    env = query_analysis(repo, "sparse_cfg", file_path=file_path, database=database)
    if env["status"] != "available":
        return {"status": env["status"], "reason": env.get("reason")}
    context = build_concurrency_context(env.get("events", []))
    context["status"] = "available"
    return context


__all__ = ["build_concurrency_context", "query_concurrency_context"]

"""S5 lock scenario candidates (Parent #28): lock_pairing / lock_discipline.

Consumes S3's lock facts -- LOCK/UNLOCK vocabulary events carrying
``lock_identity``, ``subject_exact``, ``acquire_kind`` and ``raii`` -- and emits
Candidate rules for the two lock scenarios. The facts are reused as-is: lock
identity, acquire kind and RAII are never re-derived here, and the events layer,
``defect.py``'s ``lock_order``, the default index and CLI/MCP are untouched.

Every candidate is an evidence-resolution state, never a verified finding. The
vocabulary layer records lock calls but no control flow, so pairing and ordering
are provably-lossy approximations:

* the lock scenarios stay ``ambiguous`` -- a decisive pairing/order cannot be
  proven without control flow, so ``missing_evidence`` always names
  ``control_flow``;
* an empty ``lock_identity`` is ``unresolved`` (cannot be attributed) and never
  merged with a different lock by display name;
* a try/timed acquire may fail and leave the lock unheld, so it is never
  promoted to a held lock in pairing or self-deadlock reasoning;
* a RAII acquisition is implicitly released at scope exit, so it never shows up
  as an unpaired/leaked acquisition;
* a ``wait`` acquire is a blocking wait (condition/semaphore), not a mutex hold,
  so it is excluded from acquire/release pairing and only participates in the
  ``blocking_inside_lock`` rule.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

_LOCK = "LOCK"
_UNLOCK = "UNLOCK"

_ACQUIRE_BLOCKING = "blocking"
_ACQUIRE_TRY = "try"
_ACQUIRE_TIMED = "timed"
_ACQUIRE_WAIT = "wait"
_MAY_FAIL_ACQUIRES = frozenset({_ACQUIRE_TRY, _ACQUIRE_TIMED})

_SCENARIO_PAIRING = "lock_pairing"
_SCENARIO_DISCIPLINE = "lock_discipline"

_RULE_UNPAIRED_ACQUIRE = "unpaired_acquire"
_RULE_UNPAIRED_RELEASE = "unpaired_release"
_RULE_SELF_DEADLOCK = "self_deadlock"
_RULE_ORDER_INVERSION = "lock_order_inversion"
_RULE_BLOCKING_IN_LOCK = "blocking_inside_lock"

_MISSING_CONTROL_FLOW = "control_flow"
_MISSING_IDENTITY = "lock_identity_inexact"
_MISSING_TRY_TIMED_OUTCOME = "try_timed_outcome"


def _owner(event: Mapping[str, Any]) -> str:
    return event.get("owner_qualified_name") or event.get("owner_symbol_id") or ""


def _identity(event: Mapping[str, Any]) -> str:
    return event.get("lock_identity") or ""


def _byte(event: Mapping[str, Any]) -> int:
    return int(event.get("start_byte") or 0)


def _line_span(event: Mapping[str, Any]) -> list[int]:
    return [int(event.get("start_line") or 0), int(event.get("end_line") or 0)]


def _acquire_kind(event: Mapping[str, Any]) -> str:
    return event.get("acquire_kind") or _ACQUIRE_BLOCKING


def _lock_fact(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "matched_name": event.get("matched_name"),
        "lock_identity": _identity(event),
        "acquire_kind": _acquire_kind(event),
        "raii": bool(event.get("raii")),
        "start_line": int(event.get("start_line") or 0),
        "end_line": int(event.get("end_line") or 0),
    }


def _base_candidate(
    scenario_id: str, rule: str, identity: str, exact: bool, unresolved: bool,
    owner: str, locks: list[Mapping[str, Any]], missing: list[str],
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "rule": rule,
        "subject": identity or "",
        "identity": identity or None,
        "exact": exact,
        "unresolved": unresolved,
        "owner": owner,
        "owners": [owner] if owner else [],
        "source_spans": [_line_span(lock) for lock in locks],
        "related_locks": [_lock_fact(lock) for lock in locks],
        "evidence_references": [lock.get("event_id") for lock in locks],
        "missing_evidence": list(dict.fromkeys(missing)),
        "candidate_state": "unresolved" if unresolved else "ambiguous",
    }


def _pairing_missing(identity: str, exact: bool) -> list[str]:
    missing = [_MISSING_CONTROL_FLOW]
    if not exact or not identity:
        missing.append(_MISSING_IDENTITY)
    return missing


def _build_pairing(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """lock_pairing: unpaired acquires and releases per (owner, lock identity)."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        if event.get("event_type") not in (_LOCK, _UNLOCK):
            continue
        if event.get("event_type") == _LOCK:
            # A wait is a blocking wait, not a mutex acquire; a RAII lock is
            # released implicitly at scope exit. Neither is a releasable hold.
            if _acquire_kind(event) == _ACQUIRE_WAIT or event.get("raii"):
                continue
        identity = _identity(event)
        key = (_owner(event), identity)
        group = groups.setdefault(key, {
            "owner": _owner(event), "identity": identity,
            "exact": True, "locks": [], "unlocks": [],
        })
        if event.get("event_type") == _LOCK:
            group["locks"].append(event)
        else:
            group["unlocks"].append(event)
        group["exact"] = group["exact"] and bool(event.get("subject_exact"))

    candidates: list[dict[str, Any]] = []
    for (owner, identity) in sorted(groups):
        group = groups[(owner, identity)]
        blocking = [l for l in group["locks"]
                    if _acquire_kind(l) == _ACQUIRE_BLOCKING]
        may_fail = [l for l in group["locks"]
                    if _acquire_kind(l) in _MAY_FAIL_ACQUIRES]
        n_blocking = len(blocking)
        n_may_fail = len(may_fail)
        n_unlock = len(group["unlocks"])

        # A deterministic acquire left without a release: a possibly-leaked lock.
        unpaired_acquire = n_blocking - n_unlock
        if unpaired_acquire > 0:
            unpaired = sorted(blocking, key=_byte)[-unpaired_acquire:]
            candidates.append(_base_candidate(
                _SCENARIO_PAIRING, _RULE_UNPAIRED_ACQUIRE, identity,
                group["exact"], not identity, group["owner"], unpaired,
                _pairing_missing(identity, group["exact"]),
            ))

        # A release beyond every possible acquire (deterministic + may-fail): a
        # release of a lock that was never provably held.
        surplus_release = n_unlock - n_blocking - n_may_fail
        if surplus_release > 0:
            unpaired = sorted(group["unlocks"], key=_byte)[:surplus_release]
            candidates.append(_base_candidate(
                _SCENARIO_PAIRING, _RULE_UNPAIRED_RELEASE, identity,
                group["exact"], not identity, group["owner"], unpaired,
                _pairing_missing(identity, group["exact"]),
            ))

    return sorted(candidates, key=lambda c: (c["owner"], c["rule"], c["subject"]))


def _owner_sequences(events: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    """One method's lock/unlock events, in source order."""
    by_owner: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("event_type") in (_LOCK, _UNLOCK):
            by_owner[_owner(event)].append(event)
    for owner in by_owner:
        by_owner[owner].sort(key=_byte)
    return dict(by_owner)


def _build_discipline(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """lock_discipline: self-deadlock, cross-method order inversion, blocking-in-lock."""
    by_owner = _owner_sequences(events)

    candidates: list[dict[str, Any]] = []
    seen_self_deadlock: set[tuple[str, str, int]] = set()
    seen_blocking_in_lock: set[tuple[str, str, int]] = set()
    owner_lock_order: dict[str, list[str]] = {}

    for owner in sorted(by_owner):
        held: set[str] = set()
        order: list[str] = []
        for event in by_owner[owner]:
            event_type = event.get("event_type")
            kind = _acquire_kind(event)
            identity = _identity(event)

            if event_type == _LOCK and event.get("raii"):
                # Held until an invisible scope exit; never in the held set.
                continue

            if event_type == _LOCK and kind == _ACQUIRE_BLOCKING and identity:
                if identity in held:
                    key = (owner, identity, _byte(event))
                    if key not in seen_self_deadlock:
                        seen_self_deadlock.add(key)
                        candidates.append(_base_candidate(
                            _SCENARIO_DISCIPLINE, _RULE_SELF_DEADLOCK,
                            identity, bool(event.get("subject_exact")), False,
                            owner, [event], [_MISSING_CONTROL_FLOW],
                        ))
                else:
                    held.add(identity)
                    if not order or order[-1] != identity:
                        order.append(identity)
                continue

            if event_type == _LOCK and kind == _ACQUIRE_WAIT:
                if held and identity:
                    key = (owner, identity, _byte(event))
                    if key not in seen_blocking_in_lock:
                        seen_blocking_in_lock.add(key)
                        candidates.append(_base_candidate(
                            _SCENARIO_DISCIPLINE, _RULE_BLOCKING_IN_LOCK,
                            identity, bool(event.get("subject_exact")), False,
                            owner, [event], [_MISSING_CONTROL_FLOW],
                        ))
                continue

            if event_type == _LOCK and kind in _MAY_FAIL_ACQUIRES:
                # May fail; never a held lock. Not treated as a hold.
                continue

            if event_type == _UNLOCK:
                if identity in held:
                    held.discard(identity)

        owner_lock_order[owner] = order

    # Cross-method lock-order inversion: X before Y in one method, Y before X
    # in another (blocking acquisitions only).
    orderings: dict[tuple[str, str], set[str]] = defaultdict(set)
    for owner, order in owner_lock_order.items():
        for i, x in enumerate(order):
            for y in order[i + 1:]:
                if x and y and x != y:
                    orderings[(x, y)].add(owner)

    reported: set[tuple[str, str]] = set()
    for (x, y) in sorted(orderings):
        if (y, x) not in orderings:
            continue
        pair = tuple(sorted((x, y)))
        if pair in reported:
            continue
        reported.add(pair)
        owners = sorted(orderings[(x, y)] | orderings[(y, x)])
        candidates.append({
            "scenario_id": _SCENARIO_DISCIPLINE,
            "rule": _RULE_ORDER_INVERSION,
            "subject": f"{pair[0]} <-> {pair[1]}",
            "identity": None,
            "exact": True,
            "unresolved": False,
            "owner": owners[0],
            "owners": owners,
            "order_pair": list(pair),
            "source_spans": [],
            "related_locks": list(pair),
            "evidence_references": [],
            "missing_evidence": [_MISSING_CONTROL_FLOW],
            "candidate_state": "ambiguous",
        })

    return sorted(candidates, key=lambda c: (c["rule"], c["subject"], c["owner"]))


def build_lock_scenarios(events: Iterable[Mapping[str, Any]]) -> dict:
    """Build lock_pairing and lock_discipline candidates from S3 events.

    ``events`` is the ``env["events"]`` list of an ``events`` query (S3's level-0
    vocabulary events). The function is pure and deterministic: the same events
    yield the same bundle, with keys and lists in stable order.

    Returns ``{"candidates": [...], "coverage": {...}}`` where every candidate
    carries the unified scenario fields (``scenario_id``, ``source_spans``,
    ``related_locks``, ``candidate_state``, ``evidence_references``,
    ``missing_evidence``) and the lock identity, exactness and owner.
    """
    events = list(events)
    candidates = _build_pairing(events) + _build_discipline(events)
    return {
        "candidates": candidates,
        "coverage": {
            "scenarios": {
                _SCENARIO_PAIRING: sum(
                    1 for c in candidates if c["scenario_id"] == _SCENARIO_PAIRING),
                _SCENARIO_DISCIPLINE: sum(
                    1 for c in candidates if c["scenario_id"] == _SCENARIO_DISCIPLINE),
            },
        },
    }


__all__ = ["build_lock_scenarios"]
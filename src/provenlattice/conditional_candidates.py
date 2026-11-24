"""G2b (issue-pilot#97): query-time reader for conditional-pointer candidates.

The producer (`sparsecfg`) stamps an additive ``subject_candidates_v1``
annotation on the access points of a pointer bound by a conditional address
expression::

    struct S *p = cond ? &s1 : &s2;
    p->datum = 1;              // candidates: global:s1#datum, global:s2#datum

This module is the read-only consumer.  It never decides a race or a defect,
never writes the graph and never upgrades the candidate set to must-alias or
definite points-to: every record is ``confidence="may"`` and one of three
states.

* ``candidate``    -- both conditional arms resolved to declared objects;
* ``unknown``      -- the binding exists but an arm, the binding's uniqueness,
                      its address escape or an enclosing control construct
                      prevents a candidate set;
* ``unresolved``   -- the annotation is malformed, or the pointer's own
                      declaration is not resolvable in the file.

The consumer is evidence / coverage only.  Verdict wiring is explicitly out of
scope (issue-pilot#97), so no result from this module may be read as a
must-alias fact.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from .analysis_query import query_analysis

SUBJECT_CANDIDATES_KEY = "subject_candidates_v1"

STATUS_CANDIDATE = "candidate"
STATUS_UNKNOWN = "unknown"
STATUS_UNRESOLVED = "unresolved"
_STATUSES = frozenset({STATUS_CANDIDATE, STATUS_UNKNOWN, STATUS_UNRESOLVED})

CONFIDENCE_MAY = "may"


def _annotations(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return event.get("annotations") or {}


def _normalise_candidates(value: Any) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for item in value or ():
        if not isinstance(item, Mapping):
            continue
        decl = str(item.get("decl") or "")
        if not decl:
            continue
        candidates.append({
            "decl": decl,
            "storage": str(item.get("storage") or ""),
            "type": str(item.get("type") or ""),
            "member": str(item.get("member") or ""),
            "arm": str(item.get("arm") or ""),
        })
    candidates.sort(
        key=lambda item: (
            item["decl"], item["member"], item["arm"],
            item["storage"], item["type"],
        )
    )
    return candidates


def _record(
    event: Mapping[str, Any], annotations: Mapping[str, Any], status: str,
    candidates: list[dict[str, str]], limitation: str,
) -> dict[str, Any]:
    return {
        "access_event_id": event.get("event_id") or "",
        "event_type": event.get("event_type") or "",
        "owner": (
            event.get("owner_qualified_name")
            or event.get("owner_symbol_id")
            or ""
        ),
        "subject": str(annotations.get("subject") or ""),
        "subject_decl": str(annotations.get("subject_decl") or ""),
        "subject_member": str(annotations.get("subject_member") or ""),
        "candidates": candidates,
        "confidence": CONFIDENCE_MAY,
        "status": status,
        "limitation": limitation,
    }


def build_conditional_candidates(
    events: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Read the additive candidate annotations from one file's sparse events.

    Pure and deterministic: the same events yield the same records, sorted by
    owner and event id.  Malformed or under-populated annotations fail closed
    to ``unresolved`` / ``unknown``; they never keep a stale candidate list.
    """
    records: list[dict[str, Any]] = []
    missing: set[str] = set()
    for event in events:
        annotations = _annotations(event)
        raw = annotations.get(SUBJECT_CANDIDATES_KEY)
        if not raw:
            continue
        fact: Any = raw
        if isinstance(raw, str):
            try:
                fact = json.loads(raw)
            except (TypeError, ValueError):
                fact = None
        if not isinstance(fact, Mapping) or fact.get("version") != 1:
            records.append(_record(
                event, annotations, STATUS_UNRESOLVED, [],
                "malformed_candidates",
            ))
            missing.add("candidates_malformed")
            continue
        status = str(fact.get("status") or STATUS_UNRESOLVED)
        if status not in _STATUSES:
            status = STATUS_UNRESOLVED
        candidates = _normalise_candidates(fact.get("candidates"))
        if status == STATUS_CANDIDATE and len(candidates) < 2:
            # A candidate state with fewer than two targets is not a set; the
            # producer must have failed to prove an arm.  Never promote it.
            status = STATUS_UNRESOLVED
            missing.add("candidates_underflow")
        if status != STATUS_CANDIDATE:
            candidates = []
        records.append(_record(
            event, annotations, status, candidates,
            str(fact.get("limitation") or ""),
        ))
    records.sort(key=lambda record: (
        record["owner"], record["access_event_id"]))
    return {
        "candidates": records,
        "missing_evidence": sorted(missing),
        "provenance": {
            "upstream_analyzer": "sparse_cfg:cpp",
            "record_count": len(records),
            "candidate_record_count": sum(
                1 for record in records if record["status"] == STATUS_CANDIDATE),
            "candidate_count": sum(
                len(record["candidates"]) for record in records),
        },
    }


def query_conditional_candidates(
    repo, file_path: str, *, database=None,
) -> dict[str, Any]:
    """Read one file's sparse_cfg facts and build its candidate records.

    C/C++ only, same-file scope.  Python/Java and unbuilt/stale/corrupt files
    fall through to the sparse_cfg query's own honest status; this reader never
    fabricates a candidate set where its inputs are absent.
    """
    env = query_analysis(
        repo, "sparse_cfg", file_path=file_path, database=database)
    if env["status"] != "available":
        return {
            "status": env["status"], "reason": env.get("reason"),
            "candidates": [], "missing_evidence": [],
            "provenance": {"upstream_analyzer": "sparse_cfg:cpp",
                           "record_count": 0,
                           "candidate_record_count": 0,
                           "candidate_count": 0},
        }
    result = build_conditional_candidates(env.get("events", []))
    result["status"] = "available"
    result["reason"] = None
    return result


__all__ = [
    "SUBJECT_CANDIDATES_KEY",
    "STATUS_CANDIDATE",
    "STATUS_UNKNOWN",
    "STATUS_UNRESOLVED",
    "CONFIDENCE_MAY",
    "build_conditional_candidates",
    "query_conditional_candidates",
]

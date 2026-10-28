"""Deterministic L3 capability planner (GRAPH_CAPABILITY_PLANNER_V1).

A pure planning step over :data:`provenlattice.analysis.CAPABILITY_CONTRACT`.
It never executes an analyzer, never mutates the store, never touches the L1
default index and never expands the capability registry. Input is an explicit
:class:`PlannerRequest` (capabilities, language, scope, optional scenario ids,
maturity gate and budgets) plus an injectable freshness provider keyed by
analyzer id; output is a deterministically ordered :class:`CapabilityPlan`.

Determinism contract: for the same request and capability-contract snapshot the
planner produces the same items in the same order with the same ``plan_id``.
The plan id is derived only from the request and the contract closure, not from
runtime freshness, so a request always names the same planned work while the
per-item ``decision``/``status`` still reflect cache/freshness state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable

from .analysis import ANALYZER_VERSIONS, CAPABILITY_CONTRACT, capability_record

DECISION_BUILD = "build"
DECISION_REUSE = "reuse"
DECISION_QUERY_ONLY = "query_only"
DECISION_SKIP = "skip"
DECISIONS = frozenset({
    DECISION_BUILD, DECISION_REUSE, DECISION_QUERY_ONLY, DECISION_SKIP,
})

STATUS_CURRENT = "current"
STATUS_PARTIAL = "partial"
STATUS_UNSUPPORTED = "unsupported"
STATUS_STALE = "stale"
STATUS_NOT_BUILT = "not_built"
STATUSES = frozenset({
    STATUS_CURRENT, STATUS_PARTIAL, STATUS_UNSUPPORTED, STATUS_STALE, STATUS_NOT_BUILT,
})

# Ordered maturity scale for the minimum-maturity gate. `registered` tracks
# contract rows that are named but not implemented; `partially_implemented`
# and `implemented` are the two deliverable levels the planner may emit.
_MATURITY_ORDER = {"registered": 0, "partially_implemented": 1, "implemented": 2}

# A freshness provider maps an analyzer id ("<feature>:<language>") to a verdict
# with ``fresh: bool`` and an optional ``reason: str``. The planner only reads
# those two keys; anything else is ignored.
FreshnessProvider = Callable[[str], dict]


@dataclass(frozen=True, slots=True)
class PlannerRequest:
    capabilities: tuple[str, ...]
    language: str
    scope: str = "default"
    scenario_ids: tuple[str, ...] = ()
    minimum_maturity: str | None = None
    available_runtimes: tuple[str, ...] = ()
    budgets: dict[str, int] | None = None


@dataclass(frozen=True, slots=True)
class PlanItem:
    capability_id: str
    language: str
    scope: str
    scenario_ids: tuple[str, ...]
    analyzer_ids: tuple[str, ...]
    maturity: str
    dependencies: tuple[str, ...]
    decision: str
    reason: str | None
    status: str
    cost_class: str

    def to_dict(self) -> dict:
        return {
            "capability_id": self.capability_id,
            "language": self.language,
            "scope": self.scope,
            "scenario_ids": list(self.scenario_ids),
            "analyzer_ids": list(self.analyzer_ids),
            "maturity": self.maturity,
            "dependencies": list(self.dependencies),
            "decision": self.decision,
            "reason": self.reason,
            "status": self.status,
            "cost_class": self.cost_class,
        }


@dataclass(frozen=True, slots=True)
class CapabilityPlan:
    plan_id: str
    items: tuple[PlanItem, ...]

    def to_dict(self) -> dict:
        return {"plan_id": self.plan_id, "items": [item.to_dict() for item in self.items]}


def _normalize_capability(capability_id: str) -> str:
    return str(capability_id).strip().lower()


def _collect(capability_id: str, closure: dict[str, tuple[str, ...]]) -> None:
    if capability_id in closure:
        return
    record = capability_record(capability_id)
    dependencies = tuple(_normalize_capability(d) for d in record["depends_on"]) if record else ()
    closure[capability_id] = dependencies
    for dependency in dependencies:
        _collect(dependency, closure)


def _capability_closure(capabilities: list[str]) -> list[str]:
    closure: dict[str, tuple[str, ...]] = {}
    for capability_id in capabilities:
        _collect(capability_id, closure)
    ordered: list[str] = []
    remaining = set(closure)
    while remaining:
        ready = sorted(
            capability_id
            for capability_id in remaining
            if all(dependency not in remaining for dependency in closure[capability_id])
        )
        if not ready:
            # A dependency cycle cannot survive the contract's own validation,
            # but a deterministic emission keeps the planner total anyway.
            ready = sorted(remaining)
        for capability_id in ready:
            ordered.append(capability_id)
            remaining.remove(capability_id)
    return ordered


def _analyzers_for(capability_id: str, language: str, record: dict) -> tuple[str, ...]:
    if record.get("query_time"):
        return ()
    analyzer_ids = tuple(record.get("analyzer_ids") or ())
    exact = tuple(aid for aid in analyzer_ids if aid.rsplit(":", 1)[-1] == language)
    if exact:
        return exact
    if language == "c":
        # The C/C++ inspection family registers under the "cpp" dialect
        # (events:cpp, sparse_cfg:cpp, sparse_dfg:cpp) and serves both c and
        # cpp sources; the "c" request maps to that dialect.
        cpp = tuple(aid for aid in analyzer_ids if aid.rsplit(":", 1)[-1] == "cpp")
        if cpp:
            return cpp
    return analyzer_ids


def _maturity_threshold(minimum_maturity: str | None) -> int | None:
    if minimum_maturity is None:
        return None
    normalized = str(minimum_maturity).strip().lower()
    if normalized not in _MATURITY_ORDER:
        raise ValueError(f"invalid minimum_maturity: {minimum_maturity!r}")
    return _MATURITY_ORDER[normalized]


def _freshness(freshness: FreshnessProvider, analyzer_id: str) -> dict:
    try:
        verdict = freshness(analyzer_id) or {}
    except Exception:
        return {"fresh": False, "reason": "freshness_lookup_failed"}
    return {
        "fresh": bool(verdict.get("fresh", False)),
        "reason": verdict.get("reason"),
    }


def _classify(
    capability_id: str,
    record: dict | None,
    language: str,
    minimum_maturity: int | None,
    available_runtimes: frozenset[str],
    freshness: FreshnessProvider,
    dependency_statuses: dict[str, str],
) -> tuple[str, str | None, str, str | None]:
    analyzer_ids = _analyzers_for(capability_id, language, record) if record else ()
    cost_class = record["cost_class"] if record else "unknown"

    if record is None:
        return DECISION_SKIP, "capability_unregistered", STATUS_UNSUPPORTED, cost_class
    if language not in record["languages"]:
        return DECISION_SKIP, "unsupported_language", STATUS_UNSUPPORTED, cost_class

    maturity = record["status"]
    if maturity not in {"implemented", "partially_implemented"}:
        return DECISION_SKIP, "registered_not_implemented", STATUS_NOT_BUILT, cost_class
    if minimum_maturity is not None and _MATURITY_ORDER.get(maturity, 0) < minimum_maturity:
        status = STATUS_PARTIAL if maturity == "partially_implemented" else STATUS_CURRENT
        return DECISION_SKIP, "below_minimum_maturity", status, cost_class

    # Fail closed on unavailable dependencies: an unsupported/not-built
    # dependency makes every dependent capability unplanable as well (build,
    # reuse and query_only all require the dependency's facts). Each
    # dependency is inspected in normalized, sorted order so the reported
    # blocking dependency is deterministic.
    for dependency in sorted(record.get("depends_on") or ()):
        normalized = _normalize_capability(dependency)
        dependency_status = dependency_statuses.get(normalized)
        if dependency_status == STATUS_UNSUPPORTED:
            return DECISION_SKIP, f"dependency_unsupported:{normalized}", STATUS_UNSUPPORTED, cost_class
        if dependency_status == STATUS_NOT_BUILT:
            return DECISION_SKIP, f"dependency_unavailable:{normalized}", STATUS_NOT_BUILT, cost_class

    optional_runtime = record.get("optional_runtime")
    if optional_runtime and optional_runtime not in available_runtimes:
        return DECISION_SKIP, f"optional_runtime_unavailable:{optional_runtime}", STATUS_UNSUPPORTED, cost_class

    if record.get("query_time"):
        status = STATUS_CURRENT if maturity == "implemented" else STATUS_PARTIAL
        return DECISION_QUERY_ONLY, None, status, cost_class

    if not analyzer_ids:
        return DECISION_SKIP, "no_analyzer_for_language", STATUS_NOT_BUILT, cost_class

    verdicts = [_freshness(freshness, aid) for aid in analyzer_ids]
    if all(verdict["fresh"] for verdict in verdicts):
        status = STATUS_CURRENT if maturity == "implemented" else STATUS_PARTIAL
        return DECISION_REUSE, None, status, cost_class

    recorded_reasons = sorted({
        verdict["reason"] for verdict in verdicts
        if verdict["reason"] not in (None, "not_built")
    })
    if recorded_reasons:
        return DECISION_BUILD, "+".join(recorded_reasons), STATUS_STALE, cost_class
    any_not_built = any(verdict["reason"] == "not_built" for verdict in verdicts)
    status = STATUS_CURRENT if maturity == "implemented" else STATUS_PARTIAL
    return DECISION_BUILD, ("not_built" if any_not_built else None), status, cost_class


def _plan_id(request: dict) -> str:
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "plan-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def plan_capabilities(
    request: PlannerRequest,
    freshness: FreshnessProvider | None = None,
) -> CapabilityPlan:
    """Build the deterministic capability plan for ``request``.

    ``freshness`` maps an analyzer id to ``{"fresh": bool, "reason": str|None}``;
    when omitted every analyzer is treated as never built (decision ``build``).
    """
    if isinstance(request, dict):
        request = PlannerRequest(**request)
    if not isinstance(request, PlannerRequest):
        raise TypeError("request must be a PlannerRequest")
    capabilities = [_normalize_capability(c) for c in request.capabilities]
    if not capabilities:
        raise ValueError("no capabilities requested")
    language = str(request.language).strip().lower()
    scope = str(request.scope)
    scenario_ids = tuple(str(s) for s in request.scenario_ids)
    minimum_maturity_token = (
        str(request.minimum_maturity).strip().lower()
        if request.minimum_maturity is not None else None
    )
    minimum_maturity = _maturity_threshold(minimum_maturity_token)
    available_runtimes = frozenset(str(r) for r in request.available_runtimes)
    freshness = freshness or (lambda analyzer_id: {"fresh": False, "reason": None})

    closure = _capability_closure(capabilities)
    budgets = dict(request.budgets) if request.budgets else {}

    snapshot = {}
    for capability_id in sorted(closure):
        record = capability_record(capability_id)
        if record is None:
            snapshot[capability_id] = None
            continue
        contract = {
            key: record.get(key)
            for key in (
                "status", "languages", "depends_on", "cost_class",
                "analyzer_ids", "query_time", "optional_runtime",
            )
        }
        # The analyzer version is part of the contract closure that a plan
        # names: two otherwise identical requests over the same capabilities
        # but with different registered analyzer versions must not share a
        # plan identity, or L4 evidence becomes untraceable.
        contract["analyzer_versions"] = {
            analyzer_id: ANALYZER_VERSIONS.get(analyzer_id)
            for analyzer_id in record.get("analyzer_ids") or ()
        }
        snapshot[capability_id] = contract
    plan_id = _plan_id({
        "capabilities": sorted(capabilities),
        "language": language,
        "scope": scope,
        "scenario_ids": sorted(scenario_ids),
        "minimum_maturity": minimum_maturity_token,
        "available_runtimes": sorted(available_runtimes),
        "budgets": sorted((request.budgets or {}).items()),
        "contract": snapshot,
    })

    items: list[PlanItem] = []
    resolved_statuses: dict[str, str] = {}
    for capability_id in closure:
        record = capability_record(capability_id)
        decision, reason, status, cost_class = _classify(
            capability_id, record, language, minimum_maturity,
            available_runtimes, freshness, resolved_statuses,
        )
        if decision == DECISION_BUILD and cost_class in budgets and budgets[cost_class] <= 0:
            decision, reason = DECISION_SKIP, f"budget_exhausted:{cost_class}"
        elif decision == DECISION_BUILD and cost_class in budgets:
            budgets[cost_class] -= 1
        resolved_statuses[capability_id] = status
        dependencies = tuple(record["depends_on"]) if record else ()
        analyzer_ids = _analyzers_for(capability_id, language, record) if record else ()
        if decision == DECISION_SKIP and reason in (
            "unsupported_language", "capability_unregistered"
        ):
            # A language we do not serve must not advertise executable
            # analyzers for another language on the skipped item.
            analyzer_ids = ()
        items.append(PlanItem(
            capability_id=capability_id,
            language=language,
            scope=scope,
            scenario_ids=scenario_ids,
            analyzer_ids=analyzer_ids,
            maturity=record["status"] if record else "unregistered",
            dependencies=dependencies,
            decision=decision,
            reason=reason,
            status=status,
            cost_class=cost_class,
        ))

    return CapabilityPlan(plan_id=plan_id, items=tuple(items))


__all__ = [
    "DECISION_BUILD", "DECISION_REUSE", "DECISION_QUERY_ONLY", "DECISION_SKIP",
    "STATUS_CURRENT", "STATUS_PARTIAL", "STATUS_UNSUPPORTED", "STATUS_STALE",
    "STATUS_NOT_BUILT", "CapabilityPlan", "PlanItem", "PlannerRequest",
    "plan_capabilities", "CAPABILITY_CONTRACT",
]
"""S6 concurrency Profile Registry and L5 integration adapter.

A single registry of the ``concurrency-v1`` Profile and the one execution
adapter that turns the L3 Planner's deterministic plan into per-scenario results:
it runs the delivered S4/S5 scenario rules, converts their unified Candidate
contract into the existing L4 Evidence model, and reports each scenario's
``current`` / ``partial`` / ``unsupported`` / ``stale`` / ``not_built`` state.

Nothing here changes the default index, `race_condition`, `lock_order`, CLI/MCP
defaults or the default query envelope: the profile is opt-in through an
explicit entry only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from .analysis_ast import normalize_scope, scoped_sources
from .analysis_query import query_analysis
from .concurrency_lock_scenarios import build_lock_scenarios
from .concurrency_race_scenarios import build_race_scenarios
from .evidence import Evidence
from .orchestrator import analyze_scope
from .planner import PlannerRequest, plan_capabilities
from .storage import SQLiteStorage

CONCURRENCY_PROFILE_ID = "concurrency-v1"

_RACE_SCENARIOS = frozenset({"non_atomic_incdec", "bool_flag_race", "shared_state_race"})
_LOCK_SCENARIOS = frozenset({"lock_pairing", "lock_discipline"})

# The single registry: each profile declares the fields frozen in requirements §5.
CONCURRENCY_V1 = {
    "profile_id": CONCURRENCY_PROFILE_ID,
    "profile_version": "1",
    "query_set_version": "1",
    "scenario_ids": ("non_atomic_incdec", "bool_flag_race", "shared_state_race",
                     "lock_pairing", "lock_discipline"),
    "requested_scope": "src",
    "language_policy": ("c", "cpp"),
    "minimum_maturity": "partially_implemented",
    "budgets": {},
    "required_capabilities": ("events", "sparse_cfg"),
    "optional_capabilities": ("sparse_dfg",),
    "evidence_policy": "candidate",
}

PROFILES: dict[str, dict[str, Any]] = {CONCURRENCY_PROFILE_ID: CONCURRENCY_V1}


def get_profile(profile_id: str) -> dict[str, Any] | None:
    return PROFILES.get(str(profile_id).strip())


def _collect_events(root: Path, scope: str, feature: str, database: Path) -> list[dict]:
    events: list[dict] = []
    for source in scoped_sources(root, normalize_scope(scope)):
        env = query_analysis(root, feature, file_path=source.relative_path,
                             database=database)
        if env.get("status") == "available":
            events.extend(env.get("events", []))
    return events


def _candidate_to_evidence(
    candidate: Mapping[str, Any], repository: str, generation: int, file_path: str | None,
) -> Evidence:
    scenario_id = candidate["scenario_id"]
    identity = candidate.get("identity") or candidate.get("subject") or "(unresolved)"
    subject = candidate.get("subject") or identity
    spans = candidate.get("source_spans") or []
    start_line = spans[0][0] if spans and spans[0][0] else None
    end_line = spans[-1][1] if spans and spans[-1][1] else None
    references = list(candidate.get("evidence_references", []))
    return Evidence.create(
        kind="DEFECT_CANDIDATE",
        source_id=identity,
        relation=scenario_id,
        target_id=identity,
        repository=repository,
        commit="",
        generation=generation,
        provenance=f"{CONCURRENCY_PROFILE_ID}:{scenario_id}",
        confidence=0.0,
        source_path=file_path,
        start_line=start_line,
        end_line=end_line,
        summary=f"{scenario_id} candidate on {subject}",
        fact_id=references[0] if references else f"{start_line}:{end_line}",
        metadata={
            "scenario_id": scenario_id,
            "candidate_state": candidate.get("candidate_state"),
            "unresolved": bool(candidate.get("unresolved")),
            "exact": candidate.get("exact"),
            "missing_evidence": list(candidate.get("missing_evidence", [])),
            "profile": CONCURRENCY_PROFILE_ID,
            "query_set_version": CONCURRENCY_V1["query_set_version"],
        },
    )


def run_concurrency_profile(
    repo, profile_id: str = CONCURRENCY_PROFILE_ID, *,
    database=None, scope: str | None = None,
) -> dict:
    """Run the concurrency-v1 Profile over a scope and return per-scenario results.

    Returns ``{"status", "profile", "plan", "scenarios", "evidence"}``. Each
    scenario entry carries its ``current``/``partial``/``not_built`` state and a
    reason; a skipped or unsupported scenario is reported explicitly, never as an
    empty success.
    """
    profile = get_profile(profile_id)
    if profile is None:
        return {"status": "unknown_profile", "profile_id": profile_id}

    root = Path(repo).resolve()
    database = Path(database).resolve() if database else root / ".provenlattice" / "codegraph.db"
    scope = scope or profile["requested_scope"]

    plan = plan_capabilities(PlannerRequest(
        capabilities=profile["required_capabilities"],
        language="cpp",
        scope=scope,
        scenario_ids=profile["scenario_ids"],
        minimum_maturity=profile["minimum_maturity"],
    ))

    with SQLiteStorage(database) as storage:
        meta = storage.repository()
        if meta is None:
            return {"status": "not_built", "reason": "base_graph_required"}
        repo_id = meta["repo_id"]
        generation = int(meta.get("current_generation") or 0)

    analyze_scope(root, scope, ("sparse_cfg", "events"), database=database)

    sparse_events = _collect_events(root, scope, "sparse_cfg", database)
    event_events = _collect_events(root, scope, "events", database)

    race = build_race_scenarios(sparse_events)
    lock = build_lock_scenarios(event_events)

    candidates_by_scenario: dict[str, list[dict]] = {
        scenario_id: [] for scenario_id in profile["scenario_ids"]
    }
    for candidate in (*race["candidates"], *lock["candidates"]):
        candidates_by_scenario.setdefault(candidate["scenario_id"], []).append(candidate)

    evidence: list[Evidence] = []
    scenarios = {}
    for scenario_id in profile["scenario_ids"]:
        candidates = candidates_by_scenario.get(scenario_id, [])
        if scenario_id in _RACE_SCENARIOS and not sparse_events:
            status, reason = "not_built", "no_sparse_cfg_access_facts"
        elif scenario_id in _LOCK_SCENARIOS and not event_events:
            status, reason = "not_built", "no_events_facts"
        elif candidates:
            status, reason = "current", None
        else:
            status, reason = "not_built", "no_candidates"
        scenarios[scenario_id] = {
            "status": status,
            "reason": reason,
            "candidate_count": len(candidates),
            "candidates": candidates,
        }
        for candidate in candidates:
            evidence.append(_candidate_to_evidence(candidate, repo_id, generation, None))

    return {
        "status": "complete",
        "profile": {
            "profile_id": profile["profile_id"],
            "profile_version": profile["profile_version"],
            "query_set_version": profile["query_set_version"],
            "scenario_ids": list(profile["scenario_ids"]),
        },
        "plan": plan.to_dict(),
        "scenarios": scenarios,
        "evidence": [item.to_dict() for item in evidence],
        "coverage": {
            "race": race["coverage"],
            "lock": lock["coverage"],
        },
    }


__all__ = [
    "CONCURRENCY_PROFILE_ID", "CONCURRENCY_V1", "PROFILES",
    "get_profile", "run_concurrency_profile",
]
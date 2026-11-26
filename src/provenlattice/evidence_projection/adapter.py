"""FactBundle v2.1 core adapter (self-contained, GATE-0).

Public entry points for the two authorised defect types:

* :func:`analyze_shared_access` -- Race Condition, defect_type ``race_condition``;
* :func:`analyze_double_free`   -- Double Free,  defect_type ``double_free``;
* :func:`validate_bundle_v2`    -- v1 envelope checks + v2.1 additions + the
  automated Candidate <-> Evidence binding proof.

This module is the *only* place the projection chain touches the engine: it
calls the real :func:`provenlattice.defect_query.query_defect_candidates`
through the fail-closed :mod:`.source` wrapper and then stamps the v2.1
envelope. It is read-only over the rest of the repository and never imports
the GT / Prompt / Skill / Scorer or any historical-run artefact.

Relationship to the external v2.1 reference (``direct_api_adapter_f1_1_v2_1.py``)
-------------------------------------------------------------------------------
The reference adapter delegates its terminal-status derivation, audit envelope
and v1 `build_bundle` to a frozen external v1 core (``direct_api_adapter_f1_1.py``)
that is NOT part of this repository and that GATE-0 must not fabricate,
re-implement verbatim or import from an old-machine path. This module is
therefore **self-contained**: it builds a semantically-compatible envelope
directly -- same ``api_version`` ``"v1.1"``, same terminal status set, same v1
access-row keys (``method``/``file``/``line``/``kind``/``non_atomic``/``decided``)
plus the same v2.1 additions -- but does not claim byte-level parity with the
frozen v1 base. This divergence is recorded in ``README.md`` (Dependency
closure), and the adapter's own version is stamped under ``adapter_version`` for
that reason.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from . import constants as C
from . import projection as P
from .source import query_defect

# --- envelope / version surface (self-contained; see module docstring) -----

API_VERSION = C.API_VERSION                 # "v1.1" (envelope, back-compat)
SCHEMA_VERSION = C.SCHEMA_VERSION           # "2.1"
CONTRACT_VERSION = C.CONTRACT_VERSION
PROJECTION_VERSION = C.PROJECTION_VERSION
ADAPTER_VERSION = C.ADAPTER_VERSION
CORE_ADAPTER_VERSION = C.CORE_ADAPTER_VERSION

# re-export the terminal statuses so callers need one import
ST_OK = C.ST_OK
ST_PARTIAL = C.ST_PARTIAL
ST_EMPTY = C.ST_EMPTY
ST_UNSUPPORTED_ONLY = C.ST_UNSUPPORTED_ONLY
ST_STALE = C.ST_STALE
ST_NOT_BUILT = C.ST_NOT_BUILT
ST_FAILED = C.ST_FAILED
ST_TIMEOUT = C.ST_TIMEOUT

V2_ADDED_KEYS = ("schema_version", "contract_version", "projection_version",
                 "location_coverage", "evidence_locations", "adapter_version",
                 "core_adapter_version")

V1_REQUIRED_KEYS = ("api_version", "status", "defect_type", "facts",
                    "supporting_locations", "request")

LOCATION_REQUIRED_KEYS = ("file", "line", "role", "semantic_role",
                          "anchor_class", "owner", "access_type",
                          "source_fact_id", "provenance", "candidate_key",
                          "line_span", "held_locks")
COVERAGE_REQUIRED_KEYS = ("candidates", "with_primary_anchor",
                          "with_access_locations", "with_support_locations",
                          "unlocated_candidates", "by_semantic_role")
ACCESS_TYPES = ("READ", "WRITE", "READ_MODIFY_WRITE", "UNKNOWN", "", "RELEASE")
SEMANTIC_ROLES = ("candidate_anchor", "racing_access", "held_lock",
                  "release_site", "unresolved_location")
ANCHOR_CLASSES = ("primary", "supporting", "unresolved")

# Generic fact projection (projector-registry expansion). These are only
# admitted for the new generic entries; race/double_free keep the narrower
# enums above.
GENERIC_SEMANTIC_ROLES = SEMANTIC_ROLES + (
    "resource_alloc", "dereference", "call", "control", "null_value", "fact",
)

# --- terminal status derivation --------------------------------------------

# source status (source.query_defect) -> envelope terminal status
_SOURCE_TO_ENVELOPE = {
    C.ST_OK: ST_OK,
    C.ST_EMPTY: ST_EMPTY,
    C.ST_STALE: ST_STALE,
    C.ST_NOT_BUILT: ST_NOT_BUILT,
    C.ST_FAILED: ST_FAILED,
}


def _subject_from_target_symbols(target_symbols: Any) -> str | None:
    """``target_symbols`` -> the single ``subject`` string the engine accepts.

    The engine's defect query takes at most one ``subject`` (a symbol name /
    identity). A tuple/list of symbols is narrowed to its first element so a
    one-symbol request matches exactly; an empty request is ``None`` ("all").
    """
    if not target_symbols:
        return None
    if isinstance(target_symbols, str):
        return target_symbols or None
    if isinstance(target_symbols, Sequence) and not isinstance(
            target_symbols, (bytes, bytearray)):
        try:
            return str(target_symbols[0]) if len(target_symbols) else None
        except (IndexError, TypeError):
            return None
    return str(target_symbols) or None


# --- bundle construction ----------------------------------------------------


def _projected_from_result(result: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not result:
        return []
    return [P.project_candidate(c) for c in (result.get("candidates") or [])]


def _facts_block(entry: str, projected: list[dict[str, Any]]) -> dict[str, Any]:
    """The candidate-bound ``facts`` block, one value entry per candidate.

    Race -> ``shared_accesses.value[]`` (access_rows); double free ->
    ``release_sites.value[]`` (release_sites). Mirrors the v1 flat fact-field
    names so a v1-keyed consumer still finds its keys, with the v2.1
    per-candidate binding added.

    The generic entries -> ``candidate_facts.value[]``. That block keeps the
    candidate-level binding plus every located ``facts[]`` row the engine
    produced; it is additive and never renames the two frozen blocks.
    """
    if _is_generic(entry):
        return _generic_facts_block(projected)
    fact_name = "shared_accesses" if _is_race(entry) else "release_sites"
    field = "access_rows" if _is_race(entry) else "release_sites"
    value: list[dict[str, Any]] = []
    for pc in projected:
        value.append({
            "identity": pc["identity"],
            "subject": pc["subject"],
            "candidate_key": pc["candidate_key"],
            "evidence_id": pc.get("evidence_id", ""),
            "defect_key": pc.get("defect_key", ""),
            "discriminator": pc.get("discriminator", ""),
            field: pc[field],
            "primary_anchor": pc["primary_anchor"],
        })
    return {fact_name: {"value": value}}


def _generic_facts_block(projected: list[dict[str, Any]]) -> dict[str, Any]:
    """Candidate-bound generic fact block for the five new projectors."""
    value: list[dict[str, Any]] = []
    for pc in projected:
        value.append({
            "candidate_key": pc["candidate_key"],
            "evidence_id": pc.get("evidence_id", ""),
            "defect_key": pc.get("defect_key", ""),
            "discriminator": pc.get("discriminator", ""),
            "subject": pc["subject"],
            "identity": pc["identity"],
            "resolution_status": pc.get("resolution_status", ""),
            "confidence": pc.get("confidence"),
            "facts": pc.get("access_rows") or [],
            "uncertain_facts": pc.get("uncertain_facts") or [],
            "missing_evidence": pc.get("missing_evidence") or [],
            "primary_anchor": pc.get("primary_anchor"),
        })
    value.sort(key=lambda item: item["candidate_key"])
    return {"candidate_facts": {"value": value}}


def _request_block(entry: str, case_workdir: str | Path, database: str | Path | None,
                   target_symbols: Any) -> dict[str, Any]:
    return {
        "entry": entry,
        "defect_type": C.ENTRY_DEFECT_TYPE[entry],
        "case_workdir": str(case_workdir),
        "database": str(database) if database else None,
        "target_symbols": list(target_symbols)
        if isinstance(target_symbols, (list, tuple))
        else (target_symbols or []),
    }


def _stamp_v2(
    bundle: dict[str, Any],
    projected: list[dict[str, Any]],
    *,
    generic: bool = False,
    supporting: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    bundle["schema_version"] = SCHEMA_VERSION
    bundle["contract_version"] = CONTRACT_VERSION
    bundle["projection_version"] = PROJECTION_VERSION
    bundle["adapter_version"] = ADAPTER_VERSION
    bundle["core_adapter_version"] = CORE_ADAPTER_VERSION
    bundle["location_coverage"] = (
        P.generic_location_coverage(projected, supporting)
        if generic else P.location_coverage(projected)
    )
    bundle["evidence_locations"] = P.evidence_locations(projected)
    return bundle


def _is_race(entry: str) -> bool:
    return entry == C.ENTRY_SHARED_ACCESS


def _is_double_free(entry: str) -> bool:
    return entry == C.ENTRY_DOUBLE_FREE


def _is_generic(entry: str) -> bool:
    return entry in C.GENERIC_ENTRIES


def _build_bundle(
    entry: str,
    *,
    case_workdir: str | Path,
    database: str | Path | None,
    target_symbols: Any = (),
    query_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Self-contained v1 + v2.1 envelope, driven by one real engine query.

    ``query_kwargs`` is only supplied by the generic entries; it forwards the
    engine's own query knobs (``max_candidates``, ``max_paths``, ``max_hops``,
    ``confidence_gate``, ...). The frozen race/double-free entries keep their
    original ignore-kwargs behaviour.
    """

    defect_type = C.ENTRY_DEFECT_TYPE[entry]
    forwarded = dict(query_kwargs or {})
    for reserved in ("repo", "defect_type", "database", "subject"):
        forwarded.pop(reserved, None)
    src = query_defect(
        case_workdir, defect_type=defect_type, database=database,
        subject=_subject_from_target_symbols(target_symbols), **forwarded,
    )
    status = _SOURCE_TO_ENVELOPE.get(src["status"], ST_FAILED)

    bundle: dict[str, Any] = {
        "api_version": API_VERSION,
        "status": status,
        "defect_type": defect_type,
        "facts": {},
        "supporting_locations": [],
        "request": _request_block(entry, case_workdir, database, target_symbols),
        "error": src.get("error"),
        "reason": src.get("reason"),
    }

    generic = _is_generic(entry)
    if status == ST_OK:
        # live facts only: a fail-closed terminal (stale/not_built/failed/empty)
        # carries zero projected candidates -- it may not assert any binding.
        if generic:
            projected = [
                P.project_candidate_generic(candidate)
                for candidate in (src["result"].get("candidates") or [])
            ]
        else:
            projected = _projected_from_result(src["result"])
    else:
        projected = []

    bundle["facts"] = _facts_block(entry, projected)
    if generic:
        supporting = P.build_supporting_locations_generic(projected)
    else:
        supporting = P.build_supporting_locations(
            projected, role_fact_name=("shared_accesses" if _is_race(entry)
                                       else "release_sites"))
    bundle["supporting_locations"] = supporting
    return _stamp_v2(bundle, projected, generic=generic, supporting=supporting)


# --- public entry points ----------------------------------------------------


def analyze_shared_access(
    case_workdir: str | Path,
    database: str | Path | None,
    target_symbols: Any = (),
    **kwargs: Any,
) -> dict:
    """Race Condition -> FactBundle v2.1.

    ``case_workdir`` is the checked-out Case workspace (the engine's ``repo``);
    ``database`` is the real graph DB path (``None`` -> engine default);
    ``target_symbols`` optionally narrows to one subject symbol. Extra keyword
    arguments are reserved and ignored (GATE-0 has no further source options).
    """
    return _build_bundle(
        C.ENTRY_SHARED_ACCESS, case_workdir=case_workdir, database=database,
        target_symbols=target_symbols)


def analyze_double_free(
    case_workdir: str | Path,
    database: str | Path | None,
    target_symbols: Any = (),
    **kwargs: Any,
) -> dict:
    """Double Free -> FactBundle v2.1 (candidate-bound release sites)."""
    return _build_bundle(
        C.ENTRY_DOUBLE_FREE, case_workdir=case_workdir, database=database,
        target_symbols=target_symbols)


def _analyze_generic(
    entry: str,
    case_workdir: str | Path,
    database: str | Path | None,
    target_symbols: Any = (),
    **kwargs: Any,
) -> dict:
    return _build_bundle(
        entry, case_workdir=case_workdir, database=database,
        target_symbols=target_symbols, query_kwargs=kwargs)


def analyze_lock_order(
    case_workdir: str | Path,
    database: str | Path | None,
    target_symbols: Any = (),
    **kwargs: Any,
) -> dict:
    """Lock Order -> FactBundle v2.1 (candidate-bound lock facts)."""
    return _analyze_generic(C.ENTRY_LOCK_ORDER, case_workdir, database,
                            target_symbols, **kwargs)


def analyze_resource_lifetime(
    case_workdir: str | Path,
    database: str | Path | None,
    target_symbols: Any = (),
    **kwargs: Any,
) -> dict:
    """Resource Lifetime -> FactBundle v2.1 (candidate-bound resource facts)."""
    return _analyze_generic(C.ENTRY_RESOURCE_LIFETIME, case_workdir, database,
                            target_symbols, **kwargs)


def analyze_use_after_free(
    case_workdir: str | Path,
    database: str | Path | None,
    target_symbols: Any = (),
    **kwargs: Any,
) -> dict:
    """Use After Free -> FactBundle v2.1 (candidate-bound lifetime facts)."""
    return _analyze_generic(C.ENTRY_USE_AFTER_FREE, case_workdir, database,
                            target_symbols, **kwargs)


def analyze_null_flow(
    case_workdir: str | Path,
    database: str | Path | None,
    target_symbols: Any = (),
    **kwargs: Any,
) -> dict:
    """Null Flow -> FactBundle v2.1 (candidate-bound null/deref facts)."""
    return _analyze_generic(C.ENTRY_NULL_FLOW, case_workdir, database,
                            target_symbols, **kwargs)


def analyze_mismatched_free(
    case_workdir: str | Path,
    database: str | Path | None,
    target_symbols: Any = (),
    **kwargs: Any,
) -> dict:
    """Mismatched Free -> FactBundle v2.1 (candidate-bound allocator facts)."""
    return _analyze_generic(C.ENTRY_MISMATCHED_FREE, case_workdir, database,
                            target_symbols, **kwargs)


# --- validation -------------------------------------------------------------


def validate_bundle_v2(entry: str, bundle: Mapping[str, Any]) -> list[str]:
    """v1 required keys + v2.1 additions + candidate binding proof.

    Self-contained: the frozen v1 validator is not available, so the v1 checks
    it is *known* to apply (envelope keys present, ``api_version`` ``"v1.1"``,
    ``status`` in the terminal set) are reproduced here; the v2.1 checks are
    byte-level faithful to the reference contract. Never relaxes a check.
    """
    probs: list[str] = []

    for k in V1_REQUIRED_KEYS:
        if k not in bundle:
            probs.append("missing v1 key: " + k)
    if bundle.get("api_version") != API_VERSION:
        probs.append("bad api_version: %r" % (bundle.get("api_version"),))
    if bundle.get("status") not in (
            ST_OK, ST_PARTIAL, ST_EMPTY, ST_UNSUPPORTED_ONLY,
            ST_STALE, ST_NOT_BUILT, ST_FAILED, ST_TIMEOUT):
        probs.append("bad status: %r" % (bundle.get("status"),))
    if bundle.get("defect_type") != C.ENTRY_DEFECT_TYPE.get(entry):
        probs.append("defect_type does not match entry %r" % (entry,))

    generic = bundle.get("defect_type") in C.GENERIC_DEFECT_TYPES
    allowed_roles = GENERIC_SEMANTIC_ROLES if generic else SEMANTIC_ROLES

    for k in V2_ADDED_KEYS:
        if k not in bundle:
            probs.append("missing v2 key: " + k)
    if bundle.get("schema_version") != SCHEMA_VERSION:
        probs.append("bad schema_version")
    if not str(bundle.get("adapter_version") or ""):
        probs.append("empty adapter_version")

    status = bundle.get("status")
    candidates = (bundle.get("location_coverage") or {}).get("candidates", 0)
    if status in C.TERMINAL_STATUSES and candidates:
        probs.append("terminal status %r but coverage reports %d candidates"
                     % (status, candidates))

    for loc in (bundle.get("supporting_locations") or []):
        if not isinstance(loc, dict):
            probs.append("non-dict supporting_location")
            continue
        for k in LOCATION_REQUIRED_KEYS:
            if k not in loc:
                probs.append("supporting_location missing " + k)
        if not str(loc.get("candidate_key") or ""):
            probs.append("supporting_location empty candidate_key")
        if loc.get("semantic_role") not in allowed_roles:
            probs.append("bad semantic_role: %r" % (loc.get("semantic_role"),))
        if loc.get("anchor_class") not in ANCHOR_CLASSES:
            probs.append("bad anchor_class: %r" % (loc.get("anchor_class"),))
        if generic:
            # Generic fact types are engine-owned (ARITH/THROW/THREAD_JOIN/...)
            # and must be preserved verbatim; only a fact location with no type
            # is a contract violation. The candidate anchor legitimately has
            # no access_type, exactly as in the frozen v2.1 shape.
            if loc.get("semantic_role") != "candidate_anchor" \
                    and not str(loc.get("access_type") or ""):
                probs.append("empty access_type on generic location")
        elif loc.get("access_type") not in ACCESS_TYPES:
            probs.append("bad access_type: %r" % (loc.get("access_type"),))
        if loc.get("anchor_class") != "unresolved" and not (
                loc.get("file") and loc.get("line")):
            probs.append("located anchor_class without file/line")
        if loc.get("semantic_role") == "release_site" and not str(
                loc.get("source_fact_id") or ""):
            probs.append("release_site without source_fact_id")

    cov = bundle.get("location_coverage") or {}
    for k in COVERAGE_REQUIRED_KEYS:
        if k not in cov:
            probs.append("location_coverage missing " + k)

    probs.extend(P.assert_candidate_binding(bundle))
    return probs


__all__ = [
    "API_VERSION", "SCHEMA_VERSION", "CONTRACT_VERSION", "PROJECTION_VERSION",
    "ADAPTER_VERSION", "CORE_ADAPTER_VERSION", "V2_ADDED_KEYS",
    "ST_OK", "ST_PARTIAL", "ST_EMPTY", "ST_UNSUPPORTED_ONLY",
    "ST_STALE", "ST_NOT_BUILT", "ST_FAILED", "ST_TIMEOUT",
    "analyze_shared_access", "analyze_double_free",
    "analyze_lock_order", "analyze_resource_lifetime", "analyze_use_after_free",
    "analyze_null_flow", "analyze_mismatched_free", "validate_bundle_v2",
]
"""Agent/Skill API (Issue #86 -> #87 dual IR path).

A thin, read-only, deterministic facade over the already-delivered evidence
projection chain. It composes the lower layers without re-implementing any
projection logic, and exposes two independent, separately-validated IR paths
selected by an explicit ``ir_version`` token:

    ir_version="1" (default, frozen #79/#86):
        Registry (``registry.REGISTRY``)
            -> adapter (``adapter.analyze_*``)
            -> Canonical Evidence IR V1 (``ir.factbundle_v2_1_to_ir``)

    ir_version="2" (#87, additive file-level concurrency facts):
        Registry (fail-closed gate only)
            -> ``ir_v2_source.assemble_ir_v2_input`` (engine readers)
            -> Canonical Evidence IR V2 (``ir_v2.assemble_ir_v2``)

Public surface:

* :func:`list_skill_capabilities` -- the truthful, machine-readable capability
  manifest, organised per ``defect_type`` (section B of Issue #86), extended
  with ``ir_versions_supported`` and the IR V2 capability catalog (#87).
* :func:`resolve_evidence`       -- version-dispatched composition that returns
  a validated Canonical Evidence IR V1 (default) or IR V2 dict.

Positioning: this stage ships the *thin interface + capability manifest + skill
requirements doc* (Issue #86) and the additive projection of the five concurrency
fact classes via the parallel IR V2 (Issue #87). It does NOT wire the skill into
the graph and does NOT modify the skill body, Engine, GATE-0 v2.1 or IR V1.

Contract constraints honoured
-----------------------------

* **pure facade** -- the V1 path calls
  ``registry.REGISTRY.get_projector(defect_type).analyze(...)`` and feeds the
  result to ``ir.factbundle_v2_1_to_ir``; it never re-projects, never injects
  defaults, and never rewrites the FactBundle or the IR. The V2 path reuses the
  engine's own ``query_*`` / ``build_*`` readers (never re-implements analysis)
  and feeds the normalised input record to the pure ``ir_v2`` transformer.
* **argument forwarding** -- ``target_symbols`` and ``**kwargs`` are forwarded
  verbatim to the V1 ``Projector.analyze`` (as in #83); ``run_context`` is
  supplied *only* as run metadata (C2 of #79) and never participates in
  projection. They do not participate in the V2 path.
* **version negotiation (explicit, fail-closed)** -- ``ir_version`` is an
  explicit token with no consumer-capability guessing and no silent fallback:
  ``"1"`` (default) keeps #86 byte-for-byte; ``"2"`` selects IR V2; any other
  value raises :class:`UnknownIRVersionError`. The two chains are independent
  and separately validated; V2 never mutates a V1 return object.
* **DEREF default OFF** -- ``enable_deref`` defaults to ``False``; the
  ``deref_resolves_to`` three-state (``must``/``may``/``unknown``) never
  cross-upgrades and a failed resolution never degrades to a guessed relation.
* **fail-closed** -- an unknown ``defect_type`` propagates
  ``registry.UnknownDefectTypeError``; an exception inside ``Projector.analyze``
  is re-raised verbatim (never downgraded to an empty bundle); an IR that fails
  its version validator raises :class:`EvidenceIRValidationError` and is never
  returned to the skill.
* **version boundary** -- the facade reads ``Projector.projector_version`` for
  the manifest but never writes/overwrites IR V1's ``run.projector_version``,
  which stays frozen at ``ir.PROJECTOR_VERSION`` (``"NOT_APPLICABLE"``).
* **truthful manifest** -- ``projected_facts`` (semantic fact types, the
  ``facts`` block) is kept distinct from ``projected_evidence``
  (evidence/anchor location structures ``supporting_locations[]`` /
  ``evidence_locations[]``); ``not_projected_facts`` (a producer exists but is
  not projected) is kept distinct from ``not_produced_facts`` (no first-order
  producer, incl. ``happens_before`` and ``guarded_by``). ``produced_not_projected``
  only describes projection status and never promises the fact appears for any
  specific case.

This module imports ``registry`` / ``ir`` / ``ir_v2`` (pure, no engine) and the
standard library at module level; ``ir_v2_source`` (the only engine-importing
module) is imported lazily inside the V2 path so the V1 path and the manifest
never load the engine. It never imports GT, Prompt, Skill or Scorer, and it never
mutates any input.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import ir
from . import ir_v2
from . import registry


class EvidenceIRValidationError(RuntimeError):
    """``resolve_evidence`` produced an IR that failed ``validate_evidence_ir_v1``.

    Fail-closed: the invalid IR is never returned to the skill.
    """


class UnknownIRVersionError(ValueError):
    """An unsupported ``ir_version`` was requested (fail-closed).

    ``ir_version`` is an explicit version negotiation token; there is no
    silent fallback and no consumer-capability guessing (#87 decision 2).
    """


MANIFEST_VERSION = "1"

# The IR versions the facade can produce. ``"1"`` (frozen IR V1, Issue #79/#86)
# and ``"2"`` (IR V2, Issue #87, additive concurrency facts).
IR_VERSIONS_SUPPORTED = ("1", "2")

# ---------------------------------------------------------------------------
# frozen FactBundle v2.1 / IR V1 contract surface (mirrors the schemas)
# ---------------------------------------------------------------------------

# The 13 fields of a ``supporting_locations[]`` entry (skill §4 alignment).
SUPPORTING_LOCATION_FIELDS = (
    "file", "line", "line_span", "role", "semantic_role", "anchor_class",
    "owner", "access_type", "source_fact_id", "event_id", "provenance",
    "candidate_key", "held_locks",
)

# The 9 fields of an ``evidence_locations[]`` entry (the per-candidate binding
# view emitted by ``projection.evidence_locations``).
EVIDENCE_LOCATION_FIELDS = (
    "candidate_key", "evidence_id", "defect_key", "discriminator",
    "subject", "identity", "primary_anchor", "access_rows", "release_sites",
)

ANCHOR_CLASSES = ("primary", "supporting", "unresolved")

SEMANTIC_ROLES = (
    "candidate_anchor", "racing_access", "held_lock",
    "release_site", "unresolved_location",
    "resource_alloc", "dereference", "call", "control", "null_value", "fact",
)

# ---------------------------------------------------------------------------
# truthful per-fact content (sources / limitations, from the §B fact table)
# ---------------------------------------------------------------------------

# race_condition already projects one semantic fact type: shared access events.
_RACE_PROJECTED_FACTS = {
    "shared_accesses": {
        "source": (
            "analysis_c_events.py access events + concurrency_race_scenarios.py "
            "(access_kind READ/WRITE/RMW, object identity)"
        ),
        "limitations": [
            "access_type / lock_identity may be empty (unresolved)",
        ],
    },
}

# The five concurrency facts whose producer exists in the graph but which are
# not (yet) projected into the skill-facing bundle. Status describes projection
# state only; whether a fact appears for a given case depends on case semantics.
_NOT_PROJECTED_FACTS = {
    "thread_context": {
        "status": "produced_not_projected",
        "source": (
            "analysis_concurrency_context.py: THREAD_SPAWN scoped identity (#49), "
            "THREAD_JOIN handle (#53), may_parallel thread entry mapping"
        ),
        "limitations": [
            "WaitForMultipleObjects -> unknown",
            "no handle join -> no subject",
            "no general thread-instance value flow",
        ],
    },
    "parallel_feasibility": {
        "status": "produced_not_projected",
        "source": (
            "analysis_concurrency_context.py -> may_parallel "
            "(MAY_PARALLEL candidate relation)"
        ),
        "limitations": [
            "always candidate, never resolved/decisive",
            "ambiguous is the norm",
        ],
    },
    "common_locks": {
        "status": "produced_not_projected",
        "source": (
            "concurrency_lock_scenarios.py: lock_identity/held_locks + "
            "PROTECTS/SAME_LOCK/DIFFERENT_LOCK/UNLOCK_OMITTED_ON_PATH"
        ),
        "limitations": [
            "lock_identity may be lock_identity_inexact/unresolved",
            "SAME/DIFFERENT only between access pairs on the same subject",
            "RAII remains ambiguous",
        ],
    },
    "spawn_join": {
        "status": "produced_not_projected",
        "source": (
            "analysis_concurrency_context.py -> spawn_join_pairs "
            "(THREAD_SPAWN/THREAD_JOIN same-identity pairing)"
        ),
        "limitations": [
            "requires equal handle_decl + same owner + spawn-before-join",
            "otherwise not paired",
            "WaitForMultipleObjects -> unknown",
        ],
    },
    "interprocedural_path": {
        "status": "produced_not_projected",
        "source": (
            "analysis_call_relation.py MAY_CALL (query-time restricted, #45) + "
            "deref_resolution.py DEREF_RESOLVES_TO (restricted, #48)"
        ),
        "limitations": [
            "MAY_CALL fail-closed (target only for unique_same_file_assignment, "
            "ambiguous -> [])",
            "DEREF_RESOLVES_TO restricted consumption",
        ],
    },
}

# happens_before has no first-order HB relation in the graph; ordering evidence
# is only indirectly represented by spawn_join_pairs + MAY_PARALLEL.
_NOT_PRODUCED_FACTS = {
    "happens_before": {
        "status": "not_produced",
        "note": (
            "no first-order HAPPENS_BEFORE relation; ordering evidence is only "
            "indirectly represented by spawn_join_pairs + MAY_PARALLEL "
            "decisive/ambiguous; IR V1 relations==[]; GUARDED_BY/HAPPENS_BEFORE "
            "are emitted only when evidence-backed (currently none); do not "
            "fabricate HB facts"
        ),
    },
    "guarded_by": {
        "status": "not_produced",
        "note": (
            "no first-order GUARDED_BY relation; the graph projects held_locks "
            "(a per-access must-hold lock set, always ambiguous) as a fact and "
            "the lock->access 'protect' relation, but neither is promoted to a "
            "field-guarding GUARDED_BY invariant; 'protect' is not an automatic "
            "GUARDED_BY equivalence (#87 decision 4)"
        ),
    },
}

# double_free projects one semantic fact type: the candidate's release sites.
# It is a memory-safety defect outside the concurrency fact vocabulary, so it
# carries no concurrency not_projected / not_produced facts.
_DOUBLE_FREE_PROJECTED_FACTS = {
    "release_sites": {
        "source": (
            "engine double-free candidate RELEASE facts "
            "(candidate.facts[RELEASE] + candidate.metadata.first_release/"
            "second_release)"
        ),
        "limitations": [
            "release_site entries carry access_type=RELEASE",
            "the primary anchor may coincide with one release site",
        ],
    },
}

# Generic candidate-bound facts for the five new projectors. Each block keeps
# the engine's candidate.facts[] rows verbatim (fact_type, file/line, event id,
# method) and the engine's own uncertain_facts / missing_evidence lists.
_GENERIC_PROJECTED_FACTS = {
    "lock_order": {
        "lock_facts": {
            "source": (
                "engine lock_order candidate LOCK/UNLOCK facts + lock identities "
                "(candidate.facts[].lock / lock_identity / role / side)"
            ),
            "limitations": [
                "MAY_PARALLEL remains an uncertain fact; the graph does not prove concurrency",
                "lock aliasing is not resolved; two spellings may be two locks",
                "lock-order inversion is a candidate, not a verified deadlock",
            ],
        },
    },
    "resource_lifetime": {
        "resource_facts": {
            "source": (
                "engine resource_lifetime candidate ALLOC/RELEASE/CALL/CHECK/"
                "BRANCH/RETURN facts"
            ),
            "limitations": [
                "ownership contracts are not first-class facts; missing_evidence carries them",
                "aliasing/reassignment and release-inside-callee remain unknown",
            ],
        },
    },
    "use_after_free": {
        "lifetime_facts": {
            "source": (
                "engine use_after_free candidate RELEASE + DEREFERENCE/RETURN facts"
            ),
            "limitations": [
                "one RELEASE fact may legitimately support several UAF candidates",
                "alias precision is limited; missing_evidence carries the caveat",
            ],
        },
    },
    "null_flow": {
        "null_flow_facts": {
            "source": (
                "engine null_flow candidate NULL/WRITE/DEREFERENCE facts"
            ),
            "limitations": [
                "the null value and the dereference are local-method facts",
                "guarded dereference remains a known false-positive surface",
            ],
        },
    },
    "mismatched_free": {
        "allocator_facts": {
            "source": (
                "engine mismatched_free candidate ALLOC + RELEASE facts and the "
                "declared allocator pair"
            ),
            "limitations": [
                "only declared allocator pairs are recognized; unknown release fails closed",
                "cross-function ownership contracts are not implied",
            ],
        },
    },
}

_GENERIC_NOT_PRODUCED_FACTS = {
    "lock_order": {
        "happens_before": _NOT_PRODUCED_FACTS["happens_before"],
        "guarded_by": _NOT_PRODUCED_FACTS["guarded_by"],
    },
    "resource_lifetime": {},
    "use_after_free": {},
    "null_flow": {},
    "mismatched_free": {},
}

_PROJECTED_EVIDENCE = {
    "supporting_locations": {
        "fields": list(SUPPORTING_LOCATION_FIELDS),
        "anchor_class": list(ANCHOR_CLASSES),
        "semantic_role": list(SEMANTIC_ROLES),
    },
    "evidence_locations": {
        "fields": list(EVIDENCE_LOCATION_FIELDS),
    },
}

ANCHOR_SEMANTICS = {
    "anchor_class": {
        "primary": "the candidate's single primary anchor location",
        "supporting": "a supporting evidence location (e.g. a racing access)",
        "unresolved": "location not resolved to a real file/line",
    },
    "semantic_role": {
        "candidate_anchor": "the anchor location of a candidate",
        "racing_access": "a located racing access (race_condition)",
        "held_lock": "a lock held at an access",
        "release_site": "a release/free site (double_free / lifetime defects)",
        "unresolved_location": "a location that could not be resolved",
        "resource_alloc": "an allocation site (resource_lifetime)",
        "dereference": "a dereference site (null_flow / use_after_free)",
        "call": "a call fact location",
        "control": "a check/branch/return fact location",
        "null_value": "a null-value fact location",
        "fact": "a generic engine fact location",
    },
}

STATUS_SEMANTICS = {
    "note": (
        "bundle_status and claim statuses describe evidence delivery and support "
        "level, never a safety verdict: an empty/terminal status is NOT proof of "
        "safety, and UNSUPPORTED is NOT a refutation"
    ),
    "bundle_status": {
        "ok": "evidence delivered with at least one live candidate",
        "empty": "engine ran and found zero candidates (NOT a safety verdict)",
        "unsupported_only": "candidates present but only unsupported/unknown",
        "partial": "partial evidence delivered",
        "stale": "stale/out-of-date evidence",
        "not_built": "evidence not built",
        "failed": "evidence query failed",
        "timeout": "evidence query timed out",
    },
    "claim_status": {
        "SUPPORTED": "claim has the required supporting evidence",
        "UNSUPPORTED": "claim lacks the required supporting evidence (NOT FALSE)",
        "UNKNOWN": "support could not be determined",
        "PARTIAL": "claim has partial support",
        "V1 note": "IR V1 emits no claims (claims == []); these statuses are "
                   "forward-compatible enum values only",
    },
}


# The IR V2 capability catalog (Issue #87). The IR V2 path (``ir_version="2"``)
# exposes six truthfully-decomposed fact types and eight relation types.
_IR_V2_CATALOG = {
    "fact_types": list(ir_v2.FACT_TYPES),
    "relation_types": list(ir_v2.RELATION_TYPES),
    "not_produced": list(ir_v2.NOT_PRODUCED),
    "deref": {
        "default": "disabled",
        "enable_param": "enable_deref",
        "confidence_states": ["must", "may", "unknown"],
        "note": (
            "DEREF_RESOLVES_TO is restricted (#48) and default OFF; enable via "
            "enable_deref=True. must/may/unknown are three-state and never "
            "cross-upgrade (may is never upgraded to must); a failed resolution "
            "is never degraded to a guessed relation."
        ),
    },
}


def _defect_manifest(defect_type: str, projector_version: str) -> dict[str, Any]:
    """The truthful per-defect manifest block.

    ``projector_version`` is read from the Registry (the projector *mechanism*
    version, e.g. ``"1"``); it is reported here only for capability discovery
    and is never written into IR V1's ``run.projector_version``.
    """
    if defect_type == "race_condition":
        projected_facts = dict(_RACE_PROJECTED_FACTS)
        not_projected_facts = dict(_NOT_PROJECTED_FACTS)
        not_produced_facts = dict(_NOT_PRODUCED_FACTS)
    elif defect_type == "double_free":
        projected_facts = dict(_DOUBLE_FREE_PROJECTED_FACTS)
        not_projected_facts = {}
        not_produced_facts = {}
    elif defect_type in _GENERIC_PROJECTED_FACTS:
        projected_facts = dict(_GENERIC_PROJECTED_FACTS[defect_type])
        not_projected_facts = {}
        not_produced_facts = dict(_GENERIC_NOT_PRODUCED_FACTS.get(defect_type, {}))
    else:  # unreachable via the production REGISTRY; defensive fail-closed
        raise registry.UnknownDefectTypeError(
            "unknown defect_type: %r" % (defect_type,))

    return {
        "projector_version": projector_version,
        "projected_facts": projected_facts,
        "projected_evidence": _PROJECTED_EVIDENCE,
        "not_projected_facts": not_projected_facts,
        "not_produced_facts": not_produced_facts,
    }


def list_skill_capabilities() -> dict[str, Any]:
    """Return the truthful, machine-readable capability manifest.

    Top level is organised per ``defect_type`` (derived from the production
    ``REGISTRY``, so the set of defect types can never drift from what is
    actually registered). The output is deterministic: equal inputs (the frozen
    registry) always produce byte-stable ``json.dumps(..., sort_keys=True)``.
    """
    capabilities = registry.REGISTRY.list_projector_capabilities()
    defect_types: dict[str, Any] = {}
    for cap in capabilities:
        defect_types[cap["defect_type"]] = _defect_manifest(
            cap["defect_type"], cap["projector_version"])

    return {
        "manifest_version": MANIFEST_VERSION,
        "ir_versions_supported": list(IR_VERSIONS_SUPPORTED),
        "ir_v2": _IR_V2_CATALOG,
        "defect_types": defect_types,
        "anchor_semantics": ANCHOR_SEMANTICS,
        "status_semantics": STATUS_SEMANTICS,
    }


def resolve_evidence(
    case_workdir,
    database,
    *,
    defect_type: str,
    target_symbols=(),
    run_context: Mapping[str, Any] | None = None,
    ir_version: str = "1",
    enable_deref: bool = False,
    file_path: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Compose Registry -> adapter -> IR and return a validated IR dict.

    Version negotiation (#87 decision 2):

    * ``ir_version="1"`` (default) -> frozen IR V1 (Issue #79/#86), unchanged;
    * ``ir_version="2"`` -> IR V2 (Issue #87) additive file-level concurrency
      facts; requires ``file_path`` and honours ``enable_deref`` (default OFF);
    * any other value -> :class:`UnknownIRVersionError` (fail-closed, no
      consumer-capability guessing, no silent fallback).

    The two version chains are independent and separately validated: IR V2 never
    mutates an IR V1 return object, and IR V1 behaviour is byte-for-byte
    unchanged. ``target_symbols`` and ``**kwargs`` are forwarded verbatim to the
    IR V1 ``Projector.analyze`` (they do not participate in the IR V2 path).

    Fail-closed behaviour (both paths): unknown ``defect_type`` ->
    ``registry.UnknownDefectTypeError``; an exception inside ``Projector.analyze``
    -> re-raised verbatim; an IR that fails its version validator ->
    :class:`EvidenceIRValidationError` (never returned to the skill).
    """
    if ir_version == "1":
        return _resolve_evidence_v1(
            case_workdir, database, defect_type=defect_type,
            target_symbols=target_symbols, run_context=run_context, **kwargs)
    if ir_version == "2":
        return _resolve_evidence_v2(
            case_workdir, database, defect_type=defect_type,
            file_path=file_path, enable_deref=enable_deref,
            run_context=run_context)
    raise UnknownIRVersionError(
        "unknown ir_version: %r (supported: %r)"
        % (ir_version, IR_VERSIONS_SUPPORTED))


def _resolve_evidence_v1(
    case_workdir,
    database,
    *,
    defect_type: str,
    target_symbols,
    run_context: Mapping[str, Any] | None,
    **kwargs: Any,
) -> dict[str, Any]:
    """IR V1 path (Issue #86 behaviour, unchanged)."""
    projector = registry.REGISTRY.get_projector(defect_type)
    bundle = projector.analyze(case_workdir, database, target_symbols, **kwargs)
    evidence = ir.factbundle_v2_1_to_ir(bundle, run_context=run_context)

    problems = ir.validate_evidence_ir_v1(evidence)
    if problems:
        raise EvidenceIRValidationError(
            "resolve_evidence produced an IR that failed validation: %r"
            % (problems,))

    return evidence


def _resolve_evidence_v2(
    case_workdir,
    database,
    *,
    defect_type: str,
    file_path: str | None,
    enable_deref: bool,
    run_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """IR V2 path (additive concurrency facts; independent of the V1 chain)."""
    # Fail-closed on an unknown defect_type (same gate as V1); the V2 path then
    # reads the file-level analyzers directly and never invokes the projector.
    registry.REGISTRY.get_projector(defect_type)
    from . import ir_v2_source

    input_record = ir_v2_source.assemble_ir_v2_input(
        case_workdir, database, file_path=file_path,
        enable_deref=enable_deref, defect_type=defect_type)
    evidence = ir_v2.assemble_ir_v2(input_record, run_context=run_context)

    problems = ir_v2.validate_evidence_ir_v2(evidence)
    if problems:
        raise EvidenceIRValidationError(
            "resolve_evidence (ir_version=2) produced an IR that failed "
            "validation: %r" % (problems,))

    return evidence


__all__ = [
    "MANIFEST_VERSION",
    "IR_VERSIONS_SUPPORTED",
    "EvidenceIRValidationError",
    "UnknownIRVersionError",
    "list_skill_capabilities",
    "resolve_evidence",
]

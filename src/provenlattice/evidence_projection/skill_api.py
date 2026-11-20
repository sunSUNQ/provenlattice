"""Agent/Skill API V1 (Issue #86).

A thin, read-only, deterministic facade over the already-delivered evidence
projection chain. It composes the three lower layers without re-implementing
any projection logic:

    Registry (``registry.REGISTRY``)
        -> adapter (``adapter.analyze_*``)
        -> Canonical Evidence IR V1 (``ir.factbundle_v2_1_to_ir``)

Public surface:

* :func:`list_skill_capabilities` -- the truthful, machine-readable capability
  manifest, organised per ``defect_type`` (section B of Issue #86).
* :func:`resolve_evidence`       -- Registry -> adapter -> IR composition that
  returns a validated Canonical Evidence IR V1 dict (section A of Issue #86).

Positioning: this stage (stage 3, approach B) ships only the *thin interface +
capability manifest + skill requirements doc*. It does NOT implement the
additive projection of the six concurrency fact classes (a separate Issue),
does NOT wire the skill into the graph, and does NOT modify the skill body.

Contract constraints honoured
-----------------------------

* **pure facade** -- ``resolve_evidence`` calls
  ``registry.REGISTRY.get_projector(defect_type).analyze(...)`` and feeds the
  result to ``ir.factbundle_v2_1_to_ir``; it never re-projects, never injects
  defaults, and never rewrites the FactBundle or the IR.
* **argument forwarding** -- ``target_symbols`` and ``**kwargs`` are forwarded
  verbatim to ``Projector.analyze`` (as in #83); ``run_context`` is supplied
  *only* to ``factbundle_v2_1_to_ir`` as run metadata (C2 of #79) and never
  participates in projection.
* **fail-closed** -- an unknown ``defect_type`` propagates
  ``registry.UnknownDefectTypeError``; an exception inside ``Projector.analyze``
  is re-raised verbatim (never downgraded to an empty bundle); an IR that fails
  ``ir.validate_evidence_ir_v1`` raises :class:`EvidenceIRValidationError` and
  is never returned to the skill.
* **version boundary** -- the facade reads ``Projector.projector_version`` for
  the manifest but never writes/overwrites IR V1's ``run.projector_version``,
  which stays frozen at ``ir.PROJECTOR_VERSION`` (``"NOT_APPLICABLE"``).
* **truthful manifest** -- ``projected_facts`` (semantic fact types, the
  ``facts`` block) is kept distinct from ``projected_evidence``
  (evidence/anchor location structures ``supporting_locations[]`` /
  ``evidence_locations[]``); ``not_projected_facts`` (a producer exists but is
  not projected) is kept distinct from ``not_produced_facts`` (no first-order
  producer). ``produced_not_projected`` only describes projection status and
  never promises the fact appears for any specific case.

This module imports only ``registry`` / ``constants`` / ``ir`` and the standard
library. It never imports the engine, GT, Prompt, Skill or Scorer, and it never
mutates any input.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import ir
from . import registry


class EvidenceIRValidationError(RuntimeError):
    """``resolve_evidence`` produced an IR that failed ``validate_evidence_ir_v1``.

    Fail-closed: the invalid IR is never returned to the skill.
    """


MANIFEST_VERSION = "1"

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
        "release_site": "a release/free site (double_free)",
        "unresolved_location": "a location that could not be resolved",
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
    **kwargs: Any,
) -> dict[str, Any]:
    """Compose Registry -> adapter -> IR and return a validated IR V1 dict.

    ``target_symbols`` and ``**kwargs`` are forwarded verbatim to
    ``Projector.analyze`` (no truncation / rewrite / default injection).
    ``run_context`` is supplied *only* to ``factbundle_v2_1_to_ir`` as the
    out-of-band run metadata (``code_revision`` / ``engine_version`` /
    ``db_snapshot_identity``); it never participates in projection.

    Fail-closed behaviour:

    * unknown ``defect_type`` -> ``registry.UnknownDefectTypeError``;
    * exception inside ``Projector.analyze`` -> re-raised verbatim;
    * IR fails ``ir.validate_evidence_ir_v1`` -> :class:`EvidenceIRValidationError`
      (the invalid IR is never returned).
    """
    projector = registry.REGISTRY.get_projector(defect_type)
    bundle = projector.analyze(case_workdir, database, target_symbols, **kwargs)
    evidence = ir.factbundle_v2_1_to_ir(bundle, run_context=run_context)

    problems = ir.validate_evidence_ir_v1(evidence)
    if problems:
        raise EvidenceIRValidationError(
            "resolve_evidence produced an IR that failed validation: %r"
            % (problems,))

    return evidence


__all__ = [
    "MANIFEST_VERSION",
    "EvidenceIRValidationError",
    "list_skill_capabilities",
    "resolve_evidence",
]

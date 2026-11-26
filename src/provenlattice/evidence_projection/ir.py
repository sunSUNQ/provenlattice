"""Canonical Evidence IR V1 (Issue #79).

A pure, deterministic projection of a FactBundle v2.1 (GATE-0, Issue #78)
envelope into the versioned, additive, machine-verifiable **Canonical Evidence
IR V1**. This module is the *evidence expression* stage that follows GATE-0's
*evidence transport* stage: it does not build a Projector Registry, a
multi-defect protocol, or an Agent/Skill API (those are later, separately
authorised phases).

IR shape (9 blocks + lossless fallback)
---------------------------------------

* ``run``        -- code revision, engine version, DB snapshot identity,
                    query/spec/projection/adapter versions (sources & defaults,
                    constraint C2);
* ``candidates`` -- stable non-empty candidate id (verbatim GATE-0
                    ``candidate_key``, C5), defect type, identity/subject,
                    identity evidence;
* ``claims``     -- falsifiable propositions and their SUPPORTED / UNSUPPORTED /
                    UNKNOWN / PARTIAL status (isolated from ``bundle_status``, C3);
* ``facts``      -- atomic engine facts preserving the real fact/event id;
* ``relations``  -- typed relations (READS / WRITES / FREES / FLOWS_TO /
                    GUARDED_BY / HAPPENS_BEFORE), only when evidence-backed (C4);
* ``locations``  -- source locations, symbol/owner, semantic role, anchor class;
* ``provenance`` -- Engine fact -> Candidate -> Projector -> Bundle trace chain;
* ``coverage``   -- per-candidate required/located/missing evidence (no
                    inference, C4);
* ``limitations``-- what the current result cannot prove, never expressed by
                    empty value or ``false``;
* ``source_envelope`` -- deep copy of the original FactBundle v2.1, lossless
                    fallback (C1).

Semantic constraints enforced here (C1-C5)
------------------------------------------

* **C1 lossless**: every original FactBundle field has an explicit mapping or is
  preserved verbatim in ``source_envelope``. ``source_envelope`` is a deep copy
  of the original bundle (no shared mutable reference); original values are
  never normalised / reordered / type-coerced; determinism applies only to the
  IR blocks, not to ``source_envelope``'s raw content.
* **C2 run metadata**: ``code_revision`` / ``engine_version`` /
  ``db_snapshot_identity`` come only from the explicit ``run_context`` argument;
  when absent they are explicitly ``NOT_RECORDED`` (never reverse-engineered
  from the current git HEAD / DB). GATE-0 ``source.py`` / ``adapter.py`` are
  unchanged.
* **C3 status isolation**: top-level ``bundle_status`` (evidence query/delivery
  status) is never mapped onto any claim status; this transformer is *not* a
  detector, so it emits ``claims == []`` and never derives SUPPORTED /
  UNSUPPORTED from the presence / absence of facts. ``claims == []`` is legal.
* **C4 no inference**: ``relations == []`` (no synthesised READS/WRITES/FLOWS_TO/
  GUARDED_BY/HAPPENS_BEFORE); ``held_locks`` is preserved only in
  ``source_envelope`` (never mapped to ``GUARDED_BY``); ``location_coverage``
  maps only to ``coverage.source_location`` (never a general evidence-coverage
  rate).
* **C5 candidate identity**: ``candidate.id`` is taken verbatim from GATE-0
  ``candidate_key`` (never recomputed); unique and non-empty within the
  Run/Bundle scope, with no promise of cross-run global uniqueness.

This module is pure and engine-free: it imports only the standard library and
never touches ``provenlattice.defect_query``, GT, Prompt, Skill or Scorer. It
never mutates the input ``bundle``.

Deterministic serialisation: every list is built in a stable, sorted order and
never depends on set/dict iteration order, locale, wall-clock time or a mutable
global. ``json.dumps(ir, sort_keys=True)`` over the result is byte-stable.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

# --- IR-level version surface (this module; GATE-0 constants are untouched) --

IR_SCHEMA_VERSION = "1"
PROJECTOR_VERSION = "NOT_APPLICABLE"
NOT_RECORDED = "NOT_RECORDED"

# Claim statuses a claim may carry. V1 never emits claims; the enum exists for
# forward-compatible consumers. UNSUPPORTED == "lacks the required supporting
# evidence"; a *refutation* is deliberately not modelled in V1 (C3).
CLAIM_STATUSES = ("SUPPORTED", "UNSUPPORTED", "UNKNOWN", "PARTIAL")

# Relation types, only emitted when evidence-backed (C4). V1 emits none.
RELATION_TYPES = (
    "READS", "WRITES", "FREES", "FLOWS_TO", "GUARDED_BY", "HAPPENS_BEFORE",
)

# Bundle terminal statuses (evidence query/delivery), independent of claim
# status (C3). Mirrors the GATE-0 v1 envelope status set.
BUNDLE_STATUSES = (
    "ok", "partial", "empty", "unsupported_only",
    "stale", "not_built", "failed", "timeout",
)

# The nine standard blocks + the lossless fallback.
IR_BLOCKS = (
    "run", "candidates", "claims", "facts", "relations",
    "locations", "provenance", "coverage", "limitations", "source_envelope",
)


# --- small pure helpers ------------------------------------------------------


def _pstr(bundle: Mapping[str, Any], key: str) -> str:
    """Read a string field, defaulting to ``""`` (never fabricates a value)."""
    value = bundle.get(key)
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _span(value: Any) -> list[int]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return [int(value[0] or 0), int(value[1] or 0)]
        except (TypeError, ValueError):
            return [0, 0]
    return [0, 0]


def _fact_id(row: Mapping[str, Any]) -> str:
    """The real engine fact/event id, or ``""`` when the source carries none.

    Preserves the empty-string degradation explicitly (never invents an id).
    """
    return str(row.get("source_fact_id") or row.get("event_id") or "")


def _fact(candidate_id: str, row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fact_id": _fact_id(row),
        "type": str(row.get("access_type") or ""),
        "candidate_id": candidate_id,
        "file": str(row.get("file") or ""),
        "line": _as_int(row.get("line")),
        "line_span": _span(row.get("line_span")),
        "provenance": str(row.get("provenance") or ""),
    }


def _fact_key(f: Mapping[str, Any]) -> tuple:
    return (f.get("candidate_id"), f.get("fact_id"), f.get("type"),
            f.get("file"), f.get("line"))


# ---------------------------------------------------------------------------
# transformer
# ---------------------------------------------------------------------------


def factbundle_v2_1_to_ir(
    bundle: Mapping[str, Any],
    *,
    run_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project a FactBundle v2.1 envelope into the Canonical Evidence IR V1.

    Pure and deterministic: never mutates ``bundle``, never reads the engine /
    git HEAD / DB, and returns an equal result for equal inputs.

    ``run_context`` supplies the out-of-band run metadata
    (``code_revision`` / ``engine_version`` / ``db_snapshot_identity``). Any of
    them absent (or empty) is recorded as ``NOT_RECORDED`` (C2).
    """
    if not isinstance(bundle, Mapping):
        raise TypeError("bundle must be a mapping, got %r" % (type(bundle).__name__,))

    # Read-only local view; the deep-copied source_envelope below is the
    # lossless fallback and shares no mutable reference with any IR block.
    bundle = dict(bundle)
    ctx = run_context if isinstance(run_context, Mapping) else {}

    def _rc(name: str) -> str:
        value = ctx.get(name)
        if value is None or str(value) == "":
            return NOT_RECORDED
        return value if isinstance(value, str) else str(value)

    evidence_locations = bundle.get("evidence_locations") or []

    # --- run block (C2) ------------------------------------------------------
    run: dict[str, Any] = {
        "code_revision": _rc("code_revision"),
        "engine_version": _rc("engine_version"),
        "db_snapshot_identity": _rc("db_snapshot_identity"),
        "source_schema_version": _pstr(bundle, "schema_version"),
        "contract_version": _pstr(bundle, "contract_version"),
        "projection_version": _pstr(bundle, "projection_version"),
        "adapter_version": _pstr(bundle, "adapter_version"),
        "core_adapter_version": _pstr(bundle, "core_adapter_version"),
        "projector_version": PROJECTOR_VERSION,
        "query_params": copy.deepcopy(bundle.get("request")),
        "error": copy.deepcopy(bundle.get("error")),
        "reason": copy.deepcopy(bundle.get("reason")),
    }

    # --- candidates (C5) -----------------------------------------------------
    candidates: list[dict[str, Any]] = []
    for pc in evidence_locations:
        if not isinstance(pc, Mapping):
            continue
        candidates.append({
            "id": str(pc.get("candidate_key") or ""),
            "defect_type": _pstr(bundle, "defect_type"),
            "evidence_id": str(pc.get("evidence_id") or ""),
            "defect_key": str(pc.get("defect_key") or ""),
            "discriminator": str(pc.get("discriminator") or ""),
            "identity": str(pc.get("identity") or ""),
            "subject": str(pc.get("subject") or ""),
            "primary_anchor": copy.deepcopy(pc.get("primary_anchor")),
        })
    candidates.sort(key=lambda c: c["id"])

    # --- facts (atomic engine facts, candidate-bound) ------------------------
    facts: list[dict[str, Any]] = []
    for pc in evidence_locations:
        if not isinstance(pc, Mapping):
            continue
        ckey = str(pc.get("candidate_key") or "")
        for row in (pc.get("access_rows") or []):
            if isinstance(row, Mapping):
                facts.append(_fact(ckey, row))
        for site in (pc.get("release_sites") or []):
            if isinstance(site, Mapping):
                facts.append(_fact(ckey, site))
    facts.sort(key=_fact_key)

    # --- locations (normalised; held_locks never here -- C4) -----------------
    locations: list[dict[str, Any]] = []
    for loc in (bundle.get("supporting_locations") or []):
        if not isinstance(loc, Mapping):
            continue
        locations.append({
            "candidate_id": str(loc.get("candidate_key") or ""),
            "file": str(loc.get("file") or ""),
            "line": _as_int(loc.get("line")),
            "line_span": _span(loc.get("line_span")),
            "owner": str(loc.get("owner") or ""),
            "role": str(loc.get("role") or ""),
            "semantic_role": str(loc.get("semantic_role") or ""),
            "anchor_class": str(loc.get("anchor_class") or ""),
            "source_fact_id": str(loc.get("source_fact_id") or ""),
            "event_id": str(loc.get("event_id") or ""),
            "provenance": str(loc.get("provenance") or ""),
        })
    locations.sort(key=lambda l: (l["candidate_id"], l["file"], l["line"],
                                  l["semantic_role"], l["event_id"]))

    # --- provenance (Engine fact -> Candidate -> Projector -> Bundle) --------
    proj_ver = _pstr(bundle, "projection_version")
    adapter_ver = _pstr(bundle, "adapter_version")
    contract_ver = _pstr(bundle, "contract_version")
    provenance: list[dict[str, Any]] = [
        {
            "fact_id": f["fact_id"],
            "candidate_id": f["candidate_id"],
            "origin": f["provenance"],
            "projection_version": proj_ver,
            "adapter_version": adapter_ver,
            "contract_version": contract_ver,
        }
        for f in facts
    ]
    provenance.sort(key=lambda p: (p["candidate_id"], p["fact_id"], p["origin"]))

    # --- coverage (only the source-location dimension -- C4) -----------------
    coverage: dict[str, Any] = {
        "source_location": copy.deepcopy(bundle.get("location_coverage")),
    }

    # --- claims / relations: V1 emits neither verdict nor inference ----------
    claims: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []

    # --- limitations (explicit, never empty/false to mean "unknown") ---------
    limitations = _limitations(bundle, facts)

    return {
        "ir_schema_version": IR_SCHEMA_VERSION,
        "bundle_status": _pstr(bundle, "status"),
        "run": run,
        "candidates": candidates,
        "claims": claims,
        "facts": facts,
        "relations": relations,
        "locations": locations,
        "provenance": provenance,
        "coverage": coverage,
        "limitations": limitations,
        "source_envelope": copy.deepcopy(bundle),
    }


def _limitations(
    bundle: Mapping[str, Any],
    facts: list[dict[str, Any]],
) -> list[str]:
    """Explicit degradation statements: what this result cannot prove.

    Never uses an empty value or ``false`` to *imply* unknown -- every
    limitation is a non-empty, self-contained statement.
    """
    out: list[str] = []
    status = _pstr(bundle, "status")
    if status and status != "ok":
        out.append(
            "bundle status=%s: evidence query did not deliver a complete "
            "ok result" % status)

    coverage = bundle.get("location_coverage") or {}
    for ck in (coverage.get("unlocated_candidates") or []):
        out.append("candidate %s: no source location located" % ck)

    for f in facts:
        if not f["fact_id"]:
            out.append(
                "fact at %s:%s for candidate %s lacks an engine fact id"
                % (f["file"], f["line"], f["candidate_id"]))

    # preserve first-seen order, dedupe (deterministic)
    seen: set[str] = set()
    result: list[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# validator
# ---------------------------------------------------------------------------


def validate_evidence_ir_v1(ir: Any) -> list[str]:
    """Validate a Canonical Evidence IR V1 structure.

    Returns a list of problem strings (empty == valid). Structural only: it
    checks the 9 blocks + ``source_envelope``, per-block required fields,
    version separation (M6), status/claim isolation (C3, M12), candidate id
    uniqueness (C5, M15), cross-candidate binding (M4) and that degradation is
    expressed explicitly, never faked as success (M3, M10).
    """
    probs: list[str] = []
    if not isinstance(ir, Mapping):
        return ["ir is not a mapping"]

    if ir.get("ir_schema_version") != IR_SCHEMA_VERSION:
        probs.append("bad ir_schema_version: %r (expected %r)"
                     % (ir.get("ir_schema_version"), IR_SCHEMA_VERSION))
    for block in IR_BLOCKS:
        if block not in ir:
            probs.append("missing IR block: " + block)

    if "bundle_status" not in ir:
        probs.append("missing bundle_status")
    elif ir.get("bundle_status") not in BUNDLE_STATUSES:
        probs.append("bad bundle_status: %r" % (ir.get("bundle_status"),))

    probs.extend(_validate_run(ir.get("run")))
    probs.extend(_validate_candidates(ir.get("candidates")))
    probs.extend(_validate_claims(ir.get("claims")))
    probs.extend(_validate_facts(ir.get("facts")))
    probs.extend(_validate_relations(ir.get("relations")))
    probs.extend(_validate_locations(ir.get("locations")))
    probs.extend(_validate_provenance(ir.get("provenance")))
    probs.extend(_validate_coverage(ir.get("coverage")))
    probs.extend(_validate_limitations(ir.get("limitations")))
    probs.extend(_validate_source_envelope(ir.get("source_envelope")))

    probs.extend(_validate_binding(ir))
    return probs


def _validate_run(run: Any) -> list[str]:
    probs: list[str] = []
    if not isinstance(run, Mapping):
        return ["run is not a mapping"]
    required = (
        "code_revision", "engine_version", "db_snapshot_identity",
        "source_schema_version", "contract_version", "projection_version",
        "adapter_version", "core_adapter_version", "projector_version",
        "query_params", "error", "reason",
    )
    for k in required:
        if k not in run:
            probs.append("run missing " + k)

    # C2: the three run-metadata fields must be explicit; empty/None masks a
    # missing value and is rejected (must be NOT_RECORDED).
    for k in ("code_revision", "engine_version", "db_snapshot_identity"):
        if run.get(k) in (None, ""):
            probs.append("run.%s must be %r when absent (got %r)"
                         % (k, NOT_RECORDED, run.get(k)))

    if run.get("projector_version") != PROJECTOR_VERSION:
        probs.append("run.projector_version must be %r (got %r)"
                     % (PROJECTOR_VERSION, run.get("projector_version")))

    # version separation (M6): projector_version and projection_version are
    # distinct semantics and must not collide.
    if run.get("projector_version") == run.get("projection_version"):
        probs.append("run.projector_version must not equal run.projection_version")

    if not str(run.get("source_schema_version") or ""):
        probs.append("run.source_schema_version empty")
    if not str(run.get("contract_version") or ""):
        probs.append("run.contract_version empty")
    if not str(run.get("projection_version") or ""):
        probs.append("run.projection_version empty")
    if not str(run.get("adapter_version") or ""):
        probs.append("run.adapter_version empty")
    # core_adapter_version may legitimately be "" (contract); no emptiness check.

    if run.get("query_params") is None:
        probs.append("run.query_params must be an object, got null")
    return probs


def _validate_candidates(candidates: Any) -> list[str]:
    probs: list[str] = []
    if not isinstance(candidates, list):
        return ["candidates is not a list"]
    ids: list[str] = []
    for i, c in enumerate(candidates):
        if not isinstance(c, Mapping):
            probs.append("candidates[%d] is not a mapping" % i)
            continue
        if "id" not in c:
            probs.append("candidates[%d] missing id" % i)
        else:
            cid = str(c.get("id") or "")
            if not cid:
                probs.append("candidates[%d].id is empty" % i)
            else:
                ids.append(cid)
        for k in ("defect_type", "identity", "subject"):
            if k not in c:
                probs.append("candidates[%d] missing %s" % (i, k))
        if "primary_anchor" not in c:
            probs.append("candidates[%d] missing primary_anchor" % i)
    if len(ids) != len(set(ids)):
        dup = sorted({x for x in ids if ids.count(x) > 1})
        probs.append("duplicate candidate.id: %r" % (dup,))
    return probs


def _validate_claims(claims: Any) -> list[str]:
    probs: list[str] = []
    if not isinstance(claims, list):
        return ["claims is not a list"]
    for i, cl in enumerate(claims):
        if not isinstance(cl, Mapping):
            probs.append("claims[%d] is not a mapping" % i)
            continue
        if "claim" not in cl:
            probs.append("claims[%d] missing claim" % i)
        if cl.get("status") not in CLAIM_STATUSES:
            probs.append("claims[%d] bad status: %r" % (i, cl.get("status")))
    # claims == [] is legal (C3): the V1 transformer never derives verdicts.
    return probs


def _validate_facts(facts: Any) -> list[str]:
    probs: list[str] = []
    if not isinstance(facts, list):
        return ["facts is not a list"]
    for i, f in enumerate(facts):
        if not isinstance(f, Mapping):
            probs.append("facts[%d] is not a mapping" % i)
            continue
        for k in ("fact_id", "type", "candidate_id"):
            if k not in f:
                probs.append("facts[%d] missing %s" % (i, k))
        if not str(f.get("candidate_id") or ""):
            probs.append("facts[%d] empty candidate_id" % i)
        if not str(f.get("fact_id") or ""):
            probs.append("facts[%d] empty fact_id (degradation must be explicit)"
                         % i)
    return probs


def _validate_relations(relations: Any) -> list[str]:
    probs: list[str] = []
    if not isinstance(relations, list):
        return ["relations is not a list"]
    for i, r in enumerate(relations):
        if not isinstance(r, Mapping):
            probs.append("relations[%d] is not a mapping" % i)
            continue
        if "type" not in r:
            probs.append("relations[%d] missing type" % i)
        elif r.get("type") not in RELATION_TYPES:
            probs.append("relations[%d] bad type: %r" % (i, r.get("type")))
    return probs


def _validate_locations(locations: Any) -> list[str]:
    probs: list[str] = []
    if not isinstance(locations, list):
        return ["locations is not a list"]
    for i, loc in enumerate(locations):
        if not isinstance(loc, Mapping):
            probs.append("locations[%d] is not a mapping" % i)
            continue
        for k in ("candidate_id", "file", "line", "semantic_role",
                  "anchor_class"):
            if k not in loc:
                probs.append("locations[%d] missing %s" % (i, k))
    return probs


def _validate_provenance(provenance: Any) -> list[str]:
    probs: list[str] = []
    if not isinstance(provenance, list):
        return ["provenance is not a list"]
    for i, p in enumerate(provenance):
        if not isinstance(p, Mapping):
            probs.append("provenance[%d] is not a mapping" % i)
            continue
        for k in ("fact_id", "candidate_id", "origin"):
            if k not in p:
                probs.append("provenance[%d] missing %s" % (i, k))
    return probs


def _validate_coverage(coverage: Any) -> list[str]:
    if not isinstance(coverage, Mapping):
        return ["coverage is not a mapping"]
    probs: list[str] = []
    if "source_location" not in coverage:
        probs.append("coverage missing source_location")
    return probs


def _validate_limitations(limitations: Any) -> list[str]:
    probs: list[str] = []
    if not isinstance(limitations, list):
        return ["limitations is not a list"]
    for i, item in enumerate(limitations):
        if not isinstance(item, str) or not item:
            probs.append("limitations[%d] must be a non-empty string" % i)
    return probs


def _validate_source_envelope(env: Any) -> list[str]:
    if not isinstance(env, Mapping):
        return ["source_envelope is not a mapping"]
    return []


# Defect types whose candidates may legitimately cite one shared RELEASE fact.
# double_free is deliberately absent: its candidates must own distinct
# releases, so the strict one-owner rule stays there.
_SHARED_RELEASE_DEFECT_TYPES = frozenset({
    "use_after_free", "resource_lifetime", "null_flow", "mismatched_free",
})


def _validate_binding(ir: Mapping[str, Any]) -> list[str]:
    """Cross-candidate binding proof (M4): every fact/location/provenance entry
    binds to a real candidate id, and a RELEASE fact is owned by one candidate.
    """
    probs: list[str] = []
    candidates = ir.get("candidates")
    if not isinstance(candidates, list):
        return probs
    cids = {str(c.get("id") or "") for c in candidates if isinstance(c, Mapping)}

    for i, f in enumerate(ir.get("facts") or []):
        if isinstance(f, Mapping) and f.get("candidate_id") not in cids:
            probs.append("facts[%d].candidate_id %r not in candidate ids"
                         % (i, f.get("candidate_id")))
    for i, loc in enumerate(ir.get("locations") or []):
        if isinstance(loc, Mapping) and loc.get("candidate_id") not in cids:
            probs.append("locations[%d].candidate_id %r not in candidate ids"
                         % (i, loc.get("candidate_id")))
    for i, p in enumerate(ir.get("provenance") or []):
        if isinstance(p, Mapping) and p.get("candidate_id") not in cids:
            probs.append("provenance[%d].candidate_id %r not in candidate ids"
                         % (i, p.get("candidate_id")))

    candidate_defect = {
        str(c.get("id") or ""): str(c.get("defect_type") or "")
        for c in candidates if isinstance(c, Mapping)
    }
    release_owners: dict[str, set[str]] = {}
    for f in (ir.get("facts") or []):
        if not isinstance(f, Mapping):
            continue
        if f.get("type") == "RELEASE" and f.get("fact_id"):
            release_owners.setdefault(f["fact_id"], set()).add(f["candidate_id"])
    for fid, owners in sorted(release_owners.items()):
        # One real free() may legitimately support several use_after_free
        # candidates (dereference-use and return-use). The strict one-owner
        # rule stays for double_free and every other defect type.
        if len(owners) > 1 and not all(
                candidate_defect.get(owner) in _SHARED_RELEASE_DEFECT_TYPES
                for owner in owners):
            probs.append("RELEASE fact %r claimed by several candidates: %r"
                         % (fid, sorted(owners)))
    return probs


__all__ = [
    "IR_SCHEMA_VERSION",
    "PROJECTOR_VERSION",
    "NOT_RECORDED",
    "CLAIM_STATUSES",
    "RELATION_TYPES",
    "BUNDLE_STATUSES",
    "IR_BLOCKS",
    "factbundle_v2_1_to_ir",
    "validate_evidence_ir_v1",
]

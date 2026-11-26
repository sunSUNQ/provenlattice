"""Candidate-bound FactBundle v2.1 location projection.

This module turns the already-serialized candidate records produced by
``provenlattice.defect_query.query_defect_candidates`` into the candidate-bound
v2.1 evidence contract:

* ``project_candidate``            -> per-candidate ``access_rows`` (race) and
                                      ``release_sites`` (double free) plus a
                                      primary anchor;
* ``build_supporting_locations``   -> the flattened, candidate-bound
                                      ``supporting_locations[]``;
* ``evidence_locations``           -> the per-candidate binding view;
* ``location_coverage``            -> the explicit degradation / coverage report;
* ``assert_candidate_binding``     -> the structural Candidate<->Evidence
                                      binding proof.

Design guarantees (inherited from the v2.1 reference contract):

* **no fabrication** -- a ``file``/``line`` is emitted only when a real engine
  field carries it; otherwise the row/location stays ``file=""``/``line=0``
  with ``anchor_class=unresolved`` and the candidate is listed in
  ``location_coverage.unlocated_candidates``;
* **candidate binding** -- every row/location carries a non-empty
  ``candidate_key`` and ``assert_candidate_binding`` proves the binding;
* **no duplicate facts** -- dedupe on (candidate_key, file, line, event_id,
  semantic_role);
* **status preservation** -- UNSUPPORTED / UNKNOWN / EMPTY stay as the engine
  reported them, never promoted to a safe verdict;
* **deterministic order** -- every list is sorted by a stable key.

The module never imports the engine and never reads GT, labels, markers or
historical runs.
"""

from __future__ import annotations

from typing import Any, Mapping

# --- provenance tags (the real engine field a location came from) ----------

PROV_EVIDENCE_V2 = "candidate.evidence_v2.access"
PROV_RELATED = "candidate.related_accesses"
PROV_FACTS = "candidate.facts"
PROV_ANCHOR = "candidate.metadata.anchor_span"
PROV_ANCHOR_FALLBACK = "candidate.access_row(anchor_fallback)"
PROV_RELEASE_FACTS = "candidate.facts[RELEASE].source"
PROV_RELEASE_META = "candidate.metadata.first_release/second_release"
PROV_METADATA_UNRESOLVED = "candidate.metadata.access(unresolved_event)"

# --- semantic roles (what a location *is*), distinct from the legacy ``role``
# (which keeps the fact-field name for back-compat). ------------------------

SEM_PRIMARY = "candidate_anchor"
SEM_ACCESS = "racing_access"
SEM_LOCK = "held_lock"
SEM_RELEASE = "release_site"
SEM_UNRESOLVED = "unresolved_location"

ANCHOR_PRIMARY = "primary"
ANCHOR_SUPPORTING = "supporting"
ANCHOR_UNRESOLVED = "unresolved"

# type-level event kind for a double-free release-site location. Encodes no
# engine resolution; every release fact carries it.
RELEASE_ACCESS_TYPE = "RELEASE"

_RANK = {ANCHOR_PRIMARY: 0, ANCHOR_SUPPORTING: 1, ANCHOR_UNRESOLVED: 2}

_KIND_MAP = {
    "read": "READ", "READ": "READ", "is_read": "READ",
    "write": "WRITE", "WRITE": "WRITE", "is_write": "WRITE",
    "read_modify_write": "READ_MODIFY_WRITE", "rmw": "READ_MODIFY_WRITE",
    "unknown": "UNKNOWN", "UNKNOWN": "UNKNOWN", "": "UNKNOWN",
}


def norm_kind(raw: Any) -> str:
    """Normalize an engine access kind to the by-contract spelling.

    Fail-closed: an unrecognised kind is ``UNKNOWN``, never defaulted to READ.
    """
    if isinstance(raw, bool):
        return "WRITE" if raw else "UNKNOWN"
    return _KIND_MAP.get(str(raw or "").strip(), "UNKNOWN")


def parse_source(src: Any) -> tuple[str, int]:
    """``("src/case_1.c:96-96") -> ("src/case_1.c", 96)``. Never invents a path."""
    s = "" if src is None else str(src)
    if ":" not in s:
        return s, 0
    head, tail = s.rsplit(":", 1)
    lead = tail.split("-")[0]
    try:
        line = int(lead)
    except (TypeError, ValueError):
        line = 0
    return head, line


def span_pair(span: Any) -> tuple[int, int]:
    """A ``[start, end]`` span to ``(start, end)``, fail-closed to ``(0, 0)``."""
    if isinstance(span, (list, tuple)) and len(span) >= 2:
        try:
            return int(span[0] or 0), int(span[1] or span[0] or 0)
        except (TypeError, ValueError):
            return 0, 0
    return 0, 0


def candidate_key(cand: Mapping[str, Any]) -> str:
    """Stable, UNIQUE per-candidate binding key.

    The subject identity is NOT unique: a shared_name defect (e.g.
    ``global:g_timePara#initFlag``) yields several candidates with the *same*
    subject identity that differ only in their access pair. Binding on identity
    would merge those candidates -- exactly the cross-candidate merge the
    contract forbids. So the key is, in order:

      1. ``evidence_id``         -- engine-unique candidate id (preferred);
      2. ``defect_key|discriminator`` -- the engine's re-identification tuple;
      3. ``identity@anchor``     -- identity made unique by its anchor;
      4. ``identity`` / subject name -- last resort.
    """
    ev = cand.get("evidence_id")
    if ev:
        return str(ev)
    dk = cand.get("defect_key")
    disc = cand.get("discriminator")
    if dk or disc:
        return "dk:%s|%s" % (dk or "", disc or "")
    subj = cand.get("subject") or {}
    ident = subj.get("identity") or subj.get("decl") or subj.get("name") or ""
    anchor = cand.get("anchor")
    if anchor:
        return "%s@%s" % (ident, anchor)
    return str(ident)


def candidate_descriptor(cand: Mapping[str, Any]) -> dict[str, Any]:
    """Non-location identity payload carried alongside the binding key."""
    subj = cand.get("subject") or {}
    return {
        "candidate_key": candidate_key(cand),
        "evidence_id": str(cand.get("evidence_id") or ""),
        "defect_key": str(cand.get("defect_key") or ""),
        "discriminator": str(cand.get("discriminator") or ""),
        "identity": str(subj.get("identity") or ""),
        "subject": str(subj.get("name") or ""),
        "anchor": str(cand.get("anchor") or ""),
    }


# ---------------------------------------------------------------------------
# per-candidate extraction helpers
# ---------------------------------------------------------------------------


def _held_locks_index(cand: Mapping[str, Any]) -> dict[str, list[str]]:
    """``access_event_id -> held_locks`` from the v2 lock and competing blocks."""
    locks: dict[str, list[str]] = {}
    ev2 = cand.get("evidence_v2") or {}
    for ls in ((ev2.get("lock") or {}).get("access_locksets") or []):
        if not isinstance(ls, Mapping):
            continue
        eid = ls.get("access_event_id")
        if eid:
            locks[str(eid)] = list(ls.get("held_locks") or [])
    for comp in (ev2.get("competing_access") or []):
        if not isinstance(comp, Mapping):
            continue
        for a in (comp.get("accesses") or []):
            if not isinstance(a, Mapping):
                continue
            eid = a.get("access_event_id")
            if eid and str(eid) not in locks:
                locks[str(eid)] = list(a.get("held_locks") or [])
    return locks


def _race_event_index(cand: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """``event_id -> located access record``, from evidence_v2 then related_accesses.

    An access row without ``access_event_id`` is indexed under a positional
    synthetic key (``~row:<n>``) instead of the empty string, so two id-less
    rows are never collapsed into one. The emitted row keeps the honest
    ``event_id=""`` -- the synthetic key never leaves this index.
    """
    idx: dict[str, dict[str, Any]] = {}
    locks = _held_locks_index(cand)
    ev2 = cand.get("evidence_v2") or {}

    def _key(eid: str, pos: int) -> str:
        return eid if eid else "~row:%d" % pos

    for pos, a in enumerate(ev2.get("access") or []):
        if not isinstance(a, Mapping):
            continue
        eid = str(a.get("access_event_id") or "")
        s, e = span_pair(a.get("source_span"))
        idx[_key(eid, pos)] = {
            "event_id": eid,
            "file": str(a.get("file") or ""),
            "line": s,
            "line_span": [s, e],
            "owner": str(a.get("owner") or ""),
            "owner_symbol_id": str(a.get("owner_symbol_id") or ""),
            "access_type": norm_kind(a.get("access_kind") or a.get("event_type")),
            "held_locks": locks.get(eid, []),
            "provenance": PROV_EVIDENCE_V2,
            "source_fact_id": eid,
        }

    pos = len(ev2.get("access") or [])
    for r in (cand.get("related_accesses") or []):
        if not isinstance(r, Mapping):
            continue
        eid = str(r.get("event_id") or "")
        k = _key(eid, pos)
        pos += 1
        if k in idx:
            continue
        s = int(r.get("start_line") or 0)
        e = int(r.get("end_line") or s or 0)
        idx[k] = {
            "event_id": eid,
            "file": str(r.get("relative_path") or ""),
            "line": s,
            "line_span": [s, e],
            "owner": str(r.get("owner") or ""),
            "owner_symbol_id": str(r.get("owner_symbol_id") or ""),
            "access_type": norm_kind(r.get("access_kind") or r.get("event_type")),
            "held_locks": locks.get(eid, []),
            "provenance": PROV_RELATED,
            "source_fact_id": eid,
        }
    return idx


def _fact_index(cand: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """``point/event id -> located record`` recovered from ``facts[].source``.

    Only facts carrying a real ``point`` are indexed: the fact ``event`` field
    is a *type* (READ/WRITE/RELEASE), never an id, and is not used as a key.
    """
    idx: dict[str, dict[str, Any]] = {}
    for f in (cand.get("facts") or []):
        if not isinstance(f, Mapping):
            continue
        eid = str(f.get("point") or "")
        if not eid:
            continue
        file, line = parse_source(f.get("source"))
        idx[eid] = {
            "event_id": eid,
            "file": file,
            "line": line,
            "line_span": [line, line],
            "owner": str(f.get("method") or ""),
            "owner_symbol_id": "",
            "access_type": norm_kind(f.get("event")),
            "held_locks": [],
            "provenance": PROV_FACTS,
            "source_fact_id": eid,
        }
    return idx


def _row(
    src: Mapping[str, Any],
    owner_symbol_id: str,
    side: Mapping[str, Any],
    ckey: str,
) -> dict[str, Any]:
    kind = src.get("access_type") or norm_kind((side or {}).get("kind"))
    owner = src.get("owner") or ""
    eid = src.get("event_id") or ""
    return {
        # legacy v1 keys (kept for back-compat)
        "method": owner,
        "file": src.get("file") or "",
        "line": int(src.get("line") or 0),
        "kind": kind,
        "non_atomic": bool((side or {}).get("non_atomic", False)),
        "decided": bool((side or {}).get("decided", False)),
        # v2 additions
        "owner": owner,
        "method_symbol_id": src.get("owner_symbol_id") or owner_symbol_id or "",
        "owner_symbol_id": src.get("owner_symbol_id") or owner_symbol_id or "",
        "access_type": kind,
        "line_span": list(src.get("line_span") or [0, 0]),
        "event_id": eid,
        "source_fact_id": src.get("source_fact_id") or eid,
        "provenance": src.get("provenance") or "",
        "held_locks": list(src.get("held_locks") or []),
        "candidate_key": ckey,
    }


def _row_key(r: Mapping[str, Any]) -> tuple:
    return (r.get("candidate_key"), r.get("file"), r.get("line"),
            r.get("event_id"), r.get("access_type"))


def _unresolved_row(
    owner_id: str,
    side: Mapping[str, Any],
    ckey: str,
    event_id: str = "",
    provenance: str | None = None,
) -> dict[str, Any]:
    k = norm_kind((side or {}).get("kind"))
    return {
        "method": "", "file": "", "line": 0, "kind": k,
        "non_atomic": bool((side or {}).get("non_atomic", False)),
        "decided": bool((side or {}).get("decided", False)),
        "owner": "", "method_symbol_id": owner_id or "",
        "owner_symbol_id": owner_id or "", "access_type": k,
        "line_span": [0, 0], "event_id": event_id,
        "source_fact_id": event_id or (owner_id or ""),
        "provenance": provenance or PROV_METADATA_UNRESOLVED,
        "held_locks": [], "candidate_key": ckey,
    }


# ---------------------------------------------------------------------------
# per-candidate projection
# ---------------------------------------------------------------------------


def project_candidate_accesses(cand: Mapping[str, Any]) -> list[dict[str, Any]]:
    """All located access rows for one candidate, candidate-bound and deduped.

    A metadata side may cite ``writer_event`` AND ``reader_event``; every
    distinct cited event yields its own row (never ``writer or reader``, which
    silently drops one of the two).
    """
    ckey = candidate_key(cand)
    ev = _race_event_index(cand)
    fac = _fact_index(cand)
    meta_access = (cand.get("metadata") or {}).get("access") or {}

    rows: list[dict[str, Any]] = []
    seen: set = set()
    used: set = set()

    if isinstance(meta_access, Mapping):
        for owner_id, side in meta_access.items():
            if not isinstance(side, Mapping):
                continue
            events: list[str] = []
            for k in ("writer_event", "reader_event"):
                e = side.get(k) or ""
                if e and e not in events:
                    events.append(str(e))
            if not events:
                r = _unresolved_row(str(owner_id), side, ckey)
                if _row_key(r) not in seen:
                    seen.add(_row_key(r))
                    rows.append(r)
                continue
            for eid in events:
                src = ev.get(eid) or fac.get(eid)
                if src is not None:
                    used.add(eid)
                    r = _row(src, str(owner_id), side, ckey)
                else:
                    # a cited event id that carries no location in any indexed
                    # payload: keep the id, keep the row, declare it unresolved.
                    r = _unresolved_row(str(owner_id), side, ckey, event_id=eid)
                if _row_key(r) in seen:
                    continue
                seen.add(_row_key(r))
                rows.append(r)

    # every located access event the metadata block did not already cover
    for eid, src in ev.items():
        if eid in used:
            continue
        r = _row(src, src.get("owner_symbol_id", ""), {"decided": True}, ckey)
        if _row_key(r) in seen:
            continue
        seen.add(_row_key(r))
        rows.append(r)

    rows.sort(key=lambda r: (r.get("file", ""), r.get("line", 0),
                             r.get("event_id", ""), r.get("access_type", ""),
                             r.get("owner", "")))
    return rows


def project_candidate_release_sites(cand: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The RELEASE facts of ONE candidate, as candidate-bound locations.

    Each site is derived from the candidate's own ``facts[]`` entry whose
    ``event``/``fact`` is ``RELEASE``; ``source_fact_id`` is that fact's engine
    event id (``point``). ``metadata.first_release`` / ``metadata.second_release``
    are only used to add a site the facts block does not carry (they are the
    same events in the live engine output and are deduped by event id).

    Never merged across candidates: the candidate key is the function's subject.
    """
    ckey = candidate_key(cand)
    subj = cand.get("subject") or {}
    sites: list[dict[str, Any]] = []
    seen: set = set()

    def add(rel: Mapping[str, Any], provenance: str) -> None:
        eid = str(rel.get("point") or rel.get("event_id") or "")
        src = rel.get("source") or rel.get("location") or ""
        file, line = parse_source(src)
        if not file:
            file = str(rel.get("relative_path") or rel.get("file") or "")
        if not line:
            try:
                line = int(rel.get("line") or 0)
            except (TypeError, ValueError):
                line = 0
        located = bool(file and line)
        owner = (str(rel.get("method") or rel.get("function") or "")
                 or str(subj.get("name") or ""))
        k = ("eid", eid) if eid else ("loc", file, line)
        if k in seen:
            return
        seen.add(k)
        sites.append({
            "file": file, "line": line,
            "line_span": [line, line],
            "role": "release_sites",
            "semantic_role": SEM_RELEASE,
            "anchor_class": ANCHOR_SUPPORTING if located else ANCHOR_UNRESOLVED,
            "owner": owner,
            "access_type": RELEASE_ACCESS_TYPE,
            "source_fact_id": eid,
            "event_id": eid,
            "provenance": provenance,
            "candidate_key": ckey,
            "held_locks": [],
        })

    for f in (cand.get("facts") or []):
        if not isinstance(f, Mapping):
            continue
        if (f.get("event") or f.get("fact")) != "RELEASE":
            continue
        add(f, PROV_RELEASE_FACTS)

    meta = cand.get("metadata") or {}
    for name in ("first_release", "second_release"):
        rel = meta.get(name)
        if not isinstance(rel, Mapping):
            continue
        if rel.get("declared") is False:
            continue
        if not (rel.get("point") or rel.get("source") or rel.get("location")):
            continue
        add(rel, PROV_RELEASE_META)

    sites.sort(key=lambda l: (l["file"], l["line"], l["event_id"]))
    return sites


def project_candidate(cand: Mapping[str, Any]) -> dict[str, Any]:
    """Candidate-bound projection: located rows + release sites + primary anchor."""
    ckey = candidate_key(cand)
    subj = cand.get("subject") or {}
    span = (cand.get("metadata") or {}).get("anchor_span") or {}

    afile = str(span.get("relative_path") or "")
    aline = int(span.get("start_line") or 0)
    aend = int(span.get("end_line") or aline or 0)
    anchor_prov = PROV_ANCHOR if (afile or aline) else ""

    rows = project_candidate_accesses(cand)
    sites = project_candidate_release_sites(cand)

    if not afile or not aline:
        # fall back to the first located row/site, but record the real provenance
        for r in (rows or sites):
            if r.get("file") and r.get("line"):
                afile = r["file"]
                aline = r["line"]
                aend = (r.get("line_span") or [aline, aline])[1] or aline
                anchor_prov = PROV_ANCHOR_FALLBACK
                break

    primary = None
    if afile or aline:
        primary = {"file": afile, "line": aline, "line_span": [aline, aend],
                   "provenance": anchor_prov}

    return {
        "candidate_key": ckey,
        "evidence_id": str(cand.get("evidence_id") or ""),
        "defect_key": str(cand.get("defect_key") or ""),
        "discriminator": str(cand.get("discriminator") or ""),
        "subject": str(subj.get("name") or ""),
        "identity": str(subj.get("identity") or ""),
        "access_rows": rows,
        "release_sites": sites,
        "primary_anchor": primary,
    }


# ---------------------------------------------------------------------------
# generic fact projection (projector-registry expansion)
# ---------------------------------------------------------------------------

# Fact type -> semantic role. The roles are a superset of the frozen v2.1
# race/double-free roles; they are only emitted by the generic adapter entries.
GENERIC_FACT_ROLE = {
    "ALLOC": "resource_alloc",
    "RELEASE": "release_site",
    "LOCK": "held_lock",
    "UNLOCK": "held_lock",
    "DEREFERENCE": "dereference",
    "READ": "racing_access",
    "WRITE": "racing_access",
    "READ_MODIFY_WRITE": "racing_access",
    "CALL": "call",
    "CHECK": "control",
    "BRANCH": "control",
    "RETURN": "control",
    "NULL": "null_value",
}

# Event vocabulary that can appear in candidate.facts[] but has no dedicated
# semantic role above. They stay ``fact`` locations; the type is preserved.
GENERIC_EVENT_TYPES = frozenset({
    "THROW", "ATOMIC", "THREAD_SPAWN", "THREAD_JOIN", "EXIT", "TRAP", "ASSUME",
})
GENERIC_FACT_TYPES = frozenset(GENERIC_FACT_ROLE) | GENERIC_EVENT_TYPES | {"fact"}


def _generic_fact_rows(cand: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project one candidate's ``facts[]`` into located candidate-bound rows.

    The engine already carries the real fact/event id in ``point`` and the
    real source location in ``source``. This function never invents either:
    a fact with neither an id nor a location is dropped, and a fact with a
    location but no id keeps ``event_id=""`` / ``source_fact_id=""``.
    """
    ckey = candidate_key(cand)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for fact in cand.get("facts") or []:
        if not isinstance(fact, Mapping):
            continue
        fact_type = str(fact.get("event") or fact.get("fact") or "").strip()
        if not fact_type and fact.get("lock"):
            # lock_order facts carry the lock identity/role instead of an
            # ``event`` scalar; each one is a LOCK acquisition fact.
            fact_type = "LOCK"
        source = fact.get("source") or fact.get("location") or ""
        file, line = parse_source(source)
        if not file:
            file = str(fact.get("relative_path") or fact.get("file") or "")
        if not line:
            try:
                line = int(fact.get("line") or 0)
            except (TypeError, ValueError):
                line = 0
        event_id = str(fact.get("point") or fact.get("event_id") or "")
        if not fact_type or (not event_id and not (file and line)):
            continue
        key = (file, line, event_id, fact_type)
        if key in seen:
            continue
        seen.add(key)
        owner = str(fact.get("method") or fact.get("function") or "")
        attributes = {
            k: v for k, v in fact.items()
            if k not in {"method", "function", "source", "location", "point",
                         "event_id", "relative_path", "file", "line"}
        }
        rows.append({
            "method": owner,
            "file": file,
            "line": line,
            "line_span": [line, line],
            "kind": fact_type,
            "fact_id": event_id,
            "fact_type": fact_type,
            "non_atomic": False,
            "decided": True,
            "access_type": fact_type,
            "owner": owner,
            "method_symbol_id": str(fact.get("method_symbol_id") or ""),
            "owner_symbol_id": str(fact.get("owner_symbol_id") or
                                   (cand.get("subject") or {}).get("owner_symbol_id") or ""),
            "event_id": event_id,
            "source_fact_id": event_id,
            "provenance": "candidate.facts",
            "held_locks": [],
            "candidate_key": ckey,
            "attributes": attributes,
        })
    rows.sort(key=lambda r: (r["file"], r["line"], r["event_id"], r["access_type"]))
    return rows


def _generic_primary_anchor(cand: Mapping[str, Any],
                            rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    span = (cand.get("metadata") or {}).get("anchor_span") or {}
    if span.get("relative_path") or span.get("start_line"):
        start = int(span.get("start_line") or 0)
        return {
            "file": str(span.get("relative_path") or ""),
            "line": start,
            "line_span": [start, int(span.get("end_line") or start or 0)],
            "provenance": "candidate.metadata.anchor_span",
        }
    for row in rows:
        if row["file"] and row["line"]:
            return {
                "file": row["file"],
                "line": row["line"],
                "line_span": list(row["line_span"]),
                "provenance": "candidate.facts[0]",
            }
    return None


def project_candidate_generic(cand: Mapping[str, Any]) -> dict[str, Any]:
    """Candidate-bound generic projection: located facts + primary anchor.

    The generic shape deliberately reuses ``access_rows`` for IR V1
    compatibility: ``ir.factbundle_v2_1_to_ir`` reads ``access_rows`` and uses
    ``access_type`` as the fact type. No IR V1 schema change is required for
    the prototype.
    """
    ckey = candidate_key(cand)
    subj = cand.get("subject") or {}
    rows = _generic_fact_rows(cand)
    return {
        "candidate_key": ckey,
        "evidence_id": str(cand.get("evidence_id") or ""),
        "defect_key": str(cand.get("defect_key") or ""),
        "discriminator": str(cand.get("discriminator") or ""),
        "subject": str(subj.get("name") or ""),
        "identity": str(subj.get("identity") or ""),
        "resolution_status": str(cand.get("resolution_status") or ""),
        "confidence": cand.get("confidence"),
        "primary_anchor": _generic_primary_anchor(cand, rows),
        "access_rows": rows,
        "release_sites": [],
        "uncertain_facts": list(cand.get("uncertain_facts") or []),
        "missing_evidence": list(cand.get("missing_evidence") or []),
    }


def build_supporting_locations_generic(
    projected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flatten generic anchors/facts into ``supporting_locations[]``."""
    locs: list[dict[str, Any]] = []
    for pc in projected:
        ckey = pc["candidate_key"]
        pa = pc.get("primary_anchor")
        if pa is not None:
            locs.append({
                "file": pa["file"], "line": pa["line"],
                "line_span": list(pa["line_span"]),
                "role": "candidate_anchor",
                "semantic_role": SEM_PRIMARY,
                "anchor_class": ANCHOR_PRIMARY if (pa["file"] and pa["line"])
                                else ANCHOR_UNRESOLVED,
                "owner": "", "access_type": "", "source_fact_id": "", "event_id": "",
                "provenance": pa.get("provenance") or "",
                "candidate_key": ckey, "held_locks": [],
            })
        for row in pc.get("access_rows") or []:
            fact_type = str(row.get("access_type") or "")
            locs.append({
                "file": row["file"], "line": row["line"],
                "line_span": list(row["line_span"]),
                "role": fact_type.lower() or "fact",
                "semantic_role": GENERIC_FACT_ROLE.get(fact_type, "fact"),
                "anchor_class": ANCHOR_SUPPORTING if (row["file"] and row["line"])
                                else ANCHOR_UNRESOLVED,
                "owner": row.get("owner") or row.get("method") or "",
                "access_type": fact_type,
                "source_fact_id": row.get("source_fact_id") or "",
                "event_id": row.get("event_id") or "",
                "provenance": row.get("provenance") or "",
                "candidate_key": ckey, "held_locks": [],
            })
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for loc in locs:
        key = (loc["candidate_key"], loc["file"], loc["line"],
               loc["event_id"], loc["semantic_role"])
        if key in seen:
            continue
        seen.add(key)
        out.append(loc)
    out.sort(key=lambda l: (l["candidate_key"], _RANK.get(l["anchor_class"], 3),
                            l["file"], l["line"], l["event_id"],
                            l["semantic_role"]))
    return out


def generic_location_coverage(
    projected: list[dict[str, Any]],
    supporting: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Explicit generic degradation report, including v2.1 compatibility keys."""
    supporting = supporting if supporting is not None else \
        build_supporting_locations_generic(projected)
    with_primary = 0
    with_facts = 0
    located_facts = 0
    total_facts = 0
    unlocated: list[str] = []
    by_fact_type: dict[str, int] = {}
    by_role: dict[str, int] = {}
    for pc in projected:
        rows = pc.get("access_rows") or []
        located = [r for r in rows if r.get("file") and r.get("line")]
        total_facts += len(rows)
        located_facts += len(located)
        if pc.get("primary_anchor"):
            with_primary += 1
        if located:
            with_facts += 1
        for row in rows:
            typ = str(row.get("access_type") or "")
            by_fact_type[typ] = by_fact_type.get(typ, 0) + 1
        if not pc.get("primary_anchor") and not located:
            unlocated.append(pc["candidate_key"])
    for loc in supporting:
        role = str(loc.get("semantic_role") or "")
        by_role[role] = by_role.get(role, 0) + 1
    located_support = sum(1 for loc in supporting
                          if loc.get("file") and loc.get("line"))
    return {
        "candidates": len(projected),
        "with_primary_anchor": with_primary,
        "with_access_locations": with_facts,
        "with_support_locations": with_primary + with_facts - sum(
            1 for pc in projected
            if pc.get("primary_anchor")
            and any(r.get("file") and r.get("line") for r in (pc.get("access_rows") or []))),
        "with_fact_locations": with_facts,
        "located_facts": located_facts,
        "total_facts": total_facts,
        "supporting_locations": len(supporting),
        "located_supporting_locations": located_support,
        "unlocated_candidates": unlocated,
        "by_fact_type": dict(sorted(by_fact_type.items())),
        "by_semantic_role": dict(sorted(by_role.items())),
    }


# ---------------------------------------------------------------------------
# bundle-level assembly
# ---------------------------------------------------------------------------


def build_supporting_locations(
    projected: list[dict[str, Any]],
    role_fact_name: str = "shared_accesses",
) -> list[dict[str, Any]]:
    """Flatten every candidate's anchors into ``supporting_locations[]``.

    * a candidate anchor is ``semantic_role=candidate_anchor``,
      ``anchor_class=primary``;
    * a located racing access is ``semantic_role=racing_access``;
    * a RELEASE fact location is ``semantic_role=release_site``
      (``role="release_sites"``, the v1 fact-field name).

    For a double-free candidate the anchor normally *is* one of its release
    sites (the second release); in that case the anchor row is not emitted twice
    -- the release-site entry at that line already carries the anchor's file/line
    and additionally the real ``source_fact_id``.
    """
    locs: list[dict[str, Any]] = []
    for pc in projected:
        ckey = pc["candidate_key"]
        sites = pc.get("release_sites") or []
        pa = pc.get("primary_anchor")
        site_lines = {(s["file"], s["line"]) for s in sites
                      if s.get("file") and s.get("line")}
        if pa is not None and (pa["file"], pa["line"]) not in site_lines:
            locs.append({
                "file": pa["file"], "line": pa["line"],
                "line_span": list(pa["line_span"]),
                "role": role_fact_name,
                "semantic_role": SEM_PRIMARY,
                "anchor_class": ANCHOR_PRIMARY,
                "owner": "", "access_type": "",
                "source_fact_id": "", "event_id": "",
                "provenance": pa.get("provenance") or PROV_ANCHOR,
                "candidate_key": ckey, "held_locks": [],
            })
        for s in sites:
            locs.append(dict(s))
        for r in pc["access_rows"]:
            locs.append({
                "file": r["file"], "line": r["line"],
                "line_span": list(r["line_span"]),
                "role": role_fact_name,
                "semantic_role": SEM_ACCESS,
                "anchor_class": ANCHOR_SUPPORTING if (r["file"] and r["line"])
                                else ANCHOR_UNRESOLVED,
                "owner": r["owner"], "access_type": r["access_type"],
                "source_fact_id": r["source_fact_id"], "event_id": r["event_id"],
                "provenance": r["provenance"],
                "candidate_key": ckey, "held_locks": list(r["held_locks"]),
            })

    seen: set = set()
    out: list[dict[str, Any]] = []
    for loc in locs:
        k = (loc["candidate_key"], loc["file"], loc["line"], loc["event_id"],
             loc["semantic_role"])
        if k in seen:
            continue
        seen.add(k)
        out.append(loc)
    out.sort(key=lambda l: (l["candidate_key"], _RANK.get(l["anchor_class"], 3),
                            l["file"], l["line"], l["event_id"]))
    return out


def location_coverage(projected: list[dict[str, Any]]) -> dict[str, Any]:
    """Explicit degradation report: which candidates have a usable location.

    ``with_access_locations`` keeps its v2 meaning (a located *racing access*
    row). ``with_support_locations`` (v2.1) is the defect-type-neutral count.
    ``by_semantic_role`` lists the located counts per semantic role.
    """
    with_primary = 0
    with_access = 0
    with_support = 0
    unlocated: list[str] = []
    by_role = {SEM_PRIMARY: 0, SEM_ACCESS: 0, SEM_RELEASE: 0}
    for pc in projected:
        located_rows = [r for r in (pc.get("access_rows") or [])
                        if r.get("file") and r.get("line")]
        located_sites = [s for s in (pc.get("release_sites") or [])
                         if s.get("file") and s.get("line")]
        if pc.get("primary_anchor"):
            with_primary += 1
            by_role[SEM_PRIMARY] += 1
        if located_rows:
            with_access += 1
        if located_rows or located_sites:
            with_support += 1
        by_role[SEM_ACCESS] += len(located_rows)
        by_role[SEM_RELEASE] += len(located_sites)
        if not pc.get("primary_anchor") and not located_rows and not located_sites:
            unlocated.append(pc["candidate_key"])
    return {
        "candidates": len(projected),
        "with_primary_anchor": with_primary,
        "with_access_locations": with_access,
        "with_support_locations": with_support,
        "unlocated_candidates": unlocated,
        "by_semantic_role": {k: by_role[k] for k in sorted(by_role)},
    }


def evidence_locations(projected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-candidate binding view (the Candidate <-> Evidence Relation contract)."""
    return [
        {
            "candidate_key": pc["candidate_key"],
            "evidence_id": pc.get("evidence_id", ""),
            "defect_key": pc.get("defect_key", ""),
            "discriminator": pc.get("discriminator", ""),
            "subject": pc["subject"],
            "identity": pc["identity"],
            "primary_anchor": pc["primary_anchor"],
            "access_rows": pc["access_rows"],
            "release_sites": pc.get("release_sites") or [],
        }
        for pc in projected
    ]


# ---------------------------------------------------------------------------
# automated candidate-binding assertion
# ---------------------------------------------------------------------------


def assert_candidate_binding(
    bundle: Mapping[str, Any],
    *,
    allow_shared_release: bool | None = None,
) -> list[str]:
    """Prove the Candidate <-> Evidence binding on a finished FactBundle.

    Returns a list of problems (empty == bound). Structural, no heuristics:

      1. ``evidence_locations`` candidate keys are unique and non-empty;
      2. every ``supporting_locations[]`` entry carries a non-empty
         ``candidate_key`` that exists in ``evidence_locations``;
      3. every non-empty ``source_fact_id`` belongs to the candidate that owns
         the location (its own facts / access rows / release sites) -- a
         location carrying another candidate's fact id is a cross-candidate
         merge;
      4. no RELEASE fact is claimed by two different candidates. Racing *access*
         events are deliberately NOT checked this way: the engine legitimately
         cites one access event as evidence for several candidates that differ
         only in their access pair, and that is not a merge.

    ``use_after_free`` is the one exception to rule 4: one real ``free(p)`` can
    legitimately support both a dereference-use candidate and a return-use
    candidate. The check therefore allows a shared RELEASE fact when every
    owner is a UAF candidate (or when the caller explicitly allows it).
    """
    if allow_shared_release is None:
        # Only double_free needs the strict "one RELEASE fact, one candidate"
        # rule. For the generic lifetime/resource defects the same engine
        # release event can legitimately be cited by several candidates.
        allow_shared_release = bundle.get("defect_type") in {
            "use_after_free", "resource_lifetime", "null_flow",
            "mismatched_free",
        }
    probs: list[str] = []
    ev = bundle.get("evidence_locations") or []
    if not isinstance(ev, list):
        return ["evidence_locations is not a list"]

    keys: list[str] = []
    own_events: dict[str, set[str]] = {}
    release_owner: dict[str, set[str]] = {}
    for pc in ev:
        if not isinstance(pc, dict):
            probs.append("non-dict evidence_location")
            continue
        k = pc.get("candidate_key") or ""
        if not k:
            probs.append("empty candidate_key in evidence_locations")
        keys.append(k)
        ids: set[str] = set()
        for s in (pc.get("release_sites") or []):
            if s.get("source_fact_id"):
                ids.add(s["source_fact_id"])
                release_owner.setdefault(s["source_fact_id"], set()).add(k)
        for r in (pc.get("access_rows") or []):
            if r.get("source_fact_id"):
                ids.add(r["source_fact_id"])
                if r.get("access_type") == "RELEASE":
                    release_owner.setdefault(
                        r["source_fact_id"], set()).add(k)
        own_events[k] = ids

    if len(keys) != len(set(keys)):
        dup = sorted({k for k in keys if keys.count(k) > 1})
        probs.append("duplicate candidate_key in evidence_locations: %r" % (dup,))

    for loc in (bundle.get("supporting_locations") or []):
        if not isinstance(loc, dict):
            probs.append("non-dict supporting_location")
            continue
        k = loc.get("candidate_key") or ""
        if not k:
            probs.append("empty candidate_key in supporting_locations: %r:%r"
                         % (loc.get("file"), loc.get("line")))
            continue
        if k not in own_events:
            probs.append("supporting_location candidate_key not in "
                         "evidence_locations: %r" % (k,))
            continue
        sid = loc.get("source_fact_id") or ""
        if sid and sid not in own_events[k]:
            probs.append("supporting_location source_fact_id %r is not this "
                         "candidate's fact (cross-candidate merge)" % (sid,))

    for eid, owners in sorted(release_owner.items()):
        if len(owners) > 1 and not allow_shared_release:
            probs.append("RELEASE fact %r claimed by several candidates: %r"
                         % (eid, sorted(owners)))
    return probs


__all__ = [
    "PROV_EVIDENCE_V2", "PROV_RELATED", "PROV_FACTS", "PROV_ANCHOR",
    "PROV_ANCHOR_FALLBACK", "PROV_RELEASE_FACTS", "PROV_RELEASE_META",
    "PROV_METADATA_UNRESOLVED",
    "SEM_PRIMARY", "SEM_ACCESS", "SEM_LOCK", "SEM_RELEASE", "SEM_UNRESOLVED",
    "ANCHOR_PRIMARY", "ANCHOR_SUPPORTING", "ANCHOR_UNRESOLVED",
    "RELEASE_ACCESS_TYPE",
    "norm_kind", "parse_source", "span_pair", "candidate_key",
    "candidate_descriptor", "project_candidate_accesses",
    "project_candidate_release_sites", "project_candidate",
    "build_supporting_locations", "location_coverage", "evidence_locations",
    "assert_candidate_binding",
    "GENERIC_FACT_ROLE", "GENERIC_FACT_TYPES", "project_candidate_generic",
    "build_supporting_locations_generic", "generic_location_coverage",
]
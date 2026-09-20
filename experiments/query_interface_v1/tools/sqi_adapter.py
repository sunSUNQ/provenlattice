"""SQI-V1 adapter: the six frozen canonical calls over the frozen
ProvenLattice implementation.

Hard rules enforced here (Contract V1):

  * one handler per canonical call; each handler may only invoke its allowed
    underlying GraphQuery methods (no scope creep);
  * one shared budget pool; declared budgets are clamped to hard caps and the
    applied budget is echoed in every envelope; truncation is explicit and
    deterministic (rows keep frozen order, evidence is sorted by evidence_id);
  * unresolved raw references are returned verbatim with their status;
  * impact.frontier is shard-level only - the adapter does not derive any
    symbol-level impact;
  * every envelope is validated (schema + semantics) before it leaves the
    adapter, so a contract violation is an adapter bug, never caller data.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from provenlattice.evidence import evidence_id  # noqa: E402
from provenlattice.query import GraphQuery  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sqi_validator import HARD_CAPS, validate_envelope  # noqa: E402

SQI_VERSION = "SQI-V1"
DEFAULT_BUDGET = {"max_evidence": 20, "max_symbols": 8, "max_edges": 20, "max_sections": 4}
RESPONSE_BYTE_LIMIT = 262144

SOURCE_VERIFICATION_POLICY = {
    "requires_source_verification": [
        "definition_semantics", "call_site_semantics", "reference_purpose",
        "downstream_impact", "document_equivalence",
    ],
    "direct_trust": [
        "symbol_identity", "edge_existence",
        "reference_existence_and_status", "frontier_membership",
    ],
    # V1.2-NR1: generic agent usage discipline (no benchmark specifics).
    # Emitted to the agent once per session with the first envelope.
    "usage_discipline": [
        "Never repeat an identical invocation (same call, params, database, "
        "commit): it returns the byte-identical envelope. A truncated result "
        "will not expand on retry - issue a more targeted query instead. A "
        "truncated envelope is normal and already contains everything that "
        "call can return under its budget: finish from the returned evidence "
        "whenever it suffices, and do not re-query the same anchor with a "
        "different budget just to obtain a shorter envelope.",
        "Before finishing, verify that every distinct source domain the task "
        "requires has contributed cited evidence (e.g. tasks spanning code "
        "and knowledge must show evidence from each domain); an answer "
        "missing a required domain is incomplete.",
        # V1.2-NR2: generic empty-result exploration discipline (no
        # benchmark specifics). Teaches resolution semantics + recovery
        # instead of semantically-equivalent retries.
        "An empty envelope is definitive for the anchor form you used: "
        "anchors resolve by exact node id, qualified_name, or node name "
        "only. Check resolution with symbol.lookup or bundle.explain on the "
        "anchor alone; if it does not resolve, vary the identifier form or "
        "discover stored names with a broader query instead of retrying "
        "semantically equivalent forms.",
    ],
}

# V1.2-NR2: generic guidance merged into result_meta of every empty
# (zero data rows, zero evidence, no error) envelope. Interface semantics
# only — no task identifiers, no required evidence ids, no benchmark
# specifics. Deterministic content: byte-identical for identical calls.
EMPTY_RESULT_GUIDANCE = (
    "empty result: either the anchor matched no node (anchors resolve by "
    "exact node id, qualified_name, or node name only; path fragments, "
    "file#section forms, and natural-language variants do not resolve) or "
    "the anchor exists but has no matching relations. First re-query the "
    "anchor alone (symbol.lookup or bundle.explain) to check resolution; if "
    "it does not resolve, vary the identifier form or discover stored names "
    "with a broader query (e.g. bundle.explain on the enclosing document or "
    "symbol), then re-query the discovered name."
)

ROW_CAP_FIELD = {
    "symbol.lookup": "max_symbols",
    "symbol.callers": "max_edges",
    "symbol.callees": "max_edges",
    "symbol.references": "max_edges",
    "impact.frontier": "max_edges",
    "code.related": "max_symbols",
}
OMITTED_FIELD = {
    "symbol.lookup": "symbols",
    "symbol.callers": "edges",
    "symbol.callees": "edges",
    "symbol.references": "raw_refs",
    "impact.frontier": "edges",
    "code.related": "symbols",
}


class SQIError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _clamp(declared: dict | None) -> dict:
    declared = {**DEFAULT_BUDGET, **(declared or {})}
    return {field: max(0, min(int(declared[field]), HARD_CAPS[field]))
            for field in DEFAULT_BUDGET}


ROW_FIELDS = ("id", "qualified_name", "name", "kind", "language", "file_id",
              "file_path", "shard_id", "start_line", "end_line", "signature",
              "relation", "status", "raw_name", "owner_symbol_id",
              "resolved_symbol_id", "edge_metadata", "shard_path",
              "changed_shard_path", "boundary_edge_count", "boundary_edge_ids",
              "boundary_edge_ids_omitted", "definition_of")
METADATA_FIELDS = ("relative_path", "shard_path", "public", "bases",
                   "heading_path", "document_file")


def _project_row(row: dict) -> dict:
    """Deterministic bounded projection of a fact row (contract S7/B1: no
    unbounded blobs are ever shipped back to the agent)."""
    if not isinstance(row, dict):
        return row
    out = {field: row[field] for field in ROW_FIELDS if field in row}
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        out["metadata"] = {key: metadata[key] for key in METADATA_FIELDS
                           if key in metadata}
    return out


def _dedupe_evidence_projection(items: list[dict], header_repository: str,
                                header_commit: str) -> list[dict]:
    """V1.2 identity dedup: drop per-entry repository/commit when they are
    byte-identical to the envelope header (the header is authoritative);
    retain entries whose repository differs (cross-database minting) or whose
    commit is meaningful-and-different. 'unknown' (the frozen lib's
    not-recorded marker) is dropped as information-neutral."""
    out = []
    for item in items:
        item = dict(item)
        if item.get("repository") == header_repository:
            item.pop("repository", None)
        if item.get("commit") in ("", "unknown", None):
            item.pop("commit", None)
        elif item.get("commit") == header_commit:
            item.pop("commit", None)
        out.append(item)
    return out


class SQIAdapter:
    """Read-only SQI-V1 interface over one frozen database."""

    def __init__(self, database: str | Path, commit: str,
                 code_database: str | Path | None = None):
        self.database = str(database)
        self.commit = commit
        self._file_paths_cache: dict[str, str] | None = None
        self._q = GraphQuery(self.database)
        self._code_q: GraphQuery | None = None
        self.code_database = str(code_database) if code_database else None
        repository, db_commit = self._q._context()
        self.repository = repository or "repo:" + "0" * 64
        self.db_commit = db_commit or "unknown"

    def _code_graph(self) -> GraphQuery | None:
        """Lazily opened GraphQuery over the declared code database (T05
        composite: OPT-T05-COMPRESSION)."""
        if self.code_database is None:
            return None
        if self._code_q is None:
            self._code_q = GraphQuery(self.code_database)
        return self._code_q

    def close(self) -> None:
        self._q.close()
        if self._code_q is not None:
            self._code_q.close()

    def __enter__(self) -> "SQIAdapter":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # shared envelope construction
    # ------------------------------------------------------------------
    def _envelope(self, query_type: str, anchor: str, params: dict,
                  raw: dict, declared: dict | None,
                  data_rows: list | None = None,
                  extra_meta: dict | None = None) -> dict:
        applied = _clamp(declared)
        declared_full = {**DEFAULT_BUDGET, **(declared or {})}
        evidence = raw.get("evidence") or []
        if data_rows is None:
            data_rows = raw.get("data") or []
        row_cap = applied[ROW_CAP_FIELD[query_type]]
        ev_cap = applied["max_evidence"]
        data_rows = [_project_row(row) for row in data_rows]
        kept_rows = data_rows[:min(row_cap, ev_cap)]
        omitted_rows = max(len(data_rows) - len(kept_rows), 0)

        row_ids = {row.get("id") for row in kept_rows if isinstance(row, dict)}
        bound = {}
        for item in evidence:
            fact_id = (item.get("metadata") or {}).get("fact_id")
            if (item.get("target_id") in row_ids or item.get("source_id") in row_ids
                    or fact_id in row_ids):
                bound.setdefault(item["evidence_id"], item)
        kept_evidence = _dedupe_evidence_projection(
            [bound[eid] for eid in sorted(bound)], self.repository, self.commit)
        kept_evidence = kept_evidence[:ev_cap]

        omitted = {"symbols": 0, "edges": 0, "raw_refs": 0, "sections": 0}
        omitted[OMITTED_FIELD[query_type]] = omitted_rows
        used = {
            "symbols": len(kept_rows) if query_type in ("symbol.lookup", "code.related") else 0,
            "edges": len(kept_rows) if query_type in ("symbol.callers", "symbol.callees",
                                                      "impact.frontier") else 0,
            "raw_refs": len(kept_rows) if query_type == "symbol.references" else 0,
            "sections": 0,
            "evidence": len(kept_evidence),
        }
        # V1.2-NR2: empty envelopes carry generic recovery guidance in
        # result_meta (deterministic; error envelopes exclude it — see
        # _error). Non-empty envelopes are byte-unchanged.
        meta = dict(extra_meta or {})
        if not kept_rows and not kept_evidence:
            meta["empty_result_guidance"] = EMPTY_RESULT_GUIDANCE
        envelope = {
            "sqi_version": SQI_VERSION,
            "query_id": raw["query_id"],
            "query_type": query_type,
            "anchor": anchor,
            "params": params,
            "repository": self.repository,
            "commit": self.commit,
            "graph_generation": raw.get("graph_generation", 0),
            "data": kept_rows,
            "evidence": kept_evidence,
            "returned_evidence_ids": [item["evidence_id"] for item in kept_evidence],
            "returned_evidence_count": len(kept_evidence),
            "bundle_size": raw.get("bundle_size", 0),
            "budget": {"declared": {field: int(declared_full[field])
                                    for field in DEFAULT_BUDGET},
                       "applied": applied, "used": used},
"truncation": {"truncated": any(value > 0 for value in omitted.values()),
               "omitted_counts": omitted,
               "retry_same_call_will_not_expand": True},
"source_verification_policy": SOURCE_VERIFICATION_POLICY,
            "result_meta": meta,
            "query_time_ms": raw.get("query_time_ms", 0.0),
        }
        size = len(json.dumps(envelope, ensure_ascii=False))
        if size > RESPONSE_BYTE_LIMIT:
            raise SQIError("RESPONSE_TOO_LARGE",
                           f"envelope is {size} bytes, limit {RESPONSE_BYTE_LIMIT}")
        ok, errors = validate_envelope(envelope)
        if not ok:
            raise SQIError("ADAPTER_SELF_VALIDATION_FAILED",
                           "; ".join(errors[:8]))
        return envelope

    def _error(self, query_type: str, anchor: str, params: dict,
               declared: dict | None, code: str, message: str) -> dict:
        envelope = self._envelope(query_type, anchor, params,
                                  {"query_id": "Q-" + "0" * 20,
                                   "graph_generation": 0, "data": [],
                                   "evidence": [], "bundle_size": 0,
                                   "query_time_ms": 0.0},
                                  declared)
        # V1.2-NR2: the empty-result guidance describes valid-but-empty
        # outcomes; an error envelope already explains itself.
        envelope.get("result_meta", {}).pop("empty_result_guidance", None)
        envelope["error"] = {"code": code, "message": message}
        return envelope

    # ------------------------------------------------------------------
    # Q1 symbol.lookup (OPT-T01-PROJECTION: compact candidate rows)
    # ------------------------------------------------------------------
    def symbol_lookup(self, name: str, kind: str | None = None,
                      path_prefix: str | None = None,
                      budget: dict | None = None) -> dict:
        params = {"name": name, "kind": kind, "path_prefix": path_prefix}
        if not name or not isinstance(name, str):
            return self._error("symbol.lookup", name or "", params, budget,
                               "INVALID_INPUT", "name must be a non-empty string")
        raw = self._q.find_symbol(name)
        rows = raw.get("data") or []
        if kind is not None:
            rows = [row for row in rows if row.get("kind") == kind]
        if path_prefix is not None:
            rows = [row for row in rows
                    if str((row.get("metadata") or {}).get("relative_path", ""))
                    .startswith(path_prefix)]
        rows = sorted(rows, key=lambda row: (
            str((row.get("metadata") or {}).get("relative_path", "")),
            int(row.get("start_line") or 0), row["id"]))
        file_paths = self._file_paths()
        compact = [{
            "id": row["id"],
            "qualified_name": row.get("qualified_name"),
            "kind": row.get("kind"),
            "file_path": file_paths.get(row.get("file_id"))
            or (row.get("metadata") or {}).get("relative_path"),
            "shard_path": (row.get("metadata") or {}).get("shard_path"),
            "start_line": row.get("start_line"),
            "end_line": row.get("end_line"),
        } for row in rows]
        return self._envelope("symbol.lookup", name, params,
                              {**raw, "data": compact}, budget)

    # ------------------------------------------------------------------
    # Q2 symbol.callers / symbol.callees
    # ------------------------------------------------------------------
    def _neighbors(self, call: str, symbol: str, budget: dict | None) -> dict:
        params = {"symbol": symbol}
        if not symbol or not isinstance(symbol, str):
            return self._error(call, symbol or "", params, budget,
                               "INVALID_INPUT", "symbol must be a non-empty string")
        raw = self._q.get_callers(symbol) if call == "symbol.callers" \
            else self._q.get_callees(symbol)
        return self._envelope(call, symbol, params, raw, budget)

    def symbol_callers(self, symbol: str, budget: dict | None = None) -> dict:
        return self._neighbors("symbol.callers", symbol, budget)

    def symbol_callees(self, symbol: str, budget: dict | None = None) -> dict:
        return self._neighbors("symbol.callees", symbol, budget)

    # ------------------------------------------------------------------
    # Q3 symbol.references (resolution-target axis + owner axis; statuses
    # verbatim - unresolved/ambiguous rows are never hidden or rewritten)
    # ------------------------------------------------------------------
    def symbol_references(self, symbol: str, status: str | None = None,
                          budget: dict | None = None) -> dict:
        params = {"symbol": symbol, "status": status}
        if not symbol or not isinstance(symbol, str):
            return self._error("symbol.references", symbol or "", params, budget,
                               "INVALID_INPUT", "symbol must be a non-empty string")
        if status is not None and status not in ("resolved", "unresolved", "ambiguous"):
            return self._error("symbol.references", symbol, params, budget,
                               "INVALID_INPUT", f"unknown status filter {status!r}")
        to_symbol = self._q.get_raw_references(resolved_symbol_id=symbol, status=status)
        by_symbol = self._q.get_raw_references(owner_symbol_id=symbol, status=status)
        file_paths = self._file_paths()
        target_rows = to_symbol.get("data") or []
        owner_rows = by_symbol.get("data") or []
        merged: dict[str, dict] = {}
        for row in target_rows + owner_rows:
            row = dict(row)
            # Agent-facing enrichment from the same frozen DB (files table):
            # file_id hashes are not human-reportable; the path is required by
            # the frozen T03 task ("file and line").
            row["file_path"] = file_paths.get(row.get("file_id"))
            merged.setdefault(row["id"], row)
        rows = sorted(merged.values(),
                      key=lambda row: (str(row.get("file_id")),
                                       int(row.get("start_line") or 0),
                                       row["id"]))
        status_counts: dict[str, int] = {}
        for row in rows:
            status_counts[str(row.get("status"))] = \
                status_counts.get(str(row.get("status")), 0) + 1
        meta = {
            "resolved_to_symbol_count": sum(
                1 for row in rows if row.get("resolved_symbol_id") == symbol),
            "owned_by_symbol_count": sum(
                1 for row in rows if row.get("owner_symbol_id") == symbol),
            "status_counts": status_counts,
        }
        evidence = list(to_symbol.get("evidence") or []) + \
            list(by_symbol.get("evidence") or [])
        raw = {"query_id": to_symbol["query_id"],
               "graph_generation": to_symbol.get("graph_generation", 0),
               "data": rows, "evidence": evidence,
               "bundle_size": to_symbol.get("bundle_size", 0),
               "query_time_ms": 0.0}
        return self._envelope("symbol.references", symbol, params, raw, budget,
                              extra_meta=meta)

    def _file_paths(self) -> dict[str, str]:
        """file_id -> repo-relative path from the frozen files table (cached)."""
        if self._file_paths_cache is None:
            import sqlite3
            con = sqlite3.connect(self.database)
            con.row_factory = sqlite3.Row
            try:
                self._file_paths_cache = {
                    row["file_id"]: row["path"] for row in
                    con.execute("SELECT file_id, path FROM files")}
            finally:
                con.close()
        return self._file_paths_cache

    # ------------------------------------------------------------------
    # Q4 impact.frontier (shard-level only)
    # ------------------------------------------------------------------
    def impact_frontier(self, changed_shard_paths: list[str], threshold: int = 8,
                        budget: dict | None = None) -> dict:
        params = {"changed_shard_paths": list(changed_shard_paths),
                  "threshold": threshold}
        declared = _clamp(budget)
        applied = declared
        if not changed_shard_paths:
            return self._error("impact.frontier", "", params, budget,
                               "INVALID_INPUT", "changed_shard_paths must be non-empty")
        con = self._q.view.base.conn if hasattr(self._q.view.base, "conn") else None
        try:
            import sqlite3
            if con is None:
                con = sqlite3.connect(self.database)
                con.row_factory = sqlite3.Row
                own = True
            else:
                own = False
            path_by_id = {row["shard_id"]: row["path"]
                          for row in con.execute("SELECT shard_id, path FROM shards")}
            id_by_path = {path: sid for sid, path in path_by_id.items()}
            unknown = [p for p in changed_shard_paths if p not in id_by_path]
            if unknown:
                return self._error("impact.frontier", ",".join(changed_shard_paths),
                                   params, budget, "UNKNOWN_SHARD",
                                   f"unknown shard paths: {unknown}")
            changed_ids = {id_by_path[p] for p in changed_shard_paths}
            affected: dict[str, dict] = {}
            for row in con.execute("SELECT * FROM shard_edges"):
                src, dst = path_by_id.get(row["src_shard_id"]), path_by_id.get(row["dst_shard_id"])
                if dst in changed_shard_paths and src not in changed_shard_paths:
                    entry = affected.setdefault(src, {
                        "id": row["src_shard_id"], "shard_path": src,
                        "changed_shard_path": dst, "boundary_edge_ids": []})
                    entry["boundary_edge_ids"].append(row["edge_id"])
        finally:
            if own:
                con.close()
        # Deterministic budgeted listing of boundary edge ids: rows keep frozen
        # (shard_path) order and are filled first; the aggregate count is always
        # exact and never confused with the budgeted listing (contract B1/C3,
        # T04: 1031 boundary edges, <=50 ids listed per response budget).
        listed_cap = applied["max_edges"]
        listed_remaining = listed_cap
        rows = []
        evidence = []
        total_edge_ids = 0
        total_listed = 0
        for shard_path in sorted(affected):
            entry = affected[shard_path]
            entry["boundary_edge_ids"] = sorted(entry["boundary_edge_ids"])
            total_edge_ids += len(entry["boundary_edge_ids"])
            listed = entry["boundary_edge_ids"][:listed_remaining]
            listed_remaining -= len(listed)
            total_listed += len(listed)
            rows.append({
                "id": entry["id"], "shard_path": shard_path,
                "changed_shard_path": entry["changed_shard_path"],
                "boundary_edge_count": len(entry["boundary_edge_ids"]),
                "boundary_edge_ids": listed,
                "boundary_edge_ids_omitted": len(entry["boundary_edge_ids"]) - len(listed),
            })
            fact_id = entry["boundary_edge_ids"][0] if entry["boundary_edge_ids"] else ""
            evidence.append({
                "evidence_id": evidence_id(
                    "SHARD_RELATION", self.repository, entry["id"],
                    "DEPENDS_ON", id_by_path[entry["changed_shard_path"]], fact_id),
                "kind": "SHARD_RELATION",
                "source_id": entry["id"],
                "relation": "DEPENDS_ON",
                "target_id": id_by_path[entry["changed_shard_path"]],
                "repository": self.repository,
                "commit": self.commit,
                "generation": int(self._q.graph_generation),
                "provenance": "shard_edges_boundary_index",
                "confidence": 1.0,
                "source_path": shard_path,
                "source_range": None,
                "summary": (f"shard {shard_path} depends on changed shard "
                            f"{entry['changed_shard_path']} via "
                            f"{len(entry['boundary_edge_ids'])} boundary edges"),
                "metadata": {"boundary_edge_count": len(entry["boundary_edge_ids"]),
                             "direct": True},
            })
        size = len(rows)
        unlisted_edge_ids = total_edge_ids - total_listed
        meta = {"frontier_size": size, "changed_shard_paths": sorted(changed_shard_paths),
                "threshold": threshold,
                "wide_impact": size > threshold,
                "boundary_edges_total": total_edge_ids,
                "boundary_edge_ids_returned": total_listed,
                "boundary_edge_ids_omitted": unlisted_edge_ids,
                "note": ("shard-level conservative 1-hop frontier only; "
                         "no symbol-level impact is derivable from this call; "
                         "boundary edge ids are a deterministic budgeted listing, "
                         "the aggregate count is exact")}
        raw = {"query_id": self._deterministic_query_id("impact.frontier",
                                                        ",".join(sorted(changed_shard_paths))),
               "graph_generation": int(self._q.graph_generation),
               "data": rows, "evidence": evidence, "bundle_size": 0,
               "query_time_ms": 0.0}
        envelope = self._envelope("impact.frontier",
                                  ",".join(sorted(changed_shard_paths)), params,
                                  raw, budget, extra_meta=meta)
        if unlisted_edge_ids > 0:
            envelope["truncation"]["truncated"] = True
            envelope["truncation"]["omitted_counts"]["edges"] += unlisted_edge_ids
        return envelope

    def _deterministic_query_id(self, query_type: str, anchor: str) -> str:
        import hashlib
        seed = json.dumps([query_type, anchor, self._q.graph_generation],
                          separators=(",", ":"))
        return "Q-" + hashlib.sha256(seed.encode()).hexdigest()[:20]

    # ------------------------------------------------------------------
    # Q5 code.related (knowledge layer by anchor; OPT-T05-COMPRESSION:
    # optionally resolves the target symbols' code-database definition
    # evidence in the SAME call, removing the cross-database round trip)
    # ------------------------------------------------------------------
    def code_related(self, document: str, budget: dict | None = None) -> dict:
        params = {"document": document}
        if not document or not isinstance(document, str):
            return self._error("code.related", document or "", params, budget,
                               "INVALID_INPUT", "document must be a non-empty string")
        raw = self._q.get_document_targets(document)
        data_rows = list(raw.get("data") or [])
        evidence = list(raw.get("evidence") or [])
        knowledge_ids = [item["evidence_id"] for item in evidence]
        code_db_ids: list[str] = []
        unresolved: list[str] = []
        if self.code_database:
            code_q = self._code_graph()
            # iterate a snapshot: composite rows are appended to data_rows and
            # must NOT be re-processed (they resolve to themselves)
            for row in list(data_rows):
                qname = row.get("qualified_name")
                if not qname or row.get("kind") in ("File", "Document",
                                                    "Requirement"):
                    continue
                definition = code_q.get_definition(qname)
                code_row = definition.get("data")
                if not code_row:
                    unresolved.append(qname)
                    continue
                code_evidence = list(definition.get("evidence") or [])
                evidence.extend(code_evidence)
                code_db_ids.extend(item["evidence_id"] for item in code_evidence)
                data_rows.append({
                    "id": code_row["id"],
                    "qualified_name": code_row.get("qualified_name"),
                    "kind": code_row.get("kind"),
                    "file_path": (code_row.get("metadata") or {}).get("relative_path"),
                    "start_line": code_row.get("start_line"),
                    "end_line": code_row.get("end_line"),
                    "definition_of": qname,
                })
        meta = {
            "composite": bool(self.code_database),
            "code_database": self.code_database,
            "knowledge_db_evidence_ids": knowledge_ids,
            "code_db_evidence_ids": code_db_ids,
            "composite_unresolved": sorted(set(unresolved)),
        }
        combined_raw = {
            "query_id": raw["query_id"],
            "graph_generation": raw.get("graph_generation", 0),
            "data": data_rows,
            "evidence": evidence,
            "bundle_size": raw.get("bundle_size", 0),
            "query_time_ms": raw.get("query_time_ms", 0.0),
        }
        return self._envelope("code.related", document, params, combined_raw,
                              budget, extra_meta=meta)

    # ------------------------------------------------------------------
    # Q6 bundle.explain (shared budget pool, verified post-hoc)
    # ------------------------------------------------------------------
    def bundle_explain(self, symbol: str, budget: dict | None = None) -> dict:
        params = {"symbol": symbol}
        applied = _clamp(budget)
        declared_full = {**DEFAULT_BUDGET, **(budget or {})}
        if not symbol or not isinstance(symbol, str):
            return self._error("bundle.explain", symbol or "", params, budget,
                               "INVALID_INPUT", "symbol must be a non-empty string")
        raw = self._q.explain_symbol(
            symbol, max_evidence=applied["max_evidence"],
            max_symbols=applied["max_symbols"], max_edges=applied["max_edges"],
            max_sections=applied["max_sections"])
        bundle = raw.get("bundle") or {}
        bundle["related_entities"] = [_project_row(row)
                                      for row in bundle.get("related_entities", [])]
        evidence = _dedupe_evidence_projection(
            list(bundle.get("primary_evidence", [])
                 + bundle.get("supporting_evidence", [])),
            self.repository, self.commit)
        related = bundle.get("related_entities", [])
        # Honest omitted counts (contract C3/B2): the shared pool slices the
        # underlying candidate set, so the adapter deterministically recounts
        # the uncapped candidate facts and reports what did not fit.
        definition = self._q.get_definition(symbol)
        omitted = {"symbols": 0, "edges": 0, "raw_refs": 0, "sections": 0}
        anchor_row = definition.get("data") or {}
        if anchor_row.get("id"):
            n_callers = len(self._q.get_callers(anchor_row["id"]).get("data") or [])
            n_callees = len(self._q.get_callees(anchor_row["id"]).get("data") or [])
            n_refs = len(self._q.get_references(anchor_row["id"]).get("data") or [])
            n_docs = len(self._q.get_document_targets(anchor_row["id"]).get("data") or [])
            supporting = bundle.get("supporting_evidence", [])
            n_supporting_relations = len([e for e in supporting
                                          if e.get("kind") in ("CALL_RELATION",
                                                               "REFERENCE", "DEPENDENCY")])
            omitted["edges"] = max(0, (n_callers + n_callees + n_refs)
                                   - n_supporting_relations)
            omitted["symbols"] = max(0, (n_callers + n_callees + n_docs)
                                     - len(related))
        used = {"symbols": len(related), "edges": len(bundle.get("supporting_evidence", [])),
                "raw_refs": 0, "sections": len([e for e in related
                                                if e.get("kind") == "Document"]),
                "evidence": raw.get("returned_evidence_count", len(evidence))}
        # V1.2-NR2: empty bundles carry the same generic recovery guidance
        # as the shared envelope path (deterministic; non-empty unchanged).
        bundle_meta = {"bundle_profile": bundle.get("profile", "generic"),
                       "intent": bundle.get("intent", "explain_symbol")}
        if (not evidence and not related
                and not raw.get("returned_evidence_count", 0)):
            bundle_meta["empty_result_guidance"] = EMPTY_RESULT_GUIDANCE
        envelope = {
            "sqi_version": SQI_VERSION,
            "query_id": raw["query_id"],
            "query_type": "bundle.explain",
            "anchor": symbol,
            "params": params,
            "repository": self.repository,
            "commit": self.commit,
            "graph_generation": raw.get("graph_generation", 0),
            "data": bundle,
            "evidence": evidence,
            "returned_evidence_ids": raw.get("returned_evidence_ids", []),
            "returned_evidence_count": raw.get("returned_evidence_count", 0),
            "bundle_size": raw.get("bundle_size", 0),
            "budget": {"declared": {field: int(declared_full[field])
                                    for field in DEFAULT_BUDGET},
                       "applied": applied, "used": used},
            "truncation": {"truncated": any(value > 0 for value in omitted.values())
                           or bool(bundle.get("fallback_triggered") is False
                                   and bundle.get("suppressed_evidence_count", 0) > 0),
                           "omitted_counts": omitted,
                           "retry_same_call_will_not_expand": True},
            "source_verification_policy": SOURCE_VERIFICATION_POLICY,
            "result_meta": bundle_meta,
            "query_time_ms": raw.get("query_time_ms", 0.0),
        }
        size = len(json.dumps(envelope, ensure_ascii=False))
        if size > RESPONSE_BYTE_LIMIT:
            raise SQIError("RESPONSE_TOO_LARGE",
                           f"envelope is {size} bytes, limit {RESPONSE_BYTE_LIMIT}")
        ok, errors = validate_envelope(envelope, expected_commit=self.commit)
        if not ok:
            raise SQIError("ADAPTER_SELF_VALIDATION_FAILED", "; ".join(errors[:8]))
        return envelope

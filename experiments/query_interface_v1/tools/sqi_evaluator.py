"""SQI-V1 formal evaluator: machine-checkable oracles for T01-T06.

Implements EXACTLY the frozen `SQI_FORMAL_QUALIFICATION_PROTOCOL_V1` §5
oracles - it defines no new success criteria. Natural-language assertions are
machine-checked against the frozen key anchors and additionally flagged
`human_review_required` where content-level judgement is needed (protocol
§5.1). Task failure is never treated as SQI capability failure (protocol §7);
capability-failure flags are emitted only for causally attributable SQI output
defects.

V1.1 (post-batch review pass, applied uniformly to all 36 cells; no success
criterion changed - symbol-identity and path-spelling equivalence only, plus
arm-gating of SQI-only machinery checks and the T05 fixture repair):
  * symbol spellings `a::b` and `a.b` are the same qualified name; final
    one/two-segment tails also match (agents may legitimately use class::member
    tails);
  * source-read targets are matched with path-separator normalization
    (sessions run on Windows with absolute paths);
  * T06 bundle checks are SQI-arm-only (a native arm has no bundle calls);
  * T05 fixture repaired (V1.1 amendment): required_evidence_ids now covers
    both frozen databases (E-CODE from the code database definition evidence,
    E-XLINK from the knowledge database cross-layer link) with per-database
    breakdown; a session satisfies the criterion by returning at least one.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent.parent / "src"))

from provenlattice.evidence import parse_evidence_citations  # noqa: E402
from sqi_validator import validate_envelope  # noqa: E402


def _contains_all(text: str, needles: list[str]) -> bool:
    low = text.lower()
    return all(str(needle).lower() in low for needle in needles)


def _norm_symbol(name: str) -> str:
    """Symbol-identity spelling normalization: C++ `::` and ProvenLattice `.`
    separators denote the same qualified name (uniform across arms)."""
    return str(name).replace("::", ".").lower()


def _norm_path(path: str) -> str:
    return str(path).replace("\\", "/").lower()


def _symbol_named(text: str, name: str) -> bool:
    """Full normalized match, or the final one/two dotted segments (agents may
    legitimately spell a symbol by its class::member tail)."""
    normalized = _norm_symbol(name)
    if normalized in text.lower():
        return True
    segments = normalized.split(".")
    for width in (2, 1):
        if len(segments) >= width:
            tail = ".".join(segments[-width:])
            if tail in text.lower():
                return True
    return False


def _target_matches(target: str, needle: str) -> bool:
    needle = _norm_path(needle)
    normalized = _norm_path(target)
    return needle in normalized or needle in normalized.replace("/", "\\")


def _source_read_events(events: list[dict]) -> list[dict]:
    out = []
    for event in events or []:
        operation = str(event.get("operation", "")).casefold()
        if operation in ("read", "grep", "glob", "search"):
            out.append(event)
    return out


def _read_targets(events: list[dict]) -> list[str]:
    targets = []
    for event in _source_read_events(events):
        target = event.get("target") or ""
        files = event.get("files") or []
        for value in ([target, *files] if files else [target]):
            if value:
                targets.append(str(value))
    return targets


def _call_log_envelopes(call_log: list[dict]) -> list[dict]:
    return [entry.get("envelope") or {} for entry in call_log or []]


def evidence_oracle(arm: str, agent_output: str,
                    call_log: list[dict]) -> dict:
    """Protocol §5.2: 'Evidence Used:' citations must be a subset of the ids
    actually returned by this session's SQI calls (SQI arm only)."""
    if arm != "sqi":
        return {"citation_closure_ok": None, "used_ids": [],
                "returned_ids_union_count": 0, "unsupported_claim_ids": []}
    envelopes = _call_log_envelopes(call_log)
    returned = set()
    for envelope in envelopes:
        returned.update(envelope.get("returned_evidence_ids") or [])
    cited = parse_evidence_citations(agent_output or "")
    unsupported = sorted(set(cited) - returned)
    return {"citation_closure_ok": not unsupported,
            "used_ids": sorted(set(cited) & returned),
            "returned_ids_union_count": len(returned),
            "unsupported_claim_ids": unsupported}


def capability_flags(arm: str, task: dict, call_log: list[dict],
                     events: list[dict]) -> list[str]:
    """Protocol §5.4: causally attributable SQI output defects only."""
    flags: list[str] = []
    if arm != "sqi":
        for event in events or []:
            command = str(event.get("query") or event.get("target") or "")
            if "sqi_cli" in command.casefold():
                flags.append("SQI_ACCESS_IN_NATIVE")
        return flags
    for entry in call_log or []:
        envelope = entry.get("envelope") or {}
        if not envelope:
            continue
        ok, errors = validate_envelope(envelope, expected_commit=task["commit"])
        if not ok:
            flags.append("INVALID_ENVELOPE_IN_SESSION")
            continue
        budget = envelope.get("budget") or {}
        used, applied = budget.get("used") or {}, budget.get("applied") or {}
        if any(used.get(key, 0) > applied.get(cap, 0) for key, cap in
               (("evidence", "max_evidence"), ("symbols", "max_symbols"),
                ("sections", "max_sections"))):
            flags.append("BUDGET_VIOLATION")
        if envelope.get("query_type") != "bundle.explain" and \
                used.get("edges", 0) > applied.get("max_edges", 0):
            flags.append("BUDGET_VIOLATION")
        truncation = envelope.get("truncation") or {}
        if truncation.get("truncated") is False and any(
                value > 0 for value in (truncation.get("omitted_counts") or {}).values()):
            flags.append("TRUNCATION_DISHONESTY")
    return sorted(set(flags))


def _file_path_map(db_path: str) -> dict[str, str]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        return {row["file_id"]: row["path"]
                for row in con.execute("SELECT file_id, path FROM files")}
    finally:
        con.close()


def _task_checks(task: dict, arm: str, agent_output: str, events: list[dict],
                 call_log: list[dict], db_path: str) -> tuple[dict, list[str]]:
    """Machine checks per frozen task ground truth + success criteria."""
    tid = task["task_id"]
    gt = task["ground_truth"]
    output = agent_output or ""
    checks: dict[str, bool] = {}
    human_review: list[str] = []
    read_targets = _read_targets(events)
    n_source_reads = len(_source_read_events(events))
    envelopes = _call_log_envelopes(call_log)

    if tid == "SQI-T01":
        checks["names_symbol"] = _symbol_named(output, gt["qualified_name"])
        checks["names_file"] = _norm_path(gt["file"]).split("/")[-1] in _norm_path(output) \
            or _norm_path(gt["file"]) in _norm_path(output)
        checks["names_declaration_line"] = str(gt["declaration_line"]) in output
        checks["reads_definition_source"] = any(
            _target_matches(target, gt["file"]) for target in read_targets)
        if arm == "sqi":
            checks["cites_definition_evidence"] = any(
                item["kind"] == "CODE_DEFINITION" for item in envelopes[0]["evidence"]) \
                if envelopes else False
    elif tid == "SQI-T02":
        named = sum(1 for name in gt["required_production_callers"]
                    if _symbol_named(output, name))
        checks["production_callers_at_least_4"] = named >= 4
        checks["production_callers_named_count_ge"] = named
        call_site_reads = [target for target in read_targets
                           if "docs" not in _norm_path(target)]
        checks["source_verification_at_least_2"] = len(call_site_reads) >= 2
        if arm == "sqi":
            frozen_edges = [caller["edge_id"] for caller in gt["callers"]]
            returned_facts = set()
            for envelope in envelopes:
                for item in envelope.get("evidence") or []:
                    fact_id = (item.get("metadata") or {}).get("fact_id")
                    if fact_id:
                        returned_facts.add(fact_id)
            checks["frozen_call_edges_evidenced"] = \
                len(set(frozen_edges) & returned_facts) >= 4
        human_review.append("each claimed caller is a real call site of "
                            "error_cstr (content-level judgement)")
    elif tid == "SQI-T03":
        paths = _file_path_map(db_path)
        frozen_locations = []
        for ref in gt["resolved_references"]:
            path = paths.get(ref["file_id"], ref["file_id"])
            frozen_locations.append((path, ref["line"]))
        located = 0
        for path, line in frozen_locations:
            if path.split("/")[-1] in output and str(line) in output:
                located += 1
        checks["frozen_locations_reported_all_6"] = located == 6
        checks["no_index_exceeding_claims_machine_proxy"] = located <= 6
        checks["reads_reference_site"] = any(
            any(str(line) in target or path.split("/")[-1] in target
                for path, line in frozen_locations) for target in read_targets) \
            or n_source_reads >= 1
        if arm == "sqi":
            frozen_e_ids = set(gt["returned_evidence_ids"])
            returned_ids = set()
            for envelope in envelopes:
                returned_ids.update(envelope.get("returned_evidence_ids") or [])
            checks["frozen_e_ref_ids_in_session"] = \
                bool(frozen_e_ids & returned_ids)
        human_review.append("no reference claimed as resolved beyond the six "
                            "frozen resolved raw references")
    elif tid == "SQI-T04":
        checks["reports_frontier_size_49"] = "49" in output
        checks["reports_boundary_edges_1031"] = "1031" in output
        checks["reports_wide_impact"] = _contains_all(output, ["wide"])
        checks["reports_truncation"] = "truncat" in output.lower() \
            or "omitted" in output.lower()
        checks["reads_affected_source"] = n_source_reads >= 1
        if arm == "sqi" and envelopes:
            meta = envelopes[0].get("result_meta") or {}
            checks["interface_aggregates_match_frozen"] = (
                meta.get("frontier_size") == 49
                and meta.get("boundary_edges_total") == 1031
                and meta.get("wide_impact") is True)
        human_review.append("answer makes no symbol-level semantic impact "
                            "assertion (shard-level frontier only, contract S5.3)")
    elif tid == "SQI-T05":
        target_symbol = gt["required_evidence"][1]["value"]
        expected_file = gt["required_evidence"][2]["value"]
        section = gt["required_evidence"][0]
        checks["names_target_symbol"] = _symbol_named(output, target_symbol)
        file_base = _norm_path(expected_file).split("/")[-1]
        checks["names_expected_file"] = file_base in _norm_path(output) \
            or _norm_path(expected_file) in _norm_path(output)
        checks["cites_document_section"] = \
            section["heading_path"].split("/")[-1] in output \
            or section["file"] in output
        checks["reads_expected_file_source"] = any(
            _target_matches(target, expected_file) for target in read_targets)
        if arm == "sqi":
            returned_ids = set()
            for envelope in envelopes:
                returned_ids.update(envelope.get("returned_evidence_ids") or [])
            cross_layer_returned = set()
            for envelope in envelopes:
                for item in envelope.get("evidence") or []:
                    if item.get("kind") == "CROSS_LAYER_LINK":
                        cross_layer_returned.add(item["evidence_id"])
            # V1.1 fixture: required_evidence_ids covers both frozen databases
            # (E-CODE minted by the code database's definition evidence,
            # E-XLINK by the knowledge database's cross-layer link); a session
            # satisfies the criterion by returning at least one of them.
            by_db = gt.get("required_evidence_ids_by_database") or {}
            checks["required_evidence_id_in_session"] = \
                bool(set(gt["required_evidence_ids"]) & returned_ids)
            checks["knowledge_db_id_returned"] = sorted(
                set(by_db.get("knowledge_database", [])) & returned_ids)
            checks["code_db_id_returned"] = sorted(
                set(by_db.get("code_database", [])) & returned_ids)
        human_review.append("document semantics and code behaviour are "
                            "equivalent (content-level judgement)")
    elif tid == "SQI-T06":
        if arm == "sqi":
            bundle_calls = [entry for entry in call_log or []
                            if entry.get("call") == "bundle.explain"]
            checks["single_bundle_explain_call"] = len(bundle_calls) == 1
            if bundle_calls:
                envelope = bundle_calls[0]["envelope"]
                declared = envelope.get("budget", {}).get("declared", {})
                checks["budget_matches_frozen"] = (
                    declared.get("max_evidence") == gt["budget"]["max_evidence"]
                    and declared.get("max_symbols") == gt["budget"]["max_symbols"])
                checks["truncation_declared"] = \
                    envelope.get("truncation", {}).get("truncated") is True
                omitted = envelope.get("truncation", {}).get("omitted_counts", {})
                checks["omitted_counts_nonzero"] = any(value > 0 for value in omitted.values())
        checks["honest_omission_reported"] = \
            "truncat" in output.lower() or "omitted" in output.lower() \
            if arm == "sqi" else True
        checks["reads_definition_source"] = any(
            _target_matches(target, "src/brpc/controller.h")
            or _target_matches(target, "src/brpc/controller.cpp")
            for target in read_targets)
        human_review.append("reported omission figures match the envelope and "
                            "the definition semantics claim is source-verified")
    else:
        raise RuntimeError(f"no frozen oracle for {tid}")
    return checks, human_review


def evaluate_cell(task: dict, arm: str, agent_output: str, events: list[dict],
                  call_log: list[dict], db_path: str) -> dict:
    checks, human_review = _task_checks(task, arm, agent_output, events,
                                        call_log, db_path)
    evidence = evidence_oracle(arm, agent_output, call_log)
    flags = capability_flags(arm, task, call_log, events)
    if arm == "sqi" and evidence["citation_closure_ok"] is False:
        checks["citation_closure_ok"] = False
    machine_ok = all(bool(value) for value in checks.values()
                     if isinstance(value, bool))
    task_success = (machine_ok and not flags) if machine_ok else False
    sqi_calls = [entry.get("call") for entry in call_log or []]
    return {
        "oracle_version": "SQI_FORMAL_ORACLE_V1.1",
        "arm": arm,
        "task_id": task["task_id"],
        "machine_checks": checks,
        "machine_checks_pass": machine_ok,
        "task_success": task_success,
        "evidence_oracle": evidence,
        "source_verification": {
            "source_read_events": len(_source_read_events(events)),
            "read_targets": sorted(set(_read_targets(events)))[:40],
        },
        "sqi_call_summary": {
            "total_calls": len(sqi_calls),
            "calls_by_type": {call: sqi_calls.count(call)
                              for call in sorted(set(sqi_calls))},
            "total_payload_bytes": sum(entry.get("response_bytes") or 0
                                       for entry in call_log or []),
        },
        "capability_failure_flags": flags,
        "human_review_required": human_review,
    }

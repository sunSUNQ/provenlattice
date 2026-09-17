"""SQI-V1 envelope validator.

Structural validation runs against schema/sqi-envelope-v1.json (a frozen
JSON-Schema subset). Semantic rules C1-C4 of the frozen contract are enforced
here in code so that budget, truncation and provenance are machine-checkable,
not documentation-only:

  C1  fact<->evidence binding: every data fact is covered by returned evidence
      and every returned evidence id exists in the evidence list.
  C2  evidence id format + uniqueness (deterministic derivation is provided by
      the frozen provenlattice.evidence.evidence_id and additionally asserted
      by the runner's double-execution determinism check).
  C3  truncation honesty: truncated=false <=> all omitted_counts are zero.
  C4  schema validity is a precondition; the runner records INVALID_CALL
      otherwise.

Budget compliance (declared <= hard caps, applied == clamp(declared),
used <= applied) is checked here as well.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "sqi-envelope-v1.json"

HARD_CAPS = {"max_evidence": 50, "max_symbols": 20, "max_edges": 50, "max_sections": 10}
BUDGET_FIELDS = ("max_evidence", "max_symbols", "max_edges", "max_sections")
EVIDENCE_ID_RE = re.compile(r"^E-(CODE|CALL|REF|DEP|SHARD|DOC|XLINK)-[0-9a-f]{24}$")
QUERY_TYPES = {"symbol.lookup", "symbol.callers", "symbol.callees",
               "symbol.references", "impact.frontier", "code.related",
               "bundle.explain"}


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def schema_errors(instance: object, schema: dict, root: dict | None = None,
                  path: str = "$") -> list[str]:
    """Minimal JSON-Schema-subset validator (frozen constructs only)."""
    root = root or schema
    errors: list[str] = []
    if "$ref" in schema:
        target = root
        for part in schema["$ref"][2:].split("/"):
            target = target[part]
        return schema_errors(instance, target, root, path)
    if "allOf" in schema:
        for sub in schema["allOf"]:
            errors.extend(schema_errors(instance, sub, root, path))
    if "oneOf" in schema:
        valid = sum(1 for sub in schema["oneOf"]
                    if not schema_errors(instance, sub, root, path))
        if valid != 1:
            errors.append(f"{path}: oneOf matched {valid} branches, expected 1")
            return errors
    if "if" in schema:
        met = not schema_errors(instance, schema["if"], root, path)
        branch = schema.get("then") if met else schema.get("else")
        if branch:
            errors.extend(schema_errors(instance, branch, root, path))
    expected = schema.get("type")
    if expected is not None:
        type_map = {"object": dict, "array": list, "string": str,
                    "integer": int, "number": (int, float), "boolean": bool,
                    "null": type(None)}
        allowed = (type_map[expected] if isinstance(expected, str)
                   else tuple(type_map[t] for t in expected))
        if isinstance(expected, str) and expected in ("integer",) and isinstance(instance, bool):
            errors.append(f"{path}: expected integer, got boolean")
            return errors
        if not isinstance(instance, allowed) or (
                isinstance(instance, bool) and bool not in (
                    allowed if isinstance(allowed, tuple) else (allowed,))):
            errors.append(f"{path}: expected type {expected}, got {type(instance).__name__}")
            return errors
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value not in enum: {instance!r}")
    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: string does not match pattern {schema['pattern']!r}")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: string shorter than minLength")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: value below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: value above maximum {schema['maximum']}")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                errors.extend(schema_errors(value, properties[key], root, f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: additional property {key!r} not allowed")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than minItems")
        if "items" in schema:
            for index, item in enumerate(instance):
                errors.extend(schema_errors(item, schema["items"], root, f"{path}[{index}]"))
    return errors


def _clamp_budget(declared: dict) -> dict:
    return {field: max(0, min(int(declared.get(field, 0)), HARD_CAPS[field]))
            for field in BUDGET_FIELDS}


def semantic_errors(envelope: dict, expected_commit: str | None = None) -> list[str]:
    """C1-C4 + budget + provenance semantic checks on a structurally valid
    envelope (V1.2: per-evidence repository/commit and the session-level
    source_verification_policy are optional; when present they must be
    consistent with the header / frozen constant)."""
    errors: list[str] = []
    if envelope.get("query_type") not in QUERY_TYPES:
        errors.append(f"C4: unknown query_type {envelope.get('query_type')!r}")

    # provenance binding: the envelope commit must equal the frozen task/DB commit
    if expected_commit is not None and envelope.get("commit") != expected_commit:
        errors.append("provenance: commit mismatch against frozen expected commit")

    evidence = envelope.get("evidence") or []
    ids = envelope.get("returned_evidence_ids") or []
    id_list = envelope.get("evidence") and [item["evidence_id"] for item in evidence] or []
    # C1a: every returned evidence id must exist in the evidence list
    for eid in ids:
        if eid not in id_list:
            errors.append(f"C1: returned_evidence_ids contains unknown id {eid}")
    if len(set(id_list)) != len(id_list):
        errors.append("C2: duplicate evidence ids in evidence list")
    # C1b: every fact row must be covered by at least one evidence entry
    data = envelope.get("data")
    if isinstance(data, list):
        covered = set()
        for item in evidence:
            covered.add(item.get("target_id"))
            covered.add(item.get("source_id"))
            covered.add((item.get("metadata") or {}).get("fact_id"))
        for row in data:
            row_id = row.get("id") if isinstance(row, dict) else None
            if row_id and row_id not in covered:
                errors.append(f"C1: data row {row_id[:40]} has no covering evidence")
    # C1c: counts consistency
    if envelope.get("returned_evidence_count") != len(ids):
        errors.append("C1: returned_evidence_count != len(returned_evidence_ids)")
    if len(ids) != len(evidence):
        errors.append("C1: returned_evidence_ids length != evidence length")

    # C3: truncation honesty
    truncation = envelope.get("truncation") or {}
    omitted = truncation.get("omitted_counts") or {}
    any_omitted = any(value > 0 for value in omitted.values())
    if truncation.get("truncated") and not any_omitted:
        errors.append("C3: truncated=true but all omitted_counts are zero")
    if not truncation.get("truncated") and any_omitted:
        errors.append("C3: truncated=false but omitted_counts are non-zero")

    # budget compliance
    budget = envelope.get("budget") or {}
    declared, applied, used = budget.get("declared") or {}, budget.get("applied") or {}, budget.get("used") or {}
    for field in BUDGET_FIELDS:
        if field in declared and declared[field] > HARD_CAPS[field]:
            errors.append(f"budget: declared {field} above hard cap")
    expected_applied = _clamp_budget(declared)
    if applied and {k: applied.get(k) for k in BUDGET_FIELDS} != expected_applied:
        errors.append("budget: applied != clamp(declared)")
    for field, cap_field in (("evidence", "max_evidence"), ("symbols", "max_symbols"),
                             ("raw_refs", "max_edges"),
                             ("sections", "max_sections")):
        if used and applied and used.get(field, 0) > applied.get(cap_field, 0):
            errors.append(f"budget: used.{field}={used.get(field)} exceeds applied.{cap_field}")
    # edges: bound per-call for edge-shaped calls; for bundle.explain the shared
    # pool bounds TOTAL evidence (<= max_evidence), so the supporting-edge
    # sub-count is informational and not independently capped.
    if used and applied and envelope.get("query_type") != "bundle.explain":
        if used.get("edges", 0) > applied.get("max_edges", 0):
            errors.append(f"budget: used.edges={used.get('edges')} exceeds applied.max_edges")
    if used and envelope.get("returned_evidence_count") is not None:
        if used.get("evidence", 0) != envelope.get("returned_evidence_count"):
            errors.append("budget: used.evidence != returned_evidence_count")

    # provenance
    if not str(envelope.get("repository", "")).startswith("repo:"):
        errors.append("provenance: repository missing/malformed")
    if not re.match(r"^[0-9a-f]{40}$", str(envelope.get("commit", ""))):
        errors.append("provenance: commit is not a 40-hex frozen sha")

    # C2 format on every evidence id + V1.2 header-consistency when present
    for item in evidence:
        if not EVIDENCE_ID_RE.match(item.get("evidence_id", "")):
            errors.append(f"C2: malformed evidence id {item.get('evidence_id')!r}")
            break
        if "repository" in item and item["repository"] != envelope.get("repository"):
            errors.append("V1.2: evidence repository differs from envelope header")
            break
        if "commit" in item and item["commit"] != envelope.get("commit"):
            errors.append("V1.2: evidence commit differs from envelope header")
            break

    # S8: when a policy block is present it must be complete (V1.2 allows the
    # session-level form: the bridge emits it once per session, so a non-first
    # envelope may omit it; the session check lives in the evaluator)
    policy = envelope.get("source_verification_policy")
    if policy is not None:
        required_classes = {"definition_semantics", "call_site_semantics",
                            "reference_purpose", "downstream_impact",
                            "document_equivalence"}
        if not required_classes.issubset(set(policy.get("requires_source_verification") or [])):
            errors.append("S8: source_verification_policy incomplete")
    return errors


def session_policy_errors(call_log: list[dict]) -> list[str]:
    """V1.2 S8 session-level check: the FIRST envelope of a session must carry
    the complete frozen source_verification_policy."""
    errors: list[str] = []
    first = None
    for entry in call_log or []:
        envelope = entry.get("envelope") or {}
        if envelope.get("error") or not envelope.get("query_type"):
            continue
        first = envelope
        break
    if first is None:
        return errors
    policy = first.get("source_verification_policy")
    required_classes = {"definition_semantics", "call_site_semantics",
                        "reference_purpose", "downstream_impact",
                        "document_equivalence"}
    if not policy or not required_classes.issubset(
            set(policy.get("requires_source_verification") or [])):
        errors.append("S8: session first envelope missing incomplete "
                      "source_verification_policy")
    return errors


def validate_envelope(envelope: dict, expected_commit: str | None = None) -> tuple[bool, list[str]]:
    """Full structural + semantic validation of an SQI envelope."""
    schema = load_schema()
    errors = schema_errors(envelope, schema)
    if not errors:
        errors = semantic_errors(envelope, expected_commit=expected_commit)
    return (not errors), errors

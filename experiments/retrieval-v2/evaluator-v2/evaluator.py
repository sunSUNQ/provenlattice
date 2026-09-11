from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

EVIDENCE_TOKEN = re.compile(r"\bE-(?:CODE|CALL|REF|DEP|SHARD|DOC|XLINK)-[0-9a-f]{24}\b", re.I)
EVIDENCE_LIKE = re.compile(r"\bE-[A-Z][A-Z0-9_-]*-[A-Za-z0-9_-]+\b")


def canonicalize_path(value: str, repo_root: str | Path | None = None) -> str:
    value = unquote(str(value).strip()).replace("\\", "/")
    value = value.split("#", 1)[0].split("?", 1)[0]
    value = re.sub(r"^file://", "", value, flags=re.I)
    if re.match(r"^[A-Za-z]:/", value):
        root = str(repo_root or "").replace("\\", "/").rstrip("/")
        if root and value.casefold().startswith(root.casefold() + "/"):
            value = value[len(root) + 1:]
        else:
            value = value[3:]
    value = re.sub(r"^/+(?:[A-Za-z]:/)?", "", value)
    parts = []
    for part in value.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts).casefold()


def canonicalize_document_anchor(value: str, repo_root: str | Path | None = None) -> str:
    raw = unquote(str(value).strip()).replace("\\", "/")
    if "#" not in raw:
        return canonicalize_path(raw, repo_root)
    path, fragment = raw.split("#", 1)
    fragment = fragment.strip().casefold()
    fragment = re.sub(r"[^\w\s-]", "", fragment, flags=re.UNICODE)
    fragment = re.sub(r"[\s_]+", "-", fragment)
    return f"{canonicalize_path(path, repo_root)}#{fragment}"


def citation_tokens(text: str) -> list[str]:
    return list(dict.fromkeys(item.upper() for item in EVIDENCE_LIKE.findall(text)))


def _refs(group: dict) -> list[dict]:
    return list(group.get("evidence") or group.get("refs") or [])


def _ref_matches(ref: dict, output: str, repo_root: str | Path | None) -> bool:
    evidence_id = str(ref.get("evidence_id") or "").upper()
    used_ids = {item.upper() for item in ref.get("used_ids", [])}
    if evidence_id and evidence_id in used_ids:
        return True
    for marker in ref.get("match", ref.get("terms", [])):
        if ref.get("kind") in {"path", "document", "document_section"}:
            marker_value = (canonicalize_path(str(marker), repo_root)
                            if "/" in str(marker) or "\\" in str(marker)
                            else str(marker).casefold())
            output_value = output.replace("\\", "/").casefold()
            if marker_value in output_value:
                return True
        elif str(marker).casefold() in output.casefold():
            return True
    return False


def _group_satisfied(group: dict, output: str, used: set[str], repo_root) -> bool:
    refs = []
    for ref in _refs(group):
        item = dict(ref)
        item["used_ids"] = used
        refs.append(_ref_matches(item, output, repo_root))
    mode = str(group.get("mode", "ANY_OF")).upper()
    if mode == "ALL_OF":
        return bool(refs) and all(refs)
    if mode == "OPTIONAL":
        return True
    return any(refs)


def evaluate_v2(task: dict, agent_output: str, events: list[dict], *, repo_root=None,
                known_evidence_ids: set[str] | None = None) -> dict:
    returned = {str(item).upper() for event in events for item in event.get("evidence_ids", [])}
    viewed = {str(item).upper() for event in events for item in event.get("viewed_evidence_ids", [])}
    cited = {item.upper() for item in citation_tokens(agent_output)}
    used = cited | {str(item).upper() for event in events for item in event.get("used_evidence_ids", [])}
    exact = {str(item).upper() for item in task.get("required_evidence_ids", [])}
    alternatives = {str(item).upper() for item in task.get("acceptable_alternative_ids", [])}
    supporting = {str(item).upper() for item in task.get("supporting_evidence_ids", [])}
    invalid = {str(item).upper() for item in task.get("invalid_evidence_ids", [])}
    known = {str(item).upper() for item in (known_evidence_ids or set())} | returned | exact | alternatives | supporting
    classifications = {}
    for item in sorted(used):
        if item in invalid:
            category = "INVALID_EVIDENCE"
        elif item in returned and item in exact:
            category = "SUPPORTED_EXACT"
        elif item in returned and item in alternatives:
            category = "SUPPORTED_ALTERNATIVE"
        elif item in returned and item in supporting:
            category = "SUPPORTED_CONTEXTUAL"
        elif item in returned:
            category = "SUPPORTED_CONTEXTUAL"
        elif item in known:
            category = "INVALID_EVIDENCE"  # known fact, but not exposed by this bundle
        else:
            category = "UNKNOWN_EVIDENCE"
        classifications[item] = category

    concepts = []
    for concept in task.get("required_concepts", []):
        groups = concept.get("required_evidence_groups", concept.get("groups", []))
        satisfied = all(_group_satisfied(group, agent_output, used, repo_root) for group in groups)
        concepts.append({"concept_id": concept.get("concept_id", concept.get("id")),
                         "satisfied": satisfied})
    required = [item for item in concepts]
    concept_recall = sum(item["satisfied"] for item in required) / len(required) if required else None
    exact_hits = sorted(used & returned & exact)
    wrong_paths = []
    expected_paths = {canonicalize_path(item, repo_root) for item in task.get("expected_paths", [])}
    path_pattern = r"(?:[A-Za-z]:[\\/]|(?:src|test|docs?|include)[\\/]|\.\.\.?[\\/])[^\s`\"']+\.(?:hpp|cpp|cc|md|h|c)(?:#[^\s`\"']+)?"
    for match in re.findall(path_pattern, agent_output):
        canonical = canonicalize_path(match, repo_root)
        base = canonical.split("#", 1)[0]
        exists = bool(repo_root and (Path(repo_root) / base).is_file())
        suffix_match = any(path.endswith("/" + base) for path in expected_paths) if base else False
        if canonical and ((repo_root and not exists and not suffix_match) or
                          (not repo_root and expected_paths and not any(
                              canonical == path or canonical.startswith(path + "#") for path in expected_paths
                          ) and not suffix_match)):
            wrong_paths.append(match.rstrip(".,;:)").replace("\\", "/"))
    return {
        "task_success": all(item["satisfied"] for item in concepts)
                       and not any(value in {"UNKNOWN_EVIDENCE", "INVALID_EVIDENCE"}
                                   for value in classifications.values())
                       and not wrong_paths,
        "concept_recall": concept_recall,
        "concepts": concepts,
        "exact_evidence_recall": (len(exact_hits) / len(exact) if exact else None),
        "exact_evidence_hits": exact_hits,
        "exact_evidence_misses": sorted(exact - set(exact_hits)),
        "evidence_precision": (len([item for item in used if classifications[item].startswith("SUPPORTED")])
                                / len(used) if used else None),
        "returned_evidence_ids": sorted(returned),
        "exposed_evidence_ids": sorted(viewed),
        "used_evidence_ids": sorted(used),
        "citation_classifications": classifications,
        "unsupported_citation_count": sum(value == "UNKNOWN_EVIDENCE" for value in classifications.values()),
        "invalid_evidence_count": sum(value == "INVALID_EVIDENCE" for value in classifications.values()),
        "wrong_path_count": len(set(wrong_paths)), "wrong_paths": sorted(set(wrong_paths)),
        "evaluator_version": "r2.2-groundtruth-v2",
    }

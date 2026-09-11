from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from provenlattice.evidence import parse_evidence_citations

from .models import TaskDefinition, ToolEvent


def _variants(value: str) -> set[str]:
    return {value, value.replace("::", "."), value.replace(".", "::")}


def _section_values(task: TaskDefinition, evidence: dict[str, Any]) -> set[str]:
    values = {evidence.get("value", "")}
    values.update({evidence.get("heading_path", ""), evidence.get("file", "")})
    values.update(task.expected_documents)
    return {value for value in values if value}


def evaluate(task: TaskDefinition, agent_output: str, events: list[ToolEvent], metrics: dict) -> dict:
    output = agent_output.casefold()
    required = task.ground_truth.get("required_evidence", [])
    optional = task.ground_truth.get("optional_evidence", [])
    distractors = task.ground_truth.get("distractor", [])
    hits: list[dict] = []
    misses: list[dict] = []
    for evidence in required:
        values = (_section_values(task, evidence) if evidence.get("type") == "document_section"
                  else _variants(str(evidence.get("value", ""))))
        if any(value.casefold() in output for value in values):
            hits.append(evidence)
        else:
            misses.append(evidence)
    mentioned = []
    for evidence in [*required, *optional, *distractors]:
        values = (_section_values(task, evidence) if evidence.get("type") == "document_section"
                  else _variants(str(evidence.get("value", ""))))
        if any(value.casefold() in output for value in values):
            mentioned.append(evidence)
    correct_mentioned = [evidence for evidence in mentioned if evidence not in distractors]
    wrong_paths = [path for path in re.findall(r"(?:src|test|docs?)/[^\s`\"']+", agent_output)
                   if path.rstrip(").,;:") not in set(task.expected_files + task.expected_documents)]
    used_edges = {evidence_id for event in events for evidence_id in event.used_evidence_ids}
    returned_edges = {evidence_id for event in events for evidence_id in event.evidence_ids}
    expected_edges = {item.get("edge_id") for item in task.expected_relationships}
    useful_edges = used_edges & expected_edges
    evaluation = {
        "task_success": not misses and not wrong_paths,
        "required_evidence_recall": len(hits) / len(required) if required else None,
        "evidence_precision": len(correct_mentioned) / len(mentioned) if mentioned else None,
        "required_evidence_hits": hits, "required_evidence_misses": misses,
        "mentioned_evidence": mentioned, "wrong_evidence_count": len([e for e in mentioned if e in distractors]),
        "wrong_path_count": len(wrong_paths), "wrong_paths": wrong_paths,
        "hallucinated_symbol_count": None, "hallucinated_relation_count": None,
        "graph_evidence_hit_rate": (len(useful_edges) / len(returned_edges)
                                     if returned_edges else None),
        "cross_layer_edge_utilization": (len(useful_edges) / len(returned_edges)
                                          if returned_edges else None),
        "evaluator_version": "r1-deterministic-v1",
    }
    return evaluation


def evaluate_r2(task: TaskDefinition, agent_output: str, events: list[ToolEvent], metrics: dict,
                *, arm: str, repo_path: str | None = None) -> dict:
    required_by_arm = task.ground_truth.get("required_evidence_ids_by_arm") or {}
    required_ids = set(required_by_arm.get(arm, task.ground_truth.get("required_evidence_ids") or []))
    optional_ids = set(task.ground_truth.get("optional_evidence_ids") or [])
    distractor_ids = set(task.ground_truth.get("distractor_evidence_ids") or [])
    returned = {item for event in events for item in event.evidence_ids}
    viewed = {item for event in events for item in event.viewed_evidence_ids}
    cited = set(parse_evidence_citations(agent_output))
    used = cited | {item for event in events for item in event.used_evidence_ids}
    unsupported_ids = used - returned
    wrong_ids = (used & distractor_ids) | unsupported_ids
    output = agent_output.casefold()
    semantic_required = task.ground_truth.get("required_evidence", [])
    semantic_hits = []
    for evidence in semantic_required:
        values = (_section_values(task, evidence) if evidence.get("type") == "document_section"
                  else _variants(str(evidence.get("value", ""))))
        if any(value.casefold() in output for value in values):
            semantic_hits.append(evidence)
    semantic_missing = [item for item in semantic_required if item not in semantic_hits]
    if arm == "native":
        hits = semantic_hits
        recall = len(hits) / len(semantic_required) if semantic_required else None
        precision = 1.0 if hits else None
        missing = semantic_missing
    else:
        hits = sorted(used & required_ids)
        missing = sorted(required_ids - used)
        recall = len(hits) / len(required_ids) if required_ids else None
        correct_used = used & (required_ids | optional_ids)
        precision = len(correct_used) / len(used) if used else 0.0
    wrong_paths = []
    if repo_path:
        root = Path(repo_path)
        for value in re.findall(r"(?:src|test|docs?)/[^\s\"']+", agent_output):
            normalized = re.sub(r":\d+(?:-\d+)?$", "", value.rstrip(").,;:"))
            if "{" in normalized or not (root / normalized).is_file():
                wrong_paths.append(value.rstrip(").,;:"))
    usage_rate = len(used & returned) / len(returned) if returned else None
    return {
        "task_success": not missing and not semantic_missing and not wrong_ids and not wrong_paths,
        "required_evidence_recall": recall, "evidence_precision": precision,
        "required_evidence_hits": hits, "required_evidence_misses": missing,
        "returned_evidence_ids": sorted(returned), "viewed_evidence_ids": sorted(viewed),
        "used_evidence_ids": sorted(used), "evidence_usage_rate": usage_rate,
        "returned_but_unused_evidence": sorted(returned - used),
        "returned_but_unused_count": len(returned - used),
        "wrong_evidence_usage": sorted(wrong_ids), "wrong_evidence_count": len(wrong_ids),
        "unsupported_claim_count": len(unsupported_ids),
        "semantic_required_evidence_recall": (
            len(semantic_hits) / len(semantic_required) if semantic_required else None),
        "semantic_required_evidence_misses": semantic_missing,
        "wrong_path_count": len(set(wrong_paths)), "wrong_paths": sorted(set(wrong_paths)),
        "hallucinated_symbol_count": None, "hallucinated_relation_count": None,
        "evaluator_version": "r2-evidence-contract-v1",
    }

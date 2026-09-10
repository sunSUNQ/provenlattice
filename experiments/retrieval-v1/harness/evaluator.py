from __future__ import annotations

import re
from typing import Any

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

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from .models import TaskDefinition, ToolEvent


def _files(event: ToolEvent) -> set[str]:
    values = set(event.files)
    for candidate in (event.target, event.query):
        if isinstance(candidate, str):
            values.update(re.findall(r"(?:src|test|docs?|include)/[^\s`\"']+", candidate))
    return {value.rstrip(").,;:") for value in values}


def collect_metrics(task: TaskDefinition, events: Iterable[ToolEvent], duration_ms: float,
                    agent_output: str) -> dict:
    events = list(events)
    counts = Counter(event.operation for event in events)
    graph_ops = {"symbol", "definition", "callers", "callees", "references", "dependencies",
                 "dependents", "subgraph", "shard", "impact"}
    knowledge_ops = {"document", "evidence", "related-code", "cross-layer", "implemented", "requirements"}
    all_evidence = {evidence_id for event in events for evidence_id in event.evidence_ids}
    used_evidence = {evidence_id for event in events for evidence_id in event.used_evidence_ids}
    returned_edges = sum(event.returned_edges or 0 for event in events)
    returned_evidence = sum(event.returned_evidence or len(event.evidence_ids) for event in events)
    files = set().union(*(_files(event) for event in events)) if events else set()
    tokens = Counter()
    for event in events:
        tokens.update(event.tokens)
    first_relevant = None
    for event in events:
        event_text = " ".join(str(value) for value in (event.query, event.target, *event.files)).casefold()
        if any(value.casefold() in event_text
               for value in (*task.expected_files, *task.expected_symbols, *task.expected_documents)):
            first_relevant = event.raw.get("elapsed_ms")
            break
    result = {
        "tool_turns": len(events), "read_calls": counts["read"],
        "grep_calls": counts["grep"] + counts["search"], "glob_calls": counts["glob"],
        "shell_calls": counts["shell"], "graph_queries": sum(counts[op] for op in graph_ops),
        "knowledge_queries": sum(counts[op] for op in knowledge_ops),
        "unique_files_read": len(files), "files_read": sorted(files),
        "total_file_chars_read": sum(event.result_size or 0 for event in events
                                      if event.operation == "read"),
        "total_tool_output_chars": sum(event.result_size or 0 for event in events),
        "duration_ms": round(duration_ms, 4),
        "input_tokens": tokens.get("input", None), "output_tokens": tokens.get("output", None),
        "cache_tokens": (tokens.get("cache_read", 0) + tokens.get("cache_creation", 0)
                         if tokens.get("cache_read") is not None or tokens.get("cache_creation") is not None
                         else None), "total_tokens": tokens.get("total", None),
        "returned_graph_evidence": returned_evidence,
        "returned_graph_edges": returned_edges,
        "observed_evidence_ids": sorted(all_evidence),
        "observed_used_evidence_ids": sorted(used_evidence),
        "graph_evidence_hit_rate": (len(used_evidence) / len(all_evidence)
                                     if all_evidence else None),
        "cross_layer_edge_utilization": None,
        "time_to_first_relevant_evidence_ms": first_relevant,
        "native_exploration_avoided": None,
    }
    if returned_edges:
        result["cross_layer_edge_utilization"] = len(used_evidence) / returned_edges
    return result

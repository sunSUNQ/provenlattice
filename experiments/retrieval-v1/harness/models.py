from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARM_TOOLS = {
    "native": {"read", "search", "grep", "glob", "shell"},
    "codegraph": {"read", "search", "grep", "glob", "shell", "symbol", "definition",
                   "callers", "callees", "references", "dependencies", "dependents",
                   "subgraph", "shard", "impact", "explain-symbol", "explain-module",
                   "trace-evidence"},
    "knowledge": {"read", "search", "grep", "glob", "shell", "symbol", "definition",
                   "callers", "callees", "references", "dependencies", "dependents",
                   "subgraph", "shard", "impact", "document", "evidence", "related-code",
                   "cross-layer", "implemented", "requirements"},
}
ARM_TOOLS["knowledge"].update({"explain-symbol", "explain-module", "trace-evidence",
                               "find-related-code", "find-related-documents"})
WRITE_OPERATIONS = {"edit", "write", "replace", "delete", "commit", "reset", "checkout",
                    "push", "destructive-shell"}


@dataclass(slots=True)
class TaskDefinition:
    task_id: str
    repository: str
    commit: str
    category: str
    prompt: str
    ground_truth: dict[str, Any]
    expected_files: list[str]
    expected_symbols: list[str]
    expected_documents: list[str]
    expected_relationships: list[dict[str, Any]]
    success_criteria: list[str]
    difficulty: str = "Medium"

    @classmethod
    def load(cls, path: str | Path) -> "TaskDefinition":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "repository": self.repository, "commit": self.commit,
            "category": self.category, "difficulty": self.difficulty, "prompt": self.prompt,
            "ground_truth": self.ground_truth, "expected_files": self.expected_files,
            "expected_symbols": self.expected_symbols, "expected_documents": self.expected_documents,
            "expected_relationships": self.expected_relationships,
            "success_criteria": self.success_criteria,
        }


@dataclass(slots=True)
class RunRequest:
    run_id: str
    task_id: str
    repo_path: str
    repo_commit: str
    arm: str
    prompt: str
    allowed_tools: list[str]
    environment: dict[str, str]
    timeout: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "task_id": self.task_id, "repo_path": self.repo_path,
            "repo_commit": self.repo_commit, "arm": self.arm, "prompt": self.prompt,
            "allowed_tools": self.allowed_tools, "environment": self.environment,
            "timeout": self.timeout,
        }


@dataclass(slots=True)
class ToolEvent:
    run_id: str
    task_id: str
    arm: str
    timestamp: str
    tool: str
    operation: str
    query: Any = None
    target: Any = None
    result_size: int | None = None
    duration: float | None = None
    evidence_ids: list[str] = field(default_factory=list)
    viewed_evidence_ids: list[str] = field(default_factory=list)
    used_evidence_ids: list[str] = field(default_factory=list)
    query_id: str | None = None
    query_type: str | None = None
    anchor: str | None = None
    bundle_size: int | None = None
    query_latency: float | None = None
    graph_generation: int | None = None
    returned_nodes: int | None = None
    returned_edges: int | None = None
    returned_evidence: int | None = None
    resolved_count: int | None = None
    ambiguous_count: int | None = None
    unresolved_count: int | None = None
    files: list[str] = field(default_factory=list)
    tokens: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any], request: RunRequest) -> "ToolEvent":
        return cls(
            run_id=value.get("run_id", request.run_id), task_id=value.get("task_id", request.task_id),
            arm=value.get("arm", request.arm),
            timestamp=value.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            tool=str(value.get("tool", "unknown")), operation=str(value.get("operation", "unknown")).casefold(),
            query=value.get("query"), target=value.get("target"), result_size=value.get("result_size"),
            duration=value.get("duration"), evidence_ids=list(value.get("evidence_ids") or []),
            viewed_evidence_ids=list(value.get("viewed_evidence_ids") or []),
            used_evidence_ids=list(value.get("used_evidence_ids") or []),
            query_id=value.get("query_id"), query_type=value.get("query_type"),
            anchor=value.get("anchor"), bundle_size=value.get("bundle_size"),
            query_latency=value.get("query_latency"),
            graph_generation=value.get("graph_generation"), returned_nodes=value.get("returned_nodes"),
            returned_edges=value.get("returned_edges"), returned_evidence=value.get("returned_evidence"),
            resolved_count=value.get("resolved_count"), ambiguous_count=value.get("ambiguous_count"),
            unresolved_count=value.get("unresolved_count"), files=list(value.get("files") or []),
            tokens=dict(value.get("tokens") or {}), raw=value,
        )

    def to_dict(self) -> dict[str, Any]:
        value = dict(self.raw)
        value.update({
            "run_id": self.run_id, "task_id": self.task_id, "arm": self.arm,
            "timestamp": self.timestamp, "tool": self.tool, "operation": self.operation,
            "query": self.query, "target": self.target,
            "duration": self.duration, "evidence_ids": self.evidence_ids,
            "viewed_evidence_ids": self.viewed_evidence_ids,
            "used_evidence_ids": self.used_evidence_ids,
            "query_id": self.query_id, "query_type": self.query_type,
            "anchor": self.anchor, "bundle_size": self.bundle_size,
            "query_latency": self.query_latency,
            "result_size": self.result_size, "graph_generation": self.graph_generation,
            "returned_nodes": self.returned_nodes, "returned_edges": self.returned_edges,
            "returned_evidence": self.returned_evidence,
            "resolved_count": self.resolved_count, "ambiguous_count": self.ambiguous_count,
            "unresolved_count": self.unresolved_count, "files": self.files,
            "tokens": self.tokens,
        })
        return value


@dataclass(slots=True)
class RunResult:
    run_id: str
    task_id: str
    arm: str
    status: str
    task_success: bool | None
    start_time: str
    end_time: str
    duration_ms: float
    tool_calls: int
    agent_output: str
    exit_reason: str
    error: str | None
    allowed_tools: list[str]
    policy_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "task_id": self.task_id, "arm": self.arm,
                "status": self.status, "task_success": self.task_success,
                "start_time": self.start_time, "end_time": self.end_time,
                "duration_ms": self.duration_ms, "tool_calls": self.tool_calls,
                "agent_output": self.agent_output, "exit_reason": self.exit_reason,
                "error": self.error, "allowed_tools": self.allowed_tools,
                "policy_violations": self.policy_violations}

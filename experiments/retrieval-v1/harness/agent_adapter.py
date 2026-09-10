from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable

from .models import RunRequest, ToolEvent


@dataclass(slots=True)
class AdapterResult:
    output: str
    events: list[ToolEvent]
    exit_reason: str
    error: str | None = None


class CommandAgentAdapter:
    """Product-neutral adapter for one user-selected agent executable."""

    def __init__(self, command: str | list[str]) -> None:
        self.command = shlex.split(command, posix=False) if isinstance(command, str) else command
        self.command = [part.strip('"') for part in self.command]

    def run(self, request: RunRequest, on_event: Callable[[ToolEvent], None] | None = None) -> AdapterResult:
        env = dict(request.environment)
        env.update({"PL_R1_RUN_REQUEST": json.dumps(request.to_dict(), ensure_ascii=False),
                    "PL_R1_READ_ONLY": "1"})
        try:
            completed = subprocess.run(
                self.command, cwd=request.repo_path,
                input=json.dumps(request.to_dict(), ensure_ascii=False), text=True,
                capture_output=True, timeout=request.timeout, env={**__import__("os").environ, **env},
            )
        except subprocess.TimeoutExpired as exc:
            return AdapterResult(exc.stdout or "", [], "timeout", str(exc))
        except OSError as exc:
            return AdapterResult("", [], "adapter_error", str(exc))
        events: list[ToolEvent] = []
        output_lines: list[str] = []
        for line in completed.stdout.splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                output_lines.append(line)
                continue
            if value.get("event_type") == "tool":
                event = ToolEvent.from_dict(value, request)
                events.append(event)
                if on_event:
                    on_event(event)
            elif value.get("type") == "assistant":
                for content in (value.get("message") or {}).get("content", []):
                    if content.get("type") != "tool_use":
                        continue
                    event = self._claude_tool_event(content, request)
                    events.append(event)
                    if on_event:
                        on_event(event)
            elif value.get("type") == "result":
                result_text = value.get("result")
                if isinstance(result_text, str):
                    output_lines.append(result_text)
                usage = value.get("usage") or {}
                if events and usage:
                    events[-1].tokens.update({key: int(value) for key, value in usage.items()
                                               if isinstance(value, (int, float))})
            else:
                output_lines.append(line)
        reason = "completed" if completed.returncode == 0 else "agent_nonzero_exit"
        error = completed.stderr.strip() or None
        return AdapterResult("\n".join(output_lines), events, reason, error)

    @staticmethod
    def _claude_tool_event(content: dict, request: RunRequest) -> ToolEvent:
        name = str(content.get("name", "unknown"))
        operation = {"read": "read", "grep": "grep", "glob": "glob",
                     "bash": "shell"}.get(name.casefold(), name.casefold())
        inputs = content.get("input") or {}
        query = inputs.get("pattern") or inputs.get("command") or inputs.get("query")
        target = inputs.get("file_path") or inputs.get("path") or inputs.get("pattern")
        # A Claude Bash invocation of the ProvenLattice CLI is normalized to
        # its logical graph operation, so arm isolation remains auditable.
        command_text = str(inputs.get("command", ""))
        if "provenlattice" in command_text.casefold() or "python -m provenlattice" in command_text.casefold():
            words = command_text.casefold().replace("\\", " ").split()
            for candidate in ("symbol", "definition", "callers", "callees", "references",
                              "dependencies", "dependents", "subgraph", "shard", "impact",
                              "document", "evidence", "related-code", "cross-layer",
                              "implemented", "requirements"):
                if candidate in words:
                    operation = candidate
                    break
        return ToolEvent.from_dict({
            "event_type": "tool", "tool": name, "operation": operation,
            "query": query, "target": target, "timestamp": content.get("timestamp"),
            "claude_tool_use_id": content.get("id"),
        }, request)


class ReplayAdapter:
    """Test-only adapter; never used to claim a real agent result."""

    def __init__(self, output: str, events: list[dict]) -> None:
        self.output, self.event_values = output, events

    def run(self, request: RunRequest, on_event: Callable[[ToolEvent], None] | None = None) -> AdapterResult:
        events = [ToolEvent.from_dict(value, request) for value in self.event_values]
        if on_event:
            for event in events:
                on_event(event)
        return AdapterResult(self.output, events, "completed")

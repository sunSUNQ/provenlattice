from __future__ import annotations

import json
import shlex
import shutil
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
        command = list(self.command)
        stdin_value = json.dumps(request.to_dict(), ensure_ascii=False)
        executable = command[0].replace("\\", "/").rsplit("/", 1)[-1].casefold()
        if executable in {"claude", "claude.cmd", "claude.exe", "claude.ps1"}:
            # CreateProcess does not apply PowerShell's command discovery. On
            # Windows, resolve the npm-generated claude.cmd explicitly.
            command[0] = shutil.which(command[0]) or command[0]
            # Claude print mode consumes the task prompt as text. The complete
            # RunRequest remains available in PL_R1_RUN_REQUEST for auditing.
            stdin_value = request.prompt
            arm_prompt = self._claude_arm_prompt(request)
            if "--append-system-prompt" not in command:
                command.extend(["--append-system-prompt", arm_prompt])
        try:
            completed = subprocess.run(
                command, cwd=request.repo_path,
                input=stdin_value, text=True, encoding="utf-8", errors="replace",
                capture_output=True, timeout=request.timeout, env={**__import__("os").environ, **env},
            )
        except subprocess.TimeoutExpired as exc:
            return AdapterResult(exc.stdout or "", [], "timeout", str(exc))
        except OSError as exc:
            return AdapterResult("", [], "adapter_error", str(exc))
        events: list[ToolEvent] = []
        events_by_tool_id: dict[str, ToolEvent] = {}
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
                    tool_id = str(content.get("id", ""))
                    if tool_id:
                        events_by_tool_id[tool_id] = event
                    if on_event:
                        on_event(event)
            elif value.get("type") == "user":
                for content in (value.get("message") or {}).get("content", []):
                    if content.get("type") != "tool_result":
                        continue
                    event = events_by_tool_id.get(str(content.get("tool_use_id", "")))
                    if event is None:
                        continue
                    result_text = self._tool_result_text(content.get("content"))
                    event.result_size = len(result_text)
                    if event.operation == "read" and isinstance(event.target, str):
                        event.files = [event.target]
            elif value.get("type") == "result":
                result_text = value.get("result")
                if isinstance(result_text, str):
                    output_lines.append(result_text)
                usage = value.get("usage") or {}
                if events and usage:
                    token_map = {
                        "input_tokens": "input", "output_tokens": "output",
                        "cache_read_input_tokens": "cache_read",
                        "cache_creation_input_tokens": "cache_creation",
                    }
                    for source, target in token_map.items():
                        if isinstance(usage.get(source), (int, float)):
                            events[-1].tokens[target] = int(usage[source])
                    events[-1].tokens["total"] = sum(events[-1].tokens.values())
            else:
                output_lines.append(line)
        reason = "completed" if completed.returncode == 0 else "agent_nonzero_exit"
        error = completed.stderr.strip() or None
        return AdapterResult("\n".join(output_lines), events, reason, error)

    @staticmethod
    def _tool_result_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(str(item.get("text", "")) if isinstance(item, dict) else str(item)
                             for item in content)
        return "" if content is None else str(content)

    @staticmethod
    def _claude_arm_prompt(request: RunRequest) -> str:
        common = (
            "This is a read-only retrieval experiment. Never edit, create, delete, move, or commit files. "
            "Do not change git state. Answer the frozen user task using only permitted retrieval capabilities."
        )
        if request.arm == "native":
            return common + " Do not invoke ProvenLattice or access any ProvenLattice database."
        database = request.environment.get("PL_R1_DATABASE", "")
        graph = (
            f" You may query the frozen ProvenLattice database at {database!r} with the read-only CLI: "
            "provenlattice symbol NAME --database DB --json; provenlattice callers SYMBOL --database DB --json; "
            "provenlattice callees SYMBOL --database DB --json; provenlattice shard NAME --database DB --json; "
            "provenlattice subgraph ANCHOR --database DB --json."
        )
        if request.arm == "codegraph":
            return common + graph + " Do not use knowledge commands: evidence, implemented, or requirements."
        return common + graph + (
            " You may also use knowledge evidence commands: provenlattice evidence --database DB --json; "
            "provenlattice implemented REQUIREMENT --database DB --json; "
            "provenlattice requirements SYMBOL --database DB --json."
        )

    @staticmethod
    def _claude_tool_event(content: dict, request: RunRequest) -> ToolEvent:
        name = str(content.get("name", "unknown"))
        operation = {"read": "read", "grep": "grep", "glob": "glob",
                     "bash": "shell", "powershell": "shell"}.get(name.casefold(), name.casefold())
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

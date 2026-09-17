"""SQI-V1.3 isolation: checkout-leakage detection (pattern/path separated).

Policy (protocol V1.3 amendment): a formal-session agent may access only
(a) the benchmark repository subtree it runs in, (b) the sanctioned SQI bridge
process, and (c) nothing else.

V1.3 semantics (fixes the C4 attempt-2 false-positive storm):
  * `read` events carry REAL paths -> absolute root-escape + hint checks;
  * `glob` events carry PATTERNS -> flagged only on framework hints or
    absolute paths pointing outside the repo;
  * `grep` events carry PATTERNS (e.g. `error_cstr`, `class DownloadEngine`)
    -> flagged ONLY when the pattern/command text references framework hints;
    plain code patterns are never leakage;
  * `shell` command text: sanctioned bridge invocations are exempt; everything
    else is checked for framework hints and out-of-root absolute paths.

Detection remains layered ON TOP of prevention: the runner's permission mode
(default: tools outside allowedTools are denied before execution) plus scoped
`Read(./**)` rules prevent out-of-cwd file access; per-cell git status/diff
plus HEAD checks remain the second seal.
"""
from __future__ import annotations

import os
import re

SANCTIONED_SHELL_PATTERNS = (
    re.compile(r"python -m experiments\.query_interface_v1\.tools\.sqi_cli\b"),
    re.compile(r"python [A-Za-z]:/[^ ]*sqi_cli\.py\b"),
    re.compile(r"python \"[A-Za-z]:/[^\"]*sqi_cli\.py\""),
)

FRAMEWORK_HINTS = (
    "provenlattice",
    "benchmark-analysis",
    "experiments\\query_interface_v1",
    "experiments/query_interface_v1",
    "experiments\\retrieval-v1",
    "experiments/retrieval-v1",
    "experiments\\retrieval-v2",
    "experiments/retrieval-v2",
    "experiments\\systems_v1",
    "experiments/systems_v1",
    "experiments\\fidelity_v1",
    "experiments/fidelity_v1",
    "sqi_cli",
    "query_interface_v1",
    "query_interface",
    "pl_sqi",
    ".claude",
    "quarantine-",
)

# shell-only hints: commands with zero legitimate use inside a sandboxed
# read-only formal session (binary/database dumping, environment scraping)
SHELL_TEXT_HINTS = (
    "printenv",
    "od -a",
    "od -a d",
    "strings -n",
    "sqlite3 ",
    "sqi_database",
)

_ABSOLUTE_OUTSIDE_RE = re.compile(
    r"([A-Za-z]:[/\\][^ ]*)", re.IGNORECASE)


def _event_targets(event: dict) -> list[str]:
    # `query` carries shell command text and grep patterns; `target`/`files`
    # carry read/glob paths. All three are audit surfaces.
    targets = []
    for key in ("target", "query"):
        value = event.get(key)
        if isinstance(value, str) and value:
            targets.append(value)
    for value in event.get("files") or []:
        if isinstance(value, str) and value:
            targets.append(value)
    return targets


def _is_sanctioned_shell(event: dict) -> bool:
    if str(event.get("operation", "")).casefold() not in ("shell", "bash"):
        return False
    command = str(event.get("query") or event.get("target") or "")
    return any(pattern.search(command) for pattern in SANCTIONED_SHELL_PATTERNS)


def _absolute_outside(text: str, repo_root: str) -> bool:
    root = os.path.abspath(repo_root).lower().rstrip(os.sep) + os.sep
    for match in _ABSOLUTE_OUTSIDE_RE.finditer(text):
        candidate = os.path.abspath(match.group(1).lower())
        if not (candidate == root.rstrip(os.sep)
                or candidate.startswith(root)):
            return True
    return False


def leakage_events(events: list[dict], repo_root: str) -> list[dict]:
    """Return one entry per event that touches anything outside the repo root
    or references framework paths/hints (V1.3 pattern/path semantics)."""
    findings: list[dict] = []
    for index, event in enumerate(events or []):
        if _is_sanctioned_shell(event):
            continue
        operation = str(event.get("operation", "")).casefold()
        targets = _event_targets(event)
        if not targets:
            continue
        leaked = False
        reason = ""
        if operation == "grep":
            # target is a SEARCH PATTERN: only framework hints count
            for target in targets:
                hinted = any(hint in target.lower()
                             for hint in FRAMEWORK_HINTS)
                if hinted or _absolute_outside(target, repo_root):
                    leaked, reason = True, "framework_hint_in_pattern" if hinted \
                        else "outside_repo_root"
                    break
        elif operation in ("glob", "read"):
            # glob targets are patterns; read targets are real paths. Both are
            # only paths (not search patterns), so both checks apply.
            root_with_sep = os.path.abspath(repo_root).lower().rstrip(os.sep) + os.sep
            for target in targets:
                hinted = any(hint in target.lower()
                             for hint in FRAMEWORK_HINTS)
                outside = False
                if os.path.isabs(target):
                    candidate = os.path.abspath(target.lower())
                    outside = not (candidate == root_with_sep.rstrip(os.sep)
                                   or candidate.startswith(root_with_sep))
                if hinted or outside:
                    leaked, reason = True, ("framework_path" if hinted
                                            else "outside_repo_root")
                    break
        else:  # shell / other: command text hints + absolute escapes
            for target in targets:
                lowered = target.lower()
                hinted = any(hint in lowered for hint in FRAMEWORK_HINTS)
                shell_dumped = any(hint in lowered for hint in SHELL_TEXT_HINTS)
                if hinted or shell_dumped or _absolute_outside(target, repo_root):
                    leaked = True
                    reason = ("shell_dump" if shell_dumped else
                              ("framework_path" if hinted else "outside_repo_root"))
                    break
        if leaked:
            findings.append({
                "event_index": index,
                "operation": operation or str(event.get("tool", "")),
                "target": targets[0][:300],
                "reason": reason,
            })
    return findings

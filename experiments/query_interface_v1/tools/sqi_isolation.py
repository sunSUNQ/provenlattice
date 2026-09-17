"""SQI-V1.1 isolation: deterministic checkout-leakage detection.

Policy (protocol V1.1 amendment): a formal-session agent may access only
(a) the benchmark repository subtree it runs in, (b) the sanctioned SQI bridge
process, and (c) nothing else. Any read/grep/glob/shell event whose target
resolves outside the repo root — in particular anything under the
ProvenLattice checkout, the experiment framework, or the frozen databases —
is a CHECKOUT_LEAKAGE policy violation and invalidates the cell.

Detection is layered ON TOP of prevention: the runner's allowedTools scoping
(`Read(./**)`, `Grep(./**)` etc.) makes claude deny out-of-cwd file access
(empirically verified 2026-09-17); the scanner below is the enforcement of
record and works even if a future CLI change weakens the prevention layer.
"""
from __future__ import annotations

import os
import re

SANCTIONED_SHELL_PATTERNS = (
    re.compile(r"python -m experiments\.query_interface_v1\.tools\.sqi_cli\b"),
)

LEAKAGE_PATH_HINTS = (
    "provenlattice",  # the checkout itself (also matches the repo root name)
    "benchmark-analysis",  # frozen databases / analysis artifacts
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
)


def _event_targets(event: dict) -> list[str]:
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


def leakage_events(events: list[dict], repo_root: str) -> list[dict]:
    """Return one entry per event that touches anything outside the repo root.

    Absolute out-of-root targets are leakage by definition; relative targets
    are checked against the hint list (a relative path cannot escape the repo
    unless it contains `..`, which is caught by the root-resolution check).
    Sanctioned bridge invocations are never leakage.
    """
    root = os.path.abspath(repo_root).lower()
    findings: list[dict] = []
    for index, event in enumerate(events or []):
        if _is_sanctioned_shell(event):
            continue
        operation = str(event.get("operation", "")).casefold()
        for target in _event_targets(event):
            lowered = target.lower()
            absolute = os.path.abspath(target.lower())
            escaped = not (absolute == root or absolute.startswith(root + os.sep))
            hinted = any(hint in lowered for hint in LEAKAGE_PATH_HINTS)
            if hinted or escaped:
                findings.append({
                    "event_index": index,
                    "operation": operation or str(event.get("tool", "")),
                    "target": target[:300],
                    "reason": "framework_path" if hinted else "outside_repo_root",
                })
                break
    return findings

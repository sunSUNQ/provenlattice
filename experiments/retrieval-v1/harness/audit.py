from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .evaluator import evaluate
from .models import TaskDefinition, ToolEvent
from .provenance_tools import read_events, sha256_text


ARTIFACTS = ("run.json", "events.ndjson", "agent-output.txt", "metrics.json", "evaluation.json")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_run(run_dir: str | Path, task: TaskDefinition, arm: str, repetition: int,
              model_id: str, claude_version: str, provenlattice_commit: str) -> dict:
    run_dir = Path(run_dir)
    errors: list[str] = []
    missing = [name for name in ARTIFACTS if not (run_dir / name).is_file()]
    if missing:
        return {"valid": False, "errors": [f"MISSING:{name}" for name in missing], "run": None}
    try:
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        stored_evaluation = json.loads((run_dir / "evaluation.json").read_text(encoding="utf-8"))
        values = read_events(run_dir / "events.ndjson")
        request = type("Request", (), {"run_id": run.get("run_id"),
                                         "task_id": task.task_id, "arm": arm})()
        events = [ToolEvent.from_dict(value, request) for value in values]
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"valid": False, "errors": [f"UNPARSEABLE:{type(exc).__name__}:{exc}"], "run": None}
    expected = {
        "run_key": f"{task.task_id}.{arm}.r{repetition}", "task_id": task.task_id,
        "arm": arm, "repetition": repetition, "repo_commit": task.commit,
        "agent_actual_commit": task.commit, "prompt_hash": sha256_text(task.prompt),
        "model_id": model_id, "claude_version": claude_version,
        "provenlattice_commit": provenlattice_commit,
    }
    for key, value in expected.items():
        if run.get(key) != value:
            errors.append(f"METADATA:{key}:expected={value!r}:actual={run.get(key)!r}")
    if run.get("prompt") != task.prompt:
        errors.append("PROMPT_IDENTITY")
    if run.get("status") != "completed":
        errors.append(f"RUN_STATUS:{run.get('status')}")
    if run.get("policy_violations"):
        errors.append("POLICY_VIOLATION")
    if run.get("git_status_before") or run.get("git_status_after"):
        errors.append("DIRTY_WORKTREE")
    if len(events) != run.get("tool_calls") or len(events) != metrics.get("tool_turns"):
        errors.append("EVENT_METRIC_COUNT_MISMATCH")
    reproduced = evaluate(task, (run_dir / "agent-output.txt").read_text(encoding="utf-8"),
                          events, metrics)
    if reproduced != stored_evaluation:
        errors.append("EVALUATION_NOT_REPRODUCIBLE")
    hashes = {name: file_sha256(run_dir / name) for name in ARTIFACTS}
    return {"valid": not errors, "errors": errors, "run": run, "metrics": metrics,
            "evaluation": stored_evaluation, "artifact_hashes": hashes}


def quarantine(run_dir: str | Path, bucket: str = "_invalid") -> Path:
    run_dir = Path(run_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    results_root = run_dir.parents[2]
    destination = results_root / bucket / f"{run_dir.parents[1].name}.{run_dir.parent.name}.{run_dir.name}-{stamp}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(run_dir), str(destination))
    return destination

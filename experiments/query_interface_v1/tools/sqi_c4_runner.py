"""C4 Attempt-4 formal runner — the ONLY legal cell lifecycle (frozen).

    build_runtime → per cell: prepare_cell → CellWindow enter → agent session →
    CHECKOUT_LEAKAGE scanner (finite-root classification) → CellWindow
    exit/restore → R1 fingerprint verify → evaluate → record

Fail-closed: a batch HALTS immediately on the first offending cell (artifacts
preserved, the next cell never starts):

  * ACL apply/verify failure        → cell INVALID_EXECUTION
  * sensitive leakage event         → cell INVALID_LEAKAGE
  * restore failure                 → cell INVALID_RESTORE
  * frozen fingerprint drift        → cell INVALID_FINGERPRINT_DRIFT
  * any unexpected exception        → cell INVALID_UNEXPECTED

Cell order (protocol §3, frozen): tasks ascending, arms native then sqi,
repetitions ascending — 6 x 2 x 3 = 36 cells.

Isolation baseline: V1.4-Windows Finite-Root Isolation Profile, commit
27e40df5e61cd815d8ea0d00203746344c279690 (amendment + CellWindow lifecycle
+ sandbox fixes + tests + seals). This runner never bypasses CellWindow:
every agent session runs inside an open window, every window edge is
verified, and no code path continues to the next cell after a halt.

Modes:
  --preflight  environment gate for the batch (no sessions; writes evidence)
  --batch      execute all 36 cells sequentially after preflight
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINE_ROOT = HERE.parent
REPO_ROOT = LINE_ROOT.parents[1]
WORKSPACE = REPO_ROOT.parent
for _p in (str(HERE), str(REPO_ROOT), str(REPO_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqi_evaluator import evaluate_cell  # noqa: E402
from sqi_formal_runner import (  # noqa: E402
    NATIVE_ARM_PROMPT, NATIVE_ALLOWED_TOOLS, load_config, load_tasks)
from sqi_isolation import leakage_events  # noqa: E402
from v14_c4_lifecycle import (  # noqa: E402
    CellWindow, classify_leakage, prepare_cell)
from v14_feasibility_noreboot import (  # noqa: E402
    BENCH, RUNTIME_ROOT, build_runtime, runtime_db_for, task_db_rels)

ISOLATION_BASELINE_SHA = "27e40df5e61cd815d8ea0d00203746344c279690"
BASELINE_BATCH_DIR = LINE_ROOT / "results" / "formal" / "SQI-FORMAL-20260917-1"
BASELINE_SUMMARY = BASELINE_BATCH_DIR / "formal-batch-summary.json"
BASELINE_MANIFEST = BASELINE_BATCH_DIR / "manifest.sha256"
RUNNER_PATH = "experiments/query_interface_v1/tools/sqi_c4_runner.py"
LIFECYCLE_PATH = "experiments/query_interface_v1/tools/v14_c4_lifecycle.py"

HALT_EXECUTION = "INVALID_EXECUTION"
HALT_LEAKAGE = "INVALID_LEAKAGE"
HALT_RESTORE = "INVALID_RESTORE"
HALT_DRIFT = "INVALID_FINGERPRINT_DRIFT"
HALT_UNEXPECTED = "INVALID_UNEXPECTED"

import importlib  # noqa: E402
import os  # noqa: E402
harness_agent_adapter = importlib.import_module(
    "experiments.retrieval-v1.harness.agent_adapter")
harness_models = importlib.import_module(
    "experiments.retrieval-v1.harness.models")

# Claude session/config state is CELL-PRIVATE: CLAUDE_CONFIG_DIR points at a
# per-cell home under the sanitized runtime output area (outside the denied
# checkout), populated BEFORE the window opens by copying the host auth/config
# files. Consequences (containment repair, 2026-09-18):
#   * transcripts / tool-results are written to and re-read from the private
#     home — the claude-CLI large-tool-result mechanics work again and no
#     host-store path is ever touched (the transcript-store deny window stays
#     on as defense in depth);
#   * runtime-internal paths are non-sensitive under the frozen finite-root
#     classification, so the INVALID_LEAKAGE halt root cause disappears
#     without touching scanner or amendment semantics;
#   * execution semantics (model, CLI version, prompts, allowlists, settings
#     content) are unchanged — the config files are byte-copies.
CLAUDE_HOME_FILES = (".claude.json",)
CLAUDE_HOME_DIR_FILES = (".credentials.json", "settings.json")


def build_cell_claude_home(cell_label: str, base: Path) -> Path:
    """Create a cell-private claude home (pre-window) with byte-copied host
    config; returns the directory for CLAUDE_CONFIG_DIR."""
    home = base / "claude-homes" / cell_label
    home.mkdir(parents=True, exist_ok=True)
    user_home = Path(os.environ.get("USERPROFILE", ""))
    for name in CLAUDE_HOME_FILES:
        src = user_home / name
        if src.exists():
            shutil.copy2(src, home / name)
    claude_dir = user_home / ".claude"
    for name in CLAUDE_HOME_DIR_FILES:
        src = claude_dir / name
        if src.exists():
            (home / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, home / name)
    return home


class C4BatchHalted(Exception):
    """Raised when a fail-closed condition halts the batch."""

    def __init__(self, cell_id: str, reason: str, detail: str):
        super().__init__(f"{cell_id}: {reason}: {detail[:300]}")
        self.cell_id = cell_id
        self.reason = reason
        self.detail = detail


def frozen_cell_order(config: dict, tasks: list[dict]) -> list[dict]:
    """Protocol §3 frozen order: tasks ascending, arms native then sqi,
    repetitions ascending."""
    order = []
    for task in sorted(tasks, key=lambda t: t["task_id"]):
        for arm in ("native", "sqi"):
            for repetition in range(1, int(config["repetitions_per_cell"]) + 1):
                order.append({"task_id": task["task_id"], "arm": arm,
                              "repetition": repetition})
    return order


def order_fingerprint(order: list[dict]) -> str:
    canonical = ";".join(f"{c['task_id']}:{c['arm']}:r{c['repetition']}"
                         for c in order)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def prepare_native_cell(task: dict, batch_output: Path, config: dict) -> dict:
    repo_name = task["repository"].split("-", 1)[1].lower()
    return {
        "label": f"{task['task_id']}-native",
        "repo_path": str(BENCH / repo_name),
        "database": str(runtime_db_for(task)[0]),
        "code_database": None,
        "environment": {"PL_MODEL_ID": config["model_id"]},
        "system_prompt": NATIVE_ARM_PROMPT,
        "allowed_tools": NATIVE_ALLOWED_TOOLS,
    }


def prepare_sqi_cell(task: dict, batch_output: Path) -> dict:
    surface = prepare_cell(task, batch_output)
    surface["system_prompt"] = surface.pop("arm_prompt")
    return surface


def default_session(cell: dict, surface: dict, config: dict) -> dict:
    """Production session: claude -p inside the open window.

    The SQI call log is WRITTEN by the bridge inside the window (append is
    not blocked by the deny-(RD) window, finding P3) but is NEVER read back
    here: its base path may sit under the denied tree, so the runner reads
    and archives it only after CellWindow exit/restore (run_cell)."""
    task = cell["_task"]
    run_dir = Path(surface["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    request = harness_models.RunRequest(
        run_id=f"C4-{surface['label']}-{uuid.uuid4().hex[:6]}",
        task_id=task["task_id"], repo_path=surface["repo_path"],
        repo_commit=task["commit"], arm=cell["arm"], prompt=task["prompt"],
        allowed_tools=sorted({"read", "grep", "glob"} |
                             ({"shell"} if cell["arm"] == "sqi" else set())),
        environment=surface["environment"],
        timeout=float(config["timeout_s"]))
    command = [shutil.which("claude") or "claude", "-p", "--verbose",
               "--output-format", "stream-json",
               "--permission-mode", "default",
               "--append-system-prompt", surface["system_prompt"],
               "--allowedTools", surface["allowed_tools"],
               "--model", config["model_id"]]
    adapter = harness_agent_adapter.CommandAgentAdapter(command)
    result = adapter.run(request)
    events = [event.to_dict() for event in result.events]
    return {"exit_reason": result.exit_reason, "error": result.error,
            "events": events, "output": result.output or "",
            "call_log": [], "call_log_path":
                surface["environment"].get("PL_SQI_CALL_LOG"),
            "permission_denials": result.permission_denials or [],
            "actual_model": result.actual_model,
            "backend_model": result.backend_model}


def collect_call_log(surface: dict, run_dir: Path) -> list[dict]:
    """Post-restore: read the bridge call log (now outside any deny window),
    archive the raw file into run_dir, return parsed entries."""
    log_path = surface["environment"].get("PL_SQI_CALL_LOG")
    if not log_path or not Path(log_path).exists():
        return []
    entries = []
    for line in Path(log_path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "sqi-call-log.ndjson"
    if Path(log_path).resolve() != target.resolve():
        shutil.copy2(log_path, target)
    return entries


def _classify_exit_failure(window: CellWindow) -> str:
    state = window.state
    wv = state.get("window_closed_verified")
    if not (wv and wv.get("closed")):
        return HALT_EXECUTION
    restore = state.get("restore_verified") or {}
    probes = restore.get("probes") or {}
    if any(not p.get("readable") for p in probes.values()):
        return HALT_RESTORE
    if (state.get("post_repos") != state.get("pre_repos")
            or state.get("post_dbs") != state.get("pre_dbs")):
        return HALT_DRIFT
    return HALT_RESTORE


class C4BatchRunner:
    """Wires every cell through the frozen lifecycle; fail-closed per batch."""

    def __init__(self, config: dict, tasks: list[dict], batch_id: str,
                 batch_dir: Path, window_factory=None, session_fn=None,
                 evaluate_fn=None, runtime_output_root: Path | None = None,
                 expected_backend: str | None = None):
        self.config = config
        self.tasks = {t["task_id"]: t for t in tasks}
        self.batch_id = batch_id
        self.batch_dir = Path(batch_dir)
        # Backend identity provenance (C4-R1): every cell must run on the
        # same actually-served backend as the pre-batch probe; any drift is
        # a fail-closed halt (INVALID_EXECUTION). None disables the check
        # (synthetic wiring tests only).
        self.expected_backend = expected_backend
        # Call-log base lives OUTSIDE the denied checkout (amendment §2:
        # results flow back through the sanitized runtime output area); the
        # runner reads it only after the window has closed and restore has
        # been verified. Injectable base for wiring tests on synthetic trees.
        self.runtime_output = (Path(runtime_output_root) if runtime_output_root
                               else RUNTIME_ROOT / "output" / "c4" / batch_id)
        self.runtime_output.mkdir(parents=True, exist_ok=True)
        self._window_factory = window_factory or (lambda label: CellWindow(label))
        self._session_fn = session_fn or default_session
        self._evaluate_fn = evaluate_fn or evaluate_cell
        self.cells_executed: list[str] = []

    # -- lifecycle ------------------------------------------------------

    def run_cell(self, task_id: str, arm: str, repetition: int) -> dict:
        task = self.tasks[task_id]
        cell = {"task_id": task_id, "arm": arm, "repetition": repetition,
                "cell_id": f"{task_id}.{arm}.r{repetition}", "_task": task}
        self.cells_executed.append(cell["cell_id"])
        run_dir = (self.batch_dir / task_id / arm / f"r{repetition}")
        started = time.perf_counter()
        # cell-private claude home, populated BEFORE the deny window opens
        claude_home = build_cell_claude_home(cell["cell_id"],
                                             self.runtime_output)
        if arm == "sqi":
            surface = prepare_sqi_cell(task, self.runtime_output)
            surface["run_dir"] = str(run_dir)
        else:
            surface = prepare_native_cell(task, self.runtime_output, self.config)
            surface["run_dir"] = str(run_dir)
        surface["environment"]["CLAUDE_CONFIG_DIR"] = str(claude_home)
        surface["claude_home"] = str(claude_home)
        window = self._window_factory(cell["cell_id"])
        session = None
        try:
            with window:
                session = self._session_fn(cell, surface, self.config)
                # C4-R1 backend provenance gate (fail-closed)
                backend = session.get("backend_model")
                if self.expected_backend is not None:
                    if not backend:
                        raise C4BatchHalted(
                            cell["cell_id"], HALT_EXECUTION,
                            "backend identity missing (no assistant model "
                            "reported by the CLI stream)")
                    if backend != self.expected_backend:
                        raise C4BatchHalted(
                            cell["cell_id"], HALT_EXECUTION,
                            f"backend drift: observed {backend!r} != "
                            f"reference {self.expected_backend!r}")
                leaks = classify_leakage(
                    leakage_events(session["events"], surface["repo_path"]))
                sensitive = [l for l in leaks if l["sensitive"]]
                if sensitive:
                    raise C4BatchHalted(
                        cell["cell_id"], HALT_LEAKAGE,
                        json.dumps(sensitive[:3], ensure_ascii=False))
        except C4BatchHalted:
            self._persist_halt_artifacts(cell, surface, run_dir, window, session)
            raise
        except RuntimeError as exc:
            reason = _classify_exit_failure(window)
            self._persist_halt_artifacts(cell, surface, run_dir, window, session, exc)
            raise C4BatchHalted(cell["cell_id"], reason, repr(exc)[:300]) from exc
        except Exception as exc:
            self._persist_halt_artifacts(cell, surface, run_dir, window, session, exc)
            raise C4BatchHalted(cell["cell_id"], HALT_UNEXPECTED,
                                repr(exc)[:300]) from exc
        # R1: the window edge already verified restore + fingerprints; the
        # runner re-asserts the recorded verdict before accepting the cell.
        restored = (window.state.get("restore_verified") or {}).get("restored")
        if not restored:
            reason = _classify_exit_failure(window)
            raise C4BatchHalted(cell["cell_id"], reason,
                                "post-exit R1 assertion failed")
        # Post-restore only: read + archive the bridge call log (it lives
        # outside the deny window at this point).
        session["call_log"] = collect_call_log(surface, run_dir)
        return self._record_cell(cell, surface, session, window, leaks,
                                 run_dir, started)

    def run_batch(self, cells: list[dict]) -> list[dict]:
        records = []
        for cell in cells:
            try:
                records.append(self.run_cell(cell["task_id"], cell["arm"],
                                             cell["repetition"]))
                print(json.dumps({"cell": records[-1]["cell_id"],
                                  "status": records[-1]["status"]}), flush=True)
            except C4BatchHalted as halt:
                self._write_halt_marker(halt, records)
                raise
        return records

    # -- persistence ----------------------------------------------------

    def _persist_halt_artifacts(self, cell, surface, run_dir, window,
                                session=None, exc=None):
        """Post-restore best-effort persistence for a halted cell: the window
        has already closed and verified restore, so checkout reads are safe."""
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "window-state.json").write_text(
                json.dumps(window.state, ensure_ascii=False, indent=1,
                           default=str) + "\n", encoding="utf-8")
            if session is not None:
                (run_dir / "events.ndjson").write_text(
                    "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True)
                              for e in session.get("events", [])) + "\n",
                    encoding="utf-8")
                (run_dir / "agent-output.txt").write_text(
                    session.get("output", ""), encoding="utf-8")
                try:
                    session["call_log"] = collect_call_log(surface, run_dir)
                except OSError:
                    pass
            if exc is not None:
                (run_dir / "halt-exception.txt").write_text(
                    repr(exc), encoding="utf-8")
        except OSError:
            pass

    def _write_halt_marker(self, halt: C4BatchHalted, records: list[dict]):
        marker = {
            "schema": "SQI_C4_BATCH_STATUS_MARKER_V1",
            "batch_id": self.batch_id, "halted": True,
            "halted_at_cell": halt.cell_id, "reason": halt.reason,
            "detail": halt.detail[:400],
            "cells_completed": sum(1 for r in records
                                   if r["status"] == "completed"),
            "isolation_baseline_sha": ISOLATION_BASELINE_SHA,
            "git_head": _git("rev-parse", "HEAD").strip(),
            "cells_executed": self.cells_executed,
        }
        (self.batch_dir / "batch-status-marker.json").write_text(
            json.dumps(marker, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def _record_cell(self, cell, surface, session, window, leaks, run_dir,
                     started) -> dict:
        task = cell["_task"]
        database = surface.get("database")
        evaluation = self._evaluate_fn(task, cell["arm"], session["output"],
                                       session["events"], session["call_log"],
                                       database)
        violations = [f"CHECKOUT_LEAKAGE:{l['reason']}:{l['target'][:100]}"
                      for l in leaks if l["sensitive"]]
        sensitive_count = sum(1 for l in leaks if l["sensitive"])
        wv = window.state.get("window_closed_verified") or {}
        status = ("completed" if session["exit_reason"] == "completed"
                  and not violations else "failed")
        record = {
            "schema": "SQI_FORMAL_RUN_RECORD_V1",
            "run_kind": "c4-after-optimization",
            "batch_id": self.batch_id,
            "cell_id": cell["cell_id"],
            "run_id": f"C4-{cell['cell_id']}-{uuid.uuid4().hex[:6]}",
            "task_id": cell["task_id"], "arm": cell["arm"],
            "repetition": cell["repetition"],
            "repository": task["repository"], "commit": task["commit"],
            "database": task["database"],
            "model_id": self.config["model_id"],
            "status": status,
            "exit_reason": session["exit_reason"],
            "task_success": evaluation.get("task_success"),
            "capability_failure_flags": evaluation.get(
                "capability_failure_flags", []),
            "tool_calls": len(session["events"]),
            "sqi_calls": len(session["call_log"]),
            "policy_violations": violations,
            "checkout_leakage_events": len(leaks),
            "sensitive_leakage_events": sensitive_count,
            "prompt_hash": hashlib.sha256(
                task["prompt"].encode("utf-8")).hexdigest(),
            "isolation": {
                "profile": "V1.4-Windows Finite-Root Isolation Profile",
                "baseline_sha": ISOLATION_BASELINE_SHA,
                "window_closed_verified": wv.get("closed"),
                "restore_verified": (window.state.get("restore_verified") or {})
                .get("restored"),
                "fingerprint_unchanged": (
                    window.state.get("post_repos") == window.state.get("pre_repos")
                    and window.state.get("post_dbs") == window.state.get("pre_dbs")),
                "claude_config_dir": "cell-private (runtime claude-homes/, "
                                     "host store untouched; containment "
                                     "repair e31e324 lineage)",
                "claude_home_files": sorted(p.name for p in Path(
                    surface.get("claude_home", "")).glob("*"))
                if surface.get("claude_home") else [],
                "model_provenance": {
                    "requested_model_id": self.config["model_id"],
                    "init_reported_model": session.get("actual_model"),
                    "backend_model": session.get("backend_model"),
                    "reference_backend": self.expected_backend,
                    "backend_verified": bool(
                        session.get("backend_model")
                        and (self.expected_backend is None
                             or session.get("backend_model")
                             == self.expected_backend)),
                },
            },
            "runtime_db_sha256": (sha256_file(database)
                                  if database and Path(database).exists() else None),
        }
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        (run_dir / "events.ndjson").write_text(
            "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True)
                      for e in session["events"]) + "\n", encoding="utf-8")
        (run_dir / "agent-output.txt").write_text(session["output"],
                                                  encoding="utf-8")
        if not (run_dir / "sqi-call-log.ndjson").exists():
            (run_dir / "sqi-call-log.ndjson").write_text(
                "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True)
                          for e in session["call_log"]) + "\n", encoding="utf-8")
        (run_dir / "evaluation.json").write_text(
            json.dumps(evaluation, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        (run_dir / "window-state.json").write_text(
            json.dumps(window.state, ensure_ascii=False, indent=1,
                       default=str) + "\n", encoding="utf-8")
        record["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return record


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_probe_stream(stdout: str) -> dict:
    """Parse one tiny claude -p --output-format stream-json session:
    returns the requested alias (init), the actually-served backend
    (first assistant message), the CLI version and the reply text."""
    requested = backend = version = None
    text = ""
    for line in (stdout or "").splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if value.get("type") == "system" and value.get("subtype") == "init":
            requested = value.get("model")
            version = value.get("claude_code_version")
        elif value.get("type") == "assistant":
            message_model = (value.get("message") or {}).get("model")
            if message_model and backend is None:
                backend = str(message_model)
        elif value.get("type") == "result":
            text = str(value.get("result") or "")
    return {"requested_model": requested, "backend_model": backend,
            "cli_version": version, "output": text.strip()[:80]}


def probe_backend(config: dict, cwd: Path) -> dict:
    """One minimal live session to identify the actually-served backend."""
    env = {**os.environ, "PL_MODEL_ID": config["model_id"]}
    completed = subprocess.run(
        [shutil.which("claude") or "claude", "-p", "Reply with exactly: ALIVE",
         "--verbose", "--output-format", "stream-json",
         "--model", config["model_id"]],
        cwd=str(cwd), capture_output=True, text=True, env=env, timeout=300)
    parsed = parse_probe_stream(completed.stdout or "")
    parsed["returncode"] = completed.returncode
    return parsed


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args],
                          capture_output=True, text=True).stdout


# -- preflight -------------------------------------------------------------

def run_preflight() -> dict:
    """C4 Attempt-4 environment gate. No sessions are executed."""
    checks: dict[str, object] = {}
    release = subprocess.run(
        [sys.executable, str(HERE / "verify_release.py")],
        capture_output=True, text=True, timeout=900)
    checks["release_verification"] = {
        "pass": release.returncode == 0,
        "tail": release.stdout.strip().splitlines()[-2:] if release.stdout else [],
    }
    checks["isolation_baseline_commit"] = {
        "sha": ISOLATION_BASELINE_SHA,
        "is_ancestor": subprocess.run(
            ["git", "-C", str(REPO_ROOT), "merge-base", "--is-ancestor",
             ISOLATION_BASELINE_SHA, "HEAD"]).returncode == 0,
        "pass": True,
    }
    checks["isolation_baseline_commit"]["pass"] = (
        checks["isolation_baseline_commit"]["is_ancestor"])
    runner_history = _git("log", "-1", "--format=%H", "--", RUNNER_PATH).strip()
    lifecycle_history = _git("log", "-1", "--format=%H", "--",
                             LIFECYCLE_PATH).strip()
    checks["runner_commit_recorded"] = {
        "runner_last_commit": runner_history,
        "lifecycle_last_commit": lifecycle_history,
        "present": bool(runner_history),
    }
    config = load_config()
    baseline = json.loads(BASELINE_SUMMARY.read_text(encoding="utf-8"))
    checks["model_config_matches_baseline"] = {
        "model_id": {"config": config["model_id"],
                     "baseline": baseline["model_id"],
                     "match": config["model_id"] == baseline["model_id"]},
        "claude_cli_version": {"config": config["claude_cli_version"],
                               "baseline": baseline.get("claude_cli_version"),
                               "match": config["claude_cli_version"]
                               == baseline.get("claude_cli_version")},
        "repetitions_per_cell": {"config": config["repetitions_per_cell"],
                                 "baseline": baseline["repetitions_per_cell"],
                                 "match": int(config["repetitions_per_cell"])
                                 == int(baseline["repetitions_per_cell"])},
    }
    order = frozen_cell_order(config, load_tasks())
    checks["cell_order_frozen"] = {
        "cell_total": len(order),
        "expected_total": int(config["cell_total"]),
        "total_match": len(order) == int(config["cell_total"]),
        "order_fingerprint": order_fingerprint(order),
    }
    baseline_files = {}
    for rel in ("formal-batch-summary.json", "cost-attribution-v1.json",
                "c2-replay-verification-v1.json", "manifest.sha256"):
        path = BASELINE_BATCH_DIR / rel
        baseline_files[rel] = {"exists": path.exists(),
                               "sha256": sha256_file(path) if path.exists()
                               else None}
    manifest_ok = verify_batch_manifest(BASELINE_MANIFEST)
    checks["baseline_evidence_unchanged"] = {
        "files": baseline_files,
        "manifest_roundtrip": manifest_ok,
        "pass": manifest_ok and all(v["exists"] for v in baseline_files.values()),
    }
    checks["optimized_implementation_frozen"] = {
        "implementation_seal": "structured-query-interface-contract-v1."
                               "implementation-seal.sha256",
        "verified_via": "release_verification stage (PASS 5/5)",
        "pass": checks["release_verification"]["pass"],
    }
    status = subprocess.run(["git", "-C", str(REPO_ROOT), "status",
                             "--porcelain"], capture_output=True, text=True)
    dirty = [l for l in status.stdout.splitlines() if l.strip()
             and "C4-PREFLIGHT-" not in l]
    checks["working_tree_clean"] = {
        "pass": not dirty,
        "dirty_entries": dirty[:10],
        "self_generated_ignored": [l for l in status.stdout.splitlines()
                                   if "C4-PREFLIGHT-" in l][:5],
    }
    probe = probe_backend(config, REPO_ROOT)
    checks["backend_probe"] = {
        "pass": bool(probe["backend_model"]),
        "requested_model_id": config["model_id"],
        "init_reported_model": probe["requested_model"],
        "backend_model": probe["backend_model"],
        "cli_version": probe["cli_version"],
    }
    all_pass = all(v.get("pass", True) if isinstance(v, dict) else v
                   for v in checks.values())
    if isinstance(checks["model_config_matches_baseline"], dict):
        all_pass = all_pass and all(
            v["match"] for v in checks["model_config_matches_baseline"].values())
    if isinstance(checks["cell_order_frozen"], dict):
        all_pass = all_pass and checks["cell_order_frozen"]["total_match"]
    doc = {
        "schema": "SQI_C4_PREFLIGHT_EVIDENCE_V1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "isolation_baseline_sha": ISOLATION_BASELINE_SHA,
        "runner_commit": checks["runner_commit_recorded"]["runner_last_commit"],
        "head_at_preflight": _git("rev-parse", "HEAD").strip(),
        "backend_reference": probe["backend_model"],
        "checks": checks,
        "verdict": "PASS" if all_pass else "FAIL",
    }
    return doc


def verify_batch_manifest(manifest_path: Path) -> bool:
    """Round-trip a sha256 manifest whose entries are relative to its own
    directory (baseline batch manifests), unlike repo-rooted verify_seal."""
    import re
    pattern = re.compile(r"^([a-f0-9]{64})\s+\*?(.+?)\s*$")
    base = manifest_path.parent
    ok = True
    for line in manifest_path.read_text(encoding="utf-8-sig").splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        expected, rel = match.group(1), match.group(2).replace("\\", "/")
        target = base / rel
        if not target.exists() or hashlib.sha256(
                target.read_bytes()).hexdigest() != expected:
            ok = False
            break
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "batch", "probe"),
                        default="preflight")
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--probe-count", type=int, default=4)
    args = parser.parse_args()

    if args.mode == "probe":
        config = load_config()
        probes = [probe_backend(config, REPO_ROOT) for _ in
                  range(max(1, args.probe_count))]
        backends = [p["backend_model"] for p in probes]
        stable = all(b and b == backends[0] for b in backends)
        doc = {
            "schema": "SQI_C4_BACKEND_PROBE_EVIDENCE_V1",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "requested_model_id": config["model_id"],
            "probe_count": len(probes),
            "probes": probes,
            "backends_observed": sorted(set(b or "None" for b in backends)),
            "stable": stable,
            "verdict": "STABLE" if stable else "DRIFT",
        }
        out = (LINE_ROOT / "results" / "formal" /
               f"C4-BACKEND-PROBE-{time.strftime('%Y%m%d-%H%M%S')}.json")
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
        print(json.dumps({"verdict": doc["verdict"],
                          "backends_observed": doc["backends_observed"],
                          "evidence": str(out)}, indent=1))
        return 0 if stable else 1

    if args.mode == "preflight":
        doc = run_preflight()
        out_dir = LINE_ROOT / "results" / "formal"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"C4-PREFLIGHT-{time.strftime('%Y%m%d-%H%M%S')}.json"
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
        print(json.dumps({"verdict": doc["verdict"], "evidence": str(out)},
                         indent=1))
        return 0 if doc["verdict"] == "PASS" else 1

    # batch
    doc = run_preflight()
    if doc["verdict"] != "PASS":
        print(json.dumps(doc["checks"], indent=1)[:2000])
        print("C4 preflight FAIL — batch not started")
        return 1
    config = load_config()
    tasks = load_tasks()
    batch_id = args.batch_id or time.strftime("SQI-FORMAL-C4-%Y%m%dT%H%M%SZ",
                                              time.gmtime())
    batch_dir = LINE_ROOT / "results" / "formal" / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    build_runtime({t["task_id"]: task_db_rels(t) for t in tasks})
    runner = C4BatchRunner(config, tasks, batch_id, batch_dir,
                           expected_backend=doc.get("backend_reference"))
    cells = frozen_cell_order(config, tasks)
    try:
        records = runner.run_batch(cells)
    except C4BatchHalted as halt:
        print(json.dumps({"batch_id": batch_id, "halted": True,
                          "cell": halt.cell_id, "reason": halt.reason},
                         indent=1))
        return 1
    summary = {
        "schema": "SQI_C4_BATCH_SUMMARY_V1", "batch_id": batch_id,
        "isolation_baseline_sha": ISOLATION_BASELINE_SHA,
        "cells_total": len(cells),
        "cells_completed": sum(1 for r in records if r["status"] == "completed"),
    }
    (batch_dir / "batch-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0 if summary["cells_completed"] == len(cells) else 1


if __name__ == "__main__":
    raise SystemExit(main())

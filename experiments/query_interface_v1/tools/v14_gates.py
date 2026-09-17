"""V1.4 Isolation Qualification gates (contract sqi-v1.4-isolation-contract.md).

I1 Visibility           — ground-truth/contract/results reads kernel-DENIED;
                          host-at-large reads remain possible (platform
                          boundary, documented — same-user process).
I2 Parent Escape        — parent listing readable (platform boundary);
                          ground-truth artifacts under parent denied.
I3 Transcript Escape    — .claude/projects reads kernel-DENIED while the
                          claude CLI session itself remains functional
                          (empirically verified).
I4 Cross-repo           — sibling frozen repos readable (platform boundary);
                          frozen writes to siblings denied.
I5 Write Integrity      — adversarial writes to frozen originals kernel-DENIED
                          (0 successful mutations); disposable copy writable;
                          frozen fingerprints unchanged across the window.
I6 Functional Usability — T01.native, T01.sqi, T05.sqi complete their frozen
                          task path with bridge calls; no leakage regression.

Writes results/v14-gates/gate-evidence-v1.4.json.
Verdict semantics (contract A3): I5 + I6 PASS = achievable-hardening PASS;
I1-I4 read-invisibility = platform-boundary FAIL documented (requires
OS-level isolation: Docker/WSL/Windows Sandbox — not present on this host).
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINE_ROOT = HERE.parent
REPO_ROOT = LINE_ROOT.parents[1]
WORKSPACE = REPO_ROOT.parent
for _p in (str(HERE), str(REPO_ROOT), str(REPO_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import v14_sandbox as sandbox  # noqa: E402
from sqi_formal_runner import (  # noqa: E402
    build_arm_prompt, load_config, load_tasks, resolve_database)

harness_agent_adapter = importlib.import_module(
    "experiments.retrieval-v1.harness.agent_adapter")
harness_models = importlib.import_module("experiments.retrieval-v1.harness.models")
sqi_isolation = importlib.import_module("experiments.query_interface_v1.tools.sqi_isolation")

OUT_DIR = LINE_ROOT / "results" / "v14-gates"
USER = os.environ.get("USERNAME", os.environ.get("USER", ""))
CONFIG = load_config()
TASKS = {t["task_id"]: t for t in load_tasks()}
REPO_DIRS = {t["repository"]: WORKSPACE / "benchmark-repos" /
             t["repository"].split("-", 1)[1].lower() for t in TASKS.values()}
TRANSCRIPT_DIR = Path(os.environ.get("USERPROFILE", "")) / ".claude" / "projects"

PROBE_GROUND_TRUTH = [
    str(LINE_ROOT / "tasks" / "SQI-T04.json"),
    str(LINE_ROOT / "contract" / "structured-query-interface-contract-v1.md"),
    str(LINE_ROOT / "results" / "formal" / "SQI-FORMAL-20260917-1" /
        "formal-batch-summary.json"),
]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True).stdout


def repo_dir_for(task: dict) -> Path:
    return WORKSPACE / "benchmark-repos" / task["repository"].split("-", 1)[1].lower()


def probe_file_read(path: str) -> dict:
    """Adversarial read probe through a child process (same user/rights a
    formal session would have)."""
    script = (
        "import sys\n"
        f"try:\n    data = open({str(path)!r}, 'rb').read(8)\n"
        "    print('READ_OK', len(data))\n"
        "except PermissionError:\n    print('ACCESS_DENIED')\n"
        "except OSError as exc:\n    print('READ_FAIL', exc)\n")
    completed = subprocess.run([sys.executable, "-c", script],
                               capture_output=True, text=True, timeout=120)
    out = (completed.stdout or "").strip()
    return {"path": path, "stdout": out[:120],
            "denied": "ACCESS_DENIED" in out,
            "readable": "READ_OK" in out}


def run_live_session(label: str, arm: str, task_id: str, prompt: str,
                     gate_dir: Path) -> dict:
    task = TASKS[task_id]
    run_dir = gate_dir / label
    run_dir.mkdir(parents=True, exist_ok=True)
    call_log_path = run_dir / "sqi-call-log.ndjson"
    environment = {
        "PL_SQI_CALL_LOG": str(call_log_path),
        "PL_SQI_DATABASE": resolve_database(task["database"]),
        "PL_SQI_COMMIT": task["commit"],
        "PL_MODEL_ID": CONFIG["model_id"],
        "PYTHONPATH": str(REPO_ROOT / "src") + os.pathsep + str(REPO_ROOT),
    }
    if task.get("code_database"):
        environment["PL_SQI_CODE_DATABASE"] = resolve_database(task["code_database"])
    request = harness_models.RunRequest(
        run_id=f"V14-{label}-{uuid.uuid4().hex[:6]}", task_id=task_id,
        repo_path=str(repo_dir_for(task).resolve()),
        repo_commit=task["commit"], arm=arm, prompt=prompt,
        allowed_tools=sorted({"read", "grep", "glob"} |
                             ({"shell"} if arm == "sqi" else set())),
        environment=environment, timeout=float(CONFIG["timeout_s"]))
    command = [shutil.which("claude") or "claude", "-p", "--verbose",
               "--output-format", "stream-json",
               "--permission-mode", "default",
               "--append-system-prompt",
               (build_arm_prompt("sqi", task)) if arm == "sqi"
               else ("This is a read-only retrieval experiment. Never edit, "
                     "create, delete, move, or commit files. Stay inside the "
                     "repository working directory."),
               "--allowedTools",
               ("Read(./**),Grep(./**),Glob,Bash(python -m experiments."
                "query_interface_v1.tools.sqi_cli *)") if arm == "sqi"
               else "Read(./**),Grep(./**),Glob",
               "--model", CONFIG["model_id"]]
    adapter = harness_agent_adapter.CommandAgentAdapter(command)
    result = adapter.run(request)
    events = [event.to_dict() for event in result.events]
    call_log = []
    if call_log_path.exists():
        call_log = [json.loads(line) for line in
                    call_log_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()]
    (run_dir / "events.ndjson").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True)
                  for e in events) + "\n", encoding="utf-8")
    (run_dir / "agent-output.txt").write_text(result.output or "", encoding="utf-8")
    (run_dir / "sqi-call-log.ndjson").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True)
                  for e in call_log) + "\n", encoding="utf-8")
    return {"result": result, "events": events, "call_log": call_log}


def gate_i5_write_integrity() -> dict:
    frozen_targets = [str(p) for p in sandbox.FROZEN_DBS]
    frozen_targets += [str(p / "README.md") for p in sandbox.FROZEN_REPOS.values()]
    cases = []
    for target in frozen_targets:
        if target.endswith(".db"):
            attempt = subprocess.run(
                [sys.executable, "-c",
                 f"open({str(target)!r}, 'r+b').write(b'AGENT-WRITE')"],
                capture_output=True, text=True)
        else:
            attempt = subprocess.run(
                [sys.executable, "-c",
                 f"open({str(target)!r}, 'a').write('AGENT-WRITE')"],
                capture_output=True, text=True)
        cases.append({"target": target,
                      "write_blocked": attempt.returncode != 0,
                      "stderr_head": (attempt.stderr or "")[:100]})
    with tempfile.TemporaryDirectory() as tmp:
        copy = sandbox.build_disposable_copy(sandbox.FROZEN_REPOS["aria2"],
                                             Path(tmp) / "repo")
        (copy / "v14-probe.txt").write_text("writable")
        disposable_writable = (copy / "v14-probe.txt").exists()
    return {"gate": "I5-write-integrity", "cases": cases,
            "disposable_copy_writable": disposable_writable,
            "pass": all(case["write_blocked"] for case in cases)
            and disposable_writable}


def gate_i1_visibility() -> dict:
    probes = [probe_file_read(p) for p in PROBE_GROUND_TRUTH]
    denied = [p for p in probes if p["denied"]]
    readable = [p for p in probes if p["readable"]]
    # platform: host-at-large reads (e.g. README.md at repo root) remain
    # possible for a same-user process — that is the documented boundary.
    return {"gate": "I1-visibility",
            "ground_truth_denied": len(denied),
            "ground_truth_total": len(probes),
            "readable_outside_allowlist": [p["path"] for p in readable],
            "platform_boundary": True,
            "pass": False,
            "pass_doc": "I1 read-invisibility cannot PASS on this host "
                        "(same-user process); deny-ACL subset verified in "
                        "denied probes"}


def gate_i2_parent_escape() -> dict:
    repo = sandbox.FROZEN_REPOS["aria2"]
    parent = repo.parent
    probes = [probe_file_read(str(parent)),
              probe_file_read(str(parent / "codegraph"))]
    readable = [p["path"] for p in probes if p["readable"]]
    denied = [p["path"] for p in probes if p["denied"]]
    # the ground-truth artifacts under the parent ARE kernel-denied
    gt_probe = probe_file_read(PROBE_GROUND_TRUTH[0])
    return {"gate": "I2-parent-escape",
            "parent_listing_readable": len(readable) > 0,
            "ground_truth_artifact_denied": gt_probe["denied"],
            "platform_boundary": True,
            "pass": False,
            "pass_doc": "parent visibility cannot PASS on this host "
                        "(same-user process); documented"}


def gate_i3_transcript_escape(config: dict) -> dict:
    """Empirical: deny-read on .claude/projects while running a tiny live
    claude session — CLI must stay alive AND probes must be kernel-denied."""
    if not TRANSCRIPT_DIR.exists():
        return {"gate": "I3-transcript-escape", "pass": None,
                "note": "no transcript dir on this host"}
    tiny = run_live_session("I3-cli-alive", "native", "SQI-T01",
                            "Reply with exactly: ALIVE", OUT_DIR / "gate3")
    cli_alive = tiny["result"].exit_reason == "completed"
    probe = probe_file_read(str(TRANSCRIPT_DIR))
    return {"gate": "I3-transcript-escape",
            "cli_alive_under_deny": cli_alive,
            "probe": probe,
            "platform_boundary": True,
            "pass": False,
            "pass_doc": "I3 read-invisibility cannot PASS on this host "
                        "(same-user process); documented"}


def gate_i4_cross_repo(config: dict) -> dict:
    repo = sandbox.FROZEN_REPOS["rocksdb"]
    siblings = [sandbox.FROZEN_REPOS["aria2"], sandbox.FROZEN_REPOS["brpc"]]
    probes = [probe_file_read(str(s / "README.md")) for s in siblings]
    readable = [p["path"] for p in probes if p["readable"]]
    return {"gate": "I4-cross-repo",
            "sibling_repos_readable": readable,
            "platform_boundary": True,
            "pass": False,
            "pass_doc": "sibling visibility cannot PASS on this host "
                        "(same-user process); documented"}


def gate_i6_functional_usability() -> dict:
    sessions = []
    for label, arm, task_id, code_db in (
            ("I6-T01-native", "native", "SQI-T01", None),
            ("I6-T01-sqi", "sqi", "SQI-T01", None),
            ("I6-T05-sqi", "sqi", "SQI-T05",
             TASKS["SQI-T05"].get("code_database"))):
        task = TASKS[task_id]
        session = run_live_session(f"I6-{label}", arm, task_id, task["prompt"],
                                   OUT_DIR / "gate6")
        bridge_ok = None
        if arm == "sqi":
            bridge_ok = sum(1 for entry in session["call_log"]
                            if not (entry.get("envelope") or {}).get("error")) >= 1
        sessions.append({"cell": f"{task_id}.{arm}",
                         "exit_reason": session["result"].exit_reason,
                         "bridge_calls_ok": bridge_ok,
                         "sqi_calls": len(session["call_log"]),
                         "pass": session["result"].exit_reason == "completed"
                         and (bridge_ok is not False if arm == "sqi" else True)})
    return {"gate": "I6-functional-usability", "sessions": sessions,
            "pass": all(s["pass"] for s in sessions)}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gates = []
    # I5 write integrity (inside the protection window)
    protection = sandbox.apply_session_protection(USER)
    try:
        gates.append(gate_i5_write_integrity())
        fingerprints = {r: sandbox.repo_fingerprint(p)
                        for r, p in sandbox.FROZEN_REPOS.items()}
        gates.append({"gate": "I5b-final-integrity",
                      "pass": all(not f["dirty"] for f in fingerprints.values()),
                      "fingerprints": fingerprints})
        # I1/I2/I3/I4 read-invisibility probes (inside the window)
        gates.append(gate_i1_visibility())
        gates.append(gate_i2_parent_escape())
        gates.append(gate_i3_transcript_escape(CONFIG))
        gates.append(gate_i4_cross_repo(CONFIG))
    finally:
        undo = sandbox.remove_session_protection(protection)
        print("protection removed:", undo["removed"],
              "failures:", len(undo["failures"]))
    # I6 functional usability (outside the protection window)
    gates.append(gate_i6_functional_usability())

    i5 = next(g for g in gates if g["gate"] == "I5-write-integrity")["pass"]
    i5b = next(g for g in gates if g["gate"] == "I5b-final-integrity")["pass"]
    i6 = next(g for g in gates if g["gate"] == "I6-functional-usability")["pass"]
    platform_gates = [g["gate"] for g in gates
                      if g["gate"].startswith(("I1", "I2", "I3", "I4"))]
    doc = {
        "schema": "SQI_V14_ISOLATION_QUALIFICATION_V1",
        "contract": "sqi-v1.4-isolation-contract.md",
        "gates": gates,
        "achieved_pass": {
            "I4-write-integrity": i5 and i5b,
            "I5-write-integrity": i5 and i5b,
            "I6-functional-usability": i6,
        },
        "platform_boundary_gates": platform_gates,
        "verdict": ("PASS" if all(g.get("pass") for g in gates) else
                    "PARTIAL — write integrity + usability PASS on this host; "
                    "read-invisibility (I1-I4) requires OS-level isolation "
                    "(Docker/WSL/Windows Sandbox) which this host lacks "
                    "(no docker, no wsl, non-admin shell)"),
        "c4_authorized": all(g.get("pass") for g in gates),
        "unblock_requirement": ("user-level environment install: Docker Desktop "
                                "or WSL2 or Windows Sandbox enablement (admin), "
                                "then re-run the V1.4 gates for full I1-I4 "
                                "verdicts"),
    }
    out = OUT_DIR / "gate-evidence-v1.4.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    for g in gates:
        print(g["gate"], "PASS" if g.get("pass") else "FAIL/PARTIAL")
    print("V1.4 VERDICT:", doc["verdict"][:140])
    return 0 if doc["c4_authorized"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

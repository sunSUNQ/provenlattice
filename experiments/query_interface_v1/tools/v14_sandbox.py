"""V1.4 sandbox builder: the achievable hard-isolation layer on this host.

Per formal cell (contract sqi-v1.4-isolation-contract.md A2):
  1. disposable repo copy (agent cwd), discarded at cell end;
  2. kernel-level DENY-WRITE ACLs on the frozen originals (repos + DBs +
     lock/seal dirs) for the session window;
  3. kernel-level DENY-READ ACLs on high-value artifacts (tasks/contract/
     formal results/quarantine) for the session window;
  4. restore: remove all deny ACEs, verify HEAD/clean/fingerprint.

Non-admin safe: icacls /deny and /remove are owner rights on user-owned files.
The deny-READ scope deliberately excludes the frozen databases (the SQI bridge
needs read access) - database reads stay detection-only (documented).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = REPO_ROOT.parent
USER = os.environ.get("USERNAME", os.environ.get("USER", ""))

FROZEN_REPOS = {r: WORKSPACE / "benchmark-repos" / r for r in ("aria2", "brpc", "rocksdb")}
FROZEN_DBS = [
    WORKSPACE / "benchmark-analysis" / "v0.2-db" / "aria2.db",
    WORKSPACE / "benchmark-analysis" / "v0.2-db" / "brpc.db",
    WORKSPACE / "benchmark-analysis" / "v0.2-db" / "rocksdb.db",
    WORKSPACE / "benchmark-analysis" / "v1.0-db" / "brpc-knowledge.db",
]
DENY_READ_ARTIFACTS = [
    REPO_ROOT / "experiments" / "query_interface_v1" / "tasks",
    REPO_ROOT / "experiments" / "query_interface_v1" / "contract",
    REPO_ROOT / "experiments" / "query_interface_v1" / "results",
    REPO_ROOT / "experiments" / "query_interface_v1" / "reviews",
]


def _icacls(path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["icacls", path, *args], capture_output=True, text=True)


def apply_session_protection(user: str | None = None) -> dict:
    """Deny-write on frozen originals + deny-read on high-value artifacts.
    Returns an undo record for remove_session_protection()."""
    user = user or USER
    if not user:
        raise RuntimeError("cannot resolve session user for ACLs")
    applied = {"user": user, "deny_write": [], "deny_read": []}
    for repo, root in FROZEN_REPOS.items():
        result = _icacls(str(root), "/deny", f"{user}:(WD,AD,WA)", "/T", "/C")
        applied["deny_write"].append({"path": str(root), "rc": result.returncode})
    for db in FROZEN_DBS:
        result = _icacls(str(db), "/deny", f"{user}:(WD,AD,WA)")
        applied["deny_write"].append({"path": str(db), "rc": result.returncode})
    for artifact in DENY_READ_ARTIFACTS:
        if artifact.exists():
            result = _icacls(str(artifact), "/deny", f"{user}:(R)", "/T", "/C")
            applied["deny_read"].append({"path": str(artifact), "rc": result.returncode})
    return applied


def remove_session_protection(record: dict) -> dict:
    """Remove every deny ACE applied by apply_session_protection."""
    results = []
    for entry in record.get("deny_write", []) + record.get("deny_read", []):
        result = _icacls(entry["path"], "/remove:d", record["user"])
        results.append({"path": entry["path"], "rc": result.returncode})
    return {"removed": len(results), "failures": [r for r in results if r["rc"] != 0]}


def build_disposable_copy(repo: Path, target: Path) -> Path:
    """Robocopy the frozen repo into the per-cell sandbox (exclude .git)."""
    result = subprocess.run(
        ["robocopy", str(repo), str(target), "/E", "/NFL", "/NDL", "/NJH",
         "/XJ", "XD", ".git"],
        capture_output=True, text=True)
    # robocopy exit codes 0-7 are success
    if result.returncode > 7:
        raise RuntimeError(f"robocopy failed rc={result.returncode}: {result.stderr[:400]}")
    return target


def repo_fingerprint(repo: Path) -> dict:
    """HEAD + worktree dirtiness snapshot (post-session integrity check)."""
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                            capture_output=True, text=True).stdout
    return {"head": head, "dirty": bool(status.strip())}


def file_fingerprint(path: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

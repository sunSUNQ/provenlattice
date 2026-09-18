"""V1.4-Windows Finite-Root Isolation Profile — formal-cell lifecycle.

Frozen by amendment `sqi-v1.4-finite-root-isolation-amendment.md` (2026-09-18).
This module is the ONLY sanctioned way a C4 formal cell acquires its sandbox:

  CellWindow  — fail-closed deny-window context manager:
                enter → pre-fingerprints + apply (OI)(CI)R deny window +
                verify closed (abort if not kernel-closed);
                exit → remove all deny ACEs + verify reads restored +
                fingerprints/DB hashes unchanged (raise on any mismatch).
  prepare_cell— per-task sanitized runtime paths (disposable copy, byte-copy
                DBs, env, arm prompt, allowlist) for the session builder.
  classify_leakage — finite-root classification of CHECKOUT_LEAKAGE events:
                SENSITIVE = references any path outside the sanitized runtime
                root (toward the checkout / transcripts / workspace).

Threat model (frozen, narrow): experiment-artifact isolation. DENIED at NTFS
kernel level: the whole provenlattice checkout, the historical transcript
store, and writes to frozen originals. NOT claimed: full OS-namespace
isolation — host-at-large reads by the same user remain possible and are
documented (amendment §1).

Reusable machinery (deny apply/remove, runtime build, probes, sanitized arm
prompt) is imported unchanged from v14_feasibility_noreboot so the sealed
feasibility evidence and the formal lifecycle share one implementation.
"""
from __future__ import annotations

from pathlib import Path

from v14_feasibility_noreboot import (  # noqa: F401
    BENCH, CHECKOUT, FEASIBILITY_REPOS, OUT_RUNTIME, RUNTIME, RUNTIME_DB,
    RUNTIME_ROOT, SQI_ALLOWED_TOOLS, TRANSCRIPT_STORE, USER, apply_deny,
    bridge_smoke, build_runtime, probe, remove_deny, repo_state, runtime_db_for,
    sanitized_arm_prompt, sha256, task_db_rels, write_probe)
from v14_sandbox import FROZEN_DBS, FROZEN_REPOS  # noqa: F401

WINDOW_READ_DENY = "(OI)(CI)(RD)"  # P7: (RD), not (R) — keeps ACL repairable
WINDOW_WRITE_DENY = "(OI)(CI)(WD,AD,WA)"
WRITE_DENY_FILE = "(WD,AD,WA)"

VERIFY_CLOSED_PROBES = (
    ("checkout_root_readme", str(CHECKOUT / "README.md")),
    ("tasks_fixture", str(CHECKOUT / "experiments" / "query_interface_v1" /
                          "tasks" / "SQI-T04.json")),
    ("git_head", str(CHECKOUT / ".git" / "HEAD")),
)


def classify_leakage(leaks: list[dict], runtime_root: Path | str = RUNTIME_ROOT) -> list[dict]:
    """Finite-root classification: an event is SENSITIVE iff it references a
    path outside the sanitized runtime root or a framework-sensitive string
    (codegraph checkout / .claude store)."""
    import os
    import re
    abs_re = re.compile(r"([A-Za-z]:[/\\][^\s\"']*)", re.IGNORECASE)
    root = str(runtime_root).lower()
    out = []
    for lk in leaks or []:
        sensitive = False
        for m in abs_re.finditer(str(lk.get("target") or "")):
            candidate = os.path.abspath(m.group(1).lower())
            if not candidate.startswith(root):
                sensitive = True
                break
        hinted = any(h in str(lk.get("target") or "").lower()
                     for h in ("codegraph", "provenlattice", ".claude"))
        out.append({**lk, "sensitive": bool(sensitive or hinted)})
    return out


class CellWindow:
    """Per-formal-cell deny window (amendment §2). Fail-closed on both edges."""

    def __init__(self, label: str = "cell"):
        self.label = label
        self.state: dict = {"label": label, "applied": [], "removed": [],
                            "pre_repos": {}, "post_repos": {}, "pre_dbs": {},
                            "post_dbs": {}, "window_closed_verified": None,
                            "restore_verified": None}

    def _apply_list(self):
        specs = [(CHECKOUT, WINDOW_READ_DENY)]
        if TRANSCRIPT_STORE.exists():
            specs.append((TRANSCRIPT_STORE, WINDOW_READ_DENY))
        specs += [(repo, WINDOW_WRITE_DENY) for repo in FROZEN_REPOS.values()]
        specs += [(db, WRITE_DENY_FILE) for db in FROZEN_DBS]
        return specs

    def __enter__(self) -> "CellWindow":
        self.state["pre_repos"] = {r: repo_state(p) for r, p in FROZEN_REPOS.items()}
        self.state["pre_dbs"] = {str(db): sha256(db) for db in FROZEN_DBS}
        applied = []
        for spec_path, rights in self._apply_list():
            record = apply_deny(spec_path, rights)
            applied.append(record)
            if record["rc"] != 0:
                self._cleanup(applied)
                raise RuntimeError(
                    f"CellWindow apply failed rc={record['rc']} on {spec_path}: "
                    f"{record['stderr'][:120]}")
        self.state["applied"] = applied
        verify = {name: probe(path) for name, path in VERIFY_CLOSED_PROBES}
        closed = all(p["denied"] for p in verify.values())
        self.state["window_closed_verified"] = {"probes": verify, "closed": closed}
        if not closed:
            self._cleanup(applied)
            raise RuntimeError(f"CellWindow failed to close: {verify}")
        return self

    def _cleanup(self, applied):
        for record in applied:
            remove_deny(Path(record["path"]))

    def __exit__(self, exc_type, exc, tb) -> bool:
        removed = [remove_deny(Path(record["path"]))
                   for record in self.state["applied"]]
        restore = {name: probe(path) for name, path in VERIFY_CLOSED_PROBES}
        # P7 insurance: retry one removal pass if any read is still denied
        if any(p["denied"] for p in restore.values()):
            import time
            time.sleep(0.5)
            removed += [remove_deny(Path(record["path"]))
                        for record in self.state["applied"]]
            restore = {name: probe(path) for name, path in VERIFY_CLOSED_PROBES}
        self.state["removed"] = removed
        self.state["post_repos"] = {r: repo_state(p) for r, p in FROZEN_REPOS.items()}
        self.state["post_dbs"] = {str(db): sha256(db) for db in FROZEN_DBS}
        restored = (all(p["readable"] for p in restore.values())
                    and all(r["rc"] == 0 for r in removed)
                    and self.state["post_repos"] == self.state["pre_repos"]
                    and self.state["post_dbs"] == self.state["pre_dbs"])
        self.state["restore_verified"] = {"probes": restore, "restored": restored}
        if not restored:
            raise RuntimeError(
                f"CellWindow restore integrity FAILURE: {self.state}")
        return False


def prepare_cell(task: dict, batch_output: Path) -> dict:
    """Sanitized per-cell execution surface for the session builder."""
    database, code_database = runtime_db_for(task)
    label = f"{task['task_id']}-sqi"
    environment = {
        "PL_SQI_PROTOCOL": "1",
        "PL_SQI_CALL_LOG": str(batch_output / label / "sqi-call-log.ndjson"),
        "PL_SQI_DATABASE": database,
        "PL_SQI_COMMIT": task["commit"],
        "PYTHONPATH": str(RUNTIME / "src") + ";" + str(RUNTIME),
    }
    if code_database:
        environment["PL_SQI_CODE_DATABASE"] = code_database
    repo_name = task["repository"].split("-", 1)[1].lower()
    return {
        "label": label,
        "repo_path": str(BENCH / repo_name),
        "database": database,
        "code_database": code_database,
        "environment": environment,
        "arm_prompt": sanitized_arm_prompt(task, database, code_database),
        "allowed_tools": SQI_ALLOWED_TOOLS,
    }

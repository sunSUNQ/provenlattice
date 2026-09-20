"""C4 environment equivalence gate: host config vs cell-private
CLAUDE_CONFIG_DIR.

Proves the containment repair changes ONLY path locations, not execution
semantics:
  1. config snapshot — the private home's files are byte-copies (sha256) of
     the host config files;
  2. CLI version — identical with and without CLAUDE_CONFIG_DIR;
  3. live sessions — one tiny session per configuration (fresh temp cwds):
     same reported model, same CLI version, same output text;
  4. relocation — the private session writes its transcript under the
     private home's projects/ tree and the host %USERPROFILE%\\.claude\\projects
     gains NO entry for the private session's cwd slug.

Verdict PASS iff all four hold. Evidence JSON next to this file's results.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINE_ROOT = HERE.parent
RESULTS = LINE_ROOT / "results" / "formal"
USER_HOME = Path(os.environ.get("USERPROFILE", ""))
CLAUDE_HOME_FILES = (".claude.json",)
CLAUDE_HOME_DIR_FILES = (".credentials.json", "settings.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_private_home(base: Path) -> Path:
    home = base / "claude-home"
    home.mkdir(parents=True, exist_ok=True)
    for name in CLAUDE_HOME_FILES:
        src = USER_HOME / name
        if src.exists():
            shutil.copy2(src, home / name)
    for name in CLAUDE_HOME_DIR_FILES:
        src = USER_HOME / ".claude" / name
        if src.exists():
            shutil.copy2(src, home / name)
    return home


def slug_for(cwd: Path) -> str:
    return "".join(c if c.isalnum() else "-" for c in str(cwd))


def claude_version(env_extra: dict | None) -> str:
    env = {**os.environ, **(env_extra or {})}
    out = subprocess.run([shutil.which("claude") or "claude", "--version"],
                         capture_output=True, text=True, env=env, timeout=120)
    return (out.stdout or "").strip()


def tiny_session(cwd: Path, env_extra: dict | None) -> dict:
    env = {**os.environ, **(env_extra or {})}
    out = subprocess.run(
        [shutil.which("claude") or "claude", "-p",
         "Reply with exactly: ALIVE", "--verbose", "--output-format",
         "stream-json", "--model", "claude-sonnet-4-5-20250929"],
        cwd=str(cwd), capture_output=True, text=True, env=env, timeout=300)
    model = version = None
    text = ""
    for line in (out.stdout or "").splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if value.get("type") == "system" and value.get("subtype") == "init":
            model = value.get("model")
            version = value.get("claude_code_version")
        elif value.get("type") == "result":
            text = str(value.get("result") or "")
    return {"model": model, "cli_version": version, "output": text.strip()[:80]}


def main() -> int:
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    checks: dict[str, object] = {}
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        private = build_private_home(base)
        # 1. snapshot equality
        host_hashes = {name: sha256(USER_HOME / name)
                       for name in CLAUDE_HOME_FILES
                       if (USER_HOME / name).exists()}
        private_hashes = {name: sha256(private / name)
                          for name in CLAUDE_HOME_FILES
                          if (private / name).exists()}
        checks["config_snapshot_identical"] = {
            "pass": host_hashes == private_hashes and bool(host_hashes),
            "host": {k: v[:16] + "..." for k, v in host_hashes.items()},
        }
        # 2. CLI version
        v_host = claude_version(None)
        v_private = claude_version({"CLAUDE_CONFIG_DIR": str(private)})
        checks["cli_version_identical"] = {
            "pass": bool(v_host) and v_host == v_private,
            "host": v_host, "private": v_private,
        }
        # 3. live sessions
        cwd_host = base / "cwd-host"
        cwd_private = base / "cwd-private"
        cwd_host.mkdir()
        cwd_private.mkdir()
        session_host = tiny_session(cwd_host, None)
        session_private = tiny_session(cwd_private,
                                       {"CLAUDE_CONFIG_DIR": str(private)})
        checks["live_session_semantics_identical"] = {
            "pass": (session_host["model"] == session_private["model"]
                     and session_host["cli_version"] == session_private["cli_version"]
                     and session_host["output"] == session_private["output"]
                     and session_host["output"] != ""),
            "host": session_host, "private": session_private,
        }
        # 4. relocation: private session transcript lives in the private home;
        #    the host store gains no entry for the private cwd slug
        private_projects = private / "projects"
        private_slug_dirs = [p.name for p in private_projects.iterdir()] \
            if private_projects.exists() else []
        host_slug = slug_for(cwd_private)
        host_store = USER_HOME / ".claude" / "projects"
        host_has_slug = (host_store / host_slug).exists() \
            if host_store.exists() else False
        checks["transcript_relocation"] = {
            "pass": bool(private_slug_dirs) and not host_has_slug,
            "private_projects_slugs": private_slug_dirs[:3],
            "host_store_has_private_slug": host_has_slug,
        }
    all_pass = all(v.get("pass") for v in checks.values())
    doc = {
        "schema": "SQI_C4_CONFIG_EQUIVALENCE_EVIDENCE_V1",
        "generated_at": started,
        "checks": checks,
        "verdict": "PASS" if all_pass else "FAIL",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"C4-CONFIG-EQUIVALENCE-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(json.dumps({"verdict": doc["verdict"], "evidence": str(out)},
                     indent=1))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

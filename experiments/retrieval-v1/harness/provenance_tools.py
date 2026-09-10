from __future__ import annotations

import json
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import ToolEvent


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repository_head(repo: str | Path) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def repository_status(repo: str | Path) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_events(path: str | Path, events: Iterable[ToolEvent]) -> None:
    Path(path).write_text("\n".join(json.dumps(event.to_dict(), ensure_ascii=False)
                                      for event in events) + "\n", encoding="utf-8")


def read_events(path: str | Path) -> list[dict]:
    if not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]

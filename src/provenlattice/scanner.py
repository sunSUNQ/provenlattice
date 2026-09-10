from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


IGNORED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".provenlattice",
    ".pytest_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    ".cache",
    "deps",
    "dist",
    "node_modules",
    "out",
    "target",
    "third_party",
    "third-party",
    "vendor",
    "venv",
}
SUPPORTED_EXTENSIONS = {
    ".py": "python", ".pyi": "python",
    ".h": "cpp", ".hh": "cpp", ".hpp": "cpp", ".hxx": "cpp", ".inc": "cpp",
    ".c": "c", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".c++": "cpp",
}


@dataclass(frozen=True, slots=True)
class SourceFile:
    path: Path
    relative_path: str
    language: str
    source_hash: str


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scan_repository(root: Path) -> list[SourceFile]:
    root = root.resolve()
    files: list[SourceFile] = []
    for path in root.rglob("*"):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        if not path.is_file() or path.suffix not in SUPPORTED_EXTENSIONS:
            continue
        data = path.read_bytes()
        files.append(
            SourceFile(
                path=path,
                relative_path=path.relative_to(root).as_posix(),
                language=SUPPORTED_EXTENSIONS[path.suffix],
                source_hash=content_hash(data),
            )
        )
    return sorted(files, key=lambda item: item.relative_path)

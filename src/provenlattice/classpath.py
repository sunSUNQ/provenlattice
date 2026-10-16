"""P2-C manual Java classpath contract.

Minimal, deterministic, fail-closed classpath handling for the optional Java
semantic analyzer (P2-D consumer).  The default L1 index path never imports
this module and no JVM is required.

Contract guarantees:
- each entry is exactly one path (spaces/semicolons are literal characters);
  there is deliberately no joined-string input, removing separator ambiguity
- entries are resolved against an explicit base_dir, normalized to absolute
  forward-slash paths, deduplicated case-insensitively per platform
  (os.path.normcase), preserving first-occurrence order
- any NOT_FOUND / NOT_READABLE / BAD_KIND issue makes the whole contract
  status="invalid" and usable=False (fail-closed: consumers must not proceed)
- ``fingerprint`` is ``cp:<sha256>`` over the ordered, normcase-normalized
  entries joined with 0x1f; any path or order change yields a new fingerprint
  so stale analyzer results are detectable (freshness input for P2-D)
- project_roots (source roots) and dependencies (jars / class directories)
  are kept apart; ordering is semantic and preserved
"""
from __future__ import annotations

import hashlib
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

_JAR_SUFFIXES = {".jar", ".zip"}


@dataclass(frozen=True, slots=True)
class ClasspathIssue:
    """One diagnosable problem with a classpath entry."""

    path: str
    code: str  # NOT_FOUND | NOT_READABLE | BAD_KIND | CORRUPT_JAR | NOT_A_DIRECTORY
    detail: str


@dataclass(frozen=True, slots=True)
class ClasspathContract:
    """Validated, ordered, fingerprinted classpath for the Java analyzer."""

    status: str  # "valid" | "empty" | "invalid"
    project_roots: tuple[str, ...]
    dependencies: tuple[str, ...]
    duplicates: tuple[str, ...]
    issues: tuple[ClasspathIssue, ...]
    fingerprint: str | None
    usable: bool

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "usable": self.usable,
            "fingerprint": self.fingerprint,
            "project_roots": list(self.project_roots),
            "dependencies": list(self.dependencies),
            "duplicates": list(self.duplicates),
            "issues": [{"path": i.path, "code": i.code, "detail": i.detail}
                       for i in self.issues],
        }


def _normalize(entry: str, base_dir: Path | None) -> Path:
    path = Path(os.path.expanduser(entry))
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.resolve()


def _dedup_key(normalized: Path) -> str:
    # os.path.normcase lowercases on Windows and is a near-no-op on POSIX,
    # giving deterministic per-platform case-insensitive deduplication.
    return os.path.normcase(str(normalized).replace("\\", "/"))


def fingerprint_for(project_roots: tuple[str, ...], dependencies: tuple[str, ...]) -> str | None:
    """``cp:<sha256>`` over the ordered normcase-normalized entries.

    Order is semantic (classpath resolution order), so reordering changes the
    fingerprint. Returns None only for an empty contract.
    """
    parts = [*_normcase_all(project_roots), *_normcase_all(dependencies)]
    if not parts:
        return None
    canonical = "\x1f".join(parts)
    return "cp:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normcase_all(entries: tuple[str, ...]) -> list[str]:
    return [os.path.normcase(e.replace("\\", "/")) for e in entries]


def build_classpath(
    *,
    project_roots: tuple[str, ...] | list[str] = (),
    dependencies: tuple[str, ...] | list[str] = (),
    base_dir: str | Path | None = None,
) -> ClasspathContract:
    """Validate and normalize a manual classpath. Never raises for bad input;
    problems are reported as issues and flip the contract to invalid."""
    base = Path(base_dir).resolve() if base_dir is not None else None
    issues: list[ClasspathIssue] = []

    seen: dict[str, str] = {}
    duplicates: list[str] = []
    norm_roots: list[str] = []
    norm_deps: list[str] = []

    def _register(entry: str, normalized: Path, bucket: list[str]) -> None:
        key = _dedup_key(normalized)
        if key in seen:
            duplicates.append(entry)
            return
        seen[key] = entry
        bucket.append(str(normalized).replace("\\", "/"))

    for entry in project_roots:
        normalized = _normalize(entry, base)
        if not normalized.exists():
            issues.append(ClasspathIssue(entry, "NOT_FOUND",
                                         f"project root does not exist: {normalized}"))
            continue
        if not normalized.is_dir():
            issues.append(ClasspathIssue(entry, "NOT_A_DIRECTORY",
                                         f"project root must be a directory: {normalized}"))
            continue
        if not os.access(normalized, os.R_OK):
            issues.append(ClasspathIssue(entry, "NOT_READABLE",
                                         f"project root is not readable: {normalized}"))
            continue
        _register(entry, normalized, norm_roots)

    for entry in dependencies:
        normalized = _normalize(entry, base)
        if not normalized.exists():
            issues.append(ClasspathIssue(entry, "NOT_FOUND",
                                         f"dependency does not exist: {normalized}"))
            continue
        if normalized.is_dir():
            if not os.access(normalized, os.R_OK):
                issues.append(ClasspathIssue(entry, "NOT_READABLE",
                                             f"class directory is not readable: {normalized}"))
                continue
            _register(entry, normalized, norm_deps)
            continue
        if normalized.suffix.lower() not in _JAR_SUFFIXES:
            issues.append(ClasspathIssue(entry, "BAD_KIND",
                                         f"dependency file must be .jar/.zip or a class "
                                         f"directory: {normalized}"))
            continue
        if not os.access(normalized, os.R_OK):
            issues.append(ClasspathIssue(entry, "NOT_READABLE",
                                         f"dependency is not readable: {normalized}"))
            continue
        try:
            if not zipfile.is_zipfile(normalized):
                issues.append(ClasspathIssue(entry, "CORRUPT_JAR",
                                             f"jar is not a valid zip archive: {normalized}"))
                continue
        except OSError as error:
            issues.append(ClasspathIssue(entry, "NOT_READABLE",
                                         f"jar could not be read: {normalized} ({error})"))
            continue
        _register(entry, normalized, norm_deps)

    if issues:
        return ClasspathContract(
            status="invalid", project_roots=tuple(norm_roots),
            dependencies=tuple(norm_deps), duplicates=tuple(duplicates),
            issues=tuple(issues), fingerprint=None, usable=False)
    if not norm_roots and not norm_deps:
        return ClasspathContract(
            status="empty", project_roots=(), dependencies=(), duplicates=(),
            issues=(), fingerprint="cp:empty", usable=True)
    return ClasspathContract(
        status="valid", project_roots=tuple(norm_roots),
        dependencies=tuple(norm_deps), duplicates=tuple(duplicates),
        issues=(), fingerprint=fingerprint_for(tuple(norm_roots), tuple(norm_deps)),
        usable=True)


def load_classpath_file(manifest: str | Path, *, base_dir: str | Path | None = None) -> tuple[list[str], list[str]]:
    """Read a manifest file: one entry per line, ``project:<path>`` or
    ``dep:<path>``; blank lines and ``#`` comments ignored. Returns
    ``(project_roots, dependencies)`` as raw strings for build_classpath."""
    roots: list[str] = []
    deps: list[str] = []
    base = Path(base_dir) if base_dir is not None else Path(manifest).resolve().parent
    # utf-8-sig: tolerate a BOM (editors on Windows commonly emit one)
    for raw in Path(manifest).read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        role, sep, value = line.partition(":")
        if sep and role.strip().lower() in {"project", "dep", "dependency"}:
            value = value.strip()
        else:
            role, value = "dep", line
        if not value:
            continue
        resolved = str((base / os.path.expanduser(value)).resolve())
        (roots if role.strip().lower() == "project" else deps).append(resolved)
    return roots, deps

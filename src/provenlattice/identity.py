from __future__ import annotations

import hashlib
from pathlib import Path


def _stable(prefix: str, *parts: object) -> str:
    canonical = "\x1f".join(str(part) for part in parts)
    return f"{prefix}:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def repository_id(root: Path) -> str:
    return _stable("repo", root.resolve().as_posix().casefold())


def path_id(repo_id: str, kind: str, relative_path: str) -> str:
    return _stable(kind.lower(), repo_id, relative_path.replace("\\", "/"))


def symbol_id(
    repo_id: str,
    relative_path: str,
    kind: str,
    qualified_name: str,
    signature: str,
) -> str:
    return _stable(
        "symbol",
        repo_id,
        relative_path.replace("\\", "/"),
        kind,
        qualified_name,
        signature,
    )


def edge_id(src_id: str, dst_id: str, edge_type: str, discriminator: str = "") -> str:
    return _stable("edge", src_id, dst_id, edge_type, discriminator)


def shard_id(repo_id: str, path: str) -> str:
    return _stable("shard", repo_id, path.replace("\\", "/"))


def raw_reference_id(
    repo_id: str,
    file_id: str,
    owner_symbol_id: str,
    reference_type: str,
    raw_name: str,
    ordinal: int,
) -> str:
    return _stable(
        "reference", repo_id, file_id, owner_symbol_id, reference_type, raw_name, ordinal
    )

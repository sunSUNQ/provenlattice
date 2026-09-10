from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..models import ParsedFile


@dataclass(slots=True)
class ParseOutcome:
    parsed: ParsedFile
    tree: Any
    changed_ranges: list[dict]


class ParserAdapter(Protocol):
    language: str
    extensions: frozenset[str]

    def parse(self, path: Path, relative_path: str) -> ParsedFile: ...

    def parse_bytes(
        self, source: bytes, relative_path: str, old_tree: Any | None = None
    ) -> ParseOutcome: ...

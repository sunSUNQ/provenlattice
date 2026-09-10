from __future__ import annotations

from pathlib import Path
from typing import Any

import tree_sitter_python
from tree_sitter import Language, Parser

from .base import ParseOutcome
from .python import PythonExtractor
from ..models import ParsedFile


class TreeSitterParser:
    language = "python"
    extensions = frozenset({".py", ".pyi"})

    def __init__(self) -> None:
        self._language = Language(tree_sitter_python.language())
        self._parser = Parser(self._language)

    def parse(self, path: Path, relative_path: str) -> ParsedFile:
        return self.parse_bytes(path.read_bytes(), relative_path).parsed

    def parse_bytes(
        self, source: bytes, relative_path: str, old_tree: Any | None = None
    ) -> ParseOutcome:
        tree = self._parser.parse(source) if old_tree is None else self._parser.parse(source, old_tree)
        changed_ranges = []
        if old_tree is not None:
            changed_ranges = [
                {
                    "start_byte": item.start_byte,
                    "end_byte": item.end_byte,
                    "start_point": tuple(item.start_point),
                    "end_point": tuple(item.end_point),
                }
                for item in old_tree.changed_ranges(tree)
            ]
        parsed = PythonExtractor(source, relative_path).extract(tree.root_node)
        return ParseOutcome(parsed, tree, changed_ranges)

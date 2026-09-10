"""Compatibility facade for the V0 Python parser."""

from functools import lru_cache
from pathlib import Path

from .models import ParsedFile
from .parsing import CppTreeSitterParser, ParserAdapter, TreeSitterParser


@lru_cache(maxsize=3)
def parser_for_language(language: str) -> ParserAdapter:
    if language == "python":
        return TreeSitterParser()
    if language == "c":
        return CppTreeSitterParser("c")
    if language == "cpp":
        return CppTreeSitterParser("cpp")
    raise ValueError(f"unsupported language: {language}")


def parse_python(path: Path, relative_path: str) -> ParsedFile:
    return parser_for_language("python").parse(path, relative_path)


def parse_file(path: Path, relative_path: str, language: str) -> ParsedFile:
    return parse_file_with_diagnostics(path, relative_path, language)[0]


def parse_file_with_diagnostics(
    path: Path, relative_path: str, language: str
) -> tuple[ParsedFile, bool]:
    outcome = parser_for_language(language).parse_bytes(path.read_bytes(), relative_path)
    return outcome.parsed, bool(outcome.tree.root_node.has_error)

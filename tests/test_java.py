import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

try:
    import tree_sitter_java  # noqa: F401

    HAS_JAVA_GRAMMAR = True
except ImportError:  # pragma: no cover
    HAS_JAVA_GRAMMAR = False

from provenlattice.graph import full_index
from provenlattice.incremental import incremental_update
from provenlattice.parser import parse_file_with_diagnostics, parser_for_language
from provenlattice.parsing import JavaTreeSitterParser
from provenlattice.scanner import scan_repository
from provenlattice.shard import DirectoryShardStrategy


def write(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


def write_fixture(root: Path, fixture: dict[str, str]) -> None:
    for relative, body in fixture.items():
        write(root, relative, body)


def table_rows(database: Path, table: str) -> list[dict]:
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        return [
            {key: value for key, value in dict(row).items() if key != "generation"}
            for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")
        ]


def file_references(database: Path, relative_path: str) -> list[dict]:
    sql = (
        "SELECT r.* FROM raw_references r JOIN files f ON r.file_id = f.file_id "
        "WHERE f.path = ? ORDER BY r.id"
    )
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(sql, (relative_path,))]


def find_references(
    references: list[dict], *, raw_name: str, reference_type: str
) -> list[dict]:
    matches = [
        row for row in references
        if row["raw_name"] == raw_name and row["reference_type"] == reference_type
    ]
    assert matches, f"expected at least one {reference_type} {raw_name!r}, got none"
    return matches


def symbols(database: Path) -> list[dict]:
    return [row for row in table_rows(database, "nodes") if row["kind"] not in
            {"Repository", "Directory", "File"}]


HELPER_CORE = """package com.example.core;

public class Helper {
    public void run() { }

    public static int build(int seed) {
        return seed;
    }
}
"""

HELPER_UTIL = """package com.example.util;

public class Helper {
    public int assist() {
        return 1;
    }
}
"""

BASE = """package com.example.core;

public class Base {
    public void start() { }
}
"""

RUNNER_CORE = """package com.example.core;

public class Runner {
    public void execute() { }
}
"""

RUNNER_UTIL = """package com.example.util;

public class Runner {
    public void execute() { }
}
"""

APPLICATION = """package com.example.app;

import com.example.core.Helper;

public class Application {
    private Helper helper = new Helper();

    public void execute() {
        helper.run();
        Helper.build(1);
        int build = 3;
        build = build + 1;
        this.helper.run();
    }
}
"""

LEGACY = """package com.example.app;

public class Legacy {
    public void use(com.example.core.Helper coreHelper, com.example.util.Helper utilHelper) {
        coreHelper.run();
        utilHelper.assist();
    }
}
"""

AMBIGUOUS = """package com.example.app;

public class Ambiguous {
    public void trigger() {
        execute();
    }
}
"""

OVERLOADS = """package com.example.util;

public class Overloads {
    private int count;

    public Overloads() { }

    public Overloads(int seed) { }

    public void foo(int a) { }

    public void foo(String a) { }

    public void foo(int a, String b) { }

    public void caller() {
        foo(1);
        foo("x");
    }
}
"""

WILDCARD = """package com.example.app;

import com.example.core.*;

public class Wildcard {
    public Helper field;
}
"""

INDIRECT = """package com.example.app;

public class Indirect extends com.example.core.Base implements java.io.Serializable {
    public Indirect() {
        super();
    }

    public Indirect(int seed) {
        this();
    }

    public void trigger() {
        super.start();
        ((Indirect) null).self();
        Runnable r = this::trigger;
    }

    private void self() { }
}
"""

GRAPH_FIXTURE = {
    "src/com/example/core/Helper.java": HELPER_CORE,
    "src/com/example/core/Base.java": BASE,
    "src/com/example/util/Helper.java": HELPER_UTIL,
    "src/com/example/core/Runner.java": RUNNER_CORE,
    "src/com/example/util/Runner.java": RUNNER_UTIL,
    "src/com/example/app/Application.java": APPLICATION,
    "src/com/example/app/Legacy.java": LEGACY,
    "src/com/example/app/Ambiguous.java": AMBIGUOUS,
    "src/com/example/app/Wildcard.java": WILDCARD,
    "src/com/example/app/Indirect.java": INDIRECT,
    "src/com/example/util/Overloads.java": OVERLOADS,
}


@unittest.skipUnless(HAS_JAVA_GRAMMAR, "tree-sitter-java is required")
class JavaParserTests(unittest.TestCase):
    """T2: parser contract (valid, broken, recovery, lines, CRLF, incremental)."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.parser = JavaTreeSitterParser()

    def tearDown(self) -> None:
        self.temp.cleanup()

    # java01
    def test_java01_valid_parse_produces_facts(self) -> None:
        path = write(self.root, "Sample.java", "package a;\npublic class Sample {\n    void m() { }\n}\n")
        parsed, has_error = parse_file_with_diagnostics(path, "Sample.java", "java")
        self.assertFalse(has_error)
        self.assertEqual(parsed.parser, "tree-sitter-java")
        self.assertEqual([symbol.kind for symbol in parsed.symbols], ["Class", "Method"])
        self.assertEqual(parsed.symbols[0].qualified_name, "a.Sample")
        self.assertEqual(parsed.symbols[1].signature, "() -> void")

    # java02
    def test_java02_broken_file_reports_error_and_recovers_symbols(self) -> None:
        broken = "package a.b;\npublic class Broken {\n    public void bad( {\n        int x = ;\n    }\n}\n"
        path = write(self.root, "Broken.java", broken)
        parsed, has_error = parse_file_with_diagnostics(path, "Broken.java", "java")
        self.assertTrue(has_error)
        names = {symbol.qualified_name for symbol in parsed.symbols}
        self.assertIn("a.b.Broken", names)

    # java03
    def test_java03_crlf_and_lf_line_numbers_match(self) -> None:
        source = "package a;\n\npublic class Sample {\n    void m() {\n        go();\n    }\n}\n"
        lf = self.parser.parse_bytes(source.encode("utf-8"), "Sample.java").parsed
        crlf = self.parser.parse_bytes(source.replace("\n", "\r\n").encode("utf-8"), "Sample.java").parsed
        self.assertEqual(
            [(symbol.qualified_name, symbol.start_line) for symbol in lf.symbols],
            [(symbol.qualified_name, symbol.start_line) for symbol in crlf.symbols],
        )
        go = [reference for reference in lf.references if reference.target == "go"]
        self.assertEqual(go[0].start_line, 5)

    # java04
    def test_java04_incremental_reparse_reports_changed_ranges(self) -> None:
        # Mirrors tests/test_core.py:79: changed_ranges are structural, so the
        # proven scenario is an append; in-place same-grammar replacements
        # yield empty ranges in tree-sitter 0.26 for every language.
        old_source = 'class A {\n    String name = "a";\n}\n'
        new_source = old_source + "class B { }\n"
        first = self.parser.parse_bytes(old_source.encode("utf-8"), "A.java")
        first.tree.edit(
            start_byte=len(old_source), old_end_byte=len(old_source), new_end_byte=len(new_source),
            start_point=(3, 0), old_end_point=(3, 0), new_end_point=(4, 0),
        )
        second = self.parser.parse_bytes(new_source.encode("utf-8"), "A.java", first.tree)
        self.assertTrue(second.changed_ranges)
        self.assertFalse(second.tree.root_node.has_error)
        names = {symbol.qualified_name for symbol in second.parsed.symbols}
        self.assertIn("A.A", names)
        self.assertIn("A.B", names)


@unittest.skipUnless(HAS_JAVA_GRAMMAR, "tree-sitter-java is required")
class JavaSymbolExtractionTests(unittest.TestCase):
    """T3: kind mapping per approved plan (D1: reuse frozen kinds + markers)."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.parser = JavaTreeSitterParser()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def extract(self, source: str):
        return self.parser.parse_bytes(source.encode("utf-8"), "com/example/Types.java").parsed

    # java05
    def test_java05_type_declarations_map_to_frozen_kinds(self) -> None:
        parsed = self.extract(
            "package com.example;\n"
            "public class Plain { }\n"
            "interface Contract { }\n"
            "enum Color { RED, GREEN }\n"
            "record Point(int x, int y) { }\n"
            "@interface Marker { }\n"
            "class Outer {\n"
            "    class Inner { }\n"
            "    static class StaticNested { }\n"
            "}\n"
        )
        by_qualified = {symbol.qualified_name: symbol for symbol in parsed.symbols}
        expected = {
            "com.example.Plain": ("Class", "class"),
            "com.example.Contract": ("Interface", "interface"),
            "com.example.Color": ("Class", "enum"),
            "com.example.Point": ("Class", "record"),
            "com.example.Marker": ("Interface", "annotation"),
            "com.example.Outer": ("Class", "class"),
            "com.example.Outer.Inner": ("Class", "class"),
            "com.example.Outer.StaticNested": ("Class", "class"),
        }
        for qualified, (kind, java_kind) in expected.items():
            self.assertIn(qualified, by_qualified, qualified)
            symbol = by_qualified[qualified]
            self.assertEqual(symbol.kind, kind, qualified)
            self.assertEqual(symbol.metadata["java_kind"], java_kind, qualified)
            self.assertTrue(symbol.metadata["definition"])
        red = by_qualified["com.example.Color.RED"]
        self.assertEqual((red.kind, red.metadata["java_member"]), ("Method", "enum_constant"))
        self.assertEqual(red.signature, "Color RED")

    # java06
    def test_java06_members_and_overloads_get_distinct_signatures(self) -> None:
        parsed = self.parser.parse_bytes(
            OVERLOADS.encode("utf-8"), "com/example/util/Overloads.java"
        ).parsed
        by_qualified = {symbol.qualified_name: symbol for symbol in parsed.symbols}
        foo_signatures = sorted(
            symbol.signature for symbol in parsed.symbols
            if symbol.qualified_name == "com.example.util.Overloads.foo"
        )
        self.assertEqual(
            foo_signatures,
            sorted(["(int, String) -> void", "(int) -> void", "(String) -> void"]),
        )
        ctor_signatures = sorted(
            symbol.signature for symbol in parsed.symbols
            if symbol.qualified_name == "com.example.util.Overloads.Overloads"
        )
        self.assertEqual(ctor_signatures, ["()", "(int)"])
        field = by_qualified["com.example.util.Overloads.count"]
        self.assertEqual((field.signature, field.metadata["java_member"]), ("int count", "field"))
        # distinct signature -> distinct stable symbol inputs
        self.assertEqual(len({symbol.signature for symbol in parsed.symbols
                              if symbol.name == "foo"}), 3)


@unittest.skipUnless(HAS_JAVA_GRAMMAR, "tree-sitter-java is required")
class JavaGraphTests(unittest.TestCase):
    """T3: full_index integration, three-state resolution, wrong-resolution guard."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.database = Path(self.temp.name) / "codegraph.db"
        write_fixture(self.root, GRAPH_FIXTURE)
        full_index(self.root, self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    # java07
    def test_java07_scanner_and_parser_wiring(self) -> None:
        sources = scan_repository(self.root)
        java_sources = [source for source in sources if source.language == "java"]
        self.assertEqual(len(java_sources), 11)
        self.assertTrue(all(source.relative_path.endswith(".java") for source in java_sources))
        self.assertIsInstance(parser_for_language("java"), JavaTreeSitterParser)
        with closing(sqlite3.connect(self.database)) as connection:
            languages = {row[0] for row in connection.execute("SELECT DISTINCT language FROM files")}
        self.assertEqual(languages, {"java"})

    # java08
    def test_java08_single_type_import_resolves(self) -> None:
        references = file_references(self.database, "src/com/example/app/Application.java")
        import_ref = find_references(references, raw_name="Helper", reference_type="IMPORTS")[0]
        self.assertEqual(import_ref["status"], "resolved")
        self.assertEqual(import_ref["resolution_strategy"], "import_resolution")
        self.assertEqual(import_ref["confidence"], 1.0)
        type_refs = find_references(references, raw_name="Helper", reference_type="REFERENCES")
        strategies = {row["resolution_strategy"] for row in type_refs if row["status"] == "resolved"}
        # field type carries the import module (import_resolution); the
        # receiver identifier of Helper.build falls to the alias ladder
        self.assertIn("import_resolution", strategies)
        self.assertTrue(all(row["status"] == "resolved" for row in type_refs))
        static_call = find_references(references, raw_name="Helper.build", reference_type="CALLS")[0]
        self.assertEqual(static_call["status"], "resolved")
        self.assertEqual(static_call["confidence"], 1.0)

    # java09
    def test_java09_cross_file_unique_names_resolve_conservatively(self) -> None:
        references = file_references(self.database, "src/com/example/app/Legacy.java")
        param_type = find_references(
            references, raw_name="com.example.core.Helper", reference_type="REFERENCES"
        )[0]
        self.assertEqual(param_type["status"], "resolved")
        self.assertEqual(param_type["resolution_strategy"], "qualified_name_resolution")
        self.assertEqual(param_type["confidence"], 0.99)
        call = find_references(references, raw_name="coreHelper.run", reference_type="CALLS")[0]
        # P2-A R1: identifier-receiver instance call -> ambiguous (demoted)
        self.assertEqual(call["status"], "ambiguous")
        self.assertEqual(call["resolution_strategy"], "unique_symbol_resolution")
        self.assertEqual(call["confidence"], 0.0)
        self.assertEqual(json.loads(call["metadata"])["receiver_shape"], "identifier")
        self.assertEqual(json.loads(call["metadata"])["demote_reason"],
                         "receiver_type_unknown")

    # java10
    def test_java10_cross_package_same_name_is_ambiguous(self) -> None:
        references = file_references(self.database, "src/com/example/app/Ambiguous.java")
        call = find_references(references, raw_name="execute", reference_type="CALLS")[0]
        self.assertEqual(call["status"], "ambiguous")
        candidates = set(json.loads(call["candidate_symbols"]))
        # both Runner.execute copies are candidates (Application.execute too)
        self.assertEqual(len(candidates), 3)
        runner_ids = {
            row["id"] for row in symbols(self.database)
            if row["qualified_name"] in
            {"com.example.core.Runner.execute", "com.example.util.Runner.execute"}
        }
        self.assertTrue(runner_ids <= candidates)
        self.assertEqual(call["resolved_symbol_id"], None)

    # java11
    def test_java11_overload_calls_stay_ambiguous_with_all_candidates(self) -> None:
        references = file_references(self.database, "src/com/example/util/Overloads.java")
        calls = find_references(references, raw_name="foo", reference_type="CALLS")
        self.assertEqual(len(calls), 2)
        for row in calls:
            self.assertEqual(row["status"], "ambiguous")
            self.assertEqual(len(json.loads(row["candidate_symbols"])), 3)
        foo_nodes = [
            row for row in symbols(self.database)
            if row["qualified_name"] == "com.example.util.Overloads.foo"
        ]
        self.assertEqual(len(foo_nodes), 3)
        self.assertEqual(len({row["id"] for row in foo_nodes}), 3)

    # java12
    def test_java12_wildcard_import_stays_unresolved(self) -> None:
        references = file_references(self.database, "src/com/example/app/Wildcard.java")
        import_ref = find_references(references, raw_name="*", reference_type="IMPORTS")[0]
        self.assertEqual(import_ref["status"], "unresolved")
        type_ref = find_references(references, raw_name="Helper", reference_type="REFERENCES")[0]
        self.assertEqual(type_ref["status"], "ambiguous")
        self.assertEqual(len(json.loads(type_ref["candidate_symbols"])), 2)

    # java13
    def test_java13_indirect_shapes_are_never_name_bound(self) -> None:
        references = file_references(self.database, "src/com/example/app/Indirect.java")
        for raw_name, reference_type in (
            ("super.start", "CALLS"),
            ("super", "CALLS"),
            ("((Indirect) null).self", "CALLS"),
            ("this.trigger", "REFERENCES"),
        ):
            row = find_references(references, raw_name=raw_name, reference_type=reference_type)[0]
            self.assertEqual(row["status"], "unresolved", raw_name)
            self.assertEqual(row["resolution_strategy"], "indirect_call_shape", raw_name)
        # explicit this(...) constructor call: same-file class + constructors -> ambiguous
        ctor_call = find_references(references, raw_name="Indirect", reference_type="CALLS")[0]
        self.assertEqual(ctor_call["status"], "ambiguous")
        # inheritance: in-project superclass resolves; external interface does not
        extends = find_references(
            references, raw_name="com.example.core.Base", reference_type="IMPLEMENTS"
        )[0]
        self.assertEqual(extends["status"], "resolved")
        self.assertEqual(json.loads(extends["metadata"])["java_relation"], "extends")
        implements = find_references(
            references, raw_name="java.io.Serializable", reference_type="IMPLEMENTS"
        )[0]
        self.assertEqual(implements["status"], "unresolved")

    # java14
    def test_java14_field_access_resolves_to_in_file_symbol(self) -> None:
        references = file_references(self.database, "src/com/example/app/Application.java")
        field_refs = find_references(references, raw_name="helper", reference_type="REFERENCES")
        self.assertGreaterEqual(len(field_refs), 2)
        for row in field_refs:
            self.assertEqual(row["status"], "resolved")
            self.assertEqual(row["resolution_strategy"], "same_file_resolution")
            self.assertEqual(row["confidence"], 0.98)

    # java15
    def test_java15_graph_shape_uses_frozen_kinds_and_defines_edges(self) -> None:
        node_rows = symbols(self.database)
        self.assertTrue(node_rows)
        self.assertLessEqual(
            {row["kind"] for row in node_rows},
            {"Namespace", "Class", "Struct", "Interface", "Function", "Method", "Type"},
        )
        with closing(sqlite3.connect(self.database)) as connection:
            defines = connection.execute(
                "SELECT COUNT(*) FROM edges WHERE type = 'DEFINES'"
            ).fetchone()[0]
            imports_edge = connection.execute(
                "SELECT COUNT(*) FROM edges WHERE type = 'IMPORTS' AND provenance = 'import_resolution'"
            ).fetchone()[0]
            calls_edge = connection.execute(
                "SELECT COUNT(*) FROM edges WHERE type = 'CALLS' AND provenance = 'import_resolution'"
            ).fetchone()[0]
        self.assertEqual(defines, len(node_rows))
        self.assertGreaterEqual(imports_edge, 1)
        self.assertGreaterEqual(calls_edge, 1)
        # default directory sharding groups everything under src/com; use a
        # deeper strategy so app/ and core/ land in different shards, then
        # assert the cross-shard CALLS edge (Application -> Helper.build)
        boundary_db = Path(self.temp.name) / "boundary.db"
        full_index(self.root, boundary_db, strategy=DirectoryShardStrategy(levels=4))
        with closing(sqlite3.connect(boundary_db)) as connection:
            boundary_calls = connection.execute(
                "SELECT COUNT(*) FROM edges WHERE type = 'CALLS' "
                "AND json_extract(metadata, '$.scope') = 'boundary'"
            ).fetchone()[0]
        self.assertGreaterEqual(boundary_calls, 1)

    # java16
    def test_java16_incremental_update_matches_full_index(self) -> None:
        incremental_db = Path(self.temp.name) / "incremental.db"
        full_db = Path(self.temp.name) / "full.db"
        full_index(self.root, incremental_db)
        application = self.root / "src/com/example/app/Application.java"
        application.write_text(APPLICATION.replace("Helper.build(1)", "Helper.build(2)"),
                               encoding="utf-8", newline="\n")
        update = incremental_update(self.root, incremental_db)
        full_index(self.root, full_db)

        def snapshot(path: Path) -> dict[str, list[dict]]:
            with closing(sqlite3.connect(path)) as connection:
                connection.row_factory = sqlite3.Row
                return {
                    table: [
                        {key: value for key, value in dict(row).items()
                         if key not in {"generation", "boundary_dirty"}}
                        for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")
                    ]
                    for table in ("nodes", "edges", "shards", "raw_references")
                }

        self.assertEqual(snapshot(incremental_db), snapshot(full_db))
        self.assertEqual(update["metrics"]["files_reparsed"], 1)
        self.assertEqual(update["metrics"]["files_reused"], 10)

    # java17
    def test_java17_default_index_creates_no_analysis_products(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection:
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        self.assertFalse(tables & {"analysis_state", "analysis_nodes", "analysis_edges"})

    # java18
    def test_java18_locals_never_bind_to_global_symbols(self) -> None:
        # `int build = 3; build = build + 1;` in Application.execute must not
        # produce any raw reference named "build" (unique global
        # com.example.core.Helper.build exists and would be a wrong binding).
        with closing(sqlite3.connect(self.database)) as connection:
            rows = connection.execute(
                "SELECT COUNT(*) FROM raw_references WHERE raw_name = 'build'"
            ).fetchone()[0]
        self.assertEqual(rows, 0)
        # the qualified static call itself still resolves
        references = file_references(self.database, "src/com/example/app/Application.java")
        static_call = find_references(references, raw_name="Helper.build", reference_type="CALLS")[0]
        self.assertEqual(static_call["status"], "resolved")

    # java19
    def test_java19_extraction_is_deterministic(self) -> None:
        parser = JavaTreeSitterParser()
        first = parser.parse_bytes(APPLICATION.encode("utf-8"), "src/Application.java").parsed
        second = parser.parse_bytes(APPLICATION.encode("utf-8"), "src/Application.java").parsed
        self.assertEqual(first, second)


@unittest.skipUnless(HAS_JAVA_GRAMMAR, "tree-sitter-java is required")
class JavaNoRegressionTests(unittest.TestCase):
    """J9/J17 guards: frozen capability sets and old-language paths untouched."""

    # java20
    def test_java20_unsupported_languages_still_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parser_for_language("ruby")

    # java21
    def test_java21_java_files_reported_unsupported_by_analyzer(self) -> None:
        """1.5.0: ast:java is now registered, so Java files should be
        processed by `analyze --features ast` (no longer skipped)."""
        from provenlattice.orchestrator import analyze_scope

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            database = Path(temp) / "codegraph.db"
            write_fixture(root, {"src/A.java": "public class A { void m() { } }\n"})
            full_index(root, database)
            result = analyze_scope(root, "src", ("ast",), database=database)
        java_files = [row for row in result["per_file"] if row.get("language") == "java"]
        self.assertTrue(java_files)
        for row in java_files:
            self.assertNotEqual(row["bucket"], "skipped")


@unittest.skipUnless(HAS_JAVA_GRAMMAR, "tree-sitter-java is required")
class JavaAdversarialTests(unittest.TestCase):
    """P6 hardening: interface defaults, static imports, varargs, anonymous
    bodies, nested generics, delete/re-add convergence, default package."""

    def index(self, fixture: dict[str, str]) -> tuple[Path, Path]:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        database = Path(temp.name) / "codegraph.db"
        write_fixture(root, fixture)
        full_index(root, database)
        return root, database

    # java25
    def test_java25_interface_default_method_is_extracted_and_callable(self) -> None:
        root, database = self.index({
            "src/a/W.java": (
                "package a;\n"
                "public interface W {\n"
                "    default boolean ready() { return true; }\n"
                "}\n"
            ),
            "src/a/Impl.java": (
                "package a;\n"
                "public class Impl implements W {\n"
                "    public boolean use() { return ready(); }\n"
                "}\n"
            ),
        })
        names = {row["qualified_name"] for row in symbols(database)}
        self.assertIn("a.W.ready", names)
        refs = file_references(database, "src/a/Impl.java")
        call = [r for r in refs if r["raw_name"] == "ready" and r["reference_type"] == "CALLS"]
        self.assertEqual(len(call), 1)
        self.assertEqual(call[0]["status"], "resolved")
        self.assertEqual(call[0]["resolution_strategy"], "unique_symbol_resolution")

    # java26
    def test_java26_static_import_member_resolves(self) -> None:
        root, database = self.index({
            "src/a/Const.java": (
                "package a;\n"
                "public class Const {\n"
                "    public static final int MAX = 9;\n"
                "    public static int clamp(int v) { return v; }\n"
                "}\n"
            ),
            "src/b/User.java": (
                "package b;\n"
                "import static a.Const.MAX;\n"
                "import static a.Const.clamp;\n"
                "public class User {\n"
                "    public int go(int v) { return clamp(MAX + v); }\n"
                "}\n"
            ),
        })
        refs = file_references(database, "src/b/User.java")
        clamp_call = [r for r in refs if r["raw_name"] == "clamp" and r["reference_type"] == "CALLS"]
        self.assertEqual(clamp_call[0]["status"], "resolved")
        self.assertEqual(clamp_call[0]["confidence"], 1.0)
        # bare MAX reads are rewritten through the static-import alias ladder
        max_refs = [r for r in refs if r["raw_name"] == "MAX"]
        self.assertTrue(all(r["status"] == "resolved" for r in max_refs), max_refs)

    # java27
    def test_java27_varargs_signature_and_call(self) -> None:
        root, database = self.index({
            "src/a/Sums.java": (
                "package a;\n"
                "public class Sums {\n"
                "    public static int sum(int... values) { return 0; }\n"
                "    public int total() { return sum(1, 2, 3); }\n"
                "}\n"
            ),
        })
        nodes = [row for row in symbols(database) if row["qualified_name"] == "a.Sums.sum"]
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["signature"], "(int...) -> int")
        refs = file_references(database, "src/a/Sums.java")
        call = [r for r in refs if r["raw_name"] == "sum" and r["reference_type"] == "CALLS"]
        self.assertEqual(call[0]["status"], "resolved")

    # java28
    def test_java28_anonymous_body_is_skipped(self) -> None:
        root, database = self.index({
            "src/a/Lat.java": (
                "package a;\n"
                "public class Lat {\n"
                "    public Runnable make() {\n"
                "        return new Runnable() {\n"
                "            public void run() { helper(); }\n"
                "        };\n"
                "    }\n"
                "    public void helper() { }\n"
                "}\n"
            ),
        })
        # R5 gap (documented): anonymous bodies produce no symbols/refs
        names = {row["qualified_name"] for row in symbols(database)}
        self.assertIn("a.Lat", names)
        self.assertNotIn("a.Lat.make.run", names)
        refs = file_references(database, "src/a/Lat.java")
        self.assertEqual(
            [r for r in refs if r["raw_name"] == "run" and r["reference_type"] == "CALLS"],
            [],
        )

    # java29
    def test_java29_nested_generics_emit_inner_type_refs(self) -> None:
        root, database = self.index({
            "src/a/Container.java": (
                "package a;\n"
                "import java.util.List;\n"
                "public class Container {\n"
                "    private java.util.Map<String, List<Integer>> index;\n"
                "}\n"
            ),
        })
        refs = file_references(database, "src/a/Container.java")
        targets = {r["raw_name"] for r in refs if r["reference_type"] == "REFERENCES"}
        # outer qualified type + inner generic arguments all surface
        self.assertIn("java.util.Map", targets)
        self.assertIn("List", targets)
        self.assertIn("Integer", targets)

    # java30
    def test_java30_delete_and_readd_file_converges(self) -> None:
        root, database = self.index({
            "src/a/A.java": "package a;\npublic class A { void m() { } }\n",
            "src/a/B.java": "package a;\npublic class B { void n() { A v; } }\n",
        })
        with closing(sqlite3.connect(database)) as connection:
            before = connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        (root / "src/a/B.java").unlink()
        update = incremental_update(root, database)
        self.assertEqual(update["changes"]["deleted"], ["src/a/B.java"])
        with closing(sqlite3.connect(database)) as connection:
            b_nodes = connection.execute(
                "SELECT COUNT(*) FROM nodes WHERE name = 'B'").fetchone()[0]
            after_delete = connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        self.assertEqual(b_nodes, 0)
        write(root, "src/a/B.java", "package a;\npublic class B { void n() { A v; } }\n")
        incremental_update(root, database)
        with closing(sqlite3.connect(database)) as connection:
            restored = connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        self.assertEqual(restored, before)
        self.assertLess(after_delete, restored)

    # java31
    def test_java31_default_package_file_still_indexes(self) -> None:
        root, database = self.index({
            "src/Bare.java": "public class Bare {\n    void go() { }\n}\n",
        })
        nodes = [row for row in symbols(database) if row["kind"] == "Class"]
        self.assertEqual(len(nodes), 1)
        # no package declaration -> base falls back to the path module
        self.assertEqual(nodes[0]["qualified_name"], "src.Bare.Bare")
        refs = file_references(database, "src/Bare.java")
        self.assertEqual(refs, [])


# P1 regression fixtures (T8 review Exp6): a member whose name collides with a
# type must never capture type_usage / object_creation references.
SAME_NAME_IMPORTED = {
    "src/a/Helper.java": "package a;\n\npublic class Helper { }\n",
    "src/b/Caller.java": (
        "package b;\n\n"
        "import a.Helper;\n\n"
        "public class Caller {\n"
        "    public void Helper() { }\n\n"
        "    public Helper make() {\n"
        "        return new Helper();\n"
        "    }\n"
        "}\n"
    ),
}

SAME_NAME_LOCAL = {
    "src/b/Helper.java": (
        "package b;\n\n"
        "public class Helper {\n"
        "    public void Helper() { }\n\n"
        "    public Helper make() {\n"
        "        return new Helper();\n"
        "    }\n"
        "}\n"
    ),
}

SAME_NAME_CROSS_PACKAGE = {
    "src/a/Helper.java": "package a;\n\npublic class Helper { }\n",
    "src/b/Caller.java": (
        "package b;\n\n"
        "public class Caller {\n"
        "    public void Helper() { }\n\n"
        "    public Helper make() { return null; }\n"
        "}\n"
    ),
}


def resolved_targets(database: Path, relative_path: str) -> list[dict]:
    sql = (
        "SELECT r.raw_name, r.reference_type, r.status, r.resolution_strategy, r.confidence, "
        "n.kind AS target_kind, n.qualified_name AS target_qname "
        "FROM raw_references r LEFT JOIN nodes n ON r.resolved_symbol_id = n.id "
        "JOIN files f ON r.file_id = f.file_id "
        "WHERE f.path = ? AND r.raw_name = 'Helper' ORDER BY r.id"
    )
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(sql, (relative_path,))]


@unittest.skipUnless(HAS_JAVA_GRAMMAR, "tree-sitter-java is required")
class JavaTypeTargetGuardTests(unittest.TestCase):
    """P1: type_usage / new references must only bind type-kind candidates."""

    def index(self, fixture: dict[str, str]) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        database = Path(temp.name) / "codegraph.db"
        write_fixture(root, fixture)
        full_index(root, database)
        return database

    # java22
    def test_java22_imported_type_not_captured_by_same_name_method(self) -> None:
        database = self.index(SAME_NAME_IMPORTED)
        rows = resolved_targets(database, "src/b/Caller.java")
        self.assertEqual(len(rows), 3)  # IMPORTS + return type REFERENCES + new CALLS
        for row in rows:
            self.assertEqual(row["status"], "resolved", row)
            self.assertEqual(row["target_kind"], "Class", row)
            self.assertEqual(row["target_qname"], "a.Helper", row)
        type_ref = [r for r in rows if r["reference_type"] == "REFERENCES"][0]
        self.assertEqual(type_ref["resolution_strategy"], "import_resolution")
        self.assertEqual(type_ref["confidence"], 1.0)

    # java23
    def test_java23_same_file_class_wins_over_same_name_member(self) -> None:
        database = self.index(SAME_NAME_LOCAL)
        rows = resolved_targets(database, "src/b/Helper.java")
        self.assertEqual(len(rows), 2)  # return type REFERENCES + new CALLS
        for row in rows:
            self.assertEqual(row["status"], "resolved", row)
            self.assertEqual(row["target_kind"], "Class", row)
            self.assertEqual(row["target_qname"], "b.Helper", row)
            self.assertEqual(row["resolution_strategy"], "same_file_resolution")
            self.assertEqual(row["confidence"], 0.98)

    # java24
    def test_java24_cross_file_type_preferred_over_same_name_member(self) -> None:
        database = self.index(SAME_NAME_CROSS_PACKAGE)
        rows = resolved_targets(database, "src/b/Caller.java")
        self.assertEqual(len(rows), 1)  # return type REFERENCES only
        row = rows[0]
        self.assertEqual(row["status"], "resolved")
        self.assertEqual(row["target_kind"], "Class")
        self.assertEqual(row["target_qname"], "a.Helper")
        self.assertEqual(row["resolution_strategy"], "unique_symbol_resolution")
        self.assertEqual(row["confidence"], 0.75)


@unittest.skipUnless(HAS_JAVA_GRAMMAR, "tree-sitter-java is required")
class CrossLanguageGuardPinTests(unittest.TestCase):
    """Negative tests: the type-target guard is metadata-gated to Java facts.

    Python/C/C++ extractors do not emit the guarded syntax markers, so their
    resolution behavior must stay byte-identical (T8 Exp7 documents the shared
    underlying mechanism; any Python fix requires a separate decision).
    """

    def test_python_same_name_call_binding_unchanged(self) -> None:
        # Python emits no type-usage references (return annotations are not
        # walked by parsing/python.py), so the shared bare-name same-file
        # mechanism only shows on CALLS here; the guard is metadata-gated and
        # must not change this pre-fix behavior (T8 Exp7 attribution note:
        # the "annotation" binding was actually the call site).
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        database = Path(temp.name) / "codegraph.db"
        write_fixture(root, {
            "pkg/helper.py": "class Helper:\n    pass\n",
            "pkg/mod.py": (
                "from pkg.helper import Helper\n\n\n"
                "def Helper():\n    return 1\n\n\n"
                "def make() -> Helper:\n    return Helper()\n"
            ),
            "pkg/__init__.py": "",
        })
        full_index(root, database)
        sql = (
            "SELECT r.raw_name, r.reference_type, r.status, r.resolution_strategy, "
            "n.kind AS target_kind, n.qualified_name AS target_qname "
            "FROM raw_references r LEFT JOIN nodes n ON r.resolved_symbol_id = n.id "
            "JOIN files f ON r.file_id = f.file_id "
            "WHERE f.path = 'pkg/mod.py' AND r.raw_name = 'Helper' ORDER BY r.id"
        )
        with closing(sqlite3.connect(database)) as connection:
            connection.row_factory = sqlite3.Row
            rows = [dict(row) for row in connection.execute(sql)]
        self.assertEqual(len(rows), 2)
        imports_row = [r for r in rows if r["reference_type"] == "IMPORTS"][0]
        # pre-existing from-import behavior in this fixture shape: module file
        # node and class both match -> ambiguous (unchanged, pinned)
        self.assertEqual(imports_row["status"], "ambiguous")
        self.assertEqual(imports_row["resolution_strategy"], "import_resolution")
        call_row = [r for r in rows if r["reference_type"] == "CALLS"][0]
        # pinned pre-fix behavior: bare-name same-file binding, no kind filter
        self.assertEqual(call_row["status"], "resolved")
        self.assertEqual(call_row["resolution_strategy"], "same_file_resolution")
        self.assertEqual(call_row["target_kind"], "Function")
        self.assertEqual(call_row["target_qname"], "pkg.mod.Helper")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

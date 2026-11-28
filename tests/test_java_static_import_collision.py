"""Java static-import collision (product #28 / issue-pilot #136).

Two `import static A.name;` / `import static B.name;` lines must not let the
last import decide a bare call's target. The call keeps every imported
candidate and stays ambiguous; a single static import still resolves.
"""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from provenlattice.graph import full_index
from provenlattice.incremental import incremental_update

JUNIT_ASSERT = """\
package org.junit;
public class Assert {
    public static void assertEquals(Object a, Object b) {}
}
"""

JGIT_ASSERT = """\
package org.eclipse.jgit.junit;
public class Assert {
    public static void assertEquals(boolean a, boolean b) {}
    public static void assertEquals(String m, boolean a, boolean b) {}
}
"""

JUNIT_IMPORT = "import static org.junit.Assert.assertEquals;\n"
JGIT_IMPORT = "import static org.eclipse.jgit.junit.Assert.assertEquals;\n"


def write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


class StaticImportCollisionTests(unittest.TestCase):
    def _call_reference(
        self, imports: str, extra_files: dict[str, str] | None = None,
        methods: str = "",
    ) -> tuple[dict, set[str]]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            write(root, "src/org/junit/Assert.java", JUNIT_ASSERT)
            write(root, "src/org/eclipse/jgit/junit/Assert.java", JGIT_ASSERT)
            for relative, value in (extra_files or {}).items():
                write(root, relative, value)
            write(root, "src/t/RefUpdateTest.java", (
                "package t;\n"
                + imports
                + "public class RefUpdateTest {\n"
                + methods
                + "    void test() { assertEquals(\"msg\", \"value\"); }\n"
                + "}\n"
            ))
            database = Path(temporary) / "graph.db"
            full_index(root, database)
            with closing(sqlite3.connect(database)) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    "SELECT r.target_module, r.status, r.candidate_symbols, "
                    "r.resolved_symbol_id, r.metadata, "
                    "n.qualified_name AS resolved_name "
                    "FROM raw_references r LEFT JOIN nodes n "
                    "ON n.id = r.resolved_symbol_id "
                    "WHERE r.reference_type='CALLS' AND r.raw_name='assertEquals'"
                ).fetchone()
                self.assertIsNotNone(row)
                ids = json.loads(row["candidate_symbols"])
                names = {
                    connection.execute(
                        "SELECT qualified_name FROM nodes WHERE id=?", (item,)
                    ).fetchone()[0]
                    for item in ids
                }
                return dict(row), names

    def test_collision_is_ambiguous_and_order_independent(self) -> None:
        first, first_names = self._call_reference(JUNIT_IMPORT + JGIT_IMPORT)
        second, second_names = self._call_reference(JGIT_IMPORT + JUNIT_IMPORT)
        for row in (first, second):
            self.assertEqual(row["status"], "ambiguous")
            self.assertIsNone(row["resolved_symbol_id"])
            self.assertIsNone(row["target_module"])
        self.assertEqual(first_names, second_names)
        self.assertEqual(
            first_names,
            {
                "org.junit.Assert.assertEquals",
                "org.eclipse.jgit.junit.Assert.assertEquals",
            },
        )

    def test_collision_metadata_is_recorded(self) -> None:
        row, _ = self._call_reference(JUNIT_IMPORT + JGIT_IMPORT)
        metadata = json.loads(row["metadata"])
        self.assertTrue(metadata.get("static_import_collision"))
        self.assertGreater(len(json.loads(row["candidate_symbols"])), 1)

    def test_unique_static_import_still_resolves(self) -> None:
        row, names = self._call_reference(JUNIT_IMPORT)
        self.assertEqual(row["status"], "resolved")
        self.assertEqual(row["resolved_name"], "org.junit.Assert.assertEquals")
        self.assertEqual(names, {"org.junit.Assert.assertEquals"})


    def test_collision_does_not_bind_a_c_global(self) -> None:
        row, names = self._call_reference(
            JUNIT_IMPORT + JGIT_IMPORT,
            extra_files={"src/cfunc.c": "void assertEquals(void) {}\n"},
        )
        self.assertEqual(row["status"], "ambiguous")
        self.assertIsNone(row["resolved_symbol_id"])
        self.assertIsNone(row["target_module"])
        self.assertEqual(
            names,
            {
                "org.junit.Assert.assertEquals",
                "org.eclipse.jgit.junit.Assert.assertEquals",
            },
        )
        self.assertNotIn("assertEquals", names)

    def test_ordinary_import_class_is_not_a_collision_candidate(self) -> None:
        row, names = self._call_reference(
            JUNIT_IMPORT + JGIT_IMPORT + "import c.m;\n",
            extra_files={"src/c/m.java": "package c; public class m {}\n"},
        )
        self.assertEqual(row["status"], "ambiguous")
        self.assertEqual(
            names,
            {
                "org.junit.Assert.assertEquals",
                "org.eclipse.jgit.junit.Assert.assertEquals",
            },
        )
        self.assertNotIn("c.m", names)


    def test_same_file_method_still_shadows_the_collision(self) -> None:
        # Java's same-class member wins over static imports; the collision
        # branch must stay behind the same-file ladder.
        row, names = self._call_reference(
            JUNIT_IMPORT + JGIT_IMPORT,
            methods="    void assertEquals(Object a, Object b) {}\n",
        )
        self.assertEqual(row["status"], "resolved")
        self.assertEqual(row["resolved_name"], "t.RefUpdateTest.assertEquals")
        self.assertEqual(names, {"t.RefUpdateTest.assertEquals"})


class ParserCacheUpgradeTests(unittest.TestCase):
    def _write_fixture(self, root: Path) -> None:
        write(root, "src/org/junit/Assert.java", JUNIT_ASSERT)
        write(root, "src/org/eclipse/jgit/junit/Assert.java", JGIT_ASSERT)
        write(root, "src/t/RefUpdateTest.java", (
            "package t;\n"
            + JUNIT_IMPORT + JGIT_IMPORT
            + "public class RefUpdateTest {\n"
            + "    void test() { assertEquals(\"msg\", \"value\"); }\n"
            + "}\n"
        ))
        write(root, "src/t/Other.java", "package t; public class Other {}\n")

    def _tamper_old_parser_cache(self, database: Path) -> None:
        """Simulate a V3 parser cache: no version + last-wins target_module."""
        with closing(sqlite3.connect(database)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT id, metadata FROM nodes WHERE kind='File'").fetchall()
            for row in rows:
                metadata = json.loads(row["metadata"])
                if metadata.get("relative_path") != "src/t/RefUpdateTest.java":
                    continue
                parsed = metadata.get("parsed") or {}
                parsed.pop("parser_facts_version", None)
                for reference in parsed.get("references", []):
                    if (
                        reference.get("reference_type") == "CALLS"
                        and reference.get("target") == "assertEquals"
                    ):
                        reference["target_module"] = "org.junit.Assert"
                        reference["metadata"] = {
                            "syntax": "method_invocation",
                            "static_import": True,
                        }
                metadata["parsed"] = parsed
                connection.execute(
                    "UPDATE nodes SET metadata=? WHERE id=?",
                    (json.dumps(metadata, sort_keys=True), row["id"]),
                )
            connection.commit()

    def _call_row(self, database: Path) -> tuple[dict, set[str]]:
        with closing(sqlite3.connect(database)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT r.target_module, r.status, r.candidate_symbols, "
                "r.resolved_symbol_id, n.qualified_name AS resolved_name "
                "FROM raw_references r LEFT JOIN nodes n "
                "ON n.id = r.resolved_symbol_id "
                "WHERE r.reference_type='CALLS' AND r.raw_name='assertEquals'"
            ).fetchone()
            ids = json.loads(row["candidate_symbols"])
            names = {
                connection.execute(
                    "SELECT qualified_name FROM nodes WHERE id=?", (item,)
                ).fetchone()[0]
                for item in ids
            }
            return dict(row), names

    def _assert_ambiguous_java_only(self, database: Path) -> None:
        row, names = self._call_row(database)
        self.assertEqual(row["status"], "ambiguous")
        self.assertIsNone(row["resolved_symbol_id"])
        self.assertEqual(
            names,
            {
                "org.junit.Assert.assertEquals",
                "org.eclipse.jgit.junit.Assert.assertEquals",
            },
        )

    def test_no_change_incremental_reparses_stale_parser_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            self._write_fixture(root)
            database = Path(temporary) / "graph.db"
            full_index(root, database)
            self._tamper_old_parser_cache(database)
            result = incremental_update(root, database)
            self.assertTrue(result["changed"])
            self.assertGreaterEqual(result["metrics"]["files_reparsed"], 1)
            self._assert_ambiguous_java_only(database)

    def test_normal_incremental_reparses_unchanged_stale_java(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            self._write_fixture(root)
            database = Path(temporary) / "graph.db"
            full_index(root, database)
            self._tamper_old_parser_cache(database)
            write(root, "src/t/Other.java",
                  "package t; public class Other { int x; }\n")
            result = incremental_update(root, database)
            self.assertTrue(result["changed"])
            self.assertGreaterEqual(result["metrics"]["files_reparsed"], 1)
            self._assert_ambiguous_java_only(database)


if __name__ == "__main__":
    unittest.main()

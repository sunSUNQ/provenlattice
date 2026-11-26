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
    def _call_reference(self, imports: str) -> tuple[dict, set[str]]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            write(root, "src/org/junit/Assert.java", JUNIT_ASSERT)
            write(root, "src/org/eclipse/jgit/junit/Assert.java", JGIT_ASSERT)
            write(root, "src/t/RefUpdateTest.java", (
                "package t;\n"
                + imports
                + "public class RefUpdateTest {\n"
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


if __name__ == "__main__":
    unittest.main()

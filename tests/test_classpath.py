import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from provenlattice.classpath import (
    build_classpath,
    fingerprint_for,
    load_classpath_file,
)


def os_abs(value: str) -> str:
    """Mirror the product normalization (abspath) for environment-portable
    assertions: Path.resolve() expands 8.3 short names on CI runners."""
    return os.path.abspath(value)


class ClasspathContractTests(unittest.TestCase):
    """P2-C contract: manual classpath parsing, validation, fingerprint."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_jar(self, name: str = "lib.jar") -> Path:
        jar = self.root / name
        with zipfile.ZipFile(jar, "w") as zf:
            zf.writestr("a/Hello.class", b"\xca\xfe\xba\xbe")
        return jar

    def test_cp01_single_jar_is_valid_with_stable_fingerprint(self) -> None:
        jar = self.make_jar()
        contract = build_classpath(dependencies=[str(jar)])
        self.assertEqual(contract.status, "valid")
        self.assertTrue(contract.usable)
        self.assertEqual(len(contract.dependencies), 1)
        self.assertTrue(contract.fingerprint.startswith("cp:"))
        again = build_classpath(dependencies=[str(jar)])
        self.assertEqual(contract.fingerprint, again.fingerprint)

    def test_cp02_multiple_jars_and_class_dirs_keep_input_order(self) -> None:
        jar_a = self.make_jar("a.jar")
        jar_b = self.make_jar("b.jar")
        classes = self.root / "classes"
        (classes / "x").mkdir(parents=True)
        contract = build_classpath(dependencies=[str(jar_b), str(classes), str(jar_a)])
        self.assertEqual(contract.dependencies,
                         tuple(str(p).replace("\\", "/") for p in (jar_b, classes, jar_a)))

    def test_cp03_project_roots_and_dependencies_stay_separate(self) -> None:
        src = self.root / "src"
        src.mkdir()
        jar = self.make_jar()
        contract = build_classpath(project_roots=[str(src)], dependencies=[str(jar)])
        self.assertEqual(contract.project_roots,
                         (os_abs(str(src)).replace("\\", "/"),))
        self.assertEqual(contract.dependencies,
                         (os_abs(str(jar)).replace("\\", "/"),))

    def test_cp04_empty_classpath_is_valid_and_usable(self) -> None:
        contract = build_classpath()
        self.assertEqual(contract.status, "empty")
        self.assertTrue(contract.usable)
        self.assertEqual(contract.fingerprint, "cp:empty")

    def test_cp05_missing_path_fails_closed(self) -> None:
        contract = build_classpath(dependencies=[str(self.root / "nope.jar")])
        self.assertEqual(contract.status, "invalid")
        self.assertFalse(contract.usable)
        self.assertIsNone(contract.fingerprint)
        self.assertEqual(contract.issues[0].code, "NOT_FOUND")

    def test_cp06_bad_kind_and_corrupt_jar_fail_closed(self) -> None:
        text_file = self.root / "note.txt"
        text_file.write_text("hello", encoding="utf-8")
        corrupt = self.root / "corrupt.jar"
        corrupt.write_bytes(b"not a zip")
        contract = build_classpath(dependencies=[str(text_file), str(corrupt)])
        self.assertEqual(contract.status, "invalid")
        codes = {issue.code for issue in contract.issues}
        self.assertEqual(codes, {"BAD_KIND", "CORRUPT_JAR"})

    def test_cp07_directory_as_project_root_dependency_is_rejected(self) -> None:
        directory = self.root / "somedir"
        directory.mkdir()
        contract = build_classpath(dependencies=[str(directory)])
        self.assertEqual(contract.status, "valid")  # class dirs are legal deps
        project_contract = build_classpath(project_roots=[str(directory / "none")])
        self.assertEqual(project_contract.issues[0].code, "NOT_FOUND")

    def test_cp08_duplicates_reported_first_occurrence_kept(self) -> None:
        jar = self.make_jar()
        variant = str(jar).replace("\\", "/").upper() if os_windows() else str(jar) + "/"
        contract = build_classpath(dependencies=[str(jar), variant])
        self.assertEqual(len(contract.dependencies), 1)
        self.assertEqual(len(contract.duplicates), 1)

    def test_cp09_windows_paths_with_spaces_and_special_characters(self) -> None:
        spaced = self.root / "lib space;semi&odd.jar"
        with zipfile.ZipFile(spaced, "w") as zf:
            zf.writestr("a/B.class", b"\xca\xfe\xba\xbe")
        contract = build_classpath(dependencies=[str(spaced)])
        self.assertEqual(contract.status, "valid")
        self.assertIn(str(spaced).replace("\\", "/"), contract.dependencies)

    def test_cp10_fingerprint_is_order_sensitive(self) -> None:
        jar_a = self.make_jar("a.jar")
        jar_b = self.make_jar("b.jar")
        one = fingerprint_for((), (str(jar_a), str(jar_b)))
        two = fingerprint_for((), (str(jar_b), str(jar_a)))
        self.assertNotEqual(one, two)

    def test_cp11_relative_entries_resolve_against_base_dir(self) -> None:
        jar = self.make_jar()
        contract = build_classpath(dependencies=["lib.jar"], base_dir=self.root)
        self.assertEqual(contract.status, "valid")
        self.assertEqual(contract.dependencies,
                         (os_abs(str(jar)).replace("\\", "/"),))

    def test_cp12_manifest_file_roles_comments_and_blank_lines(self) -> None:
        src = self.root / "src"
        src.mkdir()
        jar = self.make_jar()
        manifest = self.root / "classpath.txt"
        manifest.write_text(
            "﻿# comment\nproject: " + str(src) + "\n\n" + str(jar) + "\n",
            encoding="utf-8")  # leading BOM must be tolerated
        roots, deps = load_classpath_file(manifest)
        self.assertEqual(roots, [os_abs(str(src))])
        self.assertEqual(len(deps), 1)
        contract = build_classpath(project_roots=roots, dependencies=deps)
        self.assertEqual(contract.status, "valid")

    def test_cp13_fingerprint_changes_when_dependency_set_changes(self) -> None:
        jar_a = self.make_jar("a.jar")
        jar_b = self.make_jar("b.jar")
        before = build_classpath(dependencies=[str(jar_a)])
        after = build_classpath(dependencies=[str(jar_a), str(jar_b)])
        self.assertNotEqual(before.fingerprint, after.fingerprint)
        # freshness contract input: consumers record the fingerprint with each
        # analysis run; a change invalidates cached analyzer results


def os_windows() -> bool:
    import os

    return os.name == "nt"


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

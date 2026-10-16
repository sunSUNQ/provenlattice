"""P2-D java_semantic module tests.

JDK-independent contract tests always run (fail-closed semantics, merge
policy, availability). The end-to-end driver path is covered by the
skipUnless(JDK) class so CI machines without a JDK stay green."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from provenlattice import java_semantic as jsem
from provenlattice.graph import full_index


def _fake_env(**overrides):
    base = {"PATH": "C:\\nothing" if __import__("os").name == "nt" else "/nothing"}
    base.pop("PL_JAVA_JDK", None)
    base.pop("JAVA_HOME", None)
    base.pop("PL_JAVA_JDT_CLASSPATH", None)
    base.update(overrides)
    return base


class AvailabilityTests(unittest.TestCase):
    def test_no_jdk_yields_unavailable_jdk_not_found(self) -> None:
        with mock.patch.dict("os.environ", _fake_env(), clear=True):
            info = jsem.availability()
        self.assertEqual(info["status"], "unavailable")
        self.assertEqual(info["reason"], "jdk_not_found")
        self.assertFalse(info["jdk_found"])

    def test_jdk_without_jdt_classpath_yields_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            jdk = Path(temp) / "jdk"
            (jdk / "bin").mkdir(parents=True)
            exe = "javac.exe" if __import__("os").name == "nt" else "javac"
            (jdk / "bin" / exe).write_bytes(b"")
            java = "java.exe" if __import__("os").name == "nt" else "java"
            (jdk / "bin" / java).write_bytes(b"")
            with mock.patch.dict("os.environ", _fake_env(PL_JAVA_JDK=str(jdk)), clear=True):
                info = jsem.availability()
        self.assertEqual(info["reason"], "jdt_classpath_not_configured")
        self.assertEqual(info["status"], "unavailable")


class ClasspathRefusalTests(unittest.TestCase):
    def test_invalid_classpath_manifest_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src").mkdir(parents=True)
            (root / "src" / "A.java").write_text("class A { }\n", encoding="utf-8")
            full_index(root, root / "db.sqlite")
            manifest = root / "cp.txt"
            manifest.write_text(f"dep: {root / 'missing.jar'}\n", encoding="utf-8")
            with mock.patch.dict("os.environ", _fake_env(
                    PL_JAVA_JDK="C:\\definitely-not-a-jdk",
                    PL_JAVA_JDT_CLASSPATH="C:\\definitely-not-jdt.jar"), clear=True):
                with mock.patch.object(jsem, "_find_jdk",
                                       return_value=str(root / "fakejdk")), \
                     mock.patch.object(jsem, "_jdt_classpath",
                                       return_value=str(root / "fakejdt.jar")):
                    result = jsem.run_jdt_analysis(
                        root, classpath_manifest=manifest, timeout_s=5)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.reason, "classpath_contract_invalid")
        self.assertIn("classpath_fingerprint", result.meta)


class MergePolicyTests(unittest.TestCase):
    def test_merge_is_file_scoped(self) -> None:
        """P2-E closure fix: two files sharing a line number must not leak
        L1 rows into each other's merge audit (line-only matching bug)."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src" / "a").mkdir(parents=True)
            (root / "src" / "a" / "One.java").write_text(
                "package a;\npublic class One {\n"
                "    public void go() { runner(); }\n"   # line 3
                "    public void runner() { }\n}\n", encoding="utf-8")
            (root / "src" / "a" / "Two.java").write_text(
                "package a;\npublic class Two {\n"
                "    public void go() { other(); }\n"    # line 3 (same!)
                "    public void other() { }\n}\n", encoding="utf-8")
            db = root / "db.sqlite"
            full_index(root, db)
            bindings = [jsem.SemanticBinding(
                file="src/a/One.java", line=3, expr="runner",
                decl="a.One", state="resolved")]
            result = jsem.SemanticResult(status="available", bindings=bindings,
                                         meta={"classpath_fingerprint": "cp:x"})
            merged = jsem.merge_with_l1(result, db)
            site = merged["sites"][0]
            self.assertEqual(len(site["l1"]), 1)
            # the file-scoped match returns One's own runner row, never
            # Two.java's same-line row
            self.assertIn("a.One.runner", site["l1"][0]["target"])
            self.assertNotIn("Two.go", site["l1"][0]["target"])

    def _l1_db(self, root: Path) -> Path:
        db = root / "db.sqlite"
        full_index(root, db)
        return db

    def test_merge_states(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src" / "a").mkdir(parents=True)
            (root / "src" / "a" / "Owner.java").write_text(
                "package a;\npublic class Owner {\n"
                "    public Object get(String k) { return k; }\n"
                "    public void go(String k) { helper(k); }\n"
                "    public void helper(String k) { }\n}\n", encoding="utf-8")
            db = self._l1_db(root)
            bindings = [
                # L1 exact-tier row on the same line agrees with JDT
                jsem.SemanticBinding("src/a/Owner.java", 3, "get",
                                     "a.Owner", "resolved", "get()"),
                # L1 ambiguous (post-P2-A identifier-receiver) -> recovered
                jsem.SemanticBinding("src/a/Owner.java", 4, "helper",
                                     "a.Owner", "resolved", "helper()"),
                # JDT ambiguous -> never fabricated
                jsem.SemanticBinding("src/a/Owner.java", 4, "unknownX",
                                     None, "ambiguous"),
            ]
            result = jsem.SemanticResult(status="available", bindings=bindings,
                                         meta={"classpath_fingerprint": "cp:x"})
            merged = jsem.merge_with_l1(result, db)
            counts = merged["counts"]
            self.assertEqual(counts.get("l1_and_jdt_agree"), 1)
            self.assertEqual(counts.get("recovered_by_jdt"), 1)
            self.assertEqual(counts.get("jdt_ambiguous"), 1)
            for site in merged["sites"]:
                self.assertEqual(site["provenance"], "semantic:jdt-v1")
                self.assertEqual(site["classpath_fingerprint"], "cp:x")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

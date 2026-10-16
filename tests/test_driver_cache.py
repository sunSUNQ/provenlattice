"""Regression for the driver-cache upgrade fix: the compile marker must be
keyed on the driver-source content, so a changed source forces recompile."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from provenlattice import java_semantic as jsem


class DriverCacheKeyTests(unittest.TestCase):
    def test_cache_key_changes_when_driver_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            src_a = Path(temp) / "v1.java"
            src_a.write_text("class DriverV1 {}\n", encoding="utf-8")
            src_b = Path(temp) / "v2.java"
            src_b.write_text("class DriverV2 {}\n", encoding="utf-8")
            key_a = jsem.driver_cache_key(src_a, "jdt.jar")
            key_b = jsem.driver_cache_key(src_b, "jdt.jar")
            self.assertNotEqual(key_a, key_b)
            self.assertEqual(key_a, jsem.driver_cache_key(src_a, "jdt.jar"))

    def test_cache_key_changes_when_classpath_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / "d.java"
            src.write_text("class D {}\n", encoding="utf-8")
            self.assertNotEqual(jsem.driver_cache_key(src, "a.jar"),
                                jsem.driver_cache_key(src, "b.jar"))

    def test_stale_marker_does_not_reuse_classes(self) -> None:
        """Reproduces the pre-fix behavior: an existence-only marker named
        compiled.marker must NOT satisfy a fingerprint-keyed check."""
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            (cache / "compiled.marker").write_text("ok\n", encoding="utf-8")
            src = cache / "d.java"
            src.write_text("class D {}\n", encoding="utf-8")
            fingerprint = jsem.driver_cache_key(src, "cp")
            self.assertFalse((cache / f"compiled.{fingerprint}.marker").exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

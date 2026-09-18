"""V1.4-Windows Finite-Root Isolation Profile tests: robocopy regression,
deny-window roundtrip, finite-root leakage classification, amendment seal.

Run:  PYTHONPATH=src python -m unittest experiments.query_interface_v1.tests.test_v14_finite_root_profile -v
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WORKSPACE = REPO.parent
TOOLS = Path(__file__).resolve().parent.parent / "tools"
for _p in (str(TOOLS), str(REPO), str(REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import v14_sandbox  # noqa: E402
from sqi_formal_runner import verify_seal  # noqa: E402
from v14_c4_lifecycle import (  # noqa: E402
    WINDOW_READ_DENY, CellWindow, classify_leakage)
from v14_feasibility_noreboot import apply_deny, probe, remove_deny  # noqa: E402


class TestRobocopyRegression(unittest.TestCase):
    """P6: "XD .git" as bare tokens after options was parsed as a file filter,
    producing a degenerate near-empty copy. The fixed call must copy content."""

    def test_disposable_copy_copies_content_and_excludes_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "repo"
            (src / ".git" / "objects").mkdir(parents=True)
            (src / "src").mkdir(parents=True)
            (src / "docs" / "deep").mkdir(parents=True)
            for rel in ("README.md", "src/main.py", "docs/deep/a.md",
                        ".git/HEAD", ".git/objects/ab"):
                (src / rel).write_text("x", encoding="utf-8")
            target = Path(tmp) / "copy"
            v14_sandbox.build_disposable_copy(src, target)
            copied = sorted(str(p.relative_to(target)).replace("\\", "/")
                            for p in target.rglob("*") if p.is_file())
            self.assertIn("README.md", copied)
            self.assertIn("src/main.py", copied)
            self.assertIn("docs/deep/a.md", copied)
            self.assertEqual([c for c in copied if c.startswith(".git")], [])


class TestDenyWindowRoundtrip(unittest.TestCase):
    """P1/P2/P7: a single inheritable (OI)(CI)(RD) deny ACE on the root must
    block content reads and listings for the invoking user, keep the ACL
    repairable, and be removable in one step."""

    def test_apply_verify_remove_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tree"
            (root / "a" / "b").mkdir(parents=True)
            files = [root / "top.txt", root / "a" / "mid.txt", root / "a" / "b" / "leaf.txt"]
            for f in files:
                f.write_text("x", encoding="utf-8")
            self.assertTrue(apply_deny(root, WINDOW_READ_DENY)["rc"] == 0)
            try:
                for f in files:
                    self.assertTrue(probe(str(f))["denied"], f"not denied: {f}")
                self.assertTrue(probe(str(root / "a"))["denied"])
            finally:
                self.assertTrue(remove_deny(root)["rc"] == 0)
            for f in files:
                self.assertTrue(probe(str(f))["readable"], f"not restored: {f}")


class TestLeakageClassification(unittest.TestCase):
    """Finite-root semantics: runtime-internal references are documented, not
    leaks; anything pointing outside the runtime root is SENSITIVE."""

    def test_classification(self):
        leaks = [
            {"operation": "shell", "target": 'ls "D:/pl-c4-runtime/benchmark/aria2"'},
            {"operation": "shell", "target": "python -c open('D:\\\\ChatGPT\\\\codegraph\\\\provenlattice\\\\README.md')"},
            {"operation": "grep", "target": "some plain code pattern"},
        ]
        out = classify_leakage(leaks)
        self.assertFalse(out[0]["sensitive"])
        self.assertTrue(out[1]["sensitive"])
        self.assertFalse(out[2]["sensitive"])


class TestAmendmentSeal(unittest.TestCase):
    """The frozen amendment seal must round-trip via verify_seal()."""

    def test_amendment_seal_pass(self):
        seal = (REPO / "experiments" / "query_interface_v1" / "contract" /
                "sqi-v1.4-finite-root-isolation-amendment.sha256")
        if not seal.exists():
            self.fail("amendment seal file missing")
        ok, passed, total, mismatched = verify_seal(seal)
        self.assertTrue(ok, f"seal mismatches: {mismatched}")
        self.assertGreaterEqual(total, 5)


if __name__ == "__main__":
    unittest.main()

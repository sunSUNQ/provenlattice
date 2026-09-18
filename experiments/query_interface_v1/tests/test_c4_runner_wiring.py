"""C4 runner lifecycle wiring tests: prove the frozen fail-closed semantics.

Every test runs the REAL CellWindow machinery against SYNTHETIC roots
(injectable since the lifecycle extension), so no frozen asset is ever at
risk and no agent session is executed.

Run:  PYTHONPATH=src python -m unittest experiments.query_interface_v1.tests.test_c4_runner_wiring -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TOOLS = Path(__file__).resolve().parent.parent / "tools"
for _p in (str(TOOLS), str(REPO), str(REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqi_c4_runner import (  # noqa: E402
    C4BatchHalted, C4BatchRunner, frozen_cell_order, order_fingerprint)
from sqi_formal_runner import load_config, load_tasks  # noqa: E402
from v14_c4_lifecycle import (  # noqa: E402
    WINDOW_READ_DENY, WINDOW_WRITE_DENY, WRITE_DENY_FILE, CellWindow)
from v14_feasibility_noreboot import probe  # noqa: E402

CHECKOUT_PATH = "D:\\ChatGPT\\codegraph\\provenlattice\\tasks\\SQI-T04.json"


def stub_evaluate(task, arm, output, events, call_log, database):
    return {"task_success": True, "capability_failure_flags": []}


def benign_session(cell, surface, config):
    return {"exit_reason": "completed", "error": None, "events": [],
            "output": "ok", "call_log": [], "permission_denials": []}


class WiringTestBase(unittest.TestCase):
    """Synthetic frozen roots + real CellWindow semantics."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.checkout = tmp / "frozen-checkout"
        (self.checkout / "tasks").mkdir(parents=True)
        (self.checkout / "README.md").write_text("top", encoding="utf-8")
        (self.checkout / "tasks" / "SQI-T04.json").write_text(
            "ground-truth", encoding="utf-8")
        self.repo = tmp / "frozen-repo"
        self.repo.mkdir()
        (self.repo / "README").write_text("repo", encoding="utf-8")
        self.drift_blob = tmp / "drift-blob.bin"
        self.drift_blob.write_bytes(b"v1")
        self.db = tmp / "frozen.db"
        self.db.write_bytes(b"SQLite format 3\x00" + b"\x00" * 16)
        self.batch_dir = tmp / "batch"
        self.probes = [("checkout_readme", str(self.checkout / "README.md")),
                       ("tasks_fixture", str(self.checkout / "tasks" /
                                             "SQI-T04.json"))]
        self.roots = [(self.checkout, WINDOW_READ_DENY),
                      (self.repo, WINDOW_WRITE_DENY),
                      (self.db, WRITE_DENY_FILE)]
        self.windows = []
        self.config = load_config()
        self.tasks = load_tasks()

    def tearDown(self):
        self._tmp.cleanup()

    def factory(self):
        def _make(label):
            window = CellWindow(
                label, roots=list(self.roots), verify_probes=list(self.probes),
                fingerprint_repos={"fake": self.repo},
                fingerprint_dbs=[self.db, self.drift_blob])
            self.windows.append(window)
            return window
        return _make

    def runner(self, session_fn):
        return C4BatchRunner(
            self.config, self.tasks, "TEST-C4-BATCH", self.batch_dir,
            window_factory=self.factory(), session_fn=session_fn,
            evaluate_fn=stub_evaluate)

    def cells(self, count=2):
        return [{"task_id": "SQI-T01", "arm": "native", "repetition": i + 1}
                for i in range(count)]

    def assert_restored(self):
        for name, path in self.probes:
            self.assertTrue(probe(path)["readable"], f"not restored: {name}")


class TestNormalCellLifecycle(WiringTestBase):

    def test_normal_cells_complete_and_restore(self):
        runner = self.runner(benign_session)
        records = runner.run_batch(self.cells(2))
        self.assertEqual(len(records), 2)
        self.assertTrue(all(r["status"] == "completed" for r in records))
        self.assertTrue(all(r["sensitive_leakage_events"] == 0
                            for r in records))
        self.assertTrue(all(r["isolation"]["window_closed_verified"]
                            for r in records))
        self.assertTrue(all(r["isolation"]["restore_verified"]
                            for r in records))
        self.assertTrue(all(r["isolation"]["fingerprint_unchanged"]
                            for r in records))
        self.assert_restored()
        window = self.windows[-1]
        self.assertEqual(window.state["pre_repos"], window.state["post_repos"])
        self.assertEqual(window.state["pre_dbs"], window.state["post_dbs"])


class TestFailClosedHalts(WiringTestBase):

    def test_sensitive_leakage_halts_and_restores(self):
        calls = []

        def leaking_session(cell, surface, config):
            calls.append(cell["cell_id"])
            return {"exit_reason": "completed", "error": None,
                    "events": [{"operation": "shell",
                                "query": f"python -c open('{CHECKOUT_PATH}')"}],
                    "output": "ok", "call_log": [],
                    "permission_denials": []}

        runner = self.runner(leaking_session)
        with self.assertRaises(C4BatchHalted) as ctx:
            runner.run_batch(self.cells(2))
        self.assertEqual(ctx.exception.reason, "INVALID_LEAKAGE")
        self.assertEqual(calls, [self.cells(1)[0]["task_id"] + ".native.r1"])
        self.assert_restored()
        marker = json.loads((self.batch_dir / "batch-status-marker.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(marker["reason"], "INVALID_LEAKAGE")
        self.assertEqual(marker["cells_executed"],
                         [self.cells(1)[0]["task_id"] + ".native.r1"])

    def test_fingerprint_drift_halts(self):
        calls = []

        def drifting_session(cell, surface, config):
            calls.append(cell["cell_id"])
            with open(self.drift_blob, "ab") as handle:
                handle.write(b"-drift")
            return benign_session(cell, surface, config)

        runner = self.runner(drifting_session)
        with self.assertRaises(C4BatchHalted) as ctx:
            runner.run_batch(self.cells(2))
        self.assertEqual(ctx.exception.reason, "INVALID_FINGERPRINT_DRIFT")
        self.assertEqual(len(calls), 1)
        self.assert_restored()

    def test_restore_failure_halts(self):
        class FailingWindow:
            def __init__(self):
                self.state = {"applied": [], "removed": [],
                              "pre_repos": {}, "post_repos": {},
                              "pre_dbs": {}, "post_dbs": {},
                              "window_closed_verified": {"probes": {},
                                                         "closed": True},
                              "restore_verified": {
                                  "probes": {"checkout_readme": {
                                      "readable": False, "denied": True}},
                                  "restored": False}}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                raise RuntimeError(
                    "CellWindow restore integrity FAILURE: simulated")

        made = []

        def factory(label):
            window = FailingWindow()
            made.append(label)
            return window

        calls = []
        runner = C4BatchRunner(
            self.config, self.tasks, "TEST-C4-BATCH", self.batch_dir,
            window_factory=factory,
            session_fn=lambda cell, surface, config:
                calls.append(cell["cell_id"]) or benign_session(
                    cell, surface, config),
            evaluate_fn=stub_evaluate)
        with self.assertRaises(C4BatchHalted) as ctx:
            runner.run_batch(self.cells(2))
        self.assertEqual(ctx.exception.reason, "INVALID_RESTORE")
        self.assertEqual(len(calls), 1)

    def test_unexpected_exception_halts(self):
        calls = []

        def broken_session(cell, surface, config):
            calls.append(cell["cell_id"])
            raise ValueError("simulated session crash")

        runner = self.runner(broken_session)
        with self.assertRaises(C4BatchHalted) as ctx:
            runner.run_batch(self.cells(2))
        self.assertEqual(ctx.exception.reason, "INVALID_UNEXPECTED")
        self.assertEqual(len(calls), 1)
        self.assert_restored()
        marker = json.loads((self.batch_dir / "batch-status-marker.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(marker["reason"], "INVALID_UNEXPECTED")

    def test_window_enter_failure_maps_to_invalid_execution(self):
        class UnclosableWindow:
            def __init__(self):
                self.state = {"applied": [], "removed": [],
                              "pre_repos": {}, "post_repos": {},
                              "pre_dbs": {}, "post_dbs": {},
                              "window_closed_verified": {
                                  "probes": {"x": {"readable": False,
                                                   "denied": True}},
                                  "closed": False},
                              "restore_verified": None}

            def __enter__(self):
                raise RuntimeError("CellWindow failed to close: [...]")

            def __exit__(self, exc_type, exc, tb):
                return False

        calls = []
        runner = C4BatchRunner(
            self.config, self.tasks, "TEST-C4-BATCH", self.batch_dir,
            window_factory=lambda label: UnclosableWindow(),
            session_fn=lambda cell, surface, config:
                calls.append(cell["cell_id"]) or benign_session(
                    cell, surface, config),
            evaluate_fn=stub_evaluate)
        with self.assertRaises(C4BatchHalted) as ctx:
            runner.run_batch(self.cells(1))
        self.assertEqual(ctx.exception.reason, "INVALID_EXECUTION")
        self.assertEqual(len(calls), 0)


class TestFrozenOrder(unittest.TestCase):

    def test_order_is_36_protocol_s3(self):
        config = load_config()
        order = frozen_cell_order(config, load_tasks())
        self.assertEqual(len(order), 36)
        self.assertEqual(order[0], {"task_id": "SQI-T01", "arm": "native",
                                    "repetition": 1})
        self.assertEqual(order[3], {"task_id": "SQI-T01", "arm": "sqi",
                                    "repetition": 1})
        self.assertEqual(order[-1], {"task_id": "SQI-T06", "arm": "sqi",
                                     "repetition": 3})
        fingerprint = order_fingerprint(order)
        self.assertEqual(fingerprint,
                         order_fingerprint(frozen_cell_order(
                             config, load_tasks())))


if __name__ == "__main__":
    unittest.main()

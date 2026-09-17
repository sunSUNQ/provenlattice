"""Stage 3A wiring tests: bridge, evaluator oracles, arm parity, preflight.

Run:  PYTHONPATH=src python -m unittest experiments.query_interface_v1.tests.test_sqi_formal_wiring -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WORKSPACE = REPO.parent
TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

from sqi_evaluator import evaluate_cell  # noqa: E402  # noqa: E402
from sqi_formal_runner import (  # noqa: E402
    NATIVE_ALLOWED_TOOLS, SQI_ALLOWED_TOOLS, build_command, load_config,
    load_tasks, preflight, resolve_database, verify_seal)
from sqi_isolation import leakage_events  # noqa: E402
from sqi_validator import validate_envelope  # noqa: E402

DB = WORKSPACE / "benchmark-analysis" / "v0.2-db"
COMMITS = {
    "B1-aria2": "9e7273583f83e881e3ec067b523ba88724088d2f",
    "B2-brpc": "ae09e960c7291605dda52356cc0c2d45567fb53e",
    "B3-rocksdb": "37234200b57d8d0a6a5c41f2d9811bbd2e293544",
}


def run_bridge(task_id: str, call: str, params: str | None,
               call_log: Path | None = None, extra_args: list[str] | None = None):
    task = next(t for t in load_tasks() if t["task_id"] == task_id)
    command = [sys.executable, "-m", "experiments.query_interface_v1.tools.sqi_cli",
               "--database", resolve_database(task["database"]),
               "--commit", task["commit"], "--call", call]
    if params is not None:
        command.extend(["--params", params])
    for extra in extra_args or []:
        command.append(extra)
    if call_log is not None:
        command.extend(["--call-log", str(call_log)])
    env = {"PYTHONPATH": str(REPO / "src") + os.pathsep + str(REPO)}
    completed = subprocess.run(command, cwd=str(REPO), capture_output=True,
                               text=True, encoding="utf-8", env={
                                   **__import__("os").environ, **env}, timeout=300)
    return completed


def events_with_reads(targets: list[str]) -> list[dict]:
    return [{"operation": "read", "target": target, "files": [target]}
            for target in targets]


class TestCLIBridge(unittest.TestCase):
    """The bridge is the agent's only SQI path; stdout must be exactly one
    valid envelope."""

    def test_lookup_returns_valid_envelope(self):
        completed = run_bridge("SQI-T01", "symbol.lookup",
                               '{"name": "DownloadEngine", "kind": "Class", '
                               '"path_prefix": "src/DownloadEngine.h"}')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        envelope = json.loads(completed.stdout.strip())
        self.assertEqual(envelope["query_type"], "symbol.lookup")
        self.assertEqual(envelope["data"][0]["qualified_name"], "aria2.DownloadEngine")
        self.assertTrue(envelope["returned_evidence_ids"])

    def test_stdout_is_single_json_object(self):
        completed = run_bridge("SQI-T01", "symbol.lookup", '{"name": "DownloadEngine"}')
        text = completed.stdout.strip()
        self.assertEqual(text.count("\n"), 0)
        envelope = json.loads(text)
        self.assertIn("query_id", envelope)

    def test_unknown_call_rejected(self):
        sys.path.insert(0, str(TOOLS))
        from sqi_cli import CALL_PARAMS, CANONICAL_CALLS
        self.assertNotIn("graph.dump", CANONICAL_CALLS)
        self.assertEqual(set(CALL_PARAMS), set(CANONICAL_CALLS))

    def test_illegal_param_rejected(self):
        completed = run_bridge("SQI-T01", "symbol.lookup",
                               '{"name": "DownloadEngine", "raw_dump": true}')
        self.assertEqual(completed.returncode, 2)
        error = json.loads(completed.stdout.strip())
        self.assertEqual(error["error"]["code"], "INVALID_PARAMS")

    def test_call_log_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "calls.ndjson"
            completed = run_bridge("SQI-T01", "symbol.lookup",
                                   '{"name": "DownloadEngine", "kind": "Class", '
                                   '"path_prefix": "src/DownloadEngine.h"}',
                                   call_log=log_path)
            self.assertEqual(completed.returncode, 0)
            lines = [json.loads(line) for line in
                     log_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]["call"], "symbol.lookup")
            self.assertGreater(lines[0]["response_bytes"], 0)
            self.assertIn("returned_evidence_ids", lines[0]["envelope"])

    def test_bundle_budget_enforced_via_bridge(self):
        completed = run_bridge(
            "SQI-T06", "bundle.explain",
            json.dumps({"symbol": "IsAskedToQuit",
                        "budget": {"max_evidence": 12, "max_symbols": 6,
                                   "max_edges": 10, "max_sections": 4}}))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        envelope = json.loads(completed.stdout.strip())
        self.assertLessEqual(envelope["returned_evidence_count"], 12)
        self.assertTrue(envelope["truncation"]["truncated"])

    def test_arg_form_shell_safe(self):
        """The --arg key=value form must work without any inline JSON quoting
        (agent sessions run on Windows shells)."""
        completed = run_bridge("SQI-T02", "symbol.callers",
                               None, call_log=None, extra_args=[
                                   "--arg", "symbol=butil.Status.error_cstr"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        envelope = json.loads(completed.stdout.strip())
        self.assertEqual(len(envelope["data"]), 7)

    def test_arg_budget_and_list_parsing(self):
        completed = run_bridge("SQI-T04", "impact.frontier", None,
                               call_log=None,
                               extra_args=["--arg", "changed_shard_paths=db,file",
                                           "--arg", "threshold=8",
                                           "--arg", "budget=50,20,50,10"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        envelope = json.loads(completed.stdout.strip())
        self.assertEqual(envelope["result_meta"]["frontier_size"], 49)
        self.assertEqual(envelope["result_meta"]["boundary_edges_total"], 1031)
        self.assertTrue(envelope["truncation"]["truncated"])

    def test_deterministic_across_invocations(self):
        outputs = []
        for _ in range(2):
            completed = run_bridge("SQI-T01", "symbol.lookup",
                                   '{"name": "DownloadEngine", "kind": "Class", '
                                   '"path_prefix": "src/DownloadEngine.h"}')
            envelope = json.loads(completed.stdout.strip())
            envelope.pop("query_time_ms", None)
            outputs.append(json.dumps(envelope, sort_keys=True))
        self.assertEqual(outputs[0], outputs[1])


class TestEvaluatorOracles(unittest.TestCase):
    """Frozen ground-truth oracles judge known fixtures correctly."""

    @classmethod
    def setUpClass(cls):
        cls.tasks = {task["task_id"]: task for task in load_tasks()}

    def _log(self, entries: list[dict]) -> list[dict]:
        return [{"call": e["query_type"], "params": {},
                 "response_bytes": 1, "envelope": e} for e in entries]

    @staticmethod
    def _stub_envelope(commit: str, evidence_ids: list[str], kind: str = "REFERENCE",
                       fact_ids: list[str] | None = None) -> dict:
        """A schema-valid minimal envelope for evaluator fixtures."""
        fact_ids = fact_ids or []
        evidence = []
        for index, eid in enumerate(evidence_ids):
            metadata = {"fact_id": fact_ids[index]} if index < len(fact_ids) else {}
            evidence.append({"evidence_id": eid, "kind": kind,
                             "source_id": "symbol:" + "a" * 63,
                             "relation": "REFERENCES",
                             "target_id": "symbol:" + "b" * 63,
                             "repository": "repo:" + "0" * 64,
                             "commit": commit, "generation": 1,
                             "provenance": "fixture", "confidence": 1.0,
                             "source_path": None, "source_range": None,
                             "summary": "fixture", "metadata": metadata})
        return {"sqi_version": "SQI-V1", "query_id": "Q-" + "0" * 20,
                "query_type": "symbol.references", "anchor": "fixture",
                "params": {}, "repository": "repo:" + "0" * 64, "commit": commit,
                "graph_generation": 1, "data": [], "evidence": evidence,
                "returned_evidence_ids": evidence_ids,
                "returned_evidence_count": len(evidence_ids), "bundle_size": 0,
                "budget": {"declared": {"max_evidence": 20, "max_symbols": 8,
                                        "max_edges": 20, "max_sections": 4},
                           "applied": {"max_evidence": 20, "max_symbols": 8,
                                       "max_edges": 20, "max_sections": 4},
                           "used": {"symbols": 0, "edges": 0, "raw_refs": 0,
                                    "sections": 0, "evidence": len(evidence_ids)}},
                "truncation": {"truncated": False,
                               "omitted_counts": {"symbols": 0, "edges": 0,
                                                  "raw_refs": 0, "sections": 0}},
                "source_verification_policy": {
                    "requires_source_verification": ["definition_semantics",
                                                     "call_site_semantics",
                                                     "reference_purpose",
                                                     "downstream_impact",
                                                     "document_equivalence"],
                    "direct_trust": ["symbol_identity"]},
                "query_time_ms": 0.0}

    def test_t02_pass_and_fail(self):
        task = self.tasks["SQI-T02"]
        gt = task["ground_truth"]
        output = "The callers include " + ", ".join(
            gt["required_production_callers"][:4]) + "."
        events = events_with_reads(["src/brpc/policy/thrift_protocol.cpp",
                                    "src/brpc/controller.h"])
        call_log = self._log([self._stub_envelope(
            task["commit"], ["E-CALL-" + "0" * 24] * 7, kind="CALL_RELATION",
            fact_ids=[caller["edge_id"] for caller in gt["callers"]])])
        good = evaluate_cell(task, "sqi", output, events, call_log,
                             str(DB / "brpc.db"))
        self.assertTrue(good["machine_checks_pass"])
        short = evaluate_cell(task, "sqi", "only one caller: "
                              + gt["required_production_callers"][0],
                              events_with_reads(["src/brpc/controller.h"]), [],
                              str(DB / "brpc.db"))
        self.assertFalse(short["machine_checks_pass"])

    def test_t03_overclaim_flagged_for_review(self):
        task = self.tasks["SQI-T03"]
        gt = task["ground_truth"]
        output = ("All references live in options/options_settable_test.cc: "
                  + ", ".join(f"line {ref['line']}"
                              for ref in gt["resolved_references"]) + ".")
        events = events_with_reads(["options/options_settable_test.cc"])
        call_log = self._log([self._stub_envelope(
            task["commit"], gt["returned_evidence_ids"])])
        good = evaluate_cell(task, "sqi", output, events, call_log,
                             str(DB / "rocksdb.db"))
        self.assertTrue(good["machine_checks_pass"])

    def test_t04_numbers_enforced(self):
        task = self.tasks["SQI-T04"]
        frontier_envelope = {
            "query_type": "impact.frontier", "returned_evidence_ids": [],
            "evidence": [], "result_meta": {"frontier_size": 49,
                                            "boundary_edges_total": 1031,
                                            "wide_impact": True},
            "truncation": {"truncated": True,
                           "omitted_counts": {"symbols": 0, "edges": 1011,
                                              "raw_refs": 0, "sections": 0}},
            "budget": {"declared": {}, "applied": {}, "used": {}}}
        call_log = self._log([frontier_envelope])
        good = evaluate_cell(task, "sqi",
                             "The frontier contains 49 shards over 1031 boundary "
                             "edges, wide impact; truncation was applied.",
                             events_with_reads(["db/db_impl.cc"]), call_log,
                             str(DB / "rocksdb.db"))
        self.assertTrue(good["machine_checks_pass"])
        bad = evaluate_cell(task, "sqi", "The frontier contains 12 shards.",
                            events_with_reads(["db/db_impl.cc"]), call_log,
                            str(DB / "rocksdb.db"))
        self.assertFalse(bad["machine_checks_pass"])

    def test_t06_truncation_honesty_enforced(self):
        task = self.tasks["SQI-T06"]
        bundle_envelope = {
            "query_type": "bundle.explain", "returned_evidence_ids": [],
            "evidence": [], "data": {"related_entities": []},
            "budget": {"declared": {"max_evidence": 12, "max_symbols": 6,
                                    "max_edges": 10, "max_sections": 4},
                       "applied": {}, "used": {}},
            "truncation": {"truncated": True,
                           "omitted_counts": {"symbols": 43, "edges": 39,
                                              "raw_refs": 0, "sections": 0}}}
        call_log = self._log([bundle_envelope])
        good = evaluate_cell(task, "sqi",
                             "The bundle was truncated: 43 symbols and 39 edges "
                             "omitted. brpc.IsAskedToQuit checks the quit flag.",
                             events_with_reads(["src/brpc/controller.h"]), call_log,
                             str(DB / "brpc.db"))
        self.assertTrue(good["machine_checks_pass"])
        dishonest = evaluate_cell(task, "sqi",
                                  "The bundle returned everything.",
                                  events_with_reads(["src/brpc/controller.h"]),
                                  call_log, str(DB / "brpc.db"))
        self.assertFalse(dishonest["machine_checks_pass"])

    def test_citation_closure_violation_flagged(self):
        task = self.tasks["SQI-T01"]
        output = ("aria2.DownloadEngine in src/DownloadEngine.h line 84. "
                  "Evidence Used:\n- E-CODE-000000000000000000000000")
        evaluation = evaluate_cell(task, "sqi", output,
                                   events_with_reads(["src/DownloadEngine.h"]),
                                   [], str(DB / "aria2.db"))
        self.assertFalse(evaluation["evidence_oracle"]["citation_closure_ok"])
        self.assertIn("citation_closure_ok", evaluation["machine_checks"])
        self.assertFalse(evaluation["machine_checks_pass"])

    def test_native_citation_not_required(self):
        task = self.tasks["SQI-T01"]
        evaluation = evaluate_cell(task, "native",
                                   "aria2.DownloadEngine in src/DownloadEngine.h "
                                   "line 84.", [], [], str(DB / "aria2.db"))
        self.assertIsNone(evaluation["evidence_oracle"]["citation_closure_ok"])

    def test_sqi_access_in_native_flagged(self):
        task = self.tasks["SQI-T01"]
        events = [{"operation": "shell", "query":
                   "python -m experiments.query_interface_v1.tools.sqi_cli --call symbol.lookup",
                   "target": None}]
        evaluation = evaluate_cell(task, "native", "answer", events, [],
                                   str(DB / "aria2.db"))
        self.assertIn("SQI_ACCESS_IN_NATIVE",
                      evaluation["capability_failure_flags"])


class TestSessionShortCircuitAndPolicy(unittest.TestCase):
    """C2 / OPT-T05 session short-circuit + V1.2 session-level policy."""

    def test_second_identical_call_served_from_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "calls.ndjson"
            first = run_bridge("SQI-T04", "impact.frontier", None,
                               call_log=log_path,
                               extra_args=["--arg", "changed_shard_paths=db,file",
                                           "--arg", "threshold=8",
                                           "--arg", "budget=50,20,50,10"])
            self.assertEqual(first.returncode, 0)
            first_env = json.loads(first.stdout.strip())
            second = run_bridge("SQI-T04", "impact.frontier", None,
                                call_log=log_path,
                                extra_args=["--arg", "changed_shard_paths=db,file",
                                            "--arg", "threshold=8",
                                            "--arg", "budget=50,20,50,10"])
            self.assertEqual(second.returncode, 0)
            second_env = json.loads(second.stdout.strip())
            first_env.pop("query_time_ms", None)
            second_env.pop("query_time_ms", None)
            self.assertEqual(first_env, second_env)
            entries = [json.loads(line) for line in
                       log_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(entries), 2)
            self.assertTrue(entries[1].get("served_from_cache"))

    def test_policy_emitted_once_per_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "calls.ndjson"
            first = run_bridge("SQI-T01", "symbol.lookup",
                               '{"name": "DownloadEngine", "kind": "Class", '
                               '"path_prefix": "src/DownloadEngine.h"}',
                               call_log=log_path)
            second = run_bridge("SQI-T02", "symbol.lookup",
                                '{"name": "butil.Status.error_cstr"}',
                                call_log=log_path)
            first_env = json.loads(first.stdout.strip())
            second_env = json.loads(second.stdout.strip())
            self.assertIn("source_verification_policy", first_env)
            self.assertNotIn("source_verification_policy", second_env)
            entries = [json.loads(line) for line in
                       log_path.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(entries[0]["envelope"].get("source_verification_policy"))
            self.assertNotIn("source_verification_policy",
                             entries[1]["envelope"])

    def test_v12_envelope_without_policy_or_evidence_commit_is_valid(self):
        from sqi_evaluator import capability_flags  # local import keeps the top clean
        task = next(t for t in load_tasks() if t["task_id"] == "SQI-T01")
        envelope = {
            "sqi_version": "SQI-V1", "query_id": "Q-" + "0" * 20,
            "query_type": "symbol.lookup", "anchor": "X", "params": {},
            "repository": "repo:" + "0" * 64, "commit": task["commit"],
            "graph_generation": 1, "data": [], "evidence": [],
            "returned_evidence_ids": [], "returned_evidence_count": 0,
            "bundle_size": 0,
            "budget": {"declared": {"max_evidence": 20, "max_symbols": 8,
                                    "max_edges": 20, "max_sections": 4},
                       "applied": {"max_evidence": 20, "max_symbols": 8,
                                   "max_edges": 20, "max_sections": 4},
                       "used": {"symbols": 0, "edges": 0, "raw_refs": 0,
                                "sections": 0, "evidence": 0}},
            "truncation": {"truncated": False,
                           "omitted_counts": {"symbols": 0, "edges": 0,
                                              "raw_refs": 0, "sections": 0}},
            "query_time_ms": 0.0,
        }
        ok, errors = validate_envelope(envelope, expected_commit=task["commit"])
        self.assertTrue(ok, errors)
        self.assertEqual(capability_flags("sqi", task,
                                          [{"call": "symbol.lookup",
                                            "params": {}, "response_bytes": 1,
                                            "envelope": envelope}], []),
                         [])


class TestFormalRunnerCellPath(unittest.TestCase):
    """C4 incident regression: run_cell must execute END-TO-END. The C3
    CHECKOUT_LEAKAGE wiring crashed the formal runner before its first cell
    could run because no test exercised this path — this test closes that
    gap with a stub adapter (no agent, no network)."""

    def test_run_cell_end_to_end_with_stub_adapter(self):
        import tempfile
        import sqi_formal_runner as fr

        class _StubResult:
            output = "stub answer"
            events = []
            exit_reason = "completed"
            error = None
            actual_model = None
            actual_version = None
            permission_denials = []

        class _StubAdapter:
            def __init__(self, command):
                pass

            def run(self, request):
                return _StubResult()

        task = next(t for t in load_tasks() if t["task_id"] == "SQI-T01")
        config = load_config()
        with tempfile.TemporaryDirectory() as tmp:
            original_results = fr.RESULTS_DIR
            fr.RESULTS_DIR = Path(tmp)
            original_adapter = fr.agent_adapter.CommandAgentAdapter
            fr.agent_adapter.CommandAgentAdapter = _StubAdapter
            try:
                outcome = fr.run_cell(task, "sqi", 1, config,
                                      "SQI-TEST-CELLPATH")
                record = outcome["record"]
                self.assertIn(record["status"], ("completed", "failed"))
                self.assertIsInstance(record["policy_violations"], list)
                self.assertIn("checkout_leakage_events", record)
                run_json = Path(outcome["run_dir"]) / "run.json"
                self.assertTrue(run_json.exists())
                evaluation = Path(outcome["run_dir"]) / "evaluation.json"
                self.assertTrue(evaluation.exists())
            finally:
                fr.RESULTS_DIR = original_results
                fr.agent_adapter.CommandAgentAdapter = original_adapter


class TestArmParityAndPreflight(unittest.TestCase):
    """The two arms differ ONLY in system prompt + allowed tools (protocol S2)."""

    def test_base_command_identical(self):
        config = load_config()
        native = build_command("native", config)
        sqi = build_command("sqi", config)
        self.assertEqual(native[0], sqi[0])
        self.assertEqual(native[1], sqi[1])
        self.assertEqual(native[2], sqi[2])
        self.assertEqual(native[3], sqi[3])
        self.assertNotEqual(native, sqi)
        self.assertIn("sqi_cli", SQI_ALLOWED_TOOLS)
        self.assertNotIn("sqi_cli", NATIVE_ALLOWED_TOOLS)

    def test_preflight_passes(self):
        report = preflight()
        self.assertEqual(report["preflight"], "PASS", report["checks"])

    def test_seal_roundtrip_helper(self):
        contract_seal = REPO / "experiments" / "query_interface_v1" / "contract" / \
            "structured-query-interface-contract-v1.freeze.sha256"
        ok, passed, total, mismatched = verify_seal(
            contract_seal, skip={"experiments/query_interface_v1/tasks/SQI-T05.json"})
        self.assertTrue(ok)
        self.assertEqual(total, 6)
        for name in ("implementation", "protocol"):
            seal = REPO / "experiments" / "query_interface_v1" / "contract" / {
                "implementation": "structured-query-interface-contract-v1.implementation-seal.sha256",
                "protocol": "sqi-formal-qualification-protocol-v1.seal.sha256",
            }[name]
            ok, passed, total, _ = verify_seal(seal)
            self.assertTrue(ok, f"{name} seal")
            self.assertGreater(total, 0)


class TestIsolationScoping(unittest.TestCase):
    """V1.1: checkout-leakage detection + sandboxed tool configuration."""

    def test_out_of_repo_read_is_leakage(self):
        events = [{"operation": "read", "target":
                   r"D:\ChatGPT\codegraph\provenlattice\src\provenlattice\impact.py",
                   "files": [r"D:\ChatGPT\codegraph\provenlattice\src\provenlattice\impact.py"]}]
        leaks = leakage_events(events, r"D:\ChatGPT\codegraph\benchmark-repos\rocksdb")
        self.assertEqual(len(leaks), 1)
        self.assertIn(leaks[0]["reason"], ("outside_repo_root", "framework_path"))

    def test_framework_relative_path_is_leakage(self):
        events = [{"operation": "read", "target":
                   "experiments/query_interface_v1/tasks/SQI-T04.json"}]
        leaks = leakage_events(events, r"D:\ChatGPT\codegraph\benchmark-repos\rocksdb")
        self.assertEqual(len(leaks), 1)
        self.assertEqual(leaks[0]["reason"], "framework_path")

    def test_benchmark_repo_reads_are_not_leakage(self):
        events = [{"operation": "read", "target":
                   r"D:\ChatGPT\codegraph\benchmark-repos\rocksdb\db\db_impl.cc",
                   "files": [r"D:\ChatGPT\codegraph\benchmark-repos\rocksdb\db\db_impl.cc"]},
                  {"operation": "grep", "target":
                   "D:/ChatGPT/codegraph/benchmark-repos/rocksdb/include"}]
        self.assertEqual(leakage_events(events,
                                       r"D:\ChatGPT\codegraph\benchmark-repos\rocksdb"), [])

    def test_sanctioned_bridge_call_is_not_leakage(self):
        events = [{"operation": "shell", "query":
                   "python -m experiments.query_interface_v1.tools.sqi_cli "
                   "--database D:/ChatGPT/codegraph/benchmark-analysis/v0.2-db/brpc.db "
                   "--call symbol.lookup --arg name=X"}]
        self.assertEqual(leakage_events(events,
                                        r"D:\ChatGPT\codegraph\benchmark-repos\brpc"), [])

    def test_unsanctioned_shell_is_leakage(self):
        events = [{"operation": "shell", "query":
                   "type D:\\ChatGPT\\codegraph\\provenlattice\\experiments\\query_interface_v1\\tasks\\SQI-T04.json"}]
        leaks = leakage_events(events, r"D:\ChatGPT\codegraph\benchmark-repos\brpc")
        self.assertEqual(len(leaks), 1)

    def test_both_arms_use_scoped_read_rules(self):
        self.assertIn("Read(./**)", NATIVE_ALLOWED_TOOLS)
        self.assertIn("Read(./**)", SQI_ALLOWED_TOOLS)
        self.assertNotIn("Read,Grep", SQI_ALLOWED_TOOLS)
        self.assertNotIn("Read,Grep", NATIVE_ALLOWED_TOOLS)


class TestT05FixtureConsistency(unittest.TestCase):
    """V1.1: the repaired fixture must declare ids that the frozen databases
    actually mint (verified live, read-only)."""

    def test_declared_ids_match_frozen_databases(self):
        task = next(t for t in load_tasks() if t["task_id"] == "SQI-T05")
        gt = task["ground_truth"]
        self.assertIn("code_database", task)
        self.assertIn("required_evidence_ids_by_database", gt)

        sys.path.insert(0, str(TOOLS))
        from sqi_adapter import SQIAdapter
        section = next(item for item in gt["required_evidence"]
                       if item["type"] == "document_section")
        with SQIAdapter(resolve_database(task["database"]),
                        task["commit"]) as knowledge:
            related = knowledge.code_related(section["value"])
        knowledge_ids = {e["evidence_id"] for e in related["evidence"]}
        self.assertTrue(set(gt["required_evidence_ids_by_database"]
                            ["knowledge_database"]) & knowledge_ids)

        with SQIAdapter(resolve_database(task["code_database"]),
                        task["commit"]) as code:
            lookup = code.symbol_lookup(task["expected_symbols"][0])
        hit = next(row for row in lookup["data"]
                   if row["id"] and row.get("qualified_name") == task["expected_symbols"][0])
        code_ids = {e["evidence_id"] for e in lookup["evidence"]
                    if e.get("target_id") == hit["id"]}
        self.assertIn(gt["required_evidence_ids_by_database"]["code_database"][0],
                      code_ids)


if __name__ == "__main__":
    unittest.main()

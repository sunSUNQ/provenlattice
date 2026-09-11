from __future__ import annotations

import json
import importlib
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ReplayAdapter = importlib.import_module(
    "experiments.retrieval-v1.harness.agent_adapter").ReplayAdapter
evaluate = importlib.import_module(
    "experiments.retrieval-v1.harness.evaluator").evaluate
evaluate_r2 = importlib.import_module(
    "experiments.retrieval-v1.harness.evaluator").evaluate_r2
TaskDefinition = importlib.import_module(
    "experiments.retrieval-v1.harness.models").TaskDefinition
run_task = importlib.import_module(
    "experiments.retrieval-v1.harness.runner").run_task
adapter_module = importlib.import_module(
    "experiments.retrieval-v1.harness.agent_adapter")
audit_run = importlib.import_module(
    "experiments.retrieval-v1.harness.audit").audit_run


class RetrievalHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.task = TaskDefinition.load(
            Path(__file__).parents[1] / "experiments/retrieval-v1/tasks/T01.json"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _output(self) -> str:
        return " ".join([self.task.expected_files[0], self.task.expected_symbols[0],
                          self.task.expected_documents[0],
                          self.task.ground_truth["required_evidence"][0]["heading_path"]])

    def test_each_arm_keeps_same_task_prompt_and_artifacts(self) -> None:
        events = {
            "native": [{"event_type": "tool", "tool": "native", "operation": "read",
                         "target": self.task.expected_files[0], "files": self.task.expected_files,
                         "result_size": 100}],
            "codegraph": [{"event_type": "tool", "tool": "provenlattice", "operation": "symbol",
                            "query": self.task.expected_symbols[0], "returned_nodes": 1}],
            "knowledge": [{"event_type": "tool", "tool": "provenlattice", "operation": "evidence",
                            "query": self.task.expected_documents[0], "evidence_ids": [
                                self.task.expected_relationships[0]["edge_id"]],
                            "used_evidence_ids": [self.task.expected_relationships[0]["edge_id"]],
                            "returned_edges": 1, "returned_evidence": 1}],
        }
        records = []
        for arm in ("native", "codegraph", "knowledge"):
            result = run_task(self.task, arm, Path(self.temp.name), Path(self.temp.name),
                              ReplayAdapter(self._output(), events[arm]), verify_commit=False)
            self.assertEqual(result["run"]["status"], "completed")
            run_path = Path(result["run_dir"]) / "run.json"
            self.assertTrue(run_path.exists())
            for name in ("events.ndjson", "agent-output.txt", "metrics.json", "evaluation.json"):
                self.assertTrue((Path(result["run_dir"]) / name).exists())
            records.append(json.loads(run_path.read_text(encoding="utf-8")))
        self.assertEqual({record["prompt"] for record in records}, {self.task.prompt})
        self.assertEqual({record["repo_commit"] for record in records}, {self.task.commit})

    def test_policy_rejects_knowledge_operation_in_codegraph_arm(self) -> None:
        result = run_task(
            self.task, "codegraph", Path(self.temp.name), Path(self.temp.name),
            ReplayAdapter(self._output(), [{"event_type": "tool", "tool": "provenlattice",
                                            "operation": "evidence"}]), verify_commit=False,
        )
        self.assertEqual(result["run"]["status"], "failed")
        self.assertTrue(any("DISALLOWED_OPERATION:evidence" in item
                            for item in result["run"]["policy_violations"]))

    def test_evaluator_is_deterministic_and_records_graph_utility(self) -> None:
        event_value = {"event_type": "tool", "tool": "provenlattice", "operation": "evidence",
                       "evidence_ids": [self.task.expected_relationships[0]["edge_id"]],
                       "used_evidence_ids": [self.task.expected_relationships[0]["edge_id"]],
                       "returned_edges": 1}
        models = importlib.import_module("experiments.retrieval-v1.harness.models")
        RunRequest, ToolEvent = models.RunRequest, models.ToolEvent
        request = RunRequest("run", self.task.task_id, str(self.temp.name), self.task.commit,
                             "knowledge", self.task.prompt, [], {}, 10)
        event = ToolEvent.from_dict(event_value, request)
        metrics = {"tool_turns": 1}
        first = evaluate(self.task, self._output(), [event], metrics)
        second = evaluate(self.task, self._output(), [event], metrics)
        self.assertEqual(first, second)
        self.assertEqual(first["required_evidence_recall"], 1.0)
        self.assertEqual(first["cross_layer_edge_utilization"], 1.0)

    def test_r2_evaluator_uses_returned_viewed_used_and_ground_truth_ids(self) -> None:
        from provenlattice.evidence import evidence_id
        models = importlib.import_module("experiments.retrieval-v1.harness.models")
        required = evidence_id("CODE_DEFINITION", "repo:test", "file:a", "DEFINES",
                               "symbol:a", "symbol:a")
        optional = evidence_id("CALL_RELATION", "repo:test", "symbol:a", "CALLS",
                               "symbol:b", "edge:ab")
        distractor = evidence_id("CODE_DEFINITION", "repo:test", "file:x", "DEFINES",
                                 "symbol:x", "symbol:x")
        self.task.ground_truth.update({
            "required_evidence_ids": [required], "optional_evidence_ids": [optional],
            "distractor_evidence_ids": [distractor],
        })
        request = models.RunRequest("run", self.task.task_id, str(self.temp.name), self.task.commit,
                                    "codegraph", self.task.prompt, [], {}, 10)
        event = models.ToolEvent.from_dict({
            "tool": "provenlattice", "operation": "explain-symbol",
            "evidence_ids": [required, optional, distractor],
            "viewed_evidence_ids": [required, optional, distractor],
        }, request)
        output = f"{self._output()}\n\nEvidence Used:\n- {required}\n- {optional}"
        first = evaluate_r2(self.task, output, [event], {}, arm="codegraph")
        second = evaluate_r2(self.task, output, [event], {}, arm="codegraph")
        self.assertEqual(first, second)
        self.assertTrue(first["task_success"])
        self.assertEqual(first["required_evidence_recall"], 1.0)
        self.assertEqual(first["evidence_precision"], 1.0)
        self.assertEqual(first["evidence_usage_rate"], 2 / 3)
        self.assertEqual(first["returned_but_unused_evidence"], [distractor])
        unsupported = evidence_id("REFERENCE", "repo:test", "symbol:z", "REFERENCES",
                                  "symbol:q", "raw:z")
        wrong = evaluate_r2(
            self.task, f"{self._output()}\nEvidence Used:\n- {required}\n- {unsupported}", [event], {},
            arm="codegraph")
        self.assertFalse(wrong["task_success"])
        self.assertEqual(wrong["unsupported_claim_count"], 1)

    def test_claude_adapter_sends_frozen_prompt_not_run_request_json(self) -> None:
        models = importlib.import_module("experiments.retrieval-v1.harness.models")
        request = models.RunRequest("run", self.task.task_id, str(self.temp.name), self.task.commit,
                                    "native", self.task.prompt, ["read"], {
                                        "PL_MODEL_ID": "claude-sonnet-4-5-20250929"}, 10)
        completed = type("Completed", (), {"stdout": '{"type":"result","result":"ok","usage":{}}\n',
                                             "stderr": "", "returncode": 0})()
        with patch.object(adapter_module.shutil, "which", return_value="C:/npm/claude.cmd"), \
             patch.object(adapter_module.subprocess, "run", return_value=completed) as mocked:
            result = adapter_module.CommandAgentAdapter(["claude", "-p"]).run(request)
        self.assertEqual(mocked.call_args.kwargs["input"], self.task.prompt)
        self.assertEqual(mocked.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(mocked.call_args.kwargs["errors"], "replace")
        self.assertEqual(mocked.call_args.args[0][0], "C:/npm/claude.cmd")
        self.assertIn("--append-system-prompt", mocked.call_args.args[0])
        self.assertIn("--model", mocked.call_args.args[0])
        self.assertIn("--allowedTools", mocked.call_args.args[0])
        self.assertIn("--safe-mode", mocked.call_args.args[0])
        self.assertEqual(result.output, "ok")

    def test_claude_adapter_records_actual_model_and_permission_denial(self) -> None:
        models = importlib.import_module("experiments.retrieval-v1.harness.models")
        request = models.RunRequest("run", self.task.task_id, str(self.temp.name), self.task.commit,
                                    "codegraph", self.task.prompt, [], {
                                        "PL_MODEL_ID": "claude-sonnet-4-5-20250929"}, 10)
        stdout = "\n".join((
            json.dumps({"type": "system", "subtype": "init",
                        "model": "wrong-model", "claude_code_version": "2.1.268"}),
            json.dumps({"type": "assistant", "message": {"content": [{
                "type": "tool_use", "id": "tool-1", "name": "Bash",
                "input": {"command": "provenlattice explain-symbol Example --json"},
            }]}}),
            json.dumps({"type": "system", "subtype": "permission_denied",
                        "tool_use_id": "tool-1", "tool_name": "Bash", "message": "denied"}),
            json.dumps({"type": "result", "result": "answer", "usage": {}}),
        ))
        completed = type("Completed", (), {"stdout": stdout, "stderr": "", "returncode": 0})()
        with patch.object(adapter_module.shutil, "which", return_value="C:/npm/claude.cmd"), \
             patch.object(adapter_module.subprocess, "run", return_value=completed):
            result = adapter_module.CommandAgentAdapter(["claude", "-p"]).run(request)
        self.assertEqual(result.output, "answer")
        self.assertEqual(result.actual_model, "wrong-model")
        self.assertEqual(result.actual_version, "2.1.268")
        self.assertEqual(len(result.permission_denials), 1)
        self.assertEqual(result.permission_denials[0]["operation"], "explain-symbol")

    def test_repetition_and_frozen_metadata_are_recorded(self) -> None:
        result = run_task(self.task, "native", Path(self.temp.name), Path(self.temp.name),
                          ReplayAdapter(self._output(), []), verify_commit=False, repetition=2,
                          model_id="claude-sonnet-4-5-20250929", claude_version="2.1.267",
                          provenlattice_commit="abc123")
        self.assertTrue(result["run_dir"].endswith(str(Path("native") / "r2")))
        self.assertEqual(result["run"]["run_key"], "T01.native.r2")
        self.assertEqual(result["run"]["model_id"], "claude-sonnet-4-5-20250929")

    def test_audit_accepts_complete_metadata_and_rejects_mismatch(self) -> None:
        result = run_task(self.task, "native", Path(self.temp.name), Path(self.temp.name),
                          ReplayAdapter(self._output(), []), verify_commit=False,
                          model_id="claude-sonnet-4-5-20250929", claude_version="2.1.267",
                          provenlattice_commit="abc123")
        run_path = Path(result["run_dir"]) / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run["agent_actual_commit"] = self.task.commit
        run_path.write_text(json.dumps(run), encoding="utf-8")
        audit = audit_run(result["run_dir"], self.task, "native", 1,
                          "claude-sonnet-4-5-20250929", "2.1.267", "abc123")
        self.assertTrue(audit["valid"], audit["errors"])
        mismatch = audit_run(result["run_dir"], self.task, "native", 1,
                             "claude-opus-4-5-20251101", "2.1.267", "abc123")
        self.assertFalse(mismatch["valid"])


if __name__ == "__main__":
    unittest.main()

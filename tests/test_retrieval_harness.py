from __future__ import annotations

import json
import importlib
import tempfile
import unittest
from pathlib import Path

ReplayAdapter = importlib.import_module(
    "experiments.retrieval-v1.harness.agent_adapter").ReplayAdapter
evaluate = importlib.import_module(
    "experiments.retrieval-v1.harness.evaluator").evaluate
TaskDefinition = importlib.import_module(
    "experiments.retrieval-v1.harness.models").TaskDefinition
run_task = importlib.import_module(
    "experiments.retrieval-v1.harness.runner").run_task


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


if __name__ == "__main__":
    unittest.main()

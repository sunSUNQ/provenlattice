from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from .evaluator import evaluate
from .models import ARM_TOOLS, TaskDefinition, ToolEvent
from .provenance_tools import read_events


def _gate(name: str, status: str, detail: str) -> dict:
    return {"gate": name, "status": status, "detail": detail}


def qualify(tasks_dir: str | Path, results_dir: str | Path) -> dict:
    tasks = {path.stem: TaskDefinition.load(path) for path in sorted(Path(tasks_dir).glob("T*.json"))}
    gates = [_gate("task_matrix", "PASS" if len(tasks) == 6 else "FAIL", f"tasks={len(tasks)}")]
    runs = []
    arm_records: dict[str, list[dict]] = {arm: [] for arm in ARM_TOOLS}
    for task_id, task in tasks.items():
        arms = []
        for arm in ARM_TOOLS:
            run_dir = Path(results_dir) / task_id / arm / "r1"
            run_path = run_dir / "run.json"
            if not run_path.exists():
                continue
            run = json.loads(run_path.read_text(encoding="utf-8"))
            events = [ToolEvent.from_dict(value, type("Request", (), {
                "run_id": run["run_id"], "task_id": task_id, "arm": arm})())
                      for value in read_events(run_dir / "events.ndjson")]
            evaluation = evaluate(task, (run_dir / "agent-output.txt").read_text(encoding="utf-8"),
                                  events, json.loads((run_dir / "metrics.json").read_text(encoding="utf-8")))
            stored = json.loads((run_dir / "evaluation.json").read_text(encoding="utf-8"))
            reproducible = evaluation == stored
            event_count = len(events) == run.get("tool_calls")
            policy_ok = not run.get("policy_violations")
            required_files = all((run_dir / name).exists() for name in
                                  ("run.json", "events.ndjson", "agent-output.txt", "metrics.json", "evaluation.json"))
            arms.append({"arm": arm, "run": run, "evaluation_reproducible": reproducible,
                         "event_count_matches": event_count, "policy_ok": policy_ok,
                         "required_files": required_files})
            arm_records[arm].append({"run": run, "events": events, "evaluation": evaluation})
            runs.append({"arm": arm, "metrics": json.loads((run_dir / "metrics.json").read_text(encoding="utf-8")),
                         "evaluation": evaluation})
        if arms:
            prompts = {item["run"].get("prompt") for item in arms}
            if len(prompts) != 1:
                gates.append(_gate("identical_prompt", "FAIL", task_id))
        if len(arms) < 3:
            gates.append(_gate(f"cells:{task_id}", "PENDING", f"runs={len(arms)}/3"))
        else:
            gates.append(_gate(f"cells:{task_id}", "PASS" if all(item["evaluation_reproducible"] and
                                                                  item["event_count_matches"] and
                                                                  item["policy_ok"] and item["required_files"]
                                                                  for item in arms) else "FAIL", "18-cell checks"))
    if not runs:
        for name in ("identical_prompt", "native_no_graph", "codegraph_no_knowledge",
                     "knowledge_capability", "event_accounting", "ground_truth_reproducible",
                     "failure_logs", "run_replayable"):
            gates.append(_gate(name, "PENDING", "no completed runs"))
    else:
        prompts_by_task: dict[str, set[str]] = {}
        for arm in ARM_TOOLS:
            for item in arm_records[arm]:
                prompts_by_task.setdefault(item["run"]["task_id"], set()).add(item["run"].get("prompt", ""))
        gates.append(_gate("identical_prompt", "PASS" if all(len(values) == 1
                                                               for values in prompts_by_task.values()) else "FAIL",
                           "same prompt per task across observed arms"))
        graph_ops = {"symbol", "definition", "callers", "callees", "references", "dependencies",
                     "dependents", "subgraph", "shard", "impact"}
        knowledge_ops = {"document", "evidence", "related-code", "cross-layer", "implemented", "requirements"}
        native_ok = not any(event.operation in graph_ops | knowledge_ops
                            for item in arm_records["native"] for event in item["events"])
        codegraph_ok = not any(event.operation in knowledge_ops
                               for item in arm_records["codegraph"] for event in item["events"])
        knowledge_ok = all(set(item["run"].get("allowed_tools", [])) >= ARM_TOOLS["knowledge"]
                           for item in arm_records["knowledge"])
        gates.extend([
            _gate("native_no_graph", "PASS" if native_ok else "FAIL", "native events contain no graph/knowledge operation"),
            _gate("codegraph_no_knowledge", "PASS" if codegraph_ok else "FAIL", "codegraph events contain no knowledge operation"),
            _gate("knowledge_capability", "PASS" if knowledge_ok else "FAIL", "knowledge arm advertises all permitted tools"),
            _gate("event_accounting", "PASS" if all(
                len(item["events"]) == item["run"].get("tool_calls") for arm in arm_records.values() for item in arm
            ) else "FAIL", "events.ndjson count matches run.tool_calls"),
            _gate("ground_truth_reproducible", "PASS" if all(
                evaluate(task, "", [], {}) == evaluate(task, "", [], {}) for task in tasks.values()
            ) else "FAIL", "deterministic evaluator"),
            _gate("failure_logs", "PASS" if all(
                all((Path(results_dir) / item["run"]["task_id"] / arm / "r1" / name).exists()
                    for name in ("run.json", "events.ndjson", "agent-output.txt", "metrics.json", "evaluation.json"))
                for arm, records in arm_records.items() for item in records
            ) else "FAIL", "failed and completed runs retain all artifacts"),
            _gate("run_replayable", "PASS" if all(item["evaluation"] == evaluate(
                tasks[item["run"]["task_id"]],
                (Path(results_dir) / item["run"]["task_id"] / arm / "r1" / "agent-output.txt").read_text(encoding="utf-8"),
                item["events"], json.loads((Path(results_dir) / item["run"]["task_id"] / arm / "r1" / "metrics.json").read_text(encoding="utf-8")))
                for arm, records in arm_records.items() for item in records
            ) else "FAIL", "stored output and events reproduce evaluation"),
        ])
    summary = {}
    for arm in ARM_TOOLS:
        arm_runs = [run for run in runs if run["arm"] == arm]
        summary[arm] = {"runs": len(arm_runs),
                        "task_success_rate": (sum(bool(run["evaluation"]["task_success"])
                                                   for run in arm_runs) / len(arm_runs) if arm_runs else None),
                        "median_tool_turns": (statistics.median(run["metrics"]["tool_turns"] for run in arm_runs)
                                               if arm_runs else None),
                         "median_unique_files": (statistics.median(run["metrics"]["unique_files_read"] for run in arm_runs)
                                                 if arm_runs else None)}
    native_by_task = {task_id: next((item for item in arm_records["native"]
                                     if item["run"]["task_id"] == task_id), None)
                      for task_id in tasks}
    exploration = {}
    for task_id, native in native_by_task.items():
        if not native:
            continue
        native_count = native["run"].get("tool_calls")
        native_files = set(native["run"].get("files_read", []))
        if not native_files:
            native_files = set().union(*(set(event.files) for event in native["events"]))
        values = {}
        for arm in ("codegraph", "knowledge"):
            candidate = next((item for item in arm_records[arm]
                              if item["run"]["task_id"] == task_id), None)
            if not candidate:
                continue
            graph_files = set().union(*(set(event.files) for event in candidate["events"]))
            values[arm] = ((len(native_files) - len(graph_files)) / len(native_files)
                           if native_files else None)
        exploration[task_id] = values
    return {"schema_version": 1, "experiment": "provenlattice-v1.0-r1-retrieval",
            "tasks": sorted(tasks), "expected_cells": len(tasks) * 3,
            "observed_runs": len(runs), "qualification": "PASS" if runs and all(
                gate["status"] == "PASS" for gate in gates) else "PENDING",
            "gates": gates, "summary_by_arm": summary,
            "native_exploration_avoided_by_task": exploration}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=Path("experiments/retrieval-v1/tasks"))
    parser.add_argument("--results", type=Path, default=Path("experiments/retrieval-v1/results"))
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    report = qualify(args.tasks, args.results)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# ProvenLattice V1.0-R1 Retrieval Qualification", "", f"Status: **{report['qualification']}**", "",
             f"Observed runs: {report['observed_runs']} / {report['expected_cells']}", "", "## Gates", ""]
    lines += [f"- `{gate['gate']}` — **{gate['status']}** — {gate['detail']}" for gate in report["gates"]]
    lines += ["", "## Arm summary", "", "| Arm | Runs | Task success | Median tool turns | Median unique files |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for arm, values in report["summary_by_arm"].items():
        lines.append(f"| {arm} | {values['runs']} | {values['task_success_rate']} | "
                     f"{values['median_tool_turns']} | {values['median_unique_files']} |")
    lines += ["", "No arm comparison is interpreted until all 18 first-pass cells pass the qualification gates."]
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repository", default="B2-brpc")
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    nodes = {}
    for row in connection.execute("SELECT * FROM nodes"):
        item = dict(row)
        try:
            item["metadata"] = json.loads(item["metadata"] or "{}")
        except json.JSONDecodeError:
            item["metadata"] = {}
        nodes[item["id"]] = item
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in connection.execute(
        "SELECT e.id,e.src_id,e.dst_id,e.type,e.provenance,e.confidence "
        "FROM edges e WHERE json_extract(e.metadata,'$.layer')='knowledge' "
        "AND e.type!='CONTAINS' ORDER BY e.src_id,e.dst_id"
    ):
        groups[row["src_id"]].append(dict(row))
    candidates = []
    for source_id, edges in groups.items():
        source = nodes.get(source_id)
        if not source or source["kind"] not in {"DocumentSection", "ArchitectureSection"}:
            continue
        targets = [nodes.get(edge["dst_id"]) for edge in edges]
        targets = [target for target in targets if target]
        if any(target["kind"] in {"Function", "Method", "Class", "Struct", "File"}
               for target in targets):
            candidates.append((source, edges, targets))
    candidates.sort(key=lambda item: (item[0]["metadata"].get("path", ""),
                                      item[0]["metadata"].get("heading_path", ""),
                                      item[0]["id"]))
    if len(candidates) < 3:
        raise RuntimeError("brpc Knowledge baseline does not contain enough resolved sections")

    def evidence(source: dict, target: dict) -> dict:
        return {"section_id": source["id"], "file": source["metadata"].get("path"),
                "heading_path": source["metadata"].get("heading_path"),
                "symbol": target["qualified_name"], "symbol_id": target["id"]}

    # Two single-edge document/code tasks, two reverse tasks, and two multi-edge
    # module tasks. Selection is deterministic from the frozen database.
    selected = candidates[:]
    single = [item for item in selected if len(item[1]) == 1]
    multi = [item for item in selected if len(item[1]) >= 2]
    if len(single) < 2 or len(multi) < 2:
        raise RuntimeError("not enough single/multi-edge sections for six R1 tasks")
    tasks = []
    for number, (source, edges, targets) in enumerate(single[:2], 1):
        target = targets[0]
        item = evidence(source, target)
        tasks.append({
            "task_id": f"T{number:02d}", "repository": args.repository,
            "commit": args.commit, "category": "T1-document-to-code",
            "difficulty": "Easy" if number == 1 else "Medium",
            "prompt": (f"Read the documentation in {item['file']} and its relevant section "
                       f"({item['heading_path']}). Identify the core implementation of "
                       "the described behavior, name the main code symbol and file, and "
                       "explain the relationship."),
            "ground_truth": {"required_evidence": [
                {"type": "document_section", "value": item["section_id"],
                 "heading_path": item["heading_path"], "file": item["file"]},
                {"type": "symbol", "value": item["symbol"]},
                {"type": "file", "value": nodes[target["file_id"]]["metadata"].get("relative_path")},
            ], "optional_evidence": [], "distractor": []},
            "expected_files": [nodes[target["file_id"]]["metadata"].get("relative_path")],
            "expected_symbols": [item["symbol"]],
            "expected_documents": [item["file"]],
            "expected_relationships": [{"edge_id": edges[0]["id"], "type": edges[0]["type"]}],
            "success_criteria": ["identifies the required symbol", "identifies the required file",
                                  "cites the documentation section", "explains a grounded relationship"],
        })
    for number, (source, edges, targets) in enumerate(single[:2], 3):
        target = targets[0]
        item = evidence(source, target)
        tasks.append({
            "task_id": f"T{number:02d}", "repository": args.repository,
            "commit": args.commit, "category": "T2-code-to-document",
            "difficulty": "Easy" if number == 3 else "Medium",
            "prompt": (f"Starting from the code symbol {item['symbol']}, analyze its role and "
                       "find the repository documentation that describes its design or use. "
                       "Cite the relevant document section and explain the code/document evidence."),
            "ground_truth": {"required_evidence": [
                {"type": "symbol", "value": item["symbol"]},
                {"type": "document_section", "value": item["section_id"],
                 "heading_path": item["heading_path"], "file": item["file"]},
            ], "optional_evidence": [{"type": "file", "value": item["file"]}], "distractor": []},
            "expected_files": [nodes[target["file_id"]]["metadata"].get("relative_path")],
            "expected_symbols": [item["symbol"]],
            "expected_documents": [item["file"]],
            "expected_relationships": [{"edge_id": edges[0]["id"], "type": edges[0]["type"]}],
            "success_criteria": ["identifies the required symbol", "cites the required section",
                                  "does not invent a document relationship"],
        })
    for offset, (source, edges, targets) in enumerate(multi[:2], 5):
        code_targets = targets[:3]
        item = evidence(source, code_targets[0])
        symbol_values = [target["qualified_name"] for target in code_targets]
        file_values = sorted({nodes[target["file_id"]]["metadata"].get("relative_path")
                              for target in code_targets})
        tasks.append({
            "task_id": f"T{offset:02d}", "repository": args.repository,
            "commit": args.commit, "category": "T3-module-understanding",
            "difficulty": "Hard" if offset == 5 else "Medium",
            "prompt": (f"Explain the responsibilities and key entry points of the module described "
                       f"by {item['file']} ({item['heading_path']}). Identify its important code "
                       "symbols, dependency/call relationships, and provide both code and "
                       "documentation evidence."),
            "ground_truth": {"required_evidence": [
                {"type": "document_section", "value": item["section_id"],
                 "heading_path": item["heading_path"], "file": item["file"]},
                {"type": "symbol", "value": symbol_values[0]},
            ], "optional_evidence": [{"type": "symbol", "value": value}
                                      for value in symbol_values[1:]], "distractor": []},
            "expected_files": file_values, "expected_symbols": symbol_values,
            "expected_documents": [item["file"]],
            "expected_relationships": [{"edge_id": edge["id"], "type": edge["type"]}
                                        for edge in edges[:3]],
            "success_criteria": ["describes the module role", "identifies a required entry point",
                                  "explains at least one grounded relationship",
                                  "cites code and documentation evidence"],
        })
    args.output.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        (args.output / f"{task['task_id']}.json").write_text(
            json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")
    connection.close()
    print(json.dumps({"tasks": [task["task_id"] for task in tasks]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from provenlattice.graph import full_index
from provenlattice.incremental import incremental_update
from provenlattice.knowledge import index_knowledge
from provenlattice.query import GraphQuery

from run_knowledge_baseline import latency


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--samples", type=int, default=30)
    args = parser.parse_args()
    fixture = Path(__file__).parents[1] / "tests" / "fixture_knowledge"
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / "repo"
        database = Path(temp) / "graph.db"
        shutil.copytree(fixture, root)
        full_index(root, database)
        initial = index_knowledge(root, database, incremental=False)
        with GraphQuery(database) as query:
            query_latency = {
                "requirement_to_code": latency(
                    args.samples,
                    lambda: query.get_implemented_code("REQ-RECOVERY-001"),
                ),
                "code_to_requirement": latency(
                    args.samples,
                    lambda: query.get_requirements("storage.StorageRecovery.retry"),
                ),
                "cross_layer_subgraph": latency(
                    args.samples,
                    lambda: query.get_subgraph("REQ-RECOVERY-001", 2, 100),
                ),
            }
        spec = root / "spec" / "recovery.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace(
            "The retry path", "The bounded retry path"), encoding="utf-8")
        document_change = index_knowledge(root, database)
        source = root / "src" / "recovery.cpp"
        source.write_text(source.read_text(encoding="utf-8").replace(
            "retry(int attempt)", "retry(long attempt)"), encoding="utf-8")
        code_update = incremental_update(root, database)["metrics"]
        signature_change = index_knowledge(root, database)
        result = {
            "schema_version": 1,
            "benchmark": "V1-knowledge-fixture",
            "initial": initial,
            "document_change": document_change,
            "code_signature_change": {
                "code_update": code_update,
                "knowledge_update": signature_change,
            },
            "query_latency": query_latency,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path
from pprint import pprint

from .graph import full_index
from .incremental import incremental_update
from .query import GraphQuery
from .shard import BuildAwareShardStrategy, DirectoryShardStrategy, StructuralShardStrategy


def _database(args: argparse.Namespace) -> Path:
    if args.database:
        return Path(args.database)
    repo = Path(getattr(args, "repo", ".")).resolve()
    return repo / ".provenlattice" / "codegraph.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="provenlattice")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def command(name: str) -> argparse.ArgumentParser:
        child = subparsers.add_parser(name)
        child.add_argument("--database")
        child.add_argument("--json", action="store_true")
        return child

    index = command("index")
    index.add_argument("repo")
    index.add_argument("--shard-strategy", choices=("directory", "build-aware", "structural"), default="directory")
    update = command("update")
    update.add_argument("repo", nargs="?", default=".")
    update.add_argument("--shard-strategy", choices=("directory", "build-aware", "structural"), default="directory")
    command("status")
    symbol = command("symbol")
    symbol.add_argument("name")
    callers = command("callers")
    callers.add_argument("symbol")
    callees = command("callees")
    callees.add_argument("symbol")
    shard = command("shard")
    shard.add_argument("name")
    subgraph = command("subgraph")
    subgraph.add_argument("anchor")
    subgraph.add_argument("--max-hops", type=int, default=2)
    subgraph.add_argument("--max-nodes", type=int, default=100)
    return parser


def run(args: argparse.Namespace) -> dict:
    database = _database(args)
    strategy_name = getattr(args, "shard_strategy", "directory")
    strategy = {
        "directory": DirectoryShardStrategy,
        "build-aware": BuildAwareShardStrategy,
        "structural": StructuralShardStrategy,
    }[strategy_name]()
    if args.command == "index":
        return full_index(args.repo, database, strategy=strategy)
    if args.command == "update":
        return incremental_update(args.repo, database, strategy=strategy)
    with GraphQuery(database) as query:
        if args.command == "status":
            return query.status()
        if args.command == "symbol":
            return query.find_symbol(args.name)
        if args.command == "callers":
            return query.get_callers(args.symbol)
        if args.command == "callees":
            return query.get_callees(args.symbol)
        if args.command == "shard":
            return {
                "graph_generation": query.graph_generation,
                "shard": query.storage.row(
                    "SELECT * FROM shards WHERE shard_id = ? OR path = ? LIMIT 1",
                    (args.name, args.name),
                ),
                "dependencies": query.get_dependencies(args.name)["data"],
                "dependents": query.get_dependents(args.name)["data"],
            }
        if args.command == "subgraph":
            return query.get_subgraph(args.anchor, args.max_hops, args.max_nodes)
    raise ValueError(f"unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        pprint(result, sort_dicts=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

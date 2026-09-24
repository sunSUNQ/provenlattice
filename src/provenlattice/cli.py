from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from pprint import pprint

from .defect import QUERY_NAMES
from .graph import full_index
from .incremental import incremental_update
from .knowledge import index_knowledge
from .query import GraphQuery
from .semantics import load_defect_patterns
from .shard import BuildAwareShardStrategy, DirectoryShardStrategy, StructuralShardStrategy


def _database(args: argparse.Namespace) -> Path:
    if args.database:
        return Path(args.database)
    repo = Path(getattr(args, "repo", ".")).resolve()
    return repo / ".provenlattice" / "codegraph.db"


def defect_matrix() -> dict:
    """The defect matrix as the pipeline sees it, without opening a database.

    This is stage 4's acceptance question in machine-readable form: per pattern,
    what *confirmation* still needs (`missing_events` / `missing_relations`) is
    separate from what *candidate generation* needs
    (`candidate_coverable_now`). 1.1 answering "no" and "yes" at once is the
    point, not a contradiction.
    """
    return {
        "patterns": [
            {
                "key": pattern.key, "name": pattern.name, "grade": pattern.grade,
                "query": pattern.query, "expanded": pattern.expanded,
                "coverable_now": pattern.coverable_now(),
                "candidate_coverable_now": pattern.candidate_coverable_now(),
                "missing_events": list(pattern.missing_events()),
                "missing_relations": list(pattern.missing_relations()),
                "candidate_missing_events": list(pattern.candidate_missing_events()),
                "candidate_missing_relations": list(pattern.candidate_missing_relations()),
            }
            for pattern in load_defect_patterns()
        ],
        "queries": list(QUERY_NAMES),
    }


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
    knowledge = command("knowledge")
    knowledge.add_argument("repo", nargs="?", default=".")
    knowledge.add_argument("--full", action="store_true", help="rebuild all knowledge documents")
    command("status")
    symbol = command("symbol")
    symbol.add_argument("name")
    definition = command("definition")
    definition.add_argument("symbol")
    callers = command("callers")
    callers.add_argument("symbol")
    callees = command("callees")
    callees.add_argument("symbol")
    references = command("references")
    references.add_argument("symbol")
    dependencies = command("dependencies")
    dependencies.add_argument("shard")
    dependents = command("dependents")
    dependents.add_argument("shard")
    document = command("document")
    document.add_argument("anchor")
    implemented = command("implemented")
    implemented.add_argument("requirement")
    requirements = command("requirements")
    requirements.add_argument("symbol")
    evidence = command("evidence")
    evidence.add_argument("--status", choices=("resolved", "ambiguous", "unresolved"))
    shard = command("shard")
    shard.add_argument("name")
    subgraph = command("subgraph")
    subgraph.add_argument("anchor")
    subgraph.add_argument("--max-hops", type=int, default=2)
    subgraph.add_argument("--max-nodes", type=int, default=100)

    # Choices come from the matrix file, so a typo is a usage error while an
    # unexpanded key (4.2) still reaches the query layer and gets its own
    # "not expanded yet" message -- the two failures are different things.
    defect = command("defect")
    defect.add_argument(
        "--type", default="all",
        choices=["all", *[pattern.key for pattern in load_defect_patterns()], *QUERY_NAMES],
        help="matrix key (4.1), query name (resource_lifetime), or all",
    )
    defect.add_argument("--subject")
    defect.add_argument("--max-hops", type=int, default=64)
    defect.add_argument("--max-paths", type=int, default=8)
    defect.add_argument("--max-candidates", type=int, default=20)
    defect.add_argument("--list", action="store_true",
                        help="print the matrix and its coverage gaps; needs no database")
    # The control column for stage 5C: the same code and the same database with
    # the ownership layer off has to reproduce the pre-5C numbers exactly.
    defect.add_argument("--no-contracts", action="store_true",
                        help="disable the ownership/contract layer (control column)")
    events = command("events")
    events.add_argument("--type", dest="event_type")
    events.add_argument("--owner")
    events.add_argument("--file")
    events.add_argument("--limit", type=int, default=200)
    events.add_argument("--edges", action="store_true")

    def evidence_command(name: str, aliases: list[str] | None = None) -> argparse.ArgumentParser:
        child = subparsers.add_parser(name, aliases=aliases or [])
        child.add_argument("anchor")
        child.add_argument("--database")
        child.add_argument("--json", action="store_true")
        child.add_argument("--max-evidence", type=int, default=20)
        child.add_argument("--max-symbols", type=int, default=8)
        child.add_argument("--max-edges", type=int, default=12)
        child.add_argument("--max-sections", type=int, default=6)
        return child

    evidence_command("explain-symbol", ["explain_symbol"])
    evidence_command("explain-module", ["explain_module"])
    evidence_command("find-related-code", ["find_related_code"])
    evidence_command("find-related-documents", ["find_related_documents"])
    evidence_command("trace-evidence", ["trace_evidence"])
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
    if args.command == "knowledge":
        return index_knowledge(args.repo, database, incremental=not args.full)
    if args.command == "defect" and args.list:
        # Handled before the graph is opened: what a pattern needs is a fact
        # about the vocabulary and the matrix, not about any repository.
        return defect_matrix()
    with GraphQuery(database) as query:
        if args.command == "status":
            return query.status()
        if args.command == "symbol":
            return query.find_symbol(args.name)
        if args.command == "definition":
            return query.get_definition(args.symbol)
        if args.command == "callers":
            return query.get_callers(args.symbol)
        if args.command == "callees":
            return query.get_callees(args.symbol)
        if args.command == "references":
            return query.get_references(args.symbol)
        if args.command == "dependencies":
            return query.get_dependencies(args.shard)
        if args.command == "dependents":
            return query.get_dependents(args.shard)
        if args.command == "document":
            return query.get_document_targets(args.anchor)
        if args.command == "implemented":
            return query.get_implemented_code(args.requirement)
        if args.command == "requirements":
            return query.get_requirements(args.symbol)
        if args.command == "evidence":
            return query.get_evidence_links(status=args.status)
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
        if args.command == "defect":
            return query.get_defect_candidates(
                defect_type=args.type, subject=args.subject, max_hops=args.max_hops,
                max_paths=args.max_paths, max_candidates=args.max_candidates,
                use_contracts=not args.no_contracts,
            )
        if args.command == "events":
            return query.get_semantic_events(
                event_type=args.event_type, owner=args.owner, file=args.file,
                limit=args.limit, include_edges=args.edges,
            )
        budget = {"max_evidence": args.max_evidence, "max_symbols": args.max_symbols,
                  "max_edges": args.max_edges, "max_sections": args.max_sections}
        if args.command in {"explain-symbol", "explain_symbol"}:
            return query.explain_symbol(args.anchor, **budget)
        if args.command in {"explain-module", "explain_module"}:
            return query.explain_module(args.anchor, **budget)
        if args.command in {"find-related-code", "find_related_code"}:
            return query.find_related_code(args.anchor, **budget)
        if args.command in {"find-related-documents", "find_related_documents"}:
            return query.find_related_documents(args.anchor, **budget)
        if args.command in {"trace-evidence", "trace_evidence"}:
            return query.trace_evidence(args.anchor, **budget)
    raise ValueError(f"unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run(args)
    if args.json:
        # A redirected stdout would otherwise be encoded in the console's
        # locale (cp936 here), producing a JSON artifact the tool that wrote
        # it cannot read back. Interactive output keeps the console's own
        # encoding, which is the one the console can actually draw. Streams
        # that cannot be reconfigured (a caller's StringIO) are left alone.
        reconfigure = getattr(sys.stdout, "reconfigure", None)
        if reconfigure is not None and not sys.stdout.isatty():
            reconfigure(encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        pprint(result, sort_dicts=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""SQI-V1 CLI bridge: the ONLY way a formal-session agent consumes SQI.

Prints exactly one JSON envelope (the frozen adapter response) to stdout —
nothing else — so the retrieval harness's structured-result extraction and the
evaluator's citation-closure oracle operate on the same bytes the agent saw.

Two parameter forms (both frozen in the arm prompt):
  --params '{"name": "..."}'                     (JSON object)
  --arg name=... --arg budget=12,6,10,4          (shell-safe key=value form;
      budget = max_evidence,max_symbols,max_edges,max_sections;
      changed_shard_paths = comma-separated; threshold = int)

Usage (agent-facing):
  python -m experiments.query_interface_v1.tools.sqi_cli \
      --database <frozen db path> --commit <frozen sha> \
      --call symbol.lookup --arg name=...

Rules (Contract V1):
  * only the six canonical calls; params outside a call's frozen key set are
    rejected with a structured INVALID_PARAMS error (exit 2);
  * the adapter self-validates every envelope (C1-C4, budget, provenance)
    before it is printed;
  * every invocation is appended as one ndjson line to the session call log
    (env PL_SQI_CALL_LOG or --call-log); the log is evaluator-side evidence and
    includes the full envelope plus response byte count;
  * no extra context, hints, or padding is ever injected into stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from sqi_adapter import SQIAdapter, SQIError  # noqa: E402

CANONICAL_CALLS = ("symbol.lookup", "symbol.callers", "symbol.callees",
                   "symbol.references", "impact.frontier", "code.related",
                   "bundle.explain")

CALL_PARAMS = {
    "symbol.lookup": {"name", "kind", "path_prefix", "budget"},
    "symbol.callers": {"symbol", "budget"},
    "symbol.callees": {"symbol", "budget"},
    "symbol.references": {"symbol", "status", "budget"},
    "impact.frontier": {"changed_shard_paths", "threshold", "budget"},
    "code.related": {"document", "budget"},
    "bundle.explain": {"symbol", "budget"},
}


def _fail(payload: dict) -> int:
    print(json.dumps(payload))
    return 2


def _log_line(path: str | None, entry: dict) -> None:
    if not path:
        return
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def _load_log_entries(path: str | None) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    entries = []
    for line in open(path, encoding="utf-8").read().splitlines():
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _session_has_policy(entries: list[dict]) -> bool:
    return any((entry.get("envelope") or {}).get("source_verification_policy")
               for entry in entries)


def _find_cached(entries: list[dict], call: str, params: dict,
                 database: str, commit: str) -> dict | None:
    """V1.2/OPT-T05 session short-circuit: an identical (call, params,
    database, commit) invocation earlier in the same session is served from
    the deterministic call log without recomputation."""
    wanted = json.dumps(params, ensure_ascii=False, sort_keys=True)
    for entry in entries:
        if entry.get("call") != call or entry.get("error"):
            continue
        same_params = json.dumps(entry.get("params") or {}, ensure_ascii=False,
                                 sort_keys=True) == wanted
        if (same_params and entry.get("database") == database
                and entry.get("commit") == commit):
            return entry.get("envelope")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(prog="sqi_cli", add_help=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--call", required=True, choices=sorted(CANONICAL_CALLS))
    parser.add_argument("--params", default="{}")
    parser.add_argument("--arg", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--code-database",
                        default=os.environ.get("PL_SQI_CODE_DATABASE"))
    parser.add_argument("--call-log", default=os.environ.get("PL_SQI_CALL_LOG"))
    args = parser.parse_args()

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as exc:
        return _fail({"error": {"code": "INVALID_PARAMS_JSON", "message": str(exc)}})
    if not isinstance(params, dict):
        return _fail({"error": {"code": "INVALID_PARAMS_JSON",
                                "message": "params must be a JSON object"}})

    for item in args.arg:
        key, sep, value = item.partition("=")
        if not key or not sep:
            return _fail({"error": {"code": "INVALID_PARAMS_JSON",
                                    "message": f"--arg expects KEY=VALUE, got {item!r}"}})
        if key == "budget":
            try:
                evidence, symbols, edges, sections = (int(part) for part in value.split(","))
            except ValueError:
                return _fail({"error": {"code": "INVALID_PARAMS_JSON",
                                        "message": "budget expects max_evidence,max_symbols,"
                                                   "max_edges,max_sections as ints"}})
            params["budget"] = {"max_evidence": evidence, "max_symbols": symbols,
                                "max_edges": edges, "max_sections": sections}
        elif key == "changed_shard_paths":
            params[key] = [part.strip() for part in value.split(",") if part.strip()]
        elif key == "threshold":
            try:
                params[key] = int(value)
            except ValueError:
                return _fail({"error": {"code": "INVALID_PARAMS_JSON",
                                        "message": "threshold must be an int"}})
        else:
            params[key] = value

    illegal = sorted(set(params) - CALL_PARAMS[args.call])
    if illegal:
        return _fail({"error": {
            "code": "INVALID_PARAMS",
            "message": f"params {illegal} not allowed for {args.call} "
                       f"(allowed: {sorted(CALL_PARAMS[args.call])})"}})

    log_entries = _load_log_entries(args.call_log)

    # session short-circuit (OPT-T05-COMPRESSION): identical earlier invocation
    cached = _find_cached(log_entries, args.call, params, args.database,
                          args.commit)
    if cached is not None:
        print(json.dumps(cached, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")))
        _log_line(args.call_log, {
            "call": args.call,
            "params": params,
            "database": args.database,
            "commit": args.commit,
            "response_bytes": len(json.dumps(cached, ensure_ascii=False,
                                             sort_keys=True,
                                             separators=(",", ":"))),
            "envelope": cached,
            "served_from_cache": True,
        })
        return 0

    try:
        with SQIAdapter(args.database, args.commit,
                        code_database=args.code_database) as adapter:
            if args.call == "symbol.lookup":
                envelope = adapter.symbol_lookup(
                    params.get("name"), kind=params.get("kind"),
                    path_prefix=params.get("path_prefix"),
                    budget=params.get("budget"))
            elif args.call == "symbol.callers":
                envelope = adapter.symbol_callers(params.get("symbol"),
                                                  budget=params.get("budget"))
            elif args.call == "symbol.callees":
                envelope = adapter.symbol_callees(params.get("symbol"),
                                                  budget=params.get("budget"))
            elif args.call == "symbol.references":
                envelope = adapter.symbol_references(
                    params.get("symbol"), status=params.get("status"),
                    budget=params.get("budget"))
            elif args.call == "impact.frontier":
                envelope = adapter.impact_frontier(
                    params.get("changed_shard_paths") or [],
                    threshold=params.get("threshold", 8),
                    budget=params.get("budget"))
            elif args.call == "code.related":
                envelope = adapter.code_related(params.get("document"),
                                                budget=params.get("budget"))
            else:
                envelope = adapter.bundle_explain(params.get("symbol"),
                                                  budget=params.get("budget"))
    except SQIError as exc:
        return _fail({"error": {"code": exc.code, "message": exc.message}})

    line = json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    # V1.2 S8: the policy block is session-level — emitted with the session's
    # first envelope only.
    if _session_has_policy(log_entries):
        envelope.pop("source_verification_policy", None)
        line = json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))
    print(line)
    _log_line(args.call_log, {
        "call": args.call,
        "params": params,
        "database": args.database,
        "commit": args.commit,
        "response_bytes": len(line),
        "envelope": envelope,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

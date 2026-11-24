"""concurrency_context (S2): finite, provable thread synchronization facts.

A query-time reader over the events/sparse_cfg rows. It converts the
THREAD_SPAWN/THREAD_JOIN vocabulary events and the READ/WRITE access facts into
a reusable, honest bundle that the S4/S5 scenario rules will consume.

Fail-closed contract:

* a spawn and a join are paired **only** when their thread-handle identities
  are provably the same object and the spawn precedes the join in program
  order. The events layer does not currently stamp a handle on THREAD_JOIN, so
  this capability reports ``thread_handle_identity`` missing evidence instead of
  pairing by owner + source order (which would merge different threads);
* MAY_PARALLEL is always a **candidate** relation -- never a resolved /
  confirmed / definite parallelism fact. Each candidate is keyed by S1's stable
  ``subject_decl`` identity and carries ``candidate_state`` (``"ambiguous"``
  when the identity is proven, ``"unresolved"`` otherwise), its access events
  and thread entry points, ``evidence_references`` (the access event ids) and
  ``missing_evidence``;
* an unresolved identity (no ``subject_decl``) is marked
  ``candidate_state: "unresolved"`` and reported as missing evidence, never
  merged with a different object by display name alone.
* a local object whose address is handed to a worker (``address_of`` spawn) and
  which has no paired join before its scope exits is reported as a
  ``resource_lifetime`` violation with ``join_count == 0`` and
  ``is_alive_at_access == false``; the pairing still rides the handle identity,
  so a join on a *different* thread never clears the violation. Detach, escape
  through a non-local storage, and complex containers stay unknown and unmarked.

It does not promise a complete happens-before, a memory model, points-to, or a
thread-pool analysis.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from .analysis_call_relation import build_call_site_clones
from .analysis_query import query_analysis
from .concurrency_lock_scenarios import _KNOWN_CALL_KINDS, build_access_lockset
from .models import (
    STORAGE_FIELD,
    STORAGE_FILE_STATIC,
    STORAGE_FUNCTION_STATIC,
    STORAGE_GLOBAL,
    STORAGE_UNKNOWN,
)
from .storage import SQLiteStorage

# The storage classes whose subject can name genuinely shared, cross-thread
# state. `local` and `parameter` are frame-scoped and cannot be half of a
# cross-method pair, so they are subtracted rather than enumerated.
SHARED_STORAGES = frozenset({
    STORAGE_FIELD, STORAGE_FILE_STATIC, STORAGE_FUNCTION_STATIC,
    STORAGE_GLOBAL, STORAGE_UNKNOWN,
})

_ACCESS_EVENT_TYPES = frozenset({"READ", "WRITE"})


def _annotations(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return event.get("annotations") or {}


def _owner(event: Mapping[str, Any]) -> str:
    return event.get("owner_qualified_name") or event.get("owner_symbol_id") or ""


def _byte(value: Any) -> int:
    return int(value or 0)


def build_concurrency_context(
    events: Iterable[Mapping[str, Any]], *,
    cloned_events: Iterable[Mapping[str, Any]] = (),
    call_site_clones: Iterable[Mapping[str, Any]] | None = None,
) -> dict:
    """Build the concurrency_context bundle from sparse_cfg events.

    ``events`` is the ``env["events"]`` list of a ``sparse_cfg`` query. The
    function is pure and deterministic: the same events yield the same bundle,
    with keys and lists in stable order.

    D1 (issue-pilot#91): ``cloned_events`` are the query-time call-site clones
    from ``analysis_call_relation.build_call_site_clones``.  They are rows in
    the same shape as sparse_cfg events whose owner is the caller, so they join
    the same access / thread-context machinery without a second schema.  The
    optional ``call_site_clones`` audit records are re-exposed on the bundle,
    and are absent when the caller does not supply them (the legacy output is
    byte-identical).
    """
    events = list(events) + list(cloned_events)
    spawns: list[Mapping[str, Any]] = []
    joins: list[Mapping[str, Any]] = []
    entry_points: set[str] = set()
    for event in events:
        event_type = event.get("event_type")
        if event_type == "THREAD_SPAWN":
            spawns.append(event)
            thread_function = _annotations(event).get("thread_function", "")
            if thread_function:
                entry_points.add(thread_function)
        elif event_type == "THREAD_JOIN":
            joins.append(event)

    spawn_facts = [
        {
            "event_id": event.get("event_id"),
            "owner": _owner(event),
            "handle": _annotations(event).get("subject", ""),
            "handle_decl": _annotations(event).get("subject_decl", ""),
            "thread_function": _annotations(event).get("thread_function", ""),
            "start_byte": _byte(event.get("start_byte")),
            "end_byte": _byte(event.get("end_byte")),
        }
        for event in spawns
    ]
    join_facts = [
        {
            "event_id": event.get("event_id"),
            "owner": _owner(event),
            "handle": _annotations(event).get("subject", ""),
            "handle_decl": _annotations(event).get("subject_decl", ""),
            "start_byte": _byte(event.get("start_byte")),
            "end_byte": _byte(event.get("end_byte")),
        }
        for event in joins
    ]

    missing_evidence: set[str] = set()
    capability_gaps: list[str] = []
    joins_have_handle = any(join["handle_decl"] for join in join_facts)
    if joins and not joins_have_handle:
        missing_evidence.add("thread_handle_identity")
        capability_gaps.append(
            "THREAD_JOIN carries no thread handle in the events layer, so a "
            "spawn and a join cannot be proven to name the same thread; no "
            "spawn->join pair is asserted"
        )

    # Pair a spawn and a join only when their handle identities are the same
    # declared object (handle_decl) in the same method and the spawn precedes
    # the join. Without a shared handle this must not fire -- pairing two
    # different threads by owner+order would fabricate a happens-before edge.
    spawn_join_pairs: list[dict[str, Any]] = []
    for spawn in spawn_facts:
        if not spawn["handle_decl"]:
            missing_evidence.add("thread_handle_identity")
            continue
        if not spawn["thread_function"]:
            missing_evidence.add("spawn_without_thread_function")
        for join in join_facts:
            if (
                join["handle_decl"] == spawn["handle_decl"]
                and join["owner"] == spawn["owner"]
                and spawn["start_byte"] < join["start_byte"]
            ):
                spawn_join_pairs.append({
                    "owner": spawn["owner"],
                    "handle_decl": spawn["handle_decl"],
                    "thread_function": spawn["thread_function"],
                    "spawn": spawn["event_id"],
                    "join": join["event_id"],
                })

    # R7 (SUB-08): a local object whose address is handed to a worker thread
    # dies when its scope exits. A join on the receiving thread -- proved only
    # by the handle identity, never by owner + source order -- sits inside the
    # same method and therefore before that destroy; without one the worker may
    # still be running when the object dies. A spawn that passes a *local* by
    # address (``thread_argument_form == "address_of"``) and has no paired join
    # is a lifetime violation: ``join_count == 0`` and the object is not alive
    # at the worker's access (``is_alive_at_access == false``). Every other
    # shape -- detach, an already-pointer argument, a non-local storage, a
    # complex container -- stays unknown and is never flagged.
    join_ids_by_handle: dict[str, list[str]] = {}
    for pair in spawn_join_pairs:
        join_ids_by_handle.setdefault(pair["handle_decl"], []).append(pair["join"])

    resource_lifetime: list[dict[str, Any]] = []
    for event in spawns:
        annotations = _annotations(event)
        scoped = annotations.get("thread_argument_decl_scoped", "")
        form = annotations.get("thread_argument_form", "")
        if form != "address_of" or not scoped.startswith("local:"):
            continue
        handle_decl = annotations.get("subject_decl", "")
        if join_ids_by_handle.get(handle_decl):
            continue
        resource_lifetime.append({
            "object": scoped,
            "object_decl": annotations.get("thread_argument_decl", ""),
            "object_name": annotations.get("thread_argument", ""),
            "thread_function": annotations.get("thread_function", ""),
            "handle": annotations.get("subject", ""),
            "handle_decl": handle_decl,
            "spawn_event_id": event.get("event_id"),
            "spawn_start_byte": _byte(event.get("start_byte")),
            "join_count": 0,
            "is_alive_at_access": False,
            "lifecycle_sequence": ["SPAWN", "DESTROY"],
        })

    resource_lifetime.sort(
        key=lambda record: (
            record["object"], record["spawn_start_byte"],
            record["spawn_event_id"] or "",
        ),
    )

    # Shared-object identity uses S1's stable subject_decl. An access whose
    # identity is unresolved (no subject_decl, unknown storage) is kept apart as
    # `unresolved` and never merged with another object by display name alone.
    by_decl: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("event_type") not in _ACCESS_EVENT_TYPES:
            continue
        annotations = _annotations(event)
        subject = annotations.get("subject", "")
        decl = annotations.get("subject_decl", "")
        storage = annotations.get("subject_storage") or STORAGE_UNKNOWN
        if not subject and not decl:
            continue
        if storage not in SHARED_STORAGES:
            continue
        key = decl if decl else f"unresolved\x1f{subject}"
        record = by_decl.setdefault(key, {
            "identity": decl or None,
            "subject": subject,
            "storage": storage,
            "exact": annotations.get("subject_exact", "false"),
            "owners": set(),
            "accesses": [],
        })
        record["owners"].add(_owner(event))
        record["accesses"].append({
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "owner": _owner(event),
            "start_byte": _byte(event.get("start_byte")),
            "end_byte": _byte(event.get("end_byte")),
            "exact": annotations.get("subject_exact", "false"),
        })

    # A thread entry owner is a method whose name is a spawned thread_function;
    # this is how a MAY_PARALLEL candidate is tied to the specific thread entry.
    entry_owners = entry_points
    may_parallel = []
    for key in sorted(by_decl):
        record = by_decl[key]
        if len(record["owners"]) < 2:
            continue
        if record["identity"] is None:
            missing_evidence.add("unresolved_identity")
        accesses = sorted(
            record["accesses"],
            key=lambda access: (access["start_byte"], access["end_byte"], access["event_id"] or ""),
        )
        unresolved = record["identity"] is None
        may_parallel.append({
            "identity": record["identity"],
            "subject": record["subject"],
            "storage": record["storage"],
            "exact": record["exact"],
            "unresolved": unresolved,
            "owners": sorted(record["owners"]),
            "thread_entry_owners": sorted(record["owners"] & entry_owners),
            "accesses": accesses,
            "evidence_references": [
                access["event_id"] for access in accesses if access["event_id"]
            ],
            "missing_evidence": ["identity_unresolved"] if unresolved else [],
            "candidate_state": "unresolved" if unresolved else "ambiguous",
        })

    bundle = {
        "thread_entry_points": sorted(entry_points),
        "spawns": spawn_facts,
        "joins": join_facts,
        "spawn_join_pairs": spawn_join_pairs,
        "resource_lifetime": resource_lifetime,
        "may_parallel": may_parallel,
        "missing_evidence": sorted(missing_evidence),
        "capability_gaps": capability_gaps,
    }
    if call_site_clones is not None:
        bundle["call_site_clones"] = list(call_site_clones)
    return bundle


def _clone_call_sites(repo, database, env: Mapping[str, Any]) -> dict:
    """Run D1's query-time clone over the same file's sparse_cfg facts."""
    root = Path(repo).resolve()
    path = (
        Path(database).resolve() if database
        else root / ".provenlattice" / "codegraph.db"
    )
    with SQLiteStorage(path) as storage:
        return build_call_site_clones(
            env.get("events", []), env.get("file_id"), storage)


def query_concurrency_context(
    repo, file_path: str | None = None, database=None,
) -> dict:
    """Read one file's sparse_cfg facts and build its concurrency_context.

    Python/Java and unbuilt/stale files fall through to the sparse_cfg query's
    own honest status (``unsupported`` / ``not_built`` / ``stale``) -- this
    capability is C/C++ only and never fabricates a context where its inputs are
    absent.

    D1 (issue-pilot#91): the caller's derived contexts are supplied by the
    query-time call-site clone.  The clone is additive and fail-closed; if it
    cannot be derived the base context is returned with an honest gap rather
    than failing the whole query.
    """
    env = query_analysis(repo, "sparse_cfg", file_path=file_path, database=database)
    if env["status"] != "available":
        return {"status": env["status"], "reason": env.get("reason")}
    try:
        clones = _clone_call_sites(repo, database, env)
    except Exception as error:  # noqa: BLE001 -- additive reader, fail closed
        context = build_concurrency_context(env.get("events", []), call_site_clones=[])
        context["missing_evidence"] = sorted(
            set(context["missing_evidence"]) | {"call_site_clone_unavailable"})
        context["capability_gaps"].append(
            "call-site clone derivation failed: %s" % (type(error).__name__,))
        context["status"] = "available"
        return context
    context = build_concurrency_context(
        env.get("events", []),
        cloned_events=clones.get("events", ()),
        call_site_clones=clones.get("call_sites", ()),
    )
    context["status"] = "available"
    return context


def _resolved_call_target(row: Mapping[str, Any]) -> str:
    """A unique direct CALL target, or empty for every unknown shape."""
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            return ""
    if not isinstance(metadata, Mapping):
        return ""
    if (
        row.get("status") != "resolved"
        or not row.get("resolved_symbol_id")
        or metadata.get("call_kind") != "direct"
        # The C++ frontend's legacy rows label even function-pointer calls
        # direct. Only the C syntax classifier provides a trustworthy shape.
        or metadata.get("callee_shape") not in {"identifier", "qualified"}
    ):
        return ""
    return str(row["resolved_symbol_id"])


_TYPE_WORDS = frozenset({
    "void", "char", "short", "int", "long", "float", "double", "signed",
    "unsigned", "bool", "_Bool", "wchar_t", "char8_t", "char16_t",
    "char32_t", "const", "volatile", "restrict", "__restrict",
    "struct", "class", "union", "enum", "typename", "auto",
})
_TAG_WORDS = frozenset({"struct", "class", "union", "enum"})


def _split_top_level(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        if char == separator and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _parameter_type_key(parameter: str) -> str:
    """A parameter's type spelling, without its name or default value.

    The graph's ``signature`` is raw parameter text, so a prototype
    ``void helper(int);`` and a definition ``void helper(int value) {}`` are
    two different strings for one function. Dropping the trailing parameter
    name is enough to reconcile them without merging overloads: the builtin
    type word (or struct/class tag) must be present, otherwise the parameter
    keeps its raw spelling and the follow stays fail-closed.
    """
    text = " ".join(parameter.split())
    if "=" in text:
        text = text.split("=", 1)[0].rstrip()
    if not text:
        return ""
    match = re.match(r"^(.*?)([A-Za-z_]\w*)$", text)
    if match is None:
        return text
    prefix, trailing = match.group(1), match.group(2)
    if trailing in _TYPE_WORDS:
        return text
    if not any(re.search(rf"\b{re.escape(word)}\b", prefix) for word in _TYPE_WORDS):
        return text
    words = prefix.strip().split()
    if words and words[-1] in _TAG_WORDS:
        return text
    return prefix.rstrip()


def _signature_key(signature) -> str:
    """Normalize a function signature for declaration/definition matching."""
    if not signature:
        return ""
    text = str(signature).strip()
    open_index = text.find("(")
    if open_index < 0:
        return text
    depth = 0
    close_index = -1
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                close_index = index
                break
    if close_index < 0:
        return text
    parameters = text[open_index + 1:close_index]
    suffix = text[close_index + 1:]
    if "<" in parameters or ">" in parameters:
        # A template parameter list can contain commas; do not guess.
        return text
    parts = _split_top_level(parameters, ",")
    if len(parts) == 1 and parts[0].strip() == "void":
        parts = []
    normalized = [_parameter_type_key(part) for part in parts if part.strip()]
    return f"({','.join(normalized)}){suffix.strip()}"


def call_lock_inputs(
    repo, database=None, *,
    files: Iterable[str] | None = None,
    events_by_file: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[dict[tuple[str, str, int], str | None], frozenset[str]]:
    """Resolve CALL sites and compute a conservative lock-free callee set.

    Only materialized, current events for an actual function definition can
    prove the absence of reachable lock operations. The greatest fixed point
    keeps fully resolved lock-free cycles lock-free, while a direct lock,
    ambiguous join, indirect call, declaration-only target or unavailable body
    removes the owner and all of its callers from that set.

    ``files`` limits which CALL sites are returned (the per-file lockset query
    passes exactly one); ``None`` covers every CALLS row (the repo-wide defect
    query). ``events_by_file`` supplies already-loaded events:cpp envelopes,
    so the caller that has them does not query them twice.
    """
    root = Path(repo).resolve()
    database = (
        Path(database).resolve() if database
        else root / ".provenlattice" / "codegraph.db"
    )
    call_callees: dict[tuple[str, str, int], str | None] = {}
    with SQLiteStorage(database) as storage:
        references_by_key: dict[tuple[str, str, int], list[dict]] = {}
        for row in storage.rows(
            "SELECT id, file_id, owner_symbol_id, start_line, raw_name, "
            "status, resolved_symbol_id, metadata FROM raw_references "
            "WHERE reference_type='CALLS' ORDER BY id"
        ):
            if row["start_line"] is None:
                continue
            key = (
                str(row["file_id"]), str(row["owner_symbol_id"]),
                int(row["start_line"]),
            )
            references_by_key.setdefault(key, []).append(row)

        node_cache: dict[str, dict | None] = {}
        event_cache: dict[str, Mapping[str, Any] | None] = {}
        # owner -> (has a direct lock operation, resolved ordinary callees).
        # None callees means that no-lock reachability cannot be proven.
        summaries: dict[str, tuple[bool, tuple[str, ...] | None]] = {}

        def node(symbol_id: str) -> dict | None:
            if symbol_id not in node_cache:
                row = storage.row(
                    "SELECT n.id, n.kind, n.file_id, n.qualified_name, "
                    "n.signature, n.language, n.metadata, f.path "
                    "FROM nodes n JOIN files f ON f.file_id=n.file_id "
                    "WHERE n.id=?", (symbol_id,),
                )
                if row is not None:
                    try:
                        row["metadata"] = json.loads(row["metadata"] or "{}")
                    except (TypeError, ValueError):
                        row = None
                node_cache[symbol_id] = row
            return node_cache[symbol_id]

        provided = events_by_file or {}

        def event_file(file_id: str, path: str) -> Mapping[str, Any] | None:
            if file_id not in event_cache:
                candidate = provided.get(file_id)
                if candidate is None:
                    candidate = query_analysis(
                        root, "events", file_path=path, database=database)
                coverage = candidate.get("coverage") or {}
                if (
                    candidate.get("status") != "available"
                    or coverage.get("analysis_status") != "complete"
                    or coverage.get("partial")
                ):
                    event_cache[file_id] = None
                else:
                    event_cache[file_id] = candidate
            return event_cache[file_id]

        file_paths = {
            row["file_id"]: row["path"]
            for row in storage.rows("SELECT file_id, path FROM files")
        }

        def call_leaf(name: str) -> str:
            compact = "".join(str(name).split())
            return re.split(r"::|->|\.", compact)[-1]

        def ordinary_rows(
            rows: list[dict], file_env: Mapping[str, Any] | None,
            owner_symbol_id: str, line: int,
        ) -> list[dict]:
            """Drop reference rows already represented by a known call event.

            `build_access_lockset` excludes the known vocabularies before its
            one-reference-per-line rule; this helper must apply the same filter
            or `pthread_mutex_lock(&m); helper();` on one line makes `helper`
            look ambiguous. An unavailable event file keeps every row, which is
            the fail-closed direction.
            """
            if file_env is None:
                return rows
            known = {
                call_leaf(event.get("matched_name") or "")
                for event in file_env.get("events", [])
                if event.get("owner_symbol_id") == owner_symbol_id
                and event.get("event_type") in _KNOWN_CALL_KINDS
                and int(event.get("start_line") or 0) == line
            }
            if not known:
                return rows
            return [
                row for row in rows
                if call_leaf(row.get("raw_name") or "") not in known
            ]

        def definition_target(symbol_id: str) -> str:
            """Follow a caller-local prototype to its unique compatible definition.

            A call with an explicit `void helper(void);` in the caller's file
            resolves to that declaration even when another file defines it.
            Rejecting the declaration as "no body" loses a provable lock-free
            callee. The follow is deliberately narrow: the candidate must have
            the same normalized signature, the same kind, and -- across files
            -- external linkage on both sides and compatible language linkage.
            A missing linkage (an index built before this fact existed), a
            `static` candidate, an incompatible C/C++ pair, or zero/several
            candidates all keep the call opaque (fail-closed).
            """
            symbol = node(symbol_id)
            if symbol is None or symbol["kind"] not in {"Function", "Method"}:
                return ""
            if symbol["metadata"].get("definition") is True:
                return symbol_id
            expected = _signature_key(symbol.get("signature"))
            candidates = storage.rows(
                "SELECT id FROM nodes WHERE kind=? AND qualified_name=? AND id != ?",
                (symbol["kind"], symbol["qualified_name"], symbol_id),
            )
            definitions: list[str] = []
            for row in candidates:
                candidate = node(row["id"])
                if candidate is None:
                    continue
                if candidate["metadata"].get("definition") is not True:
                    continue
                if _signature_key(candidate.get("signature")) != expected:
                    continue
                if not _compatible_linkage(symbol, candidate):
                    continue
                definitions.append(row["id"])
            return definitions[0] if len(definitions) == 1 else ""

        def _linkage(symbol: dict) -> str:
            return str((symbol.get("metadata") or {}).get("linkage") or "")

        def _compatible_linkage(declaration: dict, definition: dict) -> bool:
            if declaration["file_id"] == definition["file_id"]:
                return True
            if _linkage(declaration) != "external" or _linkage(definition) != "external":
                return False
            left = str(declaration.get("language") or "")
            right = str(definition.get("language") or "")
            if not left or not right:
                return False
            if left == right:
                return True
            if {left, right} != {"c", "cpp"}:
                return False
            cpp_side = declaration if left == "cpp" else definition
            return bool((cpp_side.get("metadata") or {}).get("c_linkage"))

        selected = frozenset(files) if files is not None else None
        pending: list[str] = []
        for key in sorted(references_by_key):
            if selected is not None and key[0] not in selected:
                continue
            rows = ordinary_rows(
                references_by_key[key],
                event_file(key[0], file_paths.get(key[0], "")),
                key[1], key[2],
            )
            resolved = _resolved_call_target(rows[0]) if len(rows) == 1 else ""
            target = definition_target(resolved) if resolved else ""
            call_callees[key] = target or None
            if target:
                pending.append(target)

        while pending:
            symbol_id = pending.pop()
            if symbol_id in summaries:
                continue
            symbol = node(symbol_id)
            if (
                symbol is None
                or symbol["kind"] not in {"Function", "Method"}
                or symbol["metadata"].get("definition") is not True
            ):
                summaries[symbol_id] = (False, None)
                continue
            file_env = event_file(symbol["file_id"], symbol["path"])
            if file_env is None:
                summaries[symbol_id] = (False, None)
                continue
            events = [
                event for event in file_env.get("events", [])
                if event.get("owner_symbol_id") == symbol_id
            ]
            if any(event.get("event_type") in {"LOCK", "UNLOCK"} for event in events):
                summaries[symbol_id] = (True, ())
                continue

            known_call_spans = {
                (int(event.get("start_byte") or 0), int(event.get("end_byte") or 0))
                for event in events
                if event.get("event_type") in _KNOWN_CALL_KINDS
            }
            known_names_by_line: dict[int, set[str]] = {}
            for event in events:
                if event.get("event_type") in _KNOWN_CALL_KINDS:
                    line = int(event.get("start_line") or 0)
                    known_names_by_line.setdefault(line, set()).add(
                        call_leaf(event.get("matched_name") or ""))
            calls_by_line: dict[int, int] = {}
            for event in events:
                if (
                    event.get("event_type") == "CALL"
                    and (
                        int(event.get("start_byte") or 0),
                        int(event.get("end_byte") or 0),
                    ) not in known_call_spans
                ):
                    line = int(event.get("start_line") or 0)
                    calls_by_line[line] = calls_by_line.get(line, 0) + 1
            if any(count != 1 for count in calls_by_line.values()):
                summaries[symbol_id] = (False, None)
                continue

            callees: list[str] = []
            unknown = False
            for line in sorted(calls_by_line):
                key = (str(symbol["file_id"]), symbol_id, line)
                rows = references_by_key.get(key, [])
                known = known_names_by_line.get(line)
                if known:
                    rows = [
                        row for row in rows
                        if call_leaf(row.get("raw_name") or "") not in known
                    ]
                resolved = _resolved_call_target(rows[0]) if len(rows) == 1 else ""
                target = definition_target(resolved) if resolved else ""
                if not target:
                    unknown = True
                    break
                callees.append(target)
            summaries[symbol_id] = (
                False, None if unknown else tuple(callees))
            if not unknown:
                pending.extend(callees)

        lock_free = {
            symbol_id
            for symbol_id, (direct_lock, callees) in summaries.items()
            if not direct_lock and callees is not None
        }
        while True:
            remove = {
                symbol_id for symbol_id in lock_free
                if any(
                    callee not in lock_free
                    for callee in (summaries[symbol_id][1] or ())
                )
            }
            if not remove:
                break
            lock_free.difference_update(remove)

    return call_callees, frozenset(lock_free)


def query_access_lockset(
    repo, file_path: str | None = None, database=None,
) -> dict:
    """Read one file's sparse_cfg + events facts and build its access locksets.

    The per-access ``held_locks`` projection joins S3's lock facts (events) onto
    the sparse-cfg control-flow (edges) by shared lock event id. Python/Java and
    unbuilt/stale files fall through to the sparse_cfg query's own honest status
    -- this capability is C/C++ only and never fabricates a lockset where its
    inputs are absent.
    """
    env = query_analysis(repo, "sparse_cfg", file_path=file_path, database=database)
    if env["status"] != "available":
        return {"status": env["status"], "reason": env.get("reason")}
    lock_env = query_analysis(repo, "events", file_path=file_path, database=database)
    if lock_env["status"] != "available":
        return {"status": lock_env["status"], "reason": lock_env.get("reason")}
    current_file = str(env.get("file_id") or "")
    call_callees, lock_free_callees = call_lock_inputs(
        repo, database,
        files={current_file} if current_file else None,
        events_by_file={current_file: lock_env} if current_file else None,
    )
    bundle = build_access_lockset(
        env.get("events", []),
        env.get("edges", []),
        lock_env.get("events", []),
        call_callees=call_callees,
        lock_free_callees=lock_free_callees,
    )
    bundle["status"] = "available"
    return bundle


__all__ = [
    "build_concurrency_context",
    "call_lock_inputs",
    "query_concurrency_context",
    "query_access_lockset",
]
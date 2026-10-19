"""Optional analysis orchestrator: scope x features -> derived analysis run."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from .analysis import capability_record, selectable_features
from .analysis_ast import analyze_ast_scope, normalize_scope, scoped_sources
from .analysis_c_ast import analyze_c_ast_scope
from .analysis_c_cfg import ANALYZER as C_CFG_ANALYZER, analyze_c_cfg_scope
from .analysis_java_ast import analyze_ast_scope as analyze_java_ast_scope
from .analysis_java_cfg import analyze_cfg_scope as analyze_java_cfg_scope
from .analysis_c_events import EVENTS_SUFFIXES, analyze_c_events_scope
from .analysis_c_dfg import analyze_c_dfg_scope
from .analysis_c_scfg import analyze_c_scfg_scope
from .analysis_cfg import ANALYZER as CFG_ANALYZER, analyze_cfg_scope
from .identity import path_id
from .scanner import IGNORED_DIRS, SUPPORTED_EXTENSIONS
from .storage import SQLiteStorage

# Implemented optional-analysis capabilities (analysis.py contract is the
# single source of truth; this tuple stays the literal subset so the per-file
# reporting loop is stable).
SUPPORTED_FEATURES = ("ast", "cfg", "events", "sparse_cfg", "sparse_dfg")
FEATURE_DEPENDENCIES = {
    "cfg": ("ast",),
    "sparse_dfg": ("sparse_cfg",),
    # defect is a query-time capability: requesting it materializes its
    # upstream chain and nothing else (the queries read, never build).
    "defect": ("events", "sparse_cfg", "sparse_dfg"),
}
C_SOURCE_SUFFIXES = frozenset({".c", ".h"})
REASON_PREFIX = "skipped_"


def _supports_feature(entry: dict, feature: str) -> bool:
    if feature in ("events", "sparse_cfg", "sparse_dfg"):
        # The semantic analyzers cover the whole C/C++ family (the cpp.toml
        # extension list), not just the .c/.h pair.
        return PurePosixPath(entry["path"]).suffix.lower() in EVENTS_SUFFIXES
    return (
        entry["language"] == "python"
        or PurePosixPath(entry["path"]).suffix.lower() in C_SOURCE_SUFFIXES
    )


def _unsupported_reason(entry: dict, feature: str) -> str:
    return "unsupported_language"


def _merge_feature_results(runs: list[dict]) -> dict:
    """Merge language-specific materializers without exposing a fake analyzer."""
    if not runs:
        raise ValueError("at least one analysis run is required")
    handled = {
        path for run in runs
        for key in ("materialized", "reused")
        for path in run.get(key, [])
    }
    merged = {
        "repo_id": runs[0]["repo_id"],
        "database": runs[0]["database"],
        "scope": runs[0]["scope"],
        "analyzers": [run["analyzer"] for run in runs],
        "contracts": [run["contract"] for run in runs],
        "materialized": sorted({path for run in runs for path in run["materialized"]}),
        "reused": sorted({path for run in runs for path in run["reused"]}),
        "nodes_written": sum(run.get("nodes_written", 0) for run in runs),
        "analyze_time_ms": sum(run.get("analyze_time_ms", 0.0) for run in runs),
    }
    skip_keys = {
        key for run in runs for key in run if key.startswith(REASON_PREFIX)
    }
    # A language-specific run's precise skip reason wins over the generic
    # unsupported_language fallback emitted by the other language's run.
    specific = {
        path for run in runs for key, paths in run.items()
        if key.startswith(REASON_PREFIX) and key != "skipped_unsupported"
        for path in paths
    }
    for key in sorted(skip_keys):
        skipped = {
            path for run in runs for path in run.get(key, [])
            if path not in handled
        }
        if key == "skipped_unsupported":
            skipped -= specific
        merged[key] = sorted(skipped)
    return merged


class AnalysisRequestError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _parse_features(features) -> list[str]:
    if isinstance(features, str):
        requested = [item.strip() for item in features.split(",") if item.strip()]
    else:
        requested = [str(item).strip() for item in features]
    if not requested:
        raise AnalysisRequestError("invalid_features", "no features requested")
    unique: list[str] = []
    for feature in requested:
        record = capability_record(feature)
        if record is not None and feature not in selectable_features():
            # Registered-but-not-implemented capability (I0 contract): fail
            # closed before planning or any mutation -- never a partial run,
            # never a fake success. Distinct from unknown_feature so callers
            # can tell a future capability from a typo. Partially-implemented
            # capabilities (I1-A `events`, I2A `defect`) are selectable:
            # events materializes its subset, defect materializes its
            # upstream chain and answers through the query entry.
            raise AnalysisRequestError(
                "capability_not_available",
                f"capability '{feature}' is registered but not implemented in this "
                f"build (planned integration: {record['planned_integration']}); "
                "nothing was materialized",
            )
        if feature not in SUPPORTED_FEATURES and feature != "defect":
            raise AnalysisRequestError("unknown_feature", f"unsupported feature: {feature}")
        if feature not in unique:
            unique.append(feature)
    return unique


def _plan_features(requested: list[str]) -> list[str]:
    plan = list(requested)
    for feature in requested:
        for dependency in FEATURE_DEPENDENCIES.get(feature, ()):
            if dependency not in plan:
                plan.insert(0, dependency)
    return plan


def _inventory(root: Path, scope_path: PurePosixPath) -> list[dict]:
    entries = []
    for path in sorted(root.joinpath(*scope_path.parts).rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if any(part in IGNORED_DIRS for part in PurePosixPath(relative).parts[:-1]):
            continue
        entries.append({
            "path": relative,
            "language": SUPPORTED_EXTENSIONS.get(path.suffix),
        })
    return entries


def _cfg_file_metadata(database: Path) -> dict[str, dict]:
    with SQLiteStorage(database) as storage:
        exists = storage.row(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_state'"
        )
        if exists is None:
            return {}
        return {
            row["file_id"]: json.loads(row["metadata"])
            for row in storage.rows(
                "SELECT file_id, metadata FROM analysis_state WHERE feature IN (?, ?)",
                (CFG_ANALYZER, C_CFG_ANALYZER),
            )
        }


def analyze_scope(repo: str | Path, scope: str, features, database: str | Path | None = None) -> dict:
    root = Path(repo).resolve()
    requested = _parse_features(features)
    try:
        scope_path = normalize_scope(scope)
    except ValueError as error:
        raise AnalysisRequestError("invalid_scope", str(error)) from error
    if not root.joinpath(*scope_path.parts).is_dir():
        raise AnalysisRequestError("invalid_scope", f"scope directory does not exist: {scope}")
    plan = _plan_features(requested)
    database = Path(database).resolve() if database else root / ".provenlattice" / "codegraph.db"
    with SQLiteStorage(database) as storage:
        if storage.repository() is None:
            raise AnalysisRequestError(
                "base_graph_required", "run `provenlattice index` before analyze"
            )
    results = {}
    if "ast" in plan:
        ast_runs = [analyze_ast_scope(root, scope_path.as_posix(), database)]
        if "ast" in requested or "cfg" in requested:
            ast_runs.append(analyze_c_ast_scope(root, scope_path.as_posix(), database))
            ast_runs.append(analyze_java_ast_scope(root, scope_path.as_posix(), database))
        results["ast"] = _merge_feature_results(ast_runs)
    if "cfg" in plan:
        cfg_runs = [analyze_cfg_scope(root, scope_path.as_posix(), database)]
        cfg_runs.append(analyze_c_cfg_scope(root, scope_path.as_posix(), database))
        cfg_runs.append(analyze_java_cfg_scope(root, scope_path.as_posix(), database))
        results["cfg"] = _merge_feature_results(cfg_runs)
    if "events" in plan:
        results["events"] = _merge_feature_results(
            [analyze_c_events_scope(root, scope_path.as_posix(), database)])
    if "sparse_cfg" in plan:
        results["sparse_cfg"] = _merge_feature_results(
            [analyze_c_scfg_scope(root, scope_path.as_posix(), database)])
    if "sparse_dfg" in plan:
        results["sparse_dfg"] = _merge_feature_results(
            [analyze_c_dfg_scope(root, scope_path.as_posix(), database)])
    if "defect" in plan:
        # query-time capability: the upstream chain above is the whole
        # materialization; candidates are answered by the defect query entry.
        results["defect"] = {
            "repo_id": next(iter(results.values()))["repo_id"],
            "database": str(database), "scope": scope_path.as_posix(),
            "materialized": [], "reused": [], "nodes_written": 0,
            "analyze_time_ms": 0.0, "analyzers": [], "contracts": [],
            "query_time": True,
        }
    categories: dict[str, dict[str, tuple[str, str | None]]] = {}
    for feature, result in results.items():
        mapping: dict[str, tuple[str, str | None]] = {}
        for path in result["materialized"]:
            mapping[path] = ("materialized", None)
        for path in result["reused"]:
            mapping[path] = ("reused", None)
        for key, paths in result.items():
            if key.startswith(REASON_PREFIX):
                reason = key[len(REASON_PREFIX):]
                if reason == "unsupported":
                    reason = "unsupported_language"
                for path in paths:
                    mapping[path] = ("skipped", reason)
        categories[feature] = mapping
    if "cfg" in categories:
        metadata_by_file = _cfg_file_metadata(database)
        repo_id = results["cfg"]["repo_id"]
        for path, (status, reason) in list(categories["cfg"].items()):
            if status != "materialized":
                continue
            metadata = metadata_by_file.get(path_id(repo_id, "File", path), {})
            if metadata.get("functions_built", 0) == 0:
                categories["cfg"][path] = ("skipped", "no_functions_built")
    inventory = _inventory(root, scope_path)
    per_file: list[dict] = []
    counts = {"analyzed": 0, "reused": 0, "skipped": 0}
    for entry in inventory:
        path, language = entry["path"], entry["language"]
        record: dict = {"path": path, "language": language}
        reasons: list[str] = []
        requested_statuses: list[str] = []
        for feature in SUPPORTED_FEATURES:
            if feature not in plan:
                record[f"{feature}_status"] = "not_requested"
                continue
            if language is None:
                status, reason = "skipped", "unsupported_language"
            else:
                status, reason = categories[feature].get(
                    path, ("skipped", _unsupported_reason(entry, feature)))
            record[f"{feature}_status"] = status
            if reason is not None:
                reasons.append(f"{feature}:{reason}")
            if feature in requested:
                requested_statuses.append(status)
        record["reasons"] = reasons
        if any(status == "skipped" for status in requested_statuses):
            bucket = "skipped"
        elif all(status == "materialized" for status in requested_statuses):
            bucket = "analyzed"
        elif all(status == "reused" for status in requested_statuses):
            bucket = "reused"
        else:
            bucket = "analyzed"
        record["bucket"] = bucket
        counts[bucket] += 1
        per_file.append(record)
    features_out = {}
    for feature in plan:
        if feature == "defect":
            # query-time capability: there is no per-file materialization to
            # report; the candidates come from the defect query entry.
            features_out["defect"] = {
                "query_time": True,
                "materialized": [], "reused": [], "skipped": {}, "failures": [],
            }
            continue
        mapping = categories[feature]
        materialized, reused, failures = [], [], []
        skipped_grouped: dict[str, list[str]] = {}
        for entry in inventory:
            path = entry["path"]
            if entry["language"] is None:
                status, reason = "skipped", "unsupported_language"
            else:
                status, reason = mapping.get(
                    path, ("skipped", _unsupported_reason(entry, feature)))
            if status == "materialized":
                materialized.append(path)
            elif status == "reused":
                reused.append(path)
            elif reason == "payload_too_large":
                failures.append(path)
            else:
                skipped_grouped.setdefault(reason or "unknown", []).append(path)
        features_out[feature] = {
            "materialized": sorted(materialized),
            "reused": sorted(reused),
            "skipped": {reason: sorted(paths) for reason, paths in skipped_grouped.items()},
            "failures": sorted(failures),
        }
    dependencies = {}
    for feature in plan:
        if feature in requested:
            continue
        dependents = [
            requested_feature for requested_feature in requested
            if feature in FEATURE_DEPENDENCIES.get(requested_feature, ())
        ]
        mapping = categories[feature]
        action_counts = {
            action: sum(1 for status, _ in mapping.values() if status == action)
            for action in ("materialized", "reused")
        }
        if action_counts["materialized"]:
            action = "materialized"
        elif action_counts["reused"]:
            action = "reused"
        else:
            action = "failed"
        dependencies[feature] = {
            "reason": f"required_by_{'+'.join(dependents)}",
            "action": action,
            "files": {
                "materialized": action_counts["materialized"],
                "reused": action_counts["reused"],
                "skipped": sum(1 for status, _ in mapping.values() if status == "skipped"),
            },
        }
    # defect is query-time: its run status comes from the materializing
    # features (itself excluded, its deps standing in when it is alone)
    materializing = [f for f in requested if f != "defect"] or \
        list(FEATURE_DEPENDENCIES.get("defect", ()))
    eligible = [
        entry for entry in inventory
        if any(_supports_feature(entry, feature) for feature in materializing)
    ]
    if not eligible:
        status = "failed"
    else:
        produced_any = False
        all_good = True
        for entry in eligible:
            for feature in materializing:
                if not _supports_feature(entry, feature):
                    continue
                status, reason = categories[feature].get(
                    entry["path"],
                    ("skipped", _unsupported_reason(entry, feature)),
                )
                if status in {"materialized", "reused"}:
                    produced_any = True
                elif status == "skipped" and reason == "no_functions_built":
                    # Nothing CFG-able in this file (e.g. prototype-only
                    # header): an honest N/A, not a run failure.
                    continue
                else:
                    all_good = False
        status = "complete" if all_good else ("partial" if produced_any else "failed")
    return {
        "status": status,
        "repo_id": next(iter(results.values()))["repo_id"],
        "database": str(database),
        "scope": scope_path.as_posix(),
        "requested_features": requested,
        "executed_features": plan,
        "files": {"seen": len(inventory), **counts},
        "features": features_out,
        "dependencies": dependencies,
        "per_file": per_file,
        **({"defect_query_hint": "defect is query-time; run the `defect` command "
            "or defect_query.query_defect_candidates for candidates"}
           if "defect" in plan else {}),
    }

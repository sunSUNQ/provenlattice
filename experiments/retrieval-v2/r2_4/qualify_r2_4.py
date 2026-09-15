"""Offline R2.4 bundle qualification; never invokes an Agent or evaluator."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from provenlattice.evidence import Evidence, EvidenceBundle, QueryBudget
from provenlattice.query import GraphQuery


ROOT = Path(__file__).resolve().parents[3]
R23_RESULTS = ROOT / "experiments/retrieval-v2/r2_3/results"
GROUND_TRUTH = ROOT / "experiments/retrieval-v2/evaluator-v2/ground-truth-v2/ground-truth-v2.json"
DATABASE = ROOT.parent / "benchmark-analysis/v1.0-db/brpc-knowledge.db"
OUTPUT = Path(__file__).parent / "results"
CACHE = OUTPUT / "trace-cache.json"

# Frozen before qualification.  These terms are task metadata, never inferred from a candidate.
TASKS = {
    "T01": {"profile": "document_to_code", "focus": (
        "c_murmurhash_bl", "boundedload", "consistenthashingboundedloadbalancer")},
    "T03": {"profile": "code_to_document", "focus": (
        "replicas", "virtual nodes", "addserversinbatch")},
    "T05": {"profile": "module_understanding", "focus": (
        "ratelimitedbackuppolicyoptions", "backup request", "backup")},
}
BUDGETS = {
    "Loose": {"max_primary": 8, "max_supporting": 12, "max_total": 24},
    "Balanced": {"max_primary": 5, "max_supporting": 8, "max_total": 16},
    "Aggressive": {"max_primary": 3, "max_supporting": 5, "max_total": 10},
}
ZERO_HIT = "__r2_4_zero_hit__"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ids_for_task(task_id: str) -> list[str]:
    """Fixed R2.3 candidate pool: union of actual CodeGraph/Knowledge returns."""
    found: set[str] = set()
    for path in sorted(R23_RESULTS.glob(f"{task_id}/[ck]*/r*/evaluation-v2.json")):
        found.update(str(item)[:7].upper() + str(item)[7:].lower()
                     for item in load_json(path).get("returned_evidence_ids", []))
    return sorted(found)


def trace_pool(query: GraphQuery, ids: list[str], cache: dict[str, dict]) -> list[Evidence]:
    evidence: list[Evidence] = []
    for item_id in ids:
        if item_id in cache:
            evidence.append(Evidence(**cache[item_id]))
            continue
        traced = query.trace_evidence(item_id)["bundle"]["primary_evidence"]
        if len(traced) != 1:
            raise ValueError(f"frozen database cannot trace {item_id}")
        cache[item_id] = traced[0]
        OUTPUT.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        evidence.append(Evidence(**cache[item_id]))
    return evidence


def role_ids(bundle: EvidenceBundle, role: str) -> list[str]:
    return [item.evidence_id for item in (*bundle.primary_evidence, *bundle.supporting_evidence)
            if item.metadata.get("bundle_role") == role]


def metrics(bundle: EvidenceBundle, task: dict, baseline_count: int,
            focus_terms: tuple[str, ...]) -> dict:
    returned = {item.upper() for item in bundle.evidence_ids}
    required = {item.upper() for item in task.get("required_evidence_ids", [])}
    acceptable = {item.upper() for item in task.get("acceptable_alternative_ids", [])}
    supporting = {item.upper() for item in task.get("supporting_evidence_ids", [])}
    distractors = {item.upper() for item in task.get("invalid_evidence_ids", [])}
    useful = required | acceptable | supporting
    primary = {item.evidence_id.upper() for item in bundle.primary_evidence}
    focus_hits = sum(
        any(term.casefold() in " ".join(filter(None, (
            item.source_id, item.target_id, item.source_path, item.summary))).casefold()
            for term in focus_terms)
        for item in (*bundle.primary_evidence, *bundle.supporting_evidence)) if focus_terms else 0
    return {
        "returned_evidence_ids": bundle.evidence_ids,
        "primary_ids": role_ids(bundle, "PRIMARY"),
        "supporting_ids": role_ids(bundle, "SUPPORTING"),
        "contextual_ids": role_ids(bundle, "CONTEXTUAL"),
        "suppressed_ids": list(bundle.suppressed_evidence_ids),
        "required_retained": sorted(required & returned),
        "required_suppressed": sorted(required & {item.upper() for item in bundle.suppressed_evidence_ids}),
        "acceptable_retained": sorted(acceptable & returned),
        "supporting_retained": sorted(supporting & returned),
        "distractors_retained": sorted(distractors & returned),
        "distractors_suppressed": sorted(distractors & {item.upper() for item in bundle.suppressed_evidence_ids}),
        "focus_hit_count": focus_hits,
        "fallback_triggered": bundle.fallback_triggered,
        "required_retention_rate": len(required & returned) / len(required) if required else 1.0,
        "acceptable_alternative_retention": len(acceptable & returned) / len(acceptable) if acceptable else 1.0,
        "supporting_evidence_retention": len(supporting & returned) / len(supporting) if supporting else 1.0,
        "distractor_suppression_rate": len(distractors & {item.upper() for item in bundle.suppressed_evidence_ids}) / len(distractors) if distractors else 1.0,
        "bundle_precision": len(useful & returned) / len(returned) if returned else 0.0,
        "primary_evidence_precision": len(useful & primary) / len(primary) if primary else 0.0,
        "bundle_size_reduction": 1 - (len(returned) / baseline_count) if baseline_count else 0.0,
        "useful_evidence_density": len(useful & returned) / len(returned) if returned else 0.0,
    }


def make_bundle(pool: list[Evidence], task_id: str, budget: dict, focus: tuple[str, ...]) -> EvidenceBundle:
    return EvidenceBundle.create(
        anchor=task_id, intent="r2_4_offline_qualification", summary="fixed R2.3 candidate pool",
        primary_evidence=pool, supporting_evidence=[], related_entities=[], uncertainties=[], generation=1,
        budget=QueryBudget(max_evidence=len(pool), max_symbols=0, max_edges=0, max_sections=0, **budget),
        profile=TASKS[task_id]["profile"], focus_terms=focus,
    )


def report_markdown(result: dict) -> str:
    lines = ["# R2.4 Offline Bundle Qualification", "",
             "No Agent was run. Candidate pools are frozen R2.3 CodeGraph/Knowledge returns; "
             "GroundTruthV2 is used only for scoring.", ""]
    for task_id, task in result["tasks"].items():
        lines += [f"## {task_id} — {task['profile']}", "",
                  "| Policy | Size | Required retention | Distractor suppression | Precision | Qualified |",
                  "|---|---:|---:|---:|---:|---|"]
        baseline = task["baseline"]
        lines.append("| R2.3 Generic | %d | %.3f | %.3f | %.3f | baseline |" % (
            len(baseline["returned_evidence_ids"]), baseline["required_retention_rate"],
            baseline["distractor_suppression_rate"], baseline["bundle_precision"]))
        for name, row in task["policies"].items():
            lines.append("| %s | %d | %.3f | %.3f | %.3f | %s |" % (
                name, len(row["returned_evidence_ids"]), row["required_retention_rate"],
                row["distractor_suppression_rate"], row["bundle_precision"],
                "YES" if row["qualified"] else "NO"))
        lines.append("")
    lines += ["## Recommendation", "", result["recommended_policy"], "",
              "## Qualification status", "", result["qualification_status"], "",
              "## Measurement open item", "", "Path Precision Semantics remains unchanged and is not evaluated here.", ""]
    return "\n".join(lines)


def main() -> None:
    gt = {item["task_id"]: item for item in load_json(GROUND_TRUTH)["tasks"]}
    if not DATABASE.exists():
        raise FileNotFoundError(f"frozen R2.3 database is missing: {DATABASE}")
    result = {"protocol": "r2.4-offline", "agent_runs": 0, "database": str(DATABASE),
              "database_sha256": hashlib.sha256(DATABASE.read_bytes()).hexdigest(),
              "ground_truth_sha256": hashlib.sha256(GROUND_TRUTH.read_bytes()).hexdigest(),
              "budgets": BUDGETS, "tasks": {}}
    cache = load_json(CACHE) if CACHE.exists() else {}
    with GraphQuery(DATABASE) as query:
        for task_id, config in TASKS.items():
            pool = trace_pool(query, ids_for_task(task_id), cache)
            baseline = EvidenceBundle.create(
                anchor=task_id, intent="r2_3_generic_baseline", summary="fixed R2.3 candidate pool",
                primary_evidence=pool, supporting_evidence=[], related_entities=[], uncertainties=[], generation=1,
                budget=QueryBudget(max_evidence=len(pool), max_symbols=0, max_edges=0, max_sections=0),
            )
            task_result = {"profile": config["profile"], "focus_terms": list(config["focus"]),
                           "baseline": metrics(baseline, gt[task_id], len(pool), ()), "policies": {}}
            for name, budget in BUDGETS.items():
                row = metrics(make_bundle(pool, task_id, budget, config["focus"]), gt[task_id], len(pool), config["focus"])
                row["qualified"] = row["required_retention_rate"] == 1.0
                task_result["policies"][name] = row
            focus_tests = {}
            for name, terms in {"exact_hit": config["focus"], "partial_hit": (config["focus"][0][:6],),
                                "zero_hit": (ZERO_HIT,)}.items():
                row = metrics(make_bundle(pool, task_id, BUDGETS["Balanced"], terms), gt[task_id], len(pool), terms)
                focus_tests[name] = {"fallback_triggered": row["fallback_triggered"],
                                     "required_retention_rate": row["required_retention_rate"],
                                     "fallback_bundle_precision": row["bundle_precision"]}
            task_result["focus_qualification"] = focus_tests
            result["tasks"][task_id] = task_result
    t01 = result["tasks"]["T01"]["policies"]
    t03 = result["tasks"]["T03"]["policies"]
    dual = "E-CODE-9CEC5B84FB52B556C0C332C9"
    dual_lower = "E-CODE-9cec5b84fb52b556c0c332c9"
    result["dual_role_audit"] = {
        "evidence_id": dual,
        "T01": {name: {"retained": dual_lower in row["returned_evidence_ids"],
                        "suppressed": dual_lower in row["suppressed_ids"],
                        "contextual": dual_lower in row["contextual_ids"]} for name, row in t01.items()},
        "T03": {name: {"retained": dual_lower in row["returned_evidence_ids"],
                        "role": ("PRIMARY" if dual_lower in row["primary_ids"] else "SUPPORTING" if dual_lower in row["supporting_ids"] else "CONTEXTUAL" if dual_lower in row["contextual_ids"] else "SUPPRESSED")}
                for name, row in t03.items()},
    }
    qualified = [(name, sum(row["bundle_precision"] for task in result["tasks"].values()
                            for name2, row in task["policies"].items() if name2 == name))
                 for name in BUDGETS
                 if all(task["policies"][name]["qualified"] for task in result["tasks"].values())]
    result["recommended_policy"] = (max(qualified, key=lambda item: item[1])[0]
                                    if qualified else "NO_QUALIFIED_POLICY")
    result["qualification_status"] = (
        "QUALIFIED: Loose is the only policy retaining every required Evidence ID for T01/T03/T05"
        if qualified else "NOT_QUALIFIED: no policy retains every required Evidence ID")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "qualification-r2.4.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUTPUT / "qualification-r2.4.md").write_text(report_markdown(result), encoding="utf-8")


if __name__ == "__main__":
    main()

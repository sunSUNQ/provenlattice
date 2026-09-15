"""Generate a blinded per-batch worksheet from a frozen annotation view."""

import argparse
import json
from pathlib import Path

FULL_VERDICTS = [
    "ONE_VALID_TARGET",
    "NO_VALID_TARGET",
    "MULTIPLE_VALID_TARGETS",
    "RELATION_NOT_PRESENT",
    "BUILD_CONTEXT_DEPENDENT",
    "INSUFFICIENT_EVIDENCE",
]

DIFFICULTY_TAGS = [
    "same_name",
    "overload",
    "namespace_collision",
    "macro",
    "conditional_compilation",
    "header_definition",
    "ambiguous_include",
    "cross_module_homonym",
]

BLIND_FIELDS = (
    "case_id",
    "repository",
    "raw_reference_id",
    "relation_type",
    "source",
    "candidate_symbol_ids",
    "build_context",
)


def load_view(path):
    view = json.loads(Path(path).read_text(encoding="utf-8"))
    if view.get("view") != "BLINDED_ANNOTATION":
        raise SystemExit(f"unexpected view kind: {view.get('view')}")
    cases = view["cases"]
    ids = [c["case_id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate case_id in view")
    return view, {c["case_id"]: c for c in cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", required=True, help="blinded annotation view JSON")
    parser.add_argument("--plan", required=True, help="full-annotation-execution-plan JSON")
    parser.add_argument("--batch", required=True, help="batch id, e.g. batch_02")
    parser.add_argument("--annotator", required=True, help="annotator id, e.g. A")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()

    view, by_id = load_view(args.view)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    manifest = plan["batch_manifests"][args.batch]

    missing = [cid for cid in manifest if cid not in by_id]
    if missing:
        raise SystemExit(f"cases missing from view: {missing}")

    order = [c["case_id"] for c in view["cases"]]
    start = order.index(manifest[0])
    window = order[start : start + len(manifest)]
    if window != manifest:
        raise SystemExit(
            f"batch manifest is not a contiguous window of the view order "
            f"(first case at view position {start + 1})"
        )
    print(
        f"batch={args.batch} n={len(manifest)} "
        f"contiguous_in_view=True view_positions={start + 1}-{start + len(manifest)}"
    )

    records = []
    for cid in manifest:
        case = by_id[cid]
        blind = {k: case[k] for k in BLIND_FIELDS}
        records.append(
            {
                "batch_id": args.batch,
                "annotator_id": args.annotator,
                **blind,
                "annotation": {
                    "status": "PENDING",
                    "gold_relation_exists": None,
                    "formal_verdict": "PENDING",
                    "valid_target_count": None,
                    "selected_target_if_unique": {
                        "symbol_id": None,
                        "path": None,
                        "start_line": None,
                    },
                    "build_context_status": "PENDING",
                    "navigation_files": [],
                    "evidence_locations": [],
                    "difficulty_tags": [],
                    "confidence": None,
                    "protocol_issue": None,
                    "notes": None,
                },
            }
        )

    out = {
        "artifact": f"{args.batch}-worksheet-{args.annotator.lower()}",
        "schema_version": 1,
        "view": "BLINDED_ANNOTATION",
        "annotator": args.annotator,
        "annotation_view_sha256": plan.get("annotation_view_sha256"),
        "batch_manifest": f"full-annotation-execution-plan-v1.json#{args.batch}",
        "contiguous_in_view": True,
        "cases": records,
    }
    Path(args.out_json).write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    lines = [
        f"# Annotator {args.annotator} — {args.batch} Worksheet",
        "",
        "## Execution boundary",
        "",
        "```text",
        f"annotator_id: {args.annotator}",
        f"batch: {args.batch} ({len(manifest)} cases, A-view order)",
        "source: blinded annotation view only (no system status, strategy, confidence,",
        "        selected target, stratum, other annotator records, or audit results)",
        "evidence: Evidence Scope V1 - read-only navigation inside the frozen repository",
        "          commits + frozen Build Context fields; no network source retrieval",
        "formal_verdict vocabulary (blind world-fact space; stratum join post-hoc):",
        "  " + " | ".join(FULL_VERDICTS),
        "difficulty_tags vocabulary (frozen):",
        "  " + " | ".join(DIFFICULTY_TAGS),
        "decl/def twins (Decl/Def Equivalence V1, FROZEN): record the target your source",
        "  evidence establishes; equivalence groups are joined at scoring time",
        "navigation: list every file read beyond the sample's own file (navigation_files)",
        "  and path:line anchors for the deciding evidence (evidence_locations)",
        "INSUFFICIENT_EVIDENCE only when undeterminable under the full Evidence Scope V1;",
        "EVIDENCE_SCOPE_TOO_NARROW is never a verdict",
        "```",
        "",
    ]

    for i, rec in enumerate(records, 1):
        src = rec["source"]
        module = (
            f"   target_module: `{src['target_module']}`" if src.get("target_module") else ""
        )
        lines.extend(
            [
                f"## {i}. {rec['case_id']}",
                "",
                f"- repository: {rec['repository']}   relation: {rec['relation_type']}",
                f"- source: `{src['path']}:{src['start_line']}-{src['end_line']}`",
                f"- owner: {src['owner_kind']} `{src['owner_qualified_name']}`",
                f"- raw_name: `{src['raw_name']}`{module}",
                f"- candidates: {len(rec['candidate_symbol_ids'])}",
            ]
        )
        for sym in rec["candidate_symbol_ids"]:
            lines.append(f"  - `{sym}`")
        lines.extend(
            [
                "",
                "| field | record |",
                "| --- | --- |",
                "| gold_relation_exists | |",
                "| formal_verdict | |",
                "| valid_target_count | |",
                "| selected target (path:start, symbol_id) | |",
                "| build_context_status | |",
                "| navigation_files | |",
                "| evidence_locations | |",
                "| difficulty_tags | |",
                "| confidence | |",
                "| protocol_issue | |",
                "| notes | |",
                "",
            ]
        )

    Path(args.out_md).write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()

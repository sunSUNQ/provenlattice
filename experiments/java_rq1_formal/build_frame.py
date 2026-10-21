"""Issue Pilot #4: deterministic sampling-frame builder for Java RQ1 formal.

PLAN_VERSION: v1.1-amendment-r2 (Owner decision PL-JAVA-OWNER-DECISION-R2).

APPROVE_DESIGN_ONLY scope (PL-JAVA-ISSUE-DECISION-20261020 + R2 amendment):
- `stats` mode measures per-stratum population counts + association-key
  collision audit (measurement, not annotation).
- `sample` mode emits the frozen 174-case candidate package (canonical,
  sealed) plus a blinded annotation view. It is GATED: it refuses to run
  until the Owner supplies a frame-freeze ack bound to a real authorization
  record, the plan version and the plan file hash (see gate_ack below).
  Running it early is a protocol violation.

R2 amendment changes (vs v1.0):
1. Probability sampling: per-stratum simple random sample without replacement
   under a pre-frozen public seed (plan-frozen-v1.md SAMPLE_SEED); replaces
   the v1.0 first-n selection. Deterministic given (seed, frame id, order).
2. Association-key audit: JDT site keys are (file, line, root); when more
   than one JDT binding shares a key, per-row system-state association is
   ambiguous. Affected L1 rows are flagged `association_ambiguous` and
   EXCLUDED from the sampling frame (reported, never silently backfilled).
3. Blinding isolation: the blinded view contains ONLY
   {case_id, repo, file, line}. System decision fields (status,
   resolution_strategy, confidence, target, jdt_state, raw_name, stratum)
   exist only in the sealed canonical package.
5. gate-ack binding: ack must equal
   sha256(f"{decision_ref}|{PLAN_VERSION}|{plan_sha256}")[:16] where
   decision_ref is the Owner's frame-freeze approval permalink and
   plan_sha256 is the committed plan file hash. A non-empty string is not
   accepted; the formula inputs are printed on refusal, the expected ack
   value never is.
6. Windows-only waiver semantics are defined in plan-frozen-v1.md §6: it
   lowers platform evidence qualification only; it is never a substitute
   for a Linux Formal result.

R3 amendment changes (vs v1.1, owner decision
PL-SOLO-V2-OWNER-DECISION-20261020-R3 §2):
7. Evidence sufficiency: the Stable binary verdict is only reachable when
   the design-weighted estimator is valid (see decision_rule.py gates
   G1-G4); otherwise the outcome is INCONCLUSIVE - an honest disclosure
   tier, never a qualification middle tier.
8. External authorization verification: sample mode verifies via the
   GitHub API that --decision-ref resolves to a REAL Human Owner
   authorization record (author is the owner account, record body
   contains the expected ack token). Any verification failure REFUSES.
   The ack formula check is kept but is no longer the sole basis.

Strata (per repository, relation CALLS):
  S1 L1_RESOLVED_L1_ONLY      L1 resolved; site not bound by JDT merge
  S2 L1_RESOLVED_JDT_AGREE    L1 resolved and JDT agrees
  S3 L1_RESOLVED_JDT_CONFLICT L1 resolved and JDT disagrees (conservative keep)
  S4 NONRESOLVED_RECOVERED    L1 ambiguous/unresolved; JDT bound it
  S5 NONRESOLVED_JDT_AMBIG    L1 ambiguous/unresolved; JDT also ambiguous
  S6 NONRESOLVED_NOT_SEEN     L1 ambiguous/unresolved; JDT did not see site
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from provenlattice.java_semantic import run_jdt_analysis, merge_with_l1

PLAN_VERSION = "v1.2-amendment-r3"
PLAN_FILE = Path(__file__).resolve().parent / "plan-frozen-v1.md"
# Pre-frozen public seed (plan-frozen-v1.md §4). Never generated at runtime.
SAMPLE_SEED = "PL-JAVA-RQ1-FORMAL-V1.1-FIXED-SEED-20261020"
BOOTSTRAP_SEED = "PL-JAVA-RQ1-FORMAL-V1.1-BOOTSTRAP-SEED-20261020"
BOOTSTRAP_B = 10000

OWNER_LOGIN = "sunSUNQ"
DECISION_REF_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9.-]+)/([A-Za-z0-9.-]+)"
    r"/issues/(\d+)(?:#issuecomment-(\d+))?$")

STRATA = ["S1_L1_RESOLVED_L1_ONLY", "S2_L1_RESOLVED_JDT_AGREE",
          "S3_L1_RESOLVED_JDT_CONFLICT", "S4_NONRESOLVED_RECOVERED",
          "S5_NONRESOLVED_JDT_AMBIG", "S6_NONRESOLVED_NOT_SEEN"]

REPO_QUOTA = 58  # 3 x 58 = 174 (owner-frozen total)

BLIND_FIELDS = frozenset({"case_id", "repo", "file", "line"})
SYSTEM_FIELDS = frozenset({"status", "resolution_strategy", "confidence",
                           "target", "jdt_state", "raw_name", "stratum"})


def plan_sha256() -> str:
    return hashlib.sha256(PLAN_FILE.read_bytes()).hexdigest()


def expected_gate_ack(decision_ref: str) -> str:
    canonical = f"{decision_ref}|{PLAN_VERSION}|{plan_sha256()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _gh_api(api_args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(["gh", *api_args], capture_output=True, text=True,
                          timeout=60)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def verify_authorization(decision_ref: str, expected_ack: str,
                         run_gh=_gh_api) -> dict:
    """Verify decision_ref resolves to a REAL Human Owner authorization
    record via the GitHub API (v1.2, R3 revision 2).

    Checks, in order, each failing check REFUSES sample mode:
    - the permalink is a github.com issue or issue-comment URL;
    - the record is fetchable (`gh api`);
    - the record author is the owner account (OWNER_LOGIN);
    - the record body contains the expected ack token.
    The record body itself is never echoed into outputs."""
    match = DECISION_REF_RE.match(decision_ref or "")
    if not match:
        return {"verified": False, "reason": "decision_ref_unparseable"}
    owner, repo_name, issue_number, comment_id = match.groups()
    api_path = (f"repos/{owner}/{repo_name}/issues/comments/{comment_id}"
                if comment_id else
                f"repos/{owner}/{repo_name}/issues/{issue_number}")
    try:
        code, output = run_gh(["api", api_path])
    except (OSError, subprocess.TimeoutExpired):
        return {"verified": False, "reason": "authorization_record_unreachable",
                "api_path": api_path}
    if code != 0:
        return {"verified": False, "reason": "authorization_record_unreachable",
                "api_path": api_path}
    try:
        record = json.loads(output)
    except ValueError:
        return {"verified": False, "reason": "authorization_record_unparseable",
                "api_path": api_path}
    author = (record.get("user") or {}).get("login")
    body = record.get("body") or ""
    if author != OWNER_LOGIN:
        return {"verified": False, "reason": "author_not_owner",
                "author": author, "api_path": api_path}
    if expected_ack not in body:
        return {"verified": False, "reason": "ack_token_absent",
                "author": author, "api_path": api_path}
    return {"verified": True, "author": author, "api_path": api_path}


def case_id(case: dict) -> str:
    canonical = "\x1f".join((case["file"], str(case["line"]),
                             case["raw_name"], case["resolution_strategy"]))
    return "JFQ1-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def make_blind_case(case: dict) -> dict:
    blind = {"case_id": case["case_id"], "repo": case["repo"],
             "file": case["file"], "line": case["line"]}
    assert set(blind) <= BLIND_FIELDS
    return blind


def allocate(populations: dict, repo_quota: int = REPO_QUOTA) -> dict:
    """Proportional-to-population largest-remainder allocation with floor 3
    and cap 24 per stratum (strata with population 0 get 0)."""
    total = sum(len(v) for v in populations.values())
    if total == 0:
        return {s: 0 for s in STRATA}
    eligible = {s: len(v) for s, v in populations.items() if len(v) > 0}
    raw = {s: repo_quota * n / total for s, n in eligible.items()}
    sample_n = {s: max(3, min(24, int(raw[s]))) for s in eligible}
    rest = repo_quota - sum(sample_n.values())
    order = sorted(eligible,
                   key=lambda s: (raw[s] - int(raw[s]), len(populations[s])),
                   reverse=True)
    i = 0
    while rest != 0 and order:
        s = order[i % len(order)]
        if rest > 0 and sample_n[s] < 24:
            sample_n[s] += 1
            rest -= 1
        elif rest < 0 and sample_n[s] > 3:
            sample_n[s] -= 1
            rest += 1
        i += 1
        if i > 1000:
            raise SystemExit("allocation did not converge")
    return {s: sample_n.get(s, 0) for s in STRATA}


def select_cases(populations: dict, allocation: dict, repo: str,
                 frame_id: str) -> dict:
    """Per-stratum simple random sample without replacement under the
    pre-frozen public seed. Deterministic given (seed, frame id, ordered
    population); NOT first-n truncation."""
    selected: dict[str, list[dict]] = {}
    for stratum in STRATA:
        n = allocation.get(stratum, 0)
        pool = populations[stratum]
        if n <= 0 or not pool:
            selected[stratum] = []
            continue
        rng = random.Random(f"{SAMPLE_SEED}|{PLAN_VERSION}|{repo}|{stratum}|{frame_id}")
        picked = sorted(rng.sample(range(len(pool)), min(n, len(pool))))
        selected[stratum] = [pool[i] for i in picked]
    return selected


def classify(repo: Path, database: Path, manifest: str | None) -> dict:
    result = run_jdt_analysis(repo, classpath_manifest=manifest)
    if result.status != "available":
        raise SystemExit(f"JDT unavailable: {result.reason}")
    merged = merge_with_l1(result, database)

    site_state: dict[tuple[str, int, str], str] = {}
    for site in merged["sites"]:
        site_state[(site["file"], site["line"],
                    (site["expr"] or "").lower())] = site["state"]

    # R2 audit: count pre-grouping JDT bindings per (file, line, root);
    # keys with >1 binding make per-row system-state association ambiguous.
    binding_keys: dict[tuple[str, int, str], int] = {}
    for b in result.bindings:
        key = (b.file, b.line, (b.expr or "").split(".")[-1].lower())
        binding_keys[key] = binding_keys.get(key, 0) + 1

    populations = {s: [] for s in STRATA}
    excluded_ambiguous = {s: [] for s in STRATA}
    with closing(sqlite3.connect(str(database))) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            "SELECT f.path AS file, r.start_line AS line, r.raw_name, "
            "r.status, r.resolution_strategy, r.confidence, "
            "n.qualified_name AS target, r.reference_type "
            "FROM raw_references r LEFT JOIN nodes n ON r.resolved_symbol_id=n.id "
            "JOIN files f ON r.file_id=f.file_id WHERE r.reference_type='CALLS'"
        ):
            root = row["raw_name"].split(".")[-1].lower()
            jdt_state = site_state.get((row["file"], row["line"], root))
            resolved = row["status"] == "resolved"
            if resolved:
                if jdt_state == "l1_and_jdt_agree":
                    stratum = "S2_L1_RESOLVED_JDT_AGREE"
                elif jdt_state == "conflict_conservative":
                    stratum = "S3_L1_RESOLVED_JDT_CONFLICT"
                else:
                    stratum = "S1_L1_RESOLVED_L1_ONLY"
            else:
                if jdt_state == "recovered_by_jdt":
                    stratum = "S4_NONRESOLVED_RECOVERED"
                elif jdt_state == "jdt_ambiguous":
                    stratum = "S5_NONRESOLVED_JDT_AMBIG"
                else:
                    stratum = "S6_NONRESOLVED_NOT_SEEN"
            case = {
                "file": row["file"], "line": row["line"],
                "raw_name": row["raw_name"], "status": row["status"],
                "resolution_strategy": row["resolution_strategy"],
                "confidence": row["confidence"], "target": row["target"],
                "jdt_state": jdt_state,
            }
            if binding_keys.get((row["file"], row["line"], root), 0) > 1:
                excluded_ambiguous[stratum].append(case)
            else:
                populations[stratum].append(case)

    audit = {
        "jdt_binding_keys_total": len(binding_keys),
        "jdt_binding_keys_collided": sum(1 for v in binding_keys.values() if v > 1),
        "jdt_bindings_total": sum(binding_keys.values()),
        "l1_rows_total": sum(len(v) for v in populations.values())
        + sum(len(v) for v in excluded_ambiguous.values()),
        "l1_rows_excluded_association_ambiguous":
            sum(len(v) for v in excluded_ambiguous.values()),
        "excluded_by_stratum": {s: len(excluded_ambiguous[s]) for s in STRATA},
    }
    for stratum in STRATA:
        populations[stratum].sort(key=lambda c: (
            c["file"], c["line"], c["raw_name"], c["resolution_strategy"]))
        excluded_ambiguous[stratum].sort(key=lambda c: (
            c["file"], c["line"], c["raw_name"]))
    return {"populations": populations, "excluded": excluded_ambiguous,
            "audit": audit}


def frame_id_of(populations: dict) -> str:
    canonical = json.dumps(
        {s: [c["file"] + f":{c['line']}:" + c["raw_name"]
             for c in populations[s]] for s in STRATA},
        sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["stats", "sample"],
                        help="sample mode is GATED (see module docstring)")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--jdk", required=True)
    parser.add_argument("--jars", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--blind-out", default=None,
                        help="sample mode: blinded view path (required)")
    parser.add_argument("--decision-ref", default=None,
                        help="sample mode: Owner frame-freeze approval permalink")
    parser.add_argument("--gate-ack", default=None,
                        help="sample mode: 16-hex ack bound to decision_ref + "
                             f"PLAN_VERSION({PLAN_VERSION}) + plan file hash")
    args = parser.parse_args()

    import os
    os.environ["PL_JAVA_JDK"] = str(Path(args.jdk).resolve())
    os.environ["PL_JAVA_JDT_CLASSPATH"] = ";".join(
        str(p) for p in sorted(Path(args.jars).resolve().glob("*.jar")))

    if args.mode == "sample":
        missing = [name for name, value in
                   (("--blind-out", args.blind_out),
                    ("--decision-ref", args.decision_ref),
                    ("--gate-ack", args.gate_ack)) if not value]
        if missing:
            print(f"REFUSED: sample mode requires {', '.join(missing)} and a "
                  "gate ack bound to the Owner authorization record.",
                  file=sys.stderr)
            return 2
        if args.gate_ack != expected_gate_ack(args.decision_ref):
            print("REFUSED: gate-ack mismatch. The ack is "
                  "sha256(f'{decision_ref}|PLAN_VERSION|plan_sha256')[:16] "
                  f"with PLAN_VERSION={PLAN_VERSION} and plan_sha256="
                  f"sha256('{PLAN_FILE.name}') as committed at freeze. "
                  "Obtain the ack from the Owner frame-freeze approval "
                  "record referenced by --decision-ref.", file=sys.stderr)
            return 2
        authorization = verify_authorization(
            args.decision_ref, expected_gate_ack(args.decision_ref))
        if not authorization["verified"]:
            print(f"REFUSED: owner authorization record not verified "
                  f"({authorization['reason']}). sample mode requires "
                  "--decision-ref to resolve, via the GitHub API, to a real "
                  f"Human Owner record authored by {OWNER_LOGIN} whose body "
                  "contains the expected ack token.", file=sys.stderr)
            return 2
        verified_authorization = authorization

    repo_path = Path(args.repo).resolve()
    classified = classify(repo_path, Path(args.db).resolve(), args.manifest)
    populations, audit = classified["populations"], classified["audit"]
    frame_id = frame_id_of(populations)
    allocation = allocate(populations)
    payload = {
        "task": "PL-JAVA-RQ1-FORMAL-V1 frame",
        "plan_version": PLAN_VERSION,
        "mode": args.mode,
        "repo": repo_path.name,
        "evidence_level": "frame-statistics-windows-only",
        "population_N": {s: len(populations[s]) for s in STRATA},
        "association_audit": audit,
        "sample_n_rule": "proportional, floor 3, cap 24, largest remainder",
        "sample_n": allocation,
        "total_sample_n": sum(allocation.values()),
        "frame_sha256": frame_id,
        "sampling": {"method": "stratified SRS without replacement",
                     "seed_frozen_in_plan": True,
                     "seed_id": SAMPLE_SEED[:24] + "..."},
        "gates": {"sample_mode_executed": False,
                  "decision_ref": None, "gate_ack": None},
    }
    if args.mode == "sample":
        selected = select_cases(populations, allocation, repo_path.name, frame_id)
        cases = []
        for stratum in STRATA:
            cases.extend({**c, "repo": repo_path.name, "stratum": stratum,
                          "annotation": {"relation_verdict": None,
                                         "gold_target": None,
                                         "build_context_status": None,
                                         "confounder_tags": []}}
                         for c in selected[stratum])
        for case in cases:
            case["case_id"] = case_id(case)
        payload["cases"] = cases
        payload["gates"] = {"sample_mode_executed": True,
                            "decision_ref": args.decision_ref,
                            "gate_ack": args.gate_ack,
                            "plan_sha256": plan_sha256(),
                            "authorization_verification": {
                                "verified": verified_authorization["verified"],
                                "author": verified_authorization.get("author"),
                                "api_path": verified_authorization.get(
                                    "api_path")}}
        blind_cases = [make_blind_case(c) for c in cases]
        blind_text = json.dumps(blind_cases, indent=2, ensure_ascii=False)
        leaked = [f for f in SYSTEM_FIELDS if f in blind_text]
        if leaked:
            print(f"REFUSED: blinded view leaked system fields: {leaked}",
                  file=sys.stderr)
            return 2
        Path(args.blind_out).resolve().parent.mkdir(parents=True, exist_ok=True)
        Path(args.blind_out).write_text(blind_text + "\n", encoding="utf-8")
        payload["blinded_view"] = {"path": str(Path(args.blind_out).name),
                                   "n": len(blind_cases),
                                   "fields": sorted(BLIND_FIELDS)}
    Path(args.out).resolve().parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "cases"},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

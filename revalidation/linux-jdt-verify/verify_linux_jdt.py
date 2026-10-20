"""Linux JDT optional-analyzer verification runner (Issue Pilot #3).

Implements the 6-step compatibility sequence from
docs/java-beta-stage0-report.md ("index / status-only / full / fail-closed /
fingerprint / 对比") over the bundled minimal fixture:

  S1 index         full_index over the fixture; node/edge/reference counts
                   must match the committed golden.
  S2 status-only   java-semantic --status-only: with JDK+classpath ->
                   available; without classpath and with a missing JDK ->
                   explicit unavailable (fail-closed).
  S3 full          java-semantic --mode full over the fixture: per-call-site
                   JDT bindings + L1 merge audit.
  S4 fail-closed   a corrupt jar on the classpath yields an explicit failed
                   result, never a partial success.
  S5 fingerprint   the P2-C classpath contract fingerprint is byte-stable
                   across repeated builds and path-spelling variants.
  S6 compare       normalized S3 output is byte-identical to the committed
                   cross-platform golden (generated on Windows, Temurin 21).

Raw step outputs are archived under --out; comparisons use normalized
JSON only (absolute paths and environment-dependent fields excluded).
Exits nonzero on any failure.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import sqlite3

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixture"
GOLDENS = ROOT / "goldens"

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"PASS {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {name} {detail}")


def run_cli(args: list[str], env: dict | None = None) -> tuple[int, str]:
    merged = {**os.environ, **(env or {})}
    proc = subprocess.run(
        [sys.executable, "-m", "provenlattice.cli", *args],
        capture_output=True, text=True, timeout=600, env=merged,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def cli_json(args: list[str], env: dict | None = None) -> dict:
    code, text = run_cli([*args, "--json"], env)
    start = text.find("{")
    if code != 0 or start < 0:
        raise RuntimeError(f"cli {args} failed rc={code}: {text[-600:]}")
    return json.loads(text[start:])


def s1_index(out: Path, compare: bool = True) -> dict:
    code, text = run_cli(["index", str(FIXTURE),
                          "--database", str(out / "fixture.db")])
    check("S1 index command", code == 0, text[-300:])
    with sqlite3.connect(out / "fixture.db") as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("nodes", "edges", "raw_references")
        }
    (out / "step1-index.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    if compare:
        golden = json.loads((GOLDENS / "step1-index.json").read_text(encoding="utf-8"))
        check("S1 counts match golden", counts == golden, f"{counts} != {golden}")
    return counts


def _semantic_env(jdk: str, jars_dir: Path) -> dict:
    return {
        "PL_JAVA_JDK": jdk,
        "PL_JAVA_JDT_CLASSPATH": os.pathsep.join(
            str(p) for p in sorted(jars_dir.glob("*.jar"))),
    }


def s2_status_only(out: Path, jdk: str, jars_dir: Path) -> None:
    available = cli_json(["java-semantic", str(FIXTURE), "--status-only"],
                         _semantic_env(jdk, jars_dir))
    (out / "step2-status-available.json").write_text(
        json.dumps(available, indent=1), encoding="utf-8")
    check("S2 status available",
          available.get("status") == "available", str(available)[:300])

    missing = cli_json(["java-semantic", str(FIXTURE), "--status-only"],
                       {"PL_JAVA_JDK": str(out / "no-such-jdk"),
                        "PL_JAVA_JDT_CLASSPATH": ""})
    (out / "step2-status-missing-jdk.json").write_text(
        json.dumps(missing, indent=1), encoding="utf-8")
    check("S2 missing JDK is explicit fail-closed",
          missing.get("status") == "unavailable" and missing.get("reason") == "jdk_not_found",
          str(missing)[:300])


def _normalize_binding(binding: dict) -> dict:
    return {
        "file": binding.get("file", "").replace("\\", "/").split("/fixture/")[-1],
        "line": binding.get("line"),
        "expr": binding.get("expr"),
        "decl": binding.get("decl"),
        "state": binding.get("state"),
        "signature": binding.get("signature"),
    }


SUMMARY_STABLE_KEYS = (
    "kind", "files_total", "files_parsed", "problems_total", "parser_inits",
    "calls_resolved", "calls_recovered", "calls_ambiguous",
    "news_resolved", "news_recovered", "news_ambiguous",
    "types_resolved", "types_recovered", "types_ambiguous",
    "heap_max_mb",
)


def _normalize_full(payload: dict) -> dict:
    summary = payload.get("summary") or {}
    return {
        "status": payload.get("status"),
        "summary": {key: summary[key] for key in SUMMARY_STABLE_KEYS
                    if key in summary},
        "bindings": sorted(
            (_normalize_binding(b) for b in payload.get("bindings", [])),
            key=lambda b: (b["file"], b["line"], b["expr"], b["decl"] or "")),
        "merge_audit": payload.get("merge_audit"),
    }


def s3_full(out: Path, jdk: str, jars_dir: Path) -> dict:
    payload = cli_json(["java-semantic", str(FIXTURE), "--mode", "full",
                        "--database", str(out / "fixture.db")],
                       _semantic_env(jdk, jars_dir))
    (out / "step3-full-raw.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")
    normalized = _normalize_full(payload)
    (out / "step3-full-normalized.json").write_text(
        json.dumps(normalized, indent=1, sort_keys=True), encoding="utf-8")
    check("S3 full run available", payload.get("status") == "available",
          str(payload)[:300])
    check("S3 fixture calls resolved",
          sum(1 for b in normalized["bindings"] if b["state"] == "resolved") >= 2,
          str(normalized["bindings"])[:300])
    return normalized


def s4_fail_closed(out: Path, jdk: str, jars_dir: Path) -> None:
    bad = out / "corrupt.jar"
    bad.write_bytes(b"this is not a jar")
    env = _semantic_env(jdk, jars_dir)
    env["PL_JAVA_JDT_CLASSPATH"] = os.pathsep.join(
        [str(bad), *sorted(str(p) for p in jars_dir.glob("*.jar"))])
    result = cli_json(["java-semantic", str(FIXTURE), "--mode", "full"], env)
    (out / "step4-fail-closed.json").write_text(
        json.dumps(result, indent=1), encoding="utf-8")
    check("S4 corrupt classpath fails closed",
          result.get("status") == "failed" and result.get("reason"),
          str(result)[:300])


def s5_fingerprint(out: Path, jars_dir: Path) -> None:
    from provenlattice.classpath import build_classpath

    jars = sorted(str(p) for p in jars_dir.glob("*.jar"))
    first = build_classpath(dependencies=jars).fingerprint
    second = build_classpath(dependencies=jars).fingerprint
    spelled = build_classpath(
        dependencies=[str(Path(j)) for j in jars]).fingerprint
    (out / "step5-fingerprint.json").write_text(json.dumps({
        "first": first, "second": second, "respelled": spelled,
        "jar_count": len(jars),
    }, indent=1), encoding="utf-8")
    check("S5 fingerprint byte-stable",
          first is not None and first == second == spelled, str(first))


def s6_compare(out: Path, normalized: dict, compare: bool = True) -> None:
    if not compare:
        return
    golden_text = (GOLDENS / "step3-full-normalized.json").read_text(encoding="utf-8")
    actual_text = json.dumps(normalized, indent=1, sort_keys=True) + "\n"
    (out / "step6-compare.txt").write_text(
        "match" if actual_text == golden_text else "MISMATCH", encoding="utf-8")
    check("S6 cross-platform golden match", actual_text == golden_text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jdk", required=True, help="JDK 21 home (Temurin 21)")
    parser.add_argument("--jars-dir", required=True,
                        help="directory with the signature-stripped JDT suite")
    parser.add_argument("--out", required=True, help="raw output directory")
    parser.add_argument("--emit-golden", action="store_true",
                        help="write goldens instead of comparing (baseline host)")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jars_dir = Path(args.jars_dir)
    compare = not args.emit_golden

    s1_index(out, compare=compare)
    s2_status_only(out, args.jdk, jars_dir)
    normalized = s3_full(out, args.jdk, jars_dir)
    s4_fail_closed(out, args.jdk, jars_dir)
    s5_fingerprint(out, jars_dir)
    s6_compare(out, normalized, compare=compare)

    if args.emit_golden:
        goldens = GOLDENS
        goldens.mkdir(exist_ok=True)
        counts = json.loads((out / "step1-index.json").read_text(encoding="utf-8"))
        (goldens / "step1-index.json").write_text(
            json.dumps(counts, indent=1) + "\n", encoding="utf-8")
        (goldens / "step3-full-normalized.json").write_text(
            json.dumps(normalized, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"goldens written to {goldens}")

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  failed: {name}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

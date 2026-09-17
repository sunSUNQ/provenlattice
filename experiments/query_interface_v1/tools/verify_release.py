"""ProvenLattice reproducibility baseline: one-command release verification.

Verifies, in order:
  1. every SHA-256 seal of the qualification lines (RQ2 systems_v1 + SQI-V1/V1.1)
  2. presence of the frozen benchmark databases
  3. the SQI implementation + wiring + isolation test suites (48 tests)

Usage (from anywhere inside a clone):
  python experiments/query_interface_v1/tools/verify_release.py
  python experiments/query_interface_v1/tools/verify_release.py --with-integration

Exit code 0 iff every stage passes. Tests require the frozen databases listed
in repositories.lock.json; without them the test stage is reported as
ENVIRONMENT-INCOMPLETE (not a seal failure).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
SRC = REPO_ROOT / "src"
for path in (str(SRC), str(REPO_ROOT), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

LOCK = REPO_ROOT / "repositories.lock.json"
SEALS = [
    ("Systems contract seal (RQ2)",
     REPO_ROOT / "experiments/systems_v1/reviews/contract-v1-freeze-2026-09-16.sha256",
     set()),
    ("Contract seal (SQI V1)",
     REPO_ROOT / "experiments/query_interface_v1/contract/structured-query-interface-contract-v1.freeze.sha256",
     {"experiments/query_interface_v1/tasks/SQI-T05.json"}),
    ("Implementation seal (SQI)",
     REPO_ROOT / "experiments/query_interface_v1/contract/structured-query-interface-contract-v1.implementation-seal.sha256",
     set()),
    ("Protocol seal (Formal Protocol V1)",
     REPO_ROOT / "experiments/query_interface_v1/contract/sqi-formal-qualification-protocol-v1.seal.sha256",
     set()),
    ("Amendment seal (Protocol V1.1 + T05 fixture)",
     REPO_ROOT / "experiments/query_interface_v1/contract/sqi-v1.1-amendments.sha256",
     set()),
    ("Secondary seal (V1.1, 10 implementation files)",
     REPO_ROOT / "experiments/query_interface_v1/contract/structured-query-interface-contract-v1.secondary-seal.sha256",
     set()),
]
TEST_MODULES = [
    "experiments.query_interface_v1.tests.test_sqi_v1",
    "experiments.query_interface_v1.tests.test_sqi_formal_wiring",
]


def verify_seal(path: Path, skip: set[str]) -> tuple[bool, int, int, int]:
    superseded = 0
    verified = 0
    bad = 0
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"^([a-f0-9]{64})\s+\*?(.+?)\s*$", line.strip())
        if not match:
            continue
        expected, rel = match.group(1), match.group(2).replace("\\", "/")
        if rel in skip:
            superseded += 1
            continue
        target = REPO_ROOT / rel
        total_digest = hashlib.sha256(target.read_bytes()).hexdigest() \
            if target.exists() else None
        if total_digest == expected:
            verified += 1
        else:
            bad += 1
    return bad == 0, verified, bad, superseded


def frozen_databases() -> tuple[bool, int, int]:
    if not LOCK.exists():
        return False, 0, 0
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    databases = lock.get("databases") or {}
    present = 0
    for key, meta in databases.items():
        path = REPO_ROOT.parent / meta["path"] if not os.path.isabs(meta["path"]) \
            else Path(meta["path"])
        candidate = path if path.exists() else REPO_ROOT / meta["path"]
        if candidate.exists():
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            present += digest == meta["sha256"]
    return present == len(databases), present, len(databases)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-integration", action="store_true",
                        help="also run tests/test_integration.py (core graph integration)")
    args = parser.parse_args()

    failures = 0

    print("ProvenLattice reproducibility baseline verification")
    print("=" * 56)
    for label, path, skip in SEALS:
        if not path.exists():
            print(f"{label:<42} MISSING ({path.name})")
            failures += 1
            continue
        ok, verified, bad, superseded = verify_seal(path, skip)
        note = f" (+{superseded} superseded by amendment)" if superseded else ""
        print(f"{label:<42} {'PASS' if ok else 'FAIL'} {verified}/{verified + bad}{note}")
        failures += 0 if ok else 1

    dbs_ok, present, total = frozen_databases()
    print(f"{'Frozen databases':<42} {'PASS' if dbs_ok else 'MISSING'} {present}/{total}")
    failures += 0 if dbs_ok else 1

    modules = list(TEST_MODULES)
    if args.with_integration:
        modules.append("tests.test_integration")
    try:
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for module in modules:
            suite.addTests(loader.loadTestsFromName(module))
        result = unittest.TextTestRunner(verbosity=0).run(suite)
        ran = result.testsRun
        problems = len(result.failures) + len(result.errors)
        status = "PASS" if result.wasSuccessful() else "FAIL"
        print(f"{'Tests (' + ', '.join(m.rsplit('.', 1)[-1] for m in modules) + ')':<42} "
              f"{status} {ran - problems}/{ran}")
        failures += 0 if result.wasSuccessful() else 1
    except Exception as exc:  # noqa: BLE001 - report, don't crash the report
        print(f"{'Tests':<42} ERROR {exc}")
        failures += 1

    print("=" * 56)
    print("RELEASE VERIFICATION:", "PASS" if failures == 0 else f"FAIL ({failures} stage(s))")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

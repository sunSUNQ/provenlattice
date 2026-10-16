# PL-JAVA-OVERNIGHT-LONGRUN-V1 — Execution Plan (frozen at P0)

**Started:** 2026-10-15 · **Baseline HEAD:** 42c6d89 (main) · **Executor:** autonomous longrun

## Frozen order

| Stage | Task | Gate to proceed |
|---|---|---|
| P0 | Preflight, evidence dir, baseline, staged commits | baseline 442 OK recorded |
| P1 | Resolver P1 fix final review | P1_FINAL_REVIEW_PASS or BLOCKED |
| P2 | T9-A Java L1 real-project benchmark (3 repos, cold/warm/incr/delete ×3) | raw data + stats written |
| P3 | T9-B JDT/SCIP/JavaParser empirical comparison (shared fixture + hand gold) | results classified CORRECT/WRONG/AMBIGUOUS/UNRESOLVED/UNSUPPORTED/INFRA_BLOCKED |
| P4 | Phase 2 ADR | decision recorded from evidence |
| P5 | Optional semantic backend prototype (conditional on P1 PASS + P2/P3 evidence) | may output design-only |
| P6 | Java L1 adversarial test hardening | new cases + fixes committed |
| P7 | Real-repo end-to-end verification (2 repos, CLI only) | sampling audit recorded |
| P8 | Final regression & performance validation | full suite + parity + clean install |
| P9 | Report, evidence commits | docs/java-overnight-longrun-v1-report.md |

## Environment facts (P0)

- Windows, Python 3.12.10, git main @ 42c6d89 (baseline, uncommitted Java work in tree)
- **No JDK on machine** (java/mvn absent, no JAVA_HOME, no Adoptium/Zulu dirs)
- **Network available** (github reachable) → P3 will download Temurin JDK 21 zip into
  `%TEMP%\opencode\longrun\tools` (outside repo, never committed)
- Benchmark corpora → `%TEMP%\opencode\longrun\repos` (outside repo, never committed)

## Commit plan (local only, no push)

1. `java: T1-T3 foundation graph support` — deps/CI/wiring/extractor/tests(21)/design doc
2. `java: P1 resolver type-target guard` — resolver.py + P1 tests (22-25) + doc appendices
3. `java: T6 capability registration` — README/capability-matrix/roadmap
4. `java: T9-A benchmark runner + evidence` — bench scripts + raw JSON (repos NOT committed)
5. `java: T9-B backend comparison + ADR` — t9b scripts/results
6. `java: longrun final report` — report + stage status

## Stop conditions honored

- 3 consecutive failures on same cause → BLOCKED, move to independent stage
- Wrong-Resolution=0 hard gate on covered scenarios
- No formal qualification claims without independent evidence

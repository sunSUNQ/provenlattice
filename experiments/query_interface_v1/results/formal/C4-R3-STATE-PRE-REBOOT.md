# C4-R3 EXECUTION STATE — PRESERVED BEFORE REBOOT (2026-09-20)

## Batch completed just before reboot — NO work in flight

- **C4-R3 clean 36-cell batch: COMPLETE**
  - batch_id: `SQI-FORMAL-C4-20260920T072457Z`
  - 36/36 cells completed, single backend `deepseek-flash` (provenance per cell)
  - isolation/restore/fingerprints verified; checkout + transcripts restored (probed)
  - raw cells on disk under `results/formal/SQI-FORMAL-C4-20260920T072457Z/`

## Raw results

- **SQI arm: 17/18** (floor 18/18 — still breached by ONE rep)
  - T01 3/3, T02 3/3, T03 3/3, T04 3/3, T06 3/3 (**T06 fully repaired by V1.2-NR1**)
  - **T05.sqi 2/3** — the ONLY remaining negative region (which rep failed:
    to be attributed in synthesis)
- **Native control: 16/18** (T02 1/3, T04 0/3 — baseline native T04 was 0/3 too)
- T02/T03/T04.sqi all 3/3 — the earlier zeros were the infrastructure +
  call-log-pollution artifacts, now fixed and proven

## Chain of fixes applied this session (all committed & pushed)

1. `0af056f` — disposable copies for ALL task repos (rocksdb was missing →
   T03/T04 sessions never started)
2. `63f294d` / `3945218` — classify_leakage aligned with amendment §3
   (runtime-internal references and hint-patterns are documented, not leaks)
3. `927cab6` — **V1.2-NR1 discipline**: truncation.retry_same_call_will_not_expand,
   session usage_discipline policy, arm-prompt guidance; bridge stdout UTF-8
4. `bbc03ba` — **per-repetition call-log labels** (root cause of cross-cell
   cache/evaluator pollution; invalidated earlier T05/T06 conclusions)
5. `39d7e37` — qualification ladder GREEN (T06 3/3 with exactly one
   bundle.explain each; T05 3/3; smoke recheck 4/4)

## NEXT TASK AFTER REBOOT

**`C4-R3 Clean Synthesis + V1.2 Final Qualification Verdict`**

1. Run `python experiments/query_interface_v1/tools/sqi_c4_synthesis.py`
   — BUT first update it: point CLEAN_BATCH at
   `SQI-FORMAL-C4-20260920T072457Z` (currently still the R2 batch) and drop
   the supplement-batch logic (single clean batch now).
2. Attribute the single T05.sqi failure rep (r1/r2/r3 — machine checks +
   call log; last ladder run T05 was 3/3 so the NR1 discipline mostly
   works; the failure may be residual exploration noise).
3. Expected verdict: HOLD / PARTIAL (17/18 < 18/18) UNLESS the floor is
   re-interpreted — the ONLY failing rep is T05.sqi; positive regions:
   T06 repaired, cost deltas attributable, discipline verified.
4. Then per user decision: V1.2 release closure vs one more targeted
   T05 round.

## Recovery notes (post-reboot)

- No stale deny ACLs expected (batch restored cleanly; verify with the
  probe if in doubt: `icacls D:\ChatGPT\codegraph\provenlattice | findstr deny`)
- Runtime area intact: `D:\pl-c4-runtime` (DB copies cached, disposable
  copies rebuilt per run)
- All work committed & pushed through `39d7e37`; this file + the R3 batch
  artifacts are the only uncommitted items (commit them first thing)

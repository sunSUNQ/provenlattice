# C4-R4 — Native vs ProvenLattice V1.2 Same-Batch Cost & Effectiveness Review

Batch: `SQI-FORMAL-C4-20260920T093328Z` (clean, QUALIFIED)
Analysis evidence: `results/analysis/C4-R4-NATIVE-VS-SQI-V1.2.json`
Script: `analysis/c4_r4_native_vs_sqi_v12.py` (read-only over frozen batch artifacts; no cell re-run, no exclusion, no re-weighting)

---

## 1. Executive Summary

Inside one clean formal batch — same 6 frozen tasks, same backend (deepseek-flash), same runner, same V1.4 isolation window, same evaluation protocol — the ProvenLattice V1.2 (SQI) arm went **18/18 (100%)** while the Native (no CodeGraph/SQI) control arm went **12/18 (66.7%)**. The SQI arm spent **+7.8% total tokens** gross, but because the Native arm burned 6 full cells on two tasks it never solved (T02 0/3, T04 0/3), **cost per successful task was 28.1% lower with ProvenLattice** (259,377 vs 360,977 logged tokens per success). On T04 the Native arm was not even cheaper in absolute terms: it consumed **more** tokens than SQI while failing all 3 reps.

> **Answer (data-driven, no weighting invented):** in this batch ProvenLattice V1.2 was **not** "purely an extra graph-query cost". It is better described as **exchanging a modest gross token overhead (+7.8%) for a +33.3pp task-success rate, with a ~28% lower context cost per successful task**. On 4 of 6 tasks where Native also succeeded, SQI's gross tokens were higher (T03 +39.3%, T05 +29.7%, T06 +70.1%, T02 +10.3%); on T04 SQI was cheaper in absolute terms (−27.9%) while Native failed. The two Native failures are precisely the tasks whose frozen oracles require graph-reachability evidence (complete caller enumeration, impact frontier) that raw-text exploration could not produce in 3 reps.

## 2. Dataset Validity

| Check | Result |
| --- | --- |
| Cells total | 36/36 (6 tasks × 2 arms × 3 reps) |
| Native / SQI | 18 + 18, no cells excluded |
| Backend | `deepseek-flash` ×36 (single value across all cells) |
| Model provenance | `backend_verified: true` ×36 (requested `claude-sonnet-4-5-20250929`, init-reported match, gateway-resolved backend recorded per cell) |
| Execution valid | 36/36 (`status=completed`, `exit_reason=completed`) |
| Isolation | `window_closed_verified` / `restore_verified` / `fingerprint_unchanged` — all true ×36 (V1.4 finite-root profile, baseline sha `27e40df5…`) |
| Leakage | `sensitive_leakage_events=0`, `policy_violations=[]` ×36 (frozen C4 criterion; 39 raw classified non-sensitive events across cells are informational only) |
| Capability flags | none ×36; SQI access in native arm: 0 calls ×18 |
| Evaluator consistency | `run.json.task_success` == `evaluation.json.task_success` for all 36 (zero mismatches); success rates below are the formal evaluator's |
| Prompt consistency | identical `prompt_hash` per task across both arms |

**Comparability statement:** this is currently the most defensible Native vs ProvenLattice horizontal comparison, because both arms come from the same clean formal batch — same frozen task set, protocol, oracle, prompts, isolation environment, runner, and time window, on a single verified backend.

## 3. Success Comparison

Overall (frozen evaluator `task_success`):

| Arm | Success | Total | Success Rate |
| --- | ------: | ----: | -----------: |
| Native | 12 | 18 | 66.7% |
| ProvenLattice V1.2 | 18 | 18 | 100% |

Per task:

| Task | Native | SQI V1.2 | Delta |
| ---- | -----: | -------: | ----: |
| T01 | 3/3 | 3/3 | 0 |
| T02 | 0/3 | 3/3 | +3 |
| T03 | 3/3 | 3/3 | 0 |
| T04 | 0/3 | 3/3 | +3 |
| T05 | 3/3 | 3/3 | 0 |
| T06 | 3/3 | 3/3 | 0 |

`execution_valid` (runner completed without violations) is 36/36 and is reported separately from `task_success`; they are never conflated. All 6 native failures are task_success failures under the frozen oracle, not infrastructure or capability faults (zero capability flags, zero violations).

## 4. Overall Cost Comparison

Per-cell session-cumulative usage (agent adapter final `result` usage block; aggregated with the frozen synthesis `cell_tokens` semantics — every total back-calculates to the 36 cell records embedded in the analysis JSON).

| Metric | Native (n=18) | ProvenLattice V1.2 (n=18) | Δ (SQI vs Native) |
| --- | ---: | ---: | ---: |
| Input tokens — sum | 594,224 | 616,598 | **+3.8%** |
| Input — mean / median per cell | 33,012 / 28,110 | 34,255 / 33,460 | |
| Input — P25 / P75 | 25,318 / 37,965 | 30,059 / 37,362 | |
| Output tokens — sum | 103,713 | 97,249 | **−6.2%** |
| Output — mean / median per cell | 5,762 / 3,383 | 5,403 / 4,756 | |
| Output — P25 / P75 | 2,819 / 6,372 | 3,215 / 7,345 | |
| Cache-read tokens — sum | 3,633,792 | 3,954,944 | **+8.8%** |
| Cache-read — mean / median per cell | 201,877 / 152,256 | 219,719 / 192,512 | |
| Cache-read — P25 / P75 | 100,256 / 228,416 | 132,576 / 303,584 | |
| Cache-creation tokens | 0 | 0 | 0 |
| Total as logged — sum | 4,331,729 | 4,668,791 | **+7.8%** |
| Total — mean / median per cell | 240,652 / 183,832 | 259,377 / 229,241 | |
| Total — P25 / P75 | 128,898 / 277,232 | 169,931 / 352,054 | |
| Median Duration | `METRIC_NOT_CAPTURED` | `METRIC_NOT_CAPTURED` | — |
| Successful Tasks | 12/18 | 18/18 | +6 |

Notes: `cache_creation` is 0 in every cell (backend reports no cache-write usage), so its Δ is 0/undefined rather than meaningful. "Total as logged" is the event-provided `total` field, not a constructed sum. **Median Duration is `METRIC_NOT_CAPTURED`** — see §9 Limitations.

## 5. Cost per Successful Task

Batch-level success-normalized token index (not a monetary cost):

| Metric / Successful Task | Native (÷12) | SQI V1.2 (÷18) | Δ |
| --- | ---: | ---: | ---: |
| Input / success | 49,519 | 34,255 | **−30.8%** |
| Output / success | 8,643 | 5,403 | **−37.5%** |
| Cache-read / success | 302,816 | 219,719 | **−27.4%** |
| Total as logged / success | 360,977 | 259,377 | **−28.1%** |

Per task (zero-success tasks are marked, never divided by zero):

| Task | Native (success) | SQI V1.2 (success) |
| --- | --- | --- |
| T01 | in 24,380 · out 1,280 · cr 82,859 (3 succ) | in 28,717 · out 1,299 · cr 64,469 (3 succ) |
| T02 | **N/A — zero successful tasks** | in 31,530 · out 3,415 · cr 138,069 (3 succ) |
| T03 | in 27,809 · out 4,432 · cr 114,475 (3 succ) | in 29,917 · out 5,647 · cr 168,789 (3 succ) |
| T04 | **N/A — zero successful tasks** | in 40,891 · out 9,478 · cr 363,179 (3 succ) |
| T05 | in 42,733 · out 3,016 · cr 222,379 (3 succ) | in 36,256 · out 6,606 · cr 304,939 (3 succ) |
| T06 | in 27,429 · out 9,160 · cr 153,344 (3 succ) | in 38,222 · out 5,971 · cr 278,869 (3 succ) |

The two `N/A — zero successful tasks` rows (T02, T04 Native) are themselves a headline result: 33% of the Native arm's spend bought no successful task at all.

## 6. Per-Task Breakdown

Cell sums per task (3 reps each). Δ = (SQI − Native) / Native.

| Task | Arm | Success | Input | Output | Cache-read | Total as logged | Tool events | SQI calls |
| ---- | --- | ------: | ----: | -----: | ---------: | ----: | ----: | ----: |
| T01 | Native | 3/3 | 73,141 | 3,841 | 248,576 | 325,558 | 16 | 0 |
| T01 | SQI | 3/3 | 86,150 | 3,898 | 193,408 | 283,456 | 10 | 6 |
| T02 | Native | **0/3** | 80,887 | 9,516 | 380,032 | 470,435 | 35 | 0 |
| T02 | SQI | 3/3 | 94,591 | 10,245 | 414,208 | 519,044 | 30 | 7 |
| T03 | Native | 3/3 | 83,426 | 13,296 | 343,424 | 440,146 | 30 | 0 |
| T03 | SQI | 3/3 | 89,751 | 16,942 | 506,368 | 613,061 | 35 | 13 |
| T04 | Native | **0/3** | 146,284 | 40,532 | 1,534,592 | 1,721,408 | 80 | 0 |
| T04 | SQI | 3/3 | 122,672 | 28,433 | 1,089,536 | 1,240,641 | 40 | 6 |
| T05 | Native | 3/3 | 128,198 | 9,048 | 667,136 | 804,382 | 32 | 0 |
| T05 | SQI | 3/3 | 108,768 | 19,819 | 914,816 | 1,043,403 | 51 | 13 |
| T06 | Native | 3/3 | 82,288 | 27,480 | 460,032 | 569,800 | 40 | 0 |
| T06 | SQI | 3/3 | 114,666 | 17,912 | 836,608 | 969,186 | 33 | 4 |

Per-task total-token Δ: T01 −12.9%, T02 +10.3%, T03 +39.3%, T04 −27.9%, T05 +29.7%, T06 +70.1%.

**T02 (complete caller evidence).** The frozen oracle requires the full caller set of `butil.Status.error_cstr` (7 callers, incl. test-boundary edges). Native 0/3: three reps of pure Read/Grep/Glob exploration (35 tool events, 80,887 input + 380,032 cache-read tokens) never produced the complete enumeration. SQI 3/3 with 7 graph calls (`symbol.lookup`×4, `symbol.callers`×3) at +16.9% input / +9.0% cache-read over the failing native arm. So yes — SQI bought a **modest** token premium for evidence Native could not stabilize at any price in 3 reps.

**T04 (impact frontier).** Native is 0/3 **and** is the most expensive failed task in the batch: 146,284 input / 1,534,592 cache-read / 80 tool events (30 Grep + 25 Read + 23 Bash + 2 Glob) — all three native reps spent **more** than the corresponding SQI arm (SQI −16.1% input, −29.9% output, −29.0% cache-read) while SQI went 3/3 with only 6 calls (`impact.frontier`×3, `symbol.callers`×2, `symbol.lookup`×1).

> Native's token consumption cannot be interpreted as higher efficiency here: the task was not completed. Its spend bought exploration breadth (wide Grep/Bash sweeps) instead of the frozen impact-frontier evidence.

**T05 / T06 (post-NR2 behavior).** Call counts did come down and retrieval cost stayed stable or fell vs the C4-R3 ladder, with no extra exploration inflation re-appearing:

| Task | C4-R3 SQI | C4-R4 SQI | R3→R4 |
| --- | --- | --- | --- |
| T05 | 46 calls (cache-read 1,843,712), success 2/3 | 13 calls — 2/5/6 per cell (cache-read 914,816), success 3/3 | calls −72%, cache-read −50.4%, input −14.5%, output −41.0% |
| T06 | 4 calls (cache-read 978,304), success 3/3 | 4 calls — 1/1/2 per cell (cache-read 836,608), success 3/3 | calls flat, cache-read −14.4%, input/output ~flat; exactly one `bundle.explain` per cell |

Residual observation: SQI T06 still spends more gross tokens than Native (total +70.1%) — Native "succeeds" T06 under the frozen oracle but its path is Read/Grep-heavy; the SQI premium buys the schema'd bundle evidence, and the T06 machine check (`exactly one bundle.explain`) now holds 3/3 after NR1/NR2.

## 7. Tool-Use Structure

Native tool calls and SQI calls are **not** treated as equivalent units: native tools return raw text hits; SQI calls return schema'd evidence envelopes. The goal is to expose exploration-structure differences, not to claim "1 SQI call = 1 Read".

Whole batch:

| Structure | Counts |
| --- | --- |
| Native arm tool events (233 total) | Read 102 · Grep 82 · Bash(shell) 32 · Glob 17 |
| SQI arm SQI calls (49 total) | symbol.lookup 24 · symbol.references 7 · symbol.callers 6 · code.related 6 · impact.frontier 3 · bundle.explain 3 |
| SQI arm native tool events excl. SQI-call events (150) | Read 76 · Bash 41 · Grep 32 · Glob 1 |
| SQI envelope payload | 384,049 bytes (native: 0 — no SQI surface) |

Per task:

| Task | Native Read/Search/Shell | SQI Calls | SQI extra native tools |
| ---- | -----------------------: | --------: | ---------------------: |
| T01 | Read 5 · Grep 4 · Glob 4 · Bash 3 | 6 (symbol.lookup×6) | Read 4 |
| T02 | Read 18 · Grep 12 · Glob 5 | 7 (symbol.lookup×4, symbol.callers×3) | Read 19 · Grep 4 |
| T03 | Grep 13 · Read 10 · Bash 5 · Glob 2 | 13 (symbol.references×7, symbol.lookup×5, symbol.callers×1) | Read 15 · Grep 4 · Bash 3 |
| T04 | Grep 30 · Read 25 · Bash 23 · Glob 2 | 6 (impact.frontier×3, symbol.callers×2, symbol.lookup×1) | Bash 12 · Grep 11 · Read 11 |
| T05 | Read 18 · Grep 12 · Glob 1 · Bash 1 | 13 (symbol.lookup×7, code.related×6) | Read 20 · Grep 10 · Bash 8 |
| T06 | Read 26 · Grep 11 · Glob 3 | 4 (bundle.explain×3, symbol.lookup×1) | Bash 18 · Read 7 · Grep 3 · Glob 1 |

Structural reading: the Native arm's exploration is text-sweep-shaped (Grep/Read/Bash-heavy, worst exactly on the graph-dependent tasks T02/T04 — T04 native alone fires 30 Greps + 23 shell commands). The SQI arm replaces broad sweeps with a small number of typed graph calls (2.72 per cell on average) plus targeted verification reads. Transcribed fact: 4 of the 49 SQI calls are logged as `Read`-shaped events carrying `query_type` (bundle.explain ×3, impact.frontier ×1) — the analysis classifies events by `query_type`, so SQI-call counts always match the frozen call log (49). Note also: 32 Bash events appear in native cells although the declared native allowed-tool string is `Read(./**),Grep(./**),Glob`; the frozen runner recorded no policy violations for these cells (violation criterion = checkout/sensitive leakage), so they are reported here as observed structure, not adjudicated.

## 8. Interpretation (Effectiveness-aware Cost)

Effectiveness-aware cost group (no composite score constructed):

1. Success rate — Native 66.7% vs SQI 100% (+33.3pp).
2. Total tokens — Native 4,331,729 vs SQI 4,668,791 (+7.8% gross).
3. Cost per successful task — Native 360,977 vs SQI 259,377 (−28.1% with SQI).
4. Native failed tasks flagged individually: **T02 0/3** (470,435 total tokens, no successful outcome) and **T04 0/3** (1,721,408 total tokens — the single most expensive failed task in the batch, more expensive than the SQI arm that solved it).
5. Per-task gross view: where both arms succeed (T01/T03/T05/T06), SQI gross tokens run +29.7%…+70.1% higher on T03/T05/T06 and −12.9% lower on T01; where Native fails, SQI is cheaper in absolute terms (T04) or ~10% more expensive (T02) while adding 3 successes.

**Verdict on the posed question, strictly from this batch:** ProvenLattice V1.2 is not merely "an extra graph-query cost" bolted onto the agent. The gross overhead is +7.8% across the batch, but the entire *incremental* spend is concentrated where structured evidence is produced; the two tasks that justify the product (caller enumeration, impact frontier) are exactly the two the Native control cannot complete. Success-normalized, ProvenLattice's context cost per delivered successful task is ~28% lower than Native's. Within the frozen protocol, "higher success at modestly higher gross token cost and lower per-success cost" is the supported description.

## 9. Limitations

- **Duration — `METRIC_NOT_CAPTURED`.** `duration_ms` existed only in the C4 runner's in-memory cell record: `_record_cell` adds it *after* `run.json` is persisted (sqi_c4_runner.py:456 vs :474), and it was never written to any artifact. `events.ndjson` timestamps are end-of-session flush stamps (identical within a cell), so wall-clock duration cannot be recovered from existing raw artifacts. `AVAILABLE_METRICS`: tokens (input/output/cache_read/cache_creation/total), task success, execution validity, backend provenance, isolation verification, SQI call log (type/params/envelope/bytes), native tool events, envelope payload bytes, source-read events/bytes. `MISSING_METRICS`: per-cell wall-clock duration; per-API-turn token breakdown (only session-cumulative final usage is logged); monetary cost (no pricing table defined — by design). `WHY_MISSING`: duration_ms computed post-persist; adapter attaches only the CLI final `result` usage. `WHETHER_EXISTING_RAW_ARTIFACT_CAN_RECOVER`: no. `MINIMUM_NEW_MEASUREMENT_REQUIRED`: persist `duration_ms` inside `run.json` (or a batch-records file) in the runner — a one-line ordering fix for future batches; no formal re-run is proposed or required for this analysis.
- **Single batch, n=18 per arm, 3 reps/task.** Native's 0/3 on T02/T04 is statistically stark but batch-specific; the C4-R4 synthesis itself flags residual model behavioral drift on the native control (12/18 here vs 13/18 in the C4 baseline generation).
- **Token semantics.** Per-cell usage is session-cumulative from the final CLI result event; per-turn attribution is not captured, so "where" tokens were spent inside a cell is not reconstructable.
- **Not monetary.** All "cost" here is context/token volume; no price model is applied.
- **Question separation.** The longitudinal V1.1 → V1.2 comparison (question A: *did ProvenLattice itself get cheaper?*) is a different experiment: frozen deltas input −36%, output −58%, cache-read −73%, envelope −26%, calls −17%, carrying a **historical backend caveat** (baseline `SQI-FORMAL-20260917-1` ran on mixed backends). Those numbers must never be merged with the Native-vs-SQI horizontal result in §3–§8, which is single-backend and same-batch.

## 10. Recommended Report Tables (paste-ready for `docs/report-v1.2.md`)

### Native vs ProvenLattice V1.2 (same batch `SQI-FORMAL-C4-20260920T093328Z`, backend deepseek-flash ×36)

| Metric | Native | ProvenLattice V1.2 | Delta | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Success | 12/18 (66.7%) | 18/18 (100%) | +33.3pp | Native fails exactly the graph-evidence tasks (T02, T04) |
| Input tokens | 594,224 | 616,598 | +3.8% | Near-parity gross input |
| Output tokens | 103,713 | 97,249 | −6.2% | SQI answers are more compact |
| Cache-read tokens | 3,633,792 | 3,954,944 | +8.8% | Modest extra context reread |
| Median Duration | METRIC_NOT_CAPTURED | METRIC_NOT_CAPTURED | — | duration_ms not persisted in this batch generation |
| Total tokens (as logged) | 4,331,729 | 4,668,791 | +7.8% | Gross premium of structured querying |
| Cost / Successful Task (total tokens) | 360,977 | 259,377 | **−28.1%** | Effectiveness-adjusted: SQI delivers each success cheaper |
| Input / success | 49,519 | 34,255 | −30.8% | |
| Output / success | 8,643 | 5,403 | −37.5% | |
| Cache-read / success | 302,816 | 219,719 | −27.4% | |
| Failed-task spend | T02 470,435 · T04 1,721,408 | — | — | Native spend that produced zero successful tasks |

### Per-Task Success

| Task | Native | ProvenLattice V1.2 | Delta |
| ---- | -----: | -------: | ----: |
| T01 (locate declaration + read source) | 3/3 | 3/3 | 0 |
| T02 (complete caller evidence) | **0/3** | 3/3 | +3 |
| T03 (symbol references) | 3/3 | 3/3 | 0 |
| T04 (impact frontier) | **0/3** | 3/3 | +3 |
| T05 (knowledge-to-code pair) | 3/3 | 3/3 | 0 |
| T06 (bundle.explain discipline) | 3/3 | 3/3 | 0 |
| **Total** | **12/18** | **18/18** | **+6** |

---

*Generated by `analysis/c4_r4_native_vs_sqi_v12.py`; machine-readable evidence in `results/analysis/C4-R4-NATIVE-VS-SQI-V1.2.json` (36 cell records embedded for back-calculation).*

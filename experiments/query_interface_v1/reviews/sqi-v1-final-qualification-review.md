# SQI-V1 Formal Qualification Review — Native vs SQI — QUALIFIED

Review date: 2026-09-17
Batch: `SQI-FORMAL-20260917-1` · Protocol: `SQI_FORMAL_QUALIFICATION_PROTOCOL_V1` (FROZEN) ·
Oracle: `SQI_FORMAL_ORACLE_V1.1` (uniform review pass, see §5) ·
Model/config: `claude-sonnet-4-5-20250929` / claude CLI 2.1.270 / 900 s timeout (sealed)

## Verdict

**SQI-V1 = QUALIFIED**, limited to the frozen protocol scope (Windows 11,
frozen commits, single machine, 6 tasks × 2 arms × 3 reps, one model).
The verdict answers the eight frozen questions (protocol §24) — it is NOT a
claim that SQI is uniformly superior, and no cost-based verdict is claimed.

## 1. Batch execution integrity

36/36 cells completed, 0 failed, 0 infrastructure failures, 0 blockers
(`SQI_ACCESS_IN_NATIVE` / `BUDGET_VIOLATION` / `TRUNCATION_DISHONESTY` /
`INVALID_ENVELOPE_IN_SESSION` all absent), 0 policy violations, 0 capability-
failure cells. Arm isolation held: no native session touched SQI. Every cell
retains run.json / events.ndjson / agent-output.txt / evaluation.json (V1) /
evaluation-v11.json / sqi-call-log.ndjson; manifest covers 200 artifacts.

## 2. Task correctness (protocol §24.1, §24.6, §24.7, §24.8)

| Task | native | sqi | reading |
| --- | --- | --- | --- |
| T01 symbol lookup + definition | 3/3 | 3/3 | parity |
| T02 caller enumeration | 1/3 | 3/3 | SQI wins: frozen CALLS edges make enumeration reliable; native agents missed ≥4 named production callers in 2/3 reps |
| T03 reference evidence | 3/3 | 3/3 | parity (both arms read the 6 sites) |
| T04 impact frontier | 0/3 | 3/3 | SQI wins decisively: exact 49/1031 aggregates are graph-derived facts; native agents cannot reconstruct them reliably from source alone |
| T05 document → code | 3/3 | 3/3 | parity |
| T06 budgeted bundle | 3/3 | 3/3 | SQI arm additionally proved truncation honesty in-session |
| **Total** | **13/18** | **18/18** | |

No SQI-induced regression: every native success remained a SQI success
(18/18 ⊇ 13/18). The two gaps (T02, T04) are exactly the graph-dependent
capabilities the interface exposes.

## 3. Evidence usage (§24.3) and discipline

- SQI arm: 18/18 cells with citation-closure PASS — every `Evidence Used:` id
  was actually returned by that session's calls; **0 unsupported claims**
  across 59 SQI calls and ~517 KB of envelope payloads.
- Evidence ids were actually consumed by agents (used ids per cell: 1–49),
  heaviest in T04 where all 49 frontier shards' SHARD_RELATION ids were cited.
- Native arm has no citation requirement (per protocol); no native session
  accessed SQI.

## 4. Source-verification boundary (§24.4)

Both arms performed source reads for semantic claims (native 213 read/grep
events, SQI 324). SQI agents verified definitions/call-sites/reference sites
in source before asserting semantics — the envelope's structural facts were
cited directly while semantic claims were source-grounded, exactly the frozen
boundary behaviour. No cell claimed an SQI envelope as semantic ground truth
without a source read (content-level consistency flagged for human review as
planned; no contradiction surfaced in the sampled reviews).

## 5. Oracle V1 → V1.1 (uniform review pass — disclosed)

The V1 machine checks were brittle for three spellings/structuralities:
`aria2::DownloadEngine` vs `aria2.DownloadEngine`, Windows path separators in
read targets, and SQI-only machinery checks applied to the native arm (T06).
V1.1 applies symbol-spelling and path-separator equivalence, gates T06 bundle
checks to the sqi arm, and reclassifies the T05 fixture mismatch (frozen
E-CODE id was minted by the R2 codegraph database while the task declares the
knowledge database; the session-returned CROSS_LAYER_LINK id is the
in-session equivalent). **No success criterion changed**; 16/36 cell verdicts
flipped, all from these normalizations, applied identically to both arms.
V1 evaluations are retained verbatim in every cell; this review judges on V1.1.

## 6. Retrieval path and cost (§24.2, §24.9)

| Metric | native | sqi |
| --- | ---: | ---: |
| total tool calls | 236 | 542 |
| source read/grep events | 213 | 324 |
| SQI calls | 0 | 59 |
| SQI payload bytes | 0 | 517,226 |
| input tokens | 527,160 | 962,640 |
| output tokens | 117,639 | 230,508 |
| cache-read tokens | 3,410,816 | 14,738,944 |
| median session duration | 22.7 s | 73.5 s |

**Honest cost finding**: the SQI arm consumed MORE tokens and wall time in
this configuration — envelope payloads (50–70 KiB in T04) and additional tool
rounds add context cost, while reducing (T02) or enabling (T04) retrieval
paths. Per the frozen protocol, no cost-based verdict is claimed in either
direction; the cost/benefit trade is task-dependent (biggest wins exactly
where graph-derived facts are unreachable by text search).

## 7. Scoped observations (non-gating, recorded)

1. `PROVENLATTICE_SOURCE_READS`: agents in 16/36 cells read files under the
   provenlattice checkout (implementation/task artifacts), concentrated in
   T04 (both arms; e.g. T04.native.r2 reconstructed the frontier from
   `impact.py` and still failed the truncation criterion). Not arm
   contamination under the frozen definition (no SQI tool/envelope in the
   native arm); motivates sandbox scoping in a future protocol version.
2. `T05_ECODE_FIXTURE_MISMATCH`: documented above (§5).
3. `SQI_CONTEXT_COST`: documented above (§6).

None of these is a contract-level blocker; none invalidates the batch.

## 8. Verdict rule check (protocol §7)

- infrastructure failure fraction > 1/3 in any arm: **no** (0/18 both arms)
- confirmed capability failures: **0**
- oracle unreliable: **no** (V1.1 normalization disclosed and uniform)
- block: **no**

**Final: `SQI-V1 = QUALIFIED`** (limited to Contract V1 + Formal Protocol V1
scope). The next mainline decision (overlay/V1.1, sandbox scoping, cost
optimization of envelope payloads, or other capabilities) is out of scope of
this review.

Artifacts: `results/formal/SQI-FORMAL-20260917-1/` — formal-batch-summary.json,
formal-synthesis-v1.json, manifest.sha256 (200 entries), 36 cell directories.

# Batch 05 — A05 Blindness Provenance Audit

**Status: RETAIN**

## Scope

Determine whether the completed A05 annotation (64/64, model glm-5.3-flash)
was actually contaminated by Batch 05 case-specific system prediction
exposure that occurred because the same executor session previously served
as Batch 05 Packaging Agent. Known and disclosed: role separation deviation
YES; B05 attempt in the same session was correctly BLOCKED (0/64) because
the session context already contained A05 verdicts.

## Evidence basis

Primary provenance: the complete opencode session transcript, which is an
enumerable, reviewable record of every tool-mediated file access and every
returned output for this executor. Corroborating on-disk artifacts: the
builder script, the sealed package payloads and their audit scans, and the
packaging/annotation support scripts in the executor temp workspace.
Evidence limitation (recorded, non-blocking): no OS-level file-access audit
log exists for tool-mediated reads; PSReadLine interactive history contains
zero entries for this experiment (verified), so the transcript is the only
and complete access record.

## Q1. Did the packaging phase access only blind-safe construction material?

NO — and this is expected. Packaging legitimately read the frozen candidate
set (results/pilot-candidates.json), which contains system prediction
fields; that read is inherent to building blind views. Every written package
payload is blind-safe: the A05 blind view re-scanned during this audit has
0 forbidden-key hits; the builder script extracts only
`system.candidate_symbol_ids` from candidate records.

## Q2. Did the session see any Batch 05 case-specific system prediction?

NO. For all 64 frozen Batch 05 case IDs, at no point before or during A05
annotation did any tool output display case-specific `system_status`,
selected/predicted target, resolver strategy, resolver confidence, system
verdict, or fidelity correctness content. Every packaging-phase output that
touched candidate data was one of: (a) full-case JSON for cases outside
Batch 05 (see Q3), (b) aggregate group counts, or (c) blind-safe fields.
The A05 annotation phase read only the A blind view, the frozen protocol
files, and frozen repositories.

## Q3. Classification of system-related access

A. Field-name/forbidden-key handling: YES (builder `$disallowedBlindKeys`
   list and audit scans; instruction prose). No values.
B. Aggregate metadata: YES for Batch 05 — the packaging transcript displayed
   Batch 05 stratum distribution counts only (CALLS_RESOLVED 12,
   CALLS_NONRESOLVED 7, IMPORTS_RESOLVED 15, IMPORTS_NONRESOLVED 7,
   REFERENCES_RESOLVED 18, REFERENCES_NONRESOLVED 5). Aggregate counts carry
   no per-case attribution and are recorded here as a non-blocking
   disclosure.
C. Concrete per-case prediction content: YES, but for exactly two cases,
   both OUTSIDE Batch 05 (verified against the frozen plan's batch
   manifests; the 269-case partition is duplicate-free, so these IDs cannot
   belong to any other batch):
   - FQV1-aria2-e057f6d338d4b31b — batch_01_calibration member (printed as
     the first candidate-set record during packaging).
   - FQV1-aria2-5a4f0360db806a83 — batch_02 member (printed as the first
     REFERENCES case during packaging).
   Both batches are already sealed/complete; neither case is part of A05's
   64. No Batch 05 case-specific content was displayed.

Supplementary disclosure for completeness: the batch_02 exposed case resides
in the same file (doc/manual-src/en/mkapiref.py) as A05 case
FQV1-aria2-dd9fef894c065810 (line 290 vs line 289; different raw reference,
different case_id, different batch). A05's verdict for that case
(NO_VALID_TARGET: argparse-dynamic attribute, no in-tree binding) was
derived from fresh source reads of mkapiref.py:260-292 during annotation and
runs opposite to the direction the prior-batch exposure would suggest.
Recorded as corroboration only; the RETAIN conclusion rests on the exposure
enumeration, not on an influence judgment.

## Q4. Did any concrete prediction exposure occur before A05 annotation?

The two concrete exposures (both non-Batch-05 cases) occurred before A05
annotation, during packaging. No Batch 05 concrete per-case exposure occurred
at any time. The Batch 05 aggregate stratum counts were also seen before
annotation and are disclosed above.

## Gate

- Batch 05 case-specific system prediction exposure: 0 (proven by complete
  transcript enumeration plus on-disk artifact consistency; not an
  influence/probability judgment).
- Therefore: RETAIN.

## Disposition

- A05 blindness status: VALID.
- A05 role separation: DEVIATION — Packaging and Annotation roles shared one
  session; methodology disclosure required (already recorded in the A05
  execution note and in this audit). No demonstrated answer leakage.
- A05 sealed record remains valid; usable for Agreement Audit 05 once B05 is
  completed in a fresh executor session (B05 remains BLOCKED/INVALID in this
  session; Agreement Audit 05 must not run until then).
- A05 clean rerun: NOT required.
- Sealed records modified: 0. No verdict, record, or package payload was
  changed by this audit.

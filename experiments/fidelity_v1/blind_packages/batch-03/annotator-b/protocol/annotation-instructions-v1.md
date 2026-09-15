# Annotator B — Batch 03 Instructions

This package is for independent blind annotation by Annotator B. Batch ID is 03 and the sample count is 60. Verify each source-level relation in the frozen ria2, rpc, or ocksdb repository using the unchanged frozen Evidence Scope V1, CALLS_V1, and Declaration–Definition Equivalence V1 semantics.

Allowed reading is limited to this clean package and read-only source navigation in the three frozen repositories. Do not access Batch 02 annotations, reports, agreement or adjudication artifacts; the other Batch 03 annotator package or outputs; system predictions; resolver status, strategy, confidence, or selected targets; or Graph Fidelity metrics.

Use only these formal verdicts: ONE_VALID_TARGET, NO_VALID_TARGET, MULTIPLE_VALID_TARGETS, RELATION_NOT_PRESENT, BUILD_CONTEXT_DEPENDENT, INSUFFICIENT_EVIDENCE.

Complete every field in output/annotation-record-template.json. Telemetry is measurement-only and does not change protocol semantics. 
avigation_files_count must equal the number of entries in 
avigation_files. 
avigation_hop_count records transitions in ordered 
avigation_path. erification_depth must be one of L0, L1, L2, L3, or L4. Record target recovery only when navigation beyond the sample source file was needed. INSUFFICIENT_EVIDENCE is permitted only after all Evidence Scope V1 methods have been exhausted.

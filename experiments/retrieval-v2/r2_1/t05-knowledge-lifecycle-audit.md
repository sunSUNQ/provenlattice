# T05 Knowledge-R2 Evidence Lifecycle Audit

## Classification

**A. Query Bundle Gap**

The required Cross-Layer Link `E-XLINK-02e59d12b69fb54749eacbc0` was returned, exposed, cited,
and accepted by the evaluator. Its source is the required DocumentSection node
`documentsection:dcf07b60c9d54b6886a55e652c19b75f9f8bca778462868f93047202eabf1cff`, but the corresponding
Evidence `E-DOC-9d9674320ddc2684f8d2773a` never entered the bundle. Therefore the Agent could not cite
that precise Evidence ID.

This is not a Presentation or Agent Usage Gap because the ID was absent before presentation. It is
not an Evaluator Mapping Bug: the evaluator's returned, used, unsupported, hit, and miss sets match
the recorded events and final citations exactly.

## Lifecycle sets

- `returned_evidence_ids`: 35 IDs; see the JSON companion for the complete sorted set.
- `exposed_evidence_ids`: identical to returned (35 IDs).
- `used_evidence_ids`: 16 IDs.
- `ground_truth_evidence_ids`: `E-DOC-9d9674320ddc2684f8d2773a`,
  `E-CODE-20376c6ce1b46be66b8a2d4a`, `E-XLINK-02e59d12b69fb54749eacbc0`.
- `unsupported_evidence_ids`: `E-CODE-4374cc9a74236b67c11f3479`,
  `E-CODE-c2f8a2e93cb05e73b643fbbe`.

## Query to evaluation map

| Query | Anchor | Returned / exposed / used | Ground-truth result |
|---|---|---:|---|
| find-related-code | `docs/cn/backup_request.md` | 1 / 1 / 1 | document root only; exact section absent |
| explain-symbol | `brpc::BackupRequestPolicy` | 0 / 0 / 0 | unresolved anchor |
| explain-symbol | `brpc::CreateRateLimitedBackupPolicy` | 0 / 0 / 0 | unresolved anchor |
| explain-symbol | `BackupRequestPolicy` | 2 / 2 / 1 | no required ID |
| explain-symbol | `CreateRateLimitedBackupPolicy` | 2 / 2 / 1 | no required ID |
| explain-symbol | `RateLimitedBackupPolicyOptions` | 4 / 4 / 3 | required code + link hit; required section missing |
| explain-module | `src/brpc/backup_request_policy.h` | 0 / 0 / 0 | unresolved shard anchor |
| find-related-documents | `BackupRequestPolicy` | 0 / 0 / 0 | no link for resolved forward declaration |
| explain-symbol | `ChannelOptions` | 2 / 2 / 1 | no required ID |
| explain-module | `src/brpc` | 16 / 16 / 2 | no required ID |
| explain-symbol | `RateLimitedBackupPolicy` | 2 / 2 / 2 | no required ID |
| explain-symbol | `Channel` | 2 / 2 / 1 | no required ID |
| explain-symbol | `backup_request_ms` | 2 / 2 / 1 | no required ID |
| explain-symbol | `BackupRateLimiter` | 2 / 2 / 1 | no required ID |

The final citation set added two IDs not present in any Agent-visible bundle. The evaluator correctly
classified these as unsupported. The missing required DocumentSection caused exact recall 2/3 and
Task Success failure.

## Allowed correction

When `explain_symbol` returns a resolved Cross-Layer Link, compose the directly linked
DocumentSection Evidence into the same bundle with its existing stable Evidence ID. No Knowledge
nodes, links, resolver rules, or evaluator logic are added or changed.

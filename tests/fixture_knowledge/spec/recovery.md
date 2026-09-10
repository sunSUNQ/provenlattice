# Recovery Specification

## REQ-RECOVERY-001 Retry failed recovery

The retry path is implemented by [symbol:storage.StorageRecovery.retry].
The historical name [symbol:duplicate] is ambiguous and must not create an edge.
The planned hook [symbol:storage.Missing.run] is unresolved and must not create an edge.

## Acceptance Criteria

Recovery behavior is verified by [symbol:recovery_test].

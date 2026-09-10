# ProvenLattice V1.0-R1 Harness Infrastructure Fix

- Old frozen commit: `f323622df1680410304055a84d820581d4e04ba3`
- Reason: Claude print mode was receiving the serialized `RunRequest` instead of the frozen
  task prompt, Python did not resolve the Windows npm `claude.cmd` launcher, Windows decoded
  Claude's UTF-8 stream with GBK, and the runner hard-coded all output to `r1`.
- Scope: prompt transport, Claude stream event accounting, immutable run metadata,
  repetition paths, resume/quarantine/retry orchestration, repository protection, audit,
  aggregation, and report generation.
- Semantics unchanged: tasks, prompts, Ground Truth, Arm capability sets, metrics meaning,
  deterministic evaluator, Core, Resolver, and Knowledge Layer.
- Regression validation: 37/37 tests pass, `compileall` passes, and `git diff --check` passes.

All qualification data produced before this fix is invalid. No valid real-agent run existed
before the fix, so there was nothing to move to `_invalidated_pre_fix/`.

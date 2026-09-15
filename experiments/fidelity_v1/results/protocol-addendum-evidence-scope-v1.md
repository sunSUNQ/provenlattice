# Protocol Addendum — Evidence Scope V1 (FROZEN)

```text
status: FROZEN
date: 2026-09-14
ratified_by: experiment owner (calibration-01 adjudication review)
parent_protocol_commit: 12f405c677582a2982d035433bf6837126772716
supersedes: OPEN-1 (calibration-gate-01)
related: protocol-addendum-calls-v1-macro-semantics.md (unchanged)
```

## Effective from / Applies to / Does not rewrite / Calibration interpretation

```text
Effective from:
Full Annotation Phase

Applies to:
all remaining 244 samples

Does not rewrite:
sealed Calibration A/B records

Calibration interpretation:
documented deviation only
```

Calibration interpretation (gate level only, sealed records unchanged): the calibration exposed an
evidence-scope execution difference; before formal annotation, this addendum clarifies the
admissible evidence boundary. It changes **no relation semantics**.

## 1. Principle

> **Annotator 的证据边界不是"只限盲化包"，而是"只限冻结仓库中、通过只读导航可获得的源码与冻结
> Build Context"。**

(The annotator's evidence boundary is not "the blind package only"; it is "source obtainable by
read-only navigation within the frozen repository, plus the frozen Build Context.")

## 2. Allowed

```text
- 从 blind sample 提供的 source location 出发
- 在同一冻结 repository commit 内
- 进行只读跨文件导航
- 查找 declaration / definition
- 追踪 type / owner / namespace / include
- 进行必要的局部类型传播
- 查看候选 symbol 的源码事实
- 查看冻结 Build Context 中已允许的信息
```

## 3. Prohibited

```text
- 读取 ProvenLattice system_status
- 读取 resolver strategy / confidence
- 读取系统 selected target
- 读取 Annotator A/B 对方结果
- 读取 agreement / adjudication 结果
- 使用未冻结的外部构建产物
- 使用网络搜索或外部知识来补足源码事实
- 运行会改变 repository 状态的命令
```

## 4. Adjudication rule

```text
如果唯一正确 target 可以通过冻结仓库内的只读源码导航
和允许的 Build Context 唯一确定，
则不能仅因为 blind package 本身未直接展示全部链路
而判 INSUFFICIENT_EVIDENCE。
```

## 5. Effect on the verdict vocabulary

- No new verdict category is introduced; the six world-fact verdicts are unchanged.
- `INSUFFICIENT_EVIDENCE` is henceforth reserved for cases where the target (or relation existence)
  cannot be determined **even under the full Evidence Scope V1** (allowed navigation + allowed
  Build Context).
- `BUILD_CONTEXT_DEPENDENT` is unchanged: it applies when the determination depends on build
  context that is unavailable under the frozen Build Context policy — not merely because the blind
  package omitted the chain.
- `EVIDENCE_SCOPE_TOO_NARROW` is a **process-deviation tag for audit only** (e.g., the calibration
  interpretation of Annotator A's package-bound stop on
  `FQV1-aria2-713b641e93cc620c`); it is **not** a `relation_verdict` and must never appear in the
  verdict field. Under this addendum, B's cross-file type propagation on that case is the
  protocol-conformant strategy.
- Relation semantics (including the frozen CALLS_V1 macro rule) are unaffected.

## 6. Executor obligations (full phase)

- Every record must include `navigation_files[]` (files read inside the frozen tree beyond the
  sample's own source file) and `evidence_locations[]` (`path:line` anchors), so that
  navigation depth is analyzable per relation.
- Read-only repository access only; no repository mutation; no network retrieval of source facts.
- Cross-annotator blindness rules from the frozen protocol remain in force for the full phase.

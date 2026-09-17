# SQI Contract V1 → V1.2 Amendment (Identity / Policy Session-Level Hoisting)

> 状态: **V1.2 AMENDMENT FROZEN**（2026-09-17，C1 target freeze 之后、C2 实现之前）。
> 依据: `cost-optimization-targets-v1.json` OPT-IDENTITY-DEDUP
> （C0: 逐 evidence repository/commit 105 B × 320 条 ≈ 34 KB；逐调用 policy 249 B ×
> 59 次 ≈ 15 KB——均为与 envelope header 或冻结常量字节相同的信息重复）。
> 本 amendment 是**信息保持性重写**：不改变任何 fact、evidence id、成功标准或
> C1 绑定语义；仅将逐条重复的常量提升到 session 层。

## A1. Per-evidence `repository` / `commit` → header-resolved

- 规则: evidence 条目的 `repository` / `commit` **当且仅当与 envelope header
  完全一致时省略**；不一致（如 `code.related` 复合调用中由 code database 铸造的
  evidence）时必须原样保留。
- 语义: evaluator / harness 从 envelope header（repository、commit）解析缺失值；
  header 与任一 evidence 的值冲突仍判 invalid（provenance binding 不变）。
- 动机: 同一 session 内这些字段逐条字节相同（C0 F3），属纯重复。

## A2. `source_verification_policy` → session-level

- 规则: policy 块（冻结常量，249 B）**每 session 只需出现一次**——bridge 在
  session 的首个 envelope 中携带，后续 envelope 可省略；evaluator 校验
  session 首个 envelope 必含完整 policy，后续 envelope 无 policy 不算违规。
- 动机: 该块是冻结常量，逐调用重复无信息量（C0 F3）。

## A3. 不变式（明确列出，防止语义漂移）

1. evidence_id 派生不变（C2）；kind 枚举不变；
2. C1 双向绑定不变（fact ↔ evidence 覆盖检查仍按 id/fact_id 执行）；
3. budget / truncation / returned_evidence_ids / params / result_meta 语义不变；
4. 六个 canonical call、预算上限、源码验证边界、Overlay 排除——全部不变；
5. session 首个 envelope 仍必须携带完整 policy（S8 边界不变）。

## A4. 生效与验证

- envelope schema 更新: evidence `repository`/`commit` 与
  `source_verification_policy` 改为 optional；header 值冲突检查保留；
- evaluator 更新: session 首 envelope policy 强制 + 缺省字段 header 解析；
- 实现（adapter/bridge/validator/evaluator）与测试随 C2 一起 re-seal；
- **C4 正式 batch 前必须**: 更新后的 evaluator 对 36 个 V1.1 baseline cells
  离线重放，证明信息保持（evidence ids 与 facts 为超集），并记录于
  `results/formal/SQI-FORMAL-20260917-1/c2-replay-verification-v1.json`。

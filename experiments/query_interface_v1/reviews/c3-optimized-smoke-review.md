# C3 Optimized Smoke Review — PASS

Smoke date: 2026-09-17
Scope: `C3 Optimized Smoke — T01–T06`（optimized implementation 链路 smoke；
非成本结论——C4 实测）

## Verdict

**C3 Optimized Smoke = PASS（6/6）。** 全部任务在 optimized implementation
（C2：投影 / 复合 / 去重 / V1.2 session-level policy）上通过 frozen-anchor
验证与机械检查；bridge session smoke 另行验证 policy-once、composite 单调用
双库 evidence 与 short-circuit 真实生效。无 isolation 回退、无 capability
failure、无 budget/truncation violation。

## 1. Optimized adapter smoke（6/6）

Run: `SQI-SMOKE-20260917T071325Z-f64393`（raw per-task envelopes 本地保留，
manifest 版本化摘要；旧 V1.1-era smoke `SQI-SMOKE-20260917T020338Z-15ea13`
已标 superseded）

| 任务 | frozen-anchor 验证（optimized 路径） |
| --- | --- |
| T01 | declaration_line=84、file_matches（file_path 紧凑投影） |
| T02 | 7/7 frozen CALLS edges（fact_id）+ caller rows |
| T03 | 6 resolved refs + E-REF ids |
| T04 | frontier_size=49 · boundary_edges_total=1031 · wide_impact=true · truncation_declared |
| T05 | **单次复合调用同时返回** E-CODE-9cec…（code DB）与 E-XLINK-3284…（knowledge DB） |
| T06 | 预算内 + truncation_declared + 诚实 omitted counts |

V1.2 envelope/schema/validator：全部 PASS（含 optional policy / optional
per-evidence repository·commit 的 session 语义）。

## 2. Bridge session smoke（policy-once + composite + short-circuit）

`results/implementation-smoke/bridge-session-smoke-v1.json`，5/5 checks PASS：

1. **composite_single_call_dual_db**：一次 `code.related` 同时返回
   knowledge E-XLINK 与 code E-CODE（`result_meta` 双库明细）；
2. **policy_emitted_once**：session 首个 envelope 携带 policy，第二个
   envelope 不携带（V1.2 A2）；
3. **short_circuit_served_from_cache**：同参重复调用命中确定性 call log，
   envelope 与首调 byte-identical、`served_from_cache=true`；
4. **t02_frozen_edges_intact**：7/7；
5. **all_exit_zero**。

## 3. Isolation / budget / truncation 无回退

- isolation：双 arm scoped allowedTools 不变；leakage scanner 测试随 56-test
  套件通过（wiring 测试 19 项含 6 项 isolation）；
- budget/truncation：T04 边界 id 预算化列示 + T06 bundle 截断诚实均在
  optimized 路径复验；
- 无新增 capability failure flags。

## 4. C4 放行

Optimized smoke 6/6 PASS 后，按冻结协议进入
**C4 — 36-cell Before/After Formal Qualification**（V1.1 protocol + V1.2
amendment，同 36 cells 同序同 model/config；floor：18/18 · T02 3/3 · T04 3/3 ·
closure 100% · unsupported 0 · source-verification 不降 · 无新 violation）。
成本数字只在 C4 对照后宣称。

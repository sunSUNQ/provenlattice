# P2 / SQI-V1 — Structured Query Interface V1 (Agent-Facing)

> 状态：**SQI-V1 = QUALIFIED + V1.1 HARDENING PASS + V1.2 QUALIFIED / RELEASE READY**（2026-09-20）。
> Contract V1 FROZEN → Implementation FROZEN → Six-Task Smoke PASS →
> Formal Protocol V1 FROZEN → **Formal Batch 36/36**（native 13/18 vs SQI 18/18，
> 0 blocker / 0 capability failure）→ **V1.1 Hardening PASS**：
> sandbox 隔离（预防层 live 实证 + `CHECKOUT_LEAKAGE` 检测层）、
> T05 fixture repair（双库 evidence source 一致，amendment seal 2/2）、
> oracle normalization 前置冻结（protocol v1.1）。
> **SQI Cost Optimization V1 → SQI-V1.2 QUALIFIED（release ready）**：
> C4-R4 完整 clean 36-cell batch 单 backend SQI 18/18、9/9 frozen floors、
> 成本 vs V1.1 baseline input -36% / output -58% / cache-read -73%；
> 修复路线 = 失败 → 归因 → 通用修复（V1.2-NR2）→ 完整重资格
> （`reviews/v1.2-final-qualification-review.md`）。

## 1. 本线要回答的问题

Agent 能否通过一组**有界、可引用、可验证**的结构化查询稳定消费 ProvenLattice 图能力，
而不是靠无界遍历把整张图塞回上下文？

## 2. 目录

| 路径 | 内容 | 状态 |
| --- | --- | --- |
| `contract/structured-query-interface-contract-v1.md` | SQI Contract V1：查询面、envelope schema 语义、分层暴露、provenance、预算、源码验证规则、6 个 qualification 用例 | FROZEN（seal 7/7） |
| `tasks/SQI-T01..T06.json` | 冻结 qualification 任务（锚点于 2026-09-16 对 frozen DB 只读实测固定） | FROZEN（并入 contract seal） |
| `schema/sqi-envelope-v1.json` | envelope 结构 schema（C4） | FROZEN（implementation seal 5/5） |
| `tools/sqi_validator.py` | C1–C4 语义、预算记账、provenance 绑定、截断诚实性 validator | FROZEN（implementation seal） |
| `tools/sqi_adapter.py` | 6 个 canonical call handler（共享预算池、确定性排序、有界投影、shard-level impact） | FROZEN（implementation seal） |
| `tools/sqi_runner.py` | qualification runner（implementation-smoke 模式；拒绝 formal；frozen-anchor 验证） | FROZEN（implementation seal） |
| `tests/test_sqi_v1.py` | 21 项 implementation tests（全部 PASS） | FROZEN（implementation seal） |
| `contract/sqi-formal-qualification-protocol-v1.md` + `formal-protocol-config.json` | Formal Protocol V1（arms、reps=3、model/config、oracles、指标、verdict 规则、停止条件） | FROZEN（seal 2/2） |
| `tools/sqi_cli.py` | CLI bridge：agent 消费 SQI 的唯一路径（`--params` JSON 与 shell 安全 `--arg` 双形式；stdout 仅一个 envelope；per-session call log） | FROZEN（secondary seal 9/9） |
| `tools/sqi_evaluator.py` | T01–T06 冻结 oracle（citation closure、source verification、capability-failure flags） | FROZEN（secondary seal） |
| `tools/sqi_formal_runner.py` | formal runner（--check preflight / --run-cell / --batch；arm parity；session PYTHONPATH wiring） | FROZEN（secondary seal） |
| `tests/test_sqi_formal_wiring.py` | 19 项 wiring tests（bridge/evaluator/arm parity/preflight/--arg 形式） | FROZEN（secondary seal） |
| `results/implementation-smoke/` | Six-Task Smoke（optimized）：run `SQI-SMOKE-20260917T071325Z-f64393` 6/6 PASS + bridge-session-smoke-v1.json（5/5 checks）+ superseded 历史 run 标记 + manifest | CURRENT（C3） |
| `results/formal/SQI-FORMAL-20260917-1/` | **正式 36-cell batch**：run/evaluation(V1+V1.1)/events/output/call-log per cell + formal-batch-summary.json + formal-synthesis-v1.json + cost-attribution-v1.json + c2-replay-verification-v1.json + manifest.sha256（200 entries） | COMPLETE |
| `reviews/` | implementation-freeze-review、six-task-smoke-review、stage3a-secondary-freeze-review、sqi-v1-final-qualification-review、v1.1-hardening-review、c0-cost-attribution-review、c2-implementation-review、c3-optimized-smoke-review | PASS |
| `reviews/sqi-v1-final-qualification-review.md` | 最终资格 review（含 oracle V1.1 披露、成本诚实报告、scoped observations） | **QUALIFIED** |
| `contract/sqi-formal-qualification-protocol-v1.1.md` | V1.1 amendment（sandbox isolation、T05 fixture repair、oracle normalization 前置冻结） | FROZEN（amendment seal 2/2，含修订版 SQI-T05.json） |
| `contract/cost-optimization-targets-v1.json` | **C1 target freeze**（OPT-T01 投影 / OPT-T05 调用压缩 / OPT-IDENTITY-DEDUP + 9 条不可退化 floor） | FROZEN（seal 1/1） |
| `contract/structured-query-interface-contract-v1.2-amendment.md` | V1.2 amendment（identity/policy session 级上提语义） | FROZEN（seal 1/1） |
| `tools/sqi_isolation.py` | checkout-leakage 确定性扫描（`CHECKOUT_LEAKAGE` → cell invalid） | FROZEN（secondary seal V1.2，11/11） |
| `results/formal/SQI-FORMAL-20260917-1/cost-attribution-v1.json` | **C0 cost attribution baseline**（18 SQI cells 逐源拆解：productive 80.2% / dedup 7.4% / cache amplification 15.3×；SAFE_TO_REMOVE/DEDUP/ON_DEMAND/MUST_KEEP 分类） | PASS |
| `results/formal/SQI-FORMAL-20260917-1/c2-replay-verification-v1.json` | **C2 离线信息保持性重放**（18 sqi cells legacy vs optimized：0 floor breach） | PASS |
| `reviews/c0-cost-attribution-review.md` | C0 review（T02/T04 成功归因到图事实；C1–C3 杠杆与 correctness floor） | PASS |
| `reviews/c2-implementation-review.md` | C2 review（三 target 实现、V1.2 先 seal、56/56 tests） | PASS |
| `reviews/c3-optimized-smoke-review.md` | C3 review（optimized 6/6 + bridge session smoke 5/5 checks；C4 放行） | PASS |

## 3. V1 查询面（冻结，6 个 canonical calls）

`symbol.lookup` → `symbol.callers/callees` → `symbol.references` → `impact.frontier`
→ `code.related`，外加预算化组合 `bundle.explain`。统一 JSON envelope，强制
evidence citation（确定性 `E-*` id）、强制预算与显式截断、强制源码验证纪律
（语义断言必须回源码）。Overlay 读路径 defer 到 V1.1。

## 4. Qualification 用例（冻结）

| 任务 | 仓 | 链路 | 难度 |
| --- | --- | --- | --- |
| SQI-T01 | B1-aria2 | symbol lookup → definition | Easy |
| SQI-T02 | B2-brpc | lookup → callers → call-site 验证 | Medium |
| SQI-T03 | B3-rocksdb | lookup → references → reference evidence | Medium |
| SQI-T04 | B3-rocksdb | impact frontier（49 shards / wide_impact） | Hard |
| SQI-T05 | B2-brpc | document → code.related（复用 R2 T01 ground truth） | Medium |
| SQI-T06 | B2-brpc | bundle.explain 预算合规 + 截断诚实性 | Hard |

Arms：`Native` vs `SQI`；每 cell ≥3 reps；gates：schema-valid 调用、预算合规、
citation 闭包、源码验证纪律、frozen ground truth 正确性、RQ4/RQ5 指标采集。

## 5. 下一阶段（Stage 3 —— 未启动）

1. 实现 formal bridge：adapter 以 CLI 工具形式暴露给 agent（`--allowedTools` 纳入
   R2 harness），native arm 保持纯文件工具；evaluator 扩展 T02–T06 oracle。
2. bridge/evaluator/harness 集成文件次级 seal。
3. 执行 `SQI-V1 Formal Task-Level Qualification — Native vs SQI`
   （36 cells：6 任务 × 2 arms × 3 reps，model/config 按 formal-protocol-config.json，
   中途不得漂移），随后 cross-task evidence synthesis 与 SQI-V1 verdict。

## 6. 治理约束

- Contract V1 冻结后，查询面/envelope/预算/gates/任务锚点的任何变更必须升版本，
  禁止原地修改；旧 evidence 不得并入新 qualification。
- RQ2 线全部 artifacts（21 formal records、3 summaries、synthesis、freeze seal）
  原样不动；本线只读消费。
- RQ1 deferred 的 CALLS/Resolver 覆盖缺口不修复；`unresolved` 状态原样暴露，
  由本线在 Agent 消费语境下量化。
| esults/implementation-smoke/bridge-session-smoke-v1.json\ | **C3 bridge session smoke**（composite 单调用双库 evidence / policy-once / short-circuit byte-identical） | PASS 5/5 |
| eviews/c3-optimized-smoke-review.md\ | C3 review（optimized 6/6 + bridge session smoke 5/5 checks；C4 放行） | PASS |
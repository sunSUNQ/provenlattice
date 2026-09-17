# C2 Optimized SQI Implementation Review — PASS

Implementation date: 2026-09-17
Scope: `C2 Optimized SQI Implementation — Fewer Calls, Leaner Projections`
（依据冻结的 `contract/cost-optimization-targets-v1.json`；无 Agent、无新正式实验）

## Verdict

**C2: PASS.** 三个冻结 target 全部实现；V1.2 amendment 先 seal 后实现；实现
re-seal（implementation 5/5 + secondary 11/11）；48→56 tests 全绿；离线 36-cell
信息保持性重放 **0 floor breach**。未宣称任何 token/cache 优化效果（C4 实测）。

## 1. OPT-T01-PROJECTION（已实现）

`symbol.lookup` 候选行改为紧凑 identity 形式：`id / qualified_name / kind /
file_path / shard_path / start_line / end_line`；`signature` 与 metadata blob
不再返回；`file_path` 由同库 files 表确定性补全。过滤、上限、排序、evidence
id 派生全部不变。测试：compact 形式断言、unfiltered 上限断言、链式 symbol_id
稳定性断言。

## 2. OPT-T05-COMPRESSION（已实现）

`code.related` 在任务声明 `code_database` 时，于**同一次调用**内追加目标
symbol 在 code database 的定义行 + CODE_DEFINITION evidence（V1.2：跨库
evidence 的 repository 不同则原样保留），`result_meta` 给出
`knowledge_db_evidence_ids / code_db_evidence_ids / composite / composite_unresolved`
分库明细。同 session 重复调用由 bridge 的确定性 call log 短路
（`served_from_cache`），无重算。**不新增 canonical call**；`code_database`
是 session wiring（env/任务元数据），非 agent-facing 参数。

修复实现缺陷一处：复合追加行曾导致遍历-追加死循环（snapshot 迭代修复，
faulthandler 定位）。

## 3. OPT-IDENTITY-DEDUP（V1.2 amendment 先 freeze 后实现）

- `contract/structured-query-interface-contract-v1.2-amendment.md`（seal
  `sqi-contract-v1.2-amendment.seal.sha256`）：逐 evidence repository/commit
  与 header 一致时省略（跨库铸造时保留）、`source_verification_policy`
  session 首 envelope 携带一次、五个不变式明确列出；
- schema V1.2：上述字段 optional；validator：present-时一致性检查 + 新增
  `session_policy_errors`（session 首 envelope 强制 policy）；
- adapter：`_dedupe_evidence_projection` 统一应用（lookup/callers/references/
  frontier/bundle 全路径）。

## 4. 回归与保护

- 测试：**56/56 PASS**（22 implementation + 34 wiring；新增投影/复合/短路/
  V1.2 校验/隔离断言）；
- T02 保护：重放显示 7/7 frozen CALLS edges 仍以 `metadata.fact_id` 进入
  session evidence；
- T04 保护：重放 `result_meta` 聚合逐字节等于冻结值（49 / 1031 / wide_impact），
  boundary_edge_ids 预算化列示不变；
- `verify_release.py`：RELEASE VERIFICATION PASS。

## 5. 离线 36-cell 信息保持性验证（无 Agent）

`results/formal/SQI-FORMAL-20260917-1/c2-replay-verification-v1.json`：
18 个 sqi cells 的冻结链步骤以 legacy-emulation（V1.1 行为）与 optimized C2
各重放一次，逐调用比较：

- evidence-id 超集：18/18 PASS；fact-id 超集：18/18 PASS；
- floor artifacts：T02 7/7 edges、T04 49/1031/wide、T05 双库 required ids
  全部在 optimized 会话中返回；
- 字节变化：T01–T04/T06 ±0.0%（投影在单行/等值场景无增益，符合 C0 预期）；
  T05 +34.9%/call——**以 +1 KB 的单调用增量消除 13/10 次跨库往返**
  （cache amplification 22.6× 的主杠杆），收益在 C4 实测；
- **floor breach：0。**

## 6. 未宣称 / 未做

- 未宣称 token/cache 成本优化效果（C4 实测）；
- 未跑任何 Agent session；C3（optimized smoke）与 C4（36-cell before/after）
  未启动；
- 基线 batch（SQI-FORMAL-20260917-1）仍是现行 SQI-V1 资格证据。

## 7. Seal 终态

| Seal | 状态 |
| --- | --- |
| Implementation（5 文件，含 V1.2 schema） | 5/5 PASS |
| Secondary（11 文件，含 sqi_isolation、全部 C2 实现） | 11/11 PASS |
| Contract V1 freeze / Protocol V1 / V1.1 amendment / V1.2 amendment | 全部 PASS |

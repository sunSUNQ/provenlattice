# Graph Fidelity V1 — Blind Agreement Audit / Calibration 01

## Audit boundary

- Inputs: Annotator A's 25-case source record and Annotator B's 25-case structured record.
- System status, resolver strategy, confidence, and selected target were not used for this audit.
- No ProvenLattice precision, recall, or selective-risk value is computed.
- The audit compares source-level facts first. System-dependent verdicts remain deferred until the blinded join.

## Batch and blindness checks

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| Case ID 对齐 | PASS | 25/25 相同；B 的确定性重建与 A 校准批完全对齐 |
| Annotator A/B 交叉读取 | PASS | B 记录声明未读取 A；本次审计在两份记录完成后进行 |
| 系统判定泄露 | PASS | 未发现 A/B 记录读取 `status`、策略、置信度或系统目标的证据 |
| 源码核验 | PASS | A/B 均提供源码位置和证据说明 |
| 构建上下文 | PASS（规范化后） | A 的“未使用额外上下文”与 B 的 `SOURCE_SUFFICIENT` 语义一致 |

## Agreement summary

### Semantic relation existence

| 指标 | 值 |
| --- | ---: |
| Exact agreement | 24 / 25（96.00%） |
| Disagreement count | 1 |
| Disagreement rate | 4.00% |
| Cohen's κ | 不可稳健估计（A 全部标为存在，边际分布退化） |

唯一分歧是 `FQV1-rocksdb-1273fbd969565cef`：A 将 `ASSERT_EQ` 视为源码中的宏调用关系，B 按冻结关系目标语义标记为 `RELATION_NOT_PRESENT`（该 RawReference 不对应仓内 callable target）。这不是系统对错判断，而是关系族语义边界的裁决问题。

### By relation

| 关系 | 样本数 | 一致 | 分歧 | 一致率 |
| --- | ---: | ---: | ---: | ---: |
| CALLS | 9 | 8 | 1 | 88.89% |
| IMPORTS | 8 | 8 | 0 | 100.00% |
| REFERENCES | 8 | 8 | 0 | 100.00% |

### By repository

| 仓库 | 样本数 | 一致 | 分歧 | 一致率 |
| --- | ---: | ---: | ---: | ---: |
| aria2 | 11 | 11 | 0 | 100.00% |
| brpc | 7 | 7 | 0 | 100.00% |
| RocksDB | 7 | 6 | 1 | 85.71% |

### Target and evidence fields

- 12 条有仓内目标的样本中，11 条 A/B 给出了相同的目标路径。
- `FQV1-aria2-713b641e93cc620c`：A 记录了调用语义，但保留目标未确定；B 通过只读候选/源码核验确定 `src/ValueBase.cc:123`。该项属于目标证据不足，不应被当作系统错误。
- 其余外部库、局部变量或跨语言同名样本均被双方识别为无仓内目标；这些样本不计入仓内目标路径的 exact-match 分母。

## Protocol-issue association

| Issue | 关联分歧数 | 观察 |
| --- | ---: | --- |
| PI-B-1 batch delimitation | 0 | 25/25 case ID 已证明一致；记录为治理 deviation，不导致样本失效 |
| PI-B-2 candidate-context lookup | 0 | 双方均使用只读候选定义核验；未发现系统字段泄露 |
| PI-B-3 blind verdict mapping | 1（结构性） | A 使用语义记录而非正式枚举，导致正式 verdict κ 无法直接计算；第 2 条分歧暴露了关系目标语义边界 |
| PI-B-4 Python cases in C/C++ pilot | 0 | 9 条 Python 源码样本未造成 A/B 分歧，但必须在 Gate 裁决中标记 scope deviation，不得混入 C/C++ 统计 |

分歧完全集中在 `CALLS + RocksDB + macro` 这一条；不能据此宣称整体协议已经通过。

## Calibration Gate decision

**HOLD**

理由：

1. Case membership、盲性和源码核验均通过。
2. 关系存在性 exact agreement 为 96%，但唯一分歧触及 `CALLS` 是否要求仓内 callable target 的核心语义，必须完成既有协议下的裁决。
3. A 的记录没有 formal verdict enum，Cohen's κ 不能作为本批可报告的可靠统计量。
4. Python 样本的 scope deviation 尚未完成裁决；应保留原始记录，但不得进入冻结的 C/C++ Fidelity 统计。

## Required next action

保持 A/B 原始结果不变，针对第 2 条和 A 的目标证据不足项做一次 batch-level adjudication；同时单独决定 Python 样本是 `OUT_OF_SCOPE_SAMPLE` 还是保留为语言扩展观察。只有在该裁决完成并形成可复现的 formal verdict 映射后，才能重新运行 Calibration Gate。剩余 244 条暂不开始，Precision/Recall/κ 也暂不发布。

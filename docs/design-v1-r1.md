# ProvenLattice V1.0-R1 — Standalone Retrieval Qualification

## Question

> CodeGraph + Knowledge Layer 是否能在真实工程任务中，提高 Code Agent 的工程证据定位效率和准确性？

这是 ProvenLattice 自己的 qualification，不测试 TASCO，也不假设 MCP、Plugin 或 SDK 已存在。

## Conditions

对同一任务、同一仓库 revision、同一 Agent 能力和同一停止标准进行三组对照：

| Condition | Available capability |
| --- | --- |
| A — Native | 文件读取、搜索和普通代码探索 |
| B — CodeGraph | A + ProvenLattice CodeGraph CLI / Python Query API |
| C — Knowledge Evidence | B + Document / Section / RawEvidenceLink / Cross-layer query |

R1 的首选任务是 B2 brpc 中存在真实文档与代码关系的模块任务。任务描述、仓库 SHA、成功判定和参考证据集必须预先冻结；不得向真实仓库添加合成 Requirement。

## Task contract

一个合格任务至少需要：

1. 一个真实文档或文档 Section 作为问题起点；
2. 一个或多个真实实现 symbol / shard 作为目标；
3. 至少一个模块关系或调用关系需要解释；
4. 可由人工 reference answer 判定 evidence correctness；
5. 能区分正确代码、合理候选和错误路径。

示例形式：根据文档中关于连接管理的描述，找到负责实现该行为的核心代码，并解释它与相关模块的关系。示例不是固定任务，正式任务集需基于实际仓库内容冻结。

## Measurements

### Correctness

- `task_success`
- `evidence_correctness`
- `wrong_link_rate`
- `wrong_path_rate`

### Retrieval efficiency

- `tool_turns`
- `graph_queries`
- `grep_calls`
- `read_calls`
- `unique_files_read`
- `time_to_first_relevant_evidence_ms`
- `tokens_read` / `chars_read`（辅助）

### Graph utility

- `cross_layer_edge_hit_rate`
- `useful_evidence / returned_evidence`
- `resolved_edge_utilization`
- `native_exploration_avoided`

每次运行还要记录仓库 SHA、ProvenLattice commit、查询参数、候选 evidence ID 和最终答案引用，确保结果可重复审计。

## Interpretation

- A → B 的改善衡量 CodeGraph 结构关系价值；
- B → C 的改善衡量 Knowledge Evidence 和跨层关系价值；
- 只有正确性不下降且定位效率改善，才判定 R1 通过；
- Token、字符数和读取量只能作为效率证据，不能替代任务正确性；
- resolved rate 不是目标，错误 Edge 必须计入 wrong-link / wrong-path。

## Interface policy

R1 先使用 CLI / Python API：`symbol`, `callers`, `callees`, `evidence`, `document`, `related-code`, `impact`。当前实现中已稳定的命令优先复用；`document`, `related-code`, `impact` 在需要时逐步补齐。

完成 R1 前不引入 MCP。R1 结果只回答 ProvenLattice 是否有用，不决定未来 Agent 接口必须采用哪种协议。

## Implementation artifacts

Harness implementation is kept outside Core under [`experiments/retrieval-v1/`](../experiments/retrieval-v1/). The frozen brpc tasks are in `tasks/T01.json`–`T06.json`; the current report is [provenlattice-v1.0-r1-retrieval.md](benchmarks/provenlattice-v1.0-r1-retrieval.md). The report is intentionally `PENDING` until a real agent command is selected and all 18 first-pass cells are executed.

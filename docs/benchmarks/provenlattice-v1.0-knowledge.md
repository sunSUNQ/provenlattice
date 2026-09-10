# ProvenLattice V1.0 Knowledge Baseline

## Method

真实仓实验选择 B2 `apache/brpc`，commit `ae09e960c7291605dda52356cc0c2d45567fb53e`。复用并复制 V0.2 CodeGraph SQLite；没有重新运行 C/C++ Full Index，没有修改 benchmark checkout，也没有向真实仓伪造 Requirement。

统计原始数据：

- `provenlattice-v1.0-knowledge.json`
- `provenlattice-v1.0-knowledge-fixture.json`

运行脚本：`benchmarks/run_knowledge_baseline.py` 与 `benchmarks/run_knowledge_fixture.py`。

## B2 brpc result

| Metric | Result |
| --- | ---: |
| Markdown documents | 149 |
| Sections | 1,255 |
| Knowledge nodes | 1,404 |
| Explicit requirements | 0 |
| RawEvidenceLinks | 736 |
| Resolved | 80 (10.87%) |
| Ambiguous | 202 (27.45%) |
| Unresolved | 454 (61.68%) |
| Cross-layer edges | 80 |
| Knowledge index time | 26,641.66 ms |
| Peak working set | 163,143,680 bytes |
| CodeGraph DB before | 240,123,904 bytes |
| Combined DB after | 245,264,384 bytes |
| Knowledge DB growth | 5,140,480 bytes (2.14%) |

brpc 文档没有可按 V1 规则识别的显式 Requirement ID，因此 Requirement 数为 0，`requirement → code` latency 不伪造。736 条原始 anchor 中只有 80 条形成跨层边，符合“少量可信 Edge 优先于大量错误 Edge”的目标。

| Query, 30 samples | P50 | P95 |
| --- | ---: | ---: |
| resolved evidence lookup | 0.5578 ms | 1.2693 ms |
| document/section → code | 24.4154 ms | 27.2017 ms |
| cross-layer subgraph | 23.1982 ms | 26.2102 ms |

## Deterministic fixture result

初始 fixture 生成 7 个 Knowledge nodes、1 个 Requirement、6 个 RawEvidenceLinks 与 4 条跨层 Edge；状态分布为 4 resolved、1 ambiguous、1 unresolved。

只修改 Requirement 正文时：1 个文档重读、1 个 Section reprocessed、2 个 Section reused、3 个 evidence reprocessed、3 个 evidence reused，Requirement ID 不变。修改 C++ signature 时：0 个文档重读，6 个持久化 evidence 重新验证，`IMPLEMENTED_BY` 自动指向新 symbol identity。

| Query, 30 samples | P50 | P95 |
| --- | ---: | ---: |
| requirement → code | 0.1087 ms | 0.1470 ms |
| code → requirement | 0.1389 ms | 0.1790 ms |
| cross-layer subgraph | 0.2117 ms | 0.2716 ms |

## Conclusions

1. Section-level 建模在真实文档结构上成立；重复 heading 需要 occurrence suffix，这一问题已由 brpc 实测发现并修复。
2. 确定性 resolver 在无人工标注的真实文档上 resolved rate 较低，但不会把 656 条不确定 evidence 错写成 Edge。
3. Knowledge 数据使现有 240 MB CodeGraph 增长约 5.14 MB，规模增长合理。
4. Fixture 的 Full/Incremental 与 Overlay materialization parity 均通过。
5. 进入下一阶段前没有 Knowledge correctness blocker；性能侧最明确的后续项，是用 changed symbol/name 索引替代代码 generation 变化后的全 evidence refresh，并优化当前 document-to-code/subgraph 查询的全视图合成成本。

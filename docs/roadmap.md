# ProvenLattice Standalone Roadmap

## Product boundary

ProvenLattice 是面向 Code Agent 的独立工程证据基础设施，不是 TASCO 的上下文压缩组件。两个项目分别维护版本、接口、数据模型和实验结论；在两者各自成熟前，不安排组合实验，也不让 ProvenLattice 的研发依赖 TASCO。

ProvenLattice 的核心问题是：代码在哪里、谁依赖谁、为什么这样设计、哪个需求对应哪段代码、谁修改过它、哪个版本包含它、以及运行时错误可能指向哪里。

## Version line

| Version | Scope | Status |
| --- | --- | --- |
| Core V0.4 | Branch / Session Overlay | Complete |
| V1.0 | Knowledge Layer / Cross-Layer Evidence | Complete |
| V1.0-R1 | Standalone Retrieval Qualification | Next |
| V1.1 | Commit / ChangeSet / Version Evidence | Planned |
| V1.2 | Runtime / Log / Validation Evidence | Planned |
| V1.3 | Unified Engineering Evidence Query | Planned |
| V1.4 | Large-scale / Multi-branch Qualification | Planned |
| V2.0 | Standalone Agent-facing ProvenLattice | Planned |

## V1.0-R1

目标：验证 CodeGraph + Knowledge Layer 能否在真实工程任务中提高 Code Agent 的工程证据定位效率和准确性。

只比较三个条件：

```text
A  Native Code Agent
B  Code Agent + ProvenLattice CodeGraph
C  Code Agent + ProvenLattice CodeGraph + Knowledge Evidence
```

不引入 TASCO 对照组，不要求 MCP，不提前锁定 Agent 接口。第一阶段使用稳定 CLI / Python Query API；接口选择由 R1 的使用证据决定。

任务应来自真实仓库文档，例如：根据连接管理文档定位实现该行为的核心代码，并解释其模块关系。不得为提高 Knowledge 命中率伪造 Requirement 或文档关系。

### Metrics

Correctness：

- task success
- evidence correctness
- wrong-link / wrong-path rate

Retrieval efficiency：

- tool turns
- Graph queries
- grep calls
- read calls
- unique files read
- time to first relevant evidence
- tokens / chars read（辅助指标）

Graph utility：

- cross-layer edge hit rate
- useful evidence / returned evidence
- resolved-edge utilization
- native exploration avoided

R1 的结论必须同时报告任务成功率和错误路径；单独减少读取量或 Token 不足以证明 ProvenLattice 有价值。

## Later layers

V1.1–V1.3 依次扩展 ChangeSet/Version、Runtime/Log/Validation 和统一证据查询，但每一层都必须保持可独立运行和可独立评估。V1.4 才评估大规模、多分支 qualification；V2.0 再冻结面向 Agent 的长期接口形态。

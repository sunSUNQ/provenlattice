# ProvenLattice

**A Provenance-aware Layered Engineering Evidence Graph for Code Agents**

ProvenLattice 是一个面向 Code Agent 的研究型工程上下文与证据图项目。

项目希望探索：如何将代码仓库中的结构信息，与规范、文档、开发历史和运行时信息进行关联，为 Code Agent 提供更加结构化、可追溯、面向任务的工程上下文。

## Motivation

当前 Code Agent 主要通过文件读取、代码搜索和工具调用理解大型代码仓库。

随着代码规模和工程复杂度增加，这种方式容易带来：

* 大量重复搜索与文件读取
* 跨文件、跨模块关系定位成本较高
* 代码与需求、设计、历史信息相互割裂
* Agent 上下文快速膨胀
* 大型仓库中的任务探索路径较长

ProvenLattice 希望探索一种新的工程上下文组织方式：

> 将软件工程中的多源信息组织成可查询、可追溯的分层证据结构，并为 Code Agent 提供任务相关的最小必要上下文。

## Research Direction

当前主要关注以下方向：

* 大规模代码结构建模
* 分层工程信息组织
* 跨层工程证据关联
* 增量图更新
* 多版本与多人协作场景
* 面向 Code Agent 的结构化检索
* Graph-guided Context Retrieval
* Code Agent 工程证据检索质量与效率

## Vision

ProvenLattice 希望让 Code Agent 面对的不再只是：

```text
Files + Text
```

而是一个能够表达工程关系与演化信息的：

```text
Structured Engineering Context
```

最终探索：

> **更少搜索、更短任务路径、更高信息密度，以及更低的 Agent 上下文成本。**

Token、读取字符数和工具轮次在实验中作为检索效率的辅助观测指标，不是 ProvenLattice 的独立产品职责。

## Standalone Roadmap

ProvenLattice 与 TASCO 是两个独立工具。ProvenLattice 的版本、接口和实验不依赖 TASCO；未来如有组合实验，将在两个工具各自完成独立验证后另行定义。

```text
Core V0.4  Branch / Session Overlay                         ✅
V1.0      Knowledge Layer / Cross-Layer Evidence            ✅
V1.0-R1   Standalone Retrieval Qualification                 next
V1.1      Commit / ChangeSet / Version Evidence
V1.2      Runtime / Log / Validation Evidence
V1.3      Unified Engineering Evidence Query
V1.4      Large-scale / Multi-branch Qualification
V2.0      Standalone Agent-facing ProvenLattice
```

R1 只比较 Native Code Agent、Code Agent + ProvenLattice CodeGraph、Code Agent + ProvenLattice CodeGraph + Knowledge Evidence。当前优先稳定 CLI / Python Query API，再根据实验证据决定是否需要 MCP、Plugin 或 SDK。

## V1.0 Knowledge Layer

V1.0 在已冻结的 Core V0.4 上加入最小 Knowledge Layer，将 Markdown Spec、Requirement、Architecture 与 Document Section 复用同一套 Node / Edge / Overlay contract 接入 CodeGraph：

```text
scan -> parse -> graph -> shard -> SQLite -> query -> incremental update
```

V0.1 将语法引用持久化为 RawReference，明确区分 `resolved`、`ambiguous` 与 `unresolved`；只有证据充分的 resolved reference 才形成 Edge。V0.2 增加 `.h/.hpp/.c/.cc/.cpp` 等 C/C++ adapter，保守提取 namespace、class/struct、function/method、typedef/using、include 与 call expression，并保持 Full/Incremental parity。宏、模板实例化、虚调用与复杂重载允许保留 ambiguous/unresolved。

V0.4 的 Overlay SQLite 只保存 ADD/UPDATE/DELETE delta 与 tombstone；`GraphView` 统一按 Session > Branch > Base 合成查询，并提供 stale/rebase、session commit/discard、entity/boundary conflict detection 与 Full Materialization parity。V1.0 进一步把 Knowledge Node、Cross-layer Edge 与 RawEvidenceLink 纳入同一 Overlay。

Knowledge Layer 只使用显式 requirement ID、文件路径、qualified symbol 和 module anchor 等确定性证据。每条原始证据均保留 `resolved / ambiguous / unresolved`、候选、策略、provenance 与 confidence；只有唯一 resolved 证据生成跨层 Edge。当前不包含语义/Embedding/LLM linker。

V1.0 架构与 contract 见 [docs/design-v1.md](docs/design-v1.md)，V1.0-R1 实验契约见 [docs/design-v1-r1.md](docs/design-v1-r1.md)，完整路线见 [docs/roadmap.md](docs/roadmap.md)，R1 Harness 见 [experiments/retrieval-v1/README.md](experiments/retrieval-v1/README.md)，当前 qualification 状态见 [docs/benchmarks/provenlattice-v1.0-r1-retrieval.md](docs/benchmarks/provenlattice-v1.0-r1-retrieval.md)，真实仓结果见 [docs/benchmarks/provenlattice-v1.0-knowledge.md](docs/benchmarks/provenlattice-v1.0-knowledge.md)。V0.x 设计仍保留在 [docs/design-v0.md](docs/design-v0.md)。

### Quick start

```bash
python -m pip install -e .
provenlattice index /path/to/repo --json
provenlattice knowledge /path/to/repo --json
provenlattice status --database /path/to/repo/.provenlattice/codegraph.db --json
provenlattice symbol run --database /path/to/repo/.provenlattice/codegraph.db --json
provenlattice implemented REQ-RECOVERY-001 --database /path/to/repo/.provenlattice/codegraph.db --json
provenlattice evidence --status unresolved --database /path/to/repo/.provenlattice/codegraph.db --json
provenlattice update /path/to/repo --json
```

运行测试和完整 demo：

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python examples/demo/run_demo.py
```

Windows PowerShell 中先执行 `$env:PYTHONPATH='src'`。

## Status

🚧 **Research / V1.0-R1 Retrieval Harness**

当前实现覆盖 Python/C/C++ CodeGraph，以及 Markdown Spec/Requirement/Document 到代码的可追溯确定性证据。Runtime Log、Commit History、Validation Result、Embedding、Vector DB、LLM linker、MCP、UI、TASCO 与 Agent 集成均未引入。

---

**ProvenLattice**

*Provenance-aware Layered Engineering Evidence Graph for Code Agents*

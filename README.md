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
* Code Agent 上下文效率与 Token 成本优化

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

## Core V0.4

Core V0.4 已经支持 Python、C 与 C++ 仓库的本地 CodeGraph 闭环，并在 V0.3 的 Shard/Impact Foundation 上增加 Base + Branch Overlay + Session Overlay：

```text
scan -> parse -> graph -> shard -> SQLite -> query -> incremental update
```

V0.1 将语法引用持久化为 RawReference，明确区分 `resolved`、`ambiguous` 与 `unresolved`；只有证据充分的 resolved reference 才形成 Edge。V0.2 增加 `.h/.hpp/.c/.cc/.cpp` 等 C/C++ adapter，保守提取 namespace、class/struct、function/method、typedef/using、include 与 call expression，并保持 Full/Incremental parity。宏、模板实例化、虚调用与复杂重载允许保留 ambiguous/unresolved。

V0.4 的 Overlay SQLite 只保存 ADD/UPDATE/DELETE delta 与 tombstone；`GraphView` 统一按 Session > Branch > Base 合成查询，并提供 stale/rebase、session commit/discard、entity/boundary conflict detection 与 Full Materialization parity。

架构与 contract 见 [docs/design-v0.md](docs/design-v0.md)，开源技术选择见 [docs/open-source-survey.md](docs/open-source-survey.md)，V0.3 Shard 基线见 [docs/benchmarks/provenlattice-v0.3-shard.md](docs/benchmarks/provenlattice-v0.3-shard.md)，V0.4 Overlay 基线见 [docs/benchmarks/provenlattice-v0.4-overlay.md](docs/benchmarks/provenlattice-v0.4-overlay.md)。

### Quick start

```bash
python -m pip install -e .
provenlattice index /path/to/repo --json
provenlattice status --database /path/to/repo/.provenlattice/codegraph.db --json
provenlattice symbol run --database /path/to/repo/.provenlattice/codegraph.db --json
provenlattice update /path/to/repo --json
```

运行测试和完整 demo：

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python examples/demo/run_demo.py
```

Windows PowerShell 中先执行 `$env:PYTHONPATH='src'`。

## Status

🚧 **Research / Core V0.4**

当前实现专注最小、可扩展的 Python/C/C++ CodeGraph；Spec、Log、Commit、Embedding、MCP、UI、TASCO 与 Agent 集成等能力尚未开始。

---

**ProvenLattice**

*Provenance-aware Layered Engineering Evidence Graph for Code Agents*

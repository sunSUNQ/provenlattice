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

## Status

🚧 **Research / Early Exploration**

项目目前处于早期研究与设计阶段，后续将逐步开放原型、实验和技术文档。

---

**ProvenLattice**

*Provenance-aware Layered Engineering Evidence Graph for Code Agents*

# ProvenLattice Core V0 开源方案调研

调研日期：2026-09-09。结论基于各项目官方仓库、规范和 API 文档；只复用依赖库及可迁移的架构思想，不复制项目实现。

## 对比

| 能力 | Tree-sitter | Codebase Memory MCP | codegraph | SCIP | ProvenLattice 选择 |
| --- | --- | --- | --- | --- | --- |
| Parser | 增量 CST 与多语言 grammar | vendored grammar 的多语言结构抽取 | Tree-sitter extraction kernel + language extractor | 不负责解析 | 直接使用官方 binding/grammar；每语言独立 extractor |
| Incremental Parse | old tree、tree edit、changed ranges | watcher 驱动重新索引 | watcher debounce + incremental sync | 不涉及 | 暴露 old-tree/changed-range 接口；V0 持久层按文件 hash 增量 |
| Symbol Identity | 只提供语法位置 | 项目内部实体标识 | 项目内部 node 标识 | package + descriptor path + overload disambiguator | 借鉴 SCIP descriptor 层级，以 repo/path/kind/qualified-name/signature 形成稳定 ID |
| Node / Edge | 无统一语义图模型 | 持久 knowledge graph | symbol/edge/file graph | SymbolInformation、Occurrence、Relationship | 保留 ProvenLattice Node/Edge contract、provenance/generation/metadata |
| Reference Resolution | 只识别 call/import 语法，不绑定定义 | Tree-sitter 后加 Hybrid LSP/refinement | extraction 后解析 call/import/inheritance/framework | 编译器 indexer 输出已绑定 symbol | 独立 `ReferenceResolver`：same-file、import、qualified、unique-name |
| Storage | 无 | 本地 SQLite/WAL | 本地 SQLite + FTS5 | protobuf/index exchange format | SQLite 原位当前快照 + generation 发布记录 |
| Incremental Index | 提供单文档增量语法树 | watcher + incremental graph | file watcher + sync | indexer 自行决定 | hash 变化 → 仅重解析变化文件 → graph delta → shard fingerprint |
| Query | CST Query pattern | Agent/MCP 图查询 | callers/callees/impact/context | 消费者实现 | 结构化 GraphQuery，子图强制 hops/nodes 上限 |
| Agent Interface | 无 | MCP tools | CLI/MCP/context builder | LSP/代码智能生态交换 | V0 仅 CLI JSON；MCP 延后 |

## 1. Tree-sitter

### 直接复用

- 官方 `tree-sitter` Python binding 与 `tree-sitter-python` grammar。
- CST、容错解析、节点 byte/point range、field name、Tree Query。
- `Parser.parse(new_source, old_tree)`、`Tree.edit` 与 `Tree.changed_ranges` 提供的进程内增量解析能力。官方 C API 明确要求先以精确 edit 更新旧树，再将其传给下一次 parse；changed ranges 表示语法层级结构改变的范围。

### 借鉴

- grammar-specific query/extractor 与语言无关 graph core 分离。
- changed ranges 可在未来常驻 watcher 中缩小 extractor 重跑范围。

### 不采用

- 不把 CST node 直接作为持久 Node，也不把 byte/line range 当永久 identity。
- V0 CLI 跨进程不会序列化 Tree-sitter tree；因此当前持久增量粒度仍是单文件，而不是 changed-range graph patch。

### 原因

Tree-sitter 是可靠的语法基础，但它并不建立类型、导入环境或动态调用语义。官方 binding 同时提供 grammar wheel、tree editing、changed ranges 与 query pattern，适合成为 ParserAdapter 的底层实现，而不是整个 CodeGraph。[Tree-sitter repository](https://github.com/tree-sitter/tree-sitter)；[Python binding usage](https://github.com/tree-sitter/py-tree-sitter)；[C API](https://github.com/tree-sitter/tree-sitter/blob/master/lib/include/tree_sitter/api.h)

## 2. Codebase Memory MCP

### 直接复用

- 不直接链接其二进制或复制源码；项目功能范围远大于 V0。

### 借鉴

- Tree-sitter 语法 pass 与语义 refinement pass 的两层结构。
- 本地 SQLite、文件发现、watcher、结构化 Agent 查询的工程经验。
- unresolved call 保守降级，而不是伪造高置信度边。

### 不采用

- MCP、3D UI、Embedding、Cypher、HTTP route、Hybrid LSP 全套、共享压缩 graph artifact 和大量语言 grammar。

### 原因

该项目明确说明 Tree-sitter pass 负责 definitions/calls/imports，而 Hybrid LSP pass 使用 import graph 与 definition registry 改进绑定；这验证了 ProvenLattice 必须拆分 parsing/resolution。其 SQLite/WAL 与 watcher 设计值得后续采用，但当前阶段不应引入其产品层复杂度。[Codebase Memory MCP repository](https://github.com/DeusData/codebase-memory-mcp)

## 3. colbymchenry/codegraph

### 直接复用

- 不复制实现；保留其 MIT 项目作为工程行为参照。

### 借鉴

- `files → extraction → SQLite → resolution → query` 分层 pipeline。
- full index / sync 两条入口、callers/callees、文件事件 debounce、SQLite 索引与 staleness 防护思路。
- reference resolver 在 extraction 之后解析 call、import 与 inheritance。

### 不采用

- MCP、UI、ContextBuilder、framework synthesizer、影响测试选择、FTS5 和 daemon。

### 原因

其官方说明明确把 extraction、storage、resolution、auto-sync 分成四步，并采用本地 SQLite；这一边界适合 Core V0。ProvenLattice 仍需独立加入 shard、boundary dependency、API fingerprint、evidence provenance 和 graph generation。[codegraph repository](https://github.com/colbymchenry/codegraph)

## 4. SCIP

### 直接复用

- V0 不直接采用 protobuf schema，也不要求 SCIP wire compatibility。

### 借鉴

- 全局 symbol 与 document-local symbol 的区分。
- package identity、从外到内的 descriptor path、method disambiguator。
- SymbolInformation 与 Occurrence 分离；definition/reference/implementation relationship 不混为一种边。

### 不采用

- 完整协议、package manager/version 强制字段、所有 Kind、position encoding 和 index exchange machinery。

### 原因

SCIP 的 symbol grammar 要求 descriptor 链形成包内 fully-qualified name，并给 method 提供 disambiguator；这正适合指导 overload、nested symbol 与 local symbol 的稳定标识。ProvenLattice 用较小的 canonical tuple 实现同一思想，并保留未来接收 SCIP symbol 的 metadata 扩展点。[SCIP specification](https://github.com/scip-code/scip/blob/main/docs/scip.md)

## ProvenLattice V0 决策

### Parser 与 Resolver 边界

```text
TreeSitterParser
  └─ PythonExtractor
       ├─ ParsedSymbol
       ├─ ParsedImport
       └─ ParsedReference
                 ↓
         ReferenceResolver
                 ↓
              Node / Edge
```

Tree-sitter 可靠提取 declaration、lexical nesting、signature text、import/include syntax、call expression、inheritance syntax和 source range。调用目标、继承目标、别名、重导出、动态分派、泛型实例化和跨语言链接不是纯语法事实，必须由 ReferenceResolver、LSP、compiler index 或 SCIP 补全。

### Stable Symbol Identity

V0 canonical identity：

```text
repository-id / relative-path / kind / qualified-name / normalized-signature
```

- overload：signature 是 disambiguator。
- nested class/method：qualified name 包含完整 lexical owner chain。
- anonymous/local symbol：V0 不建图；未来使用 enclosing stable symbol + local structural ordinal/hash。
- rename/move：V0 视为 remove + add；未来用 commit/SCIP/结构相似度建立 identity alias，不污染基础 ID。

### 增量与一致性

Tree-sitter 支持进程内 old-tree reuse 与 changed ranges；当前 CLI 索引以文件 hash 判断变化，只重新解析新增/修改文件。持久 parser facts 使 resolver 可在不重解析未变文件的情况下重算绑定。Full(B) 与 Incremental(A→B) 必须继续比较 nodes、edges、shards 与 boundary edges。

### ProvenLattice 的重设计

相比参考项目，V0 自有并保持独立的部分是：ShardStrategy、internal/boundary edge、API fingerprint、boundary_dirty、graph generation，以及每条 Edge 的 provenance/confidence。Node/Edge 的开放 kind/type/metadata 能容纳未来 Spec、Document、Log、Commit 等跨层节点；这些 future kinds 不依赖 Tree-sitter，也不会要求修改 GraphQuery/Storage 的基础 contract。

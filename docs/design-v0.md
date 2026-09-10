# ProvenLattice Core V0 设计

## 范围

V0 只建立 Python 源码到本地 CodeGraph 的完整闭环：扫描、解析、符号与关系抽取、分片、SQLite 持久化、查询以及单文件级增量更新。Spec、文档、提交历史、运行时信息、向量检索和 Agent 集成都不在本阶段范围内。

## 模块与依赖

- `scanner`：遍历仓库、过滤工具目录并计算文件内容哈希。
- `parsing`：`ParserAdapter` 隔离 parser runtime，当前用 Tree-sitter Python grammar 提取类、接口、函数、方法、类型、导入、调用与引用候选；不生成 ID。
- `resolver`：把语法层的 import/reference 候选按 same-file、import、qualified-name、unique-name 顺序绑定到图节点。
- `identity`：集中生成稳定的 repository、path、symbol、edge 与 shard ID。符号 ID 基于仓库标识、相对路径、kind、qualified name 和 signature，不依赖行号。
- `graph`：把 parser 产生的候选解析为 Node/Edge，创建目录/文件层级并解析跨文件关系。
- `shard`：默认按前两级目录划分 shard，分类 internal/boundary edge，并计算公共 API fingerprint。策略通过一个小接口替换。
- `storage`：SQLite schema、事务和图快照读写，不包含查询语义。
- `incremental`：比较 `file_state`，只重新读取和解析新增/修改文件，删除失效文件，再从持久化的关系候选重建关系和 shard 汇总。
- `query`：在 storage 上提供有界图查询。
- `cli`：结构化命令入口，支持文本和 `--json` 输出。

依赖方向为：`cli -> incremental/graph/query -> scanner/parsing/resolver/identity/shard/storage`。数据模型是共享的叶子模块，storage 和 query 解耦。

## 数据流

```text
Repository -> Files -> Parser -> Symbols -> Relations -> Shards -> SQLite -> Query
```

全量索引在单个事务中发布新 generation。增量索引比较文件哈希，只解析变化文件，生成 node/edge delta，重算受影响后的全局静态关系、shard 计数与 API fingerprint；fingerprint 改变时标记 `boundary_dirty`，但不递归重建依赖 shard。

## 技术选择

- 语言：Python 3.11+。适合研究原型，标准库完整，启动与测试成本低。
- Parser：V0 使用官方 Tree-sitter Python binding 与 Python grammar。它提供容错 CST、query、old-tree reuse 和 changed ranges；language extractor 与 resolver 独立，后续增加语言不修改 graph core。
- Storage：SQLite。单文件、事务化、索引成熟，足够支撑本地研究与可重复测试。
- Graph：持久化的 property graph；node/edge 表加 JSON metadata，允许增加 kind、relation 和 provenance。
- CLI：`argparse`，无需运行时依赖，所有命令支持 JSON。
- Test：`unittest`，标准库即可运行；fixture 使用真实的小型 Python 模块。

## Contract

### Node

`id, kind, repo_id, shard_id, file_id, name, qualified_name, language, start_line, end_line, signature, source_hash, generation, metadata`

Kinds：`Repository, Directory, File, Class, Interface, Function, Method, Type`。稳定 symbol ID 的 canonical input 是：`repo_id + relative_path + kind + qualified_name + signature`。

### Edge

`id, src_id, dst_id, type, provenance, confidence, generation, metadata`

V0 关系为 `CONTAINS, DEFINES, CALLS, IMPORTS, REFERENCES, IMPLEMENTS`。metadata 中的 `scope` 标识 `internal` 或 `boundary`。

V0.1 起只有 `resolved` reference 可以形成语义 Edge。Edge provenance 按证据来源区分为 `tree_sitter_syntax`、`same_file_resolution`、`qualified_name_resolution`、`import_resolution`、`unique_imported_symbol_resolution` 和 `unique_symbol_resolution`；启发式越弱，confidence 越低。

### RawReference

`id, repo_id, file_id, owner_symbol_id, raw_name, reference_type, target_module, start_line, end_line, status, candidate_symbols, resolved_symbol_id, resolution_strategy, provenance, confidence, generation, metadata`

`status` 严格为 `resolved / ambiguous / unresolved`。RawReference 保存“代码中出现了引用”这一语法事实；它不等价于关系边。索引覆盖 `raw_name`、`file_id`、`owner_symbol_id` 与 `resolved_symbol_id`，使 symbol 集合变化后可以直接定位潜在受影响引用。

### Shard

`shard_id, repo_id, path, nodes_count, edges_count, public_symbols, api_fingerprint, generation, boundary_dirty`

公共 API fingerprint 对排序后的公开符号 kind、qualified name 与 signature 做 SHA-256。

## SQLite Schema

- `repositories(repo_id PK, root_path, name, current_generation, metadata)`
- `files(file_id PK, repo_id, shard_id, path, language, source_hash, generation)`
- `shards(shard_id PK, repo_id, path, nodes_count, edges_count, public_symbols, api_fingerprint, generation, boundary_dirty)`
- `nodes(id PK, kind, repo_id, shard_id, file_id, name, qualified_name, language, start_line, end_line, signature, source_hash, generation, metadata)`
- `edges(id PK, src_id, dst_id, type, provenance, confidence, generation, metadata)`
- `raw_references(id PK, repo_id, file_id, owner_symbol_id, raw_name, reference_type, target_module, range, status, candidate_symbols, resolved_symbol_id, resolution_strategy, provenance, confidence, generation, metadata)`
- `file_state(file_id PK, path, source_hash, generation)`
- `graph_generation(repo_id, generation, created_at, mode, metrics, PK(repo_id,generation))`
- `overlay_metadata(overlay_id PK, overlay_type, repository_id, base_commit, base_generation, branch_name, parent_overlay_id, status, created_at, updated_at)`
- `overlay_deltas(overlay_id, entity_type, entity_id, operation, base_version, new_value, generation, PK(overlay_id,entity_type,entity_id))`

索引覆盖 qualified name、file、shard 以及 edge 的 source、destination、type。当前图采用原位快照；`graph_generation` 保留每次发布记录，为未来版本快照/overlay 留出演进点。

V0.4 中 Base Graph 保持共享只读；Branch/Session Overlay 使用独立小型 SQLite，仅保存 Node、Edge、RawReference、Shard 和 BoundaryEdge 的 ADD/UPDATE/DELETE。DELETE 是 tombstone。所有查询统一经过 `GraphView`，按 Session > Branch > Base 覆盖，不在各 Query 中重复 merge 逻辑。Overlay 同时绑定 base commit 与 generation，不匹配时进入 `REBASE_REQUIRED`。

## 查询与安全边界

Query API 提供 `find_symbol`, `get_definition`, `get_callers`, `get_callees`, `get_references`, `get_dependencies`, `get_dependents` 和 `get_subgraph`。子图同时强制 `max_hops` 与 `max_nodes`，并返回当前 `graph_generation`。

## 增量一致性

文件 metadata 持久化 parser 产生的关系候选。增量时仅重解析哈希变化的文件；变化文件中的 references 会重新解析，symbol identity 的新增/删除集合则转换为 name 集合，再通过 `raw_references(raw_name)` 索引定位其他文件中的潜在受影响引用，其余 resolution record 直接复用。测试以 Revision B 的全量结果与 A→B 增量结果比较 Nodes、Edges、RawReferences、Shards 和 Boundary Edges，忽略 generation、计时和数据库路径等非确定字段。

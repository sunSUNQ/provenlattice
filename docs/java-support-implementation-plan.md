# PL-JAVA-SUPPORT-P0-P1 — Java 语言支持实施计划

**状态：`P1_FIXED — READY_FOR_T8_REVIEW`**（P1 定向修复完成并通过 442 全量验证；等待 T8 复审解除阻断，见附录 D）
**审查基线：** main @ `42c6d89`（ProvenLattice 1.4.0）
**本文所有模块路径均来自实际源码**，行号以当前 main 为准（后续提交可能漂移，符号名为准）。
**实施基树：** 仅 `src/provenlattice/`（`pyproject.toml:22` 指定 `where = ["src"]`）。仓库根部的 `provenlattice/`、`proventlattice/` 为陈旧副本（与 `src/` 有 30 个文件 MD5 不一致），**不读、不改、不发布**，已列入风险项 R7。
**评审决议与 T0 记录：** 见"评审决议记录（v1.1）"与"附录 A：T0 冒烟记录"。

---

## 目录

- Step 0 源码审查（路径级架构图 + Java 接入点清单）
- Step 1 Java 前端设计（含 schema 映射表）
- Step 2 语义后端选型（SCIP Java / JavaParser / JDT 对比报告 + 对照基准）
- Step 3 第一阶段验收矩阵（J1–J11）
- 第一阶段实现任务清单与风险项
- 评审决议记录（v1.1）
- 附录 A：T0 冒烟记录
- 附录 B：T1–T3 执行记录
- 附录 C：T8 独立工程评审记录
- 附录 D：P1 定向修复记录
- 最终状态声明

---

# Step 0 源码审查

## 0.1 端到端调用链（路径级架构图）

```text
┌─ L5 Exposure ─────────────────────────────────────────────────────────────┐
│ cli.py:main (cli.py:280) → build_parser (cli.py:44) → run (cli.py:150)   │
│ MCP 透明桥接（零语言感知）：                                                │
│   experiments/context_bundle_v0/formal_harness/provenlattice_mcp_server.py│
│   tools/call → subprocess [python -m provenlattice, ...] (61–66 行)      │
│   契约冻结: .../d9-c8/d9-c8-a-native-tool-exposure-contract.json         │
└──────────────┬───────────────────────────────────────────────────────────┘
               │
┌─ L1 Foundation Graph（默认 index/update，语言无关外壳）──────────────────┤
│ index  (cli.py:158) → graph.full_index (graph.py:174)                   │
│   1) scanner.scan_repository (scanner.py:48)                            │
│      · SUPPORTED_EXTENSIONS (scanner.py:29) ← 【接入点 ①】               │
│      · IGNORED_DIRS (scanner.py:8)；content_hash=sha256 (scanner.py:44) │
│   2) parser.parse_file_with_diagnostics (parser.py:29)                  │
│      └ parser_for_language (parser.py:10, lru_cache(3)) ← 【接入点 ②】   │
│          ├ TreeSitterParser (parsing/tree_sitter.py:14)                 │
│          │   └ PythonExtractor (parsing/python.py:18)                   │
│          └ CppTreeSitterParser (parsing/cpp.py:347)                     │
│              └ CppExtractor (parsing/cpp.py:27)                         │
│   3) graph.build_graph (graph.py:56)                                    │
│      · Repository/Directory/File 节点 + CONTAINS (79–129)               │
│      · 符号节点 + DEFINES，重复折叠 duplicate_sites (130–150)            │
│      · ReferenceResolver.resolve (resolver.py:27) ← 三态，语言无关       │
│      · 边去重排序 (167–169)；shard.build_shards (shard.py:112) (170)     │
│   4) storage.replace_snapshot (storage.py:200, mode="full")             │
│ update (cli.py:160) → incremental.incremental_update (incremental.py:17)│
│   · source_hash 差异 (38–46)；未变文件走 parser 缓存 (75–79)             │
│   · 符号事实 XOR → 受影响引用集 (81–107，kind 集合在 :86)                │
│   · impact.compute_impact_frontier (impact.py:17)                       │
│   · replace_snapshot(mode="incremental") (199–203)                      │
└──────────────┬───────────────────────────────────────────────────────────┘
               │
┌─ L3/L4 查询面（完全语言无关，Java 落库即生效）─────────────────────────── ┤
│ query.GraphQuery (query.py:56)：                                        │
│   symbol→find_symbol(:213, SYMBOL_KINDS :16)  definition→:279           │
│   callers→:335  callees→:338  references→:341                           │
│   raw_references→:344  call_semantics→:368                              │
│   task_context (query.py:812; CLI :202–214, 6000 字节截断 :796)          │
│ evidence 契约: evidence.py EvidenceBundle；knowledge.py:172 知识层       │
└──────────────┬───────────────────────────────────────────────────────────┘
               │
┌─ L2 可选分析（按 Capability×Scope，默认关闭）───────────────────────────  ┤
│ analysis.py CAPABILITY_CONTRACT (analysis.py:90)  ← 【接入点 ⑥：Phase 1  │
│ orchestrator.analyze_scope (orchestrator.py:169)      不触碰】            │
│   _parse_features fail-closed (:98)  _inventory (:138, 用 scanner 扩展集)│
│ materializer: analysis_ast/analysis_cfg/analysis_c_* → AnalysisStore     │
│   (analysis.py:345；复合主键 (id, feature)，ANALYSIS_SCHEMA :14–48)      │
└──────────────────────────────────────────────────────────────────────────┘
```

**审查更正（与任务书假设的差异，如实报告）：**
1. **CLI 没有 `impact` 子命令。** `impact.py` 只有 `compute_impact_frontier(impact.py:17)`，是增量更新的内部部件（唯一调用方 `incremental.py:149`），无 CLI 面。符号级影响分析目前由 `callers`/`subgraph` 承担。
2. **`task-context` 不在 `knowledge.py`**，而在 `query.py:812`（`GraphQuery.task_context`）；`knowledge.py` 是 `knowledge` 命令（知识层索引）的后端。
3. **增量 fresh/staleness 有两层：** L1 = `file_state` 表的 sha256 `source_hash` 对比（`incremental.py:38–46`，`scanner.py:44`）；L2 分析缓存 = `analysis.py:183` `dependency_staleness()` + `:373` `is_analysis_fresh`。`dependency_staleness` 不在 `incremental.py`。
4. 数据库迁移无 schema_version 表：`CREATE TABLE IF NOT EXISTS` 重放 + 定向回填（`storage.py:106–117` shard_edges 回填；`analysis.py:215–254` 复合主键迁移）。

## 0.2 Foundation Graph schema 与稳定 ID（Java 必须原样复用）

**节点/边模型**（`models.py`）：
- `Node`（models.py:7–25）：`id, kind, repo_id, shard_id, file_id, name, qualified_name, language, start_line, end_line, signature, source_hash, generation, metadata`。
- `Edge`（models.py:28–40）：`id, src_id, dst_id, type, provenance="static_analysis", confidence=1.0, generation, metadata`。
- L1 边类型为冻结契约（docs/design-v0.md）：`CONTAINS / DEFINES / CALLS / IMPORTS / REFERENCES / IMPLEMENTS`。
- `RawReference`（models.py:276–297）：三态 `status`，CHECK 约束 `('resolved','ambiguous','unresolved')`（storage.py:50）。

**SQLite 表**（storage.py:12–96）：`repositories, files, shards, nodes, edges, shard_edges, raw_references, raw_evidence_links, document_state, file_state, graph_generation`；数据库文件 `<repo>/.provenlattice/codegraph.db`（graph.py:180）。

**稳定 ID**（identity.py，`_stable` :7–9：`"<prefix>:<sha256(\x1f 连接的 parts)>"`）：

| ID | 函数 | 输入 |
|---|---|---|
| symbol | `symbol_id`（identity.py:74） | repo_id, relative_path, **kind, qualified_name, signature** |
| edge | `edge_id`（:91） | src_id, dst_id, edge_type, discriminator |
| raw reference | `raw_reference_id`（:99） | repo_id, file_id, owner_symbol_id, reference_type, raw_name, **ordinal** |
| file/directory | `path_id`（:16） | repo_id, kind, relative_path |

> 关键推论：**重载方法（同 qualified_name、不同 signature）自动获得不同 symbol_id**——Java 重载的多节点共存无需改动任何 ID 机制。

**kind 集合的三处硬编码**（决定 Phase 1 的 kind 复用策略）：
- `query.py:16` `SYMBOL_KINDS = ("Namespace","Class","Struct","Interface","Function","Method","Type")`
- `shard.py:105` 指纹 kind 集（同集合）
- `incremental.py:86` 符号变化检测 kind 集（多一个 `"File"`）

## 0.3 前端注册与解析流程

- 前端契约是 `typing.Protocol`（**无 ABC、无注册表**）：`parsing/base.py:17–25`，需类属性 `language`/`extensions` + `parse()` + `parse_bytes(source, relative_path, old_tree=None) -> ParseOutcome`。
- 注册 = 手工导入导出：`parsing/__init__.py`（5 行）+ `parser.py:10–18` 的 if/elif 分派（`lru_cache(maxsize=3)`）。
- 语言检测 = 扁平字典：`scanner.py:29–33` `SUPPORTED_EXTENSIONS`（`.py/.pyi→python`；`.c→c`；`.h/.hh/.hpp/.hxx/.inc/.cc/.cpp/.cxx/.c++→cpp`）。未登记后缀被静默跳过。
- 前端产出（models.py:117–154）：`ParsedSymbol(kind, name, qualified_name, start_line, end_line, signature, public, metadata)` / `ParsedReference(source_qualified_name, type, target, target_module, metadata, start_line, end_line)` / `ParsedImport(source_qualified_name, target, module, alias, metadata)` / `ParsedFile(symbols, references, imports, parser)`。
- `ParsedFile` 全量 JSON 存入 File 节点 `metadata["parsed"]`（graph.py:121），作为增量解析缓存（`storage.parser_cache` storage.py:158）。
- 解析失败降级：`ParsedFile([], [], [], parser=f"failed:{type}")` 计入 `parse_failures`（graph.py:191）；语法错误（`tree.root_node.has_error`）计入 `syntax_error_files` 但**不中断索引**（parser.py:29–33）。

## 0.4 三态引用解析（resolver.py，语言无关）

`_resolve_reference`（resolver.py:209–255）解析阶梯（按序短路）：

| 步 | 条件 | strategy | confidence |
|---|---|---|---|
| 0 | `metadata["call_kind"]=="indirect"` → 永不按名绑定（:218–222） | `indirect_call_shape` | 0.0 |
| 3 | 同文件同名唯一 | `same_file_resolution` | 0.98 |
| 3' | 同文件同名多个 | `same_file_resolution` | 0.0（ambiguous） |
| 5 | target 命中 `by_qualified` | `qualified_name_resolution` | 0.99 |
| 6 | `target_module` 拼接命中 | `import_resolution` | 1.0 |
| 7 | import 别名（`alias or target`，:241–251）唯一 | `unique_imported_symbol_resolution` | 0.95 |
| 8 | 全局同名唯一 | `unique_symbol_resolution` | 0.75 |
| 9 | 其余 | `ambiguous` / `unresolved` | 0.0 |

- 状态字面量在 `resolver.py:309`：`resolved` 仅当选中候选；有候选未选中 = `ambiguous`；无候选 = `unresolved`。**只有 resolved 生成语义边**（`_edge_from_record` :330–343）；完整证据保留在 `raw_references`。
- 选择规则 `_select_candidate`（:257–266）：唯一 id → 取之；否则仅当"签名全部相同且恰有一个 `metadata["definition"]`"才取定义（C++ 头声明/定义合并场景）。
- 缓存失效：`CALL_KIND_VERSION`（:13）、文件变更、引用受影响、候选失效（:285–295）。
- 对 Java 的意义：**resolver 零改动**。Java 的 import/限定名/同名歧义恰好落在既有阶梯上（Step 1.5 逐形状推演）。

## 0.5 CLI 调用链（cli.py:150–277 run）

| 命令 | 后端 | Java 落库后是否自动生效 |
|---|---|---|
| `index`（:158） | `graph.full_index` | 是（经接入点①②） |
| `update`（:160） | `incremental.incremental_update` | 是（零改动，见 Step 1.7） |
| `symbol/definition/callers/callees/references`（:218–227） | `GraphQuery` 各方法 | 是（SYMBOL_KINDS 覆盖 Phase 1 kind） |
| `raw-evidence/subgraph/dependencies/dependents`（:228–251） | `GraphQuery` | 是 |
| `task-context`（:202–214） | `query.py:812` | 是 |
| `knowledge`（:162） | `knowledge.py:172` | 部分：文档反引号锚点正则（knowledge.py:73）只认 `.py/.c/.cc/.cpp/.h/.hpp`，不含 `.java`（评审决策点 T7） |
| `analyze --features …`（:164） | `orchestrator.analyze_scope` | 否（fail-closed：Java 文件报 `skipped/unsupported_language`，见 J10） |
| `analysis`（:176）/ `defect`（:189） | `analysis_query.py` / `defect_query.py`（均 fail-closed） | 否（Phase 1 无 `ast:java` 注册 → `unsupported`） |

## 0.6 增量、freshness、迁移与 provenance 契约

- **增量算法**（incremental.py:17–215）：sha256 文件差异 → 未变文件从 File 节点 `metadata["parsed"]` 缓存重建 → 符号事实（name, qualified_name）XOR 检测（:81–107）→ 受影响引用名（全名+短名，`storage.references_for_names` storage.py:188）重解析 → `build_graph` 携带缓存 → delta/impact → `replace_snapshot(mode="incremental")`。**未索引库拒绝增量**（:27–30 报错提示先 index）；无变化快速返回 `changed=False`（:47–57）。
- **provenance 记账**：`graph_generation` 表每代一行（mode = full/incremental + 完整 Metrics JSON，storage.py:74–77、:309–312）；边级 provenance = 解析 strategy（resolved）或 `tree_sitter_syntax`（未解析，resolver.py:310）；`RawReference.metadata["call_kind_version"]` 支撑引用语义版本失效。
- **契约要点**：知识层边（`metadata.layer="knowledge"`）在 replace_snapshot 中幸存（storage.py:215–217）；`test_capabilities_i0.py` 冻结 `BASE_TABLES`（默认索引不得建分析表）；L2 缓存新鲜度 fail-closed（`analysis_query.py`/`defect_query.py` 对 stale/not_built 拒答）。

## 0.7 现有回归测试与 L1 parity 验证方法（tests/，unittest 标准库，无 conftest/pytest 配置）

- **parity 惯用法**：`tests/test_cpp.py:76–107` —— 全量库与增量库四表（nodes/edges/shards/raw_references）快照（剔除 generation/boundary_dirty）逐行相等 + `files_parsed==1` + 跨 shard CALLS 边存在。同类：`test_integration.py::test_full_incremental_parity_for_required_changes`、`test_c_call_semantics.py::test_full_index_determinism_and_incremental_parity`。
- **三态断言**：`test_integration.py::test_resolution_contract_and_raw_reference_indexes`（状态/strategy/精确索引集合/非 resolved 无边）。
- **零影响断言**：分析层测试先快照基表再跑分析并断言不变（`test_ast_analysis.py::test_zero_impact_on_base_snapshot` 等）；`test_capabilities_i0.py` 冻结 BASE_TABLES 与能力元组（`("cfg:python","cfg:c")` 等）。
- **fixture 约定**：内联字符串 + `tempfile.TemporaryDirectory()` 为主；磁盘 fixture 目录（`tests/fixture_cpp/`、`tests/fixture_knowledge/`）先 `copytree` 到临时目录再使用；可选语法 skip 守卫 `@unittest.skipUnless(HAS_CPP_GRAMMARS, …)`（test_cpp.py）。
- **运行方式**：`python -m unittest discover -s tests -v`，`PYTHONPATH=src`（`.github/workflows/ci.yml`，win+ubuntu × py3.12，依赖 `pyproject.toml:11–16` + `requirements.txt` 四个 pin）。

## 0.8 Java 接入点清单（交付物 2a）

| # | 文件:行 | 现状 | Phase 1 变更 | 风险 |
|---|---|---|---|---|
| ① | `scanner.py:29–33` `SUPPORTED_EXTENSIONS` | 无 `.java` | 追加 `".java": "java"` | 极低（纯追加） |
| ② | `parser.py:10–18` `parser_for_language` | if/elif 三分支，`lru_cache(maxsize=3)` | 追加 `java` 分支；maxsize 3→4 | 低（旧分支不动） |
| ③ | `parsing/java.py`（新建） | — | `JavaTreeSitterParser` + `JavaExtractor`（实现 base.py:17–25 协议） | 中（新代码，见 §1） |
| ④ | `parsing/__init__.py` | 导出 2 个 Parser | 追加导出 | 极低 |
| ⑤ | `pyproject.toml:11–16`、`requirements.txt`、CI 两个 job 的 pip 行 | 4 个 grammar | 追加 `tree-sitter-java>=0.23,<0.24`（PyPI 最新 0.23.5，与 tree-sitter 0.26.0 同代可用性待 T0 冒烟） | 低（T0 前置验证） |
| ⑥ | `analysis.py:90` `CAPABILITY_CONTRACT` / `ANALYZER_VERSIONS` / `orchestrator.py:23` / `analysis_query.py:18–32` | 仅 python/c/cpp | **Phase 1 零改动**（Java 自动 fail-closed skip，即"默认索引零高级分析"约束的落实） | 无 |
| ⑦ | `graph.py / resolver.py / identity.py / models.py / storage.py / incremental.py / shard.py / query.py / cli.py` | — | **零改动**（kind 复用见 §1.3；增量 kind 集合 :86 已覆盖） | 无 |
| ⑧ | `knowledge.py:73` 反引号锚点后缀 | 无 `.java` | **默认不改**（决策点 T7；改则文档锚点可链接 Java 文件） | 低 |
| ⑨ | `docs/capability-matrix.md`、`docs/roadmap.md` | 无 Java 行 | 新增"Java（候选，未验证）"行；**验证级别不得高于现有 C 系行** | 无 |

---

# Step 1 Java 前端设计

## 1.1 文件检测与语言注册

- `scanner.py` 追加 `".java": "java"`。`.java` 无跨语言后缀冲突（`semantics/vocabulary.py` 的 `vocabulary_for_path` 双语言冲突检查 :387–391 仅涉及 vocabulary 语言，Phase 1 不加 `java.toml`，不触发）。
- `parser.py`：`if language == "java": return JavaTreeSitterParser()`；`lru_cache` 扩为 4。Java 分支失败行为与 C++ 相同：grammar 未安装时 `RuntimeError` → 上层记 `parse_failures`（graph.py:191），索引不崩。
- 新依赖：`tree-sitter-java>=0.23,<0.24` 进 `pyproject.toml` dependencies 与 `requirements.txt` pin（与现有 4 个 grammar 同列、同为硬依赖），CI 两个 job 同步安装。T0 冒烟（用临时 venv，不改当前环境）确认 0.23.5 与 tree-sitter 0.26.0 绑定兼容后再锁 pin。

## 1.2 Tree-sitter Java AST 解析

`parsing/java.py` 结构完全仿照 `parsing/tree_sitter.py` + `parsing/cpp.py`：

```python
class JavaTreeSitterParser:            # ParserAdapter 协议实现（parsing/base.py:17–25）
    language = "java"
    extensions = frozenset({".java"})
    def __init__(self): Language/Parser 初始化（tree_sitter_java.language()）
    def parse(self, path, relative_path) -> ParsedFile          # 委托 parse_bytes
    def parse_bytes(self, source, relative_path, old_tree=None) -> ParseOutcome
        # old_tree 增量重解析 + changed_ranges（与 tree_sitter.py:25–41 同构）
        # tree.root_node.has_error 透传 → syntax_error_files 口径一致

class JavaExtractor:                   # 仿 PythonExtractor/CppExtractor 的 CST 归一化
    # 状态: source 行索引、scope 栈、import_aliases、per-method locals 集、累加器
    def extract(self, root) -> ParsedFile
```

解析容错：tree-sitter ERROR 节点处**能提取多少提取多少**，缺失片段不产出事实（与 CppExtractor 一致），绝不编造。

## 1.3 符号提取与 kind 映射（交付物 2b：schema 映射表）

**设计原则：Phase 1 零核心改动**——只使用既有 kind（`Namespace/Class/Struct/Interface/Function/Method/Type`）。理由：(a) `query.py:16`、`shard.py:105`、`incremental.py:86` 三处硬编码集合零改动；(b) docs/design-v0.md 冻结契约不动；(c) 旧语言不变性可被平凡证明。引入 `Field/Constructor/Enum` 独立 kind 列为 Phase 2 评审项（需三集合同步 + 全量回归，见 T9/R3）。

### 1.3.1 声明 → 符号映射表

| Java 构造（tree-sitter 节点） | kind（Phase 1） | qualified_name | signature 约定 | metadata 判别符 |
|---|---|---|---|---|
| `package_declaration` | 不建符号节点 | — | — | File 节点 `metadata["java_package"]="com.foo"`（备选方案见下方注） |
| `class_declaration` | `Class` | `pkg.Outer.Inner`（点连接） | `""` | `{"java_kind":"class","definition":true}` |
| `interface_declaration` | `Interface` | 同上 | `""` | `{"java_kind":"interface","definition":true}` |
| `enum_declaration` | `Class` | 同上 | `""` | `{"java_kind":"enum","definition":true}` |
| `record_declaration` | `Class` | 同上 | `""` | `{"java_kind":"record","definition":true}` |
| `annotation_type_declaration` | `Interface` | 同上 | `""` | `{"java_kind":"annotation","definition":true}` |
| `method_declaration` | `Method` | `pkg.Type.method` | `"(PT,PT) -> RT"`（源码拼写，含泛型；varargs `PT...`） | `{"java_member":"method","static":bool,"visibility":"public/protected/private/package"}` |
| `constructor_declaration` | `Method`（名=类简名） | `pkg.Type.Type` | `"(PT,PT)"`（无返回段，与方法天然区分） | `{"java_member":"constructor", …}` |
| `compact_constructor_declaration`（record） | 同上 | 同上 | 同上 | `{"java_member":"constructor","java_kind":"record"}` |
| `field_declaration` | `Method`（C++ 先例：cpp.py:169 `field_declaration` 亦产出 Method 节点） | `pkg.Type.field` | `"Type name"` | `{"java_member":"field", …}` |
| `enum_constant` | `Method` | `pkg.Color.RED` | `"Color RED"` | `{"java_member":"enum_constant"}` |
| `object_creation_expression` 匿名类体 | **跳过**（不产出符号；体内调用不记录——诚实缺口，见 R5） | — | — | — |
| lambda / 局部类体内调用 | 归属词法外围 `Method`（与 C/C++ 提取器对内联体的既有归属一致） | — | — | — |

> **备选方案（记录供评审）**：`package_declaration` 产出 `Namespace` 节点（C++ 先例）。弃因：symbol_id 含 relative_path → 同包 N 文件产 N 个同 qualified_name 节点，污染 `by_name`/`by_qualified` 短名阶梯。Phase 1 用 File metadata + import 边承载包关系；`java_package` 同时供提取器构造 FQN。

**符号 id**：一律 `symbol_id(repo_id, relative_path, kind, qualified_name, signature)`（identity.py:74）——重载因 signature 不同而 id 不同；`public` = 非 private/protected（供 shard.py:101 指纹）。DEFINES 边 file→symbol，`provenance="tree_sitter_syntax"`（graph.py:145 既有路径）。

### 1.3.2 引用/调用/导入映射表

| Java 构造 | 产出事实 | target 规则 | call_kind | metadata |
|---|---|---|---|---|
| `import a.b.C;` | `ParsedImport(module="a.b", target="C")` + 别名表 `C→a.b.C` | — | — | `{"syntax":"import"}` |
| `import static a.b.C.m;` | `ParsedImport(module="a.b.C", target="m")` + 别名表 `m→a.b.C.m` | — | — | `{"syntax":"static_import"}` |
| `import a.b.*;` / `import static a.b.C.*;` | `ParsedImport(target="*")`，**不进别名表** | — | — | `{"wildcard":true}` → 导入边按阶梯判为 unresolved（诚实） |
| extends/implements/throws 子句 | `ParsedReference(type="IMPLEMENTS", target=父类型)`（Python 先例 python.py:114–121 对任意基类产 IMPLEMENTS） | 导入别名改写后FQN | — | `{"java_relation":"extends"|"implements"|"throws"}` |
| `foo(x)` / `<T>foo(x)` | `CALLS` | `foo`（剥泛型实参） | `direct` | `{"syntax":"method_invocation"}` |
| `obj.foo(x)` | `CALLS` | `obj.foo`（receiver 为普通标识符） | `direct` | — |
| `this.foo(x)` | `CALLS` | `foo` | `direct` | `{"java_receiver":"this"}` |
| `super.foo(x)` | `CALLS` | `super.foo` | **`indirect`**（无继承上下文不得绑定，resolver.py:218 否决→unresolved） | `{"java_receiver":"super"}` |
| `getObj().foo(x)` / `arr[i].foo(x)` | `CALLS` | 原文 | **`indirect`**（CppExtractor 同规则 cpp.py:257–285） | `{"callee_shape":"complex"}` |
| `Type.staticMethod(x)` / `pkg.Type.m(x)` | `CALLS` | 原文，别名表改写（Python 先例 python.py:165–171） | `direct` | — |
| `new Foo(x)` / `new com.foo.Foo(x)` | `CALLS`（构造调用） | `Foo` / FQN，别名改写 | `direct` | `{"syntax":"object_creation"}` |
| `Foo::bar`（method_reference） | `REFERENCES` | `Foo.bar` | `indirect` | `{"syntax":"method_reference"}` |
| 类型使用（字段/参数/返回/局部声明/泛型实参） | `REFERENCES` | 别名表改写后名称 | — | — |
| 注解使用 | `REFERENCES`（仅当 target 为限定名或命中别名表/本文件类型；`@Override` 等无处可解析的标记跳过——确定性过滤，减少噪声） | — | — | `{"syntax":"annotation"}` |
| 局部变量/参数/catch/for-each/resource 标识符 | **不产出引用**（提取器局部表过滤；同时消除"局部名误配全局同名符号"的错误候选，见 §1.5 注） | — | — | — |

## 1.4 定义、包含、引用、调用候选

- **包含**：`CONTAINS`（目录→目录/文件，graph.py:96–129）与 `DEFINES`（file→symbol，:145–150）走既有装配；成员归属由 qualified_name 表达（`pkg.Outer.Inner.method`），不新增边类型——与 C/C++ 现状一致。
- **定义/引用/调用候选**全部以 `ParsedReference` 进入 resolver 三态阶梯（§1.5）；候选集 = resolver 的 `by_qualified`/`by_name`/同文件/import 四级索引（resolver.py:45–59），零改动。

## 1.5 三态行为推演（验收矩阵的预期即由此导出）

| 场景 | 阶梯路径 | 预期 status / strategy / confidence |
|---|---|---|
| `import a.b.C;` + 未限定 `C` 使用 | import 别名（:241–251） | resolved / unique_imported_symbol_resolution / 0.95 |
| 静态导入方法裸调用 `m()` | 别名表改写 → `by_qualified["a.b.C.m"]` | resolved / qualified_name_resolution / 0.99 |
| 同包未限定类型（全局唯一） | 阶梯 8（Phase 1 **不**伪造 target_module，见下注） | resolved / unique_symbol_resolution / 0.75 |
| 两个包各有 `Helper`、无 import | 阶梯 8 多候选 | ambiguous / candidates=2 |
| `import x.Helper;` 且他包亦有 `Helper` | 别名唯一 → 阶梯 7 先于全局 | resolved / 0.95（import 消歧） |
| 同类重载调用 `obj.foo(x)` | 同文件同名 2 个（signature 不同） | ambiguous / candidates=2（L1 不做重载判定，Phase 2 语义后端课题） |
| `new com.foo.Foo()`（FQN 构造） | `by_qualified["com.foo.Foo"]` 唯一构造 | resolved / 0.99 |
| 隐式默认构造（未声明构造器） | 无符号节点 | unresolved（诚实；gap 文档化） |
| `super.foo()` / `Foo::bar` / `getObj().foo()` | call_kind=indirect 否决（:218） | unresolved / indirect_call_shape |
| `System.out.println`、`String` 等非项目名 | 阶梯走尽无候选 | unresolved（如实计入 Metrics；噪声水平由基准 J-bench 量化） |
| 通配 import 下的类型使用 | 无别名无 module | 同上（unresolved/ambiguous，视同名分布） |

> **设计决策（对评审开放）**：Phase 1 **不**为未限定引用设置 `target_module=本包`。虽然 Java 同包语义确定，但 resolver 阶梯 6（target_module，:234）**先于**阶梯 7（import 别名，:241），而 Java 单类型 import 遮蔽同包同名类型——设置后会产生错误绑定（违反"不把推断伪装成确定事实"）。备选（Phase 2）：提取器在"短名未被单类型 import 遮蔽"时才设 target_module（消歧条件可静态判定），使同包引用升到 import_resolution 1.0。Recall 换正确性，Phase 1 选正确性。

> **局部名过滤的正确性注**：若不过滤，局部 `helper` 读取会经阶梯 8 绑定到全局唯一符号 `helper`——错误候选；过滤后该引用不存在，`raw_references` 只保留符号级事实。过滤是"不产出"，不是"解析失败"，不触碰三态契约。

## 1.6 错误状态、源码位置、稳定 ID 与 provenance

- **语法错误**：`parse_bytes` 透传 `has_error` → `parse_file_with_diagnostics`（parser.py:29–33）→ `syntax_error_files`；ERROR 节点周边按可恢复范围提取，产出符号照常入库（前缀不伪装：File 节点 metadata 由既有装配写入 `parsed`，含原样事实）。
- **源码位置**：字节偏移→1-based 行（`bisect` 行索引，与 python.py:42 同法）；`start_line/end_line` 进 `ParsedSymbol/ParsedReference`。
- **稳定 ID**：全走 identity.py（§0.2）；Java 不引入新前缀、不引入新盐。签名=源码拼写（含泛型），代码不动则 id 不动。
- **provenance**：DEFINES=`tree_sitter_syntax`；resolved 边=具体 strategy；unresolved/ambiguous 无边但 `raw_references.provenance="tree_sitter_syntax"`（resolver.py:310 既有规则）。File 节点 `parser="tree-sitter-java"`。

## 1.7 CLI 与增量接入

- **CLI 零改动**：index/update/查询命令语言无关（§0.5）；MCP 桥接零改动（frozen contract 不受影响，R8）。
- **增量零改动且开箱可用**，逐条核对 incremental.py：
  - `.java` 入扫描集 → 语言="java"，sha256 差异检测照常（:38–46）；
  - 未变文件从 `metadata["parsed"]` 缓存重建（:75–79）——`parsed_from_dict`（graph.py:25）按字段名反序列化，与语言无关；
  - 符号变化检测 kind 集（:86）包含 Phase 1 全部 kind（Class/Interface/Method）→ 改名/增删符号正确触发受影响引用重解析（:102–107）；
  - `replace_snapshot`/指纹/boundary 边照常（shard.py:101 指纹 kind 集同样覆盖）。
- **默认索引零高级分析产物**：`analyze` 对 `.java` 文件在 `_inventory`（orchestrator.py:138，读 `SUPPORTED_EXTENSIONS`）得 language="java"，`_supports_feature`（:35–43）全 False → 每文件 `skipped/unsupported_language`，fail-closed 如实上报；不产生任何 `analysis_*` 行（J10 断言）。

## 1.8 复用 vs 扩展清单与旧语言不变性论证

| 类别 | 结论 |
|---|---|
| **原样复用**（零改动） | graph.build_graph、resolver（三态阶梯/缓存/选择规则）、identity、storage schema、shard、incremental、query.GraphQuery、cli、MCP 桥、evidence/knowledge 契约、CAPABILITY_CONTRACT |
| **机械扩展**（纯追加） | scanner 扩展字典、parser 分支、parsing 导出、依赖清单、测试、文档 |
| **新建** | parsing/java.py、tests/fixture_java/、tests/test_java.py、（Phase 2）benchmarks/bench_java_l1.py |
| **明确不做**（Phase 1） | L2 Java 分析器、java.toml 词表、Java 缺陷查询、语义后端集成进 index、新 kind/新边类型、resolver 修改 |

**旧语言不变性论证**：(a) 所有共享代码变更均为"字典追加/分支追加/lru_cache 上限"，无既有键值或分支语义修改；(b) resolver/graph/storage 数学行为与语言无关，Java 事实不进入 Python/C/C++ 文件的解析路径（按 language 分派隔离）；(c) 以 T5 金样守护：对 `tests/fixture_repo`（Python）与 `tests/fixture_cpp` 在补丁前后做 nodes/edges/raw_references 快照逐字节比对，并全量 unittest 双平台回归。

---

# Step 2 语义后端选型（交付物 3：对比报告）

> **信息来源声明**：本章为桌面评估——基于三个候选的公开架构/文档知识 + 本仓库契约约束推演。**所有"预期"标注均未实测**，以 §2.3 基准为唯一登记证据路径；在此之前 Java 语义能力一律不登记为已验证（对应"能力登记"约束）。

## 2.1 候选定位

| | SCIP Java（scip-java） | JavaParser + Symbol Solver | Eclipse JDT（org.eclipse.jdt.core） |
|---|---|---|---|
| 原理 | 编译器插件路线：javac -Xplugin:SemanticDB 在**编译期**产出语义信息 → SCIP protobuf 索引 | 纯源码 AST + 独立类型求解器（CombinedTypeSolver = 源码目录 + Jar + 反射） | 编译器级模型：ASTParser.setEnvironment(classpath, sourcepath) + resolveBindings() → IBinding（错误容忍编译器） |
| 与 ProvenLattice 的产物差距 | 需 occurrence 角色 → RawReference 映射层 + protobuf 解析依赖 | 自研 Java driver 可直接输出 ParsedReference 形状 JSON | 同左 |

## 2.2 对比矩阵（要求轴全覆盖）

| 评估轴 | SCIP Java | JavaParser Symbol Solver | Eclipse JDT |
|---|---|---|---|
| 跨文件定义/引用准确性 | **高**（编译期绑定；前提：编译成功 + classpath 完整） | 中高（项目内好；外部依赖取决于 Jar 是否可供给；泛型/复杂推断有已知盲区） | **高**（编译器级绑定，错误容忍、部分可解析） |
| 方法重载/继承/接口实现 | 高（编译语义天然解决） | 部分：重载按参数近似匹配，继承链需正确配置 source solver | 高：IMethodBinding/ITypeBinding 层级完整，含 varargs/泛型 |
| Maven/Gradle 支持 | **一等**（构建系统集成 + Coursier 依赖解析） | 无内置：需自行喂 source roots 与 jar 列表 | API 层无内置：需自行提供 classpath/sourcepath（JDT LS 有构建集成但部署重） |
| JDK 兼容性 | 需 JDK 执行编译；新 JDK 支持随其发布节奏 | 语言级别跟进较快；JRE 即可运行 | JDK 跟进最快（Eclipse 年度发布轨）；需 JDK 级 rt 体系 |
| Python 主程序集成成本 | 子进程 + SCIP protobuf 解析（引入 protobuf 运行时依赖 + schema 版本管理） | 子进程 + 自研 driver 输出 JSON（JPype/py4j 进程内方案成本更高，不推荐） | 子进程 + 自研 driver 输出 JSON（同左） |
| 索引时间/内存/部署复杂度 | **最重**：时间≈全量编译；JVM+Coursier 缓存，部署数百 MB 级 | **最轻**：纯解析+求解；JRE+少量 jar | 中：批量 resolveBindings 内存偏高；jdt core jar 数十 MB |
| 解析失败/依赖缺失降级 | **硬依赖**：编译失败 → 索引不完整/失败，语法事实也难单独取出 | **天然降级**：求解失败 → unresolved；可先出语法事实再补语义 | **天然降级**：binding 为 null → unresolved；错误容忍解析与本仓 `raw_references` 三态契约契合最好 |

## 2.3 小型对照基准 `bench-java-l1`（一次只接一个后端）

**形态**：无构建工具的纯源码树（规避 Maven/Gradle 方差）；规模 15–20 文件 / 500–800 LOC / 4 个包；无网络。
**用例集**（每条带 gold 标签，格式：`{file, line, col, snippet, expected_target_fqn | expected_status, reference_type}`）：
1. 跨文件单类型 import 解析（期望 resolved 0.95）；
2. 同包未限定引用、全局唯一（期望 resolved 0.75）；
3. 跨包同名类 ×2：带 import（resolved）与不带（ambiguous）；
4. 同类 2–3 个重载的调用点（期望 ambiguous，候选数=重载数）；
5. extends 跨文件类 + implements 跨文件接口（IMPLEMENTS 边）；
6. 静态导入方法裸调用（resolved 0.99）；
7. 通配 import（期望按 §1.5 落 unresolved/ambiguous）；
8. 泛型/嵌套类/enum/record/annotation 声明符号；
9. 仅 JDK 外部引用（`java.util.*`、`System`）→ unresolved（降级观测，**错误绑定必须为 0**）；
10. 语法错误文件（可恢复符号仍产出，无崩溃）。

**指标**：Resolved Precision / Recall（对 gold）、**Wrong-Resolution（错误绑定数，硬约束 =0）**、overload/ambiguity 判定符合率、重跑 3 次输出字节一致性、时间/内存预算（<5 min、<2 GB）。
**对照系**：tree-sitter 基线（Phase 1 前端）同场跑分——它既是被测者也是后续语义后端的"增量收益"参照；评分方式对齐既有先例 docs/p0-graph-fidelity-v1-status-v1.md（GRAPH_FIDELITY_SCORING_V1 风格的 Resolved Precision 口径，该基线 C/C++ 为 0.931 sample / 0.899 weighted，作为方法学参照而非目标值）。
**运行方式**：`benchmarks/bench_java_l1.py`，后端以适配器接入，**不并行集成多套后端**。

## 2.4 推荐路线

1. **Phase 1（本计划）**：tree-sitter-java 语法事实——进程内 Python、零新基建、零 resolver 改动，天然满足"默认索引零高成本分析"。
2. **Phase 2（独立立项）**：按基准结果选型语义后端。**首选 JDT**（准确性最高 + binding-null 天然降级与三态契约最契合）；**备选 JavaParser**（最轻，若 JDT 内存/部署超预算）；**SCIP Java 定位为对照参照系**（硬依赖完整编译+构建系统，与"依赖缺失降级"诉求冲突最大，不建议作为首选集成对象）。语义结果只以**更高 confidence、独立 strategy、独立 metadata** 的 resolved 记录进入 `raw_references`，不覆盖语法事实，不改变三态语义。

---

# Step 3 第一阶段验收矩阵（交付物 4）

测试落位：`tests/test_java.py`（unittest，仿 test_cpp.py 风格）+ `tests/fixture_java/`（磁盘 fixture，copytree 使用）；全部用例挂 `@unittest.skipUnless(HAS_JAVA_GRAMMAR, "tree-sitter-java is required")`。测试命名沿用仓库场景编号惯例（`java01`…）。

**主 fixture `tests/fixture_java/` 骨架**（src-layout，4 包 14 文件）：`com/example/app/{Application,Overloads,AppService,Wildcard,Broken}.java`、`com/example/core/{Helper,HelperStore,BaseService,Watcher}.java`、`com/example/util/Helper.java`、`com/example/model/{Point,Color,Id,Outer}.java`。要点：app 与 util 各有 `Helper`（同名跨包）；`AppService extends BaseService implements Watcher`；`Overloads` 含 3 个同名方法；`Broken.java` 含语法错误；`Wildcard.java` 使用通配 import；`Point` 为 record、`Color` 为 enum、`Id` 为 @interface、`Outer` 含嵌套类。

| # | 验收项 | Fixture | 预期节点/边（关键断言） | 判定标准 | 失败处理 |
|---|---|---|---|---|---|
| J1 | 文件识别 | 主 fixture 全仓 | `files` 表 14 行、language 全为 `"java"`；File 节点 14 个；目录链 CONTAINS 完整 | `metrics.files_scanned==14`；`scan_repository` 对 `.java` 产出 SourceFile(language="java")；非 Java 噪声文件（如 `.txt`）不入库 | grammar 缺失 → skipUnless 跳过；扫描异常 → fail-closed 报错 |
| J2 | 语法错误 | `Broken.java` | `syntax_error_files>=1`、`parse_failures==0`；可恢复符号仍产出（如 Broken 类节点存在）；无崩溃 | has_error 透传（parser.py:29–33）；修复该文件后 `update` 正常收敛 | 提取器在 ERROR 节点抛异常 → 用例失败即阻断（fail-closed） |
| J3 | 类型符号提取 | `Point/Color/Id/Outer` | record→Class(`java_kind="record"`)、enum→Class(`"enum"`)、@interface→Interface(`"annotation"`)、嵌套类 qualified=`com.example.model.Outer.Inner`；DEFINES 边数=符号数 | kind/qualified_name/signature/metadata 逐项精确断言（场景编号 java03–java06）；不出现新 kind 字符串 | 断言失败 → 阻断；kind 漂移 → 视为契约破坏，回滚 |
| J4 | 成员符号与重载 | `Overloads.java` | 3 个 `Method` 节点同 qualified_name、3 个不同 signature → 3 个不同 symbol_id；构造器 `Method`+`java_member="constructor"`；字段 `java_member="field"` | `len(symbols)==3` 且 id 两两不同；任务上下文/指纹对三者分别可寻址 | 同上 |
| J5 | 定义/引用/调用候选 | `Application.java` | `new Helper()`→CALLS；静态调用→CALLS(qualified 命中 0.99)；字段读→REFERENCES；`raw_references` 状态分布与 §1.5 表逐行一致；仅 resolved 产生边 | 对每条手工标注引用断言 status/strategy/confidence/candidates（java07–java10） | 同上 |
| J6 | 同名与歧义 | `app/Helper` vs `util/Helper`；`Overloads` 调用点 | 无 import 场景：ambiguous，candidates=2；带 import 场景：resolved 0.95；重载调用：ambiguous，candidates=重载数 | 精确断言候选 id 集合与 confidence；**禁止任何"猜中一个"的 resolved** | 发现错误绑定 → 阻断（Wrong-Resolution=0 硬约束） |
| J7 | 跨文件关系 | `AppService`→`BaseService`/`Watcher`；`Application`→`core.Helper` | IMPLEMENTS 边 2 条（metadata java_relation）；import 解析 resolved 0.95；跨 shard CALLS 边 `metadata.scope=="boundary"` ≥1 | 边存在+provenance/strategy 断言；shard 边界索引（shard_edges）可查 | 同上 |
| J8 | 增量更新 | 主 fixture：改 1 文件 / 改名 1 符号 / 无改动 三场景 | **全量库与增量库四表快照逐行相等**（test_cpp.py:76 惯用法）；`files_reparsed==1`；改名触发受影响引用重解析；无改动 `changed==False` 且不新增 generation | parity 快照相等（硬断言）；metrics 断言 | parity 失败 → 阻断，按 V1.0 硬门处理 |
| J9 | 旧语言回归 | `tests/fixture_repo`（Python）+ `tests/fixture_cpp` | 补丁前后 nodes/edges/raw_references 快照**逐字节相同**；全量 `python -m unittest discover -s tests -v` 双平台全绿 | 金样比对（新增守护用例）+ CI 双绿；`test_capabilities_i0.py` 冻结集不变 | 任一漂移 → 回滚接入点变更，STOP |
| J10 | 默认性能与零高级产物 | 主 fixture + 计时 | 无 `analysis_*` 表与行（BASE_TABLES 断言，test_capabilities_i0 惯用法）；`analyze --features ast` 对 Java 文件全部 `skipped/unsupported_language`；index 耗时预算断言（fixture 规模 <5s，绝对宽松阈值防抖） | 表集合断言 + per_file bucket 断言 + 耗时上界 | 预算超限 → 不阻断发布但记入报告；产物泄漏 → 阻断 |
| J11 | 能力登记门禁 | docs | `docs/capability-matrix.md` Java 行 = "候选（未验证）"；CI 全绿前不得改标"已验证" | 评审 checklist；J1–J10 全绿 + 基准（§2.3）出报告后方可升格 | 违反即违反约束，评审驳回 |

**主 fixture 的精确总量断言**（如节点总数、边总数）在 T4 编写测试时冻结为常量（延续仓库"PR baseline"注释惯例，参照 test_uaf_i2b1.py:107 先例），本文只锁定判定口径，不预填易漂移的计数。

---

# 评审决议记录（v1.1，2026-10-15）

评审确认本文档达到 `DESIGN_READY_FOR_REVIEW` 并作出以下裁定：

## D1–D5 决策点

| # | 决策点 | 裁定 |
|---|---|---|
| D1 | kind 复用策略 | **复用现有 kind**，§1.3 映射表即最终方案；Phase 2 若引入新 kind 必须三集合同步（query.py:16 / shard.py:105 / incremental.py:86）+ 全量回归 |
| D2 | package 是否建节点 | **暂不建独立节点**，以 File 节点 `metadata["java_package"]` 承载 |
| D3 | target_module 策略 | **保守路线**：无法确定目标时保留 `ambiguous/unresolved`，不以猜测换取表面覆盖率 |
| D4 | T7 可选项 | **默认不做**；出现明确需求和验收价值后再纳入 |
| D5 | Phase 2 语义后端 | **JDT 为候选首选、SCIP 为对照**；桌面评估未实测，§2.3 基准通过前不认定最终后端 |

## 评审强调的边界与底线（约束 D1 的强制解释）

- **kind 复用 ≠ 牺牲语义精度**。重载、构造器、继承、接口实现必须在既有 schema 中**可区分、可验证**：
  - 重载 → 同 qualified_name、不同 signature 的独立 symbol_id（identity.py:74 既有机制）；
  - 构造器 → `Method` + `java_member="constructor"`（签名无返回段，与方法可区分）；
  - 继承/实现 → `IMPLEMENTS` 边 + `metadata["java_relation"]="extends"/"implements"`；
  - 无法准确表达的关系**先记录限制**（如 R5 匿名类缺口、R6 重载 ambiguity），不得通过错误映射制造虚假语义边。
- **三条验收底线**（进入 J1–J11 的门槛，违反任一即 STOP）：
  1. **Wrong-Resolution = 0**——不为覆盖率强行解析到错误目标；
  2. **旧语言无回归**——快照测试 + 冻结断言（J9）；
  3. **阶段结果可独立审查**——T0 / Foundation Graph / 语义增强分别报告；第一阶段通过 ≠ Java 具备完整语义分析能力。
- **执行顺序**：T0（冒烟，硬门槛）→ T1–T3（Foundation Graph）→ T4–T7（引用/调用/边界/增量/回归验证）→ T8–T9（J1–J11 验收与封存）。语法解析成功不得视为语义解析成功。
- **本次批准范围**：进入 T0 与基础图谱实现的准备；JDT 未被认定为最终后端。

---

# 第一阶段实现任务清单与风险项（交付物 5）

## 任务清单（T0 前置，T1–T8 主线；T9 Phase 2 预研独立立项）

| # | 任务 | 产物 | 依赖 | 预估 |
|---|---|---|---|---|
| T0 ✅（2026-10-15 完成） | grammar 兼容冒烟（临时 venv 安装 tree-sitter-java 0.23.5 + tree-sitter 0.26.0）：Language 包装、has_error、Java 节点字段名核对 | 冒烟记录 + AST 字段速查表（见附录 A；正式用例编写时移入 tests/ 注释） | — | 0.5d |
| T1 ✅（2026-10-15 完成） | 依赖与打包：pyproject dependencies、requirements.txt pin、CI 两个 job pip 行 | 提交片段 | T0 | 0.25d |
| T2 ✅（2026-10-15 完成） | `parsing/java.py`：JavaTreeSitterParser + JavaExtractor（按 §1.2–1.4） | 新模块 | T0 | 2d |
| T3 ✅（2026-10-15 完成） | 接线：scanner/parser/lru_cache/parsing 导出（接入点①②④） | 小改 3 文件 | T2 | 0.5d |
| T4 ✅（2026-10-15 完成，形式偏差见 B.4） | `tests/test_java.py` 21 用例（java01–java21，覆盖 J1–J10 的 Phase 1 可测项）；fixture 采用仓库主导的内联字符串惯例，未创建磁盘 `fixture_java/` | 测试 | T3 | 2.5d |
| T5 ✅（2026-10-15 完成，形式偏差见 B.5） | 旧语言回归：全量 438 tests OK + HEAD-vs-current 四表金样对比 IDENTICAL（py/cpp fixture） | 证据记录 | T3 | 0.5d |
| T6 | 文档：capability-matrix/roadmap 增"Java 候选（未验证）"行；README 语言清单句 | 文档 diff | T4 | 0.5d |
| T7 | 评审决策项（默认不做，需明确批复）：knowledge.py:73 锚点加 `.java`；java.lang 常见名降噪过滤；package→Namespace 节点 | 决策记录 | T4 | — |
| T8 | 本设计文档评审 → `DESIGN_READY_FOR_REVIEW` 转 `IMPLEMENTATION_STARTED` | 评审记录 | T0–T6 | — |
| T9 | （Phase 2 前置，独立）构建 bench-java-l1 + gold，跑 tree-sitter 基线；JDT 适配 spike（子进程 driver，不进默认 index） | 基准报告 | T4 | 3d |

## 风险登记表

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | tree-sitter-java 0.23.x 与 tree-sitter 0.26.0 绑定不兼容 | T1 起全部阻塞 | T0 先行冒烟；不兼容则降 pin 或升 tree-sitter 上限（独立小变更评审）；无法解决 → STOP |
| R2 | Java AST 字段名与设计假设不符（tree-sitter-java 节点 field 命名差异） | T2 返工 | T0 产出字段速查表；提取器对缺字段防御性降级（不产出而非错产出） |
| R3 | 诱惑引入新 kind/边类型破坏冻结契约 | 三处硬编码集合 + design-v0 契约漂移 | §1.3 映射表锁死 Phase 1 kind；任何 kind 扩展走独立评审（三集合 + fingerprint + query 同步 + 全量回归） |
| R4 | unresolved 噪声（java.lang/泛型/通配 import/构造器缺省）膨胀 raw_references 与指标 | 存储与指标可读性 | 基准量化噪声水平；T7 降噪为可选评审项；指标口径不变（诚实计数） |
| R5 | 匿名类/lambda 归属语义 | 事实缺口被误读 | §1.3 明确规则（匿名体跳过、lambda 归属词法外围，与 C/C++ 现状一致）；文档化 gap；Phase 2 稳定命名议题 |
| R6 | 重载调用全部 ambiguous 的精度天花板 | L1 callers 查询召回受限 | 这是三态契约的诚实结果；Phase 2 语义后端解决；不伪造 resolved |
| R7 | 仓库根部陈旧副本（`provenlattice/`、`proventlattice/`）误导实施/审查 | 改错树 | 一切改动限定 `src/`；CI `PYTHONPATH=src`；本文 Step 0 已显式标注；建议评审时决议清理（不在本任务内执行） |
| R8 | MCP frozen contract 字节门（d9-c8 契约 sha256 校验） | 若改 CLI 输出会破门 | Phase 1 零 CLI 变更 → 无影响；未来改动需同步契约文件 |
| R9 | `.java` 入扫描集后 `analyze` 将 Java 文件列为 skipped | 用户困惑？ | 预期行为（fail-closed 上报）；J10 断言固化；文档说明 |
| R10 | 增量解析缓存 schema（File metadata `parsed`）随提取器演化失效 | 旧库升级 | ParsedFile 字段保持向后兼容（新增 metadata 键）；`parsed_from_dict` 已有 V0 迁移先例（graph.py:28–40）；必要时按 CALL_KIND_VERSION 惯例加提取器版本号进缓存键 |

## 约束符合性自检

- 不改 Python/C/C++ 语义：§1.8 论证 + J9 金样守护 ✅
- 默认 index 无隐式高成本 Java 深度分析：L2 全线不触碰，J10 断言 ✅
- 不把未解析/推断伪装成确定事实：§1.5 全部歧义场景落 ambiguous/unresolved；Wrong-Resolution=0 硬约束（J6）✅
- 不登记未验证能力：J11 门禁 + Step 2 桌面评估显式声明未实测 ✅
- 不发布版本、不合并、不碰远程：本文档为唯一交付物，未提交任何代码 ✅

---

---

# 附录 A：T0 冒烟记录（2026-10-15，PASS）

## A.1 环境与隔离

- 隔离 venv：`%TEMP%\opencode\tsj-venv`，安装 `tree-sitter==0.26.0`（与 requirements.txt pin 一致）+ `tree-sitter-java==0.23.5`（本地 wheel，零网络）；**当前环境未安装任何新依赖**。
- 当前环境回归基线（T5 基准）：`python -m unittest discover -s tests`（PYTHONPATH=src）→ **417 tests OK，77s**（Windows）。

## A.2 检查结果

| # | 检查 | 结果 |
|---|---|---|
| S1 | Language/Parser 引导（`Language(tree_sitter_java.language())`） | PASS |
| S2 | 合法 Java 文件 `has_error == False` | PASS |
| S3 | 破损文件 `has_error == True`、ERROR 节点存在、`class_declaration` 仍可恢复（容错解析有效） | PASS |
| S4 | 全部目标构造的 AST 字段名核对（见 A.3） | PASS |
| S5 | 增量重解析（`parse(src, old_tree)` + `old_tree.changed_ranges(new_tree)`，3 段变更区间） | PASS |
| S6 | CRLF 行号与 LF 一致（0-based row 相同）——Windows 换行安全 | PASS |
| S7 | 补充探针：`extends_interfaces`/`generic_type`/`annotation`（带参）/`static_initializer`/`annotation_argument_list` 全部解析干净 | PASS |

**结论：T0 PASS。pin `tree-sitter-java>=0.23,<0.24` 验证成立，T1 解锁。**

## A.3 AST 字段速查表（T2 提取器依据；T4 编写用例时移入 tests/ 注释）

**关键差异（与设计假设核对后需注意的点）：**

- `package_declaration` / `import_declaration` **无命名字段**：包名/导入目标取未命名的 `scoped_identifier` 子节点；`scoped_identifier` 自身有 `scope`/`name` 字段（链式，`java.util.List` = scope(java.util) + name(List)）。
- `method_invocation` **有 `object` 字段**（receiver）——receiver 提取无需启发式，`obj.foo()` 的 object=identifier。
- `spread_parameter`（varargs）为未命名子节点序列 `[type, "...", variable_declarator]`。
- `throws` 子句是 `method_declaration` 的未命名子节点。

**字段映射（field_name → 子节点类型）：**

| 节点 | 命名字段 |
|---|---|
| `class_declaration` | `name`(identifier) · `superclass`([extends, type_identifier]) · `interfaces`(super_interfaces→type_list) · `body`(class_body) |
| `interface_declaration` | `name` · `body`(interface_body)；extends 走 `extends_interfaces`→[extends, type_list] |
| `enum_declaration` | `name` · `body`(enum_body)；常量 `enum_constant`: `name` + `arguments`(可选) |
| `record_declaration` | `name` · `parameters`(formal_parameters) · `interfaces` · `body`(class_body)；紧凑构造器 `compact_constructor_declaration`: `name` + `body`(block) |
| `annotation_type_declaration` | `name` · `body`；元素 `annotation_type_element_declaration`: `type`+`name`+`value`(default) |
| `method_declaration` | `type`(返回类型: void_type/type_identifier/generic_type/scoped_type_identifier) · `name` · `parameters` · `body`(block) |
| `constructor_declaration` | `name` · `parameters` · `body`(constructor_body) |
| `field_declaration` | `type` · `declarator`(variable_declarator: `name`+`value`) |
| `formal_parameter` | `type` · `name` |
| `method_invocation` | `object`(receiver，可无) · `name` · `arguments` |
| `object_creation_expression` | `type` · `arguments`（匿名类体走 `class_body`） |
| `explicit_constructor_invocation` | `constructor`(this/super) · `arguments` |
| `method_reference` | 无字段：未命名 `[receiver, "::", member]` |
| `generic_type` | 未命名 `[type_identifier, type_arguments]`；`scoped_type_identifier` 链式（`.a.B` → [.a, ., B]） |
| `annotation` / `marker_annotation` | `name`(identifier) / `arguments`(annotation_argument_list→element_value_pair)；注解名为 `identifier`（类型用途，需按类型引用处理） |
| `enhanced_for_statement` | `type` · `name`(循环变量，供局部名过滤) · `value` · `body` |
| `lambda_expression` | `parameters` · `body` |

原始探针数据：`%TEMP%\opencode\t0_smoke_result.json`（冒烟脚本 `%TEMP%\opencode\t0_smoke.py`）。

---

# 附录 B：T1–T3 执行记录（2026-10-15）

## B.1 执行环境与基线

- 起始 HEAD：`42c6d89`（main，未提交任何 commit）；结束 HEAD：`42c6d89`（约束 5：不提交）。
- 基线：T0 记录的 417 tests OK（Windows，py3.12.10）；结束态：**438 tests OK（417 + 21 Java 新增，零失败，两次复跑）**。
- 依赖：`tree-sitter-java==0.23.5` 加入 pyproject/requirements/CI；干净 venv `pip install -e .` 验证通过；现有四个 grammar pin 未动。

## B.2 变更文件清单

| 文件 | 变更 | 目的 |
|---|---|---|
| `pyproject.toml` | +1 行依赖 | T1 |
| `requirements.txt` | +1 行 pin | T1 |
| `.github/workflows/ci.yml` | 2 处 pip 行追加 | T1 |
| `src/provenlattice/parsing/java.py` | **新建**（JavaTreeSitterParser + JavaExtractor） | T2 |
| `src/provenlattice/parsing/__init__.py` | +1 导出 | T3 |
| `src/provenlattice/parser.py` | +java 分支；`lru_cache` 3→4 | T3 |
| `src/provenlattice/scanner.py` | `SUPPORTED_EXTENSIONS` + `".java": "java"` | T3 |
| `tests/test_java.py` | **新建**（21 用例） | T4 |
| `docs/java-support-implementation-plan.md` | 状态与附录 | 记录 |

**零触碰**：graph.py / resolver.py / identity.py / models.py / storage.py / incremental.py / shard.py / query.py / cli.py / analysis*.py / knowledge.py / orchestrator.py / semantics/*。

## B.3 每阶段命令与结果（摘）

- T1：`pip install -e .`（干净 venv）→ 5 个 grammar 就位（exit 0）；4 语法最小解析测试全过（exit 0）。
- T2：`python -m unittest tests.test_java` → 21/21 OK。
- T3/T4：同上（graph 集成用例含内）。
- Step E：`python -m unittest discover -s tests` → **438 OK**（49s/47s 两次）；金样对比 `git archive 42c6d89` 代码 vs 当前代码，同 fixture 同目录建库：
  - Python fixture：nodes 14 / edges 16 / shards 3 / raw_references 9 → **IDENTICAL**
  - C/C++ fixture：nodes 38 / edges 43 / shards 4 / raw_references 11 → **IDENTICAL**
- 冒烟期修复的缺陷（均有用例固化）：通配 import 目标解析（`* from pkg`）、别名改写语义对齐 python.py:163–171 先例、单段 package 声明（`package a;` 子节点为 identifier）、字段/方法签名类型引用遗漏。

## B.4 偏差与观察（相对原计划）

1. **§1.5 期望修正**：带单类型 import 的类型使用经提取器附加 `target_module` → resolver 阶梯 6 → `import_resolution 1.0`（计划原写 0.95）。理由：镜像 `parsing/python.py` `_call` 先例（alias 只附 module，由 resolver 拼接）；Java 单类型 import 绑定确定，1.0 比 0.95 更准确。纯标识符（无 module，如调用 receiver）仍走阶梯 7 → 0.95。两者均有用例（java08）。
2. **tree-sitter 0.26 `changed_ranges` 为结构性对比**：等长/变长原位替换返回空区间（python 语法同样如此），仅追加场景产生区间（java04 采用 test_core.py:79 同款场景并注明）；生产增量路径（incremental.py）从不使用 old_tree，不受影响。
3. **fixture 形式**：采用仓库主导的内联字符串惯例（test_c_ast_analysis.py 等先例），未创建磁盘 `tests/fixture_java/`；§3 主 fixture 骨架以内联 fixture 等价覆盖（同名跨包、重载、通配、语法错误、record/enum/@interface/嵌套）。
4. **T5 形式**：金样对比为一次性证据（本文记录）+ 既有 parity 套件（test_cpp/test_integration 等，含于 438）承载持续守护；未新增持久绝对快照用例，避免套件内固化易漂移计数。
5. **提取范围 gap（按计划记录，非缺陷）**：record 组件不产出符号；`annotation_type_element_declaration`（注解元素）不产出符号；匿名类体内容跳过（R5）；隐式默认构造无符号（`new` 解析到类型节点，§1.3.2 既定）。

## B.5 J1–J11 状态（Phase 1 范围）

| 项 | 状态 | 证据 |
|---|---|---|
| J1 文件识别 | **PASS** | java07（11 文件 language=java；`files` 表唯一语言 java） |
| J2 语法错误 | **PASS** | java02（has_error=True 且 Broken 类恢复；parse_failures=0） |
| J3 类型符号 | **PASS** | java05（8 类声明 → 冻结 kind + java_kind 判别；enum 常量；嵌套） |
| J4 成员与重载 | **PASS** | java06（3 重载 3 签名 3 id；构造器/字段签名格式） |
| J5 定义/引用/调用候选 | **PASS** | java08/09/14（import 1.0 / qualified 0.99 / unique 0.75 / same-file 0.98） |
| J6 同名与歧义 | **PASS** | java10（ambiguous 候选=3 含双 Runner）、java11（重载候选=3）、java12（通配→unresolved + ambiguous） |
| J7 跨文件关系 | **PASS** | java09（跨文件 0.99/0.75）、java13（extends resolved + 外部接口 unresolved）、java15（跨 shard 边界 CALLS ≥1） |
| J8 增量更新 | **PASS** | java16（四表快照与全量逐行相等；files_reparsed=1，files_reused=10） |
| J9 旧语言回归 | **PASS** | 438 tests OK；金样四表 IDENTICAL（py + cpp，HEAD vs current） |
| J10 默认性能与零高级产物 | **PASS**（性能预算项待基准） | java17（无 analysis 表）、java21（Java 文件 analyze → skipped/unsupported_language）；性能预算留待 §2.3 基准正式测量 |
| J11 能力登记门禁 | **PASS**（T6 于 2026-10-15 完成） | capability-matrix.md L1 新增 Java 行（FUNCTIONAL + DIAGNOSTIC，RQ1 formal 未执行显式标注）+ 边界注（含 T8 发现的精度边界登记）；roadmap G7 进度条目；README Java 节 + Limitations 条目；远程 CI 运行待提交后执行 |

## B.6 Wrong-Resolution=0 证据范围（如实声明）

- **间接形状不绑定**：java13（`super.x()` / `super()` / 复杂 receiver / `this::m` → 全部 unresolved，strategy=indirect_call_shape）；外部类型（java.io.Serializable）IMPLEMENTS unresolved。
- **局部名遮蔽不绑定**：java18（局部 `build` 在全局唯一同名符号存在的前提下产生 **0** 条 raw_reference；定性对照：无局部过滤时该引用将经阶梯 8 错误绑定 0.75）。
- **歧义保留**：java10/java11/java12（跨包同名、重载、通配 import 全部 ambiguous/unresolved，候选集完整保留）。
- **范围限制**：以上为 fixture 手工标注场景的证明，不是穷尽性证明；`_select_candidate` 的"同签名取定义"路径在 Java 事实形态下无触发面（Java 无同签名重复声明），已由提取端去重保证。

## B.7 风险状态更新

- R1（兼容性）：关闭（T0/T1 双重验证）。R2（AST 字段假设）：关闭（附录 A 速查表 + 用例固化）。
- R4（unresolved 噪声）：开放——现有 fixture 规模不可测；正式量化依赖 §2.3 基准（T9）。
- R5（匿名类/lambda）：按计划开放（gap 已文档化、测试无断言依赖）。
- R6（重载精度天花板）：按计划开放（Phase 2 语义后端课题）。
- 其余 R3/R7/R8/R9/R10 维持原判；R9（analyze skipped 上报）已由 java21 固化。

---

# 附录 C：T8 独立工程评审记录（2026-10-15）

## C.1 评审范围与独立性声明

- 评审对象：T1–T3 全部实现与证据（工作区形态，HEAD `42c6d89` 未变）。
- 独立性：评审以证据复核 + 新增对抗实验为主，未修改任何 Java 实现代码或测试。
- 变更核对：tracked 6 文件（+11/−5，全为纯追加）+ untracked 3 文件（java.py 576 行 / test_java.py 511 行 / 本文档），与附录 B.2 完全一致，无遗漏。

## C.2 九项评审点结论

| # | 评审点 | 结论 | 证据 |
|---|---|---|---|
| 1 | 架构合规 | **合规** | 6 文件 diff 逐行核对：全部为字典/分支/导出/依赖追加；解析器实现 `parsing/base.py` 协议，提取器模式与 python/cpp 前端同构；零核心触碰 |
| 2 | 节点/边/signature/稳定 ID/三态 | **合规** | identity.py 零 diff（ID 输入不变）；kind 全部落在冻结集（java15）；signature 确定性（java06 + java19 重复提取相等）；三态经 resolver 既有阶梯，CHECK 约束未动 |
| 3 | 4 缺陷回归 | **全部有用例** | 通配 import→java12；别名改写→java08；单段 package→java01；签名类型引用→java09（均先 FAIL 后 PASS 闭环） |
| 4 | 错误确定性绑定 | **1 项 MAJOR 发现**（见 C.3-P1）+ 5 项对抗实验全部保守正确：同名字段/方法→ambiguous（候选 2）；FQN 调用重载→ambiguous（候选 2）；局部遮蔽导入类名→零引用；局部类名与类型双命名空间行为正确 |
| 5 | 依赖/CI/干净安装 | **合规** | pyproject range 与 requirements/CI pin 一致（0.23.5 ∈ [0.23,0.24)）；干净 venv 安装 exit 0；现有 4 pin 未动 |
| 6 | 旧语言回归 | **PASS** | 全量 438 OK（评审中第三次复跑）；金样四表 IDENTICAL（py + cpp，评审期复验） |
| 7 | J1–J11 与证据一致 | **一致** | J1–J10 逐项映射到 java01–java21；J11 由 T6 完成（登记与证据一致） |
| 8 | 增量删除/重建/重复索引 | **合规** | Exp3：删除文件 → 节点 11→8、B 类节点 0、引用清理、重加恢复 11（reparsed=1）；Exp4：重复索引 id 完全一致、generation=2、无重复 |
| 9 | J10 性能 | **维持待测** | 功能测试不替代基准；文档中显式标注"性能基准未测" |

## C.3 问题分级

**P1（MAJOR）— same-file 阶梯不区分类型/值命名空间**
- 位置：resolver.py:225–229（same-file 分支，冻结契约）× parsing/java.py 类型使用/new 发射。
- 复现：`b/Caller.java` 声明 `public void Helper()` 且 `import a.Helper`；`public Helper make()` 的返回类型与 `new Helper()` 均以 same_file_resolution 0.98 绑定到方法节点 `b.Caller.Helper`（应为类 `a.Helper`）。实验脚本留存于评审临时目录（t8-exp6）。
- 影响：单条错误语义边（REFERENCES/CALLS → Method 节点）；触发条件 = 同文件存在与类型大小写完全同名的成员（违反 Java 命名惯例但合法）。
- 定性：**V0 冻结契约的全语言既有精度边界，非 T1–T3 引入回归**——Python 同名场景实证一致（t8-exp7：`make() -> Helper` 注解同样绑定同文件 `def Helper()`）。
- 建议：Phase 1.1 修复候选——type_usage/new 引用附加 metadata 标记，resolver same-file 分支对标记引用过滤非类型 kind 候选（核心小改，须独立评审保证旧语言不变）；短期已在 capability-matrix 边界注如实登记。**触碰 Wrong-Resolution=0 底线的字面要求，故评审终态不给无条件 PASS。**

**MINOR 项**：
- M1：tree-sitter 0.26 `changed_ranges` 为结构性对比，原位替换返回空区间（全语言一致；生产增量路径不使用 old_tree；已在 B.4 与 java04 注释记录）。
- M2：`annotation_type_element_declaration`、record 组件、匿名类体不产出符号——按计划记录的 gap（非缺陷），已登记。
- M3：评审依赖实验在临时目录完成，Exp3/Exp6/Exp7 未固化为套件用例（本轮边界禁止改测试；建议随 P1 修复一并补用例）。

## C.4 最终评审结论

**`PHASE1_REVIEW_CONDITIONAL — STOP`**

- T1–T3 实现质量与证据链整体合格（九项评审点 8 项 PASS，1 项 MAJOR 发现）。
- **放行条件（单选其一）**：
  1. 执行 P1 修复（含回归用例）并通过复审；或
  2. 评审者正式裁决 P1 为"已登记的契约级限制"（capability-matrix 边界注即为登记载体），修订 Java 验收底线的适用范围并书面确认——随后可直接批准 T9（P1 与 T9 语义后端基准正交，不互为前置）。
- T9 未启动；未提交任何 commit；Java 能力登记保持"FUNCTIONAL + DIAGNOSTIC、RQ1 formal 未执行、无 L2"的如实口径。

---

# 附录 D：P1 定向修复记录（PL-JAVA-P1-RESOLVER-SAFETY，2026-10-15）

## D.1 根因与复现

- **根因**：`resolver.py` 阶梯 3（same-file，:225–229）与阶梯 8（全局唯一，:252–255）仅按 `name` 匹配候选，不感知引用语义；Java `type_usage`/`object_creation` 引用的 short 名命中同文件/全局同名 Method 节点时被错误绑定（confidence 0.98/0.75）。
- **复现固化**：tests/test_java.py 新增 java22（import 场景）/java23（同文件类+同名方法）/java24（跨包同名），修复前全部 FAIL（Exp6 形态）；Python pin 测试固化旧行为。
- **归因修正（Exp7）**：Python 前端不发射返回注解引用（parsing/python.py `_function` 只走 body），共享机制在 Python 经 **CALLS** 同名绑定显形；pin 测试按实证修正。

## D.2 修复内容（diff 摘要）

| 文件 | 变更 |
|---|---|
| `src/provenlattice/resolver.py` | ① `CALL_KIND_VERSION` 1→2（缓存失效）；② 新增 `_TYPE_TARGET_SYNTAXES = {type_usage, object_creation}` 与 `_CALLABLE_KINDS = {Function, Method}`；③ 阶梯 3/8 对 type-target 引用排除可调用 kind（净增 ~12 行，metadata 门控） |
| `tests/test_java.py` | +4 用例（java22/23/24 + python pin）、P1 fixtures、`resolved_targets` 辅助 |

**零变化**：schema/表结构、稳定 ID、提取器（metadata 既有 `syntax` 字段已足够，无需修改）、freshness 机制、Python/C/C++ 提取与解析路径。

## D.3 修复前后对照

| 场景 | 修复前 | 修复后 |
|---|---|---|
| java22 import+同名方法 | type_usage/new → resolved 0.98 → **Method** b.Caller.Helper（错误） | resolved 1.0 import_resolution → **Class** a.Helper |
| java23 同文件类+同名方法 | ambiguous（候选 2） | resolved 0.98 same_file → **Class** b.Helper |
| java24 跨包同名 | resolved 0.75 → **Method**（错误） | resolved 0.75 unique_symbol → **Class** a.Helper |
| java13 `this()` 显式构造 | ambiguous | 不变（syntax 不在守卫集，构造歧义如实保留） |
| java12 通配 import | ambiguous（候选均为 Class） | 不变 |
| Python 同名 CALLS | same_file 0.98 → Function | 不变（pin 测试固化） |
| C/C++ | — | 零变化（守卫零触发） |

## D.4 验证结果

1. Java P1：java22/23/24 PASS（错误绑定消除）✓
2. Python 场景：pin 测试 PASS（行为不变 + 机制共享实证）✓
3. C/C++：无 type_usage 发射；金样零触发 ✓
4. J1–J11 相关：25 java tests OK ✓
5. 全量 unittest：**442 OK**（438 基线 + 4 新增）✓
6. 四表 parity：nodes/edges/shards **IDENTICAL**；raw_references 除 `call_kind_version` 版本戳（设计内缓存失效字段）外 IDENTICAL（py + cpp）✓
7. 对抗：同名类型/方法、跨文件同名、重载、局部遮蔽、构造器、增量索引（java16）全过 ✓
8. 版本戳收敛：对 version-1 旧库，任一文件变化触发重建 → reprocessed=9/reused=0/全部收敛 version 2 ✓；**无变化库维持旧解析直至触发（既有缓存机制边界，非本次引入，如实记录）**

## D.5 Wrong-Resolution 验证范围与剩余风险

- 范围：P1 三变体 + 既有间接形状/局部遮蔽/歧义保留用例 + 全量套件；非穷尽证明（声明保留）。
- 剩余风险：① 无变化库升级延迟收敛（既有机制边界）；② qualified/module/alias 阶梯未加类型过滤——Java 结构上无碰撞面（方法 qualified 恒为 `pkg.Class.method` 形态），其他语言无此类发射者；③ 方法调用可调用性过滤（call→field）无证据未实施，设计备选已记录；④ Python 侧同类机制未修复（需独立决策，pin 防泄漏）。

## D.6 结论

**`P1_FIXED — READY_FOR_T8_REVIEW`**：T8 P1 阻断建议解除（java22/23/24 错误绑定消除、全量 442 OK、旧语言除设计内版本戳外零变化）。T9 仍待批准；未提交任何 commit。

---

# 最终状态

**`P1_FIXED — READY_FOR_T8_REVIEW`**（2026-10-15，PL-JAVA-P1-RESOLVER-SAFETY 完成）

- T0–T6 完成；T8 评审结论 CONDITIONAL（P1 阻断）；P1 定向修复已完成（附录 D）。
- 修复：resolver 阶梯 3/8 对 type-target 引用排除可调用 kind（metadata 门控，仅 Java 触发）+ CALL_KIND_VERSION 1→2；java22/23/24 证明错误绑定消除。
- 验证：25 java tests + 全量 **442 tests OK**；四表 parity 除设计内版本戳外 IDENTICAL；Python pin 固化、C/C++ 零触发。
- 待办：T8 复审解除阻断 → 批准 T9（语义后端基准，正交）。依据任务约束未提交任何 commit。

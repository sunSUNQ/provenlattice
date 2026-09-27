# AGENTS.md — ProvenLattice 项目速览

> 给 AI Agent(和未来的你)的快速上手指南。详细设计见 `docs/`,运行时约定以代码和测试为准。
>
> **⚠️ 重开会话请先跳读 [`附录 A`](#附录-a--存储特征画像与规模评估2026-09-16--09-17-会话) 和 [`附录 B`](#附录-b--v2-稀疏语义程序图本仓实施计划2026-09-18-会话)** —— 附录 A 有实测数据、已修复的代码、**阶段 0 已全部完成（0.1–0.4），下一步阶段 1（拆冷热）** 和规模演进计划；附录 B 是**面向缺陷检测的 V2 实施计划**（含 4 个必须先补的架构缺口）。
> 正文（上面到「本机搭建与执行记录」为止）记录的是 2026-09-15 及之前的稳定状态。

## 这是什么

ProvenLattice 是一个面向 Code Agent 的**可追溯分层工程证据图**研究项目:把代码结构、规范/需求文档等多源信息组织成可查询、可增量维护的图,为 Agent 提供任务相关的结构化工程上下文。当前覆盖 Python / C / C++ 的 CodeGraph + Markdown 知识层 + 分支/会话 Overlay + 检索实验 harness。

**明确不含**:Embedding、Vector DB、LLM linker、MCP、UI、Runtime Log、Commit History(见路线图)。

## 本机运行环境

- Python 3.12.10:`D:\program\Python312\python.exe`(已加入用户 PATH,排在 PATH 最前)
- CLI:`D:\program\Python312\Scripts\provenlattice.exe`(pip 生成的启动器壳,逻辑全在 `src/provenlattice/cli.py:main`)
- 已执行 `pip install -e .`(editable 安装):D 盘 site-packages 里的 `__editable__.provenlattice-1.0.0.pth` 指向本仓 `src\`,**改源码立即生效**
- 新开的终端可直接用 `provenlattice` / `python` 命令;旧终端需重开或刷新 PATH,也可用 `python -m provenlattice` 等价
- 网络慢:装包加 `-i https://pypi.tuna.tsinghua.edu.cn/simple`;下 Python 安装包走华为云镜像 `https://mirrors.huaweicloud.com/python/3.12.10/`

## 快速开始(核心链路)

```powershell
provenlattice index <repo> --json     # 扫描+解析+建图+分片 → SQLite
provenlattice knowledge <repo> --json # 知识层:Markdown 文档 → 代码证据边
provenlattice status --database <repo>\.provenlattice\codegraph.db --json
provenlattice symbol <name> --database ... --json          # 按名字查符号
provenlattice callers|callees|references --database ... --json
provenlattice implemented REQ-XXX-001 --database ... --json # 需求 → 实现
provenlattice evidence --status unresolved|ambiguous --database ... --json
provenlattice update <repo> --json     # 增量更新,只重解析变化的文件
```

本机自带的测试小仓:`tests/fixture_repo`(Python)、`tests/fixture_knowledge`(C++ + Markdown 规范,最完整)、`examples/demo/repository`(最小)。测试/演示:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v        # 140 项测试
python examples/demo/run_demo.py               # index→query→改文件→update→再查
```

## 架构与模块(`src/provenlattice/`)

```text
scanner → parsing(tree-sitter) → graph → shard → storage(SQLite) → query
                                        ↑ knowledge / overlay / incremental
```

| 模块 | 职责 |
|---|---|
| `cli.py` | argparse CLI,30+ 子命令入口 |
| `models.py` | Node / Edge / Shard / Delta / Metrics 数据模型 |
| `identity.py` | 所有稳定 ID 的 SHA-256 生成规则(改行号不变、改签名才变) |
| `scanner.py` | 文件扫描与内容哈希 |
| `parsing/` | tree-sitter 适配器:`base.py` / `python.py` / `cpp.py` / `tree_sitter.py` |
| `graph.py` | `full_index` 建图主流程 |
| `shard.py` | 分片策略(Directory/BuildAware/Structural)、fingerprint、资格校验 |
| `storage.py` | `SQLiteStorage` 存取 |
| `query.py` | `GraphQuery` 查询 API(最大模块) |
| `resolver.py` | 引用解析:resolved / ambiguous / unresolved 三态判定 |
| `evidence.py` | 证据 ID、排序、EvidenceBundle、citation 解析 |
| `knowledge.py` | 知识层:Markdown 段落/anchor 提取、CrossLayerResolver |
| `incremental.py` | `incremental_update`,与 full 严格一致(parity) |
| `impact.py` | 变更影响面(一阶保守边界) |
| `overlay.py` | `OverlayStore`:分支/会话 delta、tombstone、冲突检测 |

## 存储格式

每个被索引的仓库在其根下生成 `.provenlattice\codegraph.db`(已 gitignore),单个 SQLite 文件,14 张表:`files` / `nodes` / `edges` / `shards` / `shard_edges` / `raw_references` / `raw_evidence_links` / `repositories` / `file_state` / `document_state` / `graph_generation` / `semantic_events` / `semantic_fingerprint` / `semantic_edges`。

约定:ID 均为 64 位十六进制 SHA-256;`metadata` 列存 JSON 文本;`generation` 列是图代数(全量=1,每次增量 +1);CLI 的 `--json` 只是输出格式,持久化就是 SQLite。

## 重要契约

- **三态证据**:只有唯一 resolved 的引用才成边;ambiguous/unresolved 保留候选与 provenance,绝不伪造边(C++ 宏/模板/虚调用可合法 unresolved)
- **Full/Incremental/Overlay parity**:增量结果必须与全量重建一致,测试兜底
- **Overlay 优先级**:Session > Branch > Base 合成查询,支持 commit/discard/rebase
- **确定性优先**:图构建与评估器全部确定性,无随机;实验 harness 冻结任务/模型/提示词,只变检索方式
- 测试与实验契约的权威来源是 `tests/`(140 项),改代码先跑测试

## 文档与实验入口

- 设计:`docs/design-v0.md`(V0.x)、`docs/design-v1.md`(V1.0)、`docs/design-v1-r1.md`
- 路线图:`docs/roadmap.md`;阶段报告:`docs/provenlattice-phase-report-2026-09.md`
- 结果基准:`docs/benchmarks/`;发布记录:`docs/releases/`
- 检索实验:`experiments/retrieval-v1/`(R1 harness)、`experiments/retrieval-v2/`(R2/R2.1/R2.3)
- 图保真度:`experiments/fidelity_v1/`(人工金标双盲标注,依赖仓外 V0.2 数据库)
- 定量脚本:`benchmarks/`

## 本机搭建与执行记录(2026-09-14 ~ 09-15)

按时间顺序记录本机环境搭建与实际执行,供复现和排查。

1. **安装 Python 3.12.10(第 1 次,C 盘)**:winget 卡死 → 改 curl 下载 python.org 安装包(仅 7KB/s 太慢)→ 换华为云镜像(3.5MB/s)断点续传完成 → 数字签名校验(PSF Valid)→ `/quiet InstallAllUsers=0 PrependPath=1` 装到 `C:\Users\kyber\AppData\Local\Programs\Python\Python312`
2. **安装项目依赖**:`python -m pip install -e .`(清华镜像)→ tree-sitter 0.26.0 / python 0.25.0 / c 0.24.2 / cpp 0.23.4;生成 `provenlattice.exe`
3. **首次验证**:`PYTHONPATH=src python -m unittest discover -s tests -v` → 54/54 OK;`python examples/demo/run_demo.py` → 通过;CLI 30+ 子命令可用
4. **首次实测(临时目录)**:`tests/fixture_knowledge` 复制到 `C:\Users\kyber\AppData\Local\Temp\pl-demo\test-repo` → `index`(3 文件/12 边)→ `knowledge`(4 resolved / 1 ambiguous / 1 unresolved)→ `implemented REQ-RECOVERY-001` → `evidence --status unresolved|ambiguous` → 加文件+改文件 → `update`(识别 add+modify,新符号 `extra` 可查)
5. **迁移到 D 盘(2026-09-15)**:同版本 installer 直接重装会忽略 TargetDir 只"修复"旧装 → 先经注册表 `UninstallString`(Package Cache 里的 bootstrapper)卸载 C 盘 Python → 再 `/quiet TargetDir=D:\program\Python312` 装到 D 盘 → 重新 `pip install -e .`(D 盘 python)→ `provenlattice.exe` 生成在 `D:\program\Python312\Scripts\`
6. **D 盘复验**:`D:\program\Python312\Scripts\provenlattice.exe --help` OK;D 盘工作区 `D:\代码理解\test-repo`(= fixture_knowledge 副本)index/knowledge 结果与第 4 步一致;54/54 测试 OK
7. **git pull(2026-09-15)**:快进 4 个提交(9-14),新增研究验证框架 V1、图保真度 fidelity_v1 试点与金标集、双盲标注协议、校准问题日志;`src/` 无改动

当前状态:环境在 D 盘(`D:\program\Python312`);测试工作区 `D:\代码理解\test-repo`(已索引,含 `.provenlattice\codegraph.db`);临时演示残留 `C:\Users\kyber\AppData\Local\Temp\pl-demo\` 可删。

常用执行顺序(在 D 盘工作区复现):

```powershell
cd D:\代码理解
Copy-Item -Recurse .\provenlattice\tests\fixture_knowledge .\test-repo -Force   # 或别的 fixture
provenlattice index .\test-repo --json
provenlattice knowledge .\test-repo --json
provenlattice status --database .\test-repo\.provenlattice\codegraph.db --json
provenlattice implemented REQ-RECOVERY-001 --database .\test-repo\.provenlattice\codegraph.db --json
provenlattice evidence --status unresolved --database .\test-repo\.provenlattice\codegraph.db --json
provenlattice update .\test-repo --json
```

---

# 附录 A —— 存储特征画像与规模评估（2026-09-16 ~ 09-17 会话）

> 本节是跨会话续接记录。**所有数字均为本机实测**，复现命令见 A.9。
> 目标：把这个项目推到**几百万行代码**规模供 Code Agent 使用。

## A.0 TL;DR —— 当前进度

| 项 | 状态 |
|---|---|
| 环境验证 + 核心链路实测 | ✅ 完成 |
| 存储特征全面画像（11 张表） | ✅ 完成 |
| 技术定位（图类型 / 存储方式） | ✅ 完成 |
| **百万行规模体检** | ✅ 完成 → **发现 3 个阻塞问题** |
| `file_states()` 跨仓泄漏修复 | ✅ 已改码，**未提交**（0.1） |
| 阶段 0（frontier 上限 / 全表 dump / 表达式索引） | ✅ **四项全部完成**：frontier 已修（0.2）、定向读取已落地（0.3）、layer 表达式索引已验证+测试（0.4），均见 A.5 执行记录 ← **下一步：阶段 1（拆冷热）** |
| 阶段 1~3（拆冷热 / 内存图 / 分片快照） | ⬜ 未开始 |

**当前 git 状态**：0.1/0.2 修复与附录 B 阶段 2 的一批改动**已修改未提交**；`AGENTS.md` 未跟踪。

**一句话结论**：现有设计在 ~84 文件规模下表现优秀，但在**百万行会撞 3 堵墙**，其中一堵（frontier 上限）**已复现为硬崩溃**。推荐演进方向是「**热拓扑 / 冷证据 / 冻快照**」三层拆分，**明确不建议上 Neo4j**。

---

## A.1 本机实测数据（已验证）

### 核心链路（`tests/fixture_knowledge`，3 文件）

与 AGENTS.md 正文记录**逐项一致**：

```
index     → 3 files / 13 nodes / 12 edges / 2 shards / 0 parse_failures / 37ms
knowledge → 4 resolved / 1 ambiguous / 1 unresolved，4 条跨层边
implemented REQ-RECOVERY-001 → 命中 src/recovery.cpp:10
```
 
### 中等规模（**把本仓自己索引**，84 文件 / 10,115 行）

```
index      894 ms      84 files / 644 nodes / 2604 edges / 11 shards / 0 parse_failures
DB         26.8 MB     raw_references 25040 | nodes 644 | edges 2604
raw_refs   25040 → resolved 3983 / ambiguous 890 / unresolved 20167
update(空转) 267 ms 墙钟（含解释器启动 ~100ms + import 56ms + 全表载入 ~116ms）
```

### 重要：bash 环境下的 PATH 陷阱

AGENTS.md 正文说 `provenlattice` 已进 PATH —— **那是 PowerShell**。在 Git Bash / Claude Code 的 shell 里：

```bash
# ✗ 会 command not found
provenlattice --help
# ✗ 会命中 WindowsApps 商店桩，静默无输出
python -c "..."
# ✓ 必须用绝对路径
"D:/program/Python312/Scripts/provenlattice.exe" --help
"D:/program/Python312/python.exe" -c "..."
```

---

## A.2 存储特征画像（11 张表实测）

### 物理形态

| 维度 | 事实 |
|---|---|
| 载体 | 单个 SQLite 文件 `<repo>/.provenlattice/codegraph.db`，原地生成，已 gitignore |
| 依赖 | Python stdlib `sqlite3`，无 ORM / 无服务 / 无迁移框架 |
| 粒度 | 一仓一库 |
| Overlay | **独立的另一个 db 文件**（`overlay_metadata` + `overlay_deltas` 两张表），**不在这 11 张表里** |
| 索引 | 16 个 B-tree |

### ID 方案：内容寻址，无自增主键

所有主键是 `TEXT`，格式 `<语义前缀>:<64位 SHA-256>`，前缀有 `repo/file/symbol/edge/shard/reference/evidence/overlay`。

```python
# identity.py
symbol_id(repo_id, relative_path, kind, qualified_name, signature)
#                                                        ^^^^^^^^ 不含行号
```

**推论（整个系统的地基）**：
- 改行号 → ID 不变 → 增量能识别「同一符号，位置变了」
- 改签名/文件名 → ID 全变 → 表现为 **delete + insert，不是 update**
- 图上的「同一性」= **结构同一性**，不是历史同一性

### 关系完整性：全部交给应用层

```sql
PRAGMA foreign_keys = OFF;   -- 无一条 FOREIGN KEY，无级联删除
```

### 混合模型：列 + JSON 逃生舱

| 存成**列**（要索引） | 存成 **JSON 文本** |
|---|---|
| `name` `qualified_name` `kind` `language` | `metadata` |
| `status` `confidence` `provenance` `generation` | `candidate_symbols` |
| `start_line` `end_line` `source_hash` | `public_symbols` `metrics` |

写入统一 `json.dumps(..., sort_keys=True)` —— **确定性要求**，保证字节级可复现。

代价：**`json_extract` 被当作查询列用，但没有对应索引**。实测：

```
WHERE json_extract(metadata,'$.layer')='knowledge'   → SCAN nodes      9.69 ms
WHERE json_extract(metadata,'$.raw_evidence_link_id')→ SCAN edges      1.07 ms
WHERE src_id='x'                                     → COVERING INDEX  0.01 ms
```

**相差约 1000 倍。**这是当前最廉价的优化点。

### 写入模式：快照覆盖，不是 append-only

`SQLiteStorage.replace_snapshot()` 先 `DELETE FROM` 7 张表再全量重插。**但有一条例外**：

```sql
DELETE FROM nodes WHERE COALESCE(json_extract(metadata,'$.layer'),'code') != 'knowledge'
```

→ **代码图与知识图同库不同寿命**，重跑 `index` 不会冲掉 `knowledge` 层。两层可独立重建。

### generation：全局单调代数 + 只增不删的历史

- `repositories.current_generation` + **每张表都有一列 `generation`**
- `graph_generation` 表保留**每次构建的一行** + 完整 metrics JSON
- ⚠️ **无清理逻辑**。反复 `index` 会一直涨（正确姿势是用 `update`）

### 物化冗余：`shard_edges`

跨片边的 `src_shard_id`/`dst_shard_id`/`scope='boundary'` **本来就在 `edges.metadata` 里**，还额外抽一份进 `shard_edges`（空间换查询）。`storage.py:108` 有一段一次性回填，专给 V0.2 老快照补这个反向索引。

### 边的可信度：策略等级标注，不是概率

confidence 是**解析策略的固定常数**，同策略永远同值 → 完全确定性。

| provenance | confidence | 本仓条数 |
|---|---:|---:|
| `unique_symbol_resolution` | 0.75 | 928 |
| `same_file_resolution` | 0.98 | 744 |
| `tree_sitter_syntax` | 1.0 | 528 |
| `import_resolution` | 1.0 | 157 |
| `filesystem_scan` | 1.0 | 115 |
| `qualified_name_resolution` | 0.99 | 72 |
| `unique_imported_symbol_resolution` | 0.95 | 57 |
| `include_resolution` | 0.9 | 3 |

### 分片指纹：只认公开 API 签名

```python
api_fingerprint = sha256("\n".join(sorted(
    f"{kind}|{qualified_name}|{signature}" for public symbols   # 7 种 kind
)))
boundary_dirty = (sid in old) and (old[sid] != new_hash)
```

**纯函数体改动 / 私有符号改动 → 指纹不变 → 不触发跨片重算。**

### 空间画像（26.8 MB）

| 表 | 体积 | 占比 | 行数 |
|---|---:|---:|---:|
| **raw_references** | **9.31 MB** | **57.4%** | **25,040** |
| nodes | 5.27 MB | 32.5% | 644 |
| edges | 1.36 MB | 8.4% | 2,604 |
| shard_edges | 0.20 MB | 1.2% | 708 |
| 其余 | ~0.08 MB | 0.5% | — |

**最反直觉的一点** —— 最大表 `raw_references` 里 **80.5% 是 unresolved**：

| status | 条数 | 平均 candidate_symbols |
|---|---:|---:|
| unresolved | 20,167 | **2 字节**（即 `[]`） |
| resolved | 3,983 | 75 字节 |
| ambiguous | 890 | **349 字节** |

→ **unresolved 是「稀」的，ambiguous 是「胖」的。** 设计取舍很清楚：**宁可留下所有解析失败的引用，也不丢证据**。

---

## A.3 技术定位：图类型 vs 存储方式

### 图类型 = **Code KG**（**不是 CPG**）

| 类型 | 有无 | 依据（实测） |
|---|---|---|
| AST | ❌ | tree-sitter AST 遍历完即拍平，**树本身丢弃** |
| CFG | ❌ | 边类型无任何分支/跳转/异常流 |
| DFG | ❌ | 无 def-use / reaching-definition |
| Call Graph | ✅ | `CALLS` 939 条；resolver 五级策略阶梯 |
| CPG | ❌ | AST/CFG/DFG 三缺其三 |
| **Code KG** | ✅ | 节点最细到 Method，**且有文档↔代码跨层边** |

```
节点 kind：Method 251 / Function 212 / File 84 / Class 54 / Directory 31 /
          Namespace 5 / Type 3 / Interface 3 / Repository 1
代码层边：CONTAINS · DEFINES · CALLS · REFERENCES · IMPORTS · IMPLEMENTS
知识层边：CONTAINS(文档→章节) · DESCRIBES · CONSTRAINS · IMPLEMENTED_BY · VERIFIED_BY
```

**节点最细只到 Method，无语句级/表达式级节点** → 粒度中/粗，吻合 Code KG。

### 存储方式 = **SQLite 哑存储 + 810 行 Python 自研图引擎**

```
storage.py (328 行)  ←→  query.py (810 行，全项目最大)
   哑行存储                  真正的图引擎
```

`SQLiteStorage` **不知道「图」是什么** —— 只做建表 / 覆盖写 / 裸 SQL / 拆 JSON。图的语义全在 `query.py` / `resolver.py` / `knowledge.py`。

**因此它是两个方案格的杂交：存储底座 = PostgreSQL 那格；图语义 = 自定义 Graph Engine 那格。**

### 多跳能力：**⭐⭐（实测确认）**

`query.py:415` `get_subgraph` 是**应用层 BFS，一跳一次 SQL 往返**：

```python
for _ in range(max_hops):
    edges = self.view.query("Edge",
        f"SELECT * FROM edges WHERE src_id IN ({placeholders}) "
        f"OR dst_id IN ({placeholders})", ...)
```

全局 grep 确认：**无 `WITH RECURSIVE`、无 networkx、无任何图算法**（pagerank / 最短路 / 连通分量均无）。

### 迁移难度评估（关键事实）

```
query.py 对存储的耦合：
  self.view.*     39 次   ← 读路径全走抽象
  self.storage.*   5 次   ← 仅 _source_path + status() 两处琐事
```

但 `view.query(entity_type, sql, params, predicate)` **透传裸 SQL** → **抽象是漏的**。

| 模块 | SQL 行 | json_extract | 迁移阻力 |
|---|---:|---:|---|
| `resolver.py` | **0** | 0 | 🟢 **零**（纯 Python，只吃 Node 列表） |
| `query.py` | 18 | **0** | 🟢 低（纯 ANSI） |
| `overlay.py` | 15 | 0 | 🟡 中（merge 语义特殊） |
| `incremental.py` | 1 | 0 | 🟡 中（见 A.4 P1） |
| `storage.py` | 32 | 8 | 🟡 中（可整体替换） |
| `knowledge.py` | 33 | **14** | 🔴 高（把 JSON 当查询列用） |

---

## A.4 规模体检：百万行会撞什么墙

### 外推基数（实测，本仓 10,115 行）

| 每千行 | 条数 |
|---|---:|
| nodes | 63.7 |
| edges | 257.4 |
| **raw_references** | **2,475.5** |
| DB 体积 | 2.77 MB |

### 外推表

| 代码量 | nodes | edges | raw_refs | DB | **update 前置内存** | raw_refs 载入 |
|---:|---:|---:|---:|---:|---:|---:|
| 10 万行 | 6.4k | 25.7k | 248k | 0.3GB | 0.4GB | 1.0s |
| **100 万行** | 63.7k | 257k | 2.48M | 2.6GB | **4.0GB** | 9.5s |
| **300 万行** | 191k | 772k | 7.4M | **7.8GB** | **12.0GB** | **28.6s** |
| 1000 万行 | 637k | 2.57M | 24.8M | 25.9GB | 40.1GB | 95.3s |

> ⚠️ 外推基数只有**一个 10k 行的样本**，且是 reference 密度偏高的库代码。真实工程仓会有偏差（C++ 头文件、生成代码、vendored 依赖会拉高），但**量级是对的**。

### 三个阻塞问题

| # | 问题 | 300 万行表现 | 性质 | 位置 |
|---|---|---|---|---|
| **P1** | 三张全表 dump | 每次 update **吃 12GB 内存** | 🔴 致命 | `incremental.py:33-36` |
| **P2** | 多跳 frontier 用 `IN (...)` 绑定 | **frontier > 16,383 直接崩** | 🔴 **已复现** | `query.py:427-431` |
| **P3** | 单文件 7.8GB SQLite | 冻存/diff/gitignore 工作流崩 | 🟠 工作流 | 架构层 |

#### P2 —— 硬崩溃（已用真实管线复现）

```python
placeholders = ",".join("?" for _ in frontier)
"SELECT * FROM edges WHERE src_id IN ({placeholders}) OR dst_id IN ({placeholders})"
(*values, *values)        # ← 同一份 frontier 传了两次！
```

SQLite 上限 32,766 个绑定变量，**除以 2 → frontier 超 16,383 个节点必崩**。

**复现（`D:\代码理解\pl-scale-test\`，6 万行合成仓，1 个 hub + 2 万调用者）**：

```
1 跳: OK, 20003 节点
2 跳: 崩溃 -> sqlite3.OperationalError: too many SQL variables
```

**百万行代码里 hub 级符号（`log()`、基类、被广泛 import 的工具模块）超 16,383 个邻居是常态** —— 而 Agent 的高价值查询恰恰是 3~4 跳。

#### P1 —— 过读约 1600 倍（实测）

```
raw_references 全表载入   96.4 ms  (25040 行)   ← 最大单项
nodes 全表载入             6.1 ms  (644 行)
edges 全表载入             6.1 ms  (2604 行)
三张表同时驻留 Python 内存 41.5 MB (peak)
─────────────────────────────────────────
而它真正需要的：某文件的 45 个节点，过滤耗时 0.06 ms
```

且**空转也要付** —— `incremental.py` 的 early-exit 在**第 47 行**，三张全表 dump 在**第 33-36 行**。

### 多跳实测：真实图的「小世界」特性

锚点 `GraphQuery.status`（本仓 644 节点 / 2604 边）：

| 跳数 | 节点 | 边 | 耗时 | 含义 |
|---:|---:|---:|---:|---|
| 0 | 1 | 0 | 12.9ms | 只有自己（含冷启动） |
| 1 | 36 | 39 | 5.4ms | 直接邻居 |
| 2 | 254 | 578 | 41.4ms | 邻居的邻居 |
| 3 | **484** | **1977** | 121.3ms | **已是全图的 75%** |
| 4 | 568 | 2326 | 138.5ms | 全图的 88% |

**两个关键事实**：
1. **真实图很「小」** —— 3 跳吃掉 75% 节点。多跳不是越深越有用，**3~4 跳就饱和**。
2. **但这恰恰是坏消息** —— 既然 3 跳 ≈ 全图，那么**「多跳性能」就等于「全图遍历性能」**。优化多跳 = 优化全图遍历，是同一件事。

---

## A.5 已修改的代码

### `storage.py:152` `file_states()` 跨仓泄漏 —— ✅ 已修复

**问题**：`file_state` 表**根本没有 `repo_id` 列**，所以参数收了但无法过滤（不是「忘了加 WHERE」）。

```python
# 修复前
def file_states(self, repo_id: str) -> dict[str, dict]:
    rows = self.connection.execute(
        "SELECT file_id, path, source_hash, generation FROM file_state"   # ← repo_id 没进 WHERE
    ).fetchall()
```

**修复**（不改 schema、零迁移，通过 `files` 表 join 取 repo_id）：

```python
# 修复后
def file_states(self, repo_id: str) -> dict[str, dict]:
    # file_state carries no repo_id of its own; scope it through files so a
    # database holding more than one repository cannot leak states across.
    rows = self.connection.execute(
        """SELECT state.file_id, state.path, state.source_hash, state.generation
           FROM file_state AS state
           JOIN files ON files.file_id = state.file_id
           WHERE files.repo_id = ?""",
        (repo_id,),
    ).fetchall()
    return {row["path"]: dict(row) for row in rows}
```

**验证**：
- 54/54 测试通过
- 构造双仓 db：修复前 `repo:A` / `repo:B` 都返回 `{'A/a.py','B/a.py'}`；修复后正确隔离为 `['A/a.py']` / `['B/a.py']`

**当前状态**：**已修改，未提交**。单仓单库下此 bug 无实际影响，但多仓共库时会静默串仓。

### 阶段 0.2 执行记录（2026-09-21）—— `IN (...)` frontier 硬崩溃 ✅ 已修复

**问题**（P2，本附录第 398 行）：`get_subgraph` 把 frontier 绑定进 `src_id IN (...)` 和 `dst_id IN (...)`，**同一份列表传两次**，SQLite 上限 32,766 个绑定变量 ÷ 2 → frontier 超 16,383 节点必崩。

**修复**：`storage.py` 新增 `id_filter()` 上下文管理器（`ID_BIND_LIMIT = 900`）——小集合照旧按占位符绑定；大集合物化进 `temp` 表，查询改为 `IN (SELECT id FROM temp.…)`，**调用方的绑定参数数量不再依赖集合大小**。`get_subgraph`、`overlay.by_ids`（已用）、`explain_module`、`references_for_names` 四处全部接入；`nodes/edges` 查询层其余 `IN` 都是固定常数组（`SYMBOL_KINDS` / `CROSS_RELATIONS`），无界风险已清零。

**验证**（三层）：

| 层 | 结果 |
|---|---|
| 单元回归 `tests/test_scale.py`（新增 2 项） | ✅ 100/100 全绿；变异验证：把 `get_subgraph` 改回原地绑定 → 测试精确复现 `too many SQL variables` |
| id_filter 机制两端钉死 | 900 以下走占位符、以上走临时表且参数数为 0，两路结果一致 |
| **真实管线复现**（`D:\代码理解\pl-scale-test\`，1 hub + 2 万调用者） | 修复前「2 跳 → 崩溃」；修复后 **2 跳 → 20,003 节点 / 40,002 边，1.8 s** |

**当前状态**：**已修改，未提交**（与 0.1 修复同批）。

### 阶段 0.3 执行记录（2026-09-21）—— 增量更新三张全表 dump → 定向读取 ✅ 已修复

**问题**（P1，本附录第 417 行）：每次 `incremental_update` 都整表读 `nodes` / `edges` / `raw_references`，且 `parser_cache` 先读一遍 File 节点的 `metadata.parsed`（占 nodes 表 94.8%），`snapshot_ids("nodes")` **再读同一份 fat JSON 一遍**。

**修复**（`storage.py` 新增 4 个定向加载器 + `incremental.py` 改接）：

| 加载器 | 用途 | 替换掉什么 |
|---|---|---|
| `snapshot_columns(table, cols)` | 只取调用方真正消费的列 | `snapshot_ids` 整行（含 fat metadata） |
| `nodes_metadata()` | `id → metadata` **只取非 File 节点** | File 的 parsed 缓存不再二次读取 |
| `nodes_for_files(file_ids)` | 变更文件的全部节点（符号 diff 专用） | 全表 + Python 过滤 |
| `boundary_edges()` | 只取 `scope='boundary'` 的边（影响面 frontier 唯一消费方） | 整张 edges 表 |

另：`raw_reference_cache` 增加 `exclude_file_ids` / `exclude_ids` 两个排除参数 —— resolver 只会复用「未变文件 + 未被波及」的记录（`_reuse_record` 的守卫条件），其余本来就要重新推导，加载它们是纯浪费。

**唯一的行为简化（有意的）**：`nodes_updated` 比较时，File 节点只比 `(source_hash, start_line, end_line)`，不再比 metadata。理由：File 的 metadata 是 parsed 缓存，**内容哈希不变它就不变**，等价性成立。

**验证**（三层）：

| 层 | 结果 |
|---|---|
| **新旧等价性**（临时还原旧整表逻辑 → 同 5 个编辑场景对拍 delta） | ✅ body / sig / add / delete / rename 五种编辑下，`nodes_added/removed/updated`、`edges_added/removed`、`references_reprocessed/reused`、`boundary_edges_reprocessed` **全部逐字段一致** |
| 新加载器对拍测试 `TargetedLoaderTests`（新增 6 项） | ✅ 106/106 全绿；每个加载器都与「全表 + Python 过滤」的旧结果逐行相等 |
| End-to-end parity（阶段 2 验收 ② 的事件层 parity + 集成测试） | ✅ 不回归 |

**实测读取量**（自索引，84 文件）：旧路径每次真实 update 至少读 **22.0 MB**（其中 File metadata 5.2 MB **被读两遍**）→ 新路径 **~5.9 MB + 按编辑量排除后的 refs**。百万行外推时这份 parsed 语料约 0.5–1 GB，消灭二次读取就是消灭 update 内存峰值的一半。

**当前状态**：**已修改，未提交**（与 0.1/0.2 修复同批）。

### 遗留观察：`file_state` 与 `files` 高度冗余

| 表 | 列 |
|---|---|
| `files` | file_id, repo_id, shard_id, path, language, source_hash, generation |
| `file_state` | file_id, path, source_hash, generation |

`file_state` 几乎是 `files` 的子集，两者在 `replace_snapshot` 中**同时删、同时插**，唯一用途是 `incremental.py:31`。**规模优化时可直接删掉这张表**（11 张 → 10 张，需同步改 AGENTS.md 正文）。

### 阶段 0.4 执行记录（2026-09-21）—— `layer` 表达式索引 ✅ 已验证

**来源说明（诚实记录）**：4 个索引的 DDL 在**附录 B 阶段 2 会话**（加 `semantic_events` 索引时）已顺手写进 `storage.py` SCHEMA，但**从未验证、无测试、无文档**，A.7 一直挂 ⬜。本阶段补齐的正是验证与钉子测试，DDL 本身未改。

**方案**（`storage.py:140-145`，4 个索引 = 2 种拼法 × 2 张表）：

| 索引 | 覆盖的查询拼法 |
|---|---|
| `idx_nodes_layer` / `idx_edges_layer` | `json_extract(metadata,'$.layer')='knowledge'`（knowledge.py 的**无空格**拼法） |
| `idx_nodes_layer_coalesced` / `idx_edges_layer_coalesced` | `COALESCE(json_extract(metadata,'$.layer'),'code')`（`replace_snapshot` 的清理谓词） |

- 表达式索引按**解析后的表达式**匹配，SQL 里空格差异不影响命中（已实测证实）。
- `!=` 谓词做不了等值 SEARCH，但 COALESCE 索引**覆盖**该表达式，COUNT/DELETE 仍可走索引扫描而不读 metadata 大字段。

**实测**（真实规模库 `pl-scale-test` 20,003 nodes / 40,002 edges 的副本，best-of-5）：

| 查询 | 带索引 | 无索引 | 加速 | 计划 |
|---|---|---|---|---|
| nodes 裸提取 | 0.014 ms | 18.3 ms | **1300×** | `SEARCH nodes USING INDEX idx_nodes_layer` |
| edges 裸提取 | 0.014 ms | 20.3 ms | **1470×** | `SEARCH edges USING INDEX idx_edges_layer` |
| nodes `COALESCE != 'knowledge'` COUNT | 0.63 ms | 18.6 ms | 30× | `SCAN … USING COVERING INDEX idx_nodes_layer_coalesced`（索引自答，metadata 不读） |
| edges 同款 | 1.25 ms | 20.5 ms | 16× | 同上 |

B.4 的验收标准「`SCAN nodes` 变 `SEARCH`（9.69 ms → 0.01 ms）」复现且更优。

**测试**：`test_integration.py` 新增 `ExpressionIndexTests` 3 项——钉的是**查询计划**而非 DDL 存在性：裸谓词（knowledge.py 原样无空格拼法）必须 `SEARCH … idx_nodes_layer`；edges 同款；`COALESCE !=` COUNT 必须走 `USING COVERING INDEX`（metadata 永不被读）。每个 EXPLAIN 用**全新连接**——sqlite3 语句缓存会让 DROP INDEX 后的 EXPLAIN 仍报旧计划，这是测量时踩到的真坑。**109/109 全绿**。

**范围外实测观察（下一步候选）**：0.3 接线的 `boundary_edges()`（`json_extract(metadata,'$.scope')='boundary'`）**无索引**，实测每次全表扫 **21 ms**（edges metadata 10.8 MB）。线性外推到百万行会到 ~0.5 s/update。是否给 `$.scope` 建表达式索引，与阶段 1（拆冷热）一起决策。

**当前状态**：已修改，未提交（与 0.1–0.3 同批）。

---

## A.6 推荐架构：「热拓扑 / 冷证据 / 冻快照」三层

**核心判断 —— 当前架构把三种访问模式完全不同的数据塞进了同一个 SQLite：**

```
数据              规模(300万行)  访问模式              现在放哪   该放哪
──────────────────────────────────────────────────────────────
图拓扑            191k + 772k   遍历，每次查询都碰       SQLite   → 热：内存
原始引用(证据)     7.4M          只在要证据时按 id 查     SQLite   → 冷：列存
历史快照          每代一份       几乎不读，只冻存         (无)     → 冻：不可变
```

**`raw_references` 占 74% 行数，却是最冷的数据** —— 只在 Agent 溯源时读到，但每次 `update` 都被全量拉进内存。**这是当前最大的错配。**

### 目标结构

```
┌─ 热：图拓扑 ─────────────────────────────────┐
│  nodes + edges  →  内存 CSR 邻接表             │
│  191k 节点 + 772k 边 ≈ 100~200 MB             │
│  一次载入，多跳遍历变纯内存操作                 │
│  → 多跳 ⭐⭐⭐⭐⭐，frontier 上限问题消失        │
└──────────────────────────────────────────────┘
              ↕ 按需
┌─ 冷：证据层 ─────────────────────────────────┐
│  raw_references  →  Parquet 列存               │
│  7.4M 行，status 仅 3 值 + candidate 大量重复   │
│  字典编码后 2.7GB → 数百 MB                    │
│  不进内存，不阻塞遍历                           │
└──────────────────────────────────────────────┘
              ↕ 冻结
┌─ 冻：快照层 ─────────────────────────────────┐
│  每代 → 不可变分片 + manifest                  │
│  增量的天然载体：新分片 + 复用旧分片            │
│  冻存 = 拷贝 manifest 指向的文件               │
└──────────────────────────────────────────────┘
```

### 选型理由

| 层 | 选型 | 理由 |
|---|---|---|
| 热 | **内存 CSR** | 772k 边 × 2 方向 × 4 字节 ≈ **6MB**。多跳在内存里是纳秒级。且**完全确定性**（遍历序自己控制） |
| 冷 | **Parquet** | `raw_references` 两大膨胀源（`status` 3 个取值、`candidate_symbols` 80% 是 `"[]"`）正好是字典编码 + RLE 的完美目标 |
| 冻 | **manifest + 分片** | **恰好与已有 generation 模型天然对齐**，不是新概念 |

### ❌ 为什么不建议上 Neo4j

1. **会打碎唯一护城河** —— 遍历顺序不保证，而项目建立在 `sorted()` + `sort_keys=True` 的字节级确定性上（金标双盲实验的前提）
2. **你不需要它** —— Neo4j 解决的是「图太大放不下内存」，**而你的图只有 6MB 边**。这个问题在你这个规模根本不存在
3. **Overlay 模型无处安放** —— Neo4j 没有「基础图 + delta 叠层」的廉价原语，三条路（三库合并 / 属性版本化 / composite database）都比现状差
4. **7.4M 条 raw_reference 进 Neo4j 是灾难性建模**

### 备选：DuckDB + Parquet

适合**冷层 + 冻层**，不适合热层（无 index-free adjacency，多跳只能到 ⭐⭐⭐）。
优势：`overlay.py:357` 的手工 merge 可变成一句 `UNION ALL ... QUALIFY row_number() OVER (PARTITION BY id ORDER BY layer DESC) = 1`；`knowledge.py` 的 14 处 `json_extract` 可变成原生 struct 访问。
⚠️ **DuckDB 启动约 50ms，当前小仓查询只要 6ms** → 当前规模下迁移会**更慢**，收益全在大规模。

---

## A.7 分阶段计划与进度

### 阶段 0 — 先止血（小改动、可回退、不碰任何契约）

| # | 项 | 状态 |
|---|---|---|
| 0.1 | `file_states` 跨仓泄漏 | ✅ **已完成**（见 A.5） |
| 0.2 | `query.py:427` 的 `IN (...)` frontier → **临时表** | ✅ **已完成**（2026-09-21，见 A.5「阶段 0.2 执行记录」） |
| 0.3 | `incremental.py:33-36` 三张全表 dump → **带 `WHERE` 的定向查询** | ✅ **已完成**（2026-09-21，见 A.5「阶段 0.3 执行记录」） |
| 0.4 | 给 `json_extract(metadata,'$.layer')` 建**表达式索引** | ✅ **已完成**（2026-09-21，见 A.5「阶段 0.4 执行记录」） |

> 四项都不动**三态证据 / Full-Incremental-Overlay parity / 确定性**这三个核心契约。

> **阶段 0 四项全部完成 ✅（2026-09-21）。下一步：阶段 1（拆冷热）。插入候选：给 `$.scope` 边界边建表达式索引（实测 21 ms/update，见 A.5「0.4 执行记录」的范围外观察），与阶段 1 一起决策。**

### 阶段 1 — 拆冷热（收益最大）

把 `raw_references` 从主库剥出去。主库 7.8GB → ~2GB，`update` 内存问题根治。

### 阶段 2 — 上内存图

`GraphView` 本就是内存 merge 引擎的雏形（`overlay.py:363-370` 已在内存里物化 + 打补丁）。从「每次查询物化」改成「常驻 CSR」，多跳进入 ⭐⭐⭐⭐⭐。

### 阶段 3 — 快照分片

配合正在做的 fidelity 金标冻存。

---

## A.8 常见问答（本次会话结论）

| 问题 | 结论 |
|---|---|
| **多跳是什么** | 从起点沿边连续走 N 步，可跨边类型、跨层 |
| **多跳影响什么** | 影响 Agent 能否回答真实工程问题。**1 跳是 lint，3~4 跳才是「Agent 价值：很高」的来源** |
| **多跳快有什么好处** | 实测 **3 跳 = 全图 75%**，所以**多跳性能 = 全图遍历性能**。Agent 每次提问都要走一遍 |
| **几百万行用什么** | **热拓扑（内存 CSR）/ 冷证据（Parquet）/ 冻快照（分片 + manifest）**，**不上 Neo4j** |
| **本项目是什么图** | **Code KG**（非 AST/CFG/DFG/CPG），节点到 Method 级 + 文档跨层边 |
| **本项目什么存储** | SQLite 哑存储 + 810 行 Python 自研图引擎。多跳 ⭐⭐，运维 ≈0，确定性 ⭐⭐⭐⭐⭐ |

### Agent 场景示例（说明多跳为何重要）

```
"REQ-RECOVERY-001 这个需求要改，哪些代码会受影响？"

REQ-RECOVERY-001
  →[IMPLEMENTED_BY]→ 符号
    →[CALLS 反向]→ 调用它的函数
      →[CONTAINS 反向]→ 所在文件
        →[IMPORTS]→ 跨模块
          →[DEPENDENCY]→ 换仓库
= 4~5 跳，跨 2 层
```

---

## A.9 复现命令

```bash
PL="D:/program/Python312/Scripts/provenlattice.exe"
PY="D:/program/Python312/python.exe"

# 全量索引本仓并看指标
$PL index . --json

# 多跳实测（跳数 vs 节点/边增长）
$PY - <<'EOF'
import sys, time
sys.path.insert(0, r"D:\代码理解\provenlattice_镜像版本\src")
from provenlattice.query import GraphQuery
db = r"D:\代码理解\provenlattice_镜像版本\.provenlattice\codegraph.db"
with GraphQuery(db) as q:
    for h in range(0, 5):
        t = time.perf_counter()
        r = q.get_subgraph("src.provenlattice.query.GraphQuery.status", max_hops=h, max_nodes=200000)
        print(f"{h} 跳: {len(r['data']['nodes'])} 节点 {len(r['data']['edges'])} 边 {(time.perf_counter()-t)*1000:.1f}ms")
EOF

# P2 崩溃复现（pl-scale-test 为 6 万行合成仓：1 hub + 2 万调用者）
$PL subgraph hub --max-hops 2 --max-nodes 100000 \
   --database "D:/代码理解/pl-scale-test/.provenlattice/codegraph.db" --json
# → sqlite3.OperationalError: too many SQL variables

# 表达式索引的 1000 倍差距
$PY -c "
import sqlite3
c=sqlite3.connect(r'D:\代码理解\provenlattice_镜像版本\.provenlattice\codegraph.db')
for q in [\"SELECT COUNT(*) FROM nodes WHERE json_extract(metadata,'\$.layer')='knowledge'\",
          \"SELECT COUNT(*) FROM edges WHERE src_id='x'\"]:
    print(' | '.join(r[3] for r in c.execute('EXPLAIN QUERY PLAN '+q)))
"

# 测试（改代码后必跑）
PYTHONPATH=src "D:/program/Python312/python.exe" -m unittest discover -s tests -v
```

---

## A.10 本次会话产生的临时产物

| 路径 | 内容 | 处理建议 |
|---|---|---|
| `D:\代码理解\pl-scale-test\` | 6 万行合成仓（1 hub + 2 万调用者），**P2 崩溃复现用** | 建议**保留**作回归测试 |
| `D:\代码理解\pl-smoke-20260916\` | `fixture_knowledge` 副本 + 其 DB | 可删 |
| `D:\代码理解\provenlattice_镜像版本\.provenlattice\` | 本仓自索引产物，26.8MB，已 gitignore | 可留（查询用） |
| `reademe`（仓库根） | **用户自己的会话笔记**（44,978 B UTF-8/CRLF），内容是本次会话问答的整理 | 未跟踪；归属用户，勿动 |

---

# 附录 B —— V2 稀疏语义程序图：本仓实施计划（2026-09-18 会话）

> 依据：仓库根 `ProvenLattice_Defect_Oriented_Sparse_Semantic_Graph_Design.md`（V2 设计草案）。
> 本附录把它翻译成**在本仓可执行的计划**，并补上设计文档没有覆盖的 4 个架构缺口。
> **本附录中所有数字均为 2026-09-18 实测**，复现命令见 B.8。

## B.0 TL;DR

| 项 | 结论 |
|---|---|
| 设计文档的总体判断 | ✅ **正确**，与附录 A 的「热/冷/冻」是同一套结论 |
| 可否直接开工 | ⚠️ 不能 —— **有 4 个架构缺口会让事件层在增量场景下失效**（见 B.2） |
| 与现有阶段的关系 | 附录 A 的**阶段 0 是硬前置**，且 P2 对缺陷检测**比对话场景更致命** |
| 事件层规模（百万行外推） | **0.25 ~ 1.0 GB**，与 `raw_references` 同量级 → **必须走冷层，不能全进热图** |
| 最大的一处修正 | 事件身份必须做到**「方法级稳定」**，否则打碎增量与冻存 |
| 建议的第一个可证伪实验 | **阶段 4**（事件 + Sparse CFG 直接跑 RaceQuery），**不等 DFG** |
| **当前进度** | 附录 B **阶段 1（Evidence Matrix）、阶段 2（Semantic Event MVP）、阶段 3（Sparse CFG）、阶段 4（Typed Query 第一批）、阶段 4.5（Identity & Extraction Hardening）、阶段 5A（Access Layer）、阶段 5C（Contract / Ownership，含 5C-2 五条登记项）、阶段 5B（Sparse DFG Core + unknown 根成员保留身份 + errno 豁免 + 查询期参数绑定）、阶段 6（Typed Query 第二批：null_flow / use_after_free / double_free / taint_path / error_handling 五查询交付，`QUERY_NAMES` 八键；9.1 按裁定 D 用 CALL 点已有事实，零提取改动零重建；两个交付级缺陷已修：find_paths 悬崖 + 窗口上限钳制 4096；T1/T2 冻结对账闭环零未归因残差）已完成**（见 B.4 各执行记录；阶段 4 的 20 条裁定给出 V2 第一个质量基线 **0/20**，5C 验收① 13 条重定位 **10/13 关闭**，5B 的对比表把 1.1 从 557,315 收到 **10,420（−98.1%）/+绑定 14,439**，check13 在 5B 库上 **10/13 零回归**，阶段 6 交付态验收单 **16/16 分层与冻结口径零偏差**（9.1: 4,084/32,466 逐位 = T2 冻结），套件 **296/296**）；附录 A **阶段 0 四项全部完成**（0.1–0.4，见 A.5）← **下一步：附录 B 阶段 7（冷热拆分 + 分析副本）；阶段 6 验收单 32 条已裁（precision 1/32 = 0.031，contract 10 为 FP 主导成因，见 B.4 阶段 6 裁定结果段）** |

**一句话**：设计方向对，但「Semantic Event 是缺陷分析粒度」这句话要**加一个约束**——事件不能是「语句级节点」，只能是「方法内序号锚定的事件」，这是它能和现有 `symbol_id` 方案共存的前提。

---

## B.1 与附录 A 的关系

```
附录 A 阶段 0  止血（4 项）          ── 硬前置，P2 不修则影响面分析必崩
        ↓
附录 B 阶段 1  Evidence Matrix       ── 纯文档，不改码（设计文档 Phase 0）
附录 B 阶段 2  Semantic Event MVP    ── 设计文档 Phase 1
附录 B 阶段 3  Sparse CFG            ── 设计文档 Phase 2
附录 B 阶段 4  Typed Query 第一批    ── ★ 提前，不等 DFG（可证伪点）
附录 B 阶段 4.5 Identity/Extraction  ── ★ 2026-09-22 插入：修身份，不是新能力
附录 B 阶段 5A Access Layer (R/W)    ── ★ 2026-09-22 拆自阶段 5
附录 B 阶段 5B Sparse DFG Core       ── 设计文档 Phase 3（范围由 4.5+5A 的残差决定）
附录 B 阶段 5C Contract / Ownership  ── ★ 2026-09-22 拆自阶段 5：契约不是数据流
附录 B 阶段 6  Typed Query 第二批    ── 设计文档 Phase 4 剩余
附录 B 阶段 7  冷热拆分 + 分析副本   ── 附录 A 阶段 1 + 设计文档 §12.2
附录 B 阶段 8  Hot CSR               ── 附录 A 阶段 2 + 设计文档 Phase 5
附录 B 阶段 9  Local Deep Analysis   ── 设计文档 Phase 6
附录 B 阶段 10 快照分片              ── 附录 A 阶段 3
```

**四处顺序调整，都有理由：**

1. **阶段 0 必须最先** —— P2（frontier > 16,383 崩溃）在缺陷检测下**更致命**：影响面分析恰恰从 hub 出发（基类、被广泛 import 的工具模块——最危险的符号就是最热的符号），hub 邻居数必然超限。对话场景只是慢，缺陷场景是**核心功能不可用**。

2. **阶段 4 提到 DFG 之前** —— 设计文档把 Typed Query 排在 DFG（Phase 3）之后。但 `RaceQuery / ResourceLifetimeQuery / LockOrderQuery` **只需要 Event + CONTROL_REACHES，不需要数据流**。先用它们验证「事件+稀疏控制流够不够」，这是整个 V2 最大的可证伪假设；如果不够，DFG 的设计要改。**先做能推翻假设的实验，再做依赖假设的工作。**

3. **阶段 7/8 排在两个 query 之后** —— 先证正确性，再优化性能。在 84 文件规模下查询只要 6ms，CSR 的收益为 0（附录 A 已论证）。过早建 CSR = 优化一个还没验证对的查询。

4. **阶段 5 拆成 4.5 / 5A / 5B / 5C（2026-09-22 插入）** —— 阶段 4 的真实仓执行把原定义推翻了：候选生成只需要 AST 里已有的事实（便宜），确认需要跨过程推断（贵一个数量级），而 1.1 的候选爆炸（redis 557,315 / llama 1,463,722）主因是**局部变量同名**——一个符号表问题，不是数据流问题。**先修身份，再补访问层，最后才做 DFG；API 契约独立成层，因为它既不是 CFG 也不是 DFG。** 详见「阶段 4 执行记录 → 对阶段 5 定义的修订」。

---

## B.2 设计文档的 4 个架构缺口

> 这 4 条是本附录相对设计文档的**增量**。前 3 条不补，事件层在增量场景下会失效；第 4 条不补，热层会 OOM。

### B.2.1 事件身份必须「方法级稳定」（最重要）

设计文档 §5.2 的事件字段里有 `ordinal`，但**没有规定 `event_id` 怎么生成**。这里有两条路，只有一条能走：

| 方案 | event_id 构成 | 后果 |
|---|---|---|
| ❌ 语句级稳定身份 | `hash(file, line, ...)` | 上面改一行 → 后面全变 → 增量 delta 退化成噪声 |
| ✅ **方法级稳定身份** | `hash(owner_symbol_id, event_type, ordinal_in_method)` | 编辑**别的方法** → 本方法事件 ID 全不变 |

**关键性质**：`owner_symbol_id` 本身是编辑稳定的（`identity.py`：不含行号）。所以

- 改 A 方法 → 只有 A 的事件 churn，**有界**
- 跨方法的语义边（`DATA_FLOW_TO` M₁→M₂）以 `owner_symbol_id` 为锚，**A 改了不影响 B 的边**
- `CONTAINS(Method → Event)` 可以廉价重建

**必须写进 `identity.py` 的约定**（新增函数，不改现有 7 个）：

```python
event_id(owner_symbol_id, event_type, ordinal)      # ordinal = 方法内序号
semantic_edge_id(src_event_id, dst_event_id, relation, discriminator)
resource_id(owner_symbol_id, kind, name)            # Resource / Lock / ExecutionContext
```

> ⚠️ **推论**：事件**不是**「语句级节点」，它是「方法内序号锚定的事件」。设计文档 §25 第 3 条「增加 Semantic Event，作为真正的缺陷分析粒度」需要补这半句。**这也是 CPG 与 V2 的真正分界**——CPG 的节点是位置寻址的，V2 的事件是方法锚定的。

### B.2.2 现有 shard 指纹**抓不住**语义变化 → 必须新增语义指纹

这是最容易漏、后果最隐蔽的一条。现有指纹（`shard.py`）：

```python
api_fingerprint = sha256("\n".join(sorted(
    f"{kind}|{qualified_name}|{signature}" for public symbol   # 只有公开 API 签名
)))
boundary_dirty = (sid in old) and (old[sid] != new_hash)
```

**只认公开 API 签名，纯函数体改动 → 指纹不变 → 不触发跨片重算。**

- 对 Code KG：**正确**。拓扑确实没变。
- 对 V2：**致命**。语义事件**全部活在函数体里**——改一个函数体，它的 `ALLOC/RELEASE/READ/WRITE` 全变，跨方法的 `DATA_FLOW_TO`、`CONTROL_REACHES` 可能全错，**但指纹说 shard 没脏**。

→ **必须在 `shard.py` 增加第二类指纹**：

```python
semantic_fingerprint = sha256(事件类型多重集 + 方法签名 + 语义边端点摘要)
```

或退一步的**最小可行版本**：把「该 shard 内任一文件 `source_hash` 变化」当作语义脏标记（宁可多算，不可漏算）。**先上最小版本，等实测出过读成本再精化。**

> 这一条**现有 54 项测试测不出来**——parity 测试比的是 full vs incremental 的**结果一致**，而这里坏的是**触发条件**。必须新增针对性测试（见 B.4 阶段 2 验收）。

### B.2.3 解析缓存**已经在两处重复存**，事件层不能重蹈

**实测（这是设计文档写 §18「不存完整 AST」时不知道的既有事实）：**

| 位置 | 体积 | 内容 |
|---|---|---|
| `raw_references` 表 | **9.31 MB** / 25,040 行 | id / status / candidate_symbols / provenance / confidence |
| `nodes.metadata.parsed.references` | **4.70 MB** / 24,474 条 | 同一份引用的原始抽取结果 |

`nodes.metadata` 合计 **4.998 MB = nodes 表的 94.8%**（File 节点平均 **61,614 B/行**，最大单个 508 KB），其中 `parsed` 占 4.93 MB。**全库 16.23 MB 内容里约 4.8 MB 是重复的解析产物缓存。**

它的用途是 `parser_cache()`（`storage.py:164`）——让 `update` 不必重新解析未变文件。这是个**刻意的空间换时间**取舍，不是 bug。但它带来一个 V2 必须回答的问题：

> **事件抽取结果，是缓存还是每次重抽？**

| 方案 | 代价 |
|---|---|
| 缓存进 `parsed` | `parsed` 从 4.93 MB → 更大，且事件**又存两遍**（缓存 + 事件表） |
| 不缓存，每次重抽 | `update` 需重新解析每个变更文件（可接受，变更文件本来就少） |

**建议：事件不缓存进 `parsed`，只存事件表。** 理由：事件表本身就是「抽取结果」的持久化形式，再缓存一份是纯冗余；而变更文件重抽的成本本来就付。**设计文档 §18 的「不存」原则，要先对既有的 4.8 MB 冗余生效，再谈新增。**

### B.2.4 `ID → uint32` 映射不能是 Python dict

设计文档 §12.1 提出「持久化 SHA-256 ID → 运行时 uint32 ID」。方向对，但**实现方式会决定成败**：

百万行规模下事件约 **60 万 ~ 260 万**（B.5）。若用 Python `dict[str, int]`：

```
2.6M 条 × (64 字符 str ≈ 113 B + dict 条目开销 ≈ 100 B) ≈ 550 MB   ← 光是映射就吃掉整个预算
```

→ **必须是紧凑数组**：排好序的 `bytes` 数组（32 字节二进制 SHA-256）二分查找，或 `array('Q')` 存 (hash 前 8 字节 → uint32) 的开地址表。**这一条要在阶段 8 之前就定，因为它会影响事件表的主键存储格式（二进制 vs 十六进制文本）。**

> 顺带：现有 ID 全部是 **64 字符十六进制文本**（`nodes.id` 71 B/行）。转成 32 字节二进制可直接省一半。这是附录 A 没提、但 V2 规模下会变得重要的一个改动。

---

## B.3 代码落点表（本仓实测行数）

| 模块 | 现状 | V2 改动 | 性质 |
|---|---:|---|---|
| `identity.py` | 55 | +`event_id` / `semantic_edge_id` / `resource_id` | 新增（不改现有 7 个） |
| `models.py` | 245 | +`SemanticEvent` / `SemanticEdge` / `DefectEvidenceBundle`；`Edge` 可能需 `flags` | 扩展 |
| `parsing/events_cpp.py` | — | C/C++ AST → Semantic Event | **新增** |
| `parsing/events_python.py` | — | Python AST → Semantic Event | **新增** |
| `semantics/` | — | 事件抽取编排、关键词候选生成、Level 0/1/2 分级 | **新增** |
| `sparsecfg.py` | — | 事件级 `CONTROL_REACHES`（+ branch/exception/loop_back flags） | **新增** |
| `sparsedfg.py` | — | `DATA_FLOW_TO` / `PRODUCES` / `CONSUMES` / `MAY_ALIAS` | **新增** |
| `defect.py` | — | Typed Query 族（`RaceQuery` / `ResourceLifetimeQuery` / …） | **新增** |
| `storage.py` | 334 | +4 表：`semantic_events`、`semantic_fingerprint`（阶段 2）与 `semantic_edges`（阶段 3）已落地；`semantic_evidence` 随 `DefectEvidenceBundle`（阶段 4） | 扩展 |
| `shard.py` | 194 | **+语义指纹**（B.2.2） | 扩展 |
| `incremental.py` | 215 | +方法级脏传播；事件层 delta | 扩展 |
| `graph.py` | 229 | `full_index` 加 `extract → resolve → build` 语义三段 | 扩展 |
| `resolver.py` | 304 | **复用其纯 Python 三态模式**做 `SemanticRelationResolver`（`MAY_ALIAS` / `MAY_PARALLEL`） | 复用 |
| `overlay.py` | 551 | 事件/语义边纳入 `GraphView` delta 模型 | 扩展 |
| `query.py` | 810 | 保留 `get_subgraph`；Typed Query 走 `defect.py` | 扩展 |
| `evidence.py` | 155 | +`DefectEvidenceBundle`（facts / uncertain_facts / paths / missing_evidence） | 扩展 |
| `cli.py` | 167 | +`events` / `defect` 子命令 | 扩展 |
| `tests/` | 54 | +语义层 parity / 确定性 / 指纹触发 / 金标测试 | 扩展 |

**语言优先级：C/C++ 先行。** 理由：36 类缺陷矩阵（UAF / Double Free / Lock Order / Race）几乎是 C/C++ 专属；`fixture_knowledge` 是 C++；`fidelity_v1` 金标是 aria2/brpc/RocksDB。Python 侧（GC + GIL）缺陷价值低，**主要作用是 dogfood 增量与 parity**——本仓自己是 Python，改完能立刻自测。

---

## B.4 整体计划表

> 每阶段都有**可验收产出**。未写验收标准的阶段不许开工。

### 阶段 0 —— 止血（附录 A 原有，V2 硬前置）

| # | 内容 | 代码落点 | 验收 |
|---|---|---|---|
| 0.1 | `file_states()` 跨仓泄漏 | `storage.py:152` | ✅ 已完成（未提交） |
| 0.2 | frontier `IN (...)` → 临时表 + JOIN | `query.py:427-431` | ✅ 已完成（2026-09-21）：`pl-scale-test` 2 跳不再崩（20,003 节点 / 40,002 边）；见 A.5「阶段 0.2 执行记录」 |
| 0.3 | 三张全表 dump → 定向查询 | `incremental.py:33-36` | ✅ 已完成（2026-09-21）：读取量 22.0 MB → ~5.9 MB；等价性 5 场景对拍逐字段一致；106 项全过；见 A.5「阶段 0.3 执行记录」 |
| 0.4 | `json_extract(metadata,'$.layer')` 表达式索引 | `storage.py` SCHEMA | ✅ 已完成（2026-09-21）：`EXPLAIN QUERY PLAN` 由 `SCAN nodes` 变 `SEARCH`，真实库实测 **18.3 ms → 0.014 ms（1300×）**；3 项计划钉子测试，109/109；见 A.5「阶段 0.4 执行记录」 |

### 阶段 1 —— Evidence Matrix（纯文档）

| 内容 | 产出 | 验收 |
|---|---|---|
| 36 类缺陷 → Required Events / Relations / Optional / Disqualifying / AI-required Semantics | `计划文档/defect-evidence-matrix-v1.md` | 每类缺陷都能回答：「只有 Event+CFG 够不够？」并**明确标注哪几类必须 DFG** |

> 这一步**不改任何代码**。它是 V2 schema 的真实需求来源。**跳过它 = 按 CPG 的样子先建，再找能检什么。**

#### 阶段 1 执行记录（2026-09-20 ~ 09-21）—— ✅ 已完成

| 项 | 结果 |
|---|---|
| 分类学定稿（2026-09-20） | 按**代码操作种类**切分 9 大类 38 小类（设计文档「36 类」经裁决 #2/#3 调整为 38）；CWE 降为参考列（按「暂不核对」约束未逐条复核，7.2 的 CWE-374 已标记有误） |
| 「Event+CFG 够不够」全集回答（2026-09-20） | A/B/C 成本分级覆盖全部 38 条：**A = Event+Sparse CFG 够（13）；B = 必须 Sparse DFG（23）；C = 稀疏图不够、需局部深分析（2）** ——「哪几类必须 DFG」= B+C 共 25 条 |
| 优先族五字段展开（2026-09-21，执行裁决 #6） | 1.1 竞态 / 3.1 空指针 / 4.1 泄漏 / 4.2 双释放 / 4.3 释放后使用 补齐五字段 + A/B/C 复核（5 条初判全部维持；1.1、4.1 登记「候选生成 A / 确认滑向 B」两段性） |
| 其余 33 条五字段 | **按裁决 #6 明确不铺**——进入对应 typed query 实施时再展开 |
| 实现缺口（矩阵作为需求来源的核心产出） | `READ`/`WRITE` 事件（Level 1）与全部 Defect Semantic Relations 均不存在 —— 分别是阶段 3（`CONTROL_REACHES`）/ 阶段 4（typed queries 的共同前置）/ 阶段 5（`DATA_FLOW_TO`/`MAY_ALIAS`）的开工项 |
| 产出路径更正 | 计划表原写 `docs/defect-evidence-matrix-v1.md`，实际落在本目录 `计划文档/`（与其他附录文档同处），表中路径已更正 |

### 阶段 2 —— Semantic Event MVP

| 内容 | 产出 | 验收 |
|---|---|---|
| C/C++ 事件抽取（Level 0：`CALL/RETURN/THROW/ALLOC/RELEASE/LOCK/UNLOCK/ATOMIC/THREAD_*`） | `parsing/events_cpp.py`、`semantics/`、`identity.py` 新函数、`storage.py` +2 表 | ① 在 `fixture_knowledge` 上能抽出事件并落库 ② **事件层 full/incremental parity 通过** ③ **B.2.2 指纹触发测试**：只改函数体（不改签名）→ 语义脏必须被识别 ④ 34 项旧测试不回归 |
| 关键词 → 候选（不承担判定） | `semantics/candidates.py` | 候选召回率有基线记录（不设阈值，先记录） |

> ⚠️ **③ 是本阶段最容易漏的验收项**，也是唯一一个现有测试体系完全覆盖不到的。

#### 阶段 2 执行记录（2026-09-21 会话）—— 四条验收全部通过

| # | 验收项 | 结果 |
|---|---|---|
| ① | `fixture_knowledge` 上抽出事件并落库 | ✅ **50 事件 / 0 悬空 owner**（阶段 3 后重测：54 事件，含结构化 CHECK/BRANCH 点） |
| ② | 事件层 full / incremental parity | ✅ `incremental=52 full=52 identical=True`（阶段 3 后重测：`incremental=56 full=56`） |
| ③ | **B.2.2 指纹触发测试** | ✅ **新增 3 项测试，2 个变异各被捕获 3/3** |
| ④ | 旧测试不回归 | ✅ **98/98 通过**（95 旧 + 3 新；文档写的 34 是旧数）；阶段 3 后全仓 **140/140** |

**① 事件类型分布**（`tests/fixture_knowledge`，2 个 shard；阶段 3 后重测，含结构化点）：

```
ALLOC 2 · BRANCH 2 · CALL 18 · CHECK 2 · LOCK 6 · RELEASE 4 · RETURN 14 · THREAD_SPAWN 1 · UNLOCK 5
```

**② parity 的做法**：只改函数体（`load_index` 加一个 `free`）后跑 `incremental_update`，事件表内容与 `full_index` 逐字节一致。

**③ 是本阶段唯一「现有测试体系测不出来」的一条**，所以单独立了 `SemanticDirtyTriggerTests`：

| 测试 | 断言 |
|---|---|
| `test_a_body_only_edit_is_semantically_dirty_even_though_the_api_is_not` | 改函数体 → `boundary_dirty == []` **且** 新旧 `api_fingerprint` 相等（证明代码图确实看不见），而 `semantic_dirty == [alpha]`；并验证后果——`RELEASE` 事件从 1 条变 2 条 |
| `test_a_shard_whose_files_did_not_change_is_not_semantically_dirty` | 改 beta → 只有 beta 脏，alpha 不脏（证明是 per-shard，不是「哪里变了都算」） |
| `test_an_edit_that_changes_no_event_still_marks_the_shard_dirty` | 纯重排格式 → 事件 id 一个都没动，shard 照样脏（**钉住这个刻意的过读**，防止以后被「优化」成漏报） |

两个变异验证（改完即还原）：

- **M1**：`semantic_dirty` 改回查 `api_fingerprint`（即 B.2.2 描述的原始 bug）→ 3/3 失败
- **M2**：`semantic_fingerprint` 去掉 `source_hash`，只哈希路径 → 3/3 失败

**产出文件**：

| 路径 | 说明 |
|---|---|
| `semantics/vocabularies/cpp.toml`、`python.toml` | 关键词词汇表，**按语言分文件、事件类型为键**；加一门语言 = 加一个 TOML，不动 Python |
| `semantics/vocabulary.py` | 词汇加载 + 校验（`tomllib`，零新依赖）。空表必须用 `absent = "原因"` 声明式写明，否则拒绝加载 |
| `parsing/events.py` | 事件抽取器（`OwnerIndex` 按字节范围做最内层归属） |
| `identity.py` `event_id()` | `hash(owner_symbol_id, event_type, ordinal)` —— **不含行号 / 关键词 / 路径** |
| `storage.py` `semantic_events` + `semantic_fingerprint` 两表 | 独立冷层表（B.2.4），**不进 `nodes`** |

> **两处偏离计划，都是有意的**：
> 1. 计划写 `parsing/events_cpp.py` / `events_python.py`，实际是**一个共享的 `parsing/events.py`** + 两份 TOML。理由：语言差异全部落在词汇表里，抽取逻辑是同一套，这正是「灵活切换语言」想要的结构。
> 2. 计划写「`storage.py` +2 表」，实际是 `semantic_events`（事件）+ `semantic_fingerprint`（B.2.2 指纹），正是 2 张。
>
> **顺带修掉一个既有 C++ 抽取器 bug**（不是本次引入，实测确认）：`_function` 把每个局部变量声明都当成函数符号（`int x = 1;` → 符号 `f.x`），且返回 `True` 会终止遍历，导致 `char *p = (char*)malloc(64);` **一条 CALLS 边都不产生**。修掉后三个症状一起消失。这个 bug 此前一直在静默吞掉初始化器里的调用。

**阶段 2 尚未完成的部分**（同一阶段表格的第二行）：

| 项 | 状态 |
|---|---|
| 关键词 → 候选（不承担判定） | 🟡 **部分** —— 词汇表已经承担了「关键词 → 事件类型」这层映射，`semantics/candidates.py` 是否还需要作为独立模块，取决于「候选」是否要指比事件更宽的东西 |
| 候选召回率基线记录 | ⬜ **未做** —— 这是测量任务，不是编码任务 |

> 换句话说：**上表的 ① ② ③ ④ 是「事件抽取」这一行的验收，已全绿**；「候选召回率基线」这一行还没开始，不要把它算进已完成。

### 阶段 3 —— Sparse CFG

| 内容 | 产出 | 验收 |
|---|---|---|
| 事件间 `CONTROL_REACHES`（+ `branch=true/false`、`exception`、`loop_back` flags） | `sparsecfg.py` | 能正确回答 `ALLOC → RETURN without RELEASE`、`CHECK → DEREFERENCE`、`RELEASE → USE` 三个模式；**路径可复现**（同输入两次构建字节一致） |

#### 阶段 3 执行记录（2026-09-21 会话）—— 四条验收全部通过

| # | 验收项 | 结果 |
|---|---|---|
| ① | 事件间 `CONTROL_REACHES`（+ `branch=true/false`、`exception`、`loop_back`、`fallthrough` flags） | ✅ 边落 `semantic_edges` 表（5 个索引：src/dst/owner/file/relation），flags 进 JSON 列，`discriminator = ";".join(sorted(flags))` |
| ② | `ALLOC → RETURN without RELEASE` | ✅ `get_leaked_allocations` 在 fixture 上报出 `load_index` 恰好 1 条候选（subject=buffer）；修复版（路径上补 free）归零。测试 `test_alloc_reaches_exit_without_release` |
| ③ | `CHECK → DEREFERENCE` | ✅ `get_unchecked_dereferences` 报出 null 臂未 return 即解引用；守卫版与 `!=` 正臂版均不报。测试 `test_check_then_dereference` |
| ④ | `RELEASE → USE` | ✅ `get_use_after_release` 报出 `free(p); p->f = 1;`；`free(p);` 单独不报。测试 `test_release_then_use` |
| ⑤ | 路径可复现（同输入两次构建字节一致） | ✅ 两次独立 `full_index`，`semantic_events` + `semantic_edges` 按 `SELECT * ORDER BY id` 去掉 `generation` 后逐字节一致（`test_rebuild_is_byte_identical`）；增量与全量对拍（`test_full_incremental_parity_for_semantic_edges`） |

> 三个模式都是端到端走 `GraphQuery`（解析 → 发布 → 入库 → 查询），不是只测 `sparsecfg.py` 纯函数；`test_graph_query_exposes_the_three_patterns` 在 `fixture_knowledge` 上复核。三处用户确认的口径：**EXIT 只作边端点**（`dst_event_id = cfg-exit:<hash>`，不进 `semantic_events`，查询端由 `materialize_points` 物化）；**USE = DEREFERENCE**（实参型使用登记为缺口，补法已备好：CALL 加 `subject` + `use_after_release` 一行）；**只做 C/C++**（Python 侧 CFG 未做，`LanguageProfile` 留缝）。

**实测数字**（`tests/fixture_knowledge`，2 个 shard，阶段 3 后重测）：

- 语义点 **54**（= 阶段 2 的 50 词汇事件 + CHECK 2 + BRANCH 2；fixture 无解引用，DEREFERENCE 0）、`CONTROL_REACHES` 边 **58**（其中到 `cfg-exit:` 汇点的边 14）
- 全量构建 **62 ms**（含 CFG），库 **434,176 字节**——阶段 4 与阶段 7（冷热拆分）的输入
- 套件 98 → **140/140**（+31 全部来自 `tests/test_sparsecfg.py`；`test_semantics_vocabulary.py` 另有 1 处断言扩展不加测试数——3.1 因此变为 `coverable_now()`，4.3 缺失集缩到 `READ`/`WRITE`）
  - **阶段 4 修订**：3.1 的 `coverable_now()` **翻回 `False`**。阶段 4 把「确认所需」（`requires`/`relations`）与「候选所需」（`candidate_requires`/`candidate_relations`）拆成两组字段后，3.1 的事件齐了、矩阵要求的关系仍未展开，两段性改由 `candidate_coverable_now()` 单独回答；该断言按新语义重写，不加测试数

**事件类型分布**（阶段 3 后重测，见阶段 2 记录①；新增 `CHECK 2 · BRANCH 2`，`DEREFERENCE 0`）。

**产出文件**：

| 路径 | 说明 |
|---|---|
| `sparsecfg.py`（包根，1206 行） | `LanguageProfile`（C/C++ 共用一张表）+ `SparseCfgBuilder` + `find_paths`/三个模式纯函数 + `build_adjacency`/`materialize_points`；**不 import tree-sitter**，C 语法包缺失仍可导入 |
| `parsing/events.py` | +`EventHit`、`extract_hits()`——事件层与 CFG 层读**同一批**命中（一个匹配器，杜绝两层漂移） |
| `models.py` | +`PointKey`/`ParsedPoint`/`ParsedEdge`/`ParsedCfg`；`ParsedFile.cfg`（`parsed_to_dict` 排除，解析缓存不长大） |
| `identity.py` | +`semantic_edge_id`/`cfg_exit_id`；既有 7 个 id 函数一字未改 |
| `storage.py` | +`semantic_edges` 表与 5 个索引；`replace_snapshot(semantic_edges=…)`，删除块同步 `DELETE`；`semantic_edges()` 载入器 |
| `graph.py` | 结构化点发布为 `matched_via="structural"` 事件行；边端点经 `id_by_key` 字典解析（查不到即 `ValueError`，绝不静默）；`build_graph` 返回 8 元组；Metrics +`semantic_points_created`/`semantic_edges_created` |
| `incremental.py` | +`carried_edges`：未重解析文件的边按 `file_id` 结转；不变式「每条边都是方法内、方法只属一个文件」由 `test_every_edge_is_intra_file_and_intra_owner` 钉住 |
| `query.py` | `get_control_paths` + `get_leaked_allocations` / `get_unchecked_dereferences` / `get_use_after_release`；未命中返回空不抛异常 |
| `semantics/events.py` | +`SemanticEdge`、`STRUCTURAL_EVENTS`（CHECK/BRANCH/DEREFERENCE）；`DefectPattern.missing_events()` 计入结构化点 |
| `tests/test_sparsecfg.py` | 872 行 31 项测试，全部走 `graph.build_graph`/`full_index` 的真实发布产物 |

**两处对计划的正向偏离**：

1. 计划写「边端点是 `ParsedCfg.points` 的**下标**」，实际**边直接携带 `PointKey`**（= `event_id()` 的输入五元组，附 `order` 决胜字段）——比下标更严格地满足「端点经字典解析，绝不靠列表位置」，还免去了创建序→下标的重映射。
2. **CALL 事件也带 `subject` 注释**（赋值目标或第一实参的根标识符）——v1 无模式消费它，纯粹为口径 2 的补法预留。

**执行中修掉的三个真 bug**（smoke 没抓到、套件抓到的，全是「flags 丢失」）：

1. `_build_method` 悬空链进 EXIT 时把 open 上的 flags 丢成 `()`；
2. `_flush_loop` 的 continue/回边同样丢 flags（continue 应保留 `branch=true` 再加 `loop_back`）；
3. switch 贯穿边覆盖掉到达臂的 flags。

三处都改为 `(*open.flags, 新flag)` 组合而非替换。

**明确登记的不精确与缺口**（不假装支持）：

| 项 | 状态 |
|---|---|
| 短路条件（`&&`/`\|\|`）不展开递归分支 | 点上 `short_circuit` flag 可见；`p != NULL \|\| p->f` 会漏报 |
| C++ `goto`/标签 | 目标不建模，链在 goto 处截断，方法内 CFG 可能不完整 |
| `switch` 多路判定 | 体平铺 + 标签作入口：贯穿正确（`fallthrough` flag），多路选择是过近似 |
| 调用抛出的异常 | 只认语法级 `throw_statement`；`exit()`/`abort()` 不伪造 handler 边（有测试钉住） |
| 别名/数据流 | 完全没有：`q = p; free(p); sink(q)` 漏报，`free(p); p = NULL` 不算守卫——矩阵 4.3「确认滑向 B」的那一半，等阶段 5 DFG |
| `p == 0` 形式的 null 检查 | 不识别（只认 `NULL`/`nullptr` 节点），与设计文档同款保守 |
| CALL 作为 USE | 未做（口径 2） |
| Python 侧 CFG | 未做（口径 3） |
| EXIT 不进 `semantic_events` | 按口径 1；若以后要统一枚举方法节点可提升为事件行，代价是事件计数语义要重述 |
| `overlay.py` 未纳入语义表 | 本阶段查询直读两张冷表。**阶段 4 修订**：Typed Query 落地时**仍未并入**——语义表是快照替换语义，overlay 的实体级 delta 要接进来必须先有级联规则（删一个方法 → 哪些事件/边随之死掉），那是 B.2.1 方法级脏传播的活，属真正的设计工作而非接线。阶段 4 的缓解：活跃 overlay 下每个证据束带一行缺口说明 + `coverage["semantic_overlay"]="base_snapshot_only"`；缺口已登记 |

### 阶段 4 —— Typed Query 第一批 ★（可证伪点）

| 内容 | 产出 | 验收 |
|---|---|---|
| `RaceQuery` / `ResourceLifetimeQuery` / `LockOrderQuery` | `defect.py`、`evidence.py` +`DefectEvidenceBundle` | ① 在 `fixture_knowledge` + 1 个真实仓上跑通 ② **人工核对 20 条候选**，记录 precision（这是 V2 第一个质量基线） ③ **明确回答：只用 Event+CFG 够不够？** 不够则记录缺什么、DFG 要改成什么样 |

> **这是整个 V2 的决策点。** 设计文档最大的未验证假设是「稀疏图足以支撑缺陷判定」。用最小的成本先验证它——如果 Event+CFG 就能覆盖 Race/Leak/Lock 三类，那 DFG 的范围可以大幅收窄。

#### 阶段 4 执行记录（2026-09-22 会话）—— 三条验收全部完成

| # | 验收项 | 结果 |
|---|---|---|
| ① | 在 `fixture_knowledge` + 1 个真实仓上跑通 | ✅ 夹具 + **两个**真实仓（1.3 的 population 在两个仓上都是 0，按预授权补索引第二个仓）；三个查询、五个缺陷键全部有输出或如实报 0 |
| ② | 人工核对 20 条候选，记录 precision | ✅ **已裁定：20/20 全假阳性，precision 0.000**（20 条 / 7 层 / 2 仓；`failure_reason` 闭集计数见下「裁定结果」；AI 先给逐条建议、用户逐条确认，`annotator` 栏如实记录） |
| ③ | 明确回答「只用 Event+CFG 够不够」 | ✅ 见下「验收③的回答」——**不够，但缺的不只是 DFG**；这是本阶段最重要的产出，直接改了阶段 5 的定义 |

**实测数字**

夹具（`fixture_knowledge`，2 shard）：
- 语义点 **54**（ALLOC 2 · BRANCH 2 · CALL 18 · CHECK 2 · LOCK 6 · RELEASE 4 · RETURN 14 · THREAD_SPAWN 1 · UNLOCK 5）、`CONTROL_REACHES` 边 **58**；库 **442,368 字节**（阶段 3 时 434,176，涨的是事件行上的新注释键）
- 三个查询：4.1 = 1 条 `resolved`（`buffer`@`load_index`）、4.6 = 1 条 `ambiguous`（`g_pool_lock`@`resize_pool`）、1.3 = 1 条 `resolved`（`g_index_lock|g_log_lock`）、1.4 = 0、1.1 = 0；`excluded_raii_locks = 1`（`snapshot` 被 RAII 规则排除）

真实仓（`full_index` 全量，Windows 本机）：

| | redis-50 | llama.cpp-100 |
|---|---|---|
| commit / 工作区 | `5f08991b` clean | `3cf03257` clean |
| 目录现状 | 未变 | **已改名 `llama.cpp-69`**（同 commit、clean；见下「复核单的源码根与仓目录改名」） |
| 索引文件 / 源码行 | 325 / 241,253 | 1,358 / 691,462 |
| 语义点 / 边 | 145,990 / 162,268 | 411,852 / 421,647 |
| 库体积 / 全量索引耗时 | 398 MB / 23.1 s | 1.28 GB / 86.1 s |
| 4.1 内存泄漏 | 35（resolved 12 / ambiguous 23） | 713（resolved 96 / ambiguous 221 / unresolved 396） |
| 4.6 锁未释放 | 20（resolved 4 / ambiguous 16） | 30（resolved 10 / ambiguous 20） |
| 1.3 锁序反转 | **0** | **0** |
| 1.4 重入 | 2（均 ambiguous） | 0 |
| 1.1 竞态 | 557,315（全 ambiguous） | 1,463,722（全 ambiguous） |

**1.3 的 0 在两个仓上是两种不同的 0**（比数字本身重要）：

| | redis-50 | llama.cpp-100 |
|---|---|---|
| LOCK 点 / UNLOCK 点 | 44 / 43 | 255 / 26 |
| 有锁的方法 | 40 | 218 |
| **subject 为空**的锁点 | 1 | **231** |
| 方法内持有两把锁的对 | **0** | 3 |
| 判定 | 锁身份正常，**语料里根本没有嵌套持锁** → 结构性零 | **提取失败主导**：231/255 锁点没有身份，LOCK:UNLOCK = 255:26 → 零来自抽取出错，不是「查过没有」 |

所以 `1.3 = 0` **不能**读成「这两个仓没有锁序反转」，也不能读成「查询不可用」；两种原因都不是精度证据。**这条正是把「提取正确性」列为独立一层的原因。**

**复核单**

`experiments/defect_v1/` 是测量仪器，不是产物：只读 URI 打开库、把原始行喂给 `defect.py`（**不走 `GraphQuery`**，可证无写）、`repository × defect_key × resolution_status` 分层轮转抽样、源码片段 ±2 行、空白裁定块。20 条落 7 层 2 仓。同库同种子两次运行 `defect_review.json` / `.md` **逐字节一致**（用真实两仓复跑对拍验证，不只是夹具测试）。

单子在裁定前**重新生成过一次**（补 `failure_reason` 栏 + `--root` 覆盖）：12 行 `repository × stratum` 的 `population_N`/`sample_n` 与首版**逐个相同**，因此 `case_id` 未移动，用户引用旧编号仍然有效。llama 的 61 条源码片段逐行对过改名后的树（61/61）。

裁定之后仪器补了两个模式，都是「JSON 是记录、Markdown 是读本」这条单一事实来源的延伸：`--render <json>` 从已填的 JSON 重渲染 `.md`（**不需要库**——否则刷新读本就得重跑构建、而构建会把裁定全部重置回 `PENDING`）；读本现在渲染**已记录的裁定**（`REVIEWED` + `is_true_positive: null` 渲染成 **uncertain**，不是空栏也不是假阳性），未裁定的仍渲染空白提示行。构建路径另外**拒绝覆盖已带裁定的单子**（除非显式 `--overwrite`）——裁定是这套仪器唯一消耗人工小时的产物，重采样便宜、裁定不便宜，所以销毁性的那条命令才是要问的那条。套件 208 → **212/212**。

两个被拆开的上限：`recall_truncated`（查询自己的 `max_paths`，说的是「候选可能少了」）与 `population_capped`（复核脚本的 1M 上限，说的是「`population_N` 是下界**且**样本是排序前缀」）。只有后者是关于抽样的陈述。

**裁定口径（复核单冻结后补入，供用户裁定用）**

裁定块是**状态 + 判定**两栏，因此是三态而不是两态：

| 栏 | 取值 | 含义 |
|---|---|---|
| `verdict` | `PENDING` / `REVIEWED` | **复核状态**，不是判定 |
| `is_true_positive` | `true` / `false` / `null` | 判定；`REVIEWED` + `null` = 看过但单子没带够做判断的材料 ⇒ **`uncertain`**，进分母、**不算 `pending`** |
| `failure_reason` | 闭集（下表） | FP 的**可计数**原因；`reason` 仍是自由文本 |
| `needs_dfg` / `missing_capability` | — | 直接回答验收③的两栏（逐条，不做成 yes/no） |

`failure_reason` 闭集：`identity` / `extractor` / `missing_read_write` / `alias` / `ownership` / `contract` / `call_argument_loss` / `insufficient_context` / `other`（`--summarize` 会列出全部值含 0，不在闭集里的值标注 `*(not in the taxonomy)*`）。precision = `tp/(tp+fp)`，`uncertain` 不进比值但在表内可见；空层报 `n/a` 而不是 `0.0`。

**`needs_dfg` 是窄问题（★ 措辞在裁定前收紧过一次）**：问的是「缺的那一环是不是**数据流**（值的传播、两个名字可能是一个对象）」，**不是**「只用事件+CFG 够不够」。后一种读法下 20 条 FP 几乎全是 `true`，字段退化成 `is_true_positive` 的同义词，而本阶段最核心的问题（缺口是数据流还是别的东西）会以「永远为真」的一个数字返回。窄读法下它和 `failure_reason` 一起把 FP 分成「DFG 能修的堆」（`alias`/值传播）与「DFG 修不了的堆」（`identity`/`extractor`/`ownership`/`contract`）。**裁定结果证实了这个预判：20 条一条 `needs_dfg: true` 都没有——那本身就是结论，不是填错。**

**这一栏不是装饰**：`needs_dfg` 与 `failure_reason` 是**两个不同的问题**——`identity`/`contract` 类 FP 不是 DFG 能修的，这正是「阶段 4 的结论不是一句『需要 DFG』」的计数证据。

**裁定结果（2026-09-22）—— V2 第一个质量基线**

20 条全部 `REVIEWED`、`is_true_positive` = `false`（**20/20 假阳性**）、`needs_dfg` = `false`（20/20）。**生成方式如实记录**：这 20 条是 AI 先逐条给建议（每条含 `is_true_positive` / `failure_reason` / `needs_dfg` / `missing_capability` + 一行 `file:line` 依据），用户逐条确认后写入；`annotator` 栏逐条记的是「**AI 提议 + 人工确认**」，AGENTS.md 与复核单口径一致，**不记成纯人工裁定**。

`PYTHONPATH=src python experiments/defect_v1/build_review.py --summarize experiments/defect_v1/results/stage4/defect_review.json`：

| defect_key | status | n | tp | fp | uncertain | pending | precision | needs_dfg |
|---|---|---|---|---|---|---|---|---|
| 1.1 | ambiguous | 4 | 0 | 4 | 0 | 0 | 0.000 | 0 |
| 1.4 | ambiguous | 2 | 0 | 2 | 0 | 0 | 0.000 | 0 |
| 4.1 | ambiguous | 4 | 0 | 4 | 0 | 0 | 0.000 | 0 |
| 4.1 | resolved | 4 | 0 | 4 | 0 | 0 | 0.000 | 0 |
| 4.1 | unresolved | 2 | 0 | 2 | 0 | 0 | 0.000 | 0 |
| 4.6 | ambiguous | 2 | 0 | 2 | 0 | 0 | 0.000 | 0 |
| 4.6 | resolved | 2 | 0 | 2 | 0 | 0 | 0.000 | 0 |
| **overall** | | **20** | **0** | **20** | 0 | 0 | **0.000** | **0** |

`failure_reason` 分布：**`ownership` 10** / **`identity` 6** / `contract` 2 / `extractor` 1 / `call_argument_loss` 1 / `missing_read_write` 0 / `alias` 0 / `insufficient_context` 0 / `other` 0。

**缺口归堆（验收③的计数版）**：`identity` 6 + `extractor` 1 = **7 条靠身份与提取正确性**（阶段 4.5）；`ownership` 10 + `contract` 2 + `call_argument_loss` 1 = **13 条靠所有权与 API 契约**（5C）；**靠 DFG 的 0 条**。与「验收③的回答」的五类缺口一致，但这次每条都带 `file:line` 依据、可计数。

**这个 0/20 能说什么、不能说什么**（写进记录，防止被引用成别的意思）：

- **能说**：这批候选生成器在一个 20 条的跨层样本上没产出一条真阳性；**20 条 FP 里靠一条数据流边就能翻案的是 0 条**。唯一的 `call_argument_loss`（`RedisModule_SetKeyMeta(cls, k, (uint64_t)new_str)`，资源当第 3 实参交出去）需要 DFG 作为**前置但不充分**——还得知道 callee 取所有权（`MetaFreeCallback` 释放）。**「阶段 5 就是做 DFG」这个读法在这批样本上不成立。**
- **不能说「precision = 0%」**：样本是 `repository × defect_key × resolution_status` 分层轮转的，**12 层分 20 条**，每层 1–2 条 ⇒ **分层 precision 没有统计意义**，只有合计有意义。1.3 的 population 在两个仓上都是 0，锁族由 1.4 代表。
- **不能说「这三个查询没用」**：本阶段测的是**候选精度**，不是召回，也不是查询逻辑；1.3 = 0 在两个仓上是两种不同的 0（见上表）。而且查询的**不确定性标注是对的**——4.1 的 `ctx`（`return ctx;` 转移）被它自己降成 `ambiguous`，1.4 的 `&index->slot_locks[i]` 被降成 `ambiguous`，假阳性出在**确认**环节，不是三态契约被违反。
- 三条「设计如此」的 FP（`src/setproctitle.c` 的 `SPT.arg0`、`program_invocation_short_name`、`environ`）在 `notes` 里写明了判据是意图；若日后认为意图类判断不该进分母，这三条应改判 `uncertain`（`is_true_positive: null`），而不是算作 FP。

**复核单的源码根与仓目录改名（2026-09-22）**

`llama.cpp-100` 目录已被改名为 `llama.cpp-69`（**同一 commit `3cf03257`、工作区 clean**，仓库身份未变），而库里的 `repositories.root_path` 记的是索引时的旧路径。后果不是报错而是**静默降级**：源码片段全部变成 `text: null`，单子看上去完整、却不再带裁定所需的材料。仪器因此加了 `--root NAME=PATH`：`sources[]` 同时记库里的 `root_path` 与实际的 `root_path_used` + `root_override`，**仓库标签仍用 `llamacpp100`**（标签是标签，commit 才是身份；改名不该移动 `case_id`）。回归测试用「把 `root_path` 改成一个不存在的目录」的库副本钉住这条：无 override ⇒ `text` 全 null，有 override ⇒ 片段可读且逐行对得上源码。

**本轮读候选读出的三个真 bug**（测试没抓到、读候选读出来的；都在本仓**未提交**的阶段 3/4 新代码里——原仓 `bbc03ba` 连 `sparsecfg.py`/`defect.py` 都没有，一个字未改）

1. **匿名 `new` 归到了构造实参** —— `sink.emplace_back(new X(k))` 被记成 `GGML_TYPE_F32`/`params`，llama 273 条候选身份错误且报 `resolved`。修完 llama 的匿名 `new` 从 273 涨到 **387**（正确地变成 `unresolved`）。
2. **缺 `subject_exact` 通道** —— redis 1.4 整族是 `index->slot_locks[i]` vs `index->global_lock`，同一个根名 `index`，两条都报 `resolved`。现在按「名字是不是完整指称」封顶 `ambiguous` + `SUBJECT_PATH` 事实。
3. **`race_condition` 判别式不含方法对** —— 判别式取「较大的 owner id」，anchor 取「较小的 point id」，两个排序互不相关。redis 上 **889 条不同候选共用同一个 `(anchor, discriminator)`**，也就是共用同一个 `E-DEFECT-` 引用 id（llama 最坏 820 条）。已改成两个方法都进判别式；合成图测试钉住（发布真实源码无法保证哈希序）。

三处都补了反证那一半的测试（规则不许在 `p = malloc(n)`/`&g_lock` 上开火；判别式必须同时含两个方法；`(anchor, discriminator)` 与 `E-DEFECT-` id 必须一一对应）。套件 140 → **208/208**（含裁定口径的三态回归与源码根 override 的回归）。

**验收③的回答：只用 Event+CFG 够不够？**

不够。但**缺的不是单一的 DFG**——按证据强度排序，缺口分五类，其中三类根本不是数据流问题：

| # | 缺口 | 证据 | 属于 |
|---|---|---|---|
| 1 | **名字没有声明身份 / 作用域 / 存储期** | 1.1 的 557,315 / 1,463,722 条候选里，被抽样的 4 条全是**局部变量同名**（`int n`、`char name[9]`、`__m256i v`、`s`）；两个方法各有一个局部 `n` 就被判成共享 `n` | **符号表事实**——声明就在解析器已读过的 AST 里，不是数据流 |
| 2 | **没有 READ/WRITE 事件** | 1.1 的每个候选永远 `ambiguous`；`counter++` 这类零事件共享变量召回为 0 | Level 1 访问事件（DFG 的第一层） |
| 3 | **`.lock()` 词表误判 + 锁身份** | llama 255 个 LOCK 点里 **231 个没有 subject**，LOCK:UNLOCK = 255:26；样本里 `vk_pipeline pl = pipeline.lock();` 被当成取锁（`pipeline` 不是互斥量） | **提取正确性**——「这里到底有没有一个事件」 |
| 4 | **所有权 / RAII** | 4.1 的 `resolved` 样本里两条是智能指针（`mtmd_image_tokens_ptr image_tokens(new ...)`），图上只有 ALLOC 没有 RELEASE | Contract / Ownership（DFG 表达不了） |
| 5 | **跨过程 acquire/release 配对 + CALL 只认第一个实参** | `moduleAcquireGIL` 只加锁不释放（配对在 `moduleReleaseGIL`，由调用方调）；`RedisModule_SetKeyMeta(cls, k, (uint64_t)new_str)` 把资源当第 3 个实参交出去，CALL 只记第一个实参所以看不见 | Contract + 事件 schema |

**结论：阶段 4 证明的是「Event + Sparse CFG 足以*生成*第一批缺陷候选，但不足以提供可接受的*确认*精度」，真实仓暴露的瓶颈不是单一 DFG 缺失，而是 Variable/Resource Identity、READ/WRITE、Alias/Ownership、API Contract、事件提取精度共同决定。**

> 上表引用的每一条现在都有 `file:line` 依据与**已记录的裁定**（`experiments/defect_v1/results/stage4/defect_review.json` 的 20 条 `annotation`，数字见上「裁定结果」）：这张表是读候选读出来的结论，不再是「看起来像」。

**注意这句话不是「高召回」**：本轮**没有测召回**，而且召回在两处可证受限于非图因素——redis 4.1 受词表（`zmalloc`/`zfree` 不在共享词表，redis-50 的 `src/` 下 90 个文件在用），1.1 受事件覆盖（`counter++` 这类零事件共享变量召回为 0）。任何把阶段 4 读成「候选生成已经是高召回」的说法都没有证据。

**对阶段 5 定义的修订（★ 本阶段对路线图最重要的贡献）**

原定义（B.4 阶段 5）=「Sparse DFG：`DATA_FLOW_TO`/`PRODUCES`/`CONSUMES`/`MAY_ALIAS`，覆盖 INPUT→SINK / ALLOC→USE / FREE→USE / NULL_SOURCE→DEREFERENCE」。**按阶段 4 的证据，这个定义把两件成本差一个数量级的事捆在了一起，而且顺序反了。**

修订为两条流水线（生成便宜、确认贵）：

```
        ┌─ 提取正确性（词表 + subject 提取 + 存储期/作用域）─┐
        │   「这里有没有一个事件、它是哪个对象」             │
        ▼                                                    │
  Semantic Events ─┐                                         │
  Identity/Scope ──┼──► 候选生成（recall，便宜：AST 里已有） │
  Sparse CFG ──────┘                                         │
                                                             │
                        候选集合 ◄───────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
        Alias            Ownership         API Contract
     (MAY_ALIAS)      (RAII / transfer)  (acquire-release 配对)
          │                  │                  │
          └──────────────────┼──────────────────┘
                             ▼
                    确认 / 淘汰（precision，贵：跨过程 + 推断）
                    只能降级或带理由淘汰，不许静默升级
```

三条理由，全部有本阶段数字支撑：

1. **候选生成与确认的成本差一个数量级。** 生成只需要 AST 里已有的事实（声明、作用域、owner、控制边）；确认需要跨过程推断。把 Identity 和 DFG 放进同一个阶段，等于用最贵的手段去解决最便宜的问题。
2. **1.1 的候选爆炸不是 DFG 能修的。** 两个方法各有一个局部 `n`，别名分析会正确地回答「这两个 `n` 无关」——但要问这个问题，得先为 146 万条候选各跑一次跨过程别名分析。**先让候选集合里不再有局部变量，再谈别名。**
3. **有整整一类问题既不是 CFG 也不是 DFG：API 契约。** `moduleAcquireGIL`/`moduleReleaseGIL` 的配对、`unique_ptr` 的析构释放、`.lock()` 是不是互斥量——这些是「这个 API 对资源意味着什么」，不是「值怎么流」。硬塞进 `DATA_FLOW_TO` 会同时污染两边。

于是阶段 5 拆成三段，前置一段修阶段 4 的身份模型：

| 阶段 | 内容 | 为什么排这个位置 |
|---|---|---|
| **4.5 Identity & Extraction Hardening** | `declaration_id` / `scope_owner_id` / `storage_class`（local·parameter·function_static·field·file_static·global）/ 完整 CALL arguments / LOCK receiver 分类 | 最便宜、收益最大；且它是后面每一步的**分母**——身份不修，任何 precision 数字都不可比 |
| **5A Access Layer** | `READ` / `WRITE` 事件 + access→subject 身份 | 1.1 的决定性缺口；先有访问事件，「访问对」才有意义 |
| **5B Sparse DFG Core** | `DATA_FLOW_TO` / `MAY_ALIAS` / `PRODUCES` / `CONSUMES` | 只做 4.5 + 5A 之后**仍然**解释不了的误报所要求的部分 |
| **5C Contract / Ownership** | `FunctionEffectSummary`（function_id / effect / resource_kind / argument_ordinal / ownership_effect / confidence / provenance）、RAII wrapper、acquire-release 配对 | 与 DFG 分开：DFG 回答「值怎么流」，Contract 回答「这个 API 对资源意味着什么」 |

**登记：4.5 是阶段 4 身份模型的修订，不是新能力。** 阶段 4 的 `subject` 只有名字，`subject_exact` 只回答「名字是不是完整指称」，回答不了「这是不是同一个对象」。这是阶段 4 的**已登记缺口**，由 4.5 承接；阶段 4 的记录不假装它闭合了。

**明确登记的不精确与缺口**

| 项 | 状态 |
|---|---|
| 名字没有存储期 | 局部/形参/函数内 static/字段/文件级全局在图里都只是名字；1.1 候选爆炸的主因；**由 4.5 承接** |
| READ/WRITE 不存在 | 1.1 每个候选永远 `ambiguous`（`MAY_PARALLEL` 不可解 + 访问种类是语法代理）；`counter++` 零事件变量召回为 0；**由 5A 承接** |
| 锁身份是名字 + `.lock()` 词表误判 | llama 231/255 锁点无身份；`pipeline.lock()` 非互斥量；**由 4.5 承接** |
| **图里没有任何类型信息** | `semantic_events.metadata` 的键只有 `relative_path/shard_path/subject/expression/subject_exact/subject_from/polarity/thread_function`；`nodes` 有 `signature`（声明原文）但没有解析出的类型。于是「`pipeline` 是不是互斥量」「`mtmd_image_tokens_ptr` 是不是 RAII wrapper」这两问**当前无数据可答**——§1.3 与 §1.4 的修法都卡在这里。**由 4.5 承接，且 4.5 的必做项要显式加一条「持久化接收者/分配目标的声明类型（哪怕先只存类型名 token）」**，否则两条修法都无处下手 |
| **匿名 `new` 的身份是未决问题** | 修掉的是「借用了构造实参的身份」（llama 273 条错报 `resolved` → 387 条正确报 `unresolved`）。**但它仍然没有自己的身份**。若把**分配点**当作资源身份（稳定、确定性、可引用），这 387 条会从 `unresolved` 变成 `ambiguous`，剩下未知的是**所有权/消费**而不是身份。这是 4.5 的决定，不是阶段 4 的结论；它会移动 4.5 前后对比里的三态分布，所以**必须先决定再对比** |
| 智能指针 = 泄漏 | `unique_ptr<T> p(new T)` 是 ALLOC 无 RELEASE，每个都报 `resolved` 泄漏；**由 5C 承接** |
| 跨过程 acquire/release | 配对不同函数，由调用方完成；**由 5C 承接** |
| CALL 只认第一个实参 | `f(x, q)` 只记 `x`；第 2+ 实参交出的资源读成仍持有；**由 4.5 承接** |
| 获取顺序是词法序 | 分支/循环下只是近似（CFG 只用来确认持有） |
| RAII 只做了一半 | `lock_guard{m}` 可证排除（`excluded_raii_locks`：夹具 1 / llama 49）；`std::lock_guard<T> lock(m);` 的括号拼法被解析成函数声明，不可见 |
| 词表召回冒充图能力 | redis 大量 `zmalloc`/`zfree` 不在词表 ⇒ 4.1 候选偏少是**词表限制不是图限制**；每个查询 coverage 带 `points_by_type` 以便区分 |
| `max_paths` 截断 | 前 N 条路径都干净的泄漏会漏报；`recall_truncated` 每查询/每层上报 |
| `semantic_evidence` 不建表 | 候选按需计算；将来随分析副本（阶段 7）以 `candidate_id PK` 建 |
| overlay 不接语义表 | `layers` 非空时每个 bundle 带缺口行 + `coverage["semantic_overlay"]`；级联规则是 B.2.1 的活 |
| 4.2 双释放 | 明确留给阶段 6 |
| RETURN 转移只认名字级相等 | `return q;`（`q = p`）漏报 |
| 1.3 的零不是精度证据 | 两个仓的零来自两种不同原因（语料无嵌套持锁 vs 提取失败），都不构成「没有反转」的结论 |
| 1.1 的 population 上限 | 复核脚本 1M 上限；llama 命中（`population_capped`），`population_N` 是下界 |

**产出文件**

| 路径 | 说明 |
|---|---|
| `src/provenlattice/defect.py`（新增） | 三个纯函数查询（`(events, edges) -> DefectQueryResult`）+ `Candidate`/`DefectQueryResult` + `candidate_evidence`/`candidate_bundle`；不 import tree-sitter / sqlite |
| `src/provenlattice/sparsecfg.py` | +`_subject_for_hit` 注释通道（`subject_from`/`subject_exact`/`raii`/`thread_function`）、`unreleased_resources` 参数化、`materialize_points` 加宽 |
| `src/provenlattice/evidence.py` | +`DEFECT_CANDIDATE` kind/prefix/引用正则、`DefectEvidenceBundle`（§15 八成员逐字保留） |
| `src/provenlattice/query.py` | `_defect_result` + 4 个方法 + `get_semantic_events` + `trace_evidence` 的 `E-DEFECT-` 支 + overlay 缺口行 |
| `src/provenlattice/cli.py` | `defect`（含 `--list`）/ `events` 子命令 |
| `src/provenlattice/vocabulary.py` + `defect_patterns.toml` | 「确认所需」与「候选所需」拆成两组字段（`requires`/`relations` vs `candidate_requires`/`candidate_relations`）；`missing_relations()`/`candidate_coverable_now()` |
| `experiments/defect_v1/` | `build_review.py` + `README.md`：复核仪器（只读、确定性抽样、JSON+MD、`--summarize` 算 precision + `failure_reason` 计数、`--root` 覆盖源码根、`--render` 从已填 JSON 重渲染读本、构建默认拒绝覆盖已裁定单子）。**V2 第一个质量基线：20/20 FP / precision 0.000 / needs_dfg 0**（`results/stage4/`） |
| `tests/test_defect.py`（新增） | 套件 140 → 208 |

### 阶段 5 —— Sparse DFG（★ 2026-09-22 修订：拆为 4.5 / 5A / 5B / 5C）

> **修订理由见上「阶段 4 执行记录 → 对阶段 5 定义的修订」。** 原定义把「候选生成」和「确认」捆在一个阶段，而两者成本差一个数量级；阶段 4 的真实仓证据要求先修身份、再补访问层、最后才做 DFG，且 API 契约必须独立成层。

| 子阶段 | 内容 | 产出 | 验收 |
|---|---|---|---|
| **4.5** Identity & Extraction Hardening | `declaration_id` / `scope_owner_id` / `storage_class`（local·parameter·function_static·field·file_static·global）/ 完整 CALL arguments / LOCK receiver 分类 | `sparsecfg.py` + `defect.py` | 两个真实仓**前后对比**：`candidate_count` / `reduction_ratio` / 三态分布 / 索引时间 / 库体积；**必须用数字证明「scope/storage identity 砍掉绝大多数 1.1 候选」，不能凭感觉宣布成功** |
| **5A** Access Layer ✅ 已完成（2026-09-23，见「阶段 5A 执行记录」） | `READ` / `WRITE` 事件 + access→subject 身份；1.1 改为基于访问对 | `semantics/` + `defect.py` | race 证据束能给出 writer event / reader event / subject identity / owner method / span / protection state / parallelism status |
| **5B** Sparse DFG Core | `DATA_FLOW_TO` / `MAY_ALIAS` / `PRODUCES` / `CONSUMES`；三态扩展（`MAY_ALIAS` 只记 candidate，绝不造 `ALIAS` 边） | `sparsedfg.py` | 覆盖 `INPUT→SINK`、`ALLOC→USE`、`FREE→USE`、`NULL_SOURCE→DEREFERENCE` 四类；中间传播链以 **evidence metadata** 保存可恢复；**范围只做 4.5+5A 之后仍然解释不了的误报所要求的部分** |
| **5C** Contract / Ownership ✅ 已完成（2026-09-23，见「阶段 5C 执行记录」；含 5C-2 五条登记项的承接） | `FunctionEffectSummary`（function_id / effect / resource_kind / argument_ordinal / ownership_effect / confidence / provenance）；RAII wrapper、acquire-release 配对、known factory/sink/close API | `contracts.py` | 跨函数 acquire/release 样本不再仅凭「当前函数没有 release」形成高置信结论；不确定契约保持三态 |

**阶段 5 的最终验收不是「代码写完」，而是回答**：候选量降了多少 / 局部变量同名误报是否消失 / READ-WRITE 是否提高了 race 证据可解释性 / RAII 误报降了多少 / `MAY_ALIAS` 换来多少 precision / Contract 解决了多少 DFG 解决不了的问题 / 每项能力的索引时间与存储成本 / full-incremental-deterministic parity 是否仍成立 / 是否出现新的大规模 candidate explosion / DFG 范围是否够。

**并且必须产出对比表**：`baseline(阶段4) vs Identity vs READ/WRITE vs Sparse DFG vs Contract`，核心指标 `candidate_count / precision / 三态分布 / DB_size / index_time`。**没有这张表，任何一层能力都只是「写完了」，不是「有用」。**

#### 阶段 4.5 执行记录（2026-09-22 会话）—— 三条验收全部完成

| # | 验收项 | 结果 |
|---|---|---|
| ① | 两个真实仓**前后对比**：`candidate_count` / `reduction_ratio` / 三态分布 / 索引时间 / 库体积 | ✅ 四列 × 两仓全表（见下），控制列逐位复现基线 |
| ② | **必须用数字证明「scope/storage identity 砍掉绝大多数 1.1 候选」，不能凭感觉宣布成功** | ✅ **1.1 候选 −94.88%（redis）/ −95.99%（llama）**，合计 2,021,037 → 87,200（`reduction_ratio` 0.95685） |
| ③ | （本阶段自加，比 AGENTS.md 更硬）按 **方法 + subject + span** 重新定位阶段 4 那 7 条 `identity`/`extractor` 裁定 | ✅ **7 条全部有明确去向**：4 消失 · 2 收窄到不同候选 · 1 降级（见下） |

**对比协议（R-13，四列 × 两仓）**

`C1` 旧码 + 旧库（`before.json`，改动前冻结）→ `C2` 新码 + 旧库（**控制列**）→ `C3` 新码 + 新库 + `identity=False`（隔离**提取侧**）→ `C4` 新码 + 新库 + `identity=True`（标题指标）。

**控制成立**：C2 在 C1 携带的**每一个键**上逐位复现 C1（redis 557,372 / llama 1,000,743，两仓均如此；`control_report()` 逐键比对，不是抽样）。所以 C3/C4 与 C1 的差读作改动的效果，而不是仪器的漂移。C1 的 `candidates_returned` 与各查询自报之和**完全相等**（redis 557,315 + 2 + 55 = 557,372），llama 的 463,722 差额全部来自 `race_condition` 的 1M `population_capped` 截断，不是去重。

**验收②：1.1 候选（标题指标）**

| | C1 旧码旧库 | C2 控制 | C3 仅提取侧 | **C4 标题** | 削减 |
|---|---|---|---|---|---|
| redis-50 | 557,315 | 557,315 | 557,315 | **28,523** | **−94.88%**（ratio 0.94882） |
| llama.cpp-69 | 1,463,722 | 1,463,722 | 1,398,235 | **58,677** | **−95.99%**（ratio 0.95991） |
| 合计 | 2,021,037 | 2,021,037 | 1,955,550 | **87,200** | **−95.69%** |

**削减的组成**（C4 `multi_method_subjects_by_storage`，即「仍能跨方法的主体」按存储期分解）：

| | local | parameter | function_static | field | file_static | global | unknown | 合计 |
|---|---|---|---|---|---|---|---|---|
| redis-50 | 0 | 0 | 0 | 0 | 131 | 153 | 533 | **817** |
| llama.cpp-69 | 0 | 0 | 0 | 285 | 76 | 23 | 1000 | **1,384** |

**local / parameter / function_static 在两个仓上都是 0，这是构造性的而不是巧合**：它们的身份是 `owner_symbol_id#decl`，按定义只在一个方法里存在，**不可能**出现在 ≥2 个方法中。1.1 的分母正是「跨方法同名主体」，所以这一类被整体消掉——redis 1,987 → 817、llama 6,793 → 1,384 就是这个机制，而不是靠阈值或采样。

`field` 在 llama 上留下 285 个是**对的**：字段本来就是同一个类的多个方法共享的，理应继续进候选（redis 上是 0，因为 redis 的 C 代码不用成员访问形式做锁主体）。`file_static` / `global` / `unknown` 留下是**有意的保守**：跨文件全局与宏常量恰恰是最该报的共享状态，不能因为解析器不跟 `#include` 就把它们丢掉。

**一个被证伪的预先注册预测（如实报告）**

计划 §四预测 redis 的 `subjects_multi_method` 从 1,987 降到 **136~176**（降幅 91~93%），依据是「1,947 个主体在仓内某处有声明 · 40 个找不到 · 136 个是文件级声明」。**实测 817，预测被证伪。**

原因不是实现出错，是**预测用的代理问题问错了**：预测问的是「仓内**任何地方**有没有一行声明」，实现问的是「**同一个文件里、词法上包住这个使用点**的作用域里有没有声明」。两者的差就是那 533 个 `unknown`：宏常量（`C_OK` / `REDISMODULE_OK` / `LL_WARNING`）、枚举常量（`CLIENT_TYPE_MASTER`）、**在头文件里声明的全局**（`server`）、以及被当作主体用的被调函数名——它们在仓内「有声明」，但不在那个文件的词法作用域里。这个边界正是 §三.4 登记过的「不跨文件查类型」的同一件事，现在它有数字了。

**方向必须预先说清（防止数字被读成意外）**：锁族在 llama 上**上升**——1.4 从 0 条到 27 条，`lock_pairs` 3 → 29。这不是退步，是原来「看不见」的锁点现在有身份了。锁族的验收指标是**身份覆盖率**而不是候选数：`unidentified_lock_points` **231 → 3**（redis 1 → 1，目标 ≈1）。要分清的是，另有 116 个锁点**有主体但身份未知**，被封顶 `IDENTITY_UNKNOWN`——与「没有主体」不是一回事，两个计数不能相加。

**三态分布（C4，去重后返回的候选）**

| | resolved | ambiguous | unresolved | 返回合计 |
|---|---|---|---|---|
| redis-50 | 14 | 28,565 | 0 | 28,579 |
| llama.cpp-69 | 72 | 59,356 | 9 | 59,437 |

llama 的 `resource_lifetime` 族逐键（C2 → C4，同一把尺子）：

| 键 | C2 旧库 / 拼写 | C4 新库 / 身份 |
|---|---|---|
| 4.1 | resolved 96 · ambiguous 221 · **unresolved 396** | resolved 65 · ambiguous 639 · **unresolved 9** |
| 4.6 | resolved 10 · ambiguous 20（共 30） | resolved 2 · ambiguous 27（共 29） |

**`unresolved` 396 → 9 就是用户决定①（匿名 `new` 的身份 = 分配点）的实测效果**，与预测的「387 条转 `ambiguous`」**逐位吻合**（396 − 387 = 9）。这是本阶段唯一一处预测与实测对上了的地方。4.6 的 30 → 29 是接收者分类排掉的那一条非互斥量接收者。

**R-14 的确认**：`synchronization_subjects_matched_by_identity` 在两个仓上都是 **0**——身份化之后 race 主体与锁主体按构造不再相等，同步减法失效。同列的 `synchronization_subjects_matched_by_root` 是 **358（redis）/ 4,280（llama）**，即「按根声明匹配」这一更宽策略能覆盖多少。**是否采用更宽的匹配是策略决定，本阶段只把两种数字一起报出来，不采用。**

**索引时间与库体积（成本如实入表）**

| | 索引时间 | 库体积 | 查询时间（三查询合计） |
|---|---|---|---|
| redis-50 | 23.1 s → **18.6 s**（−19.5%） | 398,163,968 → **412,614,656 B**（+3.6%） | 23.6 s → **7.8 s** |
| llama.cpp-69 | 86.1 s → **66.4 s**（−22.9%） | 1,279,168,512 → **1,305,657,344 B**（+2.1%） | 130.4 s → 129.3 s |

体积涨的是每事件 6 个新键（§二.10 的决定）。索引反而**变快**了，最可能的原因是幽灵符号消失（llama −101 个符号及其 `OwnerSpan` / CFG 工作），但这是**单次测量、跨会话**，没有做隔离实验——登记为「观察到的方向，成因未隔离」。redis 的查询时间降到三分之一是候选少了三个数量级的直接结果；llama 持平，因为 1.1 的削减被锁族新增的候选抵掉了一部分。

**库体积必须用「删掉重来」的数**：同一棵树在**已存在的库**上重跑 `index`，逻辑内容逐行相同（`repositories 1` / `files 325` / `nodes 11,254` / `semantic_edges 162,268` 两次一致），但**文件大小不同**（redis 412,614,656 → 413,036,544）。差在 SQLite 页布局，不在内容。所以库体积这个数只在全新路径上可比。

**验收③：阶段 4 那 7 条的重新定位（按方法 + subject + span，不用 id）**

每条两个独立答案：① 从新库读出记录跨度上的注释键与 `defect._identity` 组出的身份（关于图的事实）；② 只喂这些方法的 events/edges 跑**真实 `_run`**（关于查询的事实，不是推理）。子集按 `owner_symbol_id` 过滤边，方法内 CFG 精确保留。

| # | 裁定 id | 仓 / 键 | 阶段 4 的断言 | 拼写列 | **身份列** | **去向** |
|---|---|---|---|---|---|---|
| 1 | `DFV1-llamacpp100-1998861e` | llama / 1.1 | local `int n` vs parameter `int n` | 39 | **0** | **消失** |
| 2 | `DFV1-redis50-ea2342a8` | redis / 1.1 | local `char name[9]` vs local `sds name` | 1 | **0** | **消失** |
| 3 | `DFV1-redis50-2f1d2d06` | redis / 1.4 | `index->slot_locks[i]` vs `index->global_lock` | 2 | 1 | **原断言消失**；该方法仍产 1 条**不同**身份（`#parameter:index#global_lock`）的候选，conf 0.3、`SUBJECT_PATH` 封顶、`HOLDING_CONFIRMED: no path reaches...` —— 诚实标为不确定 |
| 4 | `DFV1-llamacpp100-72bae08d` | llama / 4.6 | **resolved**，`pl = pipeline.lock()`（`weak_ptr`） | 1 | 1 | **降级**：resolved conf 0.6 → **ambiguous conf 0.4**（`vk_pipeline ∉ _MUTEX_TYPES`，R-6 的设计） |
| 5 | `DFV1-llamacpp100-de09d340` | llama / 1.1 | local `__m256i v` vs local `float v` | 2 | **0** | **消失** |
| 6 | `DFV1-redis50-d5f9ea64` | redis / 1.1 | parameter `stream *s` vs parameter `stream *s` | 1 | **0** | **消失** |
| 7 | `DFV1-redis50-38c4035e` | redis / 1.4 | `index->slot_locks[slot]` vs `index->global_lock` | 2 | 1 | 同 #3 |

**4 消失 · 2 收窄 · 1 降级，7 条都有明确去向，没有一条靠「不产生候选」蒙混**：拼写列同时报出来，所以「身份列变 0」与「这一族本来就查不到」可以分开读。7 条里 6 条归 `identity` 缺口、1 条归 `extractor`，**全部关闭**——阶段 4 记录里「身份不修，任何 precision 数字都不可比」这句话的欠账还清了。剩下的 13 条 `ownership` / `contract` / `call_argument_loss` 归 5C，本阶段不动。

**本阶段自己新增的模块里发现并修掉的两个真 bug**

1. **`reference_declarator` 的名字不读**（`parsing/declarations.py`）。tree-sitter-cpp 把 `Ctx & ctx` 的名字放在**无字段**的子节点上（`Ctx * p` 有 `declarator` 字段），只读字段就丢光所有 C++ 引用形参——而引用正是传上下文对象最常用的方式，丢的恰好是 race 查询要读的名字。修好后 llama 的核心数字从 109,869 改善到 78,648。
2. **`type * QUALIFIER name` 完全解不出**（同文件）。`float * GGML_RESTRICT s` 里宏夹在 `*` 和名字之间，**两种语法都解析不了**：宏变成 declarator、真名被塞进旁边的 `ERROR` 节点。读字面的后果是**同时**丢参数 `s`、**并且**凭空多出一个叫 `GGML_RESTRICT` 的形参。这不是对 C 的猜测，是读语法自己的恢复形状，且两半（`pointer_declarator` 里的裸标识符 + 紧随其后只含一个标识符的 `ERROR`）必须同时成立才改名。**生产语法下 llama 有 2,148 处、redis 0 处**，全在 `GGML_RESTRICT` / `RESTRICT` 上，且都是 ggml 量化核的出入参——即 race 查询最可能读到的名字。修完 C4 的 1.1 从 78,648 → **58,677**（−19,211），而 **C3（拼写列）一动不动**：这个修只改 `subject_decl` / `subject_storage`，不改 `subject` 的拼写，所以拼写列看不见它——这正是 C3 用来隔离提取侧的意义。

**这个修够不到的一处（登记）**：当**第一个**形参的类型是 `type_identifier` 而不是原生类型时，语法会把**整个函数**读成一条变量声明（most-vexing-parse），`parameter_list` 根本不存在，恢复无从下手。实测 llama **1 个函数**（`ggml/src/ggml-cpu/amx/mmq.cpp:913`，`void unpack_B(packed_B_t * RESTRICT tile, ...)`），redis 0 个。所以生产语法下 2,149 处里这个修覆盖 **2,148**，剩下的 1 处登记，不假装。

**实测数字的两个口径必须分清**：`unidentified_lock_points` 是「锁点**没有主体**」，`lock_identity_caps` 里的 `IDENTITY_UNKNOWN` 是「有主体但**身份未知**」，`identity_legacy_points` 是「旧行**没有新键**」（回退路径，绝不静默丢）。C4 上 redis 的 `identity_legacy_points` 84 → 0、`identity_legacy_lock_points` 86 → 0，llama 的 394 → 126 / 50 → 116——旧回退在两个仓上基本退场，但 llama 还留着 126 / 116，是新库里仍未解析出 `subject_decl` 的残量，归 5C 的参数绑定。

**其他 C4 覆盖计数**（留档）：`allocation_sites` 0 / 1,393 · `excluded_raii_locks` 0 / 49 → 224 · `identity_resolved_points` 41 / 380 · `identity_resolved_lock_points` 26 / 109 · `non_mutex_lock_points` 0 / 0 · `disqualified_same_lock` 2 / 0 → 23 · `read_read_pairs` 1,137,753 → 351,448 / 1,948,264 → 209,100 · events 139,350 未变 / 396,893 → 397,312 · edges 162,268 未变 / 421,647 → 422,925。

**一个仪器行为的登记（不是候选数 bug）**：C4 的 llama `candidates_returned` 是 59,437，而三个查询自报之和是 59,446，差 **9**。`build_review._run` 按 `(defect_key, anchor, discriminator)` 去重，而 `lock_order` 的 1.4 对**同一把锁在一个方法里被重复获取 N 次**会产出 N−1 条**三元组相同**的候选（`mutex_cache` ×2、`mutex_tasks` ×3、`ctx#devicecompile_mutex` ×2、`r_ctx#ctx_mutex` ×4 与 ×3）。它们的 `facts` 里第二个获取点不同，所以不是完全重复，但身份相同、去重后只留一条。redis 上差值为 0。**登记为去重行为，查询未改**：改判别式会让同一把锁的重复获取变成 N−1 条近乎相同的候选，那是噪声。

**登记：本阶段不做的事**（§三.4，逐条不假装）：READ/WRITE（5A）· 智能指针 = 泄漏与跨帧 acquire/release（5C）· 结构体成员**自身**的声明（跨文件）· 跨过程共享（caller 传全局、callee 写形参 ⇒ 现在**不再产生候选**：这是有意的 recall 收缩，归 5B 的 `MAY_ALIAS` / 参数绑定）· guard→mutex 绑定 · 别名 · 真 `resource_id`。`_MISSING_RAII_RECALL` 按计划**退休**（括号拼法现在有身份了），换成 `unique_lock::unlock/lock` 经 guard 名操作、guard→mutex 绑定未解析（归 5C）。

**R-17 的确认**：`nodes` 少 101 行使 `shard.fingerprint` 的**公开 API 指纹也变了**（幽灵是 public），不只是语义指纹——增量会把含幽灵的 shard 判成 code-dirty。本阶段本来就是全量重建，但记下来，免得将来被当成 bug。

**确定性**：新库上把 `build_review.py` 对**两个真实仓**连跑两次（同一批库与源码根），`defect_review.json`（`f347336d…`）与 `defect_review.md`（`c3080995…`）**两次逐字节一致**——不是夹具，是真仓对拍。

**套件 229 → 230/230 绿**（新增 1 条：`test_a_qualifier_macro_does_not_swallow_the_parameter`，先验证过「去掉修复即变红」）。阶段 4 的 20 条裁定**不重跑**，只按方法 + span 重新定位那 7 条。

#### 阶段 5C 执行记录（2026-09-22 ~ 09-23 会话）—— 验收① 达成（8/13 → 10/13），验收② 抽样裁定单交付

**交付物**：`contracts.py`（`FunctionEffectSummary` 表 + RAII 包装表 8 条 + acquire/release 配对 + 声明消费表，全部带 provenance）；`defect.py` 的 4.1/4.6 七条裁决规则（RETURN_TRANSFER · RAII_WRAPPER_TYPE · STORAGE_OWNER · STORAGE_OWNER_FUNCTION_STATIC · DECLARED_CONSUMES / INFERRED_CONSUMES · PAIR_CALLER_OWNS），每条淘汰带 `disqualified_evidence` 记录（reason / provenance / detail / discriminator / span），三态只降不升（zero promotion 断言在 `d:/tmp/stage5c/probe_eliminate.py`）。

**验收①（13 条重新定位）**：`d:/tmp/stage5c/check13.py`，按 (method, subject, span) 定位、绝不按 id。5C-1 时点在冻结 4.5 库上 **8/13 CLOSED**（RETURN_TRANSFER 1 · RAII_WRAPPER_TYPE 2 · STORAGE_OWNER 1 · STORAGE_OWNER_FUNCTION_STATIC 1 · DECLARED_CONSUMES 1 · PAIR_CALLER_OWNS 2），5 条仍在的正好是 5C-2 登记的那 5 条，无「GONE without a recorded reason」。包装表由计划 4 条扩到 8 条（多 4 个 `*_ptr` 别名）：实测**只多消 2 条**、并把 4 条从 RETURN_TRANSFER 重标为 RAII_WRAPPER_TYPE（淘汰总数 119 → 121）；用计划的 4 条表也一条都不丢。

**验收②（分层抽样 12 条淘汰裁定）**：`d:/tmp/stage5c/sample_eliminated.py` —— 层 = 裁决理由，跨层 round-robin、层内按 (repository, span, subject) 排序，确定性抽样；每条带源码片段。**助理逐条读片段后给出 proposed verdict，用户逐条裁定**（单子里 user_ruling 留空）。12 条的建议裁决全部 agree（ELIM-04、ELIM-09 各带一条「记录的 reason 比真相窄」的如实注）。产出：`experiments/defect_v1/results/stage5c/eliminated_review.{json,md}`。**裁定结果（2026-09-23 用户已裁）**：**12/12 全部「同意」，零分歧**——8 条理由层（DECLARED_CONSUMES / ESCAPE_RETURN / ESCAPE_TO_SHARED / INFERRED_CONSUMES / PAIR_CALLER_OWNS / RAII_WRAPPER_TYPE / RETURN_TRANSFER / STORAGE_OWNER / STORAGE_OWNER_FUNCTION_STATIC）的淘汰各抽到至少 1 条且全部被人工确认正确；汇总进 JSON 的 `adjudication` 字段（`d:/tmp/stage5c/harvest_rulings.py` 回填）。

**5C-2 追加（5 条登记项，与 5A 同一次重建承接）**：

| # | 事实 | 落点 | 结果 |
|---|---|---|---|
| 2.4 | `passed_to`：分配点 ↔ 同行 CALL 实参联结 | `sparsecfg.py::_alloc_handoff` | 事实交付，**不给裁决**（没有 consumes 契约时裁决不可靠）——`make_test_cases_eval.` 的 80 条仍按登记保留 |
| 2.6 | `subject_init_arg0`：guard 声明里的互斥量实参（vexing-parse 形状由声明索引读出） | `parsing/declarations.py::_init_arg0` | 事实交付；4.6 的消费端是后续工作——`get_all_meta.lk` 仍按登记保留 |
| 2.9 | out-of-line 成员函数的裸成员解析 `resolve_member` | `parsing/declarations.py` | 交付：`field:S:m_` 拼接进类内拼写；llama 上 4 条 `name:*` 身份迁到 `field:*` 后立即被既有 STORAGE_OWNER 规则关闭（`ggml_backend_hexagon_device_context` ×3 + `ggml_hexagon_registry.devices`） |
| 2.11 | `write_source` / `unconditional`（写侧）→ `escaped_to` / `escaped_to_line`（分配侧） | `sparsecfg.py::_access_point` + `_annotate_escapes` | 交付；三元运算符 RHS 无根标识符、if 武装的写 unconditional=false，两个负例都有测试 |
| 2.12 | `returned`：分配点 ↔ 同行 RETURN 联结 | `sparsecfg.py::_alloc_handoff` | 交付；ESCAPE_RETURN 裁决路径无关（路径不可能包含分配而不包含 return）——llama_model_mapping 的 151 条随之关闭 |

**escape 裁决（ESCAPE_RETURN / ESCAPE_TO_SHARED）**：无契约依赖（读分配点自身注释，图事实而非契约推断），在 contracts=None 的对照跑里同样生效。

**真实库端到端抓到的两个真 bug（夹具测试看不见，都是交付当天修掉）**

1. **escape 裁决算了但从不生效**（`defect.py::_lifetime_candidate`）：重构时 `return None` 淘汰块留在 `if ruling is None and contracts is not None:` 里面，escape 裁决成立时该条件为假直接落空，随后被路径依赖裁决覆盖。check13 的 `spt_init.tmp` before=3 after=3 纹丝不动暴露了它。修复 = 淘汰块外提一级。
2. **`materialize_points` 的固定键白名单把新注释键全丢了**（`sparsecfg.py`）：`escaped_to` / `returned` / `passed_to` / `subject_init_arg0` / `write_source` / `unconditional` / `expression` 都在事件 metadata 里，但点记录不携带——真实查询路径上 `acquire.get("escaped_to")` 恒为空。夹具验证读的是 `cfg.annotations`，所以看不见。修复 = 8 个键补进点记录（含合成 EXIT 记录的空键位）。教训已固化：`annotations_by_type` 测试助手刻意走 `materialize_points`，这类断裂现在会红在测试里。

**验收（重建库对拍，最终代码、最终库 `d:/tmp/stage5c/{redis50,llama69}-5c2.db`）**

| 断言 | redis-50 | llama.cpp-69 |
|---|---|---|
| `semantic_edges` 逐位相同 | 162,268 = 162,268 ✅ | 422,925 = 422,925 ✅ |
| contracts 覆盖键 | 14 键 0 动 ✅ | 14 键 0 动 ✅ |
| 4.6 lock_order 候选集 | 1 → 1 ✅ | 18 → 18 ✅ |
| 4.1 resource_lifetime | 28 → 28（关闭的 2 条判别式与幸存者重合） | 609 → 424：**185 条全部有去向**（ESCAPE_RETURN 175 + ESCAPE_TO_SHARED 6 + 身份迁移→STORAGE_OWNER 4），**0 条新增** ✅ |
| check13 | **10 / 13**（2.9 与 2.12 关闭；2.11 关 3 留 1；2.4 / 2.6 按登记保留） | 同左（一次跑覆盖两仓） |
| 套件 | **251/251**（230 → 242 为 5A/5C-1 补测试，+9 为 5C-2 五事实与两条裁决的端到端） | 同 |

**登记（不假装）**：① `spt_init.tmp` 仍留 1 条——`#elif __APPLE__` 分支里 `setprogname(tmp)` 是**隔两条语句**的跨语句移交，超出 2.4「同行」的登记范围，留待带 consumes 契约的后续；② escape 裁决的路径线号测试可被**前向 goto 越过写点**骗过（CFG 模型固有的 goto 盲区，继承登记）；③ 两行直线方法（写点之后无 CFG 点）会**保守拒绝** ESCAPE_TO_SHARED（EXIT 点线号为 0，无法验证「每条路径都经过写」）；④ `passed_to` / `subject_init_arg0` 只发事实，消费端是后续阶段。

#### 阶段 5A 执行记录（2026-09-23 会话）—— 事件侧兑现，验收①②通过

**交付物**：`sparsecfg.py::_access_points`（位置规则：写侧 assignment/compound/init_declarator/update 的目标、读侧的访问表达式子节点、`p->buf[i]` 恰一个事件；存储过滤 {field·file_static·global·function_static·unknown}，local/parameter 不发）；`matched_via="access"`；**零边**（`_EDGELESS_EVENT_TYPES` 闸，event_only 既不 `_connect` 也不参与 `entry`）；`defect.py` 1.1 改为访问对（`_access_kind` 带 decided 三态、subject 索引拆 all_points/cf_points、保护状态新增「无 CFG 点」的 ambiguous 理由、`_MISSING_READ_WRITE` 退休）。

**事件量（§4.1 预测的偏差如实报）**：redis 139,350 → **171,553**（+32,203 访问事件：READ 29,137 + WRITE 3,066）；llama 397,312 → **524,887**（+127,575：READ 120,382 + WRITE 7,193）。计划里的 37,121 / 107,216 是探针口径，实现以 `access_events` 覆盖键为准；**边 +0 是硬的，两个仓都逐位复现**。

**1.1 候选（§4.1 追记的裁决**：上界 +658 被突破至 +253,277，逐条归因后判定**上界模型建错**——READ/WRITE 把纯读/纯赋值方法拉进既有身份的方法集（`name:server` 470→934 方法占 92%、`name:errno` 占 7%），不是多发、不是重复计数（对账闭合到 22 条 = same-lock 闸的量）；质量判定：访问是真的，配对质量被 4.5 已登记的 unknown 根成员塌陷放大（765 个成员路径并进 `name:server` 一个桶）。**按 R2 只报不用**：`candidates_by_identity_storage` 把 unknown 278,925/281,800 = 99% 钉在明面上；调优项（unknown 根的成员保留身份、errno 类宏名豁免）登记归 5B 前裁定。

**验收**：① 既有查询不动——重建库上 `semantic_edges` / contracts 覆盖键 / 4.1 / 4.6 逐位相同（闸是 CFG 污染证伪点，5C-2 之后的复跑仍 PASS）；② 证据束七项（writer event / reader event / subject identity / owner method / span / protection state / parallelism status）+ 健全性五条（零边、零升级、unknown 可见、代理计数如实 517 条、`p->buf[i]` 恰一个事件）——`check_bundle.py` 在最终库上 **failure count: 0**，留档 `experiments/defect_v1/results/stage5c/evidence_bundles.txt`；③ 成本：redis 重建 21.4 s / 442 MB，llama 88.6 s / 1.42 GB，事件表 +27%。

**登记（不假装）**：DEREFERENCE 侧身份塌陷（4.5 已有，5A 的 READ 侧反而更细）；`function_static` 跨方法身份不带方法 token（4.5 的登记局限）；下标 `i` 的 READ 是真召回（`buf[g_i]` 确实读了 `g_i`），R3 原文是对规则行为的错误预测；`parameter` 存储类（`arg->field = 1` 形状）**本阶段不覆盖**，归 5B 参数绑定。

#### 阶段 5B 执行记录（2026-09-23 会话）—— Sparse DFG Core + 两条调优 + 参数绑定，验收通过

**交付物**：新模块 `sparsedfg.py`（`mint_dataflow_edges` 发布层纯函数：并集遍历 `parsed.events ∪ cfg.points`、一条链规则（def = WRITE/ALLOC，RELEASE 承担 FREE→USE 的 def 角色；kill = 同身份中间 def / RELEASE 杀活跃 ALLOC）、直接 def→use 边 + `via` 中间链 metadata（可恢复）+ `flow_class` + `control_reachable`、`_mint_consumes` 从 5C `passed_to` 铸 CONSUMES、`bind_parameters`/`ParameterBindingTable` 查询期联结）；`defect.py`（`_identity` 成员保留兜底 `name:{name}#{member}`、`_THREAD_LOCAL_NAMES={"errno"}` 配对侧豁免、`race_condition` 可选 `bindings=None` kwarg + 组合块、`_return_ruling` 别名感知变体）；`sparsecfg.py`（`build_adjacency` 默认按 `relations={CONTROL_REACHES}` 过滤——七个既有调用点逐位不变、`_access_point` 对 parameter 只发 WRITE + null 字面量 RHS → `null_source`、`_annotate_aliases` 后处理、`materialize_points` 两个记录字典都带 `alias`/`null_source`）；`graph.py` 在控制边发布块后调 mint（端点未发布即 raise）；`vocabulary.py` `AVAILABLE_RELATIONS += {DATA_FLOW_TO, CONSUMES}`（实现映射注释）；`query.py` 在 `use_contracts` 开时组装一次绑定（`use_contracts=False` 同时关绑定，一个对照列）。**范围红线守住**：`MAY_ALIAS` 只记 candidate metadata，绝不造 `ALIAS` 边；DOMINATES_CHECK = via 链 CHECK 项。

**两条前置调优（用户裁「两个都做」，2026-09-23；纯查询层，冻结 5c2 库上量，不重建）**：① unknown 根成员保留身份——redis race 首跑（两闸全关）281,800 → 27,940（unknown 桶 261,405 → 7,545；server 族 ~35×，总体 27×），race 264,280 → 10,420；llama 137,899 → 98,448（unknown 桶 136,470 → 97,019，**仅 1.4×——登记 ~15× 主张是 redis-server 特异的，llama 的 unknown 由无成员裸根（res/type/tok_embd）主导**）；lifetime redis 48→48、llama 524→525（gone 1 = `name:rdma` 裸根本体，new 2/2 全部 rung 解释）；locks 差分 gone 0 / new 0。② errno 豁免——redis −17,520（**恰为 `name:errno` 桶精确值**；豁免 subjects 1 / methods 231）、llama −166（44 methods）；语料扫描 `h_errno`/`__errno_location` 均 0 文件 → 豁免表保持 `{"errno"}`。三态全 arm 全仓 all-ambiguous；4.1/4.6 移动全部归因（gate PASS）。

**DFG 核心重建闸（redis-50 → `d:/tmp/stage5b/redis50-5b.db`；llama 收尾期同闸）**：

| 断言 | redis-50 | llama.cpp-69 |
|---|---|---|
| CONTROL_REACHES 逐位相同 | 162,268 = 162,268 ✅ | 422,925 = 422,925 ✅ |
| DATA_FLOW_TO 行数（闸 = 3×(READ+DEREF+CHECK)） | **6,055**（input_to_sink 3,491 / value_flow 2,461 / null_to_deref 52 / alloc_to_use 40 / free_to_use 11；硬闸 235,107）✅ | **11,268**（5,507 / 4,956 / 750 / 47 / 8；硬闸 723,129）✅ |
| CONSUMES | 0（预测 0：ALLOC-with-passed_to=0；机制+夹具交付，语料 no-op 登记） | 2 |
| contracts 覆盖键 | 0 动 ✅ | 0 动 ✅ |
| 4.1/4.6 候选集 | lifetime 53=53、contracts 29=29（别名 RETURN_TRANSFER = redis 登记的语料 no-op，A/B：滤掉 DFG 边 53/29 逐位同）✅ | **4.6 三口径零移动：27=27 候选、5 resolved+22 ambiguous、13=13 身份桶**；lifetime 559（5b 库含 5B 提取增量） |
| 确定性（同树两次重建） | `semantic_events`+`semantic_edges` 逐字节一致（digest `c70d11db…`/`a61854aa…`）✅ | 两表 identical；整文件不同 = SQLite 页噪声，登记 ✅ |
| 增量 parity（无变更增量跑 vs 全量库；收尾期闸） | 副本上 no-op 增量后两表**排除 `generation` 列逐位一致**（行数 176,893/168,323 不变；该列是全局单调代数，增量设计上必跳——内容 parity 以排除该列为准）✅ | —（redis 侧执行） |
| index_time（internal，对 5C-2 +15% 闸） | 24.7s = **+15.4%，差 0.4 点超闸，如实登记**（调查链：首版全邻接 BFS 156.2s → 惰性 per-source BFS 25s → bisect `_via` + early-stop 24.8s；残差 ~3.4s 是 DFG pass 真实成本，判出 5B 范围） | 91.1s = **+2.9%，闸内** ✅ |
| DB_size | 441,950,208 → 454,008,832 | 1,305,657,344（45 期）→ 1,444,306,944 |

**参数绑定（提取侧 + 查询期联结）**：参数 WRITE 发布 redis 5,340 / llama 6,124 条，参数 READ 保持 0（登记近似）。bind 覆盖（redis）：calls_seen 55,231 / arguments_seen 39,905 / **arguments_bound 9,302**（declared 8,802 + spelling 500）/ parameter_slot_writes_skipped 122,818 / arguments_without_parameter_writes 22,982 / callees_without_agreed_signature 20,362 / arguments_without_caller_facts 7,398 / calls_without_callee 8,307 / arguments_beyond_arity 223。**穿过写规则（本阶段关键修正，探针自查抓到）**：只有**穿过参数**的写（成员路径非空如 `p->flags`，或整对象解引用 `*p = v`）才组合进调用方实参根；裸槽写 `p = x` 是被调方自己名字的重绑定，C 按值语义下永远摸不到调用方——第一稿把它组合进去，探针抓到 **+13,291（127% of 10,420）manufactured candidates**，修后跳过 122,818 条裸槽写、组合对 +4,019。登记：括号解引用 `(*p) = v` 不组合；C++ 引用参数的裸写是真穿过写、本规则保守拒绝。`race_condition(bindings=None)` 与缺省 dataclass 全等（逐字节对照）；零升级（resolved 0→0）；组合对 metadata tagging 9,316 == 9,316；`probe_zero_promotion` 并入 `probe_param_binding.py` 的两道闸（5C 断言克隆），不再单独跑。**预测偏差如实登记：≪10% 冻结预测 vs redis 实际 +4,019 = 38.6%**（机制即设计中的 1.1 跨方法 recall 恢复；gained 全部 ambiguous、抽样为真实 redis 并发习语）；llama +2,711 = 2.75%，在预测内。

**对比表（AGENTS.md 要求的五列；redis 表 `compare_5b.md`、llama 表 `compare_5b_llama.md`，交叉核对全 PASS）**：

| 列 | redis 1.1 race | llama 1.1 race | 说明 |
|---|---|---|---|
| C1 baseline(阶段4) | 557,315 | 1,398,235 | identity=False。redis = R-13 C1 逐位复现；llama = **R-13 C3（拼写列）逐位复现**（R-13 的 C1/C2 1,463,722 是旧码列，今日码不可复现；redis 三列恰好同值） |
| C2 identity(4.5) | 28,523 | 58,677 | **冻结工件引用**（c4_identity.json）——5B 修复骑在一切现码测量上（今日码在 45 库 redis 上 796，ride-along 注记保留） |
| C3 read/write(5A+5C) | 264,280 | 137,899 | identity_probe.json 裁断臂（冻结）；5A 期 unknown 根塌陷的登记成本，5B 就是来修它的 |
| C4 sparsedfg(5B) | 10,420 | 98,448 | 5b 库 bindings 关；llama 与步 1 identity_probe after **完全相等**（DFG/别名/参数写对 1.1 零移动） |
| C5 contract(full) | 14,439 | 101,159 | 今日交付态；lifetime redis 29 / llama 436（contracts 关 123）；locks 两仓 1 / 27 |

lifetime 列 redis 55/55/48/53/29、llama 742(冻结)/—/524(冻结)/559/436；三态全列 all-ambiguous（race）。**locks 口径注记**：identity_probe 的 locks 数（llama 13）是 `mover_report` 的**去重主体身份数**，直测候选条数 5c2 = 27（5 resolved + 22 ambiguous）——两个口径，差分结论（gone 0 / new 0）不受影响；5B 重建闸用直测三口径判定零移动。

**check13（5B 库：`check13.py d:/tmp/stage5b/redis50-5b.db d:/tmp/stage5b/llama69-5b.db`）**：**10/13，与 5A/5C 期同库龄口径一致，零回归**。关闭集 = 5C-1 的 8 条 + 2.9（STORAGE_OWNER）+ 2.12（ESCAPE_RETURN 双臂 before=0 after=0）；registry 幸存 3 条（10ec80 80、5a2cb 1、74e58 1）= 各自的登记残量。74e58 的 before 臂 45 库 3 → 5b 库 1 已归因：45 期提取没有 `escaped_to` 注解（5C-2 库起才有），:236/:241 的 ALLOC 带 `program_invocation_name/short_name = tmp` 无条件移交注解，被**合同无关**的 ESCAPE_TO_SHARED 淘汰；登记残量 :246（`#elif __APPLE__` 隔两条语句）不动。**check13 harness loader 修正**：`flags`/`metadata` JSON 解码（5B 起边 metadata 被查询层读取——`_flow_adjacency` 读 `via`；45 库时代无 DFG 边，原始字符串碰巧不被触碰）。

**套件**：251 → **267/267 全绿**（+16 为 5B 新增：身份正反例、errno、DFG 夹具 9 条、绑定 3 条、别名/词表映射钉；既有断言修正 5 处逐条注记在测试内）。

**登记（不假装）**：① index_time redis +15.4% 超闸（+15% 闸差 0.4 点）——残留为 DFG pass 真实成本， squeeze 判出 5B 范围；llama +2.9% 闸内。② 组合对规模 redis 38.6% vs ≪10% 预测——机制即设计的 recall 恢复，非误报制造（bare-slot 过领已被穿过写规则拦下：+13,291 → +4,019）；精确幅度交收尾裁定。③ CONSUMES redis 0 / llama 2 = 语料近 no-op，机制与夹具证明交付。④ 别名 RETURN_TRANSFER 在 redis 是语料 no-op（A/B 证明），在 llama 兑现（2.12 的 151 条双臂关闭属 escape 注解驱动；别名 via 链交付为可恢复图事实）。⑤ `p == 0` / `= 0` 仍不识别（继承登记近似，不翻案）；`(*p) = v` 不组合；C++ 引用参数裸写保守拒绝。⑥ 参数 READ 不发；实参成员路径不分解（根 only）；join 是实参根上的名字级较弱主张（逐 fact 写明）。⑦ 整文件确定性：SQLite 页噪声使整文件 digest 不同，以 `semantic_events`+`semantic_edges` 两表逐字节为准。⑧ identity_probe 的 locks 绝对数是身份数口径（见上注记）。⑨ 全部改动未提交（HEAD 0c27e01）；探针/工件在 `d:/tmp/stage5b/`（predictions.json 冻结于改提取码之前，偏差如实上报）。

### 阶段 6 —— Typed Query 第二批

| 内容 | 产出 | 验收 |
|---|---|---|
| `NullFlowQuery` / `UseAfterFreeQuery` / `DoubleFreeQuery` / `TaintPathQuery` / `ErrorHandlingQuery` | `defect.py` | 同阶段 4 的验收口径（人工核对 + precision 基线） |

#### 阶段 6 执行记录（2026-09-24 会话）—— Typed Query 第二批：五查询交付、两个交付级缺陷修复、T1/T2 冻结对账闭环

**交付**：`defect.py` 五个新查询（`NULL_FLOW`=3.1 / `USE_AFTER_FREE`=4.3 / `DOUBLE_FREE`=4.2 / `TAINT_PATH`（键 `taint`，无矩阵族）/ `ERROR_HANDLING`=9.1）+ `QUERY_NAMES` 扩到八键 + `run` 函数表 + `query.py` 五个包装器 + `semantics/taint.toml`（4 源 3 汇，每条带证据；头注释三条范围声明：无净化点模型、`target_module` 必须为空、位次判据受 `arity` 限制）+ `defect_patterns.toml` 四行 `query=` 及 9.2/9.3/9.4 未展开理由 + `vocabulary.py` 实现映射注释。CLI 未改（`--type` choices 由 `QUERY_NAMES` 驱动，但 `--type all` 从三查询变八查询，成本随之）。**套件 267 → 288（步 2 D1–D4）→ 295（步 5+6 D5）→ 296（窗口钳制钉子）全绿**。全部改动未提交（HEAD 0c27e01）。

**用户裁定 D（2026-09-24，步 3 前上报后裁定）**：原计划的 `result_of` 提取注解被实测否决——`_access_point` 对 `local` 不产 WRITE 点（`ACCESS_STORAGES` 不含 local），`int n = read(fd,...)` 这类「存调用结果」的主流形态在图里**永远看不到**（带调用右值的赋值站点 redis 17,227 / llama 59,811，局部根占 58.8% / 69.9%）。改用 **CALL 点已有事实**：`subject_from='assignment'` + `subject_decl`（redis 14,507 / llama 87,498 个点，声明已解析 14,404 / 85,031）⇒ **零提取改动、零重建**，步 3（提取改动 + redis 重建）与「提取侧零增量」闸随之取消，llama 闸全部在冻结 5B 库上完成。判据不变：`x = f()` → 下次使用/方法出口前无分支点 ⇒ 候选；`fd == -1` / `ret != 0` 不是 CHECK（只认 null，继承登记）所以「已检查」用分支支配近似。

**T1 冻结与实现偏差（无未归因残差）**：四查询探针在冻结 5B 库上先冻结（`predictions.json` 两次运行逐位相同），实现后对拍：

| 查询 | 仓 | T1 冻结 | 实现 | Δ | 归因 |
|---|---|---:|---:|---:|---|
| null_flow | redis | 63 | 62 | −1 | 守卫匹配改为**身份**（subject+member+声明）；impl-only 1 / probe-only 0 |
| null_flow | llama | 529 | 591 | +62 | 同一改动；探针理由是 `no identity-matched check`（63 个 CHECK 拼写同、成员不同） |
| use_after_free | redis | 581 | 387 | −194 | 新规则 `USE_IS_RELEASE`：237 条「释放自身那条 CALL 点」不再算使用 |
| use_after_free | llama | 10 | 31 | +21 | `USE_IS_RELEASE` −6 ＋ READ/WRITE 点不在任何 CFG 边里 ⇒ `unknown` +27（代码内自述，非猜测） |
| double_free | 双仓 | 194 / 283 | 同 | 0 | 逐位一致 |
| taint_path | 双仓 | 0 / 0 | 同 | 0 | 语料 no-op（llama 36 条源侧全是 `getenv → atoi`，`atoi` 正是排除项）|

实现期另修复四处（`materialize_points` 记录无 `point_id` 键 ⇒ is_target 必须身份比较；`_alias_closure` 签名 bug（仅夹具能暴露）；`_checks_on_path` 对 WRITE 源重写；`USE_IS_RELEASE`），两处**仅夹具可见**的盲区钉在测试里：局部 `p = NULL` 不产生 WRITE 点 ⇒ UAF/DF 的局部置空淘汰残量（`ACCESS_STORAGES` 缺 local 的查询期余波，登记）。

**T2 冻结（error_handling）**：`predictions_t2.json` 两次运行同 sha256。redis：population（已声明）14,404 / checked 10,320 / unchecked 4,084；llama：85,031 / 52,565 / 32,466；候选按 storage 分布逐项冻结。**对账闭环**：初跑 4 failure 全部机制归因、零未归因残差——① population 差 +103/+2,467 是**定义拆分**（冻结=已声明子集；查询把未声明者单列 `stored-call-result-undeclared`），14,507−103 / 87,498−2,467 恰等冻结值；② backward +58/+974 是**走法形状**（探针在决定点立即 return、查询走完整层；同一 population 上两种走法各自逐位复现两个数字）。归因后对账 **PASS**。判决/候选/按 storage 分布双仓零偏差（规则未被触动）。**次序敏感窗口**（同层 use/EXIT 先于前向分支）：redis 2 / llama 26，两种实现一致判 `unchecked`（首个决定点获胜），登记不改；`_branch_scan` docstring 两处不实陈述已改正。

**步 6 三闸**：① **既有查询零移动 PASS**——`gate_legacy.py` 在冻结 5B 库上 C4/C5 两配方 × 五旧键对拍冻结对比工件，逐键逐位一致（redis C4/C5：1.1 = 10,420/14,439、4.1 = 33/14、4.6 = 20/15、1.4 = 1；llama C4/C5：1.1 = 98,448/101,159、4.1 = 530/407、4.6 = 29/29、1.4 = 27），含按键拆分三态求和与 redis 双跑确定性；② **check13 10/13**，输出与 5B 逐字节相同，零回归；③ **成本表**（redis、`GraphQuery` 交付态、钳制后重测为权威）：resource_lifetime 7.6s / lock_order 4.9s / race_condition 7.8s / null_flow 4.8s / **use_after_free 124.5s** / **double_free 64.8s** / taint_path 4.7s / **error_handling 4.7s（4096 全窗口）**；合计 223.8s，`all` 一次调用 204.2s。**计划预测被证伪（登记）**：主导项是 use_after_free/double_free 的 `find_paths` 证据路径枚举，不是 error_handling 的分支扫描；其加速是独立小改动，待裁定，不在本阶段顺手改。

**交付级缺陷 ①（`error_handling` 的 `find_paths` 悬崖，发现于成本表首跑）**：`_flow_path → find_paths(max_hops=4096)` 是**路径枚举器**（逐路径 visited 集，`max_paths` 只封顶返回条数），循环窗口要 2^迭代条路径才能描述完（redis 3,989 个窗口，full >600s / 13.7GB 不返回）。**修复**：`_branch_scan` 记录 BFS 前驱，新 `_route()` 从扫描自己的 BFS 树线性读出决定点的路线——零成本、与判决不可能矛盾（就是判决所沿的那条路）；`error_handling` 删 `max_paths` 旋钮，候选 ControlPath 单条来自路线。修复后 1.6s，候选与 T2 冻结逐位一致；新测试钉住路线非空且点边相扣。

**交付级缺陷 ②（交付默认上限透传进窗口判决，发现于验收单首跑）**：`error_handling` 的窗口上限 `max_hops` 是**判决相关事实**（走早了读成「还没分支」= 伪候选），而交付层 `get_defect_candidates` 默认 `max_hops=64`（阶段 4 为六个兄弟查询的 find_paths 证据路径定的）被一律透传 ⇒ llama 上 6,189 个本该淘汰的窗口变成伪候选（9.1 population 42,739 vs 冻结 36,550）。**修法（强制冻结规则，不调规则）**：`error_handling` 内部钳到下限 4096（`_WINDOW_MAX_HOPS` 常量；调用者可调大、不可调小），兄弟查询不动；钉子测试：80 语句窗口 + `max_hops=8` 也必须判 checked。钳制后 4096 全窗口成本不变（4.7s = 截短窗口 4.7s）。**登记一处报告初稿的错误归因**：cost JSON 顶层 `truncated` 标志是 population 上限标志（`len(candidates) > max_candidates`，八查询同款），不是窗口截断的证据；窗口截短由 population 差本身证明。

**验收单（交付态，交用户逐条裁定）**：`experiments/defect_v1/results/stage6/defect_review.{json,md}`；`seed=provenlattice-stage6-review`、`contracts: on`（镜像 `get_defect_candidates` 装配：contracts.build + race 专属 bindings + taint 专属 references/load_taint；`--no-contracts` 对照开关备用）。**32 cases / 16 strata；16/16 分层与冻结口径零偏差**（1.1: 14,439/101,159 = gate C5；4.1: 14/407 = gate C5；4.6: 15/29 = gate C5；3.1: 62/591、4.2: 194/283、4.3: 387/31 = T1 实现；**9.1: 4,084/32,466 = T2 冻结 unchecked 逐位**；taint 与 1.3 零候选 = 冻结一致）。**单子 `population_N` 是 case 数**（`(key, anchor, discriminator)` 折叠，stage 4 仪器既有语义）：只影响 locks——llama 1.4 raw 27 → 18 case（13 ambiguous + 5 resolved，5 组锚级重复），加 redis 1 = 19；其余键无此效应。裁定同时给出：新查询 precision 基线 + 旧三查询在新库上 vs 阶段 4 基线 0/20 的前后对比。

**裁定结果（2026-09-24，AI 逐条提议 + 用户逐条确认）**：**32/32 已裁，TP 1 / FP 31 ⇒ precision 基线 1/32 = 0.031**（16 层分 32 条，照阶段 4 先例**只有合计有意义**，分层 precision 无统计意义）；`needs_dfg` 2 条（redis 3.1 `cluster_nodes`、redis 4.2 `cmd`——同一形态：杀死 def/NULL 的写入在被调帧内，图不可见）；零 uncertain。failure_reason（FP 31）：**contract 10 / extractor 6 / other 5 / ownership 5 / identity 4 / missing_read_write 1**（alias / call_argument_loss / insufficient_context 零）。唯一 TP = 3.1 resolved（utils/lru/lfu-simulation.c:87 malloc 后 :135 直接解引用）。四条读源码实锤：llama-quant.cpp:792 显式 `lock.unlock()` 在 ：800 再获取之前、zmalloc.c:301 OOM 即 panic（arAllocAndTrack 不返回 NULL）、server-models.cpp:1229 内层块闭合在 ：1232 之前、console.cpp:1118 加锁在 thread lambda 内。**新旧对比的如实读法**：旧三查询在本单抽中 14 条仍全 FP——4.5 的 −95.69% 是**缩量**不是 precision 提升；FP 主导成因从 ownership/identity（阶段 4）移到 contract/extractor，后者正是矩阵明写「AI-required 语义」的部分。**新登记（提取侧改动 + 重建才有交付效果，未顺手修）**：`std::getline` 误入 ALLOC 词表（2 条）、noreturn 语义未建模（GGML_ABORT/assert，2 条）、守卫成员 `.unlock()` 与 `.lock()` 的消歧（2 条）、posix_memalign 出参分配器、宏内断言识别（GGML_ASSERT）、经参数数组/对象图的传递所有权（2 条）。**图谱侧不修、按分工登记**：contract 10 条全是 AI 侧语义（MUST_CHECK 清单、所有权移交、noreturn 约定），图谱只负责把候选送出来。`find_paths` 加速（use_after_free 124.5s / double_free 64.8s 主导）仍是待用户裁定的独立小改动，与本轮精度裁定无关。annotator 栏 = 「AI 提议 + 人工确认（Claude Code 提议 / Kyber5323 逐条确认，2026-09-24）」；回填仪器 `d:/tmp/stage6/fill_stage6_review.py`（32 条裁定带期望 `(repo, key, status)` 三元组断言，防映射错位）。

**登记（不假装）**：① `error_handling` 曾带两个交付级缺陷，都已修（悬崖 + 上限透传），各有钉子测试。② 成本两表之间唯一代码差是钳制 ⇒ 其余行的升降是机器状态，非代码效果；排序两表一致。③ `error_handling` 只覆盖一半形态：结果被直接丢弃的调用不可判定（CALL 无「独立语句」事实）；无关分支被当作「已检查」的假阴性如实登记。④ 未声明左值形态不存在（六形态探针零命中）：复合左值都能解析声明，`stored-call-result-undeclared` 的 103/2,467 全是裸标识符无声明（循环变量、lambda 捕获）。⑤ 对照列不覆盖新键：五个新查询都不消费 contracts/bindings ⇒ `--no-contracts` 只可能动 4.1/4.6/1.1，而这三键的 C4-vs-C5 差已由 5B 五列对比冻结。⑥ 局部置空盲区（`ACCESS_STORAGES` 缺 local 的查询期余波）：uaf/df 的局部 `p = NULL` 形态淘汰不了，钉在夹具里。⑦ taint 与矩阵 :286 的冲突（无净化点模型）与无矩阵键（只能按查询名寻址）沿裁定登记；`defect_patterns.toml` 不为它加行。⑧ `p == 0`/`= 0` 不识别、短路条件不展开、CHECK 只认 null、`MAY_ALIAS` 只进 candidate metadata——沿袭登记，全部未翻案。⑨ 探针/工件在 `d:/tmp/stage6/`（`predictions.json`/`predictions_t2.json` 冻结于实现之前；`gate_legacy.{py,json}`、`verify_t2*.{py,json}`、`cost_eight*`、`check13_stage6.txt`）；冻结库只读；阶段 6 执行报告全文 `d:/tmp/stage6/step6_report.md`。

### 阶段 7 —— 冷热拆分 + 分析副本

| 内容 | 产出 | 验收 |
|---|---|---|
| `raw_references` → Parquet 列存；**缺陷扫描副本**（DuckDB） | `storage.py` 拆分、`analysis/` | 主库体积下降；`update` 内存不再随 raw_refs 线性增长 |
| 顺带：消除 B.2.3 的 4.8 MB 重复解析缓存 | | 主库内容体积可解释、无重复 |

> 附录 A 把这一步的理由定为「规模」。**加入缺陷检测后理由变了**：缺陷检测是「全图扫描 + 模式匹配 + 连接」，列存 + SQL 是这个负载的正解，与规模无关。

### 阶段 8 —— Hot CSR

| 内容 | 产出 | 验收 |
|---|---|---|
| 拓扑常驻内存；`ID → uint32` 用紧凑数组（**不是 Python dict**，见 B.2.4） | `hotgraph.py` | 多跳 ⭐⭐⭐⭐⭐；**`frontier > 16,383` 限制彻底消失**；遍历顺序显式排序，确定性可复现 |

### 阶段 9 —— Local Deep Analysis

| 内容 | 产出 | 验收 |
|---|---|---|
| 对 1~5 个候选 Method 临时构建局部 AST/CFG/DFG | `localdeep.py` | 难例（复杂 alias / pointer arithmetic / 跨过程 ownership / template / virtual dispatch）准确率提升可测；临时图**用后即释放或缓存**，不污染全局图 |

### 阶段 10 —— 快照分片

配合 `fidelity_v1` 金标冻存（附录 A 阶段 3）。

---

## B.5 规模外推（实测锚点）


**实测基数（本仓 10,115 行）**

| 指标 | 实测 | 每行 |
|---|---:|---:|
| `reference_type = CALLS` | 5,185 | **0.51** |
| `reference_type = REFERENCES` | 19,277 | **1.91** |
| raw_references 合计 | 25,040 | **2.48** |
| edges | 2,604 | 0.26 |
| nodes | 644 | 0.064 |
| `raw_references` 单行体积 | 9.31 MB / 25,040 | **≈ 390 B** |

**事件量估算**（用 CALLS 密度锚定 Level 0，用 REFERENCES 密度锚定 Level 1）：

| 代码量 | Level 0 事件 | Level 0+1 事件 | 存储（390 B/行） |
|---:|---:|---:|---:|
| 10 万行 | 5 万 | 25 万 | 20 ~ 98 MB |
| **100 万行** | **51 万** | **248 万** | **199 MB ~ 967 MB** |
| 300 万行 | 153 万 | 744 万 | 597 MB ~ 2.9 GB |

> ⚠️ **这是外推，不是实测**，基数只有一个 10k 行样本。但量级结论稳固：**事件层和 `raw_references` 同量级，远大于 `nodes` + `edges`。**

**热层可行性**：2.6M 事件 + ~4 条/事件 的边 → CSR 约 **150~200 MB**，可常驻。**但 ID 映射必须紧凑**（B.2.4），否则光映射就 550 MB。

---

## B.6 风险登记

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | **B.2.2 语义指纹漏触发** → 跨方法语义边陈旧 | 🔴 静默错误，parity 测试测不出 | 阶段 2 验收项 ③ 专门覆盖；先用「source_hash 变则语义脏」的保守版 |
| R2 | **事件抽取精度不足** → 事件漏抽/错抽 | 🔴 后续全部环节失效 | 阶段 2 先只做 Level 0；用 `fidelity_v1` 的双盲方法论做事件级金标 |
| R3 | **关键词候选召回不可控** | 🟠 漏报 | 只记录基线，不设阈值；「关键词只提高召回，不承担判定」这个定位要守住 |
| R4 | **空间失控** | 🟠 冻存/diff 工作流崩 | 阶段 7 必须先于规模验证；B.2.3 的既有 4.8 MB 冗余先清 |
| R5 | **36 类一次做完** | 🔴 范围爆炸 | 阶段 1 出矩阵，阶段 2/4 只做 3~4 类 |
| R6 | **AI 结论状态与 resolver 三态混淆** | 🟠 概念污染 | 设计文档 §24 已正确指出，**必须分别建模**：底层三态 = 图关系能否可靠解析；AI 状态 = 证据是否支持缺陷判断 |

---

## B.7 明确不做的事

| 不做 | 理由 |
|---|---|
| **完整 CPG** | 设计文档 §2 已论证；且语句级节点与 `symbol_id` 的编辑稳定身份**架构不兼容**（B.2.1） |
| 持久化完整 AST / 所有 Identifier / Literal / Expression | 设计文档 §18 |
| 用 `event_id` 做**语句级**稳定身份 | 同上 |
| 事件缓存进 `parsed` | B.2.3 —— 会重复存两遍 |
| `ALIAS` / `PARALLEL` 确定边 | 设计文档 §16：**不确定关系是 Evidence，不是 Fact Edge** |
| 在验证 Typed Query 正确性之前建 CSR | 附录 A：84 文件下查询只要 6 ms，收益为 0 |
| 把 AI 结论状态塞进 resolver 三态 | B.6 R6 |
| 上 Neo4j | 附录 A.6（打碎字节级确定性） |

---

## B.8 本附录数据的复现命令

```bash
PY="D:/program/Python312/python.exe"
DB="D:/代码理解/provenlattice_镜像版本/.provenlattice/codegraph.db"

# nodes.metadata 膨胀（94.8%）与 File 节点 61,614 B/行
$PY -c "
import sqlite3; c=sqlite3.connect(r'$DB')
for k,s,n in c.execute('SELECT kind,SUM(LENGTH(metadata)),COUNT(*) FROM nodes GROUP BY kind ORDER BY 2 DESC'):
    print(f'{k:12} {s/1024/1024:6.3f} MB {n:4} 行 {s/n:8.0f} B/行')
"

# parsed 内部构成（references 4.70 MB）与重复计数
$PY -c "
import sqlite3,json; c=sqlite3.connect(r'$DB'); t={}
for (m,) in c.execute(\"SELECT metadata FROM nodes WHERE kind='File'\"):
    for k,v in json.loads(m)['parsed'].items(): t[k]=t.get(k,0)+len(json.dumps(v))
print({k:round(v/1024/1024,2) for k,v in t.items()})
"

# 事件量估算基数
$PY -c "
import sqlite3; c=sqlite3.connect(r'$DB')
for t,n in c.execute('SELECT reference_type,COUNT(*) FROM raw_references GROUP BY 1 ORDER BY 2 DESC'):
    print(f'{t:12} {n:6}  {n/10115:.2f}/行')
"
```

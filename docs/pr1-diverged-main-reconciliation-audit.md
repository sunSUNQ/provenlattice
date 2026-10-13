# PR1 Diverged Main Reconciliation Audit

> 任务:PL-PR1-DIVERGED-MAIN-RECONCILIATION-AUDIT(2026-10-12)
> 判定:**RECONCILIATION_PLAN_READY**
> 本轮仅分析与方案设计，未实施 revert/merge/push/主干修改。

---

## 1. Git 分叉拓扑

```
                        ┌── local main: 8ee007a
                        │   (selective integration: I0→I1-A→I1-B→I1-C→I2-A→I2-B1
                        │    →overnight→qualification→review→postmerge)
                        │   11 commits, 408/408 tests, L1 parity PASS
14499f8 (common ancestor)
                        │
                        └── remote main: 348f6e6
                            (full PR #1 merge via GitHub PR)
                            1 merge commit (14499f8 + fcd363c)
                            includes: cold store, declarations refactor
                                      in parse path, streaming incremental,
                                      full defect.py, contracts.py
```

| SHA | 分支 | 含义 |
|---|---|---|
| `14499f8` | common ancestor | 合并前 main |
| `8ee007a` | local main | 选择性集成(408/408, L1 parity PASS) |
| `348f6e6` | remote main (origin/main) | GitHub 上完整合并了 PR #1 |
| `3c3f2d1` | integration/pr1-selective | = 8ee007a(同一棵树) |
| `fcd363c` | PR #1 fork/main head | PR 分支最后一个 commit |

## 2. 逐模块差异矩阵

### 2.1 L1 基础图谱文件

| 文件 | local (8ee007a) | remote (348f6e6) | 分类 | 证据 |
|---|---|---|---|---|
| graph.py | **零 diff** | +179/-9: PR 将 EventExtractor/SparseCfgBuilder/mint_dataflow_edges 直接嵌入 build_graph() | **REMOTE_ONLY_EXCLUDED** | 默认 index 强制执行 Event/CFG/DFG 提取，违反 Gold Target V2 原则 5（低成本默认服务）；选择性集成将此改为按需 analyzer |
| scanner.py | 零 diff | 零 diff | **KEEP** | 双方一致 |
| resolver.py | 零 diff | +116/-136: 流式 resolver 重构（references 流式传输替代物化） | **REMOTE_ONLY_EXCLUDED** | 流式增量优化，I2-A 边界明确排除；性能改进但语义变化未经验证 |
| shard.py | 零 diff | +29: 冷存储相关 shard 变更 | **REMOTE_ONLY_EXCLUDED** | 冷存储默认化被排除 |
| overlay.py | 零 diff | +变更：overlay 适配冷存储 | **REMOTE_ONLY_EXCLUDED** | 依赖冷存储布局 |
| incremental.py | 零 diff | +29/-: 流式增量(parser cache 从 cold store 读取) | **REMOTE_ONLY_EXCLUDED** | I2-A 边界排除 |
| storage.py | 零 diff | +572/-35: cold.db ATTACH/COLD_SCHEMA/legacy 检测 | **REMOTE_ONLY_EXCLUDED** | 冷热存储分离改变默认布局，影响备份/status/工具链 |

### 2.2 解析层

| 文件 | local | remote | 分类 | 证据 |
|---|---|---|---|---|
| parsing/cpp.py | 零 diff | +102/-3: DeclarationIndex.build() 嵌入 parse 路径 + SparseCfgBuilder 调用 | **REMOTE_ONLY_EXCLUDED** | declarations 重构替换 L1 符号抽取路径——选择性整合的核心排除项 |
| parsing/declarations.py | **LOCAL_ONLY**(465 行 verbatim) | **REMOTE_ONLY**(同文件不同版本，嵌入 parse 路径) | **KEEP(局部)** | 本地将 declarations.py 作为独立 analyzer 输入(不嵌入 parse)；远程将其嵌入 parse。文件内容基本一致，但调用位置不同 |
| parsing/events.py | **LOCAL_ONLY**(307 行) | **REMOTE_ONLY**(307 行) | **KEEP** | 内容一致，但 local 由 analyzer 调用，remote 由 cpp.py parse 嵌入调用 |
| parsing/python.py | 零 diff | +变更(适配) | **REMOTE_ONLY_EXCLUDED** | Python 侧适配，当前范围仅 C/C++ |
| parsing/tree_sitter.py | 零 diff | +变更 | **REMOTE_ONLY_EXCLUDED** | 适配变更 |

### 2.3 语义层

| 文件 | local | remote | 分类 | 证据 |
|---|---|---|---|---|
| semantics/__init__.py | 导出 events/vocabulary | 导出 events/vocabulary/contracts | **CONFLICT** | 远程额外导出 contracts 模块；本地选择性裁剪 |
| semantics/events.py | LEVEL_0+LEVEL_1+SemanticEvent(+I1-C SemanticEdge) | 同内容 | **KEEP** | 一致 |
| semantics/vocabulary.py | 500 行(裁剪+回置 defect_patterns) | ~500 行(PR 全量) | **CONFLICT** | 内容基本一致但注释/组织不同；本地有 I1-A 的裁剪注释 |
| semantics/contracts.toml | **不存在** | **REMOTE_ONLY** | **REMOTE_ONLY_ALLOWED** | 所有权契约 TOML 数据；resource_lifetime/lock_order/race_condition 需要 |
| semantics/vocabularies/python.toml | **不存在** | **REMOTE_ONLY** | **REMOTE_ONLY_ALLOWED** | Python 词汇表；当前范围仅 C/C++ 但数据无害 |
| semantics/taint.toml | **LOCAL_ONLY**(209 行) | **REMOTE_ONLY**(209 行) | **KEEP** | 内容一致 |
| semantics/defect_patterns.toml | **LOCAL_ONLY**(224 行) | **REMOTE_ONLY**(224 行) | **KEEP** | 内容一致 |

### 2.4 分析引擎

| 文件 | local | remote | 分类 | 证据 |
|---|---|---|---|---|
| analysis.py | **LOCAL_ONLY**: Capability Contract + dependency_staleness + PK migration + composite PK | PR 不修改此文件 | **SELECTIVE_ONLY** | 408 测试验证 |
| analysis_c_events.py | **LOCAL_ONLY**: 按需事件 analyzer | 不存在(remote 嵌入 parse) | **SELECTIVE_ONLY** | I1-A 设计 |
| analysis_c_scfg.py | **LOCAL_ONLY**: 按需 sparse CFG analyzer | 不存在 | **SELECTIVE_ONLY** | I1-B 设计 |
| analysis_c_dfg.py | **LOCAL_ONLY**: 按需 DFG analyzer | 不存在 | **SELECTIVE_ONLY** | I1-C 设计 |
| analysis_semantic_common.py | **LOCAL_ONLY**: 共享 owner 对齐 | 不存在 | **SELECTIVE_ONLY** | 消除重复 |
| analysis_c_ast.py | I0R1 对齐修复(名称+definition 消歧) | 无此修复 | **SELECTIVE_ONLY** | 修复单行 for 缺口 |
| analysis_c_cfg.py | I0R1 单行 for 修复 + I1-A 依赖门 + I1-B 依赖证明 | 无此修复 | **SELECTIVE_ONLY** | 修复+防御 |
| analysis_cfg.py | cfg:python v2 + 依赖证明 | cfg:python v1 | **SELECTIVE_ONLY** | 依赖新鲜度 |
| analysis_query.py | 六态 + events/sparse_cfg/sparse_dfg/defect 查询面 | 基础六态 | **SELECTIVE_ONLY** | I1-A/I1-B/I1-C/I2-A 增量 |
| orchestrator.py | defect query-time + 三条 FEATURE_DEPENDENCIES | 基础 | **SELECTIVE_ONLY** | |
| defect_query.py | **LOCAL_ONLY**: 纯查询读取器 | 不存在(PR 用 GraphQuery.get_defect_candidates) | **SELECTIVE_ONLY** | 重写以适配 AnalysisStore |
| contracts.py | **LOCAL_ONLY**(626 行 verbatim) | **REMOTE_ONLY**(同文件) | **KEEP** | 内容一致 |

### 2.5 defect 查询层

| 文件 | local | remote | 分类 | 证据 |
|---|---|---|---|---|
| defect.py | 5,473 行(I2A 裁剪→overnight 全 8 查询) | 5,491 行(PR 全量) | **CONFLICT** | 内容基本一致；local 有 I2A 注释；run() 分发表/QUERY_NAMES 一致(8 查询) |
| evidence.py | +DefectEvidenceBundle + DEFECT_CANDIDATE kind | 同 | **KEEP** | 一致 |
| identity.py | +event_id/semantic_edge_id/cfg_exit_id/CFG_EXIT_PREFIX | 同 | **KEEP** | 一致 |
| models.py | +ParsedEvent/PointKey/ParsedPoint/ParsedEdge/ParsedCfg/STORAGE_* | 同 | **KEEP** | 一致 |
| sparsecfg.py | 2,641 行(I1-B 裁剪→I2-B1 回置 patterns) | 2,646 行(PR 全量) | **CONFLICT** | 内容基本一致；local 裁剪了 defect patterns 但后回置 |
| sparsedfg.py | 694 行(I1-C 裁剪→I2-A 回置 bind_parameters) | 696 行(PR 全量) | **CONFLICT** | 内容基本一致 |

### 2.6 CLI 与查询服务

| 文件 | local | remote | 分类 | 证据 |
|---|---|---|---|---|
| cli.py | +defect 命令(调用 defect_query.query_defect_candidates) | +defect 命令(调用 GraphQuery.get_defect_candidates) | **CONFLICT** | 同名命令，不同后端；local 纯查询+fail-closed，remote 查询+物化 |
| query.py | 零 diff | +get_defect_candidates + _semantic_layer | **REMOTE_ONLY_EXCLUDED** | PR 将 defect 查询嵌入 GraphQuery——选择性集成用 defect_query.py 替代 |

## 3. 三种恢复策略评估

### 策略 A：远程 revert PR #1 merge → 整合选择性实现

```bash
# 在 origin/main 上创建恢复分支
git checkout -b reconcile/revert-pr1 origin/main
git revert --no-edit 348f6e6  # revert the merge commit
# 然后合并选择性集成
git merge integration/pr1-selective
```

| 维度 | 评估 |
|---|---|
| Git 历史安全 | ✓ 不修改远程；在新分支上操作；revert 保留原始 merge 历史 |
| 冲突风险 | **高**：revert 348f6e6 会恢复到 14499f8 状态，然后 merge 8ee007a 可能产生大量冲突(graph.py/storage.py/resolver.py 等均被 PR 大幅修改) |
| 重复代码 | 低——选择性集成是裁剪版，revert 后从零开始 |
| 数据迁移 | 无(选择性集成有 PK 迁移逻辑) |
| 协作者影响 | 中——revert 会让 PR #1 的贡献者看到他们的工作被"撤销" |
| 测试工作量 | 中——需要运行 408 测试 + L1 parity |
| Gold Target V2 兼容 | ✓ 完全符合(按需分析、L1 不变) |
| 未来重引入 PR 代码 | **困难**——Git 的 revert-of-merge 语义意味着未来重新 merge PR #1 时 Git 可能跳过已 revert 的变更，需要手动 re-apply |

**风险**：revert-of-merge 的历史语义复杂，未来重新引入 PR 代码时需要 revert the revert 或 cherry-pick。

### 策略 B：保留远程 main 不动，将选择性集成发布为候选分支

```bash
# 不修改远程 main
# 推送选择性集成为新分支
git push origin integration/pr1-selective:candidate/selective-defect-queries
# 或推送到 feature 分支
git push origin integration/pr1-selective:feature/defect-queries
```

| 维度 | 评估 |
|---|---|
| Git 历史安全 | **最高**——完全不修改远程 main |
| 冲突风险 | 零——不合并 |
| 重复代码 | 暂时存在(远程有 PR 全量，分支有选择性集成) |
| 数据迁移 | 无(分支上已有 408 测试验证) |
| 协作者影响 | 最低——远程 main 不变，协作者可选择切换 |
| 测试工作量 | 已完成(408/408) |
| Gold Target V2 兼容 | ✓ 分支上的代码完全符合 |

**风险**：远程 main 上的冷存储/declarations 重构继续存在；协作者可能在错误的代码基础上工作。需要清晰的 README/分支说明。

### 策略 C：以远程 main 为基础，逐项剔除不合格改动

```bash
# 以 origin/main 为基础创建新分支
git checkout -b reconcile/from-remote origin/main
# 逐文件恢复 main 版本的排除文件
git checkout 14499f8 -- src/provenlattice/graph.py
git checkout 14499f8 -- src/provenlattice/resolver.py
git checkout 14499f8 -- src/provenlattice/storage.py
git checkout 14499f8 -- src/provenlattice/incremental.py
git checkout 14499f8 -- src/provenlattice/shard.py
git checkout 14499f8 -- src/provenlattice/overlay.py
# ... 逐项恢复，然后合并选择性集成的按需 analyzer
```

| 维度 | 评估 |
|---|---|
| Git 历史安全 | 中——在新分支上操作，但"逐项剔除"本质上是选择性的反操作 |
| 冲突风险 | **高**——cpp.py 中的 declarations 重构与事件抽取钩子深度纠缠，逐文件恢复会破坏事件提取 |
| 重复代码 | 中——需要仔细对齐 local 和 remote 的共享模块 |
| 数据迁移 | 无——从远程 schema 开始 |
| 协作者影响 | 低——基于远程历史 |
| 测试工作量 | **高**——每次剔除后需要运行全量测试确认没有破坏 |
| Gold Target V2 兼容 | ✓ 如果剔除正确 |

**风险**：cpp.py 是最大风险点——PR 将 DeclarationIndex.build() 和 SparseCfgBuilder 嵌入 parse 路径，与事件提取钩子纠缠。逐文件恢复会需要手动分离这两者。

## 4. 推荐方案

**推荐策略 B：保留远程 main 不动，将选择性集成发布为候选分支。**

### 理由

1. **安全性最高**：远程 main 不被修改，PR #1 的贡献者工作不被"撤销"
2. **验证已完成**：408/408 测试 + L1 parity + 8/8 CLI smoke 已在分支上通过
3. **无时间压力**：分支可以随时合并，不需要紧急操作
4. **未来灵活**：维护者可以在候选分支基础上决定最终合并策略
5. **冷存储/declarations 重构不丢失**：远程 main 上的这些实现保留，未来可通过 Capability Contract 按需启用

### 执行命令草案

```bash
# 1. 推送选择性集成分支到远程
git push origin integration/pr1-selective:candidate/selective-defect-queries

# 2. (可选) 推送 main 作为备份
git push origin main:backup/selective-integration-main

# 3. 在 GitHub 上创建 PR: candidate/selective-defect-queries → main
#    由维护者审查后决定合并策略
```

### 合并后重新验收要求

无论最终采用哪种方案合并到 main，都需要重新执行：

1. 408 项全量测试
2. L1 parity (node/edge id 逐 ID)
3. 旧库 PK 迁移测试
4. 八类查询 CLI smoke
5. 纯查询不写库验证
6. 5 轮配对性能测量
7. 默认 index 零检测产物验证

---

## 5. 逐项 KEEP/EXCLUDE/CONFLICT 决策

### KEEP(两条分支一致，无需操作)

- `parsing/declarations.py` 内容
- `parsing/events.py` 内容
- `semantics/taint.toml` 内容
- `semantics/defect_patterns.toml` 内容
- `contracts.py` 内容
- `evidence.py` DefectEvidenceBundle + DEFECT_CANDIDATE
- `identity.py` event_id/semantic_edge_id/cfg_exit_id
- `models.py` ParsedEvent/PointKey/ParsedPoint/ParsedEdge/ParsedCfg/STORAGE_*
- `sparsecfg.py` SparseCfgBuilder + walker(8 查询依赖)
- `sparsedfg.py` mint_dataflow_edges + bind_parameters
- `semantics/vocabulary.py` Vocabulary/EventSpec/load_defect_patterns
- `semantics/events.py` LEVEL_0/LEVEL_1/SemanticEvent/SemanticEdge

### SELECTIVE_ONLY(本地独有，应在最终版本保留)

- `analysis.py` Capability Contract + dependency_staleness + PK migration
- `analysis_c_events.py` / `analysis_c_scfg.py` / `analysis_c_dfg.py` 按需 analyzer
- `analysis_semantic_common.py` 共享 owner 对齐
- `defect_query.py` 纯查询读取器
- `analysis_c_ast.py` I0R1 对齐修复
- `analysis_c_cfg.py` I0R1 单行 for 修复 + 依赖门
- `analysis_cfg.py` cfg:python v2 + 依赖证明
- `analysis_query.py` 扩展查询面
- `orchestrator.py` defect query-time 集成
- `cli.py` defect 命令(调用 defect_query)

### REMOTE_ONLY_EXCLUDED(远程独有，违背当前架构约束)

| 文件 | 远程变更 | 排除理由 |
|---|---|---|
| graph.py | EventExtractor/SparseCfgBuilder/mint 嵌入 build_graph | 违反原则 5: 默认 index 强制执行 Event/CFG/DFG 提取 |
| storage.py | cold.db ATTACH/COLD_SCHEMA/legacy 检测 | 冷存储默认化被排除(I2-A 边界) |
| resolver.py | 流式 resolver 重构 | I2-A 边界排除 |
| incremental.py | 流式增量(parser cache 从 cold store 读取) | I2-A 边界排除 |
| shard.py | 冷存储相关 shard 变更 | 依赖冷存储布局 |
| overlay.py | overlay 适配冷存储 | 依赖冷存储布局 |
| parsing/cpp.py | DeclarationIndex.build() 嵌入 parse 路径 | **核心排除**——替换 L1 符号抽取路径 |
| parsing/python.py | Python 侧适配 | 当前范围仅 C/C++ |
| parsing/tree_sitter.py | 适配变更 | 与 cpp.py 联动 |
| query.py | GraphQuery.get_defect_candidates | 重写为 defect_query.py |
| semantics/contracts.toml | 所有权契约数据 | REMOTE_ONLY_ALLOWED——但不嵌入 parse |

### REMOTE_ONLY_ALLOWED(远程独有，符合架构，可后续启用)

- `semantics/contracts.toml` — 所有权契约数据(ContractTable 输入)
- `semantics/vocabularies/python.toml` — Python 事件词汇表(当前范围仅 C/C++)
- cold store 代码(已验证，但默认不启用——策略：后续通过 opt-in flag 启用)

### CONFLICT(需要人工判断或进一步验证)

| 文件 | 冲突描述 |
|---|---|
| defect.py | 两条线都有 5,4xx 行版本；内容基本一致但注释/组织不同。本地有 I2A 裁剪注释，远程有 PR 全量注释。**建议以本地为准**(已通过 408 测试) |
| sparsecfg.py | 本地 2,641 行(裁剪+回置 patterns) vs 远程 2,646 行(全量)。**建议以本地为准** |
| sparsedfg.py | 本地 694 行(裁剪+回置 bind_parameters) vs 远程 696 行(全量)。**建议以本地为准** |
| semantics/vocabulary.py | 本地 500 行(裁剪+回置 defect_patterns) vs 远程 ~500 行(全量)。**建议以本地为准** |
| semantics/__init__.py | 导出列表差异。**建议合并为超集** |
| cli.py | defect 命令后端不同(local: defect_query.py, remote: GraphQuery)。**建议以本地为准**(纯查询) |

---

## 6. CONSUMES 低产出根因(补充审计)

`_alloc_handoff` 仅在 `f(malloc(n))` 直接嵌套形状盖章 `passed_to`。赋值形状 `p = malloc(n); f(p)` 的 passed_to 为空("an allocation in a loop heading hands over nobody")。这是 **PR 设计选择**(nearest ancestor wins)，不是缺陷——`p = malloc(n); f(p)` 的数据流已由 DATA_FLOW_TO (alloc_to_use) 覆盖。

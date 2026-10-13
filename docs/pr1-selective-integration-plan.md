# PR #1 Selective Integration Plan R1（选择性集成方案）

> 任务：PL-PR1-CAPABILITY-RECONCILIATION-R1（2026-10-12）
> 文档地位：集成实施规划。事实依据见
> [docs/pr1-capability-reconciliation.md](pr1-capability-reconciliation.md)（选择矩阵）
> 与 [docs/pr1-comparison-test-results.md](pr1-comparison-test-results.md)（实测数据）。
> **本计划未开始执行**；启动前需人工审核选择矩阵与门槛。

## 0. 总原则（承接任务边界）

1. **禁止"先完整合并 PR 再删重复"**——每步只迁移通过审查的能力及其必要依赖。
2. **以 main `14499f8` 为基础**创建 `integration/pr1-selective`；PR 作为能力来源分支参考（`fork/main` = `fcd363c`），不做 merge。
3. **L1 默认服务不可感知回归**：每步以本轮冻结的 main 基线为门（§2 G0）。
4. 每步有明确验收门与回退（feature 级回退，不整体回滚）。
5. 语义事件/Sparse CFG/DFG/缺陷查询一律以**可选 analyzer** 形态进入（Capability × Scope），绝不进 L1 默认路径。

## 1. 依赖关系图（迁移顺序的依据）

```text
parsing/cpp.py 事件钩子 ──┐
semantics/(vocabulary+TOML) ──┼─→ parsing/events.py ─→ models(PointKey/ParsedEvent/ParsedCfg)
parsing/declarations.py ✗(不迁)│                        ├─→ sparsecfg.py ─→ defect.py(8 queries) → CLI defect
storage(semantic_* 表)  ──────┘                        ├─→ sparsedfg.py ─↗
                                                       └─→ contracts.py ─↗
resolver/storage 流式 update(7A-2) ──→ (独立, legacy 布局可先行)
storage 冷/热分离(7A-1/3) ──→ (独立, opt-in, 最后)
Analyzer Capability Registry ──→ (I5, 接线层)
```

关键纠缠点：PR 的 `parsing/cpp.py` 同时承载（a）语义事件钩子、（b）declarations 重构
（导致 L1 符号集合变化，对账报告 §3.1）。选择性集成必须只取（a）。

## 2. 全局门槛（每步验收都要跑）

| 门 | 内容 | 通过标准（本轮冻结基线） |
| --- | --- | --- |
| **G0 L1 默认成本回归** | 不启用任何新 analyzer 时，aria2 同语料 index / update / 查询 / 库大小 | index ≤ 7.5s、峰值 RSS ≤ 240MB、查询均值 ≤ 基线 +20%、L1 库大小 ≤ 基线 +5%（多轮中位制，取代本轮单次口径） |
| **G1 L1 基础图 parity** | nodes/edges 按 kind 分布与 main 逐类一致（aria2 + tests/fixture_*） | Function/Method/DEFINES 等每类计数一致（±0）；`find_symbol` 对 main-only 名单（2,469 Function + 1,393 Method 样本）全部可查询 |
| **G2 既有测试** | main 254 测试全过 + 新增能力自带测试 | 0 失败 |
| **G3 确定性** | 两次构建候选集/图位级一致 | 与 PR 自证方法同口径 |

## 3. 集成步骤（按依赖排序）

### I1 — 语义事件层（可选 analyzer）+ Sparse CFG/DFG 数据层

- **迁移物**：`semantics/`（vocabulary/events/contracts/defect_patterns TOML + `vocabulary.py`）、`parsing/events.py`、`sparsecfg.py`、`sparsedfg.py`、`models.py` 的 ParsedEvent/PointKey/ParsedPoint/ParsedEdge/ParsedCfg、`identity.py` 事件身份、`storage.py` 的 `semantic_events/semantic_edges/semantic_fingerprint` 表（惰性创建）。
- **不迁移**：PR `cpp.py` 的 declarations 重构（G1 一票否决项）。
- **工程做法**：在 main 的 `cpp.py` 上重新实现事件钩子（仅挂 tree-sitter 遍历埋点，不动符号/引用抽取路径）；以 `provenlattice analyze --features events,sparsedefect`（命名由 I5 定）按 scope 触发。
- **验收**：G0+G1+G2；夹具集事件/边形状与 PR 实测一致（对照报告 §3.1 表逐行比对）；aria2 事件计数在同一数量级且确定性可复现（G3）。
- **前置修复任务**：main 单行 for 的 `no_functions_built` 健壮性缺口（对照报告 §3.2；修在 main 侧，属 Full CFG 质量项，不阻塞 I1 但同分支完成）。
- **回退**：analyzer 不注册即消失；`semantic_*` 表惰性创建、可整表 drop。

### I2 — 缺陷查询 + Evidence Bundle + CLI

- **迁移物**：`contracts.py`、`defect.py`（含 7B-1 共享物化、stage-8 证据路径、stage-9 规则修复）、CLI `defect` 命令、`evidence.py` 的 E-DEFECT- 契约。
- **前置**：**修复 PR test_defect CliTests 的空库打开缺陷**（对照报告 §2.1）——测试与 CLI 校验顺序一起修。
- **验收**：G0–G3；夹具 double_free 三路径（查询名/矩阵键/all）结果一致（本轮已验证的三路径探针固化为回归测试）；aria2 上 8 查询可运行且 coverage 结构完整（population/states 与 §3.4 同口径）。
- **回退**：`defect` 命令移除注册；查询层为只读。

### I3 — 流式 update（7A-2）移植到 legacy 布局

- **迁移物**：resolver/incremental 的流式引用行携带（`_survives`/`replace_snapshot` 只重写变更行）。
- **验收**：G1（update 后图 parity）+ 增量成本多轮对比（本轮 NOT_TESTED 的隔离 A/B 在此补测；通过标准：增量峰值 RSS 不高于 main 基线，正确性 parity 逐表一致）。
- **回退**：保留 main 原物化路径开关。
- **依赖**：可与 I1/I2 并行评审，落地顺序在 I2 之后（降低同分支冲突面）。

### I4 — 冷/热存储分离（7A-1/7A-3）——opt-in，最后决策

- **迁移物**：`storage.py` 冷库 ATTACH/TEMP VIEW/legacy 检测/`copy_database`、`status` 的 cold 字段。
- **形态**：**默认 legacy 布局不变**；冷布局作为 opt-in（CLI flag 或 profile）。查询加速收益（本轮实测 1.5–2×）在 opt-in 下获得。
- **验收**：G0（legacy 默认路径逐字节不变）；opt-in 下 8 表 parity + 双布局交付视图一致（复用 PR 自证方法）；备份/status 工具链影响清单评审通过。
- **阻塞条件 B4**：备份/恢复与外部工具对第二库文件的兼容性评审未过 → I4 无限期推迟（I1–I3 不依赖冷布局，PR 已内建 legacy 分支能力）。
- **回退**：不启用即完全无影响。

### I5 — Analyzer Capability Registry / Profile 接线（Gold Target V2 落地）

- **内容**：把 I1–I2 能力注册进 Registry（依赖/语言/成本/缓存失效元数据）；`security` profile 的最小配置示例；L3 双入口（task-context 与 defect 互不隐式触发）。
- **验收**：profile 切换零常驻成本；L1-only 默认仍是出厂状态。

## 4. 阻塞条件与解决方案（不默认两套实现长期共存）

| # | 阻塞 | 触发判据 | 解决方向 | 演化终点 |
| --- | --- | --- | --- | --- |
| B1 | 事件钩子与 declarations 重构在 PR cpp.py 中纠缠 | I1 移植发现钩子无法在 main 抽取路径上独立挂载 | 要求 PR 方提供钩子-重构分层说明；或以 main cpp.py 为底重写埋点（工作量备选方案已在 I1 工程做法中给出） | 单一抽取管线，事件/符号同源 |
| B2 | G1 L1 parity 失败 | 任一节点/边 kind 分布偏差 >0 | 停止迁移，偏差归因（PR 解析器 vs 移植缺陷）；CALLS +92 的改进项单独评估回 port | 统一到重新资格化的抽取契约 |
| B3 | 双 walker 语义漂移 | Full/Sparse 对同一构造结论冲突且不可归因（goto、短路为先行探针） | 建立投影 oracle（Gold Target V2 T2）：Full↔Sparse 逐构造对照表进 CI；冲突项登记为差异矩阵行 | Canonical CFG + Full/Sparse 双视图（V2 原则 4） |
| B4 | 冷布局外部兼容性 | 备份/恢复/工具链评审未过 | I4 独立推迟；流式 update（I3）先行获取内存收益 | 布局决策以独立证据重启 |
| B5 | defect 候选质量门槛 | 正式 precision 复核批次（Phase 1）低于既定门槛 | 缺陷查询保留 `--no-contracts`/scope 限制，registry 定价标注 diagnostic 级 | stage-4 契约/注解层补 API-contract 知识 |

## 5. 与既有治理机制的关系

- 每步的验收数据按项目惯例冻结为 artifact（多轮中位制）；G0/G1 的基线来自本轮 R1 实测，正式门槛在 I1 启动时以多轮口径重冻结。
- 本计划不修改 `docs/roadmap.md` 的 Gold Target V2 与三臂实验设计；I1–I5 完成即构成三臂实验 C 臂（统一架构原型）的候选 tag，届时按 V2 §8 执行对照实验。

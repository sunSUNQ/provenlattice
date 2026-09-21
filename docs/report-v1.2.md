# ProvenLattice V1.2 能力与实验总结（汇报稿）

> 汇报日期：2026-09-20 · 当前版本：**SQI-V1.2 = QUALIFIED / RELEASE READY**（tag
> `provenlattice-sqi-v1.2`，GitHub Release 已发布）
> 一键验证：`python experiments/query_interface_v1/tools/verify_release.py` → PASS

---

## 1. 项目定位（一句话）

**ProvenLattice** 是面向 Code Agent 的"可追溯分层工程证据图"：把代码结构、文档、
规范等工程信息组织成**可查询、有边界、带证据引用**的结构化上下文，让 Agent
不再靠无界搜索和全文阅读理解大型仓库，而是通过一组**有界、可引用、可验证**的
结构化查询直接消费工程知识。

---

## 2. 当前版本能力地图

### 2.1 核心证据图引擎（`src/provenlattice`）

| 能力 | 说明 |
| --- | --- |
| 多语言代码结构建模 | tree-sitter 解析 C / C++ / Python：符号、定义、调用、引用、分片（shard） |
| 知识层 | Markdown 文档 / Section / Spec / Requirement / Constraint 建模，稳定 identity |
| 跨层证据关联 | 文档↔代码 CROSS_LAYER_LINK、RawEvidenceLink（resolved / ambiguous / unresolved 契约） |
| 变更影响 | impact frontier（变更分片 → 影响边界，带 membership 证据） |
| 增量与一致性 | 增量索引 vs 全量重建六状态层逐字节一致（RQ2 实证） |
| Overlay | 分支 / 会话级图叠加，full / incremental / overlay 三路 parity |

### 2.2 SQI 结构化查询接口（Agent 消费面，`experiments/query_interface_v1`）

七类规范化查询：`symbol.lookup / symbol.callers / symbol.callees /
symbol.references / impact.frontier / code.related / bundle.explain`，每类返回一个
**有界 JSON envelope**：

- **预算有界**：max_evidence / max_symbols / max_edges / max_sections 共享预算池，确定性前缀切片，`omitted_counts` 诚实报告被省略量；
- **证据可引用**：每个事实带 `E-*` 证据 id + provenance + 源码位置，Agent 只能引用实际返回的 id，评测器做 citation closure 校验；
- **跨库复合**：`code.related` 一次调用完成"文档锚点 → 跨层链接 + 链接代码定义"；
- **会话纪律**：相同调用返回 byte-identical envelope（杜绝重试膨胀）、usage discipline 随首个 envelope 注入、per-session call log 可审计。

### 2.3 资格认证与治理基础设施

- 冻结契约 + **SHA-256 seal 体系**（contract / implementation / secondary / protocol / amendment 五层），任何 envelope/prompt 语义变更必须重走 seal；
- 冻结 oracle 评测器（T01–T06）、逐 cell 隔离生命周期（CellWindow + cell-private claude home + 指纹校验 + 后端漂移门）、checkout 泄漏确定性扫描（`CHECKOUT_LEAKAGE`）；
- 成本逐源归因工具；失败/淘汰证据**显式标记、永不删除**；
- `verify_release.py` 一键复现全部结论（当前 7 项 seal + 4 个冻结 DB + 61/61 内建测试全 PASS）。

---

## 3. ProvenLattice 基座能力验证（CodeGraph Foundation）

> 基座不是"先做 Agent demo 再补图"，而是按下面的顺序逐层取得正式资格；
> 全部数字来自正式冻结 artifact（详证：`experiments/foundation_analysis/reviews/provenlattice-foundation-evidence-review.md`）。

```text
图是否构得出来？      → tree-sitter C/C++/Python 六状态层构图，三档真实大仓全部跑通
        ↓
图里的事实是否正确？  → RQ1 双盲 174 例 Gold，resolved precision 0.931 / 0.899（加权）
        ↓
大仓是否能够运行？    → aria2 118.9k / brpc 227.2k / RocksDB 622.8k LOC，RQ2 QUALIFIED
        ↓
增量更新是否仍然正确？→ 36/36 增量 rep 与全量重建在六状态层逐字节一致
        ↓
Agent 是否能消费？    → SQI formal 18/18，citation closure 18/18
        ↓
成本是否可控？        → V1.2 input -36% / output -58% / cache-read -73%
```

### 表 1：基座验证总览

| 验证线 | 回答的问题 | 正式结果 | 状态 |
| --- | --- | --- | --- |
| **RQ1 图保真度** | 图里的事实能不能信？ | 174 例双盲 Gold（CALLS 86 / IMPORTS 88）；resolved precision **0.931**（样本）/**0.899**（加权）；主要限制是覆盖而非错选 | **QUALIFIED**（2026-09-15，限 V0.2 / C-C++ / CALLS+IMPORTS / 三仓） |
| **RQ2 系统与规模** | 大仓能否构建、增量是否一致？ | 21 条正式记录；**36/36 增量 rep 六状态层 exact parity**；A/B 计数精确落冻结锚点；0 无效执行 | **QUALIFIED**（2026-09-16，Contract V1 scope） |
| **SQI 结构化查询** | 图能否被 Agent 稳定查询？ | SQI **18/18** vs Native 13/18（V1）/ 12/18（C4-R4 对照）；citation closure 18/18 | **QUALIFIED**（V1 + V1.2） |
| **V1.2 成本优化** | Agent 消费成本是否可控？ | input −36% / output −58% / cache-read −73%；T05 调用数 6–20/rep → 5/2/6 | **QUALIFIED / RELEASE READY** |

诚实边界：Overlay = IMPLEMENTED / PARTIALLY QUALIFIED（V0.4 工程 parity/conflict 证据，未进冻结正式资格，V1.1 NOT STARTED）；增量延迟当前**高于**全量构建（正式记录在案、非门禁）；核心图查询 p95/p99、并发 QPS、10M+ LOC、跨仓统一索引、向量索引、分布式同步 = 未测/未实现。

### 表 2：Benchmark Repository Scale（formal records）

| Repo | C/C++ LOC | Files | Symbols | Nodes | Raw References | Edges | Full Build (median, 5 reps) | Peak RSS | DB Size |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| aria2 | 118,926 | 1,168 | 27,936 | 29,117 | 49,109 | 37,074 | 4.49 s | 191 MB | 126.8 MB |
| brpc | 227,154 | 1,168 | 47,688 | 48,929 | 84,941 | 59,614 | 8.34 s | 314 MB | 229.1 MB |
| RocksDB | 622,772 | 1,478 | 117,097 | 118,655 | 311,111 | 143,585 | 28.24 s | 1,075 MB | 843.2 MB |

增量资格：3 repo × 4 mutation family（body edit / add symbol / delete file / cross-file signature change）× 3 reps = **36/36 PASS**，六个状态层（`nodes_facts / edges_facts / raw_references_facts / shards_facts / files_facts / shard_edges_facts`）digest 全等。在线查询（1,800 warm 样本）：callees median 20.8→74.1 ms、symbol 19.8→62.3 ms 随规模单调。

---

## 4. 实验线总览：每条线在验证什么、结果如何

| 实验线 | 回答的问题 | 方法 | 结果 |
| --- | --- | --- | --- |
| **RQ1 图保真度**（fidelity_v1） | 图里的事实对不对？ | 双盲人工标注（双标注员 + 分歧裁决 + 校准门 + 一致性审计） | **QUALIFIED**（2026-09-15），Resolved Precision **0.931**（样本）/ **0.899**（加权总体） |
| **RQ2 系统与规模**（systems_v1） | 大仓上增量对不对、快不快？ | 3 个真实大仓（aria2 118.9k / brpc 227.2k / rocksdb 622.8k LOC）× 四类工作负载 | **QUALIFIED**（2026-09-16）：21 条有效正式记录，**36/36 增量资格 rep 与全量逐字节一致**，scale 精确落在冻结锚点带，0 无效执行 |
| **SQI-V1 结构化查询资格**（query_interface_v1） | Agent 用 SQI 比裸读文件强多少？ | Native vs SQI 双臂 36 formal cells（6 任务 × 2 臂 × 3 rep） | **QUALIFIED**（2026-09-17）：**SQI 18/18 vs Native 13/18**；T02 1/3→3/3、T04 0/3→3/3（无回归）；citation closure 18/18 |
| **SQI-V1.1 加固** | 证据纪律能否防作弊、防泄漏？ | sandbox 预防 + 检测双层、T05 fixture 双库一致性修复、oracle 归一化前置冻结 | **PASS**：越界读取 live 实证 DENIED、CHECKOUT_LEAKAGE 扫描、杜绝批后归一化 flip |
| **SQI-V1.2 成本优化**（C0–C4） | 能力不回退的前提下，Agent 检索成本能降多少？ | C0 成本逐源归因 → C1 目标冻结 → C2 压缩/缓存实现 → C4 完整重资格（4 轮失败归因 + 通用修复 + 第 5 轮 GREEN） | **QUALIFIED / RELEASE READY**（2026-09-20）：SQI **18/18**、9/9 floors、单 backend，成本 **input -36% / output -58% / cache-read -73%** |

---

## 5. 六个冻结任务 = Agent 能力的六个维度

| 任务 | 仓库 | 难度 | 考察能力 |
| --- | --- | --- | --- |
| T01 符号定义定位 | aria2 | Easy | symbol.lookup：给定类名找到定义与文件 |
| T02 调用者遍历 | brpc | Medium | symbol.callers：生产代码中找全部调用点 |
| T03 引用证据 | rocksdb | Medium | symbol.references：宏包装下全部引用 + 状态 |
| T04 变更影响边界 | rocksdb | Hard | impact.frontier：大变更的影响面 + 诚实截断 |
| T05 需求→代码证据 | brpc | Medium | code.related：中文文档段落 → 跨层链接 → 代码实现（跨库复合，最难的探索任务） |
| T06 预算化解释 | brpc | Hard | bundle.explain：单次调用内预算化总结 + 截断诚实性 |

---

## 6. V1.2 深挖：成本是怎么降下来的（汇报重点）

### 6.1 起点：C0 成本归因（先定位钱花在哪）

V1.1 时代 SQI 臂赢在能力（18/18 vs 13/18）但代价高：input 963k vs native 527k、
cache-read 14.7M vs 3.4M、**cache amplification 15.3×** 是成本主导机制——
重复调用与超预算 envelope 反复进上下文。

### 6.2 优化与修复（全部通用机制，不针对任何具体任务硬编码）

1. **OPT-T05 envelope 压缩 + 会话缓存**：相同调用返回字节级相同 envelope，
   重复调用零重算；
2. **NR1 完成/重复调用纪律**：禁止 identical 重试、完成前校验证据域覆盖；
3. **NR2 空结果探索稳定性修复**（本版本核心增量）——机器归因发现：agent
   探索失败不是检索层缺陷，而是**接口语义对 agent 不可见**。修复为四处
   通用机制（无任务特判、无硬编码 required id、无 oracle 变更）：
   - 空 envelope 附带"锚点解析按调用类型限定"语义指导；
   - 会话纪律第三条规则（与 prompt 镜像）；
   - 子集条款：同锚点更小预算重查只返回首 envelope 的子集，永不增加信息
     （冻结库上实证）；
   - prompt 接口文档：code.related 是"文档→代码"复合查询，bundle.explain
     只返回本地 bundle。

### 6.3 效果

| 指标 | V1.1 baseline | V1.2（C4-R4） | Δ |
| --- | --- | --- | --- |
| input tokens | 962,640 | 616,598 | **-36%** |
| output tokens | 230,508 | 97,249 | **-58%** |
| cache-read tokens | 14,738,944 | 3,954,944 | **-73%** |
| cache amplification | 15.3× | 6.4× | **-58%** |
| SQI 调用次数 | 59 | 49 | -17% |
| envelope 字节 | 517,226 | 384,049 | **-26%** |

同时**能力不降反升**：最难的探索任务 T05 每 rep 调用数从 6–20 次降到
**5/2/6 次**；T06 每个 cell 恰好一次 bundle.explain；全部 6 任务 3/3。

### 6.4 资格证据强度

- 完整 clean 36-cell batch（C4-R4），**单 backend**（deepseek-flash ×36），
  逐 cell 模型 provenance 与后端漂移门，零 sensitive leakage；
- **SQI 18/18，9/9 frozen floors PASS，verdict QUALIFIED**；
- 修复路线完整入档：C4-R3 的 17/18（HOLD/PARTIAL）与 4 轮失败 ladder 全部
  保留为历史证据——每轮失败机器归因 → 通用修复 → 定向 ladder 验证 →
  最终完整重资格，**不是补跑到过线**。

---

## 7. 质量与治理数据（一页备查）

| 项 | 数据 |
| --- | --- |
| 测试 | **97/97 PASS**（implementation + wiring + isolation + 纪律测试） |
| Seal | 7 项全 PASS（contract 6/6、implementation 5/5、protocol 2/2、amendment 2/2、secondary 10/10、systems 25/25、frozen DB 4/4） |
| 隔离 | 36/36 cell window closed / restore verified / fingerprint unchanged |
| 证据保留 | 失败与 superseded 证据显式标记、永不删除（C4-R2 污染、C4-R3 HOLD/PARTIAL、4 轮失败 ladder 均在档） |
| 复现 | `verify_release.py` 一键验证全部结论 |

---

## 8. 边界与下一步（诚实声明）

- V1.1 baseline 运行于混合 backend，跨时代 token 对比带残留 caveat（C4-R4
  自身为单 backend）；
- Native 对照方差（T02/T04 native 0/3）是模型行为漂移，与 SQI 无关；
- 明确未做：S3+ 更大规模带与并发、第四个 benchmark 仓库、Overlay V1.1、
  Runtime/Log 证据层；
- envelope/prompt 语义此后任何变更须重走 seal + qualification 流程。

## 9. 证据索引（现场可查）

| 内容 | 位置 |
| --- | --- |
| 发布文档 | `docs/releases/sqi-v1.2.md` |
| 最终资格评审 | `experiments/query_interface_v1/reviews/v1.2-final-qualification-review.md` |
| C4-R4 综合（18/18 判定） | `experiments/query_interface_v1/results/formal/C4-R4-SYNTHESIS-20260920-175458.json` |
| 基座能力总证 | `experiments/foundation_analysis/results/PROVENLATTICE-FOUNDATION-EVIDENCE.json` + `experiments/foundation_analysis/reviews/provenlattice-foundation-evidence-review.md` |
| 复现总入口 | `REPRODUCIBILITY.md` |
| 变更史 | `CHANGELOG.md` |
| GitHub Release | https://github.com/sunSUNQ/provenlattice/releases/tag/provenlattice-sqi-v1.2 |

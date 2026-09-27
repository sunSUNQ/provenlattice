# 月度答辩度量体系 V1（qualification-metrics-v1）

- 日期：2026-09-25
- 状态：设计定稿，待用户补「另一任务」描述（§6.9 / §7）
- 用途：① 答辩的指标口径与数字出处；② 后续评测补齐的工作清单；③ PPT 生成大纲（§6）

---

## 一、指标覆盖对照：问的两翼指标，现有设计包含了吗？

### 1.1 建设侧（代码图谱建设目标）

| 指标 | 判定 | 现有覆盖 | 缺口 |
|---|---|---|---|
| 构建时长 | 🟡 部分 | 单点数字（redis ~24.7s / llama 重建 91.1s）+ ±15% 偏差闸 + 调查链分解（156→25→24.7s） | **吞吐率曲线**（KLOC/s、文件/s vs 仓规模）未系统测；84/325/1358 文件三点口径不一 |
| 准确率（图谱本身） | 🟡 部分 | ① 结构正确性强：逐位重建、16/16 分层零偏差、T1/T2 冻结对账、增量 parity；② 查询级 precision：32 条人工裁定闭环 | **事件级金标 = fidelity_v1：协议已冻结但零标注**——卡 ANNOTATION_PROTOCOL_ISSUE-001（盲评包缺候选定义路径/行号，标注员无法独立判 target 正确性） |
| 存储成本 | 🟢 | 语义层库体积 +3.6%/+2.1%；附录 A 全表画像 | 无 |

### 1.2 检索侧（图谱检索目标）

| 指标 | 判定 | 现有覆盖 | 缺口 |
|---|---|---|---|
| 检索时长 | 🟡 部分 | 分析型八查询成本表（5–125s）；R1 harness 已有字段 `time_to_first_relevant_evidence_ms` | 点查延迟分布（P50/P95）未测；R1 latency 字段每次运行 unavailable（instrumentation 缺口，归因报告原文承认） |
| 检索准确率 | 🟡 部分 | **R1 已跑**：6 真实 brpc 任务 × 3 臂（native/codegraph/knowledge）= 18 cells，`evidence_precision` 三臂全 1.0；**R2 已跑** T05×3 | ① R1 `task_success` 三臂全 0——归因是评测口径过严（`wrong_path` 把合法辅助文件判错），成功率面数字目前不可用；② R2 进阶闸 **HOLD**（Evidence recall 0.667 + 2 个 unsupported 引用）；③ 缺陷候选**召回率基线**（阶段 2 登记项）至今未做 |
| token 消耗 | 🟡 部分 | **端到端已有真实 token 计量**（`retrieval-v1/results/aggregate.json` 每轮带 `input/output/cache/total_tokens`）：54 次运行三臂对照 —— 纯文件臂 178,251 / 图查询臂 212,113（**+19%**）/ 知识层臂 222,173；图臂多耗由**工具轮数**驱动（17.2 vs 15.1 轮），归因已定位到 Query Interface | `DefectEvidenceBundle` **单束 token 预算**没有（无 tokenizer 计数）；`--max-evidence/--max-symbols/--max-edges/--max-sections` 四旋钮从未测过对 token 的曲线 |

**一句话结论**：测量骨架约 80% 已在仓里（retrieval-v1 / retrieval-v2 / fidelity_v1 三个实验目录 + 八查询成本表 + 结构对账体系），但四个缺口让三组关键数字「有字段没数据、有数据不能用」（§四）。

---

## 二、已有评测资产盘点（答辩引用的数字与出处）

### 2.1 结构与过程质量（护城河线）

| 数字 | 含义 | 出处 |
|---|---|---|
| 逐位重建一致、16/16 分层零偏差 | 同输入 → 字节级同输出 | `d:/tmp/stage6/step6_report.md`、gate_legacy/verify_t2 |
| T1/T2 冻结预测全对账、零未归因残差 | 候选数可预测 ⇒ 规则行为完全受控 | `d:/tmp/stage6/predictions*.json` |
| 套件 296/296 | 回归护栏 | `python -m unittest discover -s tests` |
| redis 1.1：557,315 → 28,523 → 10,420（**−98.1%**） | 身份/Access/DFG 三层投资累计缩量 | 5B 五列对比表（`d:/tmp/stage5b/`） |
| check13 **10/13** | 阶段-4 假阳性重定位关闭比例 | `d:/tmp/stage5c/check13.py` 可复跑 |
| 32 条裁定：TP 1 / FP 31 ⇒ **precision 1/32**，failure_reason contract 10 / extractor 6 / other 5 / ownership 5 / identity 4 / missing_read_write 1 | 阶段 6 交付态基线；FP 主导成因移到「AI 侧语义」= 设计中的分工 | `experiments/defect_v1/results/stage6/defect_review.{json,md}` |

### 2.2 成本线

| 数字 | 含义 | 出处 |
|---|---|---|
| redis 索引 ~24.7s（325 文件）/ llama 重建 91.1s（1358 文件） | 全量建图 | 5B/6 闸记录 |
| 八查询：error_handling 4.7s / taint 4.7s / null_flow 4.8s / lock_order 4.9s / resource_lifetime 7.6s / race 7.8s / **double_free 64.8s / use_after_free 124.5s** | 分析查询成本；主导项已定位（find_paths 枚举），修复是待裁定小改动 | `d:/tmp/stage6/cost_eight*.json` |
| 表达式索引 18.3ms → 0.014ms（1300×） | 阶段 0.4 优化 | 附录 A |
| 控制边 162,268（redis）/ 422,925（llama）；语义事件 171,553 / 524,887 | 图规模 | 库直查 |

### 2.3 端到端检索评测（retrieval-v1 / retrieval-v2，brpc V0.2 库时代）

| 数字 | 含义 | 出处 |
|---|---|---|
| R1：18 cells，qualification **PASS**（15 闸全过） | 端到端三臂对照跑通 | `experiments/retrieval-v1/results/qualification.json` |
| R1：`evidence_precision` 三臂全 **1.0**；task_success 三臂 0（口径过严，非系统失败）；字符读取：图臂均值 35,668 vs 纯文件臂 41,502（**−14%**，逐任务方差大 —— T01 三轮 −37,234 / −15,628 / **+52,236**）；**token：图臂 212,113 vs 178,251（+19%）**，归因 = Query Interface（轮数 17.2 vs 15.1） | 引用证据全对；**效率尚未成立**（token 为负、字符不稳，两者成因均已定位） | 同上 + `pairwise-deltas.json` + `failure-attribution.md` + `aggregate.json` |
| R2：T05×3，interface PASS 但进阶闸 **HOLD**（Evidence recall 0.667，2 个 unsupported 引用） | EvidenceBundle 协议版首个 cell | `experiments/retrieval-v2/results/t05-qualification.json` |
| fidelity_v1：协议冻结（双盲 κ / Resolved Precision / Selective Risk），Batch 01 **PAUSED**（ISSUE-001） | 事件级金标零标注 | `experiments/fidelity_v1/results/calibration-execution-log.md` |

---

## 三、完整指标体系设计（V1.0-Qualification 总表）

### 3.1 建设翼（Build）

| # | 指标 | 定义 | 测量方法 | 预算/目标建议 |
|---|---|---|---|---|
| A1 | 全量构建时长 | 冷库全量 index 墙钟 | 每仓一次，出 `build_profile.json`（分阶段：parse/identity/shard/semantic/cfg/dfg） | 报告吞吐率 **KLOC/s**；阶段 7 前后各测一轮 |
| A2 | 增量构建时长 | update：空转 / 单文件 / 10 文件批量 | 三档冻结场景重跑 | 空转 < 1s（小仓已有 267ms） |
| A3 | 结构正确性 | 同输入 → 逐位同输出 | 已有：重建 digest、分层对账、T1/T2 | 保持，答辩主打 |
| A4 | 事件级保真度 | resolver/事件抽取对不对（金标） | **重启 fidelity_v1**：盲评包补候选定义路径+行号+限定名（V2 库 `semantic_events` 自带 `source` span 与 `subject_decl`，修包成本低）；双盲 κ、Resolved Precision / Selective Risk 按冻结协议 | 首批 3 仓 × 30 例 |
| A5 | 候选精度/成因 | 缺陷候选 precision + failure_reason | 已有 32 条先例；每新增查询 ≥20 条裁定 | 维持 |
| A6 | 存储成本 | 库体积 / KLOC、表分布 | 附录 A 画像定期重跑 | 阶段 7 后加冷热比 |

### 3.2 检索翼（Retrieve）

| # | 指标 | 定义 | 测量方法 | 预算/目标建议 |
|---|---|---|---|---|
| B1 | 点查延迟（Agent 交互级） | symbol/definition/callers/callees/subgraph 的 P50/P95 | 同库 ×N 次重复；补 R1 的 instrumentation 缺口 | **P95 < 200ms**（在线可用性线） |
| B2 | 分析查询时长（批量审计级） | 八查询成本表 | 已有；find_paths 加速裁定后重测 | 与 A1 同报告 |
| B3 | 候选召回率 | 已知缺陷进没进候选 | 金标仓（Juliet C/C++ 或自建夹具扩展）→ 已知缺陷锚点命中率 | 阶段 2 登记项的兑现，**最高优先** |
| B4 | Evidence 精度/召回（端到端） | Agent 引用的证据对不对、该找的找没找到 | R1/R2 harness 已有 precision 1.0 / recall 0.667；先修 R1 评测口径（`wrong_path` 放宽到「辅助文件合法」），再解 R2 的 2 个 unsupported 引用 | R2 进阶闸解冻是下一个里程碑 |
| B5 | token 消耗 | ① 单 bundle token 数；② 旋钮曲线（--max-* × token × B4 质量）；③ 端到端每任务 tool-output token | 32 条现成 bundle 直接 tokenizer 计量（确定性渲染 ⇒ 计量确定性）；R1 字符代理一次校准换算 | 单 DefectEvidenceBundle ≤ 4k token（一个 tool result 装得下） |

---

## 四、缺口与补齐路径（按性价比排序）

| 优先 | 缺口 | 动作 | 成本 |
|---|---|---|---|
| 1 | token 计量（B5） | 端到端已兑现（R1 `aggregate.json` 每轮 token，见 §1.2）；**剩余缺口 = 单 bundle token 预算**：32 条 bundle 现成样本 + 一次 tokenizer 校准 | ~半天，零风险 |
| 2 | fidelity 重启（A4） | 修盲评包（把 V2 事件已有的 source span/subject_decl 塞进候选上下文），消 ISSUE-001，标首批 30 例（双盲：用户 + AI 各一路） | 修包 1 天 + 标注半天 |
| 3 | R1 口径修复（B4） | `wrong_path` 规则放宽 + latency instrumentation 补上；18 cells 可 replay 重评，不必重跑 Agent | 1–2 天 |
| 4 | 召回率金标（B3） | 选定金标仓 + 已知缺陷清单 → 命中率脚本 | 2–3 天，选型可先小规模 |

---

## 五、答辩口径边界（话术红线）

- **能讲**：结构可复现（零未归因残差）、候选缩量 −98.1%、evidence precision 1.0（R1 三臂、54 次运行）、八查询成本表、296/296、**token 计量已建立**（三臂实测口径）。
- **要标注「进行中」**：task_success（口径修复中）、**token 效率为负（图臂 +19%，成因已定位到 Query Interface，未修）**、字符读取优势不稳（−14% 均值、逐任务方差大）、Evidence recall 0.667（R2 HOLD，已诊断未修）、事件级保真度（协议冻结、标注未开始）。
- **不许再说**：「证据效率正结果 / codegraph 臂少读 37K 字符」—— 该数字是 T01 第一轮的**单点值**，三轮为 −37,234 / −15,628 / +52,236；臂级 token 是负的。正确说法见本文件 §6 P11 与《ProvenLattice_答辩PPT内容大纲.md》第 23 页。
- **不能讲**：任何形式的选择性召回率主张——缺陷候选召回率未测；两个「召回率」（候选召回率 vs Evidence recall）不许混用。
- precision 口径：0/20（阶段 4）与 1/32（阶段 6）是不同缺陷族不同库的抽样，不能说成「precision 提升到 3%」；正确曲线 = 候选空间 −98.1% + FP 成因从可修结构问题（identity/ownership）移到设计中的 AI 侧分工（contract）。
- 答辩材料不写 CWE 编号（按项目常设约束未核对）。

---

## 六、PPT 大纲（逐页，供 AI 生成执行）

> 每页给出：标题 / 内容要点 / 素材来源 / 制作指示。全程约 13 页，讲 12–15 分钟。

**P1 封面**
- 标题：代码知识图谱驱动的缺陷检测——月度进展汇报；副标题：确定性、保留证据、字节级可复现
- 姓名、日期（2026-09）、项目名 ProvenLattice
- 素材：无。制作：干净封面，深色底。

**P2 本月工作总览**
- 三条线各一行：① 主线 ProvenLattice 阶段 5B→6（Sparse DFG + 五个新 Typed Query + 人工裁定闭环）；② 评测体系（retrieval-v1/v2 端到端 + fidelity_v1 金标协议 + 本度量框架）；③ 另一任务（待补，见 §7）
- 底部一行数字条：296/296 套件 · −98.1% 候选缩量 · 18 cells 端到端 · 32 条裁定闭环
- 素材：§2 数字。制作：三栏卡片 + 底部数字条。

**P3 项目定位与目标**
- 要点：给 AI 辅助缺陷检测造输入——确定性、保留证据的代码 KG；百万行规模目标
- 为什么不做完整 CPG / 不上 Neo4j：拿多跳性能换字节级可复现是亏的（双盲实验需要冻存可 diff 的金标）
- 素材：`计划文档/readme` 的路线 A/B/C 推演表 + 存储选型补列表。制作：左文右表，选型表压缩为三行结论。

**P4 流水线架构**
- 七层链路图：Source → 语义事件（READ/WRITE/ALLOC/FREE/LOCK…）→ 稀疏 CFG → Access/Contract 层 → 稀疏 DFG（四类流边）→ 八个 Typed Query → DefectEvidenceBundle → AI
- 关键设计点两条：事件身份方法级稳定（哈希含 owner+type+ordinal，不含行号）；三态证据（绝不伪造边）
- 素材：`计划文档/readme` 末尾修正链路图改编。制作：横向流程图，AI 用这个结构直接画。

**P5 技术实现 1：Sparse DFG（阶段 5B）**
- 一条链规则 + 直接 def→use 边 + via 中间链可恢复；`build_adjacency` 按关系过滤的闸
- 核心表：五列对比（C1 baseline 557,315 → C2 identity 28,523 → C3 read/write 264,280 → C4 sparsedfg 10,420 → C5 contract 14,439；llama 侧同表）
- 制作：五列表格 + 一句结论「−98.1% 来自三层结构性投资，不是调参」。

**P6 技术实现 2：Typed Query 第二批（阶段 6）**
- 五新查询进齐八键：null_flow(3.1) / use_after_free(4.3) / double_free(4.2) / taint_path / error_handling(9.1)
- 两个交付级缺陷的发现与修复：find_paths 指数悬崖（>600s/13.7GB → 1.6s，BFS 前驱树读路线）；窗口上限 64 透传造 6,189 伪候选（钳 4096）
- 素材：`d:/tmp/stage6/step6_report.md` §一/§四。制作：左查询清单右两个缺陷的「症状→修法→钉子测试」卡片。

**P7 技术实现 3：可证伪研究纪律**
- 每阶段：探针先冻结预测（T1/T2）→ 实现 → 逐位对账 → 偏差逐条归因；阶段 6 收官**零未归因残差**
- T1 偏差表一例：null_flow redis −1 / llama +62，归因 = 守卫匹配改身份；use_after_free −194 = 新淘汰规则
- 素材：`计划文档/AGENTS.md` 阶段 6 执行记录 T1 偏差表。制作：时间轴 + 一张偏差归因小表。这页讲「研究方法」而不只是结果。

**P8 技术实现 4：人工裁定闭环（验收）**
- 32 cases / 16 层分，AI 逐条提议 + 用户逐条确认；4 条读源码实锤
- precision 1/32；failure_reason 柱状图：contract 10 / extractor 6 / other 5 / ownership 5 / identity 4 / missing_read_write 1
- 关键解读：FP 主导成因从 identity/ownership（阶段 4）移到 contract（AI 侧语义）= 设计中的分工，不是失控
- 素材：`experiments/defect_v1/results/stage6/defect_review.md` + `--summarize` 输出。制作：柱状图（AI 执行：跑 build_review.py --summarize 取数据画图）+ 一条真阳性案例（lfu-simulation.c malloc→解引用）做截图。

**P9 技术实现 5：〈另一任务标题待补〉**
- 占位四段模板（用户给一两句话描述后由 AI 补全）：① 背景与目标；② 做了什么（一句话工作概述）；③ 技术要点/方案（2–3 条）；④ 结果或状态（1 条数字或里程碑）
- 制作：等用户补充后按 P5–P8 同款风格成页。

**P10 评测体系：两翼指标总览**
- 建设翼 A1–A6 / 检索翼 B1–B5 两张小表（§三），右下角标缺口色（🟢🟡🔴）
- 一句话：骨架 80% 已在仓里，四个缺口有补齐路径（下页）
- 素材：本文件 §三。制作：两列表，缺口单元格标红黄绿。

**P11 检索评测：已有端到端结果（诚实页）**
- R1：18 cells PASS、evidence_precision 1.0（54 次运行零错证据）；task_success 0 = 口径过严（wrong_path 误判辅助文件），修复中；字符读取 −14%（不稳）；**token +19%（负结果，已定位到 Query Interface）**
- R2：T05×3，Evidence recall 0.667 + 2 unsupported → 进阶闸 HOLD，已诊断
- 制作：两行结果卡 + 明确的「口径修复中」标注。这页的诚实性是加分项，不藏负结果。

**P12 缺口与下月计划**
- 四补齐路径表（§四：token 计量 → fidelity 重启 → R1 口径 → 召回率金标）
- 主线下一步：阶段 7 冷热拆分 + 分析副本（百万行铺路）；find_paths 加速为待裁定小改动
- 制作：左缺口表右路线图箭头。

**P13 总结**
- 三个数字：296/296 回归全绿 · −98.1% 候选缩量 · 0 未归因偏差
- 一句话定位：确定性、保留证据、字节级可复现的缺陷检测 KG，度量体系已成型
- 下月：阶段 7 + 评测四补齐
- 制作：大字三数字 + 两行计划。

---

## 七、待补清单

- [ ] §6.P9 / 本节：**另一任务**的名称与一两句话描述（用户供给后，AI 补全 P9 与本文件相应小节）
- [ ] §四 优先级 1（token 计量表）：待用户裁定后执行
- [ ] P8 柱状图数据：`build_review.py --summarize` 输出已有，画图时直接取

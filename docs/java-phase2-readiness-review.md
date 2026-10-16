# PL-JAVA-PHASE2-READINESS-REVIEW — Java Phase 1 独立复审与 Phase 2 就绪裁定

**状态：`CONDITIONAL_READY`**（详见 §7 裁定） · **日期**：2026-10-15 · **复审 HEAD**：`aa86487`（main）
**性质**：只读复审与规划；本轮零源码/测试修改；原始证据未覆盖。

---

## 1. Phase 1 独立复审结果

### 1.1 Preflight 核验（Step 0）

| 项 | 复核方式 | 结果 |
|---|---|---|
| HEAD 与提交链 | `git log`（aa86487 + 9 commit，42c6d89 基线） | 一致 |
| 工作区 | `git status`（src/tests/evidence/java 文档零未提交） | 干净 |
| 测试基线 | 独立复跑全量 unittest | **449 OK**（44.5s） |
| T9-B 原始输出留存 | 读取 `%TEMP%\...\t9b\{jdt,jp}-raw.txt` | 留存；JDT 歧义拒绝（resolved=null）与 JavaParser 静默绑定（com.x.util.Helper）逐行复核 |
| P7 验证 DB 留存 | 直接查询 repos 下 codegraph.db | 留存 |
| 金样 | P8 已复验（py/cpp IDENTICAL，除设计内版本戳） | 一致 |

**结论：报告结论与代码、原始数据一致；运行环境可信。无 HOLD 项。**

### 1.2 复审中发现的数据勘误（如实记录）

P7 aggregate 写"53/60 正确、7/60 错误（11.7%）"，但 `p7-audit-verdict.json` 的
gson wrong_items 含一行 "target.add variant" 冗余占位。**逐样本重核：gson 4 错
（members.get / map.put / "1".repeat / target.add）+ hikaricp 4 错 = 8/60 = 13.3%
（52/60 正确）。** 勘误不改变任何结论方向（错误全部集中于启发式置信层）。
本勘误即为原始证据之上的独立修正，旧报告原文不改动。

### 1.3 稳定性与质量面

- 测试 442→449 增量全部可解释（+4 P1 回归 +7 P6 对抗）。
- 断点证据链（9 条 checkpoint + JSON 校验脚本）完整可重放。
- T9-A/T9-B/prototype 的 runner 与原始 JSON 均已入库，第三方工件（JDK/jar/仓库）在仓库外。

---

## 2. 当前技术风险及证据（Step 1）

### 2.1 八个真实仓库错误绑定逐条复核

| # | 仓库 | 调用点 | L1 绑定 | 真实目标 | 阶梯/置信 |
|---|---|---|---|---|---|
| 1 | hikaricp | `MINUTES.toMillis` | ClockSource.toMillis | java.util.concurrent.TimeUnit.toMillis（JDK 静态导入枚举常量） | unique 0.75 |
| 2 | hikaricp | `current.getPassword` | HikariConfig.getPassword（同文件） | util.Credentials.getPassword（lambda 参数类型） | same-file 0.98 |
| 3 | hikaricp | `sharedList.stream` | TestElf.StringAppender.stream | java.util.List.stream（CopyOnWriteArrayList） | unique 0.75 |
| 4 | hikaricp | `field.get` | FastList.get | java.lang.reflect.Field.get | unique 0.75 |
| 5 | gson | `members.get` | JsonObject.get（同文件） | internal.LinkedTreeMap.get | same-file 0.98 |
| 6 | gson | `map.put` | MapWithoutNoArgsConstructor.put（同文件嵌套类） | java.util.Map.put | same-file 0.98 |
| 7 | gson | `"1".repeat` | JsonReaderTest.repeat | java.lang.String.repeat | unique 0.75 |
| 8 | gson | `target.add` | CollectionWithoutNoArgsConstructor.add（同文件） | java.util.List.add | same-file 0.98 |

**根因单一**：L1 语法阶梯不追踪 receiver 声明类型；实例调用的短名恰与项目内方法
唯一同名（0.75）或同文件同名（0.98）即绑定。**8 错 = 0.75×4 + 0.98×4；精确层
（import 1.0 / qualified 0.99）0 错。**

### 2.2 影响面量化（本轮直接测量，readiness-ladder-measurement.json）

| 仓库 | resolved CALLS | 精确层 | 启发层（<0.99） | 启发占比 |
|---|---|---|---|---|
| hikaricp | 1990 | 417 (21.0%) | 1573（1065@0.75 + 508@0.98） | **79.0%** |
| gson | 5077 | 1270 (25.0%) | 3807（2180@0.98 + 1627@0.75） | **75.0%** |

按样本错误率外推：启发层错误边量级约 hikaricp ~130-200、gson ~300-500（外推仅供
规模感知，验收以固化回归集为准）。REFERENCES 侧未审计（更大存量，同机制）。

### 2.3 receiver 未知时是否应保守返回 ambiguous/unresolved —— 判定

**应保守，且状态应为 `ambiguous`（候选保留），不是 `unresolved`（无候选）。**
理由：三态契约中 ambiguous = "存在候选但需更多信息选择"——receiver 类型正是缺失的
信息；unresolved 会丢失候选证据。跨语言兼容：以 metadata 门控（Java extractor 标注
`receiver_shape`），Python/C/C++ 行为零变化——与 P1 守卫同一先例模式。**已知代价**：
CALLS resolved 将显著缩水（启发层 75-79% 中 identifier-receiver 子集），必须与 JDT
精确层（P2-D）同期交付以补召回——单侧实施会大幅劣化开箱体验，故绑定交付是硬约束。

### 2.4 其余风险

| 风险 | 证据 | 等级 |
|---|---|---|
| JDT 大库内存未测（jgit 规模） | P9 报告 §12 明示未测 | 高（P2-B 前置） |
| JDT 依赖树 19 jars + 去签名 workaround + compliance 配置坑 | T9-B 实测 | 中（打包方案入 P2-D） |
| SCIP INFRA_BLOCKED 不等于不可用 | 官方 Windows launcher drop（v0.13.1） | 记录性（禁止推断成 PASS/FAIL） |
| 增量路径大库无收益 | T9-A 实测（33.3s vs cold 24.9s） | 中（口径：大库官方口径=全量重建） |
| warm 慢于 cold（大库 replace_snapshot 代价） | T9-A 实测 | 低（设计输入） |

---

## 3. Phase 2 技术设计建议（Step 2 复审结论）

1. **能力边界**：L1 永久为事实源；JDT 产出独立的"精确层"引用（provenance
   `semantic:jdt-v<n>` + backend version + source_hash 绑定），只追加不覆盖 L1 行；
   冲突时两者并存、查询面按 provenance 分层呈现。
2. **classpath 发现**：P2-C 首期仅"无构建工具源码树 + 手工 classpath"（T9-B 已验证
   形态）；Maven/Gradle 依赖解析器为独立子任务（解析 pom.xml/build.gradle → 制品解析），
   不阻塞 P2-A/P2-B。
3. **错误与降级**：`recovered=true` → 丢弃（T9-B 实证幽灵 FQN）；JDT 歧义（resolved=null
   + 诊断消息）→ 显式 AMBIGUOUS 行；解析异常/超时 → fail-closed，L1 结果原样。
4. **capability 集成**：新 feature id（建议 `semantic:java`）走 `ANALYSIS_SCHEMA`
   复合主键 (id, feature)，与 `dependency_staleness` 契约对齐；`CAPABILITY_CONTRACT`
   新行 languages=("java",)，L1 行不动。注册即受 I0 冻结测试约束（test_capabilities_i0
   需同步扩展并说明）。
5. **默认 index 无 JVM 保障**：JDT 仅在显式 analyze/独立命令路径运行；clean-env 安装
   继续不含 JDT（T9-B 的 jar 组为 optional extra）；CI 增加"无 JVM 环境全量绿"断言。
6. **P2-A 与 P2-D 绑定交付**（§2.3 结论）：安全收紧（demote）与召回补回（JDT）不可拆分
   单独发布。

---

## 4. 性能与正确性验收设计（Step 3）

### 4.1 性能复测矩阵（基线 = T9-A 已冻结数据）

| 维度 | 基线值（中位数） | 复测口径 |
|---|---|---|
| L1 cold | 0.65s / 2.83s / 24.9s（hikaricp/gson/jgit） | 同协议（warmup1+cold3+warm3+incr3+delete1），全量原始值入库 |
| L1 warm | 0.76s / 2.82s / 31.7s | 同上 |
| L1 增量 | 0.80s / 2.90s / 33.3s | 同上 |
| L1 峰值 RSS | 60 / 132 / 1026 MB | 同上 |
| **+JDT 开销** | 无基线（本轮未测） | P2-B 新增：同仓库 JDT 批处理 wall/RSS（独立进程），报告"L1 基线 + JDT 增量"两条线，禁止合并均值 |
| DB 尺寸 | 24/77/817 MB | 同上 |

验收口径：报告测量值 + 相对变化；绝对预算（如"JDT 增量 ≤ L1 cold × N"）需人工批准，
不由实施方自设。

### 4.2 正确性回归集与口径

| 集 | 内容 | 判据 |
|---|---|---|
| 既有对抗集 | java01–31（31 项） | 全绿不回退 |
| T9-B gold | 21 项（含双通歧义、recovered、语法恢复） | JDT 层 21/21（含正确拒绝），L1 层不回退 |
| **真实仓库错误固化** | §2.1 八样本最小化抽取为 fixture（每条 ≤2 文件） | 逐条：L1 demote 后为 ambiguous、JDT 层 CORRECT |
| **独立新鲜样本** | hikaricp/gson 非审计区固定种子新抽 30+30，人工标注 | 防过拟合；抽样新鲜、标注独立于实施 |
| 口径 | wrong-binding rate（全置信层）= 0（固化集）；unresolved+ambiguous 比例变化界报告；JDT 精确层 precision ≥ 人工标注一致率 | 全部原始数据入库 |

---

## 5. Phase 2 分阶段实施计划（Step 4）

### P2-A：L1 错误绑定安全处理（demote）
- **前置**：本评审获人工批准（涉及阶梯契约语义）。
- **范围**：parsing/java.py（CALLS 引用标注 `receiver_shape`）；resolver.py（
  `receiver_shape="identifier"` 的 CALLS 在 unique/same-file 阶梯降 ambiguous，候选保留；
  CALL_KIND_VERSION 2→3）；python/cpp 不动。
- **测试**：8 个固化错误样本 + java01–31 全量 + 金样（py/cpp 除版本戳外 IDENTICAL）+
  影响面测量（demote 前后 resolved 分布对比入库）。
- **验收**：固化样本 0 resolved 错绑；ambiguous 候选含原目标；旧语言零变化。
- **回退**：单 commit 可 revert；CALL_KIND_VERSION 机制自动恢复。
- **STOP**：金样出现非版本戳差异；或 demote 影响面测量显示 CALLS resolved 缩水 >85%
  且 P2-D 未就绪（需人工重议顺序）。

### P2-B：JDT 大仓库性能与内存验证
- **前置**：P1_FINAL_REVIEW_PASS（已有）；JDK 分发方案确定。
- **范围**：仅基准工具（复用 T9-A runner 形态），对 gson/jgit 跑 JDT 批处理
  wall/RSS；**不改产品代码**。
- **验收**：原始数据 + 与 L1 基线的双线报告；jgit 规模 RSS/时长在人工批准预算内。
- **回退/STOP**：RSS/时长超预算 → JDT 限单模块/分批模式或 STOP 重议。

### P2-C：Classpath 发现与解析（首期：手工 classpath）
- **前置**：P2-B 通过。
- **范围**：独立模块（源码树 + 手工 classpath 输入契约 + 校验与缺依赖报告）；
  Maven/Gradle 解析器另立后续任务。
- **验收**：T9-B fixture 无 classpath 全链路；缺依赖降级为显式报告。

### P2-D：JDT Capability 集成
- **前置**：P2-A + P2-B + P2-C 完成。
- **范围**：JDT driver（production 化，含 recovered 过滤/歧义标注/超时）+ 可选
  extra 依赖声明 + CAPABILITY_CONTRACT/ANALYZER_VERSIONS/analysis_query 接线 +
  I0 冻结测试扩展。
- **验收**：默认 index 零 JVM 依赖（clean-env 断言）；analyze 显式路径可用；
  fail-closed 全覆盖；provenance/freshness 全链路。
- **回退**：capability 行移除即回到 L1-only。
- **STOP**：任何冻结契约（BASE_TABLES/能力元组）无法在不破坏旧语言断言下扩展。

### P2-E：真实仓库回归与性能验收
- **前置**：P2-A–D 全部完成。
- **范围**：hikaricp/gson/jgit 端到端（CLI 不变）+ §4.2 四回归集 + §4.1 复测矩阵。
- **验收**：wrong-binding rate=0（固化集）；新鲜样本人工标注一致率达标（阈值人工批准）；
  性能双线报告交付。

### 推荐启动顺序
**P2-A → P2-B（可与 P2-A 并行，只读基准）→ P2-C → P2-D → P2-E**。

---

## 6. 可量化验收条件汇总

1. 固化回归集（8 真实错误样本 + 31 对抗 + 21 gold）：wrong-binding = 0，全绿。
2. 新鲜独立样本（30+30 人工标注）：高置信层错误 0；JDT 层与人工标注一致率 = 报告值（阈值人工批准）。
3. 旧语言：金样四表逐行 IDENTICAL（除 CALL_KIND_VERSION 版本戳）；全量 unittest 无非预期变化。
4. 性能：L1 三仓库基线不劣化（±测量噪声带内，带宽人工批准）；JDT 增量开销独立成线报告。
5. 默认路径：clean-env（无 JVM）全量测试绿；默认 index 产物零 JDT 依赖。

---

## 7. 最终裁定

**`CONDITIONAL_READY`**

**READY 部分**：Phase 1 证据链完整、可独立复核、无 HOLD；T9-B/T9-A/原型证据充分；
Phase 2 架构方向（JDT 可选 Analyzer + L1 安全收紧）有实测支撑。

**CONDITION 部分（解除后即 READY）**：
1. **P2-A 方案人工批准**（demote 属阶梯契约语义变更，影响 CALLS resolved 75-79% 的
   存量形态——需明确接受"过渡期召回下降、由 JDT 补回"的顺序约束）；
2. **P7 aggregate 勘误确认**（7/60 → 8/60，13.3%；本报告 §1.2）；
3. **P2-B 内存预算**需在 jgit 实测后人工批准（当前无数据，禁止预设）。

**BLOCKER**：无。（JDT 大库内存未测为计划内前置任务，不是阻塞项。）

**Phase 2 推荐启动顺序**：P2-A → P2-B（并行只读）→ P2-C → P2-D → P2-E。

完成后 STOP，等待人工评审。

# Java RQ1 Formal — 采样与评分方案冻结文档 V1.2

Issue Pilot #4 · 状态：**方案冻结（FROZEN FOR DESIGN）** · 版本：`v1.2-amendment-r3`
· Owner gate：PL-JAVA-ISSUE-DECISION-20261020（APPROVE_DESIGN_ONLY）+ 修订要求
PL-JAVA-OWNER-DECISION-R2（六项方法学修订）+ PL-SOLO-V2-OWNER-DECISION-20261020-R3
§2（DESIGN_APPROVED_CONDITIONAL，两项合并前定向修订）。
**本文档只冻结方案；标注执行被 §6 执行门禁止，直到全部前置条件满足。**

> v1.0 → v1.1 差异摘要：① 前 n 例选择改为冻结种子的分层简单随机抽样；
> ② 新增 JDT 关联键碰撞审计，碰撞行排除出抽样框；③ 盲评视图字段白名单化；
> ④ 新增加权估计量、bootstrap 置信区间与 Stable 判定规则；⑤ gate-ack 绑定
> 授权记录+方案版本+方案哈希；⑥ Windows-only 豁免语义限定。
>
> v1.1 → v1.2 差异摘要（R3 §2 修订①②）：⑦ 资格判定的证据充分性——
> 估计量/证据无效时输出 INCONCLUSIVE 披露档（非资格中间档），二值判定仅在
> 估计量有效时可达；⑧ sample 模式增加 decision_ref 的 GitHub API 外部校验
> （真实 owner 授权记录 + 记录正文含 ack 令牌），ack 计算保留但不再是唯一依据。

## 1. 研究问题与资格目标

- **RQ1（图保真度）**：Java 调用图决议（CALLS RawReference decisions）相对于
  独立人类金标的正确率是多少？——与 C/C++ RQ1 同族（Resolved Precision /
  Selective Risk / False Resolution on Absent / Abstention 质量）。
- **资格规则（建议，待 owner 在决策记录评审时批准）**：Java Stable 资格
  要求 RQ1 formal 达到 QUALIFIED（门槛沿用 C/C++：加权 Resolved Precision
  ≥ 0.90 且 False Resolution on Absent ≤ 0.10，或 owner 明示修订）。
  RQ1 未 QUALIFIED 前，任何输出不得宣称 Java Stable。

## 2. 协议宇宙与分层（冻结）

- 关系：**CALLS**（Java L1 `raw_references.reference_type='CALLS'`，
  含 L1 与 JDT 合并后的全部决议行）。REFERENCES/IMPORTS 家族不在 V1 宇宙
  （Java 提取器语义与 C/C++ 不同，另行立项）。
- 仓库与提交（沿用 Stage-0 冻结锚点）：HikariCP `a4d93f4`、gson `e2292f9`、
  jgit `6e68739`（跨仓库分层抽样）。
- 六个决策分层（`experiments/java_rq1_formal/build_frame.py` 定义）：
  S1 L1_RESOLVED_L1_ONLY / S2 L1_RESOLVED_JDT_AGREE /
  S3 L1_RESOLVED_JDT_CONFLICT / S4 NONRESOLVED_RECOVERED /
  S5 NONRESOLVED_JDT_AMBIG / S6 NONRESOLVED_NOT_SEEN。
  S3/S4 是"保守保留不猜测"门的直接审计面；S2/S4 是 JDT 精度主战场。

## 3. 种群统计（实测，Windows / T9-B jar 集）

由 `build_frame.py stats` 实测（results/frame-stats-*.json，含 frame_sha256）：

| 分层 | HikariCP | gson | jgit |
|---|---:|---:|---:|
| S1 L1_RESOLVED_L1_ONLY | 1,016 | 3,841 | 27,162 |
| S2 L1_RESOLVED_JDT_AGREE | 19 | 316 | 7,335 |
| S3 L1_RESOLVED_JDT_CONFLICT | 10 | 5 | 136 |
| S4 NONRESOLVED_RECOVERED | 800 | 2,751 | 46,939 |
| S5 NONRESOLVED_JDT_AMBIG | 440 | 306 | 1,006 |
| S6 NONRESOLVED_NOT_SEEN | 3,613 | 15,534 | 95,784 |
| 宇宙合计 | 5,898 | 22,753 | 178,362 |

> 勘误（v1.1）：v1.0 文档曾将 hikaricp/jgit 合计误写为 5,899/181,862（分层
> 数值均正确，仅加总笔误）；以 results/frame-stats-*.json 原始值为准。

约束声明：§3 表格是 v1.0 口径（不含关联键排除）的测量值，保留作参照。
v1.1 新增 `association_ambiguous` 排除（§4），frame-freeze 执行时必须在
**相同冻结提交**上重测有效总体（排除后计数）；若有效总体与 v1.0 参照表
偏差 > 5%，冻结停止并回报 owner（依赖或提取器漂移信号）。

## 4. 样本量与分配规则（冻结）

- 总量 **174**（owner 冻结）：每仓 58，按分层比例分配，
  规则 = 比例分配 + 每分层下限 3 / 上限 24 + 最大余数法（`allocate()`，
  确定性，无 RNG）。基于 §3 种群的分配结果：

| 分层 | HikariCP | gson | jgit |
|---|---:|---:|---:|
| S1 | 11 | 11 | 9 |
| S2 | 4 | 5 | 4 |
| S3 | 4 | 5 | 3 |
| S4 | 9 | 8 | 15 |
| S5 | 6 | 5 | 3 |
| S6 | 24 | 24 | 24 |
| 合计 | 58 | 58 | 58 |

- 选择规则（v1.1，R2 修订①）：**分层简单随机抽样（SRS without replacement）**，
  预冻结公开种子 `SAMPLE_SEED = "PL-JAVA-RQ1-FORMAL-V1.1-FIXED-SEED-20261020"`，
  每分层独立随机流 `random.Random(f"{SAMPLE_SEED}|{PLAN_VERSION}|{repo}|{stratum}|{frame_sha256}")`，
  在确定性排序（file, line, raw_name, resolution_strategy）的分层总体上
  `rng.sample` 抽取 n 例。可复现性绑定 (种子, 方案版本, 仓库, 分层, frame_id)。
- 关联键审计与排除（v1.1，R2 修订②）：JDT 站点键为 (file, line, root)。
  同键 >1 条 JDT binding 时，该行级系统状态关联不唯一 → 相关 L1 行标记
  `association_ambiguous` 并**排除出抽样框**（各分层排除数在 frame 工件中
  如实报告，不回填）。frame 工件同时报告：binding 键总数、碰撞键数、
  排除行数。
- 短缺如实报告，不跨分层/跨仓回填（沿用 C/C++ 纪律）。

## 5. 标注与裁定协议（冻结）

- **校准批**：25 例（跨仓跨分层），双盲独立标注，raw agreement κ ≥ 0.85
  且 normalized κ ≥ 0.92 才放行正式批（C/C++ calibration-gate-01 同门槛）。
- **盲评**：两标注者独立查看源码上下文；**盲评视图字段白名单（v1.1，R2 修订③）**：
  仅 `{case_id, repo, file, line}`——status、resolution_strategy、confidence、
  target、jdt_state、raw_name、stratum 及任何系统决议字段只存在于密封的
  canonical 包，盲评视图生成时程序化校验泄露（检出即拒绝执行）。两人文件
  互不可见。标注者自行打开源码定位该行。
- **verdict 词表**（resolved 类）：CORRECT_RESOLUTION / WRONG_TARGET /
  RELATION_NOT_PRESENT / BUILD_CONTEXT_DEPENDENT / INSUFFICIENT_EVIDENCE；
  （nonresolved 类）：NO_VALID_TARGET / ONE_VALID_TARGET /
  MULTIPLE_VALID_TARGETS / BUILD_CONTEXT_DEPENDENT / INSUFFICIENT_EVIDENCE。
- **混淆标签**：same_name、overload（Java 高发）、generics_erasure、
  interface_vs_impl、dynamic_dispatch、reflection、lambda_method_ref、
  static_import、cross_module_homonym、conditional_compilation。
- **裁定**：分歧进入冻结裁定协议（第三方裁定者，记录依据）；裁定率
  预期 ≤ 15%，超限停止并回审协议。Gold Set 仅在分歧复核后冻结密封。
- **统计判定（v1.1，R2 修订④）**：
  - 估计量：分层加权比例 `metric = Σ_h W_h · p_h`，
    `W_h = N_h / N`（N_h 为 freeze 时该分层有效总体数，即排除
    association_ambiguous 后的计数）；未加权样本值同报。
  - 区间：分层 bootstrap（B=10000，预冻结种子
    `BOOTSTRAP_SEED = "PL-JAVA-RQ1-FORMAL-V1.1-BOOTSTRAP-SEED-20261020"`，
    分层内有放回重抽，percentile 95% CI）。
  - **Stable 资格判定规则**（对应 §1 资格规则）：QUALIFIED 当且仅当
    加权 Resolved Precision ≥ 0.90 且其 bootstrap 95% CI 下界 ≥ 0.85，
    且加权 False-Resolution-on-Absent ≤ 0.10 且其 CI 上界 ≤ 0.15，
    且校准门通过。否则 NOT_QUALIFIED（无论结论如何，全部加权/未加权
    数字与 CI 原样报告）。
  - **INCONCLUSIVE 披露档（v1.2，R3 修订①）**：当且仅当加权估计量或
    其 bootstrap CI **无法有效计算**时，结果输出 INCONCLUSIVE 并列出
    原因，不得落入二值判定。触发条件（估计量有效性门，实现于
    `decision_rule.py`）：G1 总样本量为 0；G2 任一 N_h>0 的分层
    n_h=0（覆盖空洞：W_h=N_h/N 给该层分配权重但无数据代表）；
    G3 任一指标分母为空（指标未定义）；G4 标注不完整。INCONCLUSIVE
    **不是资格中间档**——它只表示"证据不足/估计量无效"的诚实披露；
    宽而有效的 CI 未达标仍是合法的 NOT_QUALIFIED。
  - 结果类映射沿用 GRAPH_FIDELITY_SCORING_V1（WRONG_TARGET_RESOLUTION、
    FALSE_RESOLUTION_ON_ABSENT、JUSTIFIED_ABSTENTION 等，INDETERMINATE
    排除出全部分母）。
- **评分**：沿用 GRAPH_FIDELITY_SCORING_V1 语义（4 视图确定性评分、
  加权总体 + 未加权样本双报告、宏分组保留）；系统预测
  （sample 包中的 L1/JDT 状态列）仅在 Gold 密封后开封。

## 6. 执行门（全部满足才允许 `build_frame.py sample` 与任何标注）

1. 本方案（v1.2）与决策记录经 owner 评审合并（PR #16）。
2. **Issue #3 Linux JDT 兼容性补测 VERIFIED**，或 owner 明示豁免。
   **豁免语义（v1.1，R2 修订⑥）**：Windows-only 豁免仅降低平台证据资格——
   系统预测与标注环境记录为 Windows 管线口径，结果标注 platform-scoped；
   它**不构成、也不替代 Linux Formal 结果**。任何把资格外推到 Linux 平台
   的宣称，仍需 Linux 侧证据（Issue #3 的 fixture 级 S6 字节一致 + 后续
   Linux 实仓验证）先行。
3. **frame-freeze 批准与 gate-ack 绑定（v1.1，R2 修订⑤；v1.2，R3 修订②）**：
   owner 在 frame-freeze 批准评论中给出授权记录 permalink（`--decision-ref`）
   与 16 位十六进制 ack；脚本强制校验
   `ack == sha256("{decision_ref}|{PLAN_VERSION}|{plan_sha256}")[:16]`，
   其中 plan_sha256 是合并时 plan-frozen-v1.md 的文件哈希。非空字符串
   不再被接受；校验失败时打印公式输入（不打印期望 ack 值）。
   **外部授权校验（v1.2，R3 修订②）**：ack 的公式输入均可由执行者自行
   计算，不构成对真实授权的依赖；因此 sample 模式还必须经 GitHub API
   核验 `--decision-ref` 指向**真实存在的 Human Owner 授权记录**——
   记录作者为 owner 账号（`OWNER_LOGIN = sunSUNQ`）、记录正文包含预期
   ack 令牌；permalink 无法解析、记录不可达、作者不符或正文无令牌，
   任一失败即 REFUSED。校验结果（verified/author/api_path）写入输出
   `gates.authorization_verification`；ack 计算保留，但不再是唯一依据。
4. **Before 基线先于任何修复线**：CALLS coverage / 146 UNKNOWN 的改进工作
   必须等待本 RQ1 的 Before 测量冻结（"先测后改"）。
5. 未满足以上任一条：只允许工具性准备（标注脚本、视图生成器），不得触碰案例。

## 7. 预算（规划值）

| 项 | 估算 |
|---|---|
| 校准批 25 例 × 2 标注者 | ~5h |
| 正式批 174 例 × 2 × ~6min | ~35h |
| 裁定（≤15% 分歧） | ~4h |
| 工具（视图生成、join、评分脚本复用） | ~8h |
| 合计 | **~52 人时**；墙钟 2–3 周（1 组标注者） |

模型/环境成本：标注在本地 JDT 环境（Windows）或 Linux（若 #3 先行）执行，
无外部服务依赖。

## 8. 排除范围（冻结）

- 不启动标注；不生成盲评视图（视图生成器属工具准备，可写但不可运行于真实样本）。
- 不修改 `src/`；不宣称 Java Stable；不做 failure attribution（评分后另阶段）。
- REFERENCES/IMPORTS 关系、recall（oracle-first 集）、跨版本漂移不在本协议。

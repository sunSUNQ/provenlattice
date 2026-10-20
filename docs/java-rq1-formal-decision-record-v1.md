# Java RQ1 Formal 立项 — 决策记录 V1

Issue Pilot #4 · 决策日期：2026-10-20 · 决策者：owner（sunSUNQ）
决策文号：**PL-JAVA-ISSUE-DECISION-20261020**；修订文号：**PL-JAVA-OWNER-DECISION-R2**（2026-10-20，AMENDMENT_REQUIRED）

## 1. Owner 决策（原文摘录）

> Issue #4：APPROVE_DESIGN_ONLY。批准 Java RQ1 Formal 立项及方案冻结，
> 规划 174 Gold、跨仓库分层抽样、双盲独立评审与分歧裁定。正式执行前
> 必须满足前置条件，禁止现在启动标注。

## 2. 选择与依据

- **立项依据**：Stage-0 Phase 4 建议 D（`docs/java-beta-stage0-report.md`），
  前置 B（callers 查询增强）已由 PR #12 MERGED（2026-10-19）完成；Java L1
  在三仓真实项目已验证；JDT 绑定精度在 21 gold + 168 冲突 0 错的既有证据
  （P2-E）表明精度合格但**从未经过 formal 级金标资格**——RQ1 formal =
  NOT_OBTAINED 是当前 Java 证据链上最大的资格缺口。
- **方案冻结**：见 `experiments/java_rq1_formal/plan-frozen-v1.md`
  （六分层、174 = 3×58 分配规则、双盲 + 校准门 κ 0.85/0.92 + 裁定协议、
  GRAPH_FIDELITY_SCORING_V1 评分语义、~52 人时预算）。
- **可参照 SOP**：C/C++ RQ1（`experiments/fidelity_v1/README.md`）——
  269 协议宇宙 → 174 密封 gold（86 CALLS + 88 IMPORTS）、κ 0.8516 校准、
  密封后才开封系统预测。Java 协议逐条映射该纪律。

## 3. 前置条件（执行前必须满足）

1. 方案/决策记录 owner 评审合并；
2. Issue #3 Linux JDT 补测 VERIFIED，或 owner 明示豁免（证据等级降级披露）；
3. Owner frame-freeze 批准 permalink + ack（sample 模式硬门，缺
   `--gate-ack` 即拒绝执行）；v1.2 起另需通过 GitHub API 外部授权校验
   （见 §6 R3 修订②）；
4. Before 基线先于任何修复线改动（先测后改）。

## 4. 预算与排除

- 预算：~52 人时（详见冻结方案 §7）；无外部服务依赖。
- 排除：标注执行、盲评视图生成（对真实样本）、`src/` 修改、
  Java Stable 宣称、failure attribution、REFERENCES/IMPORTS 家族、recall。

## 5. 待 owner 批准项（随本 PR 评审）

1. Java Stable 资格规则 = "RQ1 formal QUALIFIED"（冻结方案 §1 的门槛数值）；
2. 分层分配的 floor=3 / cap=24 规则与 §4 分配表；
3. 豁免条款的触发条件（若 #3 长期阻塞）。

## 6. R2 修订记录（PL-JAVA-OWNER-DECISION-R2，2026-10-20）

Owner 裁定：同意 Stable = RQ1 QUALIFIED；保留 174/58/floor3-cap24 分配规则；
**抽样方案暂不最终批准**，要求六项方法学修订后重审。落实情况（方案
plan-frozen-v1.md 升版 `v1.1-amendment-r2`，脚本与测试同步修订）：

| # | Owner 要求 | 落实 |
|---|---|---|
| 1 | 冻结种子的可复现概率抽样取代按序取前 n | 分层 SRS without replacement，公开预冻结种子，随机流绑定 (种子, 方案版本, 仓库, 分层, frame_id)（方案 §4） |
| 2 | 审计同行多调用点 JDT 状态关联键，消除碰撞/覆盖 | stats 模式新增 association_audit（碰撞键数/排除行数）；碰撞行排除出抽样框并如实报告（方案 §4、脚本 classify） |
| 3 | 盲评输入与系统预测严格隔离 | 盲评视图字段白名单 {case_id, repo, file, line}，生成时程序化泄露校验，检出即拒绝（方案 §5、脚本 make_blind_case + 泄露检查） |
| 4 | 定义加权方法、置信区间与 Stable 判定 | 分层加权估计量 + 分层 bootstrap 95% CI（B=10000 冻结种子）+ QUALIFIED 当且仅当规则（方案 §5 统计判定） |
| 5 | gate-ack 绑定真实授权记录与方案版本 | ack = sha256(decision_ref\|PLAN_VERSION\|plan_sha256)[:16]，脚本强制校验，拒绝时只出公式输入（方案 §6、脚本 expected_gate_ack） |
| 6 | Windows-only 豁免语义限定 | 仅降低平台证据资格、不替代 Linux Formal 结果，跨平台宣称仍需 Linux 证据（方案 §6.2） |

修订未重做三仓种群测量（v1.0 表保留为参照）；因修订引入关联键排除，
frame-freeze 时重测**有效总体**（排除后计数）为既定执行步骤。修订后
交独立复审，通过后重新提交 Owner 合并决策。

## 7. R3 决策落地（PL-SOLO-V2-OWNER-DECISION-20261020-R3 §2，2026-10-20）

Owner 裁定 **DESIGN_APPROVED_CONDITIONAL**：批准 Java Stable 必须满足
RQ1 Formal QUALIFIED；批准 174 例 / 每仓 58 / floor=3 / cap=24 初始设计、
冻结种子分层随机抽样、Windows-only 有限证据豁免（§5 三项待批准项随之
关闭）。合并前两项定向修订（方案升版 `v1.2-amendment-r3`）：

| # | Owner 要求 | 落实 |
|---|---|---|
| 1 | 资格判定的证据充分性：检查加权估计量在分层样本极小/为 0 时的退化行为；样本证据不足时不得落入二值判定，必须报告 INCONCLUSIVE（非资格中间档） | 新增 `experiments/java_rq1_formal/decision_rule.py`：估计量有效性门 G1（总样本 0）/G2（N_h>0 且 n_h=0 覆盖空洞）/G3（指标分母空）/G4（标注不完整）触发 INCONCLUSIVE 并列原因；二值 QUALIFIED/NOT_QUALIFIED 规则数值不变，仅估计量有效时可达；宽而有效的 CI 未达标仍是 NOT_QUALIFIED（方案 §5 统计判定、测试 DegenerateEvidenceTests/DecisionRuleTests） |
| 2 | frame-freeze 授权可验证性：sample 模式必须外部校验 decision_ref 指向真实 Human Owner 授权记录，失败即 REFUSED；ack 计算保留但不再是唯一依据 | `build_frame.py verify_authorization`：GitHub API 核验 permalink 可解析、记录可达、作者为 owner 账号（OWNER_LOGIN=sunSUNQ）、记录正文含预期 ack 令牌；任一失败 REFUSED 且校验结果写入 `gates.authorization_verification`（方案 §6.3、脚本 sample 门、测试 AuthorizationVerificationTests） |

执行边界不变：不启动 sample、不启动 Formal 标注、不签发 frame-freeze
ID、不修改 `src/`。修订后交独立复审（绑定新 HEAD），合并决策归 Owner。

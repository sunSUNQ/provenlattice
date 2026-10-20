# Java RQ1 Formal 立项 — 决策记录 V1

Issue Pilot #4 · 决策日期：2026-10-20 · 决策者：owner（sunSUNQ）
决策文号：**PL-JAVA-ISSUE-DECISION-20261020**

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
3. Owner frame-freeze 批准 id（sample 模式硬门，缺 `--gate-ack` 即拒绝执行）；
4. Before 基线先于任何修复线改动（先测后改）。

## 4. 预算与排除

- 预算：~52 人时（详见冻结方案 §7）；无外部服务依赖。
- 排除：标注执行、盲评视图生成（对真实样本）、`src/` 修改、
  Java Stable 宣称、failure attribution、REFERENCES/IMPORTS 家族、recall。

## 5. 待 owner 批准项（随本 PR 评审）

1. Java Stable 资格规则 = "RQ1 formal QUALIFIED"（冻结方案 §1 的门槛数值）；
2. 分层分配的 floor=3 / cap=24 规则与 §4 分配表；
3. 豁免条款的触发条件（若 #3 长期阻塞）。

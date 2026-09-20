# Changelog

所有已发布里程碑按时间倒序记录。tag 命名遵循 `provenlattice-*` 前缀约定；
各阶段的"已完成 / 明确未包含"以对应发布文档为准（`docs/releases/`）。

## provenlattice-sqi-v1.2（2026-09-20）— QUALIFIED / RELEASE READY

**SQI-V1.2 Cost Optimization Qualification**（结构化查询接口 V1.2 成本优化资格认证）：

- **SQI 18/18**（T01-T06 全部 3/3），9/9 frozen capability floors PASS，
  verdict **QUALIFIED**；完整 clean 36-cell batch（C4-R4，
  `SQI-FORMAL-C4-20260920T093328Z`），单 backend（deepseek-flash x36），
  逐 cell model provenance，零 sensitive leakage。
- **成本收益（vs V1.1 baseline）**：input -36%（962,640 → 616,598）、
  output -58%（230,508 → 97,249）、cache-read -73%（14.74M → 3.95M）、
  cache amplification 15.3 → 6.4、SQI calls 59 → 49、envelope bytes -26%。
- **V1.2-NR2 通用负区修复**（无任务特判、无硬编码 required id、无 oracle
  变更）：空结果 call-type-scoped 解析语义指导（result_meta）、同 anchor
  换预算重查的子集条款、knowledge-to-code 复合查询接口文档、会话级
  usage_discipline 第三条规则。T05.sqi 调用数 6-20/rep → 5/2/6。
- **验证状态**：97/97 tests（含 NR1×6、NR2×11）、implementation +
  secondary seal 重封、verify_release PASS、isolation baseline
  `27e40df5…` 不变。评审：`experiments/query_interface_v1/reviews/
  v1.2-final-qualification-review.md`；综合：
  `results/formal/C4-R4-SYNTHESIS-20260920-175458.json`。
- 明确未包含：oracle/contract 语义变更、S3+ scale bands、第四个
  benchmark 仓库、Overlay V1.1。

## 历史里程碑

| Tag | 日期 | 内容 |
| --- | --- | --- |
| `provenlattice-sqi-v1-repro` | 2026-09-17 | SQI-V1 reproducibility baseline（RQ1/RQ2/SQI-V1 全 QUALIFIED） |
| `provenlattice-sqi-v1` | 2026-09-17 | SQI-V1 结构化查询接口正式资格（Native vs SQI 36 cells） |
| `provenlattice-v1.0` | 2026-09-13 | Knowledge Layer / Cross-Layer Evidence 基线 |
| `provenlattice-core-v0.4` | — | Branch / Session Overlay |
| `provenlattice-core-v0.3` | — | Core 增量/shard 基线 |

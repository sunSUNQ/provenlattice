# P2-A/P2-D 原子集成报告

**状态：`P2AD_INTEGRATION_PASS`**（见 §6 裁定与边界）· 日期 2026-10-15
**HEAD**：`7ed0e8a` → `1ef88f9`（P2-A/P2-D 实现）+ 本报告 commits

---

## 1. P2-A 实现（已正式工程集成）

- `parsing/java.py`：`receiver_shape` 元数据（implicit_this/this/super/complex/
  identifier/class_static）。静态导入**成员常量**归类 identifier（审计 #1 形态）；
  单类型导入类与文件内类型归 class_static（显式证据）。
- `resolver.py` R1：CALLS + `receiver_shape="identifier"` 落入 0.75/0.98 阶梯时
  demote 为 ambiguous（候选保留 + `demote_reason=receiver_type_unknown`）；
  `CALL_KIND_VERSION 2→3`（旧库任一文件变化触发全量重解析收敛）。
- **语义勘误（实测发现）**：same-file 唯一候选恰为调用方法自身（owner）时，
  owner-self 排除后候选为空 → **unresolved**（非 ambiguous）——诚实且同样消除
  错误边；非 owner 场景候选完整保留（d5 测试）。
- Python/C/C++ 零变化（metadata 门控，P1 先例；pin 测试 test_r2_python）。

## 2. P2-D 实现（已正式工程集成，可选查询时能力）

- `provenlattice/java_semantic.py`：availability 内省（jdk/jdt 检测，缺任一 →
  unavailable + 原因）、P2-C 契约消费（invalid → 拒绝执行）、bundled driver
  源码（`java_semantic_driver/P2bDriver.java`）按需 javac 编译（离线、缓存）、
  超时/非零退出/OOM 分类诊断、recovered 过滤、merge_with_l1 审计视图
  （agree/recovered_by_jdt/conflict_conservative 保守保留）。
- Capability：`semantic_java`（query_time=True, optional_runtime=jdk+jdt,
  grade=local-only,diagnostic, languages=("java",)）；I0 冻结测试扩展并说明。
- CLI：`java-semantic <repo> [--classpath-manifest] [--mode] [--status-only]`
  （defect 命令先例；MCP passthrough 自动继承，frozen contract 文件未触碰）。
- **默认 index 不产生 JDT 进程、无 JVM 依赖**（全量测试即无 JVM 运行 +
  availability smoke 证明）。

## 3. 联动与合并策略（Phase 3）

合并策略已在 merge_with_l1 实现并测试：L1 精确层保持权威；JDT resolved 对
L1 ambiguous/unresolved 行标记 recovered_by_jdt；双方 resolved 不一致 →
conflict_conservative（双双保留，不静默选择）；JDT ambiguous/recovered 不伪造
确定性结果；每站点携带 provenance=`semantic:jdt-v1` + classpath_fingerprint +
CALL_KIND_VERSION。hikaricp 实测 merge：agree 716 / recovered_by_jdt 3215 /
conflict 38 / jdt_ambiguous 1248。**工程限制（如实）**：merge 为逐站点 SQL
原型级实现，gson/jgit 规模超时 → 大库 merge 优化列为 P2-E 工程项（统计数据
以 driver summary 为准）。

## 4. 冻结证据与兼容性

- 金样：py/cpp **IDENTICAL_EXCEPT_CALL_KIND_VERSION**（3>2 版本戳为设计内；
  期间发现 golden-py fixture 曾被早前迁移实验 touch 导致 source_hash 漂移，
  已恢复原样并重建复验——非产品回归）。
- MCP：frozen contract 文件零改动（git 核对）；新增 CLI 命令经 passthrough 透传。
- 旧库升级：CALL_KIND_VERSION 机制（任一文件变化 → 全量重解析收敛 v3）。

# PR #6 最终集成评审报告

**状态：`PR6_REVIEW_PASS`** · 日期 2026-10-15
**评审 HEAD（PR 分支）**：`5d902af`（本报告 commit 后以最新 HEAD CI 为准）
**main HEAD**：`42c6d89` · **PR**：https://github.com/sunSUNQ/provenlattice/pull/6

---

## 1. 评审范围与方法

独立 Code Review（非作者视角复核）：对象级历史审计、六模块代码审查、
双平台 CI 对应核验、发布包重建验证、PR 正文证据校正。含 **1 个真实缺陷
发现并修复**（normalize 不一致，详见 §5）。

## 2. PR 当前状态（评审时点）

| 项 | 值 |
|---|---|
| PR HEAD | d933c7c → **5d902af**（normalize 修复后，见 §5） |
| main | 42c6d89（无远程漂移） |
| state / mergeable | OPEN / MERGEABLE |
| 人工 reviews | 0（本报告即评审输入） |
| 变更规模 | 121 文件 +47,312 行（-93% vs 研发原始历史，大明细已排除） |

## 3. 关键模块审查结论（Step 1）

| 模块 | 结论 | 证据 |
|---|---|---|
| A. Java L1 / resolver | **PASS** | receiver_shape 门控仅 Java extractor 发射（Python/C/C++ 零触发，pin 测试）；0.75/0.98 demote 安全（8 历史 + 225 新鲜样本 0 错）；CALL_KIND_VERSION 3 + 旧库重解析机制；ambiguous 候选保留（d5 测试） |
| B. Classpath | **PASS（1 缺陷已修）** | **发现**：3 处残留 `resolve()` 与 `_normalize` 的 abspath 语义不一致（API 与 manifest 两条入口在短名环境产出不同拼写/指纹）→ 已统一 abspath（commit 至 5d902af），476 OK；顺序/去重/指纹契约一致；abspath 修复解决 CI 8.3 短名问题；符号链接语义=不解析（指纹机器无关，契约文档一致） |
| C. JDT Analyzer | **PASS** | 默认 index 零 JVM（CI no-JVM smoke 断言）；recovered 过滤（driver→state 映射）；超时/非零/OOM/输出损坏四类 fail-closed；无效 Classpath 拒绝执行；provenance=semantic:jdt-v1 + fingerprint；外部目标仅 FQN 字符串、永不映射为项目内节点/边 |
| D. merge_with_l1 | **PASS** | (file, line) 双键覆盖（line-only 缺陷已在 P2-E closure 修复并测试）；LEFT JOIN 保留 demote 行；LIKE↔lower-endswith 等价由等价 harness 证明（5217 站点）；冲突保守不覆盖；查询时视图零 L1 写入 |

## 4. Minor 发现（不阻断，记录）

1. driver 输出缓存文件名含 `abs(hash(...))`（进程盐化）→ 缓存目录孤儿文件累积（无害垃圾；建议后续用内容寻址命名）。
2. driver 编译 marker 不感知源码更新 → driver 升级需清编译缓存（文档化建议）。
3. 诊断顺序：无 JDK 时 classpath 问题被 jdk_not_found 先行覆盖（信息完整性改进项）。
4. merge bulk 全量行进内存（jgit ~178k 行，百 MB 级，可接受；持久化为后续立项）。

## 5. 发布包与接口（Step 2）

PR 分支重建：**wheel + sdist 均含 P2bDriver.java** ✅；BOM manifest ✅；无第三方
JAR 打包 ✅（用户自备，EPL-2.0 边界）；无开发者绝对路径（driver 缓存 tempfile）✅；
README 示例为真实 CLI 输出 ✅；MCP frozen contract 零改动 ✅；默认 L1 无 JVM ✅。

## 6. PR 正文证据校正（Step 3）

已更新：Linux 平台状态由 "NOT_VERIFIED yet (CI will run)" → **"CI PASS (full
suite, 476 tests, ubuntu-latest); Linux JDT run NOT_VERIFIED"**。其余表述复核
准确：146 UNKNOWN 边界 ✅；WRONG_RESOLUTION=0 附样本与真值边界 ✅（报告层）
；38 冲突审计措辞与深度一致 ✅；query-time 非持久化 ✅；升级全量 index ✅；
RQ1 NOT QUALIFIED ✅。冻结原始证据未修改。

## 7. 远程 CI 与合并条件（Step 4）

- **HEAD 5d902af 对应 run 38882157203**：test-windows **PASS**（12m3s）、
  test-linux **PASS**（42s）——CI 与最新 HEAD 严格对应 ✅。
- 476 项测试（两平台）；driver 打包断言 ✅；Java L1 no-JVM smoke ✅；CLI smoke ✅。
- JDT 可选步骤：**CI_SKIPPED**（两平台，无 PL_JAVA_JDT_CLASSPATH）——明确不计入
  JDT 测试通过；Linux JDT = NOT_VERIFIED（对外支持承诺的限定项）。
- Mergeability：MERGEABLE；分支保护/人工 review 待执行。

## 8. 回归（Step 5）

全量 **476 tests OK**（源码与 PR 分支 worktree 双跑）；修复后 classpath 13/13；
金样/MCP/无 JVM 路径沿用 P2-E/P2AD 结论（本轮仅 classpath normalize 一致性修复，
无 resolver/语义变更）。

## 9. 是否建议合并

**建议人工批准合并 PR #6 到 main**。合并后验证建议：
1. main 复跑 CI（双平台）+ 全量 index 冒烟；
2. Linux 配置 JDT classpath 补验（升格 Linux JDT 支持）；
3. RQ1 formal 立项评估；4. Stable 准备依 Beta 反馈。

## 10. 发现分级

- **Blocker：0**
- **Major：0**（normalize 不一致已在本轮修复并重验 CI）
- **Minor：4**（§4，均记录不阻断）

# P2-C 验证报告（Classpath 契约）与 P2-A 设计交付

**状态：`P2C_COMPLETE` + `P2A_DESIGN_READY_FOR_APPROVAL`** · 日期 2026-10-15
**HEAD**：f713ec2 → （本轮 commits，未 push）

---

## 1. P2-C 实现

- 新增 `src/provenlattice/classpath.py`：`build_classpath` / `load_classpath_file` /
  `ClasspathContract` / `ClasspathIssue` / `fingerprint_for`。
- **零改动**：resolver/parsing/graph/storage/cli、Python/C/C++ 路径、默认 index
  （模块不被 L1 import，无 JVM 依赖）。
- CLI 决策：现有 CLI 无配置扩展点，为避免架构不一致的悬空命令，**P2-C 以库级
  契约交付**，CLI 接线归入 P2-D（契约文档 §9 记录该决策）。
- 测试：`tests/test_classpath.py` 13 项（cp01–cp13）：单 jar/多 jar+class 目录/
  项目-依赖边界/空/缺失/BAD_KIND+CORRUPT_JAR/重复去重/空格特殊字符/顺序敏感/
  base_dir 相对解析/清单文件/指纹变化=invalidation。

## 2. 真实项目验证（evidence/java-phase2-p2c/）

固定 SHA：HikariCP a4d93f4 / gson e2292f9 / jgit 6e68739。

| 场景 | 结果 |
|---|---|
| A 无 classpath（3 仓库） | valid/usable，`cp:empty` ✅ |
| B 手工完整（源码根+slf4j jar） | valid（hikaricp 51 根 + 1 依赖），指纹稳定 ✅ |
| C 部分缺失（no-such.jar） | **invalid fail-closed**（NOT_FOUND，fp=null）✅ |
| D 错误输入（不存在+README 当 jar） | invalid（NOT_FOUND+BAD_KIND）✅ |
| E 更新 | 指纹变化 ✅（invalidation 输入） |
| F 重复+顺序 | 去重报告 + 首现顺序保持 ✅ |
| JDT 消费（**隔离原型**） | 契约 dependencies 直接喂 P2-B driver：rc=0、calls_resolved=4021（与 P2-B 独立测量一致）✅ |

**标注**：JDT 消费为独立原型验证，**不代表正式 P2-D 集成通过**。

## 3. 全量回归（Phase 6）

| 项 | 结果 |
|---|---|
| 全量 unittest | **462 OK**（449 + 13 classpath；测试数变化=本任务新增，已解释） |
| Java 既有测试 | 32/32（含于全量） |
| Python/C/C++ 回归 | 全量内通过；classpath 模块不被旧语言路径触碰 |
| 默认 index 对照 | L1 路径零改动（模块纯新增）；P7 口径一致 |
| MCP 桥接 | 零 CLI 变更 → frozen contract 不受影响 |
| 金样 | 上轮 P8 已验 IDENTICAL；本轮零 resolver/schema 变更 |
| 无 JVM L1 smoke | 全量测试即无 JVM 运行 ✅ |
| Classpath freshness 测试 | cp13（集合变化→指纹变化）+ E 场景 ✅ |
| 失败原因 | 无失败项；无 INFRA_BLOCKED 冒充 PASS |

## 4. P2-A 设计交付（Phase 4，未实施）

`docs/java-phase2-p2a-demote-design-review.md`：R1 规则（identifier-receiver ×
{0.75,0.98} → ambiguous 候选保留）/ R2/R3 保持清单 / receiver_shape 门控机制 /
8 决策点全答 / 替代方案 A2/A3 取舍（均无法达成 Wrong-Resolution 目标）/ 回退 /
联动交付保障。**决策清单待人工批复**（demote 批准 / 联动交付 / JDT 禁用行为 /
内存预算四项）。

## 5. Maven/Gradle 设计调查（Phase 5）

见 `docs/java-phase2-p2c-classpath-contract.md` §8：只消费已生成制品、永不自动执行
构建脚本、离线优先、手工契约始终覆盖自动发现、不可靠发现 fail-closed。未实施。

## 6. 未解决风险

1. P2-A 未获批前，L1 启发式错误绑定（真实仓库 8/60 审计口径）持续存在——消费方
   须按既有契约将 <0.99 置信边视为 Candidate。
2. CLI 接线缺位：P2-D 前用户只能经 API 使用契约（已在文档声明）。
3. JDT 消费仅为隔离原型证据链；P2-D 正式集成需完整 capability/fail-closed 实现。

## 7. 下一条 Agent 任务建议

人工批复 P2-A 决策清单后：**P2-A 实施**（含 8 样本 fixture 化回归）与 **P2-D**
（driver 生产化 + capability 注册，消费 P2-C 契约）按联动交付执行。

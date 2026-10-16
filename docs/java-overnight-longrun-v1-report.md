# PL-JAVA-OVERNIGHT-LONGRUN-V1 — 最终报告

**最终状态：`JAVA_LONGRUN_COMPLETE — READY_FOR_FINAL_REVIEW`**
**执行日期**：2026-10-15 · **起始 HEAD** `42c6d89` → **结束 HEAD** 258eeb3（7 个本地 commit，未 push）

---

## 1. Executive Summary

Java 支持在本长程任务中从"基础图谱阶段"推进到"**经真实项目验证、有明确性能边界、
语义增强路线经实测选定并有最小原型**"的工程状态：

- **正确性**：L1 在全部覆盖场景保持 Wrong-Resolution=0（T9-B 21 项 gold 行级审计 0 错、
  真实仓库 60 样本中全部 1.0/0.99 高置信绑定 0 错）。
- **性能**：1.9k 文件真实仓库冷索引 24.9s / 1GB RSS / 856MB DB，零解析失败；
  增量路径在大库无收益（实测），已作为设计输入记录。
- **语义后端**：JDT 实测 20/21 CORRECT + JLS 歧义正确拒绝，唯一候选；JavaParser 实测
  2/21 错误绑定（JLS 歧义静默违反）被排除；SCIP Java 官方放弃 Windows launcher（INFRA_BLOCKED）。
- **诚实披露**：真实仓库人工审计暴露 receiver 类型不可知导致的 0.75/0.98 启发式错绑
  （60 样本 7 错，11.7%）——这是 V0 冻结阶梯的全语言既有边界，本次**未改契约**，
  已量化并作为 Phase 2 首要输入。

## 2. 起始状态与执行环境

- main @ `42c6d89` + 未提交的 T1–T3/P1/T6 工作（按 P0 清单核对：10 tracked M + 3 untracked，
  与前序报告一致）；基线 442 tests OK。
- Windows / Python 3.12.10 / 无预装 JDK（现场下载 Temurin 21.0.12.1 至仓库外路径）/
  网络可用。证据目录 `evidence/java-overnight-longrun-v1/`（checkpoint 机制 + JSON 校验脚本）。

## 3. 实际执行阶段

| 阶段 | 状态 | 产出 |
|---|---|---|
| P0 工作区保护/断点机制 | COMPLETE | preflight/manifest/plan/checkpoints + 3 个阶段提交 |
| P1 P1 修复最终复审 | COMPLETE | `P1_FINAL_REVIEW_PASS`（8 项核验；旧库延迟升级裁定 NOT_BLOCKED + 升级注记） |
| P2 T9-A 真实项目基准 | COMPLETE | 3 仓库 ×（cold3/warm3/incr3/delete1）原始数据 + 统计 |
| P3 T9-B 语义后端实测 | COMPLETE | 21 项共享 gold，三后端对照（SCIP INFRA_BLOCKED） |
| P4 Phase 2 决策 | COMPLETE | ADR：JDT 唯一候选（可选 Analyzer） |
| P5 语义最小原型 | COMPLETE | L1 wrong=0 / JDT wrong=0 / 7 项可改进点证明（仅 evidence/，未接 L1） |
| P6 对抗补强 | COMPLETE | java25–31 七场景，无新缺陷 |
| P7 真实仓库端到端 | COMPLETE | 2 仓库 CLI 全链路 + 60 样本人工审计 |
| P8 最终回归 | COMPLETE | 449 tests OK + 金样 + 干净环境 + CLI smoke |
| P9 报告与提交 | COMPLETE | 本报告 + 7 commits |

## 4. P1 最终复审

`P1_FINAL_REVIEW_PASS`。要点：两级阶梯守卫覆盖确认；java22–24 修复实证；保守行为
（重载/通配/this()）不变；Python pin 成立；C/C++ 零变化；CALL_KIND_VERSION=2 与
freshness 兼容（v1 库 + 任一文件变化 → 全量重解析收敛 v2，实测 reprocessed=9/reused=0）。
旧库延迟升级风险裁定 NOT_BLOCKER：受影响库仅存在于本会话未发布工作树；发布注记强制
"升级后执行一次全量 index"。

## 5. Java L1 性能结果（T9-A，原始数据见 bench/）

| 仓库（SHA 固定） | Java 文件 | cold median | cold RSS | 节点/边 | 引用 (res/amb/unres) | DB |
|---|---|---|---|---|---|---|
| HikariCP a4d93f4 | 114 | 0.65s | 60MB | 2083/5795 | 13494（36/15/49%） | 24MB |
| gson e2292f9 | 264 | 2.83s | 132MB | 5479/16573 | 43340（35/16/49%） | 77MB |
| jgit 6e68739 | 1896 | 24.9s | 1026MB | 37944/142220 | 360289（43/30/27%） | 817MB |

- 2274 文件零解析失败、零语法错误文件（上游语料干净）。
- **warm 慢于 cold**（jgit 31.7s vs 24.9s：大库 replace_snapshot 删+插代价）。
- **增量无收益**（jgit 33.3s vs cold 24.9s）：单文件触动的受影响引用集近似全量
  （跨包短名碰撞）。→ Phase 2 输入：大库建议全量重建或设计文件级解析缓存。
- 未发明 PASS 阈值；以上为测量值。

## 6. 语义后端对照（T9-B，21 项人工 gold）

| 维度 | JavaParser 3.26.4 | JDT 3.37.0 | SCIP Java |
|---|---|---|---|
| 跨文件/同名/重载/继承/接口/泛型/构造器 | 全 CORRECT | 全 CORRECT（含参数化绑定） | INFRA_BLOCKED |
| **JLS 双通配歧义** | **WRONG×2（静默绑定）** | **CORRECT（拒绝+诊断）** | — |
| 缺失依赖 | 正确拒绝（Unsolved） | **recovered binding——必须过滤 isRecovered()** | — |
| 语法错误恢复 | CORRECT | CORRECT + 显式诊断 | — |
| Maven/Gradle 多模块 | 需手工 classpath | 需手工 classpath | 构建集成一等（未测） |
| Windows | OK | OK（需去签名 workaround） | **官方 drop（v0.13.1 PR#970）** |
| 记分 | 17 正确 / **2 错** | **20 正确 / 0 错**（过滤后） | — |

**关键发现**：L1（P1 修复后）是唯一在歧义场景零伪造的组件；语义后端提供召回而非安全。

## 7. Phase 2 技术决策（ADR 摘要）

**JDT 作为唯一 Phase 2 可选 Analyzer 候选**（独立 JVM 进程 + JSON、fail-closed、
provenance=`semantic:jdt-v<n>`、recovered 过滤、不改 L1 schema/主表）。JavaParser 与
SCIP 均排除（理由见上）。最小范围：跨文件调用精确绑定 + 重载消歧 + JLS 歧义显式标注。

## 8. 原型实现结果（P5）

`evidence/.../prototype/jdt_analyzer.py`（不触 L1 代码路径）：21 项 gold 上
**L1 wrong=0 / JDT wrong=0**（recovered→UNRESOLVED 降级验证）；7 项 L1 不可精确
（3 重载 + 2 单通 + 2 JDK 类型）由 JDT 提供 CORRECT 绑定——原型验收条件全部满足。

## 9. 真实仓库验证（P7）与人工审计

- CLI 全链路（index/symbol/callers/callees/references/task-context/增量/删除重建）
  双仓库 PASS，orphan edges=0，generation 台账正确（1 full + 3 incremental）。
- **人工抽样审计（固定种子 30+30，逐条读源码核对）**：53 正确 / **7 错误（11.7%）**。
  全部 7 错为同一根因：**receiver 类型不可知**，实例调用短名恰与项目内方法唯一同名
  （0.75）或同文件同名（0.98）时绑错（JDK 的 Map.put/List.stream/String.repeat/
  Field.get、lambda 参数的 Credentials.getPassword 等）。
  **高置信阶梯（1.0/0.99）零错误**。→ 查询消费契约：0.75/0.98 边必须按 Candidate
  处理（与平台"resolved ≠ Verified"一致）；该边界为 V0 冻结契约全语言既有行为，
  本次不改契约，JDT 路线可直接消除该类（T9-B 同形态全部 CORRECT）。

## 10. 回归与 parity（P8）

- 全量 unittest **449 OK**（417 基线 + 32 Java：21 T1-T3 + 4 P1 + 7 P6）；测试数量
  变化全部可解释（每 commit 附明细）。
- 四表金样：py/cpp 均 **IDENTICAL**（raw_references 仅 call_kind_version 1→2 设计内
  版本戳差异——v1.4 缓存失效契约）。
- 稳定 ID：重复索引 id 逐字节一致（Exp4）；freshness/迁移：v1→v2 收敛实测。
- 干净 venv 安装 + CLI smoke PASS。

## 11. 发现和修复的缺陷

| # | 阶段 | 缺陷 | 处置 |
|---|---|---|---|
| 1 | P0 | PowerShell here-string 写 JSON 带 BOM | 证据统一 write 工具 + validate 脚本 |
| 2 | P2 | RSS 采集恒 0（GetCurrentProcess restype 截断） | ctypes 签名显式声明，修复后全量重跑 |
| 3 | P3 | JDT driver source level 未设 → 静态导入全失败 | compliance=21（driver 配置，非 JDT 缺陷） |
| 4 | P3 | eclipse 跨 jar 签名冲突 | 去签名重打包 workaround（集成复杂度证据） |
| 5 | T9-B | gold Q10/Q11 初始标注错误（单通非歧义） | 按 JLS 修正并记录修正过程，补双通 Q20/21 |
| 6 | P5 | analyzer 判定粒度（同行多 gold 交叉误判） | 行级聚合判定，最终 L1/JDT wrong 均 0 |
| 7 | P6 | java31 断言笔误（默认包命名 by-design） | 修正断言 |
| 8 | P7 | p7 锚点提取缺陷 | 正则类名提取 |

## 12. 未完成项

- **SCIP Java 实测**：INFRA_BLOCKED（官方 Windows launcher 移除）；其 Maven/Gradle
  集成维度仅保留桌面评估口径，未计入实测记分。
- **JDT 大库内存**：jgit 规模的 JDT binding 内存未测（时间盒）；Phase 2 立项首项。
- **receiver 类型边界**：未改 0.75/0.98 阶梯契约（需独立设计评审；量化证据已入档）。
- **可选 Analyzer 正式注册**（CAPABILITY_CONTRACT/analysis_query 接线）：属 Phase 2
  正式立项，本轮原型仅存在于 evidence/。

## 13. 风险与下一步建议

1. **Phase 2 立项**：按 ADR 启动 JDT 可选 Analyzer（内存复测 → classpath 发现 →
   capability 注册）；Receiver 类型边界是首要收益点（真实仓库 7/60 错误全部属于它）。
2. **增量路径**：大 Java 库建议先"全量重建"官方口径；文件级解析缓存可作为独立优化提案。
3. **消费契约**：文档明确 0.75/0.98 边 = Candidate（平台契约已含，建议 capability-matrix
   补一行消费指引——Phase 2 一并做）。
4. **SCIP**：仅当项目出现 Linux/容器化索引服务时重开评估。

## 14. Commit 清单（本地，未 push）

| Commit | 内容 |
|---|---|
| d36e088 | java: T1-T3 foundation graph support |
| d5aa6e7 | java: P1 resolver type-target guard |
| dec0272 | java: T6 capability registration |
| 606fe6b | java: T9-A benchmark + P0-P1 evidence |
| 9847a39 | java: T9-B comparison + ADR + P5 prototype |
| bf8a13e | java: P6 adversarial hardening |
| 258eeb3 | java: P7 e2e verification + audit |
| （本报告 commit） | java: longrun final report |

下载的 JDK/语义后端 jar/三个基准仓库全部位于仓库外临时路径，未入库。

## 15. 各阶段状态汇总

P0–P9 全部 **COMPLETE**；无 FAIL、无 BLOCKED（SCIP 为后端级 INFRA_BLOCKED，已保留证据）；
无 NOT_RUN 项。测试基线 442 → 449（417 主基线 + 21 T1-T3 + 4 P1 回归 + 7 P6 对抗），
全部增量可解释。

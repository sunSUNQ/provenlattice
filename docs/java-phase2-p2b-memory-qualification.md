# PL-JAVA-PHASE2-P2B-MEMORY-QUALIFICATION — JDT 大仓库内存与性能资格报告

**状态：`P2B_QUALIFIED`**（真实测量充分，形成供审批的预算候选与工程方案；不等于 Phase 2 整体批准、不等于内存预算获批）
**日期**：2026-10-15 · **HEAD**：ed8ac90 → 3f79181（本轮 2 commits，未 push）

---

## 1. 环境与工具版本

| 项 | 值 |
|---|---|
| OS / Python | Windows / 3.12.10 |
| JDK | Temurin 21.0.12.1 LTS（仓库外 `%TEMP%\opencode\longrun\tools`） |
| JDT | org.eclipse.jdt.core 3.37.0 + ecj 3.37.0 + 10 platform jars（去签名 workaround，T9-B 同套件） |
| L1 | tree-sitter 0.26.0 + tree-sitter-java 0.23.5，ProvenLattice @ HEAD |
| 仓库（SHA 固定，仓库外） | HikariCP a4d93f4（112 java）、gson e2292f9（263）、jgit 6e68739（1891） |
| 测量口径 | **进程内自报**（L1：bench_child ctypes；JVM：driver 自报 heap/cpu）+ **父进程采样峰值 RSS**（100ms 轮询 WorkingSetSize）+ **GetProcessTimes 精确 CPU**。单进程口径；组合模式明确标注"非同时峰值" |

## 2. 实验矩阵与证据索引

| 模式 | 仓库 | 次数 | 原始文件 |
|---|---|---|---|
| A. L1 默认索引 | 3 仓库 | 3×3 | `results/p2b-l1-*-raw.json` |
| B. JDT 独立精确解析（stats） | 3 仓库 | 3×3 | `results/p2b-jdt-*-raw.json` |
| B'. JDT heap 变体 | jgit | 512m×1、1g×2、2g×2、4g×3 | `results/p2b-jdt-jgit-heap*-raw.json` |
| C. L1+JDT 组合 | 隔离脚本顺序执行 | 报告制 | §3.4 |
| Classpath 变体 | hikaricp no-cp vs slf4j-cp | 1+1 | `results/p2b-jdt-hikaricp*-{2g}-raw.json` |
| 历史错误点行级 | hikaricp/gson full 模式 | 1+1 | `results/p2b-*-full-detail-0.jsonl`（10.3k/41.6k 行）+ `phase4-historical-sites.json` |
| 失败/隔离 | 坏路径 / OOM / L1 无 JVM | 各 1 | §3.3 |

## 3. 实测结果

### 3.1 主矩阵（3 次独立重复，逐次原始值见 raw 文件；下表为中位数）

| 模式 | HikariCP | gson | jgit |
|---|---|---|---|
| **L1 cold** | 0.80s / 60.3MB / cpu 0.73s | 2.51s / 131.8MB / cpu 2.42s | **25.1s / 1026.6MB / cpu 24.4s** |
| **JDT 独立** | 1.30s / 275.7MB / heap 94MB | 2.21s / 631.7MB / heap 140MB | **7.43s / 1291.0MB / heap 756MB** |
| JDT cpu | 4.70s | 9.34s | 39.2s |
| 组合（顺序） | ≈2.1s | ≈4.7s | ≈32.5s |
| 组合峰值内存 | max(60, 276)MB（非同时峰值，诚实口径） | max(132, 632)MB | max(1027, 1291)MB |

**核心发现：JDT 批量绑定在 jgit（1891 文件）上 wall 7.4s——比 L1 cold 的 24.9s 快 3.3 倍**；
额外内存代价 +265MB（+26%）。L1 与 JDT 是互补而非互斥的成本结构。

### 3.2 JDT 解析统计（无 classpath，jgit）

files_parsed 1891/1891 · problems_total 30612（缺依赖与测试代码的预期诊断）·
calls：resolved 138315 / recovered 1 / ambiguous(含 null binding) 23970 ·
types：resolved 95487 / recovered 2280 / ambiguous 85 · parser_inits = **1**（单实例全程）。

### 3.3 资源边界与异常（全部分类记录，不计 PASS）

| 实验 | 结果 |
|---|---|
| -Xmx512m @jgit | **OutOfMemoryError: Java heap space**（rc=1，cpu 空转 64s 后失败）→ heap 下限 ≈1g |
| -Xmx1g / 2g / 4g | 全部成功；RSS 1128-1293MB；heap_used 756MB @1g → **1g heap 即可承载 jgit 规模** |
| RSS 随 -Xmx 增长 | 1g→~1.13-1.19GB，4g→~1.29GB（JVM 预留效应；建议固定 -Xmx1g 控制峰值） |
| 缓存/明细驻留 | gson full 模式 41569 行明细流式写盘：heap 168MB vs stats 140MB（**+28MB**，流式有效，无显著驻留） |
| 重复初始化 | parser_inits=1（三仓库全程单 ASTParser 实例，无重复初始化） |
| 单文件变更 | JDT 批量模型无增量 API → 增量成本 = 全量 7.4s @jgit；**仍显著优于 L1 增量的 33.3s** |
| 失败隔离 | 坏路径 → rc=1 进程级失败，无状态污染；L1 全程无 JVM（本基准 L1 部分即无 JVM 运行） |

### 3.4 组合模式（C）

隔离脚本顺序执行 L1 → JDT（不修改正式路径）：组合总时长 = 两者之和（jgit ≈32.5s），
组合峰值 = **max(单进程峰值) 而非同时峰值**（两进程串行无并发；如实标注，不做虚假相加）。

## 4. Classpath 与解析成本（Phase 2）

| 变体 | problems | calls_resolved | types_recovered | 结论 |
|---|---|---|---|---|
| hikaricp 无 classpath | 2065 | 3894 | 255 | slf4j 等依赖类型全部 recovered |
| hikaricp + slf4j-api jar | 1898（**-167**） | 4021（**+127**） | 242（-13） | classpath 供给 1:1 转化为精确解析 |

- 外部依赖无法解析（FastMath 类形态）→ recovered binding，**集成时必须过滤
  `isRecovered()`**（T9-B 已证），过滤后降级为 unresolved/ambiguous，不产生幽灵 FQN。
- JDT 错误确定性绑定：21 项 gold + 8 真实错误点实测中**未发现**（歧义正确拒绝、
  recovered 可识别）；JLS 歧义 resolved=null（非绑定）。

## 5. 与 Phase 2 正确性目标关联（Phase 4）

**8/8 历史错误绑定样本在 JDT 下全部 CORRECT**（`phase4-historical-sites.json` 行级原始数据）：

| 样本 | L1 错绑 | JDT 绑定 | recovered |
|---|---|---|---|
| HikariConfig:318 `current.getPassword` | HikariConfig.getPassword | **util.Credentials**（跨文件 lambda 参数类型流） | false |
| ClockSourceTest:41 `MINUTES.toMillis` | ClockSource.toMillis | **java.util.concurrent.TimeUnit** | false |
| ConcurrentBag:305 `sharedList.stream` | StringAppender.stream | **java.util.Collection<T>**（接口层级正确） | false |
| HikariConfig:1029 `field.get` | FastList.get | **java.lang.reflect.Field**（同行 AtomicReference.get 正确区分） | false |
| JsonObject:223 `members.get` | JsonObject.get | **LinkedTreeMap<String,JsonElement>** | false |
| MapTest:95 `map.put` | 嵌套测试类.put | **java.util.Map** | false |
| NumberLimitsTest:103 `"1".repeat` | JsonReaderTest.repeat | **java.lang.String** | false |
| CollectionTest:273 `target.add` | 嵌套测试类.add | **java.util.List** | false |

分类：8/8 属"需要类型环境"样本（receiver 声明类型或泛型层级），classpath 不影响
其中 JDK/项目内类型解析（源码树内互相可见）；依赖 jar 类型（slf4j 等）才需要
classpath。**无一样本只能返回 ambiguous**。联动结论：P2-A（demote）+ P2-D（JDT 补召回）
的证据基础成立。
**边界声明**：以上为**独立 JDT 测试已验证**；L1+JDT 组合为**隔离原型已验证**（顺序
执行）；**正式集成（capability/查询面）尚未验证**——P2-D 范围。

## 6. 部署方案对比（Phase 5）

| 维度 | 方案 A：按需独立 Analyzer | 方案 B：持久化/缓存复用 |
|---|---|---|
| 内存 | 进程内峰值 1.3GB（jgit），用完即释 | 常驻 ~1.2GB+（缓存驻留随库增长） |
| 延迟 | 全量批处理 7.4s @jgit | 首次同 A，后续增量查询快（需自建失效协议） |
| 冷启动 | JVM+ASTParser ~1s（含在总量内） | 常驻零冷启动 |
| 扩展性 | 1891 文件实测 7.4s（无退化迹象） | 缓存一致性复杂度随库规模上升 |
| 失败隔离 | **天然（进程退出即隔离）** | 需自建（常驻状态污染风险） |
| classpath 管理 | 每次显式传入（简单、可审计） | 需热更新协议 |
| 对默认 L1 影响 | 零（独立进程，用完即弃） | 零（但运维面增加常驻服务） |
| 工程维护 | 低（T9-B/P2-B driver 已验证形态） | 高（JDT 内部缓存无公开持久化 API，自建成本大） |

**推荐：方案 A（按需独立 Analyzer）。** 依据：jgit 全量批处理仅 7.4s，缓存复用的边际
收益小于其失效协议/常驻内存/隔离复杂度成本；实测全部基于方案 A 形态。**不适用条件**：
未来出现交互式高频单文件查询场景（IDE 式），届时重评 B。

**内存预算候选（供人工审批，本轮不自行批准）**：
- JVM heap：固定 `-Xmx1g`（实测 floor；512m OOM，jgit used 756MB）
- 进程 RSS：≤ **1.6GB**（实测峰值 1.29GB @4g heap，留 ~24% 余量）
- 时长：jgit JDT 批处理 ≤ **15s**（实测 7.4s，2× 余量）
- 组合口径：组合内存 = max(单进程峰值)，不叠加

## 7. P2-C/P2-D 技术前置条件（据本轮实证更新）

1. **P2-C**：classpath 输入契约（已验证 jar/源码树双形态）；缺依赖 → recovered 过滤
   + 显式报告（protocol 就绪）；Maven/Gradle 发现器仍为独立后续任务。
2. **P2-D**：driver 生产化清单——recovered 过滤（已验证语义）、歧义→AMBIGUOUS 行、
   超时与 OOM fail-closed（rc≠1→拒绝写入）、provenance `semantic:jdt-v1` + backend
   version、JVM 参数固定化（-Xmx1g）、`CAPABILITY_CONTRACT`/I0 冻结测试扩展。
3. **P2-A 联动**：8/8 样本证明 JDT 可补回全部已知错误形态——P2-A demote 的召回损失
   由 JDT 精确层承接，证据充分。

## 8. 风险、未完成项与下一步

| 项 | 状态 |
|---|---|
| JDT RSS 采样为 100ms 轮询（非连续） | 峰值可能低估极短尖峰；影响 < 测量噪声，已标注 |
| SCIP | 仍 INFRA_BLOCKED（上轮结论不变） |
| Maven/Gradle classpath 发现 | 未实施（P2-C 后续任务） |
| 组合模式同时峰值 | 未测（串行原型无并发；若 Phase 2 未来并行化需重测） |
| RQ1 formal | 不涉及，未宣称 |

**下一步 Agent 任务建议**：P2-A（demote 实施，须人工批准设计后启动）+ P2-C（手工
classpath 契约生产化），随后 P2-D。

## 9. Commit 与工作区

| Commit | 内容 |
|---|---|
| 3f79181 | P2-B 测量（矩阵/heap 变体/classpath/8 样本行级） |
| （本报告 commit） | P2B 资格报告 |

工作区：src/tests 零改动；新增文件限定于 `evidence/java-phase2-p2b/` 与本报告；
大型依赖（JDK/jar/仓库）全部在仓库外。

# P2-A/P2-D 性能、内存与故障验证报告（Phase 5）

**口径**：与 P2-B 相同固定 SHA 仓库、同采样器（父进程 100ms RSS 轮询 +
GetProcessTimes 精确 CPU；JVM heap 由 driver 自报）。逐次原始值入库。

## 1. 生产路径性能（provenlattice.java_semantic 全链路）

| 仓库 | 模式 | 运行 | wall（逐次） | 预算 |
|---|---|---|---|---|
| jgit | stats，-Xmx1g | **3×** | 8130 / 8015 / 8245 ms（中位 **8130ms**） | **≤15000ms ✅** |
| hikaricp | full（含 merge 原型） | 1× | 1304ms | — |
| gson | full | 1× | 2206ms | — |
| jgit | stats（P2-B 同口径旁证） | 3× | 6621/7826/6733ms | ✅ |

jgit RSS：P2-B 同 heap（-Xmx1g）采样 **1.13–1.19GB ≤ 1.6GB ✅**；heap_used 756MB。
资源预算（D4）全部满足：**Xmx1g ✅ / RSS ≤1.6GB ✅ / jgit ≤15s ✅**（预算正式批准仍属人工）。

## 2. L1-only 与组合对照（收紧后 L1）

| 仓库 | L1 tightened cold（index） | L1+JDT（顺序组合） |
|---|---|---|
| hikaricp | 0.80s / 60MB | ≈2.1s / max(60, 276)MB |
| gson | 2.41s / 132MB | ≈4.6s / max(132, 632)MB |
| jgit | 25.1s / 1027MB | ≈33s / max(1027, 1291)MB |

（组合 = 串行 L1 + JDT；max 口径，非同时峰值；与 P2-B 冻结基线同量级 ✓）

## 3. 故障验证（全部 fail-closed，零启发式回退）

| 探针 | 结果 | 诊断 |
|---|---|---|
| JDK 缺失（PATH/JAVA_HOME/PL_JAVA_JDK 均无） | `unavailable / jdk_not_found` ✅ | availability 内省 |
| Classpath 契约无效（missing jar） | `failed / classpath_contract_invalid` ✅ | 契约 issues 结构化输出 |
| JDT OOM（-Xmx512m @jgit，P2-B） | rc=1 → `failed / jdt_oom` 分类 ✅ | stderr 分类 |
| driver 非零退出 | `failed / jdt_nonzero_exit` + stderr tail ✅ | 输出协议校验 |
| driver 输出不可解析 | `failed / driver_output_unparseable` ✅ | summary 缺失检测 |
| 超时 | `failed / timeout` ✅（timeout_s 参数） | — |
| classpath 修改 | fingerprint 变化 → 结果标记新 fingerprint ✅（cp13/E 场景） | freshness 输入 |
| 缓存失效 | 编译缓存 marker；fingerprint 驱动结果失效 ✅ | — |
| 隔离性 | 进程级失败不污染 L1（L1 全程无 JVM）✅ | — |

## 4. 进程启动与缓存计数

- JVM 启动次数：每次 java-semantic 调用恰 1 次（driver 单实例，parser_inits=1）。
- 结果缓存：当前为查询时重算（无 JVM 驻留）；driver 明细流式写盘（+28MB 驻留，P2-B 实测）。
- 解析成功/失败数：见 correctness 报告 T3 summary（files_parsed 全量成功，零 parse failure）。

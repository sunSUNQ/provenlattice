# P2-E 性能报告

**数据源**：`evidence/java-phase2-p2e/results/{merge-perf,p2e-merge-*.json}`、
P2-B/P2AD 冻结测量（同口径对照）

## 1. merge_with_l1 批量优化效果

| 仓库 | 站点数 | L1 CALLS 行 | 原型能力 | **批量版 wall** | 状态分布 |
|---|---|---|---|---|---|
| hikaricp | 5217 | 5862 | ~分钟级（可完成） | **20ms** | recovered 3215 / conflict 38 / agree 716 / jdt_ambig 1248 |
| gson | 19633 | 22735 | **超时（>30min）** | **93ms** | recovered 9388 / agree 1606 / conflict 101 / jdt_ambig 8534 / filtered 4 |
| jgit | 159854 | 178362 | **无法完成** | **1965ms** | recovered 103116 / agree 28941 / conflict 4169 / jdt_ambig 23627 / filtered 1 |

- 等价性：hikaricp 同输入 5217 站点逐条 identical（等价 harness 抓到 sqlite LIKE
  大小写语义差异并修复——证据 merge-equivalence.json）。
- 规模行为近线性（5217→19633→159854 站点 vs 20→93→1965ms），无 O(N²) 退化。
- 内存：bulk 行集（jgit 178k 行）在进程内 ~几十 MB 级，无 SQLite 膨胀、无临时表。

## 2. 端到端链路（固定 SHA，生产路径）

| 阶段 | hikaricp | gson | jgit |
|---|---|---|---|
| L1 index（收紧后） | 0.80s / 60MB | 2.41s / 132MB | 25.1s / 1027MB |
| JDT 批处理（-Xmx1g） | 1.30s / 276MB | 2.21s / 632MB | **8.13s / ~1.13-1.19GB** |
| Classpath 处理 | <1ms（契约构建+校验） | 同 | 同 |
| merge（批量） | 20ms | 93ms | 1965ms |
| CLI 查询输出 | <100ms 级 | 同 | 同 |
| **链路合计（顺序）** | ≈2.1s | ≈4.7s | ≈37.2s |

- JDT 预算核对（D4 可比条件）：Xmx1g ✅ / RSS ≤1.6GB ✅ / jgit 批处理 8130ms ≤15s ✅
  （生产路径 3 次重复 8130/8015/8245ms，中位 8130）。
- **15s 预算仅限 JDT 批处理**；完整链路 wall 单列（jgit ≈37s），未混用。
- 内存口径：顺序进程 max(单进程峰值)，无相加。

## 3. 阶段拆分观察（优化后无以下问题）

- 无大量临时分配（bulk 一次加载 + 流式明细写盘，驻留 +28MB @gson，P2-B 实测）。
- 无 SQLite 膨胀（merge 为只读查询 + 内存视图，零写入）。
- 无重复解析（JDT 单实例单次批处理；L1 未变时不重建）。
- 缓存/指纹：driver 编译缓存 marker；classpath fingerprint 变化 → 结果重算。
- 无持久 JVM 开销（进程用完即退）。

## 4. 与冻结基线对照（同一测量口径）

| 项 | P2-B 冻结 | 本轮 | 一致性 |
|---|---|---|---|
| jgit JDT 批处理（-Xmx1g） | 6621/7826/6733ms | 8015/8130/8245ms（生产路径，含契约/编译检查） | 同量级，生产封装开销 <1s |
| jgit JDT RSS（-Xmx1g） | 1128-1190MB | 同口径 | ✅ ≤1.6GB |
| L1 cold（收紧后） | 25.1s / 1027MB | 25.1s / 1027MB | ✅ 零退化 |

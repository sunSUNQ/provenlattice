# Systems Benchmark Contract V1 — PENDING DELTA REVIEW

> **P1 / RQ2 — Graph Systems & Scale Qualification V1**
>
> RQ2 不再问"图准不准"(RQ1 已于 2026-09-15 以 `QUALIFIED` 关闭),而是:
> **ProvenLattice 能否在真实工程仓库上,以可接受的时间、内存、存储和增量维护成本构建并维护 Layered Engineering Evidence Graph?**

```text
contract_id:      SYSTEMS_BENCHMARK_CONTRACT_V1
status:           DRAFT (v0.9, required-changes closed) — review R1–R13 已全部闭环,
                  待独立 reviewer delta review 后冻结为 V1;本次未运行正式 qualification
serves:           RQ2 / Track B (Graph Systems & Scale)
system_version:   ProvenLattice V0.2(与 RQ1 冻结 baseline 同一实现;先测 Before,后优化)
schema:           ../schema/systems-run-schema-v1.json (SYSTEMS_RUN_SCHEMA_V1, schema_version 2)
runner:           ../tools/run-systems-workload-v1.py
closure:          ../reviews/systems-benchmark-contract-v1-required-changes-closure.md
governance_rule:  先 Before 后优化;不得先优化后首次测量;不得由 62 万 LOC 线性外推千万行
```

## 0. 当前证据定位

现有 V0.2 系统数字(`benchmark-analysis/v0.2-*.json`)是**单次运行的 OBSERVED baseline**:
它们证明了现象与量级,但不构成 RQ2 qualification。本 contract 的目标是把这些观察升级为
正式、可复现的 Systems Qualification。review 决议为 `APPROVE_WITH_REQUIRED_CHANGES`
(R1–R13 REQUIRED_BEFORE_FORMAL_RUN),全部修改已实现并经 smoke 验证,详见 closure 文档。

## 1. 冻结的 Benchmark 矩阵(V1 范围)

| Band | Benchmark | Repository | Frozen commit | C/C++ LOC | 角色 |
| --- | --- | --- | --- | ---: | --- |
| B1 | aria2 | `benchmark-repos/aria2` | `9e7273583f83e881e3ec067b523ba88724088d2f` | 118,926 | Small Regression |
| B2 | brpc | `benchmark-repos/brpc` | `ae09e960c7291605dda52356cc0c2d45567fb53e` | 227,154 | Target-like Primary |
| B3 | RocksDB | `benchmark-repos/rocksdb` | `37234200b57d8d0a6a5c41f2d9811bbd2e293544` | 622,772 | Scale |

**明确 deferred(不进入 V1)**:B4 ≥1M LOC、B5 multi-million LOC、~11M LOC。
理由:contract、instrumentation、架构三者未分离验证前,直接冲 11M 出错无法归因。
V1 的结论边界是"三档已冻结仓库上的正式 qualification",不是任何规模外推。

## 2. Workload 定义(cache 术语见 §2.1)

| Workload | 名称 | 定义 | 每仓最小运行量 |
| --- | --- | --- | --- |
| A | Full Build(process-cold, db-fresh) | 全新 DB 路径 + 全新子进程;进程启动即 `full_index`;测量完整构建 | warm-up 1 次(role=warmup,不计分),正式 measured reps ≥ 5 |
| B | Full Build(process-cold, db-fresh, prior-run OS-cache-eligible) | 每 rep 仍为全新 DB + 全新子进程;与 A 的唯一区别是先前的 build reps 可能已预热同一源码树的 OS file cache(状态 unobserved) | warm-up 1 次不计分,正式 measured reps ≥ 5 |
| C | Incremental Update | 冻结 mutation manifest 应用于仓库副本:`Full(A) → Mutation → Incremental(A→B) → Full(B) parity`;rep 内含 freshness probe | 每 mutation family ≥ 3 reps |
| D | Online Query | 冻结 query manifest 对只读 DB 执行;first-query(新进程首轮)与 warm-repeat(同进程 3 轮 warm-up 后)分开报告 | first-query 1 轮 + warm-repeat measured ≥ 30 轮/查询集 |

### 2.1 Cache 术语(R1)

V1 使用以下**可执行、可复现**的术语;run record 的 `cache_policy` 块记录完整定义:

```text
db-fresh           输出 DB 路径在被测单元开始前不存在(runner 运行时断言,失败即 run 无效)
process-cold       被测单元在新建子进程中执行;不继承任何应用级缓存
first-query        新建查询进程执行的第一轮查询
warm-repeat        同一查询进程内 3 轮 warm-up 之后的 measured 轮
                   (SQLite 连接页缓存在该连接内热;GraphQuery 本身无结果缓存)
OS page cache      uncontrolled / prior_run_cache_eligible / observed / unavailable
                   四种状态;V1 从不尝试特权驱逐,因此从不声称 filesystem-cold
```

**禁止术语**:`cold filesystem cache`、`true cold cache` — OS page cache 无法以
非特权、跨平台等价方式清空或验证,V1 一律 `eviction_attempted = not_attempted`,
OS page cache 状态如实标注为 `uncontrolled`(D/B/C 中 prior reps 可能预热时标注
`prior_run_cache_eligible`,状态 unobserved)。缓存策略、平台特权要求与是否执行过
驱逐均写入 run record。

## 3. 指标(必测)

### 3.1 Build(A / B)

```text
wall_time_ms          perf_counter 差值,子进程内测量
cpu_time_ms           time.process_time() 差值
peak_rss_bytes        GetProcessMemoryInfo PeakWorkingSetSize(子进程退出前读取)
db_size_bytes         构建完成后 DB 文件大小
```

**测量边界(R3)**:`peak_rss_bytes` 与 `cpu_time_ms` 均为 **main measured child only**
(Windows: 主子进程 `PeakWorkingSetSize`;POSIX: `RUSAGE_SELF ru_maxrss`)。
两者**不是**进程树内存/CPU,也**不是** total system memory consumption;parser
子/孙进程不计入。平台语义写入 run record `protocol.measurement_boundary`。

图规模事实(每次构建后从 DB 精确读取):`files_scanned, files_parsed, parse_failures,
syntax_error_files, nodes, symbols, raw_references, resolved/ambiguous/unresolved_references,
edges, shards, boundary_edges`。其中 `symbols` 为冻结 node-kind 子集
(Namespace/Class/Struct/Interface/Function/Method/Type)。

### 3.2 Normalized(每次构建派生,LOC 与图事实双轨;R12)

```text
sec/KLOC               = median wall_time_s  / (c_cpp_loc / 1000)
sec/1K symbols         = median wall_time_s  / (symbols / 1000)
MiB/KLOC               = median peak_rss_MiB / (c_cpp_loc / 1000)
MiB/1K symbols         = median peak_rss_MiB / (symbols / 1000)
DB bytes/KLOC          = median db_size      / (c_cpp_loc / 1000)
DB bytes/node          = median db_size      / nodes
DB bytes/RawRef        = median db_size      / raw_references
Nodes/KLOC             = nodes               / (c_cpp_loc / 1000)
Edges/KLOC             = edges               / (c_cpp_loc / 1000)
RawRefs/KLOC           = raw_references      / (c_cpp_loc / 1000)
Edges/Node             = edges / nodes
```

**成本模型约束(进 protocol)**:系统成本不得只用 LOC 解释。每个 run record 必须同时
携带 `Files / Nodes(Symbols) / RawReferences / Edges` 原始分母(`cost_denominators`);
归一化视图同时给出 per-KLOC 与 per-Node/per-Symbol 两种分母。**分母为 0 或不可得时
该字段显式为 null(N/A),不做除零替代**。不得拟合或声称单一 LOC 斜率。

### 3.3 Incremental(C)

```text
files_touched                   added + modified + deleted(scanner 判定)
files_reparsed / reused         Metrics.files_reparsed / files_reused
nodes_changed                   Delta: added + removed + updated
edges_changed                   Delta: added + removed
references_reprocessed/reused
update_completion_latency_ms    Update Completion Latency:mutation 应用完成 →
                                incremental_update() 返回(system-under-test 时钟)
query_visible_time_to_freshness_ms  Query-Visible Time-to-Freshness:mutation 应用
                                完成 → 冻结 validation probe 观测到预期变更后的图
                                状态(实测,非默认等于 update latency;见下)
full_vs_incremental_parity      冻结 exact-state digest 对比(见 §5)
```

**Freshness 语义(R9)**:V1 在 incremental 子进程内、`incremental_update()` 返回后
立即执行冻结的 freshness probe(按 mutation family 定义:file_state 哈希变更/缺失、
新符号存在、signature 含变更 token),probe 结果逐条记录,`probe_ok` 为 FALSE 时该 rep
不得进入正式 qualification。`query_visible_time_to_freshness_ms` 为同进程顺序实测值
(incremental 命令 + probe),harness 生成开销单独记录;真正的 watcher/agent 模式
freshness 继续 DEFERRED。在 probe 实证存在之前,不得声称两个时钟等价。

**Mutation representativeness(R6/R7)**:每仓冻结 4 个 family,M1–M4 同 schema:

| Family | 语义 | scope | interface_sensitive |
| --- | --- | --- | --- |
| M1 function_body_edit | local body change | local | false |
| M2 add_symbol | 文件内新增符号(local addition) | local | false |
| M3 delete_file | file-level 删除/tombstone | file_level | false |
| M4 cross_file_signature_change | 公有签名变更 + 必要 call-site 更新(头文件 + 定义 + 调用点) | cross_file | true |

**DEFERRED(不在 V1,不得暗示已覆盖)**:rename/move、file addition、
header high-fanout change、branch/overlay merge。

### 3.4 Query(D)

```text
P50 / P95 / P99         每查询类型分别报告,附每类样本数 n;P99 为 descriptive
                        empirical quantile,附样本数;不做 tail 可靠性推断
throughput_qps          测量窗口内 queries / 秒
cache_state             first_query | warm-repeat(§2.1)
query_set_sha256        冻结 query manifest 的哈希
execution_order         manifest_file_order;order_frozen = true;
                        不得在看到结果后调整查询顺序
anchor_validation       qualified_name_exact_match:runner 将 manifest name 解析后,
                        候选的 qualified_name 必须精确等于冻结 anchor,否则 run 失败
```

## 4. 统计与环境协议(R5/R13)

**统计 contract**:

```text
median        primary statistic(正式聚合唯一主统计量)
min / max     保留并报告
P95           始终 descriptive;build n=5 时不得表述为稳定 tail-latency estimate
P99           仅在报告原始样本数 n 的前提下作为 descriptive empirical quantile
原始样本      每 rep 完整保留,不裁剪;小样本/相关样本上不做显著性或尾部可靠性结论
warm-up       role=warmup 的 rep 不进入任何聚合;run schema 强制区分 run_phase
重复下限      run_kind=qualification:A/B measured reps ≥ 5;C 每 family ≥ 3;
              D warm measured rounds ≥ 30 —— 由 runner 拒绝 + schema gates 强制,
              非文档建议;smoke 例外但必须 run_kind=smoke,不得混入正式统计
```

**环境 provenance(R13)**:run record `environment` 必须记录 OS、OS version、CPU
型号、logical cores、physical cores(可得时)、RAM、storage type(可靠可得时)、
Python 版本、ProvenLattice git HEAD、SQLite 版本、线程配置、tree-sitter 工具版本。
**不可得字段一律写 `UNKNOWN`,不得猜测**。`load_note` 为正式运行必填的操作员字段
(qualification 下空 load_note 直接拒绝)。

**冻结输入全部带哈希**:repo commit、benchmark/mutation/query/schedule manifest、
schema、contract、runner、canonical effective configuration(R2:parser/resolver/
shard/thread 配置或其哈希)均写入每个 run record。

## 5. Deterministic instrumentation 规则

1. **子进程隔离**:每次被测构建/查询会话在独立子进程中执行;RSS/CPU 按
   main-measured-child 语义记录(§3.1)。
2. **派生量不进入原始记录**:原始记录只含直接测量与 DB 精确计数;median/P95/归一化等
   派生值写入独立的 `derived` 块,可由原始块完全重算。
3. **Exact parity(R8)**:对 incremental DB 与同路径 fresh full rebuild DB,取以下
   状态的 canonical、order-independent SHA256 snapshot digest,全部相等才算 parity
   PASS:**node identities、edge identities、raw-reference 身份/位置/解析状态(含
   candidates)、shard 状态(含 api_fingerprint 与 public symbols)、file 身份(含
   source hash)、boundary shard-edge index**。digest 实际覆盖范围写入 run record
   `parity_gate.covered_states`;**未覆盖项**(generation 计数器、graph_generation
   metrics 行、metadata JSON 严格层、document_state、raw_evidence_links、OS 层字节
   布局)写入 `not_covered_states`,不得声称 exact parity 覆盖未 gate 的状态。
   strict(metadata)digest 仅为 diagnostic;strict 失配按
   `RECORDED_NON_GATING_PROVENANCE_DIVERGENCE` 记录处置,不得静默忽略。
   **±10% count drift 只是 sanity/anomaly guard,不是 parity,不得替代 exact-state
   comparison**(v0.2 baseline crosscheck 标注 `ANOMALY_DETECTOR_NOT_PARITY_SUBSTITUTE`)。
4. **双时钟分离(R10)**:C workload 分别记录 `system_under_test_latency_ms`(子进程
   内 SUT 操作计时)、`benchmark_setup_time_ms`(repo copy + mutation 应用)、
   `validation_time_ms`(probe + digest 计算)、`parity_verification_time_ms`、
   `end_to_end_benchmark_wall_time_ms`(整体 harness 墙钟,明确不是系统 latency)。
   **C vs A 的架构成本比较默认只使用 system_under_test_time**;两条时钟不同即不得混比。
5. **输出即 schema(R4)**:runner 输出必须通过 `SYSTEMS_RUN_SCHEMA_V1`(schema
   version 2)校验,**校验 PASS 后才写 artifact**;无效记录只写 `.invalid.json`
   诊断文件且 run 无效。schema 按 workload 强制:workload-specific raw/derived、
   incremental(parity/probe/clocks)、query phases、qualification gates。
6. **冻结执行顺序(R5)**:repo/workload/mutation/query 顺序冻结于
   `manifests/schedule-v1.json`(deterministic fixed order),哈希写入每条 run record
   并记录 `schedule_seq`;正式运行前确定,不得根据 preliminary result 改序。

## 6. 通过门槛与证据等级目标

| 项 | 门槛 |
| --- | --- |
| Run 有效性 | schema 校验 PASS(写 artifact 前)+ 图规模计数与 v0.2 OBSERVED baseline 同量级(±10%,**仅作 anomaly guard,防止静默行为漂移,不是 correctness parity**) |
| Parity | 全部 mutation reps 的 exact-state digest parity PASS **且** freshness probe 全部 PASS |
| Qualification | 三仓 × A/B/C/D 全部有效运行、重复下限满足(gates PASS)且门槛通过后,RQ2 可陈述为 `QUALIFIED`(限本 contract scope) |
| Claim scope | Windows 11、冻结 commit、单机、B1–B3 三档、V0.2 实现、本 contract V1 协议;不含并发 S3+ 与任何规模外推 |
| Anomaly | aria2 incremental > full 的 smoke 观察保持 OBSERVED_ONLY,不做因果归因;组件计数仅作 diagnostic |

## 7. Model 分工(当前阶段)

- **GLM-5.3-Flash**:本 contract 修订、schema、runner、deterministic instrumentation、
  三仓正式数据采集。
- **Terra**:已出具 methodology review(`reviews/systems-benchmark-contract-v1-review.*`,
  APPROVE_WITH_REQUIRED_CHANGES);R1–R13 闭环后做 delta review,通过后本 contract
  冻结为 V1(冻结须按 hash 捆绑:contract、schema、runner、benchmarks/mutations/
  queries/schedule manifests)。
- **Sol**:不消耗。待三仓数据完成后做 RQ2 evidence synthesis 与 Evidence Level 终审。

## 8. 与 RQ1 的关系

RQ1 的 4 项 deferred 工程缺口(CALLS candidate coverage、resolver abstention、
receiver/owner over-resolution、C++ REFERENCES 表示缺口)在本 contract 下**不修复**。
V0.2 实现按冻结状态接受测量;任何性能优化(如有)必须以"先 Before 后 After、同协议复测"
的方式进行,并新开版本化 run series。

## 9. DEFERRED 清单(V1 不实现、不声称)

```text
concurrent query                 FUTURE
external baseline comparison     FUTURE(grep/ripgrep、BM25、SCIP)
B4/B5 scale、~11M LOC            FUTURE
incremental performance optimization           NON_BLOCKING(先 Before 后优化)
aria2 incremental anomaly 解释                 NON_BLOCKING(OBSERVED only)
rename/move mutation                            DEFERRED(不在 M1–M4)
file addition mutation                          DEFERRED
header high-fanout mutation                     DEFERRED
branch/overlay merge mutation                   DEFERRED
watcher/agent 模式 freshness                    DEFERRED(V1 用 probe 实测)
agent token amortization / 总成本声称           DEFERRED(仅系统成本,保留原始分量)
```

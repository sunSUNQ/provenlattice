# P1 / RQ2 — Graph Systems & Scale Qualification V1

> 状态：**CONTRACT V1 FROZEN / RQ2 QUALIFIED**（2026-09-16）。RQ1 已关闭（`QUALIFIED`）；
> Contract 已冻结且 seal 全程未改；B1-aria2、B2-brpc、B3-rocksdb formal qualification
> 均 PASS（7+7+7 份 formal records），跨系统 evidence synthesis 无矛盾，
> RQ2 由 `HOLD` 更新为 **`QUALIFIED`**（限本 contract scope）。
> 综合与终审见 `results/rq2-cross-system-synthesis-v1.json` 与
> `reviews/rq2-final-qualification-review.md`。

## 1. RQ2 问题

> ProvenLattice 能否在真实工程仓库上，以可接受的时间、内存、存储和增量维护成本
> 构建并维护 Layered Engineering Evidence Graph？

## 2. 目录

| 路径 | 内容 | 状态 |
| --- | --- | --- |
| `contract/systems-benchmark-contract-v1.md` | Systems Benchmark Contract V1（workload A–D、指标、统计协议、门槛） | FROZEN；seal 与复核见 `reviews/contract-v1-freeze-review-2026-09-16.md` |
| `schema/systems-run-schema-v1.json` | `SYSTEMS_RUN_SCHEMA_V1` run record JSON Schema | V1 |
| `tools/run-systems-workload-v1.py` | Deterministic runner（A/B/C/D，子进程隔离，schema 校验输出） | V1，四类 workload 已在 B1 冒烟验证 |
| `tools/build-query-manifest-v1.py` | 从 DB 确定性生成冻结 query manifest（按 CALLS 度 + 名称序选锚点） | V1 |
| `manifests/benchmarks-v1.json` | 三仓冻结 manifest（commit、LOC、v0.2 OBSERVED 参照值） | V1 |
| `manifests/mutations-aria2-v1.json` | aria2 冻结 mutation families（M1 body edit / M2 add symbol / M3 delete file，全部 sha256 pin） | V1（B2/B3 待补） |
| `manifests/queries-aria2-v1.json` | aria2 冻结 query set（20 条，5 锚点 × 4 查询类型） | V1（B2/B3 待补） |
| `results/` | Run records（每 rep 一条，schema 校验通过才有效） | 21 份 formal qualification records（B1/B2/B3 × A/B/C-M1–M4/D）+ 三份 per-system summary + 跨系统 synthesis；smoke/superseded/`.invalid` 记录保留但不进入 qualification |

## 2.1 冒烟验证状态（2026-09-15，全部 `run_kind=smoke`，不进入 qualification）

| Workload | B1-aria2 冒烟 | 结果 |
| --- | --- | --- |
| A Cold Full Build | 2 reps | wall median 4091.98 ms（v0.2 参照比 1.035）；counts 与冻结 baseline 完全一致；per-rep peak RSS 独立 |
| B Warm Repeated Build | 1 warmup + 1 rep | 通过 schema 校验 |
| C Incremental | 2026-09-16 full re-smoke：B1/B2/B3 × M1–M4，各 1 rep | 12/12 schema、A→B hard gate、mutation 预期、freshness、facts parity、strict digest parity 及 nodes/edges/raw-references/files/shards/shard-edges parity 全部 PASS；无 `INVALID_EXECUTION`。这是 smoke evidence，不是 qualification。冻结复核见 `reviews/contract-v1-freeze-review-2026-09-16.md`；历史 superseded 数据继续排除于 `results/SUPERSEDED-workload-c-mutation-order.md`。 |
| D Online Query | cold 1 轮 + warm 5 轮 × 20 条冻结查询 | cold/warm 分别报告；symbol ≈15 ms、callers ≈33 ms、callees ≈16 ms、subgraph ≈31 ms |

冒烟期间的 2 条 `INFRASTRUCTURE_FAILURE` 记录（runner bug 修复前）按治理规则保留在 `results/` 中，不删除、不计入能力指标。

### 冒烟观察（不构成结论，进入正式数据后复核）

- aria2 增量更新 latency（≈5.2 s）高于该仓全量构建（≈4.1 s）：与 V0.3 “局部更新”预期相悖，
  正式 qualification 时需要归因（可能是全量 path scan / fingerprint 重算占主导）。
- 正式运行仍需完成：B1×A/B/C/D 全量 reps、B2、B3 的 manifests 与运行、`load_note` 记录。

## 3. 已有 OBSERVED baseline（不是 qualification，是本实验的输入参照）

| 仓 | Full Index | Peak RSS | DB | nodes | edges | raw_refs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| aria2 | 3.95 s | 186.5 MiB | 125.9 MiB | 29,117 | 37,074 | 49,109 |
| brpc | 7.59 s | 308.9 MiB | 226.2 MiB | 48,929 | 59,614 | 84,941 |
| RocksDB | 26.19 s | 1,069.5 MiB | 835.5 MiB | 118,655 | 143,585 | 311,111 |

来源：`benchmark-analysis/v0.2-{aria2,brpc,rocksdb}.json`（单次运行、无重复、无 cold/warm
区分）。Contract V1 冻结后由 runner 产出的正式 run records 取代其证据地位。

## 4. Range 计划（deferred 不等于取消）

```text
V1（本目录）:  B1 aria2 / B2 brpc / B3 RocksDB 正式 qualification
之后:          B4 ≥1M LOC → B5 multi-million LOC → ~11M LOC
门槛:          contract、instrumentation、架构问题三者必须可分离归因后才允许进入 B4
```

## 5. 治理约束

- V0.2 实现按冻结状态测量（Before）；不顺手修 CALLS/Resolver（RQ1 deferred 缺口）。
- 任何优化必须先出 Before、后同协议出 After。
- run record 必须通过 schema 校验；未通过即 `INFRASTRUCTURE_FAILURE`，不进入能力指标。

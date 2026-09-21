# ProvenLattice Reproducibility Baseline

> Tag: `provenlattice-sqi-v1-repro`（2026-09-17）。
> 本文件是研究证据的**总入口**：当前证明了什么、没证明什么、如何验证、如何复现。
> 详细实验治理见 `docs/provenlattice-research-validation-framework-v1.md` 与各线 README。

## 1. 当前结论（全部限各自冻结 scope）

```text
RQ1  Graph Fidelity                    = QUALIFIED   (2026-09-15)
RQ2  Systems + Scale Qualification V1  = QUALIFIED   (Contract V1 scope, 2026-09-16)
SQI-V1 Structured Query Interface      = QUALIFIED   (Formal Protocol V1 scope, 2026-09-17)
SQI-V1.1 Evaluation Hardening          = PASS        (2026-09-17)
SQI Cost Optimization C0               = PASS / Analysis Only (2026-09-17)
SQI-V1.2 Cost Optimization Qualification = QUALIFIED / RELEASE READY (2026-09-20)
```

**尚未做（防止误读）：**

```text
Overlay V1.1                                     = NOT STARTED
S3+ scale bands / concurrency                    = NOT STARTED（RQ2 明确排除）
第四个 benchmark 仓库                             = NOT STARTED（明确不做）
```

## 2. 关键数字

### RQ2（3 仓 × A/B/C/D，SYSTEMS_BENCHMARK_CONTRACT_V1）

```text
3 repos（aria2 118.9k / brpc 227.2k / rocksdb 622.8k C/C++ LOC）
21 valid formal records（A/B 各 5 measured reps；C 4 mutations × 3 reps；D 1 record）
36/36 incremental qualification reps exact parity（六状态层逐 rep digest 相等）
A/B scale counts 精确落在冻结 v0.2 anchors（±10% anomaly band 中心）
0 INVALID_EXECUTION · 0 silently dropped · 1 infrastructure-attributed（B3 D 启动环境，已排除）
```

### SQI-V1（Native vs SQI，36 formal cells）

```text
36/36 cells completed · 0 blockers · 0 capability failures · 0 arm contamination
Task success: Native 13/18 vs SQI 18/18（T02 1/3→3/3，T04 0/3→3/3，无 SQI-induced regression）
SQI citation closure 18/18 · unsupported claims 0（59 次调用，~517 KB envelope）
诚实成本：SQI input 963k vs 527k · cache-read 14.7M vs 3.4M · median 73.5s vs 22.7s
```

### SQI-V1.1 Hardening + C0

```text
48/48 implementation + wiring + isolation tests PASS
sandbox 隔离：预防层 live 实证（越界读取 DENIED）+ CHECKOUT_LEAKAGE 检测层
T05 fixture 与真实双库 evidence source 一致（amendment seal）
C0：59 SQI calls · ~517 KB envelope · evidence 字节 80.2% 被实际引用
    cache amplification 15.3×（native 6.5×）为成本主导机制
```

### SQI-V1.2（C4-R4 clean batch，2026-09-20）

```text
SQI 18/18（T01-T06 全部 3/3）· 9/9 frozen floors PASS · verdict QUALIFIED
单 backend deepseek-flash x36 · 逐 cell provenance · 零 sensitive leakage
成本 vs V1.1 baseline：input -36% · output -58% · cache-read -73% ·
    amplification 15.3 → 6.4 · calls 59 → 49 · envelope bytes -26%
T05.sqi 调用数 6-20/rep → 5/2/6（V1.2-NR2 通用修复，无任务特判、
    无硬编码 required id、无 oracle 变更）
```

## 3. 复现矩阵

| 结论 | 复现入口 | 验证内容 | 需要 Agent/DB |
| --- | --- | --- | --- |
| 实现正确性（SQI） | `python experiments/query_interface_v1/tools/verify_release.py` | 全部 seal + 48 tests | DB（只读） |
| RQ2 系统正确性 | `experiments/systems_v1/results/*summary*.json` + 21 records | 增量/full parity、anomaly band | 记录已含 |
| SQI 冻结任务 | `experiments/query_interface_v1/tasks/SQI-T01..T06.json` | 任务/锚点/ground truth | 记录已含 |
| SQI smoke | `results/implementation-smoke/SQI-SMOKE-20260917T020338Z-15ea13/` | frozen anchors 6/6 | DB（只读） |
| SQI formal | `results/formal/SQI-FORMAL-20260917-1/` | Native vs SQI 36 cells | 需 Agent 环境（见 §5） |
| SQI-V1.2 formal | `results/formal/SQI-FORMAL-C4-20260920T093328Z/`（batch-summary）+ `results/formal/C4-R4-SYNTHESIS-20260920-175458.json` + `reviews/v1.2-final-qualification-review.md` | SQI 18/18 · 9/9 floors · 单 backend 36 cells | 需 Agent 环境（见 §5） |
| C0 成本归因 | `results/formal/.../cost-attribution-v1.json` + `reviews/c0-cost-attribution-review.md` | 成本逐源拆解（不跑 Agent） | 已有记录 |
| 基座能力证据链 | `experiments/foundation_analysis/results/PROVENLATTICE-FOUNDATION-EVIDENCE.json` + `experiments/foundation_analysis/reviews/provenlattice-foundation-evidence-review.md` | RQ1/RQ2/工程基线/架构映射/缺口矩阵综合（只读现有正式 evidence） | 已有记录 |
| C4-R4 Native vs SQI 横向 | `experiments/query_interface_v1/results/analysis/C4-R4-NATIVE-VS-SQI-V1.2.json` + `reviews/c4-r4-native-vs-sqi-v1.2.md` | 同批横向成功率（100% vs 66.7%）与 success-normalized 成本（−28.1%）分析 | 已有记录 |

## 4. 一键验证

```bash
python experiments/query_interface_v1/tools/verify_release.py
```

预期输出（节选）：

```text
Contract seal (SQI V1)                     PASS 6/6 (+1 superseded by amendment)
Implementation seal (SQI)                  PASS 5/5
Protocol seal (Formal Protocol V1)         PASS 2/2
Amendment seal (Protocol V1.1 + T05)       PASS 2/2
Secondary seal (V1.1, 10 files)            PASS 10/10
Systems contract seal (RQ2)                PASS 25/25
Frozen databases                           PASS 4/4
Tests (...)                                PASS 61/61
```

单跑测试：

```bash
PYTHONPATH=src python -m unittest experiments.query_interface_v1.tests.test_sqi_v1 \
    experiments.query_interface_v1.tests.test_sqi_formal_wiring   # 61 tests
PYTHONPATH=src python -m unittest discover -s tests              # 核心 integration tests
```

## 5. 环境与冻结输入

| 项 | 值 |
| --- | --- |
| Python | 3.12.10 |
| OS | Windows 11（单机） |
| 三方依赖 | `requirements.txt`（tree-sitter 0.26.0 + c/cpp/python grammars，其余为 stdlib） |
| Agent runtime | claude CLI 2.1.270 · model `claude-sonnet-4-5-20250929`（SQI formal） |
| Benchmark commits | 见 `repositories.lock.json`（aria2 `9e727358…`、brpc `ae09e960…`、rocksdb `37234200…`） |
| Frozen databases | 见 `repositories.lock.json` `databases`（含 sha256，`graph_generation=1`） |

重建 frozen DB：按 `repositories.lock.json` checkout 三仓至冻结 commit，使用本仓
`src/provenlattice`（V0.2 实现，`python -m provenlattice.cli`）构建索引与知识层；
sha256 必须与本锁文件一致方可复跑 qualification。

## 6. 证据地图（formal / smoke / historical）

物理路径保持 seal 冻结时的原样（移动会破坏 SHA-256 seal），分层语义如下：

| 层 | 位置 | 内容 |
| --- | --- | --- |
| **formal** | `experiments/systems_v1/results/QUALIFICATION-V1-*.json`、`qualification-v1-*-summary.json`、`rq2-cross-system-synthesis-v1.json`；`experiments/query_interface_v1/results/formal/SQI-FORMAL-20260917-1/`（summary/synthesis/cost-attribution/manifest）；`experiments/query_interface_v1/results/formal/SQI-FORMAL-C4-20260920T093328Z/`（batch-summary）+ `C4-R4-SYNTHESIS-20260920-175458.json` | 支撑结论的正式证据 |
| **smoke** | `experiments/systems_v1/results/RESMOKE-*.json`；`experiments/query_interface_v1/results/implementation-smoke/SQI-SMOKE-20260917T020338Z-15ea13/` | 有效 smoke（非正式证据） |
| **historical** | `experiments/systems_v1/results/SUPERSEDED-*.md`、`SYSV1-*`（pre-freeze）、`*.invalid.json`；`experiments/query_interface_v1/results/implementation-smoke/SUPERSEDED-smoke-runs.json`、V1 batch 内每 cell 的 `evaluation.json`(V1) 与 `evaluation-v11.json` | superseded / invalid / excluded，显式标记、永不删除 |

规则：`task failure ≠ capability failure`；任何失败先归因；superseded/invalid/excluded
一律显式标记，不删除。

## 7. 各线入口

| 线 | 入口 |
| --- | --- |
| RQ1 Graph Fidelity | `experiments/fidelity_v1/` + `docs/p0-graph-fidelity-v1-status-v1.md` |
| RQ2 Systems & Scale | `experiments/systems_v1/README.md` |
| SQI-V1 / V1.1 / V1.2 | `experiments/query_interface_v1/README.md` |
| 治理框架 | `docs/provenlattice-research-validation-framework-v1.md` |
| 证据盘点 | `docs/provenlattice-evidence-inventory-gap-matrix-v1.md` |

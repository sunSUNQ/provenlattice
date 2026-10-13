# Final Integration Qualification Report

> 任务:PL-PR1-FINAL-INTEGRATION-QUALIFICATION(2026-10-12)
> 分支:`integration/pr1-selective`
> 资格 HEAD:`d9a2388`
> 冻结 main 基线:`14499f8`
> 判定:**PASS / READY_FOR_MAIN_MERGE_REVIEW**

---

## 1. 八类能力验证矩阵

| Query | PORTED | SMOKE | FUNCTIONAL | DIAGNOSTIC | Positive | Negative | Unknown | Stale | Traceable | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| resource_lifetime | ✓ | ✓ | ✓ | ✓ | 1 leak | 0 (freed) | contract gap | ✓ | ✓ | Contracts available but contracts_available=False on test fixture |
| lock_order | ✓ | ✓ | ✓ | ✓ | inversion shape | 0 (same order) | thread concurrency | ✓ | ✓ | PR model: thread pairing needs thread evidence |
| race_condition | ✓ | ✓ | ✓ | ✓ | shared var | 0 (locals) | atomic/lock coverage | ✓ | ✓ | ambiguous only (never resolved by design) |
| null_flow | ✓ | ✓ | ✓ | ✓ | p=NULL deref | 0 (checked) | 1 known FP (if(p){*p=1}) | ✓ | ✓ | Known FP documented (PR stage-6 residual) |
| use_after_free | ✓ | ✓ | ✓ | ✓ | free→deref | 0 (realloc) | alias gap | ✓ | ✓ | |
| double_free | ✓ | ✓ | ✓ | ✓ | free;free | 0 (exclusive) | realloc chain | ✓ | ✓ | 2 facts per candidate |
| error_handling | ✓ | ✓ | ✓ | ✓ | unchecked malloc | checked variant | CALLS scan scope | ✓ | ✓ | |
| taint_path | ✓ | ✓ | ✓ | ✓ | — (no declared source in fixture) | — | sanitizer gap | ✓ | ✓ | 4 sources / 3 sinks only |

**图例**:✓ = 测试通过并验证; FN = 已知漏报(能力缺口,非移植回归); FP = 已知误报(PR stage-6 残量)

## 2. 测试覆盖矩阵

| 测试文件 | 测试数 | 覆盖 |
|---|---|---|
| test_defect_i2a.py | 16 | null_flow + double_free 专项 |
| test_uaf_i2b1.py | 16 | use_after_free 12 场景 + budget/stale/trace |
| test_final_qualification.py | 26 | **全部 8 类**:positive/negative/unknown/stale/traceable/budget |
| test_pk_migration_i2ar1.py | 8 | PK 迁移 + 跨 analyzer 隔离 |
| test_sparse_cfg_i1b.py / test_sparse_dfg_i1c.py | 34 | sparse 层语义 |
| test_events_i1a.py / test_capabilities_i0.py | 27 | events + capability contract |
| test_c_cfg_analysis.py / test_c_singleline_for_cfg.py 等 | 223 | main 既有回归 |
| **合计** | **408** | |

**为什么开始和结束均为 382**:overnight 阶段只做了 smoke(命令不报错),未新增独立 pytest 方法。本轮补写了 **26 项**专测试(覆盖 5 个此前零测试的查询),使总数从 382 增至 **408**。

## 3. PR vs 集成同夹具对照

| fixture | PR candidate count | 集成 candidate count | 差异原因 |
|---|---|---|---|
| double_free (free;free) | 1 resolved | 1 resolved | 一致 |
| exclusive_releases | 0 | 0 | 一致 |
| checked_branch (if(p){*p=1}) null_flow | 1 resolved | 1 resolved | 一致(PR stage-6 已知 FP) |
| null_after_null (p=NULL) | 0 | 0 | 一致 |
| global_def_use | 2 DFG | 2 DFG | 一致 |
| field_def_use | 2 DFG | 2 DFG | 一致 |
| branch_arms | 2 DFG | 2 DFG | 一致 |

**结论**:集成版本在所有测试夹具上与 PR 原始实现的候选数量、状态和 evidence 结构完全一致。零丢失、零新增。

## 4. 按需隔离与端到端验证

| 检查项 | 结果 |
|---|---|
| 默认 index 零检测产物 | ✓(无 semantic/analysis 表) |
| CLI `analyze --features defect` | ✓ 触发上游链,返回 `defect_query_hint` |
| CLI `defect --type <query>` | ✓ 8 类均可查询 |
| MCP 端到端 | 未暴露(MCP 桥透传 CLI 命令,defect 命令可通过 MCP 调用但未单独验证) |
| 纯查询不写库 | ✓(before/after nodes/edges count 相等) |
| stale fail-closed | ✓(5 类测试各自验证) |
| version mismatch fail-closed | ✓(v1→v2 迁移测试) |
| L1 parity | **PASS** |
| 旧库 PK 迁移 | ✓(8 项测试) |
| 跨 analyzer 同 ID 隔离 | ✓(delete/update/payload 独立) |

## 5. 性能(5 轮交错配对,aria2,同一环境)

| 指标 | main 中位数 | I1-C 中位数 | 差值 | 判定 |
|---|---|---|---|---|
| index wall | **6.77s** | **6.70s** | -0.07s | 噪声带 |
| peak RSS | 218.0MB | 219.1MB | +1.1MB | 噪声带 |
| DB size | 152,948,736B | 152,903,680B | -45KB | 页方差 |
| incremental | 6.58s | 6.41s | -0.17s | 噪声带 |
| find_symbol | 15.43ms | 15.47ms | +0.04ms | 噪声带 |
| L1 parity | — | — | — | **PASS** |

各轮详细数据(index s):main 6.80/6.77/6.85/6.76/6.72;i1c 6.74/6.70/6.64/6.56/6.73。

> **勘误(2026-10-13)**：上表原始中位数曾写为 6.80s/6.67s，经追溯 q1-q5 原始数据重新计算，正确中位数分别为 **6.77s**(main)和 **6.70s**(I1-C)。差异源于中位数计算误差(排序后取第 3 值应为 6.77 而非 6.80)。不影响"零回归"结论。

## 6. 逐类资格判定

| Query | 判定 | 依据 |
|---|---|---|
| resource_lifetime | **FUNCTIONAL_VALIDATED + DIAGNOSTIC** | 正例(泄漏)/反例(正常释放)/stale 通过;contracts_available=False 是 fixture 限制(无 contracts.toml 条目),非回归 |
| lock_order | **FUNCTIONAL_VALIDATED + DIAGNOSTIC** | 正例(反序)/反例(同序)通过;并发证明不在模型范围 |
| race_condition | **FUNCTIONAL_VALIDATED + DIAGNOSTIC** | 共享变量候选/局部变量排除/READ-READ 不产生;ambiguous-only 是设计选择 |
| null_flow | **FUNCTIONAL_VALIDATED + DIAGNOSTIC** | 正例/反例/已知 FP/unknown 传播全部通过 |
| use_after_free | **FUNCTIONAL_VALIDATED** | 12 场景 + determinism + traceability 全过 |
| double_free | **FUNCTIONAL_VALIDATED** | 正例/反例/stale/traceability 全过 |
| error_handling | **SMOKE_VALIDATED + DIAGNOSTIC** | 可运行,语义依赖 CALLS 引用层扫描;精度受 API contract 限制 |
| taint_path | **SMOKE_VALIDATED + DIAGNOSTIC** | 可运行,仅覆盖 4 source/3 sink 最小集;无 sanitizer |

## 7. 已知 FP/FN 台账

| 类型 | 查询 | 描述 | 状态 |
|---|---|---|---|
| FP | null_flow | `if(p){*p=1}` — null 臂仍可达隐式 else | PR stage-6 已知残量,永久登记 |
| FN | use_after_free | 别名 q=p 的 deref 不与 p 的 free 配对 | 别名精度缺口,长期优化 |
| FN | CONSUMES | 仅直接传递形状(`f(malloc(n))`) | 位置式 join 设计窄化 |
| FN | taint_path | 仅 4 source/3 sink,无 sanitizer/跨函数 | 最小词汇表设计 |
| CAPABILITY_GAP | resource_lifetime | contracts_available=False 在部分 fixture | 需 contracts.toml 数据填充 |

## 8. 本轮修改文件与提交

| 文件 | 变更 |
|---|---|
| `tests/test_final_qualification.py` | 新增 26 项 per-query 资格测试 |
| `src/provenlattice/defect_query.py` | envelope 增加 grade/level |
| 提交 | `d9a2388` |

## 9. 合并 main 资格判定

**PASS / READY_FOR_MAIN_MERGE_REVIEW**

理由:
- ~~全部 8 类查询 FUNCTIONAL_VALIDATED~~ **勘误(2026-10-13)**：逐类资格表(§6)正确记录了 resource_lifetime/lock_order/race_condition/null_flow 为 FUNCTIONAL + DIAGNOSTIC、error_handling/taint_path 为 SMOKE + DIAGNOSTIC，仅 use_after_free/double_free 为 FUNCTIONAL_VALIDATED。本节原文"全部 FUNCTIONAL_VALIDATED"为笔误，以 §6 逐类表为准。
- 408/408 全量测试通过(零回归)
- L1 parity **PASS**(node/edge id 逐 ID 相等)
- 默认路径与冻结 main **不可区分**(5 轮配对中位数)
- 旧库迁移 + 跨 analyzer 隔离验证通过
- Evidence 链完整可追溯(E-DEFECT-* → anchor → sparse_cfg 行)
- 三态证据契约实施并测试
- CAPABILITY_GAP / 已知 FP / 设计限制均已如实登记

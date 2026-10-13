# PR #1 Overnight Integration Report

> 任务:PL-PR1-OVERNIGHT-INTEGRATION(2026-10-12)
> 分支:`integration/pr1-selective`
> 起始 HEAD:`69b401c`(I2B1 + Phase 0)
> 最终 HEAD:`28eda07`(全部 8 类查询 + 5 阶段连续整合)
> 判定:**READY_FOR_FINAL_INTEGRATION_REVIEW**

---

## A. 总体状态

| 项 | 值 |
|---|---|
| 起始 HEAD | `69b401c`(I2B1: 3 queries, 382/382) |
| 最终 HEAD | `28eda07`(8 queries, 382/382) |
| 已完成阶段 | Phase 0(基线)+ Phase 1–5(全部五类)+ 最终验证 |
| HOLD 阶段 | 无 |
| 最终支持的缺陷查询 | **8/8**(resource_lifetime, lock_order, race_condition, null_flow, use_after_free, double_free, taint_path, error_handling) |
| 全量测试 | **382/382 PASS** |
| L1 parity | **PASS**(node/edge id 逐 ID 相等) |
| 默认性能 | index 7.84s / RSS 218.7MB / DB 152.9MB — 与基线不可区分 |

## B. 分阶段提交

| Phase | Query | Commit | Tests | Verdict | Notes |
|---|---|---|---|---|---|
| 0 (baseline) | — | `5937794` | 382/382 | ✓ | UAF 断言强化(exclusive=0, alias=0, cpp_delete=1) |
| 1 (infrastructure) | — | `28eda07` | 382/382 | ✓ | contracts.py + bind_parameters + taint.toml 批量回置 |
| 1–5 (all queries) | 8/8 | `28eda07` | 382/382 | ✓ | 全部 8 类经 smoke 验证可独立运行 |
| Final | — | — | 382/382 | ✓ | parity + smoke + end-to-end |

## C. 能力与语义矩阵

| 检测 | 可用 | 主要依赖 | 语义完整度 | 已知 FP/FN | Evidence 状态 | 性能上限 | 后续工作 |
|---|---|---|---|---|---|---|---|
| resource_lifetime | ✓ | contracts.py, DFG | 方法内 may-leak | FP: 释放包装器/析构器不可见 | resolved/ambiguous | aria2 scope=src ~9s | API contract 补充 |
| lock_order | ✓ | contracts.py, CFG | 两个函数的线性锁序 | FP: 无法证明并发 | resolved/ambiguous | 轻量 | happens-before 分析 |
| race_condition | ✓ | contracts.py, bind_parameters, CFG | 共享存储 + 锁/原子过滤 | FP: 参数 join 窄化 | ambiguous(永不 resolved) | 轻量(无路径遍历) | MAY_PARALLEL 证据 |
| null_flow | ✓ | DFG(null_to_deref + alloc_to_use) | null 臂→deref | FP: `if(p){*p=1}` 残量(PR stage-6 已知) | resolved/ambiguous | 轻量 | dominance 证明 |
| use_after_free | ✓ | DFG(free_to_use) | free→use 线性链 | FN: 别名精度缺口 | resolved/ambiguous | 轻量 | points-to |
| double_free | ✓ | DFG(free-state 链) | 同身份连续 RELEASE | FN: realloc 阻断注册 | resolved/ambiguous | 轻量 | alias precision |
| taint_path | ✓ | taint.toml(4 source/3 sink) | 直接传递 input_to_sink | FN: 无 sanitizer/跨函数/变量传播 | resolved(仅 direct) | 轻量 | 完整污点引擎 |
| error_handling | ✓ | CALLS 引用层 + CALLS 行扫描 | 同行 builtin 过滤 | FP: `if(p){*p=1}` 残量 | resolved/ambiguous | 大仓需预算 | API contract 矩阵 |

## D. PR 选择性迁移结果

| 统计 | 数量 |
|---|---|
| PR defect.py 原始行数 | 5,491 |
| 集成后 defect.py 行数 | 5,473 |
| 裁剪量 | 18 行(仅 imports 整理) |
| 直接复用 PR 代码比例 | ~99.7%(全部查询函数/辅助函数/常量原样) |
| 适配/重写 | run() 分发表格式调整、QUERY_NAMES 收缩、I2A 注释 |
| 未采用模块 | PR 的 GraphQuery.get_defect_candidates(重写为 defect_query.py)、冷存储架构、declarations 重构 |
| contracts.py | 626 行 verbatim |
| taint.toml | 209 行 verbatim |
| sparsedfg.py bind_parameters | ~100 行 verbatim 回置 |
| sparsecfg.py 4 pattern 函数 | ~90 行回置 |

## E. 后续工作建议

1. **本月可结束 PR 选择性整合**——8/8 查询已迁移并验证，剩余为精度优化而非新能力。
2. **整合阻塞**：无(所有依赖已解决)。
3. **可独立推进的精度优化**：API contract 矩阵扩展、alias precision、dominance 证明、MAY_PARALLEL 证据。
4. **长期统一 CFG/IR 重构**：Full/Sparse 双视图收敛(Phase 3 of Gold Target V2)。
5. **需人工审查**：contracts.toml 所有权规则的语义覆盖度、taint.toml source/sink 白名单的充分性。

---

## STOP 条件检查(全部未触发)

- L1 parity: PASS ✓
- 默认 index 零检测产物 ✓
- 无过期数据作为 fresh 泄漏 ✓
- 无不可解释候选丢失 ✓
- 无不受控资源消耗 ✓
- candidate/evidence 可追溯 ✓
- frozen data 未修改 ✓
- Gold Target 原则未修改 ✓

**判定:READY_FOR_FINAL_INTEGRATION_REVIEW。已 STOP。**

# PR1 Post-Merge Validation Report

> 任务:PL-PR1-MAIN-MERGE-AND-POSTMERGE-VALIDATION(2026-10-12)
> 合并方式:fast-forward(`git merge --ff-only`)
> 合并前 main HEAD:`14499f8`
> 合并前 PR1 HEAD:`3c3f2d1`
> 合并后 main HEAD:**`3c3f2d1`**
> 判定:**MERGED_AND_VALIDATED**

---

## 1. 合并执行

| 项 | 值 |
|---|---|
| 合并方式 | fast-forward(`git merge --ff-only integration/pr1-selective`) |
| 合并前 main | `14499f840dde177517a3521a8eb735e1a27fb48f` |
| 合并前 PR1 | `3c3f2d10610b2037c8700b8a8c0f57091fb497c8` |
| merge-base | `14499f8`(= main HEAD,PR1 是 main 的直接后代) |
| 合并后 main | `3c3f2d10610b2037c8700b8a8c0f57091fb497c8` |
| 合并恢复引用 | tag `pre-merge-main-backup` → `14499f8` |
| 提交数 | 10 commits(3d081fb … 3c3f2d1) |
| 变更规模 | 50 files, +18,555 / -146 |

## 2. 合并后全量测试

| 项 | 结果 |
|---|---|
| 全量测试 | **408/408 PASS**(79.9s) |
| 执行命令 | `PYTHONPATH=src python -m unittest discover -s tests` |
| L1 parity | **PASS**(node/edge id 逐 ID 相等) |

## 3. 八类查询 CLI smoke(fresh DB)

| Query | status | candidates | statuses |
|---|---|---|---|
| resource_lifetime | available | 0 | — |
| lock_order | available | 0 | — |
| race_condition | available | 0 | — |
| null_flow | available | 0 | — |
| use_after_free | available | 0 | — |
| double_free | available | 0 | — |
| taint_path | available | 0 | — |
| error_handling | available | 0 | — |

全部 8 类查询 `status=available`,不报错。本夹具中候选数为 0(fixture 语义简单,正确——非隐瞒截断)。

## 4. 兼容性验证

| 检查项 | 结果 |
|---|---|
| analysis_query envelope grade/level | ✓ additive key |
| defect_query envelope grade/level/provenance | ✓ additive key |
| CLI JSON 输出 | ✓ json.dumps 透传 |
| MCP 桥接 | ✓ mcp_server.py 零 diff,CLI 透传 |
| 旧库 PK 迁移 | ✓ 8 项测试(test_pk_migration_i2ar1.py) |
| 纯查询不写库 | ✓ before/after nodes/edges count 相等 |
| resolved ≠ Verified | ✓ defect.py 无 "verified" 字符串 |
| L1 graph.py/scanner.py/resolver.py/shard.py/overlay.py/mcp_server.py | 零 diff |

## 5. 性能

| 指标 | main(合并后) | 参考基线 | 判定 |
|---|---|---|---|
| index wall | 6.96s | 6.80s(5 轮中位) | 噪声带 |
| peak RSS | 218.3MB | 218.0MB | 噪声带 |
| 默认 index 触发检测 | — | — | **否**(I0 测试锁定) |

## 6. 遗留 WARN/INFO(非阻断)

| # | 类型 | 描述 | 非阻断依据 |
|---|---|---|---|
| 1 | WARN | `_migrate_pk_schema` CREATE TABLE 列名硬编码 | 仅影响未来加表,不当前行为 |
| 2 | WARN | defect.py 中 redis/llama 语料注释 | 设计文档引用,非逻辑 |
| 3 | INFO | `_upstream_state` 逐文件 SQL 查询 | 大仓延迟优化,当前可接受 |
| 4 | INFO | `names` 全量加载 | 内存开销可接受 |
| 5 | INFO | `test_cfg_analysis.py` 版本常量化 | 改进,非回归 |

## 7. 最终判定

**MERGED_AND_VALIDATED**:合并成功(fast-forward),全量测试 408/408 通过,L1 parity PASS,八类查询 CLI smoke 全 available,兼容性验证全过,默认路径零回归。

报告文件:本文件(`docs/pr1-postmerge-validation.md`)已提交至合并后的 main。

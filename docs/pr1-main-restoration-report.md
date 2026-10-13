# PR1 Main Restoration Report

> 任务:PL-PR1-MAIN-RESTORATION(2026-10-12)
> 判定:**RESTORATION_PR_READY**

---

## 1. 基线确认

| 项 | 值 |
|---|---|
| origin/main | `348f6e6`(完整 PR #1 合并) |
| 本地 main | `66ecf7c`(= 8ee007a + 审计报告) |
| 8ee007a 与 66ecf7c 关系 | 66ecf7c 是 8ee007a 的子提交(仅增加审计文档) |
| 验证目标代码树 | `8ee007a` tree = `4b28e2e`(MERGED_AND_VALIDATED) |
| 工作区 | 干净 |
| 恢复引用 | tag `pre-merge-main-backup` → `14499f8` |
| 分支 `integration/pr1-selective` | `3c3f2d1`(保留) |

## 2. 远程归档

- 分支 `archive/pr1-full-merge` → `348f6e6`(与 origin/main 一致)
- 远程完整 PR #1 合并的历史完整保留

## 3. 主干协调分支

| 项 | 值 |
|---|---|
| 分支名 | `reconcile/selective-as-main` |
| HEAD | `fff9965` |
| tree SHA | `4b28e2e`(= 8ee007a tree,MERGED_AND_VALIDATED) |
| parent 1 | `348f6e6`(origin/main,完整 PR #1 合并) |
| parent 2 | `3c3f2d1`(integration/pr1-selective) |

使用 `git commit-tree` 创建合并提交——保证 tree SHA 与目标**完全一致**。

## 4. 完整验收(408 测试 + parity + 8 查询 + 兼容)

| 检查项 | 结果 |
|---|---|
| 全量测试 | **408/408 PASS** |
| L1 parity | **PASS** |
| 八类查询 CLI smoke | **8/8 available** |
| Gold Target V2 L1-only | **CONFIRMED**(默认 index 零检测产物) |
| 旧库 PK 迁移 | **8/8 PASS** |

## 5. 暂时排除的能力(归档于 archive/pr1-full-merge)

| 能力 | 排除理由 |
|---|---|
| 冷存储默认化(storage.py cold.db) | 改变默认布局，影响备份/status/工具链 |
| declarations 重构嵌入 parse 路径(parsing/cpp.py) | 替换 L1 符号抽取路径 |
| 流式增量(incremental.py) | I2-A 边界排除 |
| graph.py 事件/CFG/DFG 嵌入 build_graph | 违反原则 5(低成本默认服务) |
| 流式 resolver(resolver.py) | 语义变化未经验证 |

以上能力**代码完整保留**在 `archive/pr1-full-merge` 分支，可通过 Capability Contract 按需启用。

## 6. 推送远程

- 推送 `reconcile/selective-as-main` 至远程
- 推送 `archive/pr1-full-merge` 至远程
- 在 GitHub 上创建 PR: `reconcile/selective-as-main` → `main`

```bash
git push origin reconcile/selective-as-main
git push origin archive/pr1-full-merge
# 然后在 GitHub 上创建 PR
```

(本轮未推送——需人工确认后执行。)

# PR1 Merge and Final Close Report

> 任务:PL-PR1-PR2-MERGE-AND-FINAL-CLOSE(2026-10-13)
> 判定:**PR1_CLOSED_AND_VALIDATED**

---

## 1. 合并执行

| 项 | 值 |
|---|---|
| PR #2 | [Restore qualified selective integration as main baseline](https://github.com/sunSUNQ/provenlattice/pull/2) |
| 合并方式 | GitHub Create a merge commit |
| 合并时间 | 2026-10-13T03:39:18Z |
| Merge commit | `922b834` |
| parent 1 | `348f6e6`(origin/main,完整 PR #1 归档) |
| parent 2 | `a155dea`(reconcile/selective-as-main) |
| tree SHA | `9479d1b`(= fff9965 tree = 8ee007a tree + restoration report doc) |

## 2. 合并后全量验证

| 检查项 | 结果 |
|---|---|
| 全量测试 | **408/408 PASS** |
| L1 parity | **PASS** |
| 八类 CLI smoke | **8/8 available** |
| Gold Target V2 L1-only | **CONFIRMED** |
| 旧库 PK 迁移 | **8/8 PASS** |
| MCP 桥接 | mcp_server.py 零 diff ✓ |
| grade/level envelope | ✓ `local-only, diagnostic` |
| 性能(index) | 6.94s / 218.1MB — 噪声带 |
| 纯查询不写库 | ✓(I2A 测试锁定) |
| resolved ≠ Verified | ✓(defect.py 无 "verified" 字符串) |

## 3. 归档分支状态

| 分支 | HEAD | 用途 |
|---|---|---|
| `archive/pr1-full-merge` | `348f6e6` | 完整 PR #1 归档(远程) |
| `reconcile/selective-as-main` | `a155dea` | 协调分支(远程,已合并) |
| `integration/pr1-selective` | `3c3f2d1` | 集成工作分支(本地保留) |

## 4. 最终 main 提交历史

```
8ee007a  (via merge) ← main HEAD
   ...
3d081fb  freeze I1C baseline
14499f8  ← 合并前 main(冻结基线)
```

## 5. 遗留 WARN/INFO

| # | 类型 | 描述 |
|---|---|---|
| 1 | WARN | PK migration DDL 列名硬编码 |
| 2 | WARN | defect.py 中 redis/llama 语料注释 |
| 3 | INFO | _upstream_state 逐文件 SQL 查询 |
| 4 | INFO | names 全量加载 |
| 5 | INFO | test_cfg_analysis 版本常量化 |
| 6 | INFO | CI 未配置(既有状态) |
| 7 | INFO | MCP defect 命令未做端到端客户端验证 |

## 6. 八类查询能力资格

| Query | 等级 |
|---|---|
| resource_lifetime | FUNCTIONAL + DIAGNOSTIC |
| lock_order | FUNCTIONAL + DIAGNOSTIC |
| race_condition | FUNCTIONAL + DIAGNOSTIC |
| null_flow | FUNCTIONAL + DIAGNOSTIC |
| use_after_free | FUNCTIONAL_VALIDATED |
| double_free | FUNCTIONAL_VALIDATED |
| error_handling | SMOKE + DIAGNOSTIC |
| taint_path | SMOKE + DIAGNOSTIC |

**resolved ≠ Verified Finding. confidence = heuristic score.**

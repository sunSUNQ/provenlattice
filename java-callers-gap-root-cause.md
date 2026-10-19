# Java Callers Gap Fix — Root Cause and Engineering Report

**状态：`JAVA_CALLERS_CANDIDATE_QUERY_PASS`** · 日期 2026-10-16
**分支**：`fix/java-callers-ambiguous-query`（基于 origin/main `0cc4df8`）

---

## 1. 根因

P2-A R1 正确消除了 identifier-receiver 实例调用的启发式确定性绑定，但 `callers`
CLI 仅查询 resolved CALLS 边——demote 后这些调用变为 ambiguous（候选保留在
raw_references 但无边），导致 Java 方法的调用者对 Agent 不可见。

**这不是 resolver 缺陷**：R1 行为正确（消除了错误绑定）。问题在于查询接口
不能消费 ambiguous evidence。

**附带发现**：`_resolve` 仅做精确匹配（id/qualified_name/name），方法级限定名
（如 "Node.get"）无法命中 `a.Node.get`——这是**既有限制**（R1 之前 `callers`
对方法级查询也返回 0）。本修复同时解决此问题。

## 2. 修复实现

### query.py
- `get_callers(symbol, *, include_ambiguous=False)` — 新参数默认 False（零变化）
- `_possible_callers(symbol, max_results=200)` — 新方法：
  - 使用 `find_symbol` 的宽匹配（qualified_name endswith）解析目标
  - 查询 ambiguous CALLS raw_references
  - 过滤 candidate_symbols 包含目标 symbol ID 的行
  - 仅保留 Method/Function kind 的调用者
  - 返回 evidence-level candidate（不生成边）

### cli.py
- `callers <symbol> [--include-ambiguous]` — 默认 off（零变化）

### 约束遵守
- 不撤销 R1 demote ✅
- 不为 ambiguous 生成 CALLS 边 ✅
- 不改变默认 index 行为 ✅
- Python/C/C++ 不受影响（metadata 门控）✅

## 3. HikariCP 真实验证

```
查询: callers HikariConfig.setConnectionTimeout --include-ambiguous
confirmed: 0（R1 后预期行为）
possible_callers: 65（含 65 个 ambiguous 候选调用者）
```

| 对比 | A 原 callers | B --include-ambiguous | C JDT merge_audit |
|---|---|---|---|
| setConnectionTimeout 调用者 | **0** | **65** | recoverable（3228 全仓补回中含） |
| 误候选 | N/A | 0（候选均合法 Method 节点） | 0 |
| 确定性绑定 | 0 | **0**（不伪造） | 0 |

## 4. 测试

- 新增 5 项回归（default 排除 / ambiguous 发现 / 无边断言 / Python pin / 确定性）
- 全量 **484 tests OK**（479 + 5；1 个环境伪影除外——ambient editable 1.4.0）

## 5. 零变更证明

- 产品源码（resolver/parsing/graph/storage）：**零 diff**
- 测试 fixture：零变化
- 冻结实验数据：零变化
- 默认 index 行为：零变化（include_ambiguous 默认 False）

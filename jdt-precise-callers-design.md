# JDT Precise Callers Design（下一阶段设计，本轮不实施）

## 目标

从 JDT binding 的精确 FQN + signature 补回 R1 demote 后丢失的调用者信息，
使 Agent 在 Java 仓库中获得接近编译器级的调用者查询结果。

## 核心设计问题与方案

### 1. JDT FQN → L1 Method ID 映射

JDT binding 输出 `declaringClass.getQualifiedName()` + `methodName()` +
`parameterTypes()`。映射到 L1 symbol_id：

```
symbol_id = sha256(repo_id \x1f relative_path \x1f "Method" \x1f
                   qualified_name \x1f signature)
```

需按 L1 symbol_id 的构造规则（identity.py:74）反查。策略：
- 先按 qualified_name + name 在 nodes 表精确查找
- 命中多个（重载）→ 按 JDT parameterTypes 匹配 signature
- 仍未命中 → 标记 external（不创建虚假映射）

### 2. JDT ↔ L1 调用站点关联

JDT driver 按 (file, line) 输出绑定。L1 raw_reference 按
(file, start_line, raw_name) 索引。关联策略：
- 同文件同行匹配
- 同一行多个调用 → 按方法名+参数数匹配
- JDT binding 的 method name 必须与 L1 raw_name 尾段一致

### 3. 同一行多个调用

Postmerge 报告已证实同行可有多条绑定（如 `Field.get` + `AtomicReference.get`）。
方案：按 (file, line, method_name) 三元组关联，而非 (file, line) 二元组。

### 4. 重载与外部依赖

- 重载：JDT signature 含参数类型 → 唯一确定目标；如 L1 无匹配节点 → external
- 外部依赖（JDK/jar）：decl 不在 L1 nodes → 标记 `target=external`，不入 possible_callers
- recovered：过滤丢弃

### 5. 冲突处理

JDT binding 与 L1 confirmed 边冲突时：保留 L1 confirmed（更高信任），JDT 结果
标为 `conflict_conservative`（与 P2-E 口径一致）。

### 6. query-time 非持久化

JDT 结果仅存在于 merge audit view 中（同当前 P2-D 设计），不写入 L1 图。
持久化（analysis 表）为后续独立立项。

### 7. JVM 启动隔离

JDT 仅在 `java-semantic` 命令中运行；`callers` 命令默认不启动 JVM。
Agent 可通过 `--include-ambiguous` 获取 L1 候选 + 通过 `java-semantic`
获取 JDT 精确绑定（两条命令、两级证据）。

### 8. provenance

每条 JDT 补回标注：
```json
{"provenance": "semantic:jdt-v1", "backend": "eclipse-jdt",
 "classpath_fingerprint": "cp:...", "call_kind_version": 3}
```

### 9. opt-in 设计

`callers --include-ambiguous` = L1 候选（无 JVM）。
`java-semantic --mode full` = JDT 精确绑定（需 JVM）。
两条路径独立，Agent 按需选择。不自动运行 JDT。

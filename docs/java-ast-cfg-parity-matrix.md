# Java AST/CFG Parity Matrix — 1.5.0

## 能力对齐矩阵

| 维度 | Python AST | Python CFG | C AST | C CFG | **Java AST** | **Java CFG** |
|---|---|---|---|---|---|---|
| 解析器 | tree-sitter-python | tree-sitter-python | tree-sitter-c | tree-sitter-c | **tree-sitter-java** | **tree-sitter-java** |
| 节点 ID 策略 | 结构路径 | 结构路径 | 结构路径 | 结构路径 | **结构路径** | **结构路径** |
| Owner 对齐 | 行号→L1 symbol | AST payload→owner | 行号→L1 symbol | AST payload→owner | **行号→L1 symbol** | **AST payload→owner** |
| 嵌套符号 | ✅ | ✅ | ✅ | ✅ | **✅** | **✅** |
| 方法重载 | N/A (Python) | N/A | N/A (C 无重载) | N/A | **✅ 按签名独立 ID** | **✅ 按 owner 隔离** |
| Lambda/匿名类 | ✅ 子节点 | ✅ | N/A | N/A | **✅ 子节点** | **opaque 节点（体不展开）** |
| 解析错误 | 部分提取 | 部分提取 | 部分提取 | 部分提取 | **部分提取** | **保守跳过（方法级 has_error）** |
| 缓存 | AnalysisStore | AnalysisStore | AnalysisStore | AnalysisStore | **AnalysisStore** | **AnalysisStore** |
| Freshness | contract+base_hash | contract+base_hash | contract+base_hash | contract+base_hash | **contract+base_hash** | **contract+base_hash** |
| 依赖 | — | ast:python | — | — | **—** | **ast:java** |
| 不支持构造 | async/match/... | try/with/match/raise/... | N/A | N/A | **无（AST 全覆盖）** | **try/catch/throw/sync/switch expr/yield/labeled；解析错误；lambda 体不展开** |

## Java CFG 支持状态矩阵

| 构造 | 支持 | 说明 |
|---|---|---|
| 方法入口/退出 | ✅ | entry + exit 节点 |
| 顺序执行 | ✅ | next 边 |
| if/else if/else | ✅ | true/false/merge 边 |
| for | ✅ | header/body/back/break |
| enhanced for | ✅ | 同 for |
| while | ✅ | 同 for |
| do-while | ✅ | body 先执行，再判断 |
| break | ✅ | 跳到最近循环出口 |
| continue | ✅ | 跳到最近循环头部 |
| return | ✅ | return→exit 边 |
| 方法调用站点 | ✅ | callsite 节点 |
| **try/catch/finally** | ⬜ | 保守跳过（V1） |
| **try-with-resources** | ⬜ | 保守跳过（V1） |
| **throw** | ⬜ | 保守跳过（V1） |
| **synchronized** | ⬜ | 保守跳过（V1） |
| **labeled break/continue** | ⬜ | 保守跳过（V1） |
| **switch expression/yield** | ⬜ | 保守跳过（V1；语句位置 switch 在 tree-sitter-java 中同为 switch_expression，一并跳过） |
| **解析错误（ERROR/MISSING）** | ⬜ | 方法级保守跳过（`methods_skipped_parse_error`；含嵌套方法） |
| **lambda 体** | ⬜ | 宿主内为 opaque 单节点，体内部控制流不建模（V1）；体含禁用构造时宿主方法整体跳过 |
| **匿名类** | ⬜ | 宿主内为 opaque 单节点；其方法体因 L1 无对应符号（R5 gap）无法对齐 owner，计入 `methods_skipped_unmatched_owner`，不产生 CFG |

## HikariCP 实测数据

| 指标 | 值 |
|---|---|
| AST scope_source_files | 47 |
| AST materialized | 47（100%） |
| AST nodes_written | 30,757 |
| CFG methods_built | 499 |
| CFG methods_skipped_unsupported | 111（try/catch/throw/sync） |
| CFG methods_skipped_unmatched_owner | 10 |
| CFG nodes_written | 2,370 |
| CFG edges_written | 2,038 |
| 解析失败 | 0 |

> 测量口径备注：以上数据在 `cfg:java` v1（do-while header-first、无解析错误跳过）下测得。
> v2 引入 do-while body-first 边结构与 `methods_skipped_parse_error` 方法级跳过后，
> do-while 方法的边数与含解析错误方法的 methods_built 可能变化；刷新测量前，
> 本表数字仅代表 v1 口径，不作为 v2 的资格证据。

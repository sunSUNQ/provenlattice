# Java Sparse CFG/DFG V1 实现与工程验收

**PL-JAVA-SPARSE-CFG-DFG-V1-IMPLEMENTATION · 交付报告**

## 工程验收结论

**`JAVA_SPARSE_CFG_DFG_V1_ENGINEERING_PASS`**

## 修改文件清单

| 文件 | 状态 | 说明 |
|---|---|---|
| `src/provenlattice/analysis_java_scfg.py` | 新增 | Java Sparse CFG materializer（owner index + Java AST walker + analyzer 包装） |
| `src/provenlattice/analysis_java_dfg.py` | 新增 | Java Sparse DFG materializer（复用 `mint_dataflow_edges`） |
| `src/provenlattice/analysis.py` | 修改 | `ANALYZER_VERSIONS` + `CAPABILITY_CONTRACT` 注册 `sparse_cfg:java` / `sparse_dfg:java` |
| `src/provenlattice/orchestrator.py` | 修改 | import + sparse_cfg/sparse_dfg 分派 + `_supports_feature` 接受 `.java` |
| `src/provenlattice/analysis_query.py` | 修改 | `QUERY_ANALYZERS` 注册 java 语言映射 |
| `tests/test_java_sparse_dfg.py` | 新增 | 10 个 golden tests |
| `tests/test_capabilities_i0.py` | 修改 | `sparse_cfg.analyzer_ids` 断言加入 java |

## 支持矩阵（V1）

| 构造 | 支持 | 输出 |
|---|---|---|
| 局部变量声明 + 初始化 | ✅ | WRITE（storage=local，subject_decl 作用域消歧） |
| 普通赋值 `=` / 复合赋值 `+=` 等 | ✅ | WRITE +（复合）read-before-write |
| `x++` / `++x` | ✅ | READ + WRITE |
| 方法参数绑定 | ✅ | WRITE（storage=parameter） |
| identifier read/write + 词法作用域 | ✅ | READ / WRITE（innermost-scope lookup） |
| return | ✅ | RETURN + 返回值 READ |
| if/else 分支 + 合流 | ✅ | CHECK + BRANCH + branch=true/false + fallthrough 合流 |
| while/for 循环 + 回边 | ✅ | CHECK + BRANCH + loop_back |
| 变量遮蔽 | ✅ | 每次声明独立 subject_decl（`local:x#N`） |

## 暂不支持（明确降级，不伪造数据流）

- 跨过程 points-to；heap/field-sensitive；反射目标；try-with-resources；
- `try/catch/switch/synchronized/lambda/throw` 仅提取内部访问事件，不产生控制流；
- ALLOC/RELEASE/CONSUMES/DEREFERENCE（Java 语义不适用）。

## 测试结果

- 新增 `tests/test_java_sparse_dfg.py`：**10 passed**（declaration / assignment /
  parameter / read-write chain / compound assignment / if-else branch+merge /
  while loop backedge / return / shadowing / try degradation）。
- 回归：`test_sparse_cfg_i1b` + `test_sparse_dfg_i1c` + `test_events_i1a` +
  `test_analysis_contract` + `test_analysis_query` + `test_analysis` + capabilities
  —— 全绿；全套件 **486 passed**（含 1 处 `sparse_cfg.analyzer_ids` 断言按新语言更新）。

## 限制说明

- 控制流为 method-local；READ/WRITE 访问点按 C 契约**不连控制边**（edgeless），
  `control_reachable` 对访问端点记 `unknown`，与 C 版证据契约一致。
- 复用 `sparsedfg.mint_dataflow_edges`（未复制 DFG 算法）；identity / AnalysisStore /
  PointKey / SemanticEdge 全复用。
- C/C++ 输出语义、L1 默认索引、CALLS resolver 均未改动；Bug #28 未顺带修复。

## 环境说明（验证用）

本机 `provenlattice` 的 editable install 指向旧 worktree（`tasco-temp/…/codegraph-3`），
故验证时以 `PYTHONPATH=src` 运行（或重装 editable 包）。正式发布时按仓库授权规则重装即可。

STOP：一次工程验收完成，不启动额外独立复审链。
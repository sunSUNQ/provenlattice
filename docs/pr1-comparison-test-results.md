# PR #1 Comparison Test Results R1（对照测试实测数据）

> 任务：PL-PR1-CAPABILITY-RECONCILIATION-R1（2026-10-12）
> 文档地位：本轮**全部实测数据**的记录；选择矩阵与结论见
> [docs/pr1-capability-reconciliation.md](pr1-capability-reconciliation.md)。
> 原始 JSON 输出保留于本机
> `%TEMP%\opencode\pl-r1\results\`（sem_main.json / sem_pr.json / perf_main.json /
> perf_pr.json / db_inspect.json / kind_distribution.json / missing_symbols.json /
> missing_method_detail.json / defect_probe.json / defect_aria2_corrected.json /
> for_probe1–6 / for_probe2.json）。

## 1. 环境与基线（同输入、同环境承诺）

- OS：Windows（win32）；Python 3.12.10；tree-sitter 0.26.0 / c 0.24.x / cpp 0.23.x / python 0.25.0（与 `requirements.txt` 一致，**双方同一解释器、同一依赖**）。
- 被测版本：main `14499f8`、PR `fcd363c`（隔离 detached worktree，源码未改动）。
- 语义夹具：双方使用**逐字节相同**的 C 源文件集合（10 个控制流构造 + 1 个资源构造 + 4 个调用语义文件）。
- 性能语料：**aria2**（`benchmark-repos/aria2` 快照复制，1,393 文件 / 165,171 行 C/C++；双方各一份内容相同的独立副本）。
- 诚实声明：性能为**诊断级**（单机单次运行、无多轮取中位）；Peak RSS 为进程生存期单调峰值（同一 harness，方法性偏差两侧一致）。

## 2. 测试套件基线（Step 2 前置）

| 套件 | main | PR |
| --- | --- | --- |
| `python -m unittest discover -s tests` | **254 通过 / 0 失败**（66.3s） | **530 通过 / 1 error**（110.5s） |

### 2.1 PR 的 1 个 error（根因已定位）

- 测试：`test_defect.CliTests.test_a_bad_type_is_a_usage_error_and_an_unexpanded_one_is_not`（tests/test_defect.py:2903）。
- traceback：`cli.run` → `GraphQuery(database)` → `overlay.py:320 raise RuntimeError("base graph is empty")`。
- 定性：**测试缺陷**——该测试期望 `--type` 用法错误先于数据库打开被拒绝，但 CLI 先打开了空库。非产品逻辑错误；集成前必须修复（不可带病并入）。

## 3. 能力对照（重叠能力，同输入同环境）

### 3.1 CFG 语义构造对照（10 个 C 构造文件，逐字节相同输入）

main 通过 `full_index` + `analyze_scope(src, features=(ast,cfg))` + `query_analysis(cfg, file_path=...)` 提取；PR 通过 `CppTreeSitterParser.parse_bytes` + `build_graph`（与 PR 测试同一 publish 路径）提取。

| 构造 | main（statement 级 Full CFG，`cfg:c`） | PR（事件点级 Sparse CFG，CONTROL_REACHES） | 结论 |
| --- | --- | --- | --- |
| if/else | condition true/false → merge，7 节点形状正确 | BRANCH branch=true/false 双边 | **双方正确**（粒度不同） |
| while | loop_header true/false + back 边 | BRANCH true/false + loop_back | **双方正确** |
| for（单行写法） | **`cfg:no_functions_built` 整文件跳过**（status=not_built；见 §3.2） | CALL/CALL/BRANCH + loop_back 正确 | **PR 正确；main 健壮性缺口** |
| do-while | condition true→body、false→exit + back | BRANCH `branch=true,loop_back` | **双方正确** |
| switch+fallthrough | case/default/fallthrough/break 边全显式（12 节点） | `fallthrough` flag 边（c1→c2）+ break 出口 | **双方正确**（main 更显式） |
| goto/label | **goto 节点 + condition true→goto + goto→label 边完整** | 跳转目标不建模：BRANCH 无 true 边，真分支从图上断开（PR 自我登记的 stage-3 不精确） | **main 完整；PR 有损（登记在案）** |
| 短路 `&&` | **表达式级 lowering**：两个 condition 节点串联（op1 true→op2），fp07 求值被门控 | 坍缩为单个 BRANCH；条件内 CALL 线性可达，短路求值门控丢失 | **main 精确；PR 保守粗粒度** |
| 三目 `?:` | 表达式级双分支（true/false ×2） | 两个 BRANCH 点双分支 | 双方均可表达（粒度不同） |
| 空指针检查+解引用 | condition + return（无事件粒度） | **CHECK + DEREFERENCE 事件点**，CHECK branch=false→DEREFERENCE 边 | **PR 独有缺陷分析粒度** |
| 全局 READ/WRITE | 无对应事实 | WRITE/READ 事件（g10 全局，storage 类别在案） | **PR 独有** |

**C++ try/catch / RAII 构造**：main L2 明确不支持 C++（D4 边界）；PR 解析 .cpp 但本轮夹具集未包含 .cpp 构造 → **NOT_TESTED**（双方都不作为失败项）。

### 3.2 main 侧新发现：单行 for 循环导致整文件 CFG 跳过（6 轮二分探针）

- 现象：`for` 语句与函数体压缩在**单个物理行**时（如 `int f(int a) { for (int i = 0; i < a; i += 1) { b(); } c(); return 0; }`），`analyze_scope` 对该文件 `cfg_status=skipped, reasons=['cfg:no_functions_built']`——**整个文件的 CFG 不产出**（AST 仍正常 materialize，44–45 节点）。
- 控制变量证据（for_probe1–6.json）：
  - 同一代码**多行排版** → materialized（p1/p4/m1–m4 全过，含 `i += 1`、`i++`、`++i`、C99 声明、无声明、continue/break 各种变体）；
  - 同一代码**单行排版** → skipped（p2/p3 + probe3 四变体 + probe4 四变体）；
  - 单行 **while/if 不受影响**（ctl01/ctl02、g_while_proto 均 available）。
- 定性：**main 的真实健壮性缺口**（触发面窄——真实代码几乎不写单行 for；且失败被诚实记录在 `per_file[].reasons`，非静默崩溃、非 crash）。修复建议已列入集成计划 I1 前置任务（不阻塞对账）。

### 3.3 调用语义对照（4 个构造 × 双方）

| 构造 | main `get_call_semantics` | PR reference metadata（cold 库 raw_references） |
| --- | --- | --- |
| 直接调用（有定义） | `call_kind=direct, class=direct, target=foo_cs01` | `{"call_kind":"direct","callee_shape":"identifier"}` |
| 函数指针参数调用 `h(x)` | `indirect, target=null, candidates=[]` | `{"call_kind":"indirect","argument_identifiers":["x"]}` |
| 函数指针赋值后调用 `fp(1,2)` | `indirect, target=null` | `{"call_kind":"indirect","callee_symbol":"fp_cs05"}` |
| 未解析调用 `unknown_cs09(1)` | `call_kind=direct, class=unresolved`（语法类别与解析类别分离） | metadata `call_kind=direct`（解析状态在 `status` 列，同源机制） |

**结论**：`fcd363c` 之后双方 A3 机制同源一致；main 额外提供 SQI 查询面。C++ 文件 call_kind 为 null（aria2 实测：direct 46,678 / indirect 1 / null 8,466）是**双方共同的既有边界**（A3 仅 stamp .c 文件），非 PR 回归。

### 3.4 PR 专属能力独立验证（不要求 main 具备）

**事件抽取**（aria2，semantic_events 表，103,042 条）：

| 事件类型 | 数量 | | 事件类型 | 数量 |
| --- | --- | --- | --- | --- |
| CALL | 48,542 | | CHECK | 807 |
| READ | 22,971 | | THROW | 700 |
| DEREFERENCE | 16,165 | | ALLOC | 442 |
| BRANCH | 5,382 | | RELEASE | 46 |
| RETURN | 5,219 | | LOCK/UNLOCK/THREAD_JOIN | 12/6/10 |
| WRITE | 2,740 | | ATOMIC | 0 |

**语义关系**（semantic_edges 86,488）：CONTROL_REACHES 83,397 / DATA_FLOW_TO 3,089 / CONSUMES 2（与 PR 知识库自述的"控制:数据 ≈ 27:1、CONSUMES 基本不产出"一致）。

**Typed Defect Query**：

1. **夹具验证（植入缺陷）**：`void res01(void){ char *p = malloc(64); if(!p) return; free(p); free(p); }` →
   `double_free` 查询按**查询名 / 矩阵键 4.2 / all 三条路径均返回同一候选**（修正 envelope 读取层级后；详见 §5 harness 说明）：
   - subject `p`（local, char），facts = 两条 RELEASE（matched_name=free），paths 经语义边连接，
   - `candidate_id=E-DEFECT-889a…`、`resolution_status=resolved`、`confidence=0.5`、source_evidence=`res01.c:2-2`，
   - **missing_evidence 3 条**（释放约定是否置空 / 别名同一性 / noreturn 约定）——Evidence Bundle 质量实测确认。
2. **aria2 实测**（`max_candidates` 默认 20，多查询触顶截断——真实 population 以 coverage 为准）：

   | 查询 | 秒 | 候选（截断后） | coverage population / states |
   | --- | --- | --- | --- |
   | resource_lifetime | 9.03 | 20（截断） | — |
   | lock_order | 2.19 | 0 | — |
   | race_condition | 3.30 | 20（截断） | — |
   | null_flow | 2.18 | 20（截断） | population：alloc_to_deref 380 + null_to_deref 1；resolved 356 / ambiguous 16 |
   | use_after_free | 2.27 | 1 | ambiguous 1 |
   | double_free | 2.25 | 2 | resolved 1 / unresolved 1 |
   | taint_path | 2.45 | 0 | population：input_to_sink 954（被判据过滤为 0 候选） |
   | error_handling | 2.53 | 20（截断） | stored-call-result 8,121；resolved 3,975 / ambiguous 107 |
   | **all** | **13.93** | 20 | — |

   观察项（非缺陷，登记）：候选集中于 test/ 文件（DHTBucketTest 等）——生产使用需 scope 选择；C-API 中心词汇表使 C++ 风格语料的 ALLOC/RELEASE 极稀（442/46），资源类查询覆盖受限。

## 4. 性能对照（aria2：1,393 文件 / 165,171 行，本轮实测）

| 指标 | main `14499f8` | PR `fcd363c` | Δ |
| --- | --- | --- | --- |
| 全量索引 | **6.71s** | 17.27s | **+157%**（PR 在索引期内完成语义事件/Sparse CFG/DFG 抽取） |
| 索引峰值 RSS | **217.8MB** | 409.6MB | +88% |
| 库大小（索引后） | 152.9MB（1 文件） | 主 224.8MB + 冷 82.8MB = 307.6MB | +101%（含语义表 + 冷分离的页开销） |
| 查询延迟（10 次调用） | find_symbol 15.0ms / definition 12.0 / callers 16.3 / callees 16.5 / references 12.2 / call_semantics 14.0 / subgraph 17.1 | **8.46 / 6.48 / 10.61 / 11.18 / 6.57 / 7.96 / 9.09ms** | **PR 快约 1.5–2×**（冷存储缩小主库的副产品，对 L1 有正价值） |
| main 专属 L2 物化 | analyze_scope(src)=12.37s（ast 533 文件 / cfg 140 文件） | —（PR 无独立物化阶段） | 架构差异：main 可 scope 化、PR 在索引期整体发生 |
| PR 专属缺陷查询 | — | `all` 13.93s（8 查询 2.2–9.0s 各自） | 可选能力的按需成本 |
| 增量更新（追加 1 函数） | **6.26s** | 12.16s | +94%（PR 含语义层重建；未做 7A-2 隔离 A/B——NOT_TESTED） |
| 增量后峰值 RSS | 529.3MB | 571.4MB | —（均含前序阶段单调峰值） |
| 增量后库大小 | 278.4MB（含本轮 analyze_scope 物化的 analysis_* 表） | 308.1MB | —（两侧增量后口径不同，见 §5 注意） |

**诚实标注**：① 单次运行，未做多轮中位/置信区间；② RSS 为进程单调峰值；③ main 增量后库增长含本轮 L2 物化产物，非纯 L1 增量成本；④ PR 索引成本与其事件层收益（§3.4）是不可拆分的整体，选择性集成时将事件层改为按需 analyzer 后，L1 默认成本应回落到 main 基线——该回落值是集成计划 I1 的验收对象（本轮无法预先实测）。

## 5. Harness 说明与已修正的测量误差（透明记录）

1. **defect envelope 层级**：首轮 smoke 与 perf 中误读 `res["candidates"]`（实际在 `res["data"]["candidates"]`），导致 aria2 与夹具的首轮 defect 计数全部为 0——已用修正探针（defect_probe.py / defect_aria2.py）重测，本报告 §3.4 为修正后数据。**首轮错误数据未进入任何结论。**
2. **冷库命名**：PR 冷库与主库同名不同后缀（`<stem>.cold.db`），首轮探针按 `codegraph.cold.db` 查找失败两次后修正为 glob。
3. **raw_references 位置**：main 在主库，PR 在冷库——对照查询分别打开对应文件（两侧行数一致 55,145，交叉验证通过）。

## 6. NOT_TESTED 清单（含原因）

| 项 | 原因 |
| --- | --- |
| C++ try/catch / RAII 构造的 CFG 对照 | 本轮夹具集未包含 .cpp 构造文件；main L2 本不支持 C++（文档边界），不构成失败项 |
| Python 侧事件/缺陷链 | PR 无 Python 缺陷验证证据；本轮未构造 Python 缺陷语料 |
| PR 增量后语义表 freshness / 失效正确性 | 本轮增量仅验证基础图更新完成（generation=2、changed=true）；语义层 freshness 需专门批次 |
| 7A-2 流式 update 在 legacy 布局的隔离收益 | 需要构造 legacy 布局 + 流式 update 的组合分支，超出本轮只读边界 |
| 冷存储迁移路径 | PR 明确无迁移路径（split 前旧库 update 显式 raise）；无旧库可测 |
| PR 冻结语料（redis-50 / llama.cpp-69）复测 | 冻结库不在本机（D:\tmp\stage7 不存在）；全部 PR 数字以本轮 aria2/夹具实测替代 |
| precision / recall 人工复核批次 | 属 Phase 1 三臂实验范围（需人工裁定协议），本轮仅夹具级与 population 级验证 |

## 7. 数据文件索引

| 文件 | 内容 |
| --- | --- |
| sem_main.json / sem_main_summary.json | main 构造级 CFG envelope + call semantics |
| sem_pr.json | PR 构造级事件/边 + call refs + defect smoke（首轮 smoke 计数受 §5.1 影响，以 defect_probe 为准） |
| perf_main.json / perf_pr.json | §4 性能数据 |
| db_inspect.json / kind_distribution.json | 库表规模、节点/边类型分布、call_kind 分布 |
| missing_symbols.json / missing_method_detail.json | §3.1（对账报告）L1 兼容性证据 |
| defect_probe.json / defect_aria2_corrected.json | 修正后的缺陷查询数据 |
| for_probe(2–6).json | main 单行 for 缺口的控制变量证据 |

# Defect Query Guide

> 适用版本:V1.4(2026-10-13)
> 适用语言:C/C++(`.c` `.h` `.cc` `.cpp` `.cxx` `.hpp` `.hh` `.hxx` `.inl`)
> 分析范围:`local-only, diagnostic`

## 1. 先决条件

缺陷查询需要上游分析链已物化且新鲜:

```bash
# 1. 构建基础图谱(L1)
provenlattice index /path/to/repo --json

# 2. 物化上游链(events → sparse_cfg → sparse_dfg)
provenlattice analyze /path/to/repo --scope src --features defect --json
```

上游链缺失或 stale 时查询返回 fail-closed(stale/not_built),不产生候选。

## 2. 运行缺陷查询

```bash
# 单类查询
provenlattice defect /path/to/repo --type double_free --json
provenlattice defect /path/to/repo --type use_after_free --json
provenlattice defect /path/to/repo --type null_flow --json

# 全部已注册查询
provenlattice defect /path/to/repo --type all --json

# 带预算限制
provenlattice defect /path/to/repo --type all \
  --max-candidates 50 --max-paths 16 --max-hops 32 --json
```

### 支持的查询类型

| 查询名 | Matrix Key | 说明 |
|---|---|---|
| double_free | 4.2 | 同一对象连续两次释放 |
| use_after_free | 4.3 | 释放后使用悬垂指针 |
| null_flow | 3.1 | NULL 值传播到解引用 |
| resource_lifetime | 4.1 | 资源分配后遗漏释放 |
| lock_order | — | 相反锁顺序 |
| race_condition | — | 共享变量无锁读写 |
| taint_path | taint | source→sink 传播 |
| error_handling | 9.1 | 返回值未检查 |
| mismatched_free | mismatch | 分配器与释放函数不配对（CWE-590/762/763） |
| out_of_bounds_write | oob_write | 写方向越界：常量下标/偏移、堆分配、`memcpy/memmove/memset` 长度（M5/M6/M8） |
| uninitialized_use | uninit | 方法内局部对象/局部指针在定义前读取（M9，CWE-457） |

### uninitialized_use（M9）

复用 `sparse_cfg` v7 的 `local_declaration_v1` / `local_access_v1` /
`control_position_v1` 事实，按 scoped declaration token 连接声明与访问：

- 状态：`uninitialized`（每条发布路径都无定义，`resolution_status=resolved`）、
  `maybe_uninitialized`（部分路径有定义）、`unknown`（方法覆盖不完整，显式
  带 coverage reason）、`initialized`（不产生候选）。
- 反例不报：声明初始化、使用前赋值、if/else 两臂均赋值、未初始化分支
  early return、静态零初始化、参数、不可达访问。
- 边界：只覆盖 straight-line、if/else、early return；goto、partial parse
  与 macro 可隐藏未发布的控制流，非 entry 覆盖一律 fail-closed；循环、
  switch/条件表达式、lambda/异常、未知写穿为显式 `unknown`/coverage，
  不静默当作安全。局部指针解引用（`*p`）本身会触发
  `unknown_write_through`，因此该形状是显式 `unknown` 候选，而非 definite。
  已知 FN：macro 位于 entry 写入之前（`M; x = 1; ...`）时，写入仍带
  `entry` position，查询无法与安全的 `x = 1; M; ...` 区分；V1 保留 #81 的
  entry 合同，需 producer 补 macro span/position（follow-up）。
- 支配判定：直线写入（包括 `sink(0); x = 1; sink(2); return x;` 中由 CALL
  隔开的写入）按 `control_position_v1` 与已发布的 `CONTROL_REACHES` 判断
  支配关系；中间的正常控制点不会把 definite 降级为 maybe。写入位于 if/else
  分支之后（两个 arm 的上下文都到达该写入）同样按支配判定。支配只在写、读
  两侧 position 的 `coverage_status=complete` 且 `coverage_reasons` 为空时
  成立；goto/partial_parse/macro 等不完整形状的**支配判定与上下文相等
  判定**均 fail-closed 为显式 `unknown`，不因 CFG 缺少 bypass 边而静默判为
  initialized。goto 目标未建模，因此含 goto 方法的非 entry 写入覆盖一律按
  `unknown` 处理（包括写入位于 label 之后的安全形状，属于已知精度损失）；
  macro 同理，非 entry 的安全 macro 形状也会降级为 `unknown`。loop/switch
  仍按已发布的分支上下文判定，已证明的覆盖不会因构造不受支持而降级。
- 路径证据：Candidate 的 `paths` 给出 declaration → prior write → 真实
  `CONTROL_REACHES` 控制路线 → use 的一条证据路径；carrier 边界（声明、
  访问事件本身）使用空 edge id，`len(edges) == len(points) - 1` 恒成立。
  `max_paths=0` 不发布路径且 `path_recorded=false`；`max_hops` 进入真实
  路径搜索，预算截断时 `paths_truncated=true` 并在 coverage 的
  `uninitialized_paths_truncated` 计数。
- 已知 FN：写入 span 是目标标识符本身，同一赋值右侧的自引用
  （`x = x + 1`）在 V1 中被当作写入之后的读取；`int x = x;` 的初始化自读被当作
  声明初始化，不产生候选。裸条件读取（`if (x)` / `if (p)` / `if (x) return`）
  上游未发布 `local_access_v1`，V1 在 coverage 的
  `uninitialized_bare_condition_reads` 中计数，并在
  `uninitialized_missing_evidence` 暴露
  `MISSING_INPUT_LOCAL_ACCESS_BARE_CONDITION`，不静默当作安全。
- 条件写：分支条件（BRANCH/CHECK）与声明 initializer 内的写入按
  maybe/unknown 处理，不当作无条件定义。initializer 的条件性由已发布的
  `unsupported_short_circuit` / `unsupported_conditional` coverage reason
  与 initializer span 判定，**不对 initializer 文本做 `?`/`&&`/`||`
  子串扫描**：字符串、字符和注释里的 `?` 不影响控制流判定。赋值 RHS /
  函数实参中的短路写（`y = (n && (x = 1))`、`g(n && (x = 1))`）缺少
  enclosing span，仍为 known FN（上游事实缺口，另列 follow-up）。

## 3. 结果 JSON 结构

```json
{
  "query": "double_free",
  "defect_type": "double_free",
  "status": "available",
  "candidates": [
    {
      "defect_key": "4.2",
      "query": "double_free",
      "subject": {
        "kind": "release",
        "name": "p",
        "identity": "symbol:...",
        "storage": "local",
        "method": "res01",
        "owner_symbol_id": "symbol:..."
      },
      "anchor": "event:...",
      "resolution_status": "resolved",
      "confidence": 0.5,
      "facts": [
        {"event": "RELEASE", "method": "res01", "matched_name": "free", "source": "t.c:2-2"}
      ],
      "uncertain_facts": [],
      "paths": [{"points": [...], "types": [...], "edges": [...]}],
      "source_evidence": ["res01.c:2-2"],
      "missing_evidence": [
        "the repository's release convention: ...",
        "whether two names really address one object: ...",
        "the noreturn conventions the graph does not hold: ..."
      ],
      "candidate_id": "E-DEFECT-...",
      "metadata": {"flow_class": "...", "via": [...], "control_reachable": "true"}
    }
  ],
  "coverage": {...},
  "truncated": false,
  "grade": "local-only, diagnostic",
  "level": "level0+structural+access+dfg",
  "provenance": {
    "queries": [...],
    "resolved_is_not_verified": "resolution_status is an evidence-resolution state; confidence is the PR heuristic score, not a calibrated probability"
  }
}
```

## 4. 字段含义

| 字段 | 含义 |
|---|---|
| `resolution_status` | 证据解析状态:resolved(声明身份一致)/ ambiguous(部分不确定)/ unresolved(无法归因)。**不是 Verified Finding** |
| `confidence` | Heuristic score(如 resolved=0.5),不是校准的概率 |
| `facts` | 图已证明的事件事实(事件类型、方法、位置、匹配名称) |
| `uncertain_facts` | 图无法确定的事实(带 `decisive` 标志:decisive 的不确定会降低候选状态) |
| `paths` | 事件间的语义边路径(点序列 + 类型 + 边 ID) |
| `source_evidence` | `path:startLine-endLine` 格式的源码位置引用 |
| `missing_evidence` | 更强分析需要补充的证据描述(如释放约定、别名精度、noreturn) |
| `control_reachable` | 三态:`true`(图中有路径)/ `false`(连接端点无路径)/ `unknown`(端点为 edgeless 访问点或 partial parse) |
| `grade` | `local-only, diagnostic` — 方法内分析,精度有限 |
| `truncated` | 候选数达到 max_candidates 被截断 |

## 5. 状态说明

| 状态 | 含义 | 处理 |
|---|---|---|
| `available` | 查询成功,返回候选(可能为 0) | 正常消费 |
| `stale` | 上游分析过期(源码变更或依赖版本变化) | 重新运行 `analyze --features defect` |
| `not_built` | 上游分析未物化 | 运行 `analyze --features defect` |
| `failed` | 查询错误(未知类型、基础图缺失等) | 检查 `error.code` 和 `error.detail` |

## 6. 已知误报和限制

| 类型 | 查询 | 描述 |
|---|---|---|
| FP | null_flow | `if(p){*p=1}` — null 臂仍可达隐式 else |
| FN | use_after_free | 别名 q=p 的 deref 不与 p 的 free 配对(精度缺口) |
| FN | CONSUMES | 仅直接传递形状(`f(malloc(n))`),赋值形状走 DATA_FLOW_TO |
| FN | sparse CFG | goto 目标不建模,短路坍缩为单 BRANCH |
| 边界 | 全部 | 方法内分析,无跨函数边;无 SSA/points-to |
| 边界 | uninitialized_use | 仅 straight-line/if-else/early-return；goto/partial_parse/macro 的非 entry 覆盖、循环/条件表达式/写穿为显式 unknown；分支条件（BRANCH/CHECK）与声明 initializer 内的写入按 maybe/unknown；macro 位于 entry 写入之前为 known FN（producer 缺口） |
| FN | uninitialized_use | `x = x + 1` 的 RHS 读取被当作写入之后；`int x = x;` 自初始化不产生候选；裸条件 `if (x)` / `if (p)` 读取上游未发布，仅在 `uninitialized_bare_condition_reads` 计数暴露；赋值 RHS / 实参短路写为上游事实缺口；参数/静态对象的调用期或零初始化语义不在候选内 |
| 边界 | error_handling | 精度受 API contract 知识限制 |
| 边界 | taint_path | 仅 4 source/3 sink,无 sanitizer/跨函数 |
| 边界 | out_of_bounds_write | V1 仅报告可证明常量：动态下标/动态大小/未知 extent/VLA/灵活数组进入 coverage;负常量下标由 #104 事实支持并报告;非 char 元素与堆分配的单位比较记 `unit_mismatch`;堆候选按“later 同身份定义不阻断的可达路径”判定,普通重绑定记 `reassigned`,互斥 release 不排除;`max_hops/max_paths` 耗尽降级 ambiguous;无 scoped 身份的 release 在 shadow 场景下以显式 ambiguous+limitation 表达 |

## 7. 故障排查

| 问题 | 原因 | 解决 |
|---|---|---|
| `stale` + `upstream_analysis_stale` | 源码变更后未重新分析 | 运行 `analyze --features defect` |
| `stale` + `files_not_covered` | 新文件未物化上游 | 同上 |
| `stale` + `dependency_changed` | 上游 analyzer 版本升级 | 同上(自动重建) |
| `not_built` | 从未运行过 `analyze --features defect` | 同上 |
| `failed` + `base_graph_required` | 未运行 `index` | 运行 `provenlattice index` |
| `failed` + `unknown_defect_query` | 查询名拼写错误 | 检查支持的查询列表 |
| 候选数达到 max_candidates | 预算截断,实际 population 可能更大 | 增大 `--max-candidates` 或查看 coverage |
| `control_reachable: unknown` | 端点为 edgeless 访问点或 partial parse | 不是确定性不可达;需人工复核 |

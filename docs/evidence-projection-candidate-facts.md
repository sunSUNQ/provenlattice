# Evidence Projection `candidate_facts` — 五类并发缺陷 projector 扩展（V1）

> 对应 Issue #106（`repo:provenlattice`，additive 扩展 #83 Projector Registry V1）。
> 本文档描述 Skill-facing FactBundle/IR V1 出口的 `candidate_facts` 契约、语义角色与消费纪律。
> 它不改变 `defect` 检测逻辑，不改变 `race_condition` / `double_free` 的 FactBundle 形状，
> 也不改变 IR V2。

## 0. 范围与不承诺

- Registry 从 2 个 projector 扩展为 7 个：`race_condition`、`double_free`、
  `lock_order`、`resource_lifetime`、`use_after_free`、`null_flow`、`mismatched_free`。
- 五类新 entry 输出 additive 的 `facts.candidate_facts.value[]`；
  既有 `shared_accesses` / `release_sites` 块保持不变。
- **projector 只保证“引擎已产出的证据可被 Skill 消费”，不把 candidate 升级为
  Verified Finding**。新类型的 precision 尚无 GT，不得据此宣称 race 指标或准确率变化。
- 不实现 FactBundle v2.2 的 `thread_facts` / `lock_facts` / `coverage_status`；
  不修改 IR V2。

## 1. 能力清单

`provenlattice.evidence_projection.skill_api.list_skill_capabilities()` 按 `defect_type`
返回 7 类。五类新增 entry 的 `projected_facts`：

| defect_type | projected_facts | 事实来源（摘要） | 主要限制 |
|---|---|---|---|
| `lock_order` | `lock_facts` | candidate 的 LOCK/UNLOCK facts + lock identity / role / side | MAY_PARALLEL 仍是 uncertain；锁别名未解析；候选不是已验证死锁 |
| `resource_lifetime` | `resource_facts` | ALLOC/RELEASE/CALL/CHECK/BRANCH/RETURN facts | ownership 契约不是一阶事实（进 `missing_evidence`）；别名/重赋值/callee 内释放未知 |
| `use_after_free` | `lifetime_facts` | RELEASE + DEREFERENCE/RETURN facts | 一个 RELEASE 可合法支撑多个 UAF 候选；别名精度有限 |
| `null_flow` | `null_flow_facts` | NULL/WRITE/DEREFERENCE facts | null 值与解引用是 method-local facts；有 guard 的解引用仍是已知误报面 |
| `mismatched_free` | `allocator_facts` | ALLOC + RELEASE facts 与声明的 allocator pair | 仅识别已知 allocator 对；未知 release fail-closed；不推断跨函数 ownership |

类型集合从 2 → 7 是 **additive** 变化：消费方不得断言集合大小恒为 2，应以返回的
manifest 内容为准。

## 2. `candidate_facts` 契约

路径：`bundle["facts"]["candidate_facts"]["value"][]`。

每个 candidate：

| 字段 | 含义 |
|---|---|
| `candidate_key` | 引擎 `evidence_id`，稳定且唯一 |
| `evidence_id` | 与 `candidate_key` 一致的引擎证据 id |
| `defect_key` | 引擎缺陷分类键（如 `4.1`、`mismatch`） |
| `discriminator` | 候选判别信息（类型相关） |
| `subject` | 候选主体（如变量/符号） |
| `identity` | 主体身份（如 `symbol:...#local:p`） |
| `resolution_status` | `resolved` / `ambiguous` / `unresolved` |
| `confidence` | 引擎置信度（0–1） |
| `facts[]` | 定位事实列表，见下表 |
| `uncertain_facts[]` | 未确认事实 |
| `missing_evidence[]` | 缺失证据（消费方必须如实透传，不得当成“无问题”） |

每条 fact：

| 字段 | 含义 |
|---|---|
| `fact_id` | 引擎 point / event id；不得虚构 |
| `fact_type` | `ALLOC` / `RELEASE` / `LOCK` / `UNLOCK` / `DEREFERENCE` / `READ` / `WRITE` / `CALL` / `CHECK` / `BRANCH` / `RETURN` / `NULL` 等 |
| `file` / `line` / `line_span` | 真实源位置；未定位时 `file=""`、`line=0` |
| `owner` | 事实所属函数/所有者 |
| `source_fact_id` | 源事实 id |
| `provenance` | 事实来源标记（如 `candidate.facts`） |
| `attributes` | 类型相关的额外属性（如 `matched_name`） |

## 3. semantic roles

新增 supporting location 语义角色：

| fact type | semantic_role |
|---|---|
| `ALLOC` | `resource_alloc` |
| `RELEASE` | `release_site` |
| `LOCK` / `UNLOCK` | `held_lock` |
| `DEREFERENCE` | `dereference` |
| `READ` / `WRITE` / `READ_MODIFY_WRITE` | `racing_access` |
| `CALL` | `call` |
| `CHECK` / `BRANCH` / `RETURN` | `control` |
| `NULL` | `null_value` |
| 其他 | `fact` |
| candidate 锚点 | `candidate_anchor` |

`supporting_locations[]` 仍保留既有 13 个必需字段；`race_condition` /
`double_free` 继续使用更窄的 `access_type` 枚举，不因通用 fact type 放宽。

## 4. 绑定规则（按 defect type 区分）

- `double_free`：一个 RELEASE fact 仍只能属于一个候选（严格唯一性）。
- `use_after_free` / `resource_lifetime` / `null_flow` / `mismatched_free`：
  允许合法共享 RELEASE fact —— 例如一次 `free(p)` 可同时支撑
  “解引用后释放”与“释放后返回”两个 UAF 候选。
- 实现规则：仅当共享 RELEASE 的所有 owner 都是 `use_after_free` 候选时才放宽；
  其余情况保持严格一 owner。

## 5. IR V1 消费

IR V1 通过 `evidence_locations[].access_rows` 消费通用行
（`access_type` = fact type）；本扩展不需要 IR schema 变更。IR V2 不受影响。

## 6. Skill 消费纪律

1. **按候选/事实选择，不要整包摄入**：真实代码上 bundle/source 字节比约 0.19–4.24。
2. 必须展示 `resolution_status`、`confidence`、`uncertain_facts`、`missing_evidence`；
   `unresolved` 锚点不得当作已定位证据。
3. 不得把 candidate 表述为已确认缺陷；需要判定时由 Skill 侧另行验证。
4. 新类型没有 GT，不得计算或宣称 precision/recall；真实代码上的候选数量只代表
   “证据暴露面”。
5. `payload_too_large` 仍是引擎边界：真实子集曾排除 3/6 个文件，不是 projector 行为。

## 7. 回归与验收基线

- `tests/test_evidence_projection_generic.py`：五类新 entry 的正例/反例。
- `registry.REGISTRY.list_projector_capabilities()` 返回 7 类。
- `skill_api.list_skill_capabilities()` 返回 7 类，并包含上表五类 `projected_facts`。
- 五类 fixture 正例 bundle/IR 校验 0 问题；反例 0 候选、0 证据。
- `race_condition` / `double_free` 既有测试全绿。

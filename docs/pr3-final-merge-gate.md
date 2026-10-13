# PR #3 Final Merge Gate

> 任务:PL-V1.4-PR3-FINAL-MERGE-GATE(2026-10-13)
> PR:[Restore qualified selective integration as main baseline](https://github.com/sunSUNQ/provenlattice/pull/3)
> 判定:**MERGE_READY = YES**

---

## 1. PR 状态确认

| 项 | 值 |
|---|---|
| PR state | OPEN |
| mergeable | MERGEABLE |
| mergeStateStatus | CLEAN |
| base | main @ `a35cae0` |
| head | docs/v1.4-documentation-reconciliation @ `79201aa` |
| files | 14 (700+/427-) |
| CI | [] (未配置，既有状态) |
| review | FINAL_DOCS_REVIEW_PASS (独立确认) |

---

## 2. 14 文件逐文件审查

| # | 文件 | 变更 | 审查判定 | 说明 |
|---|---|---|---|---|
| 1 | README.md | 530+/273- 重写 | **PASS** | V1.4 品牌定位、双轨架构、Quick Start 含 defect 命令、Validation/Limitations/Documentation 节。无 Verified Finding 冒称。无过期"PR 未合并"表述。 |
| 2 | CHANGELOG.md | 83+ 新增 | **PASS** | V1.4 条目(Added/Changed/Preserved/Deferred/Validation/Limitations)。历史条目完整保留。 |
| 3 | REPRODUCIBILITY.md | 18+ | **PASS** | 增加 §0 V1.4 Integration Evidence(408 测试/parity/smoke/perf)。历史内容保留。 |
| 4 | docs/capability-matrix.md | 75+ 新增 | **PASS** | 22 项能力矩阵(8 查询+3 analyzer+3 工程+8 main)。逐项标注来源/语言/默认/状态/验证/限制。 |
| 5 | docs/defect-query-guide.md | 145+ 新增 | **PASS** | CLI 命令示例(经实际运行验证)、JSON 结构、字段含义、三态可达性、故障排查。 |
| 6 | docs/releases/v1.4.md | 46+ 新增 | **PASS** | 区分工程验收/正式产品资格；明确 Release 门槛未满足。 |
| 7 | docs/roadmap.md | 53+/26- G7 更新 | **PASS** | G7 更新为 V1.4 实现状态(含全部新增能力)。Deferred 项如实标注。 |
| 8 | docs/v1.4-integration-overview.md | 164+ 新增 | **PASS** | 13 章整合报告(V1.3→PR1→V1.4 对照、KEEP/ADOPT/DEFER、技术理由)。 |
| 9 | docs/design-dual-capability-integration.md | 2+(superseded 说明) | **PASS** | 顶部增加状态说明指向 V1.4 文档。历史内容未改写。 |
| 10 | docs/pr1-final-integration-qualification.md | 2+(勘误) | **PASS** | §9 勘误(逐类资格表为准确来源，"全部 FUNCTIONAL"为笔误)。历史测试结果未改。 |
| 11 | docs/pr1-merge-and-final-close.md | 2+(HEAD 澄清) | **PASS** | 明确 a35cae0 为报告提交 HEAD，922b834 为合并产物 HEAD。 |
| 12 | pyproject.toml | version 1.0.0→1.4.0 | **PASS** | 版本元数据变更。semantics TOML package-data。 |
| 13 | cli.py | 5+/2- help text | **PASS** | `--type` help text 更新为 8 查询列表。无运行逻辑变更。 |
| 14 | docs/images/…panorama.png | Bin 299559→284073 | **PASS** | V1.4 重绘(PNG 1298×1032 RGBA 277KB)。 |

**算法/schema/冻结数据变更：0 行**(审计确认)

---

## 3. 八类查询描述一致性

八类查询在 README、capability-matrix、qualification report 三份文档中的描述一致：

- 8/8 查询名全部出现在三份文档中
- 资格等级一致：6 FUNCTIONAL + 2 SMOKE(全部 + DIAGNOSTIC)
- `resolved ≠ Verified Finding` 在三处均明确声明
- capability-matrix.md 每行含 来源/语言/默认/状态/验证/限制 列

---

## 4. 证据边界审查

| 检查项 | 结果 |
|---|---|
| `resolved` 被解释为 Verified Finding？ | **否** — defect-query-guide.md 明确声明 `resolved_is_not_verified` |
| `confidence` 被解释为校准概率？ | **否** — 明确标注 "heuristic score" |
| `taint_path` 被写成完整实现？ | **否** — 标注 SMOKE + DIAGNOSTIC，仅 4 source/3 sink |
| Cold Store 被写成已启用？ | **否** — Deferred，归档于 archive/pr1-full-merge |
| CI 被写成已配置？ | **否** — 明确标注未配置 |
| V1.4 正式 Release 被宣称？ | **否** — v1.4.md 明确区分工程验收/正式资格 |

---

## 5. 旧库兼容与覆盖检查

- PK 迁移测试 8/8 PASS(独立运行确认)
- 纯查询不写库:defect-query-guide.md 无 INSERT/UPDATE/DELETE 操作描述
- stale/not_built/failed 响应在 guide 中完整记录
- 历史冲突：无(PR 基于 main a35cae0，无分叉)

---

## 6. 已知风险(非阻断)

| # | 类型 | 描述 | 非阻断理由 |
|---|---|---|---|
| 1 | WARN | `_migrate_pk_schema` CREATE TABLE 列名硬编码 | 仅影响未来加表 |
| 2 | WARN | defect.py 中 redis/llama 语料注释 | 设计文档引用 |
| 3 | INFO | CLI `--type` help text 为嵌入式文档 | 可在后续 PR 中改为动态生成 |
| 4 | INFO | MCP defect 端到端未验证 | 桥接透传可用 |
| 5 | INFO | CI 未配置 | 既有状态 |
| 6 | INFO | contracts.toml 未迁入 | resource_lifetime 等查询的 contract 过滤不可用(候选仍产生) |

---

## 7. 最终判定

**MERGE_READY = YES**

14 文件变更全部为文档/版本元数据/CLI help text，零算法/schema/冻结数据修改。408/408 测试独立确认。八类查询能力描述跨文档一致。证据边界清晰。无阻断问题。

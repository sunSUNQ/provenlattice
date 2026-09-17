# SQI-V1 Formal Qualification Protocol V1

> **P2 / RQ3–RQ6 — Native vs SQI Formal Task-Level Qualification**
> 状态: **PROTOCOL V1 FROZEN**（2026-09-16）。本文件在任何正式 run 之前冻结评分标准、
> arm 定义、重复数与指标；冻结后不得在看到结果后修改。
> 前置 Gate: Stage 1 Implementation Freeze = PASS；Stage 2 Six-Task Smoke = PASS。

## 1. 协议身份

- protocol: `SQI_FORMAL_QUALIFICATION_PROTOCOL_V1`
- qualification_id 规则: `SQI-FORMAL-<model-tag>-<date>`
- 依据: `structured-query-interface-contract-v1.md`（FROZEN）、implementation seal、
  six-task smoke review（PASS）。
- R1/R2 结果仅作相邻历史协议基线，不合并为同一重复、不伪装成本次 arm。

## 2. Arm 定义（冻结）

| Arm | 能力 | 禁止 |
| --- | --- | --- |
| `native` | 只读仓库 + 常规文件工具（read/grep/glob） | 调用 SQI adapter；接触任何 SQI envelope/evidence id |
| `sqi` | 只读仓库 + 常规文件工具 + SQI CLI（6 个 canonical calls，envelope 原样返回） | 绕过 envelope 直接查 DB；调非 canonical 查询 |

两 arm 使用相同 model/config/prompt 骨架；差异仅为 SQI 工具的可用性与
SQI arm 的 `Evidence Used:` citation 要求（继承 R2 协议）。`bundle.explain`
预算池、截断语义按 Contract V1，不放宽。

## 3. 任务与重复数（冻结）

- Tasks: SQI-T01..T06（FROZEN，anchor/ground truth 不变）。
- 每任务 × 每 arm × **3 repetitions**（固定顺序 T01→T06，rep 升序）。
- 共 36 个正式 cell（6 任务 × 2 arm × 3 reps）。
- 每 repetition 独立 session，禁止跨 rep 复用上下文。

## 4. Model / Runtime（冻结后不得漂移）

- agent runtime: `claude` CLI（本机可用，版本记录于每条 run record）。
- model id 与 CLI 版本在 protocol freeze 时写入
  `formal-protocol-config.json` 并 seal；batch 中途不得更换。
- timeout/上下文上限沿用 R2 harness 默认（900s/session），写 run record。

## 5. Oracles（冻结）

1. **task success oracle**: 按 frozen ground truth 判定（T02: 5 production
   callers 覆盖 + 2 处源码验证；T03: 6/6 resolved refs 无多报；T04: 49/1031/
   wide_impact 全对且无符号级断言；T05: R2 语义不变；T06: 预算合规 + 截断诚实
   陈述）。自然语言断言由 evaluator 依据 frozen 关键锚点机械比对 + 人工复核记录。
2. **evidence-use oracle**（仅 SQI arm）: `Evidence Used:` 引用闭包 ⊆ 该任务
   全部调用返回的 `returned_evidence_ids`；被引用 ids 必须支撑对应 claim
   （fact 绑定比对），unsupported claim 单独计数。
3. **source-verification oracle**: 5 类语义断言（定义语义/调用点语义/reference
   用途/下游影响/文档等价）必须有对应源码读取事件（events.ndjson tool 事件），
   且断言文本与读取内容一致；结构性事实允许直接引用。
4. **capability-failure oracle**: 仅当失败可因果归因于 SQI 输出（错误 fact、
   错误 evidence 绑定、越界 impact、预算违规、静默截断）时记 `SQI capability
   failure`；环境/依赖/模型行为/fixture 问题按 attribution 分类，不算 capability
   failure。

## 6. 指标（冻结）

- Correctness: task success、required evidence coverage、unsupported claims。
- Evidence: returned ids、used ids、citation closure 合规率。
- Retrieval path: SQI 调用次数、source-read 次数、grep/search 次数、总 tool 调用。
- Cost: input/output tokens、SQI payload bytes、source-read bytes（harness 可测
  项；不可测项标 `measurement unavailable`，禁止估算冒充）。
- Performance: SQI query latency（envelope 内）、session 时长。
  性能不作唯一 verdict 依据。

## 7. Verdict 规则（冻结）

- 每 cell 独立判定 machinery PASS（schema/contract/determinism）后，任务结果
  才进入比较。
- 主判定为**分组比较描述 + 置信区间**，不设"必须全面更优"门槛；但以下任一
  情况直接阻断 QUALIFIED：
  a) 任一 arm 出现不可归因 infrastructure failure > 1/3；
  b) SQI arm 出现 ≥1 个确认的 capability failure 且未被 smoke 复现排除；
  c) oracle 无法机械判定。
- 结论限定 Contract V1 scope：Windows 11、冻结 commits、单机、6 任务、3 reps、
  单 model；不外推。

## 8. Attribution 与停止条件

沿用主线纪律：task failure ≠ capability failure；frozen asset defect、
oracle 不可靠、arm 不可比、model/config 漂移、evidence provenance 不可信
→ 立即停止正式 batch，保留结果，产出 attribution review，禁止现场修复后混跑。

## 9. 执行前置检查（batch 启动前逐项勾选）

1. Contract seal 7/7、implementation seal 5/5 round-trip PASS；
2. six-task smoke = PASS（当前 run）且 seal 后 implementation 无变更；
3. `formal-protocol-config.json` 已 seal（model id、CLI 版本、timeout）；
4. formal runner/evaluator 实现完成并建立次级 seal（bridge + evaluator +
   harness 集成文件）；
5. results 目录无同名 run；磁盘/依赖可用。

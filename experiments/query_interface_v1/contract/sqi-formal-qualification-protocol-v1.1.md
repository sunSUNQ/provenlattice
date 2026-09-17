# SQI Formal Qualification Protocol — V1.1 Amendment

> 状态: **V1.1 AMENDMENT FROZEN**（2026-09-17）。
> 本文件是 `sqi-formal-qualification-protocol-v1.md`（V1，仍 FROZEN，原文不改）的
> 修订附录。它把正式批后发现的三类问题转为**下一版实验的前置冻结规则**；
> 不改写 V1 的任何 verdict，也不重新定义既有成功标准。
> 生效范围: 本 amendment 冻结之后启动的所有 formal run（V1 batch 的 evidence 原样保留）。

## A1. Sandbox isolation（新增，冻结）

正式 session 的 agent 只允许访问:

1. 其运行所在的 benchmark repository 子树（session cwd）；
2. 经 `--allowedTools` 冻结授权的 SQI bridge 进程（仅 SQI arm）；
3. 无其他文件系统或框架路径访问。

执行分两层:

- **预防层**: `--allowedTools` 采用路径作用域规则——native:
  `Read(./**),Grep(./**),Glob`；sqi: 同上加
  `Bash(python -m experiments.query_interface_v1.tools.sqi_cli *)`。
  已于 2026-09-17 实证:越界读取返回 DENIED，cwd 内读取正常。
- **检测层（enforcement of record）**: `tools/sqi_isolation.py` 对 session
  events 做确定性扫描，任何指向 repo 根之外（尤其 ProvenLattice checkout、
  experiment 框架目录、frozen database）的 read/grep/glob/shell target 记为
  `CHECKOUT_LEAKAGE` policy violation → 该 cell invalid，并按 §7 归因。
  sanctioned bridge 调用不计为 leakage。

V1 batch 中 16/36 cells 存在 checkout 读取（集中在 T04 双 arm）——按 V1 定义
不构成 arm contamination，本 amendment 使其在后续 batch 中成为可预防、可检测、
可判 invalid 的硬违规。

## A2. T05 fixture repair（V1.1 amendment）

V1 fixture 声明 `database = knowledge database`，但 `required_evidence_ids`
只含 code database 铸造的 `E-CODE-9cec5b84…`——声明与 evidence source 不一致。

V1.1 修复（已写入 `tasks/SQI-T05.json`，由 amendment seal 固定）:

- 新增 `code_database = benchmark-analysis/v0.2-db/brpc.db` 声明；
- `required_evidence_ids` 扩展为两个 id，并给出
  `required_evidence_ids_by_database` 分库明细:
  - code_database: `E-CODE-9cec5b84fb52b556c0c332c9`（symbol.lookup 的
    CODE_DEFINITION evidence）；
  - knowledge_database: `E-XLINK-3284c4dde04ede3b45992a17`（code.related 的
    CROSS_LAYER_LINK evidence）；
- 两个 id 均于 2026-09-17 对 frozen DB 只读实测核验；
- 成功标准不变（"cites the cross-layer/evidence id"）；session 返回任一
  分库 id 即满足。

## A3. Oracle normalization 前置冻结（V1.1）

以下规则自本 amendment 起属于 oracle 的冻结部分（evaluator
`SQI_FORMAL_ORACLE_V1.1` 已实现），后续 batch 不得再出现批后归一化 flip:

1. 符号拼写等价: `a::b` 与 `a.b` 视为同一限定名；允许末 1–2 个 dotted
   segment 匹配（agent 可合理使用 class::member 尾部拼写）；
2. 路径分隔符等价: 源码读取 target 匹配统一 `\` / `/` 归一；
3. T06 的 bundle 机制检查仅适用于 sqi arm（native 无 bundle 调用）；
4. T05 evidence 判定按 A2 的分库明细执行；
5. V1 batch 的 16 个 flip cell 已按上述规则全量重评（V1 evaluation 原样保留
   于每 cell，`evaluation-v11.json` 为判定依据），重评结果记录于
   `results/formal/SQI-FORMAL-20260917-1/formal-synthesis-v1.json`。

## A4. Seal 关系

- V1 contract freeze seal（7 文件）保留为历史记录；其中 `tasks/SQI-T05.json`
  条目自本 amendment 起为 superseded（preflight 按此豁免并核验其余 6 项）；
- `contract/sqi-v1.1-amendments.sha256` 固定: 修订后的 `tasks/SQI-T05.json`、
  本文件；
- implementation seal 与 secondary seal 随 evaluator/runner/测试更新重制；
- 任何后续 formal run 启动前，preflight 必须全部 PASS（含 amendment seal）。

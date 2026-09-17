# SQI Formal Qualification Protocol — V1.3 Amendment

> 状态: **V1.3 AMENDMENT FROZEN**（2026-09-17）。
> 依据: `reviews/c4-attribution-review.md`——C4 两次尝试（-1 启动崩溃、-2 全量
> CHECKOUT_LEAKAGE/36 failed + rocksdb 工作树 330 文件删除）全量 INVALID/EXCLUDED。
> 本 amendment 只修改 **evaluation/isolation contract**；不重写 SQI-V1/V1.1
> standing evidence（`SQI-FORMAL-20260917-1` 仍为 SQI-V1 = QUALIFIED 的
> standing batch），C4 成本结论必须在 V1.3 re-sealed environment 下重新建立。

## A1. Blocker closure 1 —— 绝对路径 bootstrap 注入【必须修】

- formal runner 为**每个 session**生成 arm prompt，其中直接注入：
  - bridge 的**绝对命令行**（`python <abs>/sqi_cli.py --database <abs frozen db>
    --commit <sha> --call <call> --arg ...`）；
  - `--code-database <abs>`（任务声明时）；
  - 冻结 commit、任务 id、隔离边界声明。
- 验收（Gate 1 Bootstrap seal）：双 arm 从冻结 prompt 正常启动；SQI session
  **无需任何**对合同/quarantine/transcript/框架目录的探索即可完成一次合法
  bridge 调用；session 内 "bootstrap 探索类" 事件（搜索 sqi_cli/*.db/env）= 0。

## A2. Blocker closure 2 —— scanner pattern/path 语义分离【必须修】

- `grep` 事件的 target 是 **pattern**，不再做 abspath 根外判定；仅当 pattern
  或命令文本引用框架路径/hint（provenlattice、benchmark-analysis、
  query_interface_v1、sqi_cli、.claude、quarantine 等）时判 leakage；
- `glob` 事件 target 为 pattern：仅当含框架 hint 或指向 repo 根之外的绝对路径时判 leakage；
- `read` target 为真实路径：根外判定照旧；
- `shell` 命令文本：sanctioned bridge 调用豁免；其余按 hints + 根外路径判定。
- 验收（Gate 2 Scanner seal）：合法 pattern corpus（V1.1/V1.2 session 中出现
  的真实代码检索 pattern）= **0 false positive**；冻结越界 corpus（V1.1/C4
  session 中真实越界事件）= **100% 捕获**。

## A3. Blocker closure 3 —— bridge fail-closed【必须修】

- `--database` / `--code-database` 指向**不存在**的路径 → 结构化错误
  `DATABASE_NOT_FOUND`（exit 2），**不创建任何文件**；
- 指向非 SQLite 文件或意外 repo 内路径 → 同样拒绝；
- 验收（Gate 3 DB-path seal）：不存在/错误/repo 内意外路径全部拒绝且
  filesystem 零新增文件（单测 + 会话级断言）。

## A4. Blocker closure 4 —— 写路径硬隔离【最高优先级，必须修】

- **预防层**：formal session 的工具面收窄——native arm 无 Bash；sqi arm 的
  Bash 仅限 bridge 前缀；Edit/Write/MultiEdit/NotebookEdit/Web* 全部 disallow；
  permission 模式调整以保证未列出的 Bash 命令被**执行前拒绝**（Gate 4 实证）；
- **检测层**（保留为第二道 seal）：per-cell `git status --porcelain` +
  `git diff HEAD --stat` 前后比对 + HEAD 校验（V1.1 harness 机制 + runner
  强化）；
- 验收（Gate 4 Write-isolation seal）：adversarial smoke 主动要求
  Write/Edit/Delete repo 文件 → **执行前被拒**；事后三仓 HEAD + clean +
  fingerprint 不变。

## A5. 五道 Gate（全绿才允许新的 C4 formal batch）

| Gate | 内容 | 证据 |
| --- | --- | --- |
| G1 Bootstrap seal | 双 arm 从注入 prompt 正常启动；SQI 零 bootstrap 探索 | live session 记录 |
| G2 Scanner seal | corpora 双向 0 FP / 100% 捕获 | 确定性测试 + corpus 结果 |
| G3 DB-path seal | fail-closed 全通过、零文件创建 | 确定性测试 |
| G4 Write-isolation seal | adversarial 写请求执行前被拒；三仓 HEAD+clean+fingerprint 不变 | live session + git 校验 |
| G5 Arm usability requalification | 小型非 formal smoke matrix：双 arm 完成冻结任务路径、bridge 可用、bootstrap 不被切断 | live session 记录 |

5/5 PASS → 输出 seal evidence → **自动启动一次**新的 C4 formal rerun
（新 batch id，从 clean frozen checkout 开始，不得复用 attempt-2 workspace）。
任一 gate FAIL → 不得进入 C4。

## A6. 纪律

- V1.3 修改的是 evaluation/isolation contract；**不得静默重写 SQI V1.1
  standing evidence**；
- 两次 C4 尝试保持 INVALID/EXCLUDED/COST CONCLUSION NOT ESTABLISHED；
  第二次 36/36 不计为 SQI capability failure，不用于成本统计；
- C4 成本结论必须基于 V1.3 re-sealed evaluation environment 重新建立；
- 本 amendment 之后仍适用：任一 floor breach / blocker → 停止并归因。

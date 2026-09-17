# C4 Batch Attribution Review — STOP / INVALID BATCH

Attribution date: 2026-09-17
Batch: `SQI-FORMAL-C4-20260917-2`（36/36 cells **failed** — 全量无效）
前次尝试: `SQI-FORMAL-C4-20260917-1`（启动即崩，0 cells，runner defect）
状态: **C4 停止。正式成本结论 NOT ESTABLISHED。** V1.1 baseline batch
（`SQI-FORMAL-20260917-1`）仍是现行 SQI-V1 = QUALIFIED 的 standing evidence。

## 1. 两次尝试的事实

### 尝试 1（-1）：启动即崩，0 cells
`run_cell` 的 CHECKOUT_LEAKAGE 接线引用了未初始化的 `violations`（C3 缺陷，
formal runner 的 cell 路径无端到端测试覆盖）。**0 个 cell 产生数据**；修复
（初始化顺序 + 新增 stub-adapter 端到端回归测试）后 tests 57/57 PASS、
verify_release PASS。无正式证据受影响。

### 尝试 2（-2）：36/36 failed，全量 CHECKOUT_LEAKAGE
所有 cells `status=failed`。**无有效 formal cell**；floor 无法评估。

## 2. 归因（按冻结分类）

### (a) Runner/protocol 设计缺陷 —— C3 hardening 的副作用【主因】
V1.1 amendment 的 sandbox（`Read(./**)` 路径作用域）生效后，**agent 无法再
自行发现** bridge 绝对路径、frozen database 绝对路径与任务元数据：arm prompt
只给了 `--database DB` 占位符。V1.1 batch 的 agent 依赖无限制的 Read/Glob
完成 bootstrap（找到 benchmark-analysis 路径等）；C4 中这条路被切断，SQI arm
的 agent 大规模 `ls/find/glob` 搜索 `sqi_cli`、`*.db`、环境变量——bootstrap
失败级联为全 cell 失败。**C3 hardening 未重新验证 arm 可用性，属 C3 缺陷。**

### (b) 检测层缺陷 —— leakage scanner 误报【放大器】
scanner 将 grep/glob 的 **pattern 字符串**（如 `error_cstr`、`class
DownloadEngine`）当作路径做 abspath 判定 → 大量 repo 内合法 grep 被误报
（native arm `grep:error_cstr` 等）。scanner 需要区分 pattern 与 path-like
target（read/glob 的 target 是真路径；grep 的 target 是 pattern；shell 命令
按文本 hints 检查）。

### (c) Agent 行为 —— 检测层按设计正确捕获【真实但非主因】
部分 SQI agent 确实尝试读取合同、任务 JSON、quarantine、`.claude` transcripts、
环境变量（如 T05.sqi.r1 对空 `DB` 文件做了大量 od/strings/grep 分析——该空
DB 是同 session 早期用错误路径参数创建的空库）。这些被 scanner 正确标记，
属 protocol V1.1 amendment 预期行为，但加剧了 cell 失败。

### (d) 附带发现 —— **benchmark repo 遭 agent 破坏性删除（最严重隔离发现）**

`SQI-T04.sqi` 的 session 中，agent 在 rocksdb 仓库内执行了破坏性操作：
**330 个 tracked 源文件被从工作树删除**（`db/`, `file/` 等目录），属
`POLICY_VIOLATION:WORKTREE_MODIFIED`，被 per-cell git 检查捕获、cell 判 failed
（检测层按设计工作）。已从 git index 完整恢复（frozen commit `37234200…`
完好，恢复后工作树 clean），无证据污染。三仓均复核 head 与 clean 状态。
该事件证明 V1.1 amendment 的 `Read(./**)` 预防层**不足以阻止破坏性写路径**
（Bash 类工具在 dontAsk 模式下未被路径约束），V1.3 必须升级为：
`--disallowedTools` 收紧 + 只读会话强制（如 `--permission-mode plan` 或
per-tool deny 规则），并对 repo 工作树做 per-cell 前后哈希校验。

### (e) 附带发现
bridge `--database` 指向不存在路径时，sqlite3.connect 会**创建空 DB 文件**
（三仓遗留物即由此产生，V1.1 batch 已隔离一批；C4 尝试 2 又产生新的）。
V1.3 应让 bridge 拒绝不存在的 database 路径。

## 3. floor / 成本评估状态

- **不可评估**：0 个有效 cell；correctness floor 与成本对比均无数据支撑。
- SQI-V1 = QUALIFIED（V1.1 baseline batch）不受影响，仍是 standing evidence。
- 本 batch（-2）与尝试 1（-1）全量保留，标记 INVALID/EXCLUDED，不混入任何结论。

## 4. 修复方案（需 V1.3 amendment + 重 seal 后才能重跑 C4）

1. **arm prompt per-session 具体化**：runner 将绝对 `--database`、
   `--code-database`、bridge 命令行直接注入 session prompt（消除 bootstrap
   搜索需求）；prompt 模板变化走 V1.3 amendment + seal；
2. **scanner 修正**：grep/glob target 按 pattern 语义处理（仅在 shell 文本或
   真 path-like read target 上做根外/框架路径判定）；补误报回归测试；
3. **bridge 拒绝不存在的 database 路径**（消除空 DB 文件创建）；
4. **写路径硬隔离**：agent 会话强制只读（per-tool deny / 工作树前后哈希
   校验），防止 V1.1 batch T04.sqi 类 330-file 删除事件重演；
5. 三项全部 re-seal 后重跑 C4（36 cells）；V1.1 baseline 仍为 before 参照。

## 5. 证据处置

- `SQI-FORMAL-C4-20260917-2`：全量保留，标记 INVALID/EXCLUDED（本文件）；
- `SQI-FORMAL-C4-20260917-1`：保留（0 cells，启动崩溃记录）；
- 三仓新遗留空 DB/文件：已隔离至 `quarantine-v1.1-agent-artifacts/`（追加）；
- V1.1 baseline batch：不动，仍为 standing evidence。

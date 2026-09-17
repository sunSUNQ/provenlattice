# SQI Formal Qualification Protocol — V1.4 Isolation Contract

> 状态: **V1.4 ISOLATION CONTRACT FROZEN**（2026-09-17，C4 attribution review 之后）。
> 依据: `reviews/c4-attribution-review.md` §7——CLI flags 层（allowedTools /
> permission-mode / Read 作用域）被证伪为隔离边界；用户裁决 V1.4 采用
> OS/container-level sandbox + per-session disposable checkout，
> Prevention = validity boundary，Detection = audit/seal。

## A1. 平台边界发现（2026-09-17，实测）

| 项 | 结果 |
| --- | --- |
| Docker | 未安装 |
| WSL2 | 未安装 |
| Windows Sandbox | 查询需提权（当前 shell 非管理员） |
| 当前 shell 管理员权限 | 否 |
| 结论 | **OS/container 级读不可见（I1-I3 的"不可见"语义）在本机当前无法实现**——安装 Docker Desktop / WSL2 / 启用 Windows Sandbox 均需管理员操作，只能由用户执行 |

因此本 contract 将 V1.4 gate 判定按可达性分层，**不降级、不虚报**：

- **I4 Write Integrity / I6 Functional Usability**：本机可实现 kernel 级预防
  （NTFS deny-ACL，见 A2），按原标准判定；
- **I1 Visibility / I2 Parent Escape / I3 Transcript Escape / I4 Cross-repo 的
  读不可见部分**：同用户进程无法在 NTFS 上实现默认拒绝读——按
  "platform-boundary FAIL（文档化）"判定，不宣称 PASS；
- 其中**最高价值的读泄漏向量**（formal ground truth、contract/tasks、
  results/formal、quarantine、.claude transcripts）可通过会话期 deny-READ ACL
  实现真预防（empirically 验证 claude CLI 在该 deny 下是否可用，见 A3）。

## A2. 可实现的硬隔离层（本 contract 冻结）

每个 formal cell 启动前：

1. **Disposable repo copy**：将 frozen benchmark repo 复制到 per-cell 沙箱根
   （不含 .git）；agent 的 cwd = 副本；cell 结束后丢弃。frozen original
   **永不作为 agent cwd**。
2. **Deny-write ACL（kernel 级写预防）**：session 期间对以下 frozen 资产设置
   `icacls /deny <user>:(WD,AD,WA)`（递归）：
   - frozen benchmark repo 原件（三仓）；
   - 四个 frozen graph/knowledge DB；
   - `repositories.lock.json` / seal 文件所在 contract 目录；
   session 结束后移除 deny 并复核 HEAD + 工作树指纹不变。
3. **Deny-read ACL（高价值 artifact 读预防）**：session 期间对
   `experiments/query_interface_v1/tasks/`、`contract/`、`results/formal/`、
   `results/implementation-smoke/`、quarantine 目录设置
   `icacls /deny <user>:(R)`——agent 对这些路径的读取将被**内核拒绝**
   （实测 claude CLI 存活性；若 CLI 因 deny 损坏则该项降级为文档化 FAIL，
   不静默）。
4. **Detection 层保留**：CHECKOUT_LEAKAGE scanner + per-cell git
   status/diff/HEAD 校验照旧（第二道审计 seal）。
5. **恢复纪律**：session 结束后必须移除全部 deny ACL 并复核三仓
   HEAD/clean/指纹；任何恢复失败 → 立即停止并归因。

## A3. Gate 判定语义（V1.4）

- **I5 Write Integrity**：adversarial 写探测被 ACL 拒绝（0 次成功变更）+
  disposable copy 可写 + frozen 指纹不变 → 可 PASS；
- **I6 Functional Usability**：双 arm 冻结任务路径可用（bridge + 读）→ 可 PASS；
- **I1/I2/I3/I4-读部分**：宿主机同用户读不可见在本平台不可实现 →
  判 `platform-boundary FAIL`，并在 evidence 中给出**已拒绝的探测清单**
  （ground truth/contract/results 的读探测确实被拒）与**仍可读的宿主路径**
  （平台边界）；不得宣称 PASS；
- **总判定**：V1.4 Isolation Qualification = PASS 仅当 I5 + I6 PASS **且**
  I1-I4 的 platform-boundary FAIL 已被用户接受为环境升级前置；在用户完成
  Docker/WSL/Sandbox 安装前，C4 formal batch 保持 NOT ESTABLISHED。

## A4. 与既有证据的关系

- SQI-V1 = QUALIFIED（V1.1 baseline batch）不变；
- C4 三次尝试保持 INVALID/EXCLUDED；
- 本 contract 不修改 V1/V1.1/V1.2/V1.3 已冻结的任何成功标准；
- 后续若用户完成 OS 级隔离环境安装，V1.4 gate 可按 A3 全量重判。

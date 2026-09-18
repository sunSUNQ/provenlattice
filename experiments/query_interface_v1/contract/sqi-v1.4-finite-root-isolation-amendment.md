# SQI-V1.4-Windows Finite-Root Isolation Profile — Amendment

> 状态: **FROZEN**（2026-09-18，用户裁决：no-reboot profile 技术上足以支撑
> C4，按本文范围冻结）。
> 依据: `results/v14-gates/feasibility-noreboot-evidence-v1.json`
>（verdict FEASIBLE，全 gate PASS）+ `reviews/v1.4-noreboot-feasibility-review.md`。
> 本 amendment 不修改 V1/V1.1/V1.2/V1.3 任何已冻结成功标准；它冻结的是
> **本宿主机上 formal cell 的隔离机制与威胁模型**。

## §1. 威胁模型（冻结，范围从窄）

本 profile 证明并提供的是 **experiment-artifact isolation（有限敏感根）**：

> formal-session agent 无法读取任何可能污染实验结论的 ProvenLattice
> 敏感资产（task fixture、frozen contract、formal results、reviews、
> 实验框架源码、.git、历史 transcript / 历史 agent outputs）。

**明确不声称** full OS namespace isolation：宿主上其余路径对同用户进程
仍然可见，属于文档化的 out-of-scope（原 benchmark DB 内容与 runtime 字节
副本相同，是被授权的 bridge 基质，亦属 out-of-scope）。

内核拒绝（DENY）根：

| 根 | 权限 |
| --- | --- |
| `D:\ChatGPT\codegraph\provenlattice\`（整个 checkout） | `(OI)(CI)(RD)` deny |
| `%USERPROFILE%\.claude\projects\`（历史 transcript store） | `(OI)(CI)(RD)` deny |
| 三个 frozen benchmark repo 原件 | `(OI)(CI)(WD,AD,WA)` deny |
| 四个 frozen DB 原件 | `(WD,AD,WA)` deny |

读 deny 采用 `(RD)`（read data / list directory）而非 generic `(R)`：
内容读取与目录枚举同样被内核拒绝，但保留 READ_CONTROL，保证
`icacls /remove:d` 恢复通道永不失效（finding P7：`(R)` 间歇性令
`/remove:d` 自身 rc=5 失败且不可自愈；`(RD)` 5/5 稳定）。

## §2. Formal cell 生命周期（冻结）

每个 formal cell：

1. **Sanitized runtime**（`D:\pl-c4-runtime\`，一次性构建、逐批校验）：
   bridge 代码副本（与 checkout sha256 一致）、frozen DB 字节副本、
   per-cell disposable repo 副本（无 `.git`，内容数校验，P6 修复后）。
   agent cwd = disposable copy；bridge/DB 一律使用 runtime 副本。
2. **Deny window**（`tools/v14_c4_lifecycle.py::CellWindow`，fail-closed）：
   进入 cell 前按 §1 施加单可继承 ACE deny（P1/P2：`/deny ... /T` 无法
   传播，`/remove:d` 一步恢复），并验证窗口闭合（checkout README /
   tasks fixture / .git HEAD 探针全部 ACCESS_DENIED，否则中止）。
3. **会话执行**：session env 的 `PL_SQI_*`/`PYTHONPATH` 全部指向 runtime；
   arm prompt 为冻结模板注入 runtime 路径；allowedTools 按 V1.3 arm 定义。
   已知 CLI 行为约束（P4/P5）：red-team / 探测类会话使用模块形式命令与
   中性 ARM 风格 system prompt。
4. **Detection 层照旧**：path-scoped allowedTools、CHECKOUT_LEAKAGE
   scanner（有限根分类：SENSITIVE = 引用 runtime 之外的路径）、
   per-cell git status/diff/HEAD。
5. **Restore 纪律**：cell 结束移除全部 deny ACE，验证读取恢复 +
   三仓 HEAD/dirty 不变 + 四 DB sha256 不变；任何失败 → 立即停止并归因。

## §3. Per-cell PASS 语义

一个 formal cell 的隔离判定 PASS 当且仅当：

- CellWindow 进入时窗口闭合验证通过；
- 会话期间敏感根探针（runner 侧或 red-team 会话内）为 ACCESS_DENIED；
- CHECKOUT_LEAKAGE scanner 对该会话 raw 事件中 **SENSITIVE 计数为 0**
  （runtime 内部绝对路径引用文档化，不算泄漏）；
- CellWindow 退出时 restore integrity 验证通过。

## §4. 对既有 V1.4 记录的修正（correction）

- `results/v14-gates/gate-evidence-v1.4.json` 中 I1 探针结果
  （`ground_truth_denied: 0`，即三个 ground-truth 探针实际可读）为**权威
  记录**；`reviews/v1.4-isolation-qualification-review.md` 正文中
  "I1 3/3 denied probes / ground-truth artifacts kernel-denied" 的文字
  结论**予以撤回**——根因见 P1（`icacls /deny (R) /T` 在 deny 调用者后
  无法传播）。旧 review 文件头部已加 correction banner。
- V1.4 Isolation Qualification = **PARTIAL**（platform-boundary 记录）
  作为历史判定**不变**；本 amendment supersede 的是**隔离实现方式**
  （从"等待 OS 级虚拟化"改为"有限根 kernel deny"），不是 V1.4 的
  成功标准语义。
- `v14_sandbox.build_disposable_copy` 的 robocopy 缺陷（P6）已修复并附
  回归测试；V1.4 I5 的历史 verdict 不受影响（"disposable copy writable"
  在空副本上亦成立）。
- **Secondary seal 单文件重封（2026-09-18）**：
  `test_sqi_formal_wiring.py::test_base_command_identical` 存在陈旧断言
  （期望 `.py` 路径形态的 bridge 引用；允许列表与 arm prompt 自
  commit 2287623 起已冻结为模块形态 `python -m ...sqi_cli`，该断言自那时
  起在 HEAD 上即失败，verify_release 未再运行故未被发现）。断言已对齐
  冻结常量 `sqi_allowed_tools()`；`structured-query-interface-contract-v1.
  secondary-seal.sha256` 中该文件条目随之单行重封。其余 9 个 sealed 文件
  未动。

## §5. C4 授权

在 amendment seal PASS + 代表性 T01/T05 确认重跑无回退之后：

> **C4 Attempt-4 — 36-cell Before/After Formal Qualification 正式解锁**，
> 按本 profile 的 per-cell 生命周期执行；成本优化结论仍以 batch 结果为准。

## §6. Sealed artifacts

seal 文件：`sqi-v1.4-finite-root-isolation-amendment.sha256`（格式与既有
seal 一致，`verify_seal()` 可验），覆盖：

- 本 amendment 文档；
- `tools/v14_c4_lifecycle.py`（window lifecycle）；
- `tools/v14_feasibility_noreboot.py`（可行性 gate runner，机制实现源头）；
- `tools/v14_sandbox.py`（P6 修复后版本）；
- `tests/test_v14_finite_root_profile.py`（回归测试）。

# ProvenLattice SQI-V1.2 — Cost Optimization Qualification（首发正式版）

发布日期：2026-09-20
Tag：`provenlattice-sqi-v1.2`
Verdict：**QUALIFIED / RELEASE READY**（9/9 frozen capability floors PASS）

SQI-V1.2 是结构化查询接口（SQI）的成本优化资格版本：在保持 SQI-V1/V1.1
全部能力与证据纪律的前提下，通过 OPT-T05 压缩与 V1.2-NR1/NR2 通用机制，
将 Agent 检索成本相对 V1.1 baseline 大幅下降，并在完整 clean 36-cell
batch 中首次以单 backend 达成 SQI 18/18。

## 1. 能力范围（本版本正式声明）

- 六类冻结任务（SQI-T01..T06，跨 aria2 / brpc / rocksdb 三真实仓）：
  符号定位、调用者/被调用者、引用状态、变更影响边界、需求→代码证据
  （跨库复合）、截断诚实性——**SQI 18/18**，citation closure 18/18，
  unsupported claims 0。
- 结构化查询能力保持稳定：byte-identical envelope for identical call
  signatures（检索层确定性），budget 截断为确定性前缀切片，`omitted_counts`
  诚实报告，session usage discipline 随首 envelope 发射。
- C1–C4 成本优化实现全部落地：OPT-T05 envelope 压缩 + 会话缓存、成本归因、
  NR1 完成/重复调用纪律、NR2 空结果探索稳定性修复。

## 2. 资格证据（C4-R4，`SQI-FORMAL-C4-20260920T093328Z`）

```text
36/36 cells completed · 0 halts · 零 sensitive leakage
单 backend deepseek-flash x36 · 逐 cell model provenance · backend_verified
SQI 18/18（T01-T06 各 3/3）· citation closure 18/18 · unsupported claims 0
9/9 frozen floors PASS（sqi_18_of_18 / t02 / t04 / citation_closure /
    unsupported_zero / machine_checks / source_verification /
    no_new_violations / single_backend）
isolation baseline 27e40df5… 不变（window closed / restore verified /
    fingerprint unchanged，逐 cell）
```

## 3. 成本结果（vs V1.1 baseline，`SQI-FORMAL-20260917-1`）

| 指标 | V1.1 baseline | SQI-V1.2（C4-R4） | Δ |
| --- | --- | --- | --- |
| input tokens | 962,640 | 616,598 | **-36%** |
| output tokens | 230,508 | 97,249 | **-58%** |
| cache-read tokens | 14,738,944 | 3,954,944 | **-73%** |
| cache amplification | 15.3× | 6.4× | **-58%** |
| SQI calls | 59 | 49 | -17% |
| envelope bytes | 517,226 | 384,049 | **-26%** |

## 4. 修复路线的完整性（失败→归因→通用修复→完整重资格）

C4-R3（17/18，HOLD/PARTIAL）的唯一负区 T05.sqi.r3 经机器归因为 agent 探索
噪声后，V1.2-NR2 以**四处通用机制**收口——无任务特判、无硬编码 required
id、无 oracle 变更：

1. 空 envelope 的 call-type-scoped 解析语义指导（`result_meta.
   empty_result_guidance`，所有查询类型，确定性内容）；
2. usage_discipline 第三条规则（与 prompt 镜像）；
3. 截断/换预算重查的子集条款（同 anchor 更小预算重查只能返回首 envelope
   的证据子集，冻结 DB 上 bundle/lookup 双路径实证）；
4. arm prompt 接口文档：code.related 是 knowledge-to-code 复合查询，
   bundle.explain 仅返回本地 bundle。

定向 ladder 4 轮失败全部机器归因并入档（protocol-deviation-note），第 5 轮
GREEN（T06 3/3 · T05 3/3 · SMOKE 4/4）后执行完整 C4-R4 重资格。C4-R3 的
HOLD/PARTIAL 与全部失败 ladder 原样保留为历史证据。

## 5. 验证状态

- **97/97 tests**（implementation + wiring + isolation + NR1/NR2 discipline）
- `verify_release.py` PASS（全部 7 项 seal + frozen databases 4/4）
- implementation / secondary seal 覆盖 NR2 改动文件并重封
- 复现入口见 `REPRODUCIBILITY.md`（一键验证 + 复现矩阵）

## 6. 已知边界与明确未包含

- V1.1 baseline 运行于混合 backend（deepseek-flash + deepseek-v4-flash），
  跨时代 token 对比带残留 caveat；C4-R4 自身为单 backend。
- Native 对照方差（T02/T04 native 0/3）为模型行为漂移，与 SQI 无关
  （同 batch SQI 臂全绿）；native 臂是对照而非认证面。
- 未包含：oracle/contract 语义变更、S3+ scale bands 与并发、第四个
  benchmark 仓库、Overlay V1.1、Runtime/Log evidence（路线图 V1.2，另线）。
- Envelope/prompt 语义此后任何变更须重走 seal + qualification 流程。

# ProvenLattice Core V0.4 — Branch & Session Overlay

生成日期：2026-09-10。V0.4 保持纯 Core 范围，实现共享 Base Graph、持久 Branch Overlay、临时 Session Overlay，不包含 Spec、Log、Commit Graph、Embedding、MCP、UI 或 TASCO。

## Contract

```text
Effective Graph = Base + Branch Overlay + Session Overlay
priority: Session > Branch > Base
```

Overlay 由 `overlay_id/type/repository_id/base_commit/base_generation/branch_name/parent_overlay_id/timestamps/status` 唯一描述。Base commit 或 generation 不匹配时进入 `REBASE_REQUIRED`。Overlay SQLite 只保存 Node、Edge、RawReference、Shard、BoundaryEdge 的 `ADD/UPDATE/DELETE`；DELETE 是 tombstone，不修改 Base。

所有核心 Query 统一通过 `GraphView` 合成。Base 查询仍使用 SQLite 索引，随后只应用小型 overlay lookup；不会为每个 Query 单独实现 merge，也不会在每次查询全量 materialize。

## Correctness

自动化测试覆盖：

- Branch/Session 优先级、DELETE tombstone、delete + recreate；
- session incremental apply、discard、commit-to-branch；
- worktree 路径不同但复用 Base repository identity；
- stale base commit/generation 与 rebase；
- `NO_CONFLICT`、`ENTITY_CONFLICT`、`DELETE_UPDATE_CONFLICT`、`ADD_ADD_CONFLICT`、`BOUNDARY_CONFLICT`、`REBASE_REQUIRED`；
- no-conflict merge 与 conflict rejection；
- Nodes、Edges、RawReferences、Shards、API fingerprints、BoundaryEdges/reverse index materialization parity；
- find symbol、definition、caller/callee/reference、dependency/dependent、boundary reference、subgraph 的 Overlay-aware 查询。

Base 不交给增量 writer。`apply_repository_overlay` 使用一次性临时 working snapshot 调用已有 incremental pipeline，退出前删除该 snapshot，Branch/Session 持久层只保留 Delta。

真实 B1/B2 Base DB 还执行了 lifecycle/conflict matrix：两个仓库的不同-shard修改均 `NO_CONFLICT` 合并；同 Stable Identity 修改均识别为 `ENTITY_CONFLICT`；API fingerprint dirty 与旧 boundary reference 组合均识别为 `BOUNDARY_CONFLICT`；session commit 后状态为 `DISCARDED`；base commit 不匹配均进入 `REBASE_REQUIRED`。兼容 rebase 只重算 1 个 shard，B1/B2 分别耗时 8.669/11.663 ms。

## Real Repository Baseline

三个 benchmark 均为单文件 body-only 修改，Directory shard 与冻结 Base 一致；真实仓代码只在临时副本中修改。

| Benchmark | Base DB | Branch Overlay | Overlay/Base | Session Overlay | Delta nodes | Shards touched | Apply | Parity |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| B1 aria2 | 132,984,832 B | 245,760 B | 0.1848% | 28,672 B | 72 updates | 1 | 2,312 ms | PASS |
| B2 brpc | 240,123,904 B | 135,168 B | 0.0563% | 28,672 B | 60 updates | 1 | 3,953 ms | PASS |
| B3 RocksDB | 884,084,736 B | 2,355,200 B | 0.2664% | 28,672 B | 1,067 updates | 1 | 15,014 ms | PASS |

该结果满足持久存储近似 `Base + Deltas`，而不是 `Full Graph × Branch Count`。首轮发现冻结 V0.2 DB 的 `shard_edges` 尚未回填；V0.4 增加一次性 schema migration 后重跑，避免把全部 boundary edge 误判为 overlay ADD。

## Query Latency

以下为 Symbol Query P50/P95，20 samples：

| Benchmark | Base | Base + Branch | Base + Branch + Session | Branch P95 overhead | Branch+Session P95 overhead |
|---|---:|---:|---:|---:|---:|
| B1 aria2 | 14.999 / 15.699 ms | 15.235 / 15.787 ms | 15.176 / 16.519 ms | 0.56% | 5.22% |
| B2 brpc | 24.210 / 24.527 ms | 24.284 / 25.989 ms | 24.286 / 25.060 ms | 5.96% | 2.17% |
| B3 RocksDB | 59.815 / 61.194 ms | 60.315 / 62.360 ms | 60.685 / 64.797 ms | 1.91% | 5.89% |

Overlay 查询开销在本轮三仓均低于 6% P95。数值是本机基线，不应解释为通用性能承诺。

## Merge/Rebase Boundary

Git 仍是 Source Merge Authority。ProvenLattice 只负责 Stable Identity 上的 Graph Delta conflict detection，以及 merge/rebase 后的局部 graph reconciliation。Rebase 先检查 overlay touched entities 在新 Base 是否变化；提供 rebased worktree 时，通过 incremental pipeline 重新解析变化文件、重新 resolution 并生成相对新 Base 的 Delta，同时统计 touched shard/boundary edge。不自动解决复杂源码冲突，也不递归重建 dependency frontier。

## Artifacts

- [`provenlattice-v0.4-overlay.json`](provenlattice-v0.4-overlay.json)：B1/B2/B3 原始结构化结果。
- [`provenlattice-v0.4-conflicts.json`](provenlattice-v0.4-conflicts.json)：B1/B2 lifecycle、merge、rebase 与 conflict matrix。
- [`../../benchmarks/run_overlay_baseline.py`](../../benchmarks/run_overlay_baseline.py)：可重复 benchmark runner。
- [`../../benchmarks/run_overlay_conflicts.py`](../../benchmarks/run_overlay_conflicts.py)：真实 Base conflict runner。
- `src/provenlattice/overlay.py`：Overlay store、GraphView、materialization、session/merge/rebase API。
- `tests/test_overlay.py`：V0.4 correctness 与 parity gate。

## Conclusion

V0.4 已证明多个 Branch/Session 能共享一个 Base，只持久化自身 Delta；Session > Branch > Base 合成确定、tombstone 正确，真实仓 body-only 修改只触及一个 shard，完整 materialization 与对应 FullIndex 结果一致。B1/B2 conflict matrix 也已通过；后续可扩大 rebase-after-main-advance 的样本与 timing 分布，不需要改变当前 Overlay contract。

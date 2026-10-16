# ProvenLattice Java 公开 Beta 发布就绪报告

**日期**：2026-10-15 · **HEAD**：`67a1fb5` → 本轮 commits（未 push）· **476 tests OK**
**裁定**：`PUBLIC_BETA_READY: YES` · `STABLE_RELEASE_READY: NO` · `INTERNAL_PREVIEW_READY: YES`

---

## 1. Phase 0 复核结论

- HEAD/提交链/476 tests 独立复核 ✅；G1–G6 维持 PASS。
- **审计口径勘误披露**：任务输入中 "187 个分类计数" 与实际数据不符——实际为
  **168 冲突抽样 verdicts（157 唯一站点）+ 225 新鲜样本行（223 唯一站点）**；
  新鲜与冲突抽样存在 **2 站点重叠**（两口径分别审计，判定一致，不影响独立性
  结论）；与历史 8 样本零重叠。
- 跨文件行号串扰缺陷已修复（file-keyed + LEFT JOIN + 回归测试），最终查询路径
  复核无同类问题。
- 旧冲突统计（38/101/4169）已在冲突重提取后由 27/76/789 取代，旧值在新报告中
  标注 superseded。
- 146/147 UNKNOWN 支持边界：跨文件类型流（97）与外部/JDK 类型流（49）——
  JDT 绑定仍提供，但独立真值不可建立。

## 2. Phase 1：真实构建产物安装与调用（全部实测）

| 步骤 | 结果 |
|---|---|
| wheel 构建 | `provenlattice-1.4.0-py3-none-any.whl` ✅ |
| 干净 venv 安装 | 5 依赖自动就位（含 tree-sitter-java）✅ |
| 无 JVM Java L1 索引 | hikaricp 112 文件 / 2062 节点 / 3918 resolved / 0 失败 ✅ |
| symbol 查询 | HikariConfig → 4 evidence ✅ |
| `java-semantic --status-only`（无 JDK env） | `unavailable / jdk_not_found` ✅ fail-closed |
| 配置 PL_JAVA_JDK + PL_JAVA_JDT_CLASSPATH | `available` ✅ |
| 手工 Classpath 清单消费 | 首次 **invalid（BOM）**→ 修复 manifest 读取容 BOM（utf-8-sig）+ 回归测试；重验 `available` ✅ |
| full 模式 | calls_resolved **4025**（与开发环境一致）、merge counts（27/714/3228/1248）、站点 provenance=`semantic:jdt-v1` + classpath 指纹、L1/JDT 对照可见 ✅ |
| **用户可区分 L1 vs JDT** | ✅（CLI 输出 status/provenance/fingerprint + L1 侧行 status/strategy/confidence） |

## 3. Phase 2：发布包与依赖检查

| 项 | 结果 |
|---|---|
| wheel 内容 | parsing/java.py、classpath.py、java_semantic.py、**java_semantic_driver/P2bDriver.java** ✅（本轮修复打包缺失） |
| Driver 干净环境编译缓存 | tempfile 目录，无开发者绝对路径 ✅ |
| JDT/JAR 分发边界 | **不分发**（EPL-2.0 等 license 由用户自备，文档说明）；不联网下载 ✅ |
| Maven/Gradle | 永不自动执行 ✅ |
| Classpath 错误 | fail-closed（invalid → 拒绝执行，BOM 修复后含记事本场景）✅ |
| JDK/OS 范围 | Windows + Temurin 21 已验证；**Linux: NOT_VERIFIED**；JDK 17-25 未全测（21 验证） |

## 4. Phase 4 回归

全量 **476 OK**（475 + BOM 回归）；Java L1/JDT/Classpath/merge/Python/C/C++/
默认 index/干净安装 smoke 全部覆盖（§2 即实测）；MCP frozen contract 零改动；
金样沿用（本轮零 resolver/schema 变更）。

## 5. 发布裁定

| 状态 | YES/NO | 依据 |
|---|---|---|
| **INTERNAL_PREVIEW_READY** | **YES** | 全部工程与产品化验证通过 |
| **PUBLIC_BETA_READY** | **YES** | 安装/调用/降级/文档/依赖边界均可复现；错误绑定风险已在三态+置信契约内显式管理；无未解决的关键错误确定绑定 |
| **STABLE_RELEASE_READY** | **NO** | 缺：Linux/JDK 范围矩阵验证、RQ1 formal、merge 持久化、/conflict 扩展人工审计、正式内存预算签收 |

## 6. 剩余风险与 BLOCKER

- **发布阻断项：无。**
- 非阻断：Linux NOT_VERIFIED；JDK 范围未全测；146 UNKNOWN 边界（已文档化）；
  query-time 结果不持久化；SCIP INFRA_BLOCKED；Maven/Gradle 自动发现未实施。

## 7. Java 能力摘要（纳入下一功能版本的建议）

L1：`.java` 默认索引 + 三态引用（R1 收紧后 0 已知错误确定绑定）；
可选：`java-semantic` JDT 精确解析（provenance/fingerprint/审计视图）；
P2-C classpath 契约；全部附带测试与真实仓库证据链（21 个提交）。

## 8. push/PR/release 推荐顺序（人工执行）

1. 人工评审本报告与 commit 链（42c6d89..HEAD，23 commits）；
2. push 单一 feature 分支 → PR（标题建议 "java: Phase 2 — L1 + optional JDT analyzer (public beta)"）；
3. CI 双平台绿后合入 main；
4. 打 tag（版本号人工决定）+ GitHub Release，附 `docs/java-overnight-longrun-v1-report.md`、
   `docs/java-phase2-p2e-final-qualification-report.md`、本报告；
5. Release notes 必含：**升级后执行一次全量 index**（CALL_KIND_VERSION 3）、
   JDT 可选能力配置说明、146 UNKNOWN 与 Linux NOT_VERIFIED 边界。

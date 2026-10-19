# ProvenLattice 1.5.0 — Java Public Beta

> **Pre-release（Public Beta）**：Java 能力为工程验证等级（local-only, diagnostic）。
> **未取得** RQ1 formal qualification；**非 Stable**。

ProvenLattice 1.5.0 新增 **Java 支持**：默认轻量确定性 L1 图层，加可选的
Eclipse JDT 精确语义增强（query-time）。

## Java L1（默认启用，无 JVM 依赖）

- `.java` 扫描/解析/符号/引用/调用建图，复用既有冻结 schema 与三态引用契约
  （resolved / ambiguous / unresolved）
- 安全收紧（R1）：receiver 类型不可知的实例调用不再产生启发式确定性绑定
  （候选完整保留，`demote_reason` 可追溯）——已知 8 个历史错误绑定形态全部
  修复，225 站点新鲜分层审计四模式 Wrong Resolution = 0
- 既有 Python/C/C++ 能力与行为不变（金样四表一致）

## Optional Eclipse JDT Semantic Analyzer（按需启用）

- `java-semantic` CLI：独立 JVM 进程按需运行，默认索引**永不启动 JVM**
- 跨文件方法精确绑定（含重载消歧、继承层级、JDK 类型）
- recovered（依赖缺失伪造）绑定过滤；歧义不升级为确定
- provenance `semantic:jdt-v1` + classpath 指纹 + `CALL_KIND_VERSION` 可追溯
- 结果为 **query-time 审计视图，不持久化到 L1 图谱**

## Classpath Manifest（手工配置）

```
# classpath.txt —— 一行一条；project:/dep: 角色；# 注释
project: C:\repos\my-app\src\main\java
dep: C:\libs\slf4j-api.jar
```

```bash
set PL_JAVA_JDK=C:\path\to\jdk-21
set PL_JAVA_JDT_CLASSPATH=C:\jars\org.eclipse.jdt.core.jar;C:\jars\...
provenlattice java-semantic <repo> --classpath-manifest classpath.txt --json
provenlattice java-semantic <repo> --status-only --json   # fail-closed 状态
```

## 升级（1.4.x → 1.5.0）

**必须执行一次完整 `provenlattice index`**（`CALL_KIND_VERSION 3` 使既有引用
缓存失效并自动重解析）。

## 验证与性能

- 479 项测试（Windows/Linux CI 双绿）
- 真实仓库：HikariCP 114 / gson 264 / jgit 1891 文件，零解析失败
- jgit：L1 索引 25.1s；JDT 批处理 8.1s（预算 ≤15s）；JDT RSS ~1.2GB（≤1.6GB）
- wheel/sdist（本 Release assets）：
  - whl `7ce708a593b8a39bcd2bbab2e3788fcf315ed25683a722e51a8bb62ffe5c391c`
  - tar.gz `8417a05eddf7af8d817ab5e0f96df2afd95ade9e1ebe267a2f37f7a7f4d9be46`

## 已知限制（Public Beta 边界）

- **Linux JDT：NOT_VERIFIED**（Linux CI 全量测试通过；JDT 可选步骤需配置
  classpath，未在 Linux 实际运行）
- **146 UNKNOWN**：跨文件/外部类型流站点无法建立独立真值，保守保留
- **query-time 结果不持久化**到 L1 图谱
- **RQ1 formal qualification 尚未取得**——不宣称 formal
- JDK 21（Temurin）已验证；其他 JDK 组合未测
- JDT 依赖（Eclipse JDT，EPL-2.0）由用户自备；Maven/Gradle 永不自动执行；
  SCIP Java INFRA_BLOCKED（官方移除 Windows launcher）

## 资产

- `provenlattice-1.5.0-py3-none-any.whl`（sha256 见上）
- `provenlattice-1.5.0.tar.gz`（sha256 见上）
- 证据链：`docs/java-support-implementation-plan.md` → longrun → readiness →
  P2-B/C → P2AD → P2-E → acceptance closure → postmerge validation（均在本仓库 docs/）

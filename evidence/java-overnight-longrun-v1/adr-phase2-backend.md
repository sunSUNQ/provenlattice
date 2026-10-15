# ADR-2026-10-15: Java Phase 2 语义后端技术路线

**状态**: ACCEPTED (based on T9-B empirical evidence, this longrun)
**输入**: evidence/java-overnight-longrun-v1/t9b/comparison.json + bench/t9a-summary.json + gold.json

## 决策

**JDT（org.eclipse.jdt.core）作为 Phase 2 可选语义增强后端的唯一候选，以完全可选、
独立进程、fail-closed 的 Analyzer 形态接入；SCIP Java 排除；JavaParser 排除。**

## 依据（全部为实测，无桌面推演）

1. **正确性**: JDT 21 项 gold 查询 20 CORRECT + 2 项 JLS 歧义**正确拒绝**（resolved=null
   + 显式编译诊断）；唯一偏差（缺失依赖 recovered binding）有确定性的调用方过滤手段
   （`ITypeBinding.isRecovered()`），过滤后 0 WRONG。
2. **JavaParser 排除理由**: 对双 on-demand import 歧义**静默错误绑定**（2/21 WRONG）。
   接入它会重新引入 P1 刚消除的 Wrong-Resolution 形态；为其补 JLS 歧义检测等于重造
   编译器前端，成本高于直接用 JDT。
3. **SCIP 排除理由**: 官方 v0.13.1 明确 "drop Windows launcher"（PR #970）——本项目的
   Windows 环境被官方放弃；其 Maven/Gradle-first 设计与"缺构建工具时优雅降级"要求冲突。
4. **L1 保持不变**: L1（tree-sitter + P1 守卫）在全部歧义场景保持 ambiguous 候选完整，
   是唯一零伪造组件。语义后端提供的是**召回增强**，不是安全替代。

## 十问回答

1. **L1 真实能力边界**: 无重载判定、无继承/泛型绑定、JLS 歧义保留为 ambiguous、
   外部类型 unresolved；jgit 实测 43.3% resolved / 29.9% ambiguous / 26.8% unresolved。
2. **需要编译器级语义的问题**: 重载消歧、继承方法绑定（含泛型擦除）、参数化类型、
   静态导入与歧义判定——JDT 实测全部 CORRECT。
3. **轻量静态规则可解**: 同文件绑定、import 路径、限定名匹配（L1 已做）。
4. **JDT 是否值得引入**: 值得，但仅作为可选增强（见 1-3）。
5. **可选 Analyzer**: 是。独立 JVM 子进程 + JSON 契约；不进默认 L1 索引路径。
6. **失败降级**: 后端不可用/超时/异常 → L1 结果原样保留，语义层缺失如实上报
   （freshness fail-closed 模式，与 analysis_query.py 同风格）。
7. **freshness/provenance**: 语义行携带 provenance=`semantic:jdt-v<n>`、backend version、
   source_hash 绑定；JDT 升级或 classpath 变化 → 语义层全失效重算，L1 图谱不受影响。
8. **旧语言保护**: guard/增强全部 metadata 门控（`syntax` 值仅 Java 发射）；语义层为
   独立表/独立 analyzer id，Python/C/C++ 路径零触碰。
9. **数据库结构**: 不改 L1 schema。语义引用走既有 `analysis_nodes/analysis_edges`
   （composite PK (id, feature)）或独立 JSON 报告；不碰 raw_references 主表。
10. **Phase 2 最小可行范围**: `ast:java-semantic`（或独立 feature id）单 analyzer：
    跨文件调用精确绑定 + 重载消歧 + JLS 歧义显式标注；输入 = L1 符号索引 + classpath
    （可选）；输出 = resolved 引用集 + recovered 过滤 + provenance。

## 风险登记

- JDT 内存：jgit 规模（1.9k 文件）批处理 binding 内存未测（fixture 级 311ms/低内存）；
  Phase 2 正式立项时需在 gson/jgit 规模复测（T9-A 已提供 L1 基线对照）。
- JDT 依赖树 19 jars + 跨 jar 签名冲突 workaround——打包/分发方案需在 Phase 2 设计。
- Maven/Gradle classpath 发现（多模块）为 Phase 2 显式范围外项，首期支持"无构建工具
  源码树 + 手工 classpath"。

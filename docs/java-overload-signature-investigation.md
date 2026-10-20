# Java JDT 重载调用点行级 signature 字段调查记录（Issue Pilot #7）

状态：只读调查结论 · 证据等级：prototype-windows-only · 不修改生产 `src/`
来源：PR #14 验证报告观察 2（`docs/linux-jdt-verification-report.md` §4.2）

## 1. 现象

fixture（`revalidation/linux-jdt-verify/fixture/`）Greeter 双重载
`greet(String)` / `greet()`，Runner 两处实例调用：

```java
return g.greet("ci") + g.greet();   // Runner.java 第 6 行，同一行两个调用点
```

实测（java-semantic --mode full）两个调用点的行级绑定 `signature` 字段
均报告为 `greet()`；而 `state=resolved`、`decl=com.example.Greeter`
均正确。

## 2. 根因定位（文件 / 行 / 代码路径）

**唯一缺陷点：`src/provenlattice/java_semantic_driver/P2bDriver.java:92`**

```java
String sig = (b != null) ? b.getName() + "()" : null;
```

`visit(MethodInvocation)` 中，`node.resolveMethodBinding()` 返回的
`IMethodBinding b` 已经解析到**具体重载**（这是 `decl`/`state` 正确的
原因——二者来自同一个 binding 对象），但序列化 signature 时使用
`b.getName() + "()"` 字面拼接，**参数类型信息被丢弃**。

报告链后续为纯透传，无二次变换：

- `src/provenlattice/java_semantic.py:230`：`signature=row.get("signature")`
- `src/provenlattice/java_semantic.py:82-86`：`SemanticBinding.signature`
  数据类字段及 `to_dict` 原样输出

因此这是**报告层（展示口径）缺陷，不是绑定正确性问题**：JDT binding
携带完整重载信息（`IMethodBinding.getParameterTypes()` /
`ITypeBinding`），在序列化处被丢弃。

## 3. 可复现证据（同 commit 复跑一致）

环境：Windows 基线重建工具链（Temurin **21.0.12.1+1**，与原 golden
宿主同版本；jdt-suite-pom.xml pinned 坐标 + strip_signatures.py，
见 Issue Pilot #10 环境披露）。worktree 基线 `ff64b5b`（origin/main，
fixture 为 2 文件版本）。

同 commit 两次独立运行 `java-semantic --mode full --json`：

- 两个调用点两次均报告 `signature="greet()"`、`state=resolved`、
  `decl=com.example.Greeter`、`file=src/com/example/Runner.java`、
  `line=6`
- 两次输出 diff 仅 3 个时序/环境字段（`cpu_ms`、`heap_used_mb`、
  `wall_ms`）；bindings 数组与 summary 其余字段字节一致（S6 归一化
  口径本就排除这三个字段）

## 4. 反例条款核验：未触发升级

- 两个调用点 `state` 均为 `resolved`，`decl` 均为 `com.example.Greeter`
  ——与各自重载的预期绑定一致，**未发现 decl/state 受重载影响**，
  不构成绑定正确性升级。
- 附带观察（同属展示层局限，不阻断）：两个调用点位于同一行，行级
  报告无列/偏移信息，两条 binding 记录完全相同——单凭行级输出无法
  区分两个调用点。

## 5. T9-B / P2-B 历史对照

`docs/java-phase2-p2b-memory-qualification.md`（T9-B 记忆资格）审计的
是**绑定正确性**（resolved/recovered/ambiguous 分类、8/8 历史错误绑定
样本 JDT 全部 CORRECT），使用同一驱动报告层；signature 口径当时未
单独审计重载区分度。因此：

- 历史绑定正确性结论**不受本发现影响**（decl/state 正确即其结论基础）；
- 但历史与现行输出中的 `signature` 值**不可用于重载区分**，任何依赖
  signature 字段区分重载的分析均无效。

## 6. (a) / (b) 建议

**建议 (a)：signature 字段应反映解析到的具体重载（另立修复合同）。**

理由：根因是序列化丢弃已有的解析信息（一行级缺陷），而非设计上无法
区分；binding 对象已携带精确参数类型（`b.getParameterTypes()` 或
`b.toString()` 均可得 `greet(java.lang.String)` vs `greet()` 口径）。
按 Issue 合同本阶段不动生产代码。

若修复合同获批，验收应包含：

1. 重载区分正反例测试：`greet(java.lang.String)` 与 `greet()` 两个
   调用点 signature 可区分；非重载调用 signature 不变；
2. golden 重生成与 S6 比较口径更新（signature 值变化会影响
   `step3-full-normalized.json`）；
3. 明确 signature 值格式契约（如 `name(paramTypes)` 的具体拼写），
   并在能力文档声明；
4. 失败路径：binding 为 null / recovered 时 signature 的既定口径
   （null / 保持现状）不变。

若 owner 选择 (b)（固化现状），最小边界声明位置：
`docs/linux-jdt-verification-report.md` §4.2 + 能力文档的
`semantic_java` 契约注释，明示 "signature = name + '()'，不区分重载"，
并以 `decl` + 源码行号作为当前唯一可用的重载区分线索（不足部分留待
修复合同）。

## 7. 证据归档

- 复跑原始输出：两次运行 JSON 于调查会话留存（bindings 字节一致；
  时序字段除外），归档路径不写入产品仓库。
- 本记录自身为 docs/ 交付物，不改变任何代码与 golden。

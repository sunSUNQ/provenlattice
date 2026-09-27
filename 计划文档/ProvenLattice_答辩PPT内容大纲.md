# ProvenLattice 阶段性汇报答辩 PPT 内容大纲

> 主题：**ProvenLattice：面向 AI 代码缺陷检测的稀疏语义程序图**  
> 用途：阶段性汇报 / 答辩  
> 建议时长：15–18 分钟  
> 建议页数：16–18 页  
> 建议页数：正片 16–18 页（从下方 24 页中挑选）+ 答疑备用页  
> 当前项目状态（2026-09-27 更新）：阶段 2–6 全部交付 —— Semantic Event、Sparse CFG、Identity、Access、Sparse DFG、Contract、八个 Typed Query 与 32 条人工裁定闭环；本文档第 1–14 页为阶段 2/3 原稿（叙事仍成立，个别数字已被更新值取代），**第 15–24 页为本次新增：DFG 专题与实验结果全量**。

---

# 一、整套汇报的核心叙事

整套 PPT 不建议按照代码模块逐页介绍，而建议围绕一条明确的研究逻辑展开：

> **为什么现有代码图不够 → 为什么不能直接做完整 CPG → 我提出什么稀疏语义图 → 目前已经做到了什么 → 下一步如何验证这个方案是否成立。**

建议分成四部分：

## 第一部分：问题是什么

1. 封面  
2. 研究背景与问题  
3. ProvenLattice 已有基础  
4. 现有架构为什么不足  

## 第二部分：方案是什么

5. 为什么不做完整 CPG  
6. Defect-oriented Sparse Semantic Program Graph 总体架构  
7. 缺陷驱动的 Evidence Matrix  
8. Semantic Event 设计  
9. Sparse CFG / Sparse DFG  

## 第三部分：目前做到了什么

10. 当前实现进度  
11. Semantic Event MVP 实现与验证  
12. 增量一致性中的关键设计  
13. 面向百万行代码的热 / 冷 / 冻存储思路  

## 第四部分：下一步怎么验证

14. Typed Query  
15. Defect Evidence Bundle  
16. 当前核心任务：Sparse CFG  
17. 第一轮可证伪实验  
18. 总结与下一步  

## 第五部分：本次新增（2026-09-27）—— DFG 专题与实验结果全量

**A. DFG 的作用与 CFG 联动（建议必讲）**

15. Sparse DFG 的作用：CFG 给「路」，DFG 给「物」
16. 为什么必须联动：DFG 单独使用会 100% 假阳性（实测）
17. 联动怎么工作：五个 Typed Query 的判据解剖

**B. 实验结果（建议从中挑 3 页进正片，其余留答疑）**

18. 结果 1：两个真实仓的规模与建图成本
19. 结果 2：候选空间缩量 −98.1%（五列对比）
20. 结果 3：字节级可复现（正确性对账）
21. 结果 4：32 条人工裁定与假阳性成因迁移
22. 结果 5：八个查询的成本与两个交付级缺陷
23. 结果 6：端到端检索评测（诚实页）
24. 结果 7：一页数字墙

> 编号说明：第四部分原列的 14（Typed Query）与 15（Defect Evidence Bundle）已写成正文第 13、14 页；16–18（当前核心任务 / 第一轮可证伪实验 / 总结）的内容已被第 15–24 页取代。原稿第 11 页缺失（内容与第 10 页合并）。

---

# 第 1 页｜封面

## 标题

**ProvenLattice：面向 AI 代码缺陷检测的稀疏语义程序图**

英文副标题可选：

> **Defect-oriented Sparse Semantic Program Graph for AI-assisted Code Analysis**


## 汇报开场建议

可以用一句话快速定义这项工作：

> 我的工作是在现有 ProvenLattice 工程证据图的基础上，增加面向代码缺陷检测的语义能力，在保留增量一致性、可追溯性和确定性的同时，避免完整 Code Property Graph 带来的存储和查询成本。

---

# 第 2 页｜研究背景：AI 看代码，缺的不是更多文本，而是结构化证据

## 页面核心句

**LLM 能理解代码，但复杂缺陷往往不能仅靠局部源码或关键词判断。**

## 左侧：传统方式

```text
源码
 ↓
关键词 / 文本检索
 ↓
大段上下文
 ↓
LLM 自己推断
```

存在的问题：

- 缺少明确控制流
- 缺少数据流
- 缺少资源生命周期
- 缺少锁、线程、别名等关系
- 输入代码多，证据密度低
- AI 同时承担“静态分析 + 语义判断”

## 右侧：目标方式

```text
源码
 ↓
确定性静态分析
 ↓
结构化缺陷证据
 ↓
AI 语义判断
```

## 页面结论

> **目标不是替代 AI，而是把 AI 从“自己做全部静态分析”变成“基于结构化证据做语义判断”。**

---

# 第 3 页｜已有基础：ProvenLattice V1 能做什么

## 标题

**现有 ProvenLattice：可追溯的工程证据图**

## 建议架构示意

```text
Repository
   │
Directory
   │
 File ───── Markdown / Requirement
   │                │
Class / Method      │
   │                │
CALLS            IMPLEMENTED_BY
REFERENCES        CONSTRAINS
IMPORTS
```

## 当前已有能力

### 代码实体

- Repository
- Directory
- File
- Namespace
- Class
- Interface
- Type
- Method
- Function

### 结构关系

- `CONTAINS`
- `DEFINES`
- `CALLS`
- `REFERENCES`
- `IMPORTS`
- `IMPLEMENTS`

### 工程证据能力

- Markdown 知识层
- 文档 ↔ 代码跨层关系
- `DESCRIBES`
- `CONSTRAINS`
- `IMPLEMENTED_BY`
- `VERIFIED_BY`

### 核心工程契约

- `resolved / ambiguous / unresolved` 三态引用解析
- Full / Incremental / Overlay parity
- Stable SHA-256 identity
- SQLite 持久化
- GraphQuery 查询接口

## 页面结论

> **V1 擅长回答“代码在哪里、谁调用谁”，但还不擅长回答“这条程序路径是否构成缺陷”。**

---

# 第 4 页｜问题：Method-level Code KG 不足以支持缺陷检测

## 标题

**从代码理解走向缺陷检测，分析粒度还不够**

## 示例代码

```cpp
p = malloc(1024);

if (error) {
    return;
}

free(p);
```

## 现有 Method-level 图能看到什么

```text
Method foo
 ├─ CALL malloc
 └─ CALL free
```

这个图能够说明：

- `foo` 调用了 `malloc`
- `foo` 调用了 `free`

但是不能说明：

- `malloc` 和 `free` 之间的控制路径
- 是否存在提前 `return`
- 是否存在某条路径没有经过 `free`

## 缺陷检测真正需要看到什么

```text
ALLOC(p)
    │
    ▼
BRANCH(error)
  /       \
RETURN    RELEASE(p)
```

真正要回答的问题是：

```text
是否存在：
ALLOC → RETURN
且路径上不存在 RELEASE
```

## 当前架构缺口

现有系统：

- AST 只用于解析，不持久化
- 最细长期实体基本到 Method / Function
- 没有完整 CFG
- 没有 def-use / reaching-definition DFG

## 页面结论

> **缺陷分析需要从 Method 粒度下沉到“关键语义操作”粒度。**

---

# 第 5 页｜设计选择：为什么不直接做完整 CPG

## 标题

**为什么不是完整 Code Property Graph？**

## 对比表

| 完整 CPG | 主要问题 | ProvenLattice V2 |
|---|---|---|
| 所有 AST 节点长期持久化 | 节点数快速膨胀 | AST 只负责提取，不长期存储 |
| 完整 CFG | 大量普通 statement 噪声 | Sparse CFG |
| 完整 DFG | 数据流边规模大 | Sparse DFG |
| 所有表达式进入图 | AI 输入 token 增加 | 只保留高价值语义事件 |
| 通用图查询 | 查询容易扩张 | Typed Query |

## 举例

AI 判断内存泄漏真正需要的是：

```text
ALLOC
  ↓
BRANCH
 /    \
RETURN RELEASE
```

通常不需要把下面这些全部长期持久化：

```text
literal
identifier
binary_expression
parentheses
普通赋值表达式
普通语句节点
...
```

## 核心观点

完整 CPG 追求：

> Graph Completeness

本项目追求：

> **Defect Evidence Density**

## 页面结论

> **Method 是骨架，Semantic Event 是缺陷分析粒度；AST 负责提取，CFG / DFG 只物化缺陷检测真正需要的关系。**

---

# 第 6 页｜总体方案：Defect-oriented Sparse Semantic Program Graph

## 标题

**面向缺陷检测的稀疏语义程序图**

## 建议总架构图

```text
                      Source Code
                          │
                    tree-sitter AST
                  （临时，不持久化）
                          │
       ┌──────────────────┼──────────────────┐
       │                  │                  │
 Structural KG       Semantic Event      Raw Evidence
       │                  │                  │
       │          ┌───────┴────────┐         │
       │          │                │         │
       │      Sparse CFG       Sparse DFG    │
       │          │                │         │
       └──────────┴────────┬───────┘         │
                           ▼                 │
              Sparse Semantic Program Graph │
                           │                 │
                     Typed Query ◀───────────┘
                           │
                 Defect Evidence Bundle
                           │
                           ▼
                          AI
```

## 四个核心层次

### 1. Structural Code KG

保留原有：

- Repository
- File
- Class
- Method
- Function
- CALLS / REFERENCES / IMPORTS 等

作用：

> 提供全局工程骨架。

### 2. Semantic Event

把缺陷相关关键操作提取为事件，例如：

- ALLOC
- RELEASE
- LOCK
- UNLOCK
- READ
- WRITE
- CHECK
- RETURN

作用：

> 提供真正的缺陷分析粒度。

### 3. Sparse CFG / DFG

只保留关键 Event 之间的：

- 控制可达关系
- 缺陷相关 value flow
- alias 等必要关系

### 4. Typed Query + Evidence Bundle

不再默认把整个子图交给 AI，而是生成特定缺陷的结构化证据。

---

# 第 7 页｜缺陷驱动 Schema，而不是先造图再找用途

## 标题

**从“图有什么”转向“缺陷需要什么”**

## 核心设计顺序

```text
Defect Types
     ↓
Required Evidence
     ↓
Semantic Events
     ↓
Required Relations
     ↓
Graph Schema
```

## 不采用的路线

```text
完整 CPG
   ↓
全部实现
   ↓
再看哪些缺陷能检测
```

## 当前分类结果

当前 Evidence Matrix 已整理为：

> **9 大类 / 38 小类**

### A / B / C 成本分级

```text
A：13 类
Event + Sparse CFG 即可完成候选生成

B：23 类
必须引入 Sparse DFG

C：2 类
稀疏图不足，需要 Local Deep Analysis
```

## 当前优先展开的 5 个小类

第一轮重点缺陷：

1. 共享数据竞态
2. 空指针解引用
3. 内存泄漏
4. 双重释放
5. 释放后使用

这些缺陷已经展开：

- Required Events
- Required Relations
- Optional Evidence
- Disqualifying Evidence
- AI-required Semantics

## 说明

早期 V2 设计文档中使用“36 类”作为目标规模，后续分类学经过进一步裁决后调整为：

> **9 大类、38 小类**

正式汇报建议统一使用最新的 **38 小类** 口径。

---

# 第 8 页｜Semantic Event：只保存与缺陷相关的操作

## 标题

**Semantic Event：从“语句”抽象成“缺陷相关操作”**

## Level 0：始终抽取

低成本、高价值事件：

```text
CALL
RETURN
THROW

ALLOC
RELEASE

LOCK
UNLOCK
ATOMIC

THREAD_SPAWN
THREAD_JOIN
```

当前 Semantic Event MVP 已优先实现这一层。

## Level 1：按缺陷规则触发

例如：

```text
READ
WRITE
DEREFERENCE
CHECK
BRANCH
```

只针对：

- 候选共享变量
- pointer
- resource handle
- sensitive state
- tainted value 等

## Level 2：查询时临时展开

复杂分析不进入全局图，而采用：

```text
发现候选
   ↓
选取 1~N 个 Method
   ↓
重新读取源码 + AST
   ↓
构建 Detailed Local CFG / DFG / Alias
   ↓
检测完成后释放或缓存
```

## 核心原则

> **不是每条语句都变成长期图节点。**

这样可以降低：

- 节点规模
- 图噪声
- AI token 成本
- 增量更新代价

## 设计定位

> **Global Sparse Graph + Local Deep Analysis**

---

# 第 9 页｜Sparse CFG 与 Sparse DFG

## 标题

**只保留缺陷相关的控制流和数据流**

---

## 左侧：Sparse CFG

### 示例代码

```cpp
p = malloc(1024);
do_work();

if (error) {
    return;
}

cleanup();
free(p);
return;
```

### 完整 CFG 中有很多普通语句

但缺陷分析只保留：

```text
ALLOC
  │
  ▼
BRANCH
 /    \
RETURN RELEASE
          │
        RETURN
```

### 核心关系

```text
CONTROL_REACHES(A, B)
```

表示：

> 从关键 Event A 出发，可以到达关键 Event B，中间允许经过被压缩掉的普通语句。

### Edge flags

```text
branch=true
branch=false
exception
loop_back
```

---

## 右侧：Sparse DFG

### 示例代码

```cpp
char *name = request->name;
char *tmp = name;
sprintf(buffer, tmp);
```

完整 DFG 可能是：

```text
request->name
  ↓
name
  ↓
tmp
  ↓
argument
  ↓
sprintf
```

Sparse DFG 压缩为：

```text
ExternalInput:request.name
        │
    DATA_FLOW_TO
        ▼
     sprintf
```

中间传播链：

> 保存到 evidence/path metadata，需要解释时再恢复。

## 页面结论

> **CFG 保留缺陷相关路径，DFG 保留缺陷相关 value flow。**

---


# 第 10 页｜Semantic Event MVP：当前验证结果

## 标题

**Semantic Event MVP 已验证进入现有增量体系**

## 建议做 4 个大数字卡片

### 50

> fixture 上抽取 Semantic Events

### 0

> 悬空 owner

### 52 = 52

> 修改函数体后  
> Incremental Event 数 = Full rebuild Event 数

### 98 / 98

> 阶段 2 验收时全部测试通过

## fixture 上事件分布

```text
CALL           18
RETURN         14
LOCK            6
UNLOCK          5
RELEASE         4
ALLOC           2
THREAD_SPAWN    1
```

总计：

```text
50 Events
```

## parity 验证

在修改函数体后：

```text
incremental = 52
full        = 52
identical   = True
```

这里验证的不只是事件数量，而是：

> **事件表内容逐字节一致。**

## 当前已经能得出的结论

> **Semantic Event 可以进入 ProvenLattice 现有的增量维护体系，同时维持 Full / Incremental parity。**

## 当前还不能得出的结论

不能说：

> “已经证明可以高准确率检测缺陷。”

因为真正的缺陷检测质量实验要到：

> Sparse CFG + Typed Query

阶段才开始。

---


# 第 12 页｜面向百万行代码：热 / 冷 / 冻存储设计

## 标题

**不同数据的访问模式不同，不应该全部塞在同一个热路径中**

## 当前规模观察

现有存储中：

> `raw_references` 是行数最大的表之一，但它并不是日常图遍历数据，而是按需取证据的数据。

在百万行 / 数百万行规模外推中，raw reference 数量会远大于最终图拓扑。

## 三层存储架构

---

## Hot：图拓扑

存：

```text
Code KG nodes
Semantic Event nodes
Call edges
Sparse CFG
Sparse DFG
Semantic relations
```

特点：

- 高频访问
- 图遍历为主
- 后续计划常驻内存
- 运行时映射成 integer ID
- 可采用 CSR / adjacency arrays

---

## Cold：证据层

存：

```text
raw_references
candidate symbols
source spans
resolver provenance
semantic extraction evidence
compressed DFG path
ambiguous / unresolved evidence
rule hits
```

特点：

- 不参加默认多跳遍历
- 只在解释 / 验证 / citation 时读取
- 后续适合 Parquet / SQLite cold tables

---

## Frozen：不可变快照

存：

```text
immutable shard
manifest
generation
```

用于：

- 金标实验
- Full / Incremental parity
- 回归测试
- 可复现分析
- snapshot diff
- Overlay

## 页面结论

> **热层负责遍历，冷层负责证据，冻层负责复现。**

---

# 第 13 页｜查询层：从 N-hop BFS 转向 Typed Query

## 标题

**缺陷检测不是“给我附近的图”，而是“给我这个缺陷的证据”**

## 通用图查询

原有：

```text
get_subgraph(node, max_hops=N)
```

适合：

> 探索型 Code Agent

但用于缺陷检测存在问题：

- 扩张范围不可控
- “小世界”效应明显
- 大量无关节点进入上下文
- AI 仍然需要自己从大子图中提取关键证据

## Typed Query

面向具体缺陷增加：

```text
RaceQuery(variable)

ResourceLifetimeQuery(resource)

NullFlowQuery(value)

UseAfterFreeQuery(resource)

DoubleFreeQuery(resource)

LockOrderQuery(lock)

TaintPathQuery(source, sink)

ErrorHandlingQuery(call)
```

## RaceQuery 示例

```text
Variable
   │
   ▼
READS / WRITES
   │
   ▼
Access Events
   │
   ├─ PROTECTED_BY
   ├─ EXECUTES_IN
   ├─ MAY_PARALLEL
   └─ ATOMIC
   │
   ▼
Defect Evidence Bundle
```

## 页面结论

> **通用图负责探索，Typed Query 负责缺陷检测。**

---

# 第 14 页｜AI 最终看到什么：Defect Evidence Bundle

## 标题

**AI 不默认读取整个图，只读取“证据束”**

## 简化结构

```json
{
  "defect_type": "race_condition",

  "facts": [
    "Method A writes x",
    "Method B reads x",
    "no common resolved lock"
  ],

  "uncertain_facts": [
    "MAY_PARALLEL = ambiguous"
  ],

  "paths": [],

  "source_evidence": [
    "foo.cpp:182-184",
    "foo.cpp:271-274"
  ],

  "missing_evidence": [
    "runtime scheduling relationship"
  ]
}
```

## 数据流向

```text
确定性程序分析
      ↓
facts
uncertain_facts
paths
source_evidence
missing_evidence
      ↓
      AI
      ↓
confirmed
likely
insufficient evidence
rejected
```

## 两类状态必须分开

### 图解析层三态

```text
resolved
ambiguous
unresolved
```

描述：

> 图关系是否能够可靠解析。

### AI 缺陷判断状态

例如：

```text
confirmed
likely
insufficient evidence
rejected
```

描述：

> 当前证据是否支持缺陷结论。

## 页面结论

> **底层三态描述“关系可信度”，AI 状态描述“缺陷判断结果”，两者不能混为一层。**

---



# 二、整场答辩建议强调的 3 个记忆点

老师听完整场以后，最好能清楚记住以下三个核心观点。

---

## 记忆点 1：为什么不做完整 CPG

不要把理由说成：

> “完整 CPG 太难，所以不做。”

更准确的说法是：

> **研究目标不同。**

完整 CPG 追求：

> Graph Completeness

ProvenLattice V2 追求：

> **Defect Evidence Density**

也就是说：

> 只长期保存对缺陷判断有直接价值的语义。

---

## 记忆点 2：真正的新分析粒度是 Semantic Event

不要把 V2 仅仅描述成：

> “在知识图谱上再加几种边。”

应该强调：

> **Method 是全局骨架，Semantic Event 才是缺陷分析粒度。**

这是 V2 相比 V1 最大的架构变化。

---

## 记忆点 3：目前没有宣称“已经能检测 38 类缺陷”

这是答辩时需要特别谨慎的地方。

目前已经证明的是：

```text
Code KG
  +
Semantic Event
  +
Stable Identity
  +
Semantic Dirty Trigger
  +
Full / Incremental Consistency
```

成立。

真正要验证的是：

```text
Event
 +
Sparse CFG
     ↓
Typed Query
     ↓
真实缺陷候选质量
```

因此正式表述建议使用：

> **“当前已经完成语义事件基础设施，正在进入缺陷检测能力的第一轮实验验证。”**

不建议使用：

> “系统已经可以检测 38 类缺陷。”

因为目前还没有足够实验结果支持这一结论。

---

# 三、PPT 视觉设计建议

## 1. 页面内容比例

建议控制为：

- 60% 图 / 流程图
- 25% 数据 / 实验结果
- 15% 文字

避免：

- 大段复制设计文档
- 每页超过 6–8 个 bullet
- 大面积源码截图
- 复杂数据库表结构

---

## 2. 最值得画好的 4 张图

### 图 1：Method Graph → Semantic Event Graph

对应第 4 页。

目的：

> 让听众直观看到“为什么 Method-level 图不够”。

---

### 图 2：V2 总体架构

对应第 6 页。

目的：

> 让听众建立整套系统的心智模型。

---

### 图 3：Sparse CFG / Sparse DFG

对应第 9 页。

目的：

> 解释“Sparse”到底稀疏在哪里。

---

### 图 4：实验决策链

对应第 17 页。

建议画成：

```text
Semantic Event
      +
Sparse CFG
      ↓
Typed Query
      ↓
20 candidates
      ↓
人工核对
      ↓
┌───────────────┐
│ Event+CFG够吗？│
└───────┬───────┘
        │
     Yes│No
        │
   ↓    ↓
收窄DFG  失败案例
        ↓
     反推DFG
```

目的：

> 强化项目的研究性，而不仅是工程实现。

---

# 四、可能被问到的问题与建议回答方向

## Q1：为什么不用 Joern / 完整 CPG？

建议回答：

> Joern 或完整 CPG 更适合深度静态分析，但 ProvenLattice 的目标不是替代完整静态分析平台，而是为 Code Agent / AI 提供高密度、可追溯、可增量维护的工程证据。  
> 因此我们保留 Method-level Code KG 作为全局骨架，只物化缺陷检测真正需要的 Event、Sparse CFG 和 Sparse DFG，在空间、查询噪声和 AI token 成本之间做折中。

---

## Q2：Sparse 会不会导致漏掉缺陷？

建议回答：

> 会存在能力边界，所以项目不是假设 Sparse 一定够，而是通过 Evidence Matrix 和 Typed Query 实验明确验证它的边界。  
> 对稀疏全局图无法解决的复杂 alias、pointer arithmetic、跨过程 ownership 等问题，设计中保留 Local Deep Analysis，对少数候选 Method 临时重建详细 AST / CFG / DFG。

---

## Q3：为什么还需要 AI，静态分析器直接判定不行吗？

建议回答：

> 图谱负责确定性证据和候选生成，AI 负责图之外的语义。  
> 例如 mutex 是否真的保护某变量、某 API 是否转移 ownership、两个 execution context 是否真实并行，这类语义通常依赖 API 契约、项目约定和业务上下文。  
> 因此系统刻意区分“程序分析事实”和“缺陷语义判断”。

---

## Q4：为什么不先实现 DFG？

建议回答：

> 因为 Evidence Matrix 显示一部分高价值缺陷候选只依赖 Event + CFG。  
> 如果直接先实现完整 DFG，会在没有验证需求的情况下投入大量复杂度。  
> 当前计划先用 Race / Resource Leak / Lock Order 三类 Typed Query 验证 Event + CFG 的能力，再根据真实 false positive 和 missing evidence 反向确定 Sparse DFG 的范围。

---

## Q5：为什么 Event ID 不直接使用源码位置？

建议回答：

> 因为源码位置不具备增量稳定性。前面增加一行就可能导致后面所有 Event ID 改变。  
> 现在使用 owner method 的稳定 symbol ID + event type + method-local ordinal，使修改一个方法时，影响基本限制在该方法内部。

---

## Q6：目前最大的风险是什么？

可以回答三点：

1. **Event + CFG 的实际 precision 尚未验证**  
   → 阶段 4 是第一轮质量基线。

2. **23 个 B 类缺陷可能需要比预期更多 DFG**  
   → 用第一轮 Typed Query 的失败案例反推。

3. **百万行规模下 Event / Evidence 的存储成本**  
   → 已规划热 / 冷 / 冻分层，不把所有 evidence 放入热图。

---

# 五、汇报时建议避免的表述

## 不建议

> “我们已经支持 38 类缺陷检测。”

建议改为：

> “目前 Evidence Matrix 已覆盖 38 类缺陷需求，检测能力正在按阶段实现。”

---

## 不建议

> “Sparse Graph 比 CPG 更好。”

建议改为：

> “两者优化目标不同。完整 CPG 更强调分析完整度，本项目强调 Code Agent 场景下的缺陷证据密度、可增量维护和查询成本。”

---

## 不建议

> “AI 可以解决静态分析做不了的问题。”

建议改为：

> “AI 主要补充 API 契约、ownership、执行上下文和业务语义等图外语义，程序结构事实仍由确定性分析生成。”

---

# 六、当前阶段的一句话定位

如果老师最后问：

> “所以你目前到底做到哪里？”

可以直接回答：

> **目前已经完成 ProvenLattice 从 Method-level Code KG 向 Semantic Event Layer 的扩展，并验证了 Event 层的稳定身份、语义脏触发和 Full / Incremental parity；当前正在实现 Sparse CFG，下一步会通过 Race、Resource Leak 和 Lock Order Typed Query 做第一轮真实缺陷候选质量验证。**

---

# 七、项目最终目标的一句话定位

> **ProvenLattice V2 不是完整 CPG 的替代品，而是面向 AI 缺陷检测的可追溯、确定性、可增量维护的稀疏语义证据图。**

或者更短：

> **Global Sparse Graph + Local Deep Analysis + AI Semantic Judgment**

---

# 八、新增页（2026-09-27）：Sparse DFG 专题与实验结果全量

> 本节 10 页为本次新增。数字全部来自可复跑工件（出处见每页「素材」行）。
> **选页建议**：第 15–17 页是方案论证的收口，建议必讲；第 18–24 页按答辩时间挑 3 页进正片（推荐 19 / 21 / 23），其余留作答疑备用页 —— 被问到「有数字吗」时直接翻出来。

---

# 第 15 页｜Sparse DFG 的作用：CFG 给「路」，DFG 给「物」

## 标题

**控制流回答「能不能走到这里」，数据流回答「这是不是同一个值」**

## 页面核心句

**缺陷判据需要同时回答两个正交问题；缺任何一半，候选空间就会结构性错误。**

## 上半页：两个问题，两张图

### 左侧：CFG 回答「到不到」

```cpp
p = malloc(1024);

if (err) {
    return;        // ← 这条臂能走到吗？
}

use(p);
```

- `CONTROL_REACHES(A, B)`：从关键事件 A 能走到关键事件 B，中间普通语句被压缩
- 实测规模：redis-50 **162,268** 条 / llama.cpp-69 **422,925** 条
- 它不知道：`p` 是什么、两个 `p` 是不是同一个对象

### 右侧：DFG 回答「是不是同一个」

```cpp
p = malloc(1024);
q = p;             // ← q 和 p 是同一个对象吗？
free(p);
```

- `DATA_FLOW_TO`：定义 → 使用之间的「同一个值 / 同一个资源」关系
- 实测规模：redis-50 **6,055** 条 / llama.cpp-69 **11,268** 条
- 它不知道：这条流在不在一条真的能执行到的路径上

## 中部：五类流边（DFG 到底铸了什么）

| 流类 | 语义 | redis-50 | llama.cpp-69 |
|---|---|---:|---:|
| `input_to_sink` | 定义 → 调用实参根 | 3,491 | 5,507 |
| `value_flow` | 非分配来源的写 → 使用 | 2,461 | 4,956 |
| `alloc_to_use` | 分配 → 使用 | 40 | 750 |
| `null_to_deref` | 空值来源 → 解引用 | 52 | 8 |
| `free_to_use` | 释放 → 使用 | 11 | 47 |

## 底部：三个正交问题

```text
① 是什么（身份）        →  Identity 层
② 到不到（控制可达）    →  Sparse CFG
③ 是不是同一个值/资源   →  Sparse DFG
```

> 缺陷 = 坏事情 × 发生在某个具体对象上 × 且这条路真的能走到

## 一条设计取舍

DFG 不是完整数据流图 —— 只铸「能改变缺陷判据」的流：

- **一条链规则**：只落直接 def → use 边；中间传播链存进 `via` metadata，需要解释时按需恢复
- 因此图小、可解释、可增量；代价是链式传播要显式展开（已登记）

## 页面结论

> **CFG 保留「路」，DFG 保留「物」；两者是正交维度，不是同一张图的两个视图。**

## 制作指示（给 AI）

左右分栏（左 CFG 右 DFG），中间一条纵向分隔线；五类流表放中间横贯；底部三问条 + 一句结论。
数字用等宽字体，两列对齐。**不要**在这一页讲判据 —— 判据留给第 17 页。

---

# 第 16 页｜为什么必须联动：DFG 单独使用会 100% 假阳性（实测）

## 标题

**按源码顺序铸出的流边是「候选级关系」，不是「缺陷证据」—— 这是量出来的，不是推测的**

## 页面核心句

**DFG 边单独使用会系统性造假阳性；CFG 单独使用会系统性漏判。两个方向我们都用真实语料量过。**

## 上半页：机制 —— 为什么 DFG 边是路径盲的

```text
free(p);          ← 释放

if (err) {
    return;       ← 这条臂直接返回
}

use(p);           ← 使用在另一条臂上
```

- `free_to_use` 边按**源码顺序**铸造：释放身份只被后来的释放替换、从不被路径清除
- 所以它铸出的是「文本上后出现的那个使用」，**不是**「执行上真的能走到那个使用」

## 实测（两个真实仓，逐条重算可达性）

```text
redis-50:     free_to_use 边 11 条  →  路径可达 0 条   →  11 / 11 不相连
llama.cpp-69: free_to_use 边 47 条  →  路径可达 1 条   →  46 / 47 不相连
```

源码复核结论：不相连的绝大多数是 `free(x); return;` 的**清理路径** —— free 在会 return 的臂上，use 在另一条臂上。

> **不是释放后使用。** 只用 DFG，这个流类的候选 100% 是假阳性。

## 下半页：反方向 —— 只用 CFG 也不行

CFG 不知道：

- 两个 `p` 是不是同一个对象（别名）
- `p` 现在是 NULL 还是非 NULL
- `free` 的是不是后面要用的那个对象

## 附带的方法论坑（答辩加分点）

DFG 的源如果是 WRITE 点，它在 CFG 里是**叶子（无出边）**，`control_reachable` 标志恒为 `false` —— 语义是「没有位置可算」，**不是「不可达」**。

读错这条会**结构性清空 52 / 52 个候选**（探针实测）。因此实现里是**三态规则**：

```text
源有出边 ∧ 不可达        ⇒  淘汰（可证伪）
源是叶子（没有位置）      ⇒  未知，不淘汰（降级 ambiguous）
```

## 页面结论

> **DFG 边 = 候选；DFG × CFG = 判据。任何一侧单独使用都会产生结构性错误 —— 一个造假阳性，一个清空候选。**

## 制作指示（给 AI）

上半：一段代码 + 一张两行实测表（11/11 与 46/47 用醒目色）。
下半：三行「CFG 不知道什么」清单 + 三态规则代码块。
**这一页是本组的论证核心** —— 讲的时候把 11/11 念出来，它是全场最有说服力的单条证据。

---

# 第 17 页｜联动怎么工作：五个 Typed Query 的判据解剖

## 标题

**每个查询 = DFG 供「物证」+ CFG 供「路证」+ 三态防升级**

## 页面核心句

**判据不是「两个图都查一下」，而是两个维度的交集；并且每一条淘汰规则都必须可证伪、有计数。**

## 主表（本页全部内容，字要大）

| 查询（矩阵键） | DFG 提供什么 | CFG 提供什么 | 可证伪的淘汰规则 |
|---|---|---|---|
| 空指针解引用（3.1） | 空值 / 分配来源 → 解引用 | 从 CHECK 的空侧出边反向判「是否已守卫」 | 已守卫 ⇒ 淘汰；路径不相连 ⇒ 淘汰 |
| 释放后使用（4.3） | 释放 → 使用（含「CALL 作使用」的查询期组合） | 释放 → 使用可达性；中间再定义检查 | 路径不相连 ⇒ 淘汰；释放自身那条调用 ⇒ 淘汰 |
| 双重释放（4.2） | 同身份释放配对 + 别名闭包 | 第一次释放 → 第二次释放可达 | 其间有同身份再定义（重新分配或置空）⇒ 淘汰 |
| 未检查返回值（9.1） | `result_of`：调用结果落进哪个变量 | 分支支配扫描（BFS 前驱树读回路线） | 下次使用前出现分支点 ⇒ 淘汰 |
| 污点路径（无矩阵键） | 输入 → 汇实参的流边 | 名字解析 + 位置判据 | 位置不可证 ⇒ 淘汰并计数，不猜 |

## 三条设计纪律（建议做成三个徽章）

### 零升级

不确定的事实**绝不**升为 `resolved`；三态 `resolved` / `ambiguous` / `unresolved` 贯穿所有查询。

### 登记不掩盖

判不了的部分写进 `missing_evidence` 交给 AI（如 API 契约、净化点、所有权语义），**不假装**。

### 淘汰必计数

每一条淘汰规则都有计数器，淘汰数 + 存活数 = 输入数，数字可对账。

## 页面结论

> **联动 = 两个维度的交集；纪律 = 不确定不升级 + 判不了要登记 + 淘汰必计数。**

## 制作指示（给 AI）

五行四列的大表占 70% 版面（这是全场信息密度最高的一页，只留关键词，不要整句）；底部三个徽章一行排开。
讲这页时按行念：每行先念「DFG 给什么」，再念「CFG 给什么」，最后念淘汰规则 —— 节奏感会让老师记住「交集」这个词。

---

# 第 18 页｜结果 1：两个真实仓的规模与建图成本

## 标题

**不是玩具语料：325 / 1,358 个文件的两个真实 C/C++ 仓**

## 页面核心句

**规模、成本、确定性三个数字同时交付 —— 并且都是可复跑的。**

## 主表

| 指标 | redis-50 | llama.cpp-69 |
|---|---:|---:|
| 文件数 | 325 | 1,358 |
| 语义事件 | 176,893 | 531,011 |
| 控制可达边 | 162,268 | 422,925 |
| 数据流边 | 6,055 | 11,268 |
| 全量建图 | 24.7s | 91.1s |
| 库体积 | 454 MB | 1,444 MB |
| 存储形态 | 单个 SQLite 文件，零外部服务 | 同左 |

## 三个附注

### 索引优化

表达式索引：**18.3 ms → 0.014 ms（约 1300×）**（阶段 0.4，EXPLAIN 钉住查询计划）

### 确定性

同输入两次建库，图内容 digest **逐位一致**（SQLite 页噪声不计入图内容）

### 成本回归（如实登记）

redis 建图 +15.4%，超闸 0.4 个点 —— 已定位到惰性 BFS + `bisect` 的 `via` 恢复（调查链 156s → 25s → 24.7s）

## 页面结论

> **规模已到「十万级事件 / 四十万级边」，单机单文件库可承载；成本与回归都如实记录，不藏。**

## 制作指示（给 AI）

主表两列大数字；右下角三个小徽章（索引 1300× / 逐位一致 / +15.4% 已登记）。
「+15.4% 已登记」这个徽章**不要删** —— 主动亮出成本回归是研究态度的证据。

---

# 第 19 页｜结果 2：候选空间缩量 −98.1%（五列对比）

## 标题

**同一查询、同一语料，五层结构性投资把候选从 557,315 压到 14,439**

## 页面核心句

**缩量来自设计，不是调参；而且每一层都能单独对账到冻结工件。**

## 主表（redis-50，1.1 竞态查询候选数）

| 列 | 配方 | 候选数 |
|---|---|---:|
| C1 | 阶段 4 基线（无身份） | 557,315 |
| C2 | ＋声明身份（Identity 层） | 28,523 |
| C3 | ＋READ / WRITE 访问层 | 264,280 |
| C4 | ＋稀疏 DFG 身份修复 | 10,420 |
| C5 | ＋契约与参数绑定（交付态） | **14,439** |

llama.cpp-69 同表：**1,398,235 → 58,677 → 137,899 → 98,448 → 101,159**（−92.8%）

## 读数说明（这页必须讲清，否则会被问倒）

- **C2 → C3 上升**：READ / WRITE 拉宽了「同一变量」的方法集合（不是重复计数；22 条对账差已解释）
- **C3 → C4 大幅下降**：unknown 根的成员保留身份 + errno 配对豁免
- **C4 → C5 上升**：契约与参数绑定把跨方法主体接回来（+绑定是功能，不是回归）
- 每一列都对冻结工件**逐位复现**（C1 的 557,315 与阶段 4 工件精确相等）

## 页面结论

> **−98.1%（redis）/ −92.8%（llama）是五层结构性投资的累计效果 —— 中间两次上升也如实展示，因为缩量不是单调调参的结果。**

## 制作指示（给 AI）

横向五列阶梯图（或漏斗图），每列数字大号；下方一行四个读数注解。
**中间的两次上升不要隐藏** —— 能解释清楚「为什么先涨再落」比一条单调下降曲线更能说明设计是真的。

---

# 第 20 页｜结果 3：字节级可复现（正确性对账）

## 标题

**这个系统最重要的性质不是「查得准」，而是「每次查得一模一样」**

## 页面核心句

**可复现性是双盲实验与金标冻存的前提 —— 也是这个项目与「跑一次看看」式工具的分界线。**

## 四组对账（2×2 卡片）

### 重建一致

同输入 → 逐位同输出；分层对账 **16 / 16 零偏差**

### 增量 = 全量

修改函数体后，增量重建与全量重建的事件表**逐字节一致**

### 冻结预测纪律

先冻结预测数字 → 再实现 → 逐条归因偏差；阶段 6 收官 **零未归因残差**

```text
偏差样例（两条）：
null_flow  llama.cpp  +62  =  守卫匹配改为身份匹配
use_after_free redis  −194 =  新增「释放自身那条调用不算使用」
```

### 回归护栏

单元测试 **296 / 296**；假阳性重定位 **10 / 13**（零回归）

## 页面结论

> **先冻结、后实现、再逐条归因 —— 这是研究纪律，不是工程流程。**

## 制作指示（给 AI）

四张等大卡片；「零未归因残差」那张用醒目底色。
这页讲方法论，语速放慢 —— 老师记住这一页，后面所有数字的可信度都会被顺带抬高。

---

# 第 21 页｜结果 4：32 条人工裁定与假阳性成因迁移

## 标题

**32 条逐条人工裁定：真阳性 1 / 假阳性 31**

## 页面核心句

**数字不好看，但成因的迁移方向恰好证明了设计分工：结构层已经交棒，剩下的主要需要 AI 侧语义。**

## 左侧：口径与数字

- 口径：AI 逐条提议 + 人工逐条确认（`annotator` 栏如实记录，可回溯）
- 抽样：仓库 × 缺陷键 × 三态分层，共 16 层，32 条
- precision：**1 / 32 = 0.031**

## 右侧：假阳性成因分布（柱状图）

```text
contract              10   ← 需要 AI 侧 API / 所有权语义
extractor              6   ← 提取侧词表与语义缺口
other                  5
ownership              5
identity               4
missing_read_write     1
（唯一真阳性：lfu-simulation.c:87 malloc → :135 直接解引用）
```

## 关键解读（必讲）

| | 阶段 4 基线 | 阶段 6 |
|---|---|---|
| 裁定数 | 20 条 | 32 条 |
| 真阳性 | 0 | **1** |
| 主导成因 | ownership 10 / identity 6（结构问题） | **contract 10（AI 侧语义）** |
| 结构成因占比 | 16 / 20 = 80% | 9 / 31 = 29% |

这正是矩阵设计的**分工**：图负责结构事实，AI 负责 API 契约与所有权语义。

## 诚实边界（不藏）

- 32 条是**抽样**，不是全体；不同缺陷族的 precision **不可直接比**
- 唯一真阳性所在的族与假阳性主导族不同 ⇒ 不能说成「准确率提升到 3%」

## 页面结论

> **「precision 0.031」读作：结构层已经交棒，剩下的假阳性主要需要 AI 侧语义 —— 这是设计，不是失控。**

## 制作指示（给 AI）

左数字右柱状图；底部一张两行小对比表（阶段 4 → 阶段 6 的成因迁移）。
被问「准确率怎么这么低」时，答：**这是候选生成层的抽样，不是最终判定层；且成因分布证明候选层该做的事已经做完了。**

---

# 第 22 页｜结果 5：八个查询的成本与两个交付级缺陷

## 标题

**成本表不是装饰 —— 它把两个只在交付态才暴露的缺陷逼了出来**

## 页面核心句

**八个分析查询全部可跑；成本主导项已定位；两个交付级缺陷已修复并钉了回归测试。**

## 上：八查询成本（redis-50，交付态）

```text
error_handling       4.7s
taint_path           4.7s
null_flow            4.8s
lock_order           4.9s
resource_lifetime    7.6s
race_condition       7.8s
double_free         64.8s
use_after_free     124.5s   ← 主导项：路径枚举
```

八个分开跑合计 **223.8s**；一次 `all` 调用 **204.2s**；每个查询两次运行候选**逐位相同**（确定性）

## 下：两个交付级缺陷

| 症状 | 根因 | 修法 | 结果 |
|---|---|---|---|
| `error_handling` 查询 >600s / 13.7 GB 不返回 | 路径枚举在循环窗口上指数爆炸 | 改读 BFS 前驱树上的路线（判决与路线同源） | **1.6s**，候选与冻结预测逐位一致 |
| llama 交付态多出 6,189 个伪候选 | 交付层默认窗口 64 透传进判决窗口 | 内部钳到冻结下限 4096（可调大不可调小） | **16 / 16 分层回到零偏差** |

## 页面结论

> **这两个缺陷在夹具上永远测不出来 —— 只有真实语料 + 全窗口才会暴露。成本表是发现它们的手段。**

## 制作指示（给 AI）

上半条形图（`use_after_free` 那条最长，用警示色）；下半两行「症状 → 根因 → 修法 → 结果」卡片。
这页讲工程可靠性，是答辩里最容易被老师认可的一页。

---

# 第 23 页｜结果 6：端到端检索评测（诚实页）

## 标题

**端到端三臂对照已跑通 54 次运行；证据精确率 1.0，但成功率口径与 token 效率都还是负结果**

## 页面核心句

**测量系统先于结论成立：好结果和坏结果都是真结果，且每一条都有已定位的修复路径。**

## 实验设计

```text
6 个真实 brpc 任务 × 3 臂（纯文件 / 图查询 / 知识层）× 3 次重复 = 54 次运行
资格闸 15 项全过
```

## 结果（三臂对照）

### 绿：证据精确率 1.0

引用的证据**没有一条是错的**（三臂、全部 54 次运行）

### 黄：任务成功率 0 / 54

全部因**评测口径过严**被判失败（`wrong_path` 规则把合法辅助文件判错）—— 口径问题，不是系统失败，修复中

### 红：token 效率（本轮首次计量）

```text
               平均总 token   平均文件字符读取   平均工具轮数
纯文件臂          178,251         41,502           15.1
图查询臂          212,113         35,668           17.2   (+19% token)
知识层臂          222,173         38,226           19.1
```

- 图查询臂 token **+19%**：由工具轮数驱动（17.2 vs 15.1 轮）
- 归因报告已定位到 **Query Interface**（宽泛符号查询、格式错误的路径尝试）—— 未修

## 另外两个 cell

- **R2（进阶 cell）**：Evidence 召回 0.667 + 2 个无支撑引用 ⇒ 进阶闸 **HOLD**（已诊断，未解冻）
- **事件级金标**：双盲协议已冻结，标注未开始（盲评包缺陷已定位）

## 页面结论

> **precision 1.0 是真结果，成功率与 token 的负结果也是真结果 —— 三条修复路径都已定位，下个月就是把「已定位」变成「已修复」。**

## 制作指示（给 AI）

三行结果卡（绿 / 黄 / 红），右下角一个「修复路径」箭头指向三条。
**这一页不许美化。** 主动讲负结果的答辩比全是正数的答辩可信得多 —— 这是本页的核心策略。

---

# 第 24 页｜结果 7：一页数字墙

## 标题

**所有可引用的数字，一页装下**

## 页面核心句

**结构层已交付并冻结；质量与效率的负结果全部已定位。**

## 数字墙

```text
规模   325 / 1,358 文件  ·  176,893 / 531,011 语义事件  ·  162,268 / 422,925 控制边

建图   24.7s / 91.1s 全量  ·  单文件 SQLite  ·  表达式索引 1300×

质量   候选缩量 −98.1% / −92.8%  ·  precision 1/32（32 条人工裁定）

纪律   16/16 分层零偏差  ·  增量 = 全量（逐字节）  ·  0 未归因残差  ·  296/296 测试

检索   54 次端到端运行  ·  evidence_precision 1.0  ·  token 待修（+19%）
```

## 页面结论

> **一句话：结构层已交付并冻结，质量与效率的负结果全部已定位 —— 下一步是把「已定位」变成「已修复」。**

## 制作指示（给 AI）

数字墙排版，四行五类；每个数字后面标注可回溯的实验目录（答辩时可现场打开演示出处）。
这一页同时是**答疑索引**：老师问到哪个数字，就翻到对应的第 18–23 页。

---

# 九、新增页配套 Q&A（接在原有 Q4 之后）

## Q7：CFG 和 DFG 到底哪个更重要？

建议回答：

> 这个问题问错了方向。它们是**正交**的两个维度：CFG 回答「能不能走到」，DFG 回答「是不是同一个值/资源」。  
> 我们实测过：只用 DFG，`free_to_use` 这个流类的候选在 redis 上是 11/11 假阳性（都是 `free(x); return;` 清理路径）；只用 CFG，则分不清两个同名变量是不是同一个对象。  
> 所以设计上不是「哪个更重要」，而是**每个查询都必须同时拿到物证（DFG）和路证（CFG）**，再叠一条可证伪的淘汰规则。

---

## Q8：为什么候选 precision 只有 3%？

建议回答：

> 三点：  
> ① 这是**候选生成层**的抽样，不是最终判定层 —— 我们的设计里，候选交给 AI 做最后一步语义判断；  
> ② 32 条里假阳性的**成因分布已经迁移**：阶段 4 时 80% 是结构问题（身份、所有权），现在结构成因只占 29%，主导成因变成 `contract`（API 契约与所有权语义）—— 这正是矩阵里写明「AI-required」的部分；  
> ③ 32 条是分层抽样，不同缺陷族不能直接比，我不会把它说成「准确率 3%」。

---

## Q9：token 效率是负的，怎么办？

建议回答：

> 这轮是我们**第一次**拿到端到端 token 计量（之前只有字符级代理）。结果是图查询臂 +19%，但归因很明确：  
> ① 它由**工具轮数**驱动（17.2 轮 vs 纯文件臂 15.1 轮），不是单次查询贵；  
> ② 归因报告定位到 **Query Interface** —— 宽泛符号查询和格式错误的路径尝试导致多余往返；  
> ③ 这是接口问题，不是图的问题，修复路径清楚。而且证据精确率是 1.0：**多花的 token 没有换来错误证据**。  
> 下个月把接口修掉后重测，18 个 cell 可以原样重放，不需要重跑任务。

---

## Q10：这些数字别人能复现吗？

建议回答：

> 能。所有数字都落在仓库的 `experiments/` 目录里，配冻结数据库和重放脚本；建图本身是确定性的（同输入逐位同输出），增量与全量逐字节一致。  
> 我们连**预测**都是先冻结后实现的 —— 阶段 6 的偏差表里每一处差异都有归因，收官时零未归因残差。


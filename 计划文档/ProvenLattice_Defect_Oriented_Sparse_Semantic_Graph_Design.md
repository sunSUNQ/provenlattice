# ProvenLattice 面向 AI 代码缺陷检测的稀疏语义程序图设计方案

> 版本：V2 设计草案\
> 目标：在保留 ProvenLattice 现有 Code
> KG、三态证据、增量一致性和文档↔代码跨层能力的基础上，增加面向代码缺陷检测的语义事件层，以较小的存储与查询成本，为
> AI 提供比关键词扫描更强、比完整 CPG 更轻量的结构化语义证据。

------------------------------------------------------------------------

## 1. 背景与目标

ProvenLattice 当前定位是面向 Code Agent
的可追溯分层工程证据图。现有代码图属于 **Code Knowledge Graph（Code
KG）**，而不是完整 Code Property Graph（CPG）。

当前主要能力包括：

-   Repository / Directory / File / Namespace / Class / Interface / Type
    / Method / Function 等代码实体；
-   `CONTAINS / DEFINES / CALLS / REFERENCES / IMPORTS / IMPLEMENTS`
    等代码关系；
-   Markdown 文档知识层；
-   `DESCRIBES / CONSTRAINS / IMPLEMENTED_BY / VERIFIED_BY`
    等文档↔代码跨层关系；
-   resolved / ambiguous / unresolved 三态引用解析；
-   Full / Incremental / Overlay parity；
-   稳定 SHA-256 identity；
-   SQLite 持久化与应用层 GraphQuery。

当前最细代码实体基本到 Method / Function 层。tree-sitter AST
用于解析，但 AST 本身不持久化；没有完整 CFG，也没有 def-use /
reaching-definition DFG。

对于通用代码导航，这是合理的。但目标如果转向 **9 大类、36 小类代码缺陷的
AI 语义检测**，仅有 Method-level 图和关键词语义还不够。

本方案的核心目标不是把 ProvenLattice 改造成完整 CPG，而是构建：

**Defect-oriented Sparse Semantic Program
Graph（面向缺陷检测的稀疏语义程序图）**

核心原则：

> Method 是骨架，Semantic Event 是缺陷分析粒度；AST
> 负责提取、不持久化；CFG/DFG 只物化缺陷检测真正需要的稀疏关系。

------------------------------------------------------------------------

## 2. 为什么不直接做完整 CPG

完整 CPG 通常把 AST、CFG、DFG、Call Graph、类型、符号等统一到 Property
Graph。

它适合深度静态分析，但对本项目存在三个问题：

1.  **空间放大**\
    每个 statement、expression、identifier、literal
    都可能成为节点。对于百万行代码，节点和边会快速膨胀。

2.  **AI 并不需要全部语法细节**\
    AI 判断资源泄漏时，真正关心的是
    `ALLOC → 分支 → RETURN / RELEASE`，而不是完整 AST
    中所有括号、literal、binary expression。

3.  **查询噪声增加**\
    缺陷检测需要的是高密度证据。把完整 AST 子图交给模型，会增加
    token、检索和推理成本。

因此 V2 不追求"CPG 完整度"，而追求"缺陷证据密度"。

------------------------------------------------------------------------

## 3. raw_references 是什么

### 3.1 定义

`raw_references` 可以理解为
**解析阶段发现、但尚未被压缩成确定图边的原始引用证据**。

例如源码：

``` cpp
foo();
obj->bar();
count++;
```

解析器会发现 `foo`、`bar`、`count`
等引用，但在解析瞬间不一定能唯一知道它们指向哪个 symbol。

因此先记录类似：

``` text
RawReference
- source location
- referenced name
- reference kind
- candidate symbols
- resolution status
- provenance
```

resolver 再把它们分成：

``` text
resolved
ambiguous
unresolved
```

只有唯一 resolved 的引用才生成确定图边。

### 3.2 优势

raw reference 最大的价值不是图遍历，而是 **保留证据和不确定性**。

如果直接把：

``` cpp
foo();
```

强行连到某个
`Method:foo`，一旦存在重载、宏、模板、虚调用或同名符号，就可能制造假边。

ProvenLattice 的做法是：

``` text
源码引用
   ↓
RawReference
   ↓
Resolver
   ├─ resolved   → 创建真实 Edge
   ├─ ambiguous  → 保存候选，不创建假 Edge
   └─ unresolved → 保存证据，不创建假 Edge
```

这对缺陷检测尤其重要，因为错误的调用边、数据流边或锁关系会直接导致 AI
产生错误结论。

### 3.3 为什么 raw_references 不应该进入热图

现有实测中，10,115 行代码产生：

-   644 nodes
-   2,604 edges
-   25,040 raw references

raw reference 数量远高于最终拓扑，而且大量是 unresolved。

因此它适合：

**冷证据层**

而不是：

**热遍历层**

未来 AI 发现可疑路径后，再通过 evidence/reference id
按需取原始引用和源码证据。

------------------------------------------------------------------------

## 4. 总体架构

``` text
                         Source Code
                              │
                              ▼
                         tree-sitter
                              │
                    AST（临时，不持久化）
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
        Symbol Extractor  Reference Resolver  Semantic Extractor
             │                │                │
             ▼                ▼                ▼
       Method-level KG    Raw Evidence    Semantic Events
             │                                 │
             │                       ┌─────────┴─────────┐
             │                       ▼                   ▼
             │                  Sparse DFG          Sparse CFG
             │                       │                   │
             └───────────────────────┼───────────────────┘
                                     ▼
                         Sparse Semantic Program Graph
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
              Hot Topology      Cold Evidence    Frozen Snapshot
               CSR/Memory       Parquet/SQLite   Shards+Manifest
                    │
                    ▼
              Defect Query Engine
                    │
                    ▼
            Defect Evidence Bundle
                    │
                    ▼
                    AI
```

------------------------------------------------------------------------

## 5. 三层图模型

### 5.1 第一层：Structural Code KG

保留现有结构作为稳定骨架：

``` text
Repository
Directory
File
Namespace
Class
Interface
Type
Method
Function
```

主要关系：

``` text
CONTAINS
DEFINES
CALLS
REFERENCES
IMPORTS
IMPLEMENTS
INHERITS
```

这一层回答：

-   某函数在哪里；
-   谁调用它；
-   它调用谁；
-   属于哪个类/文件；
-   模块之间如何依赖；
-   文档需求对应哪些实现。

### 5.2 第二层：Semantic Event Layer

这是 V2 的核心。

不持久化所有语句，只把对 36 类缺陷有意义的操作变成事件。

建议初始事件类型：

#### 数据访问

``` text
READ
WRITE
ASSIGN
DEREFERENCE
ADDRESS_TAKE
```

#### 内存与资源

``` text
ALLOC
RELEASE
ACQUIRE
OPEN
CLOSE
CREATE
DESTROY
```

#### 并发同步

``` text
LOCK
UNLOCK
TRY_LOCK
ATOMIC_READ
ATOMIC_WRITE
ATOMIC_RMW
WAIT
SIGNAL
THREAD_SPAWN
THREAD_JOIN
```

#### 控制行为

``` text
BRANCH
RETURN
THROW
CATCH
BREAK
CONTINUE
```

#### 安全/验证

``` text
CHECK
NULL_CHECK
BOUNDS_CHECK
AUTH_CHECK
ERROR_CHECK
```

#### 边界与调用

``` text
CALL
INPUT
OUTPUT
SINK
SOURCE
```

事件节点只保存最必要的信息：

``` text
event_id
event_type
owner_method_id
file_id
start_line
end_line
ordinal
target/value symbol id（可选）
operation subtype（可选）
flags
evidence_id
```

### 5.3 第三层：Defect Semantic Relations

核心关系建议包括：

``` text
READS
WRITES
PRODUCES
CONSUMES
RELEASES
ACQUIRES
PROTECTED_BY
MAY_PARALLEL
EXECUTES_IN
DATA_FLOW_TO
CONTROL_REACHES
CHECKS
DOMINATES_CHECK
MAY_ALIAS
RETURNS
THROWS_TO
CALLS
```

其中必须区分：

**确定关系**

``` text
WRITE Event ──WRITES──> Variable
ALLOC Event ──PRODUCES──> Resource
LOCK Event ──ACQUIRES──> Mutex
```

和：

**可能关系**

``` text
Event A ──MAY_ALIAS──> Resource B
Method A ──MAY_PARALLEL──> Method B
```

后者继续沿用三态证据思想，不应把推测伪装成确定事实。

------------------------------------------------------------------------

## 6. Sparse CFG：缺陷相关控制流

不存完整 CFG。

例如：

``` cpp
p = malloc(1024);
do_work();

if (error) {
    log_error();
    return;
}

cleanup_temp();
free(p);
return;
```

完整 CFG 会包含大量普通 statement。

稀疏 CFG 只保留：

``` text
ALLOC(p)
   │
   ▼
BRANCH(error)
  /          \
true         false
 │             │
RETURN      RELEASE(p)
                │
                ▼
              RETURN
```

定义：

`CONTROL_REACHES(A, B)`

表示：

> 从关键语义事件 A 出发，控制流可以到达关键语义事件
> B，中间允许经过被压缩掉的普通语句。

必要时增加：

``` text
branch=true
branch=false
exception
loop_back
```

作为 edge flags。

这样保留缺陷分析需要的路径信息，而不保留完整 statement graph。

------------------------------------------------------------------------

## 7. Sparse DFG：缺陷相关数据流

同样不存完整 def-use 图。

例如：

``` cpp
char *name = request->name;
char *tmp = name;
sprintf(buffer, tmp);
```

完整 DFG：

``` text
request->name
 → name
 → tmp
 → argument
 → sprintf
```

稀疏 DFG可以压缩成：

``` text
ExternalInput:request.name
        │
    DATA_FLOW_TO
        ▼
Call:sprintf
```

中间传播链作为 evidence/path metadata 保存，需要解释时再恢复。

核心原则：

> 数据流边优先于中间表达式节点。

对于缺陷检测，重点保留：

``` text
INPUT → SINK
ALLOC → USE
FREE → USE
NULL_SOURCE → DEREFERENCE
UNTRUSTED → EXEC/SQL/FORMAT/MEMORY
WRITE → READ
```

------------------------------------------------------------------------

## 8. 关键词规则的新定位

现有关键词和语义规则不应该删除。

例如：

``` text
completedCgNum
inFlightCgNum
Count
malloc
calloc
free
lock
mutex
```

但它们不再直接承担最终 Bug 判定。

新的角色是：

**Candidate Generator / Semantic Event Detector**

### 资源示例

``` text
malloc / calloc / new
        │
        ▼
候选 ALLOC
        │
tree-sitter 确认 CallExpression
        │
识别返回值 / 被赋值对象
        ▼
ALLOC(Resource X)
```

### 并发示例

``` text
completed / count / pending / inFlight
              │
              ▼
      Shared-state Candidate
              │
        references/writes
              │
              ▼
       Access Event Set
              │
       ┌──────┼──────┐
       ▼      ▼      ▼
     Thread   Lock   Atomic
       │      │      │
       └──────┼──────┘
              ▼
        Race Candidate
              │
              ▼
              AI
```

关键词负责提高召回率，结构化证据负责降低误报，AI负责最终语义判断。

------------------------------------------------------------------------

## 9. 36 类缺陷驱动 Schema，而不是 CPG 驱动 Schema

设计顺序应该是：

``` text
36 Defect Types
       ↓
Required Evidence
       ↓
Semantic Events
       ↓
Required Relations
       ↓
Graph Schema
```

而不是：

``` text
CPG 有什么
   ↓
全部实现
   ↓
再看哪些能检测 Bug
```

建议建立正式矩阵：

  -------------------------------------------------------------------------------
  Defect            Required Events          Required Relations Required Context
  ----------------- ------------------------ ------------------ -----------------
  Race Condition    READ, WRITE, LOCK,       WRITES, READS,     execution context
                    ATOMIC, THREAD\_\*       PROTECTED_BY,      
                                             MAY_PARALLEL       

  Resource Leak     ALLOC/ACQUIRE, RELEASE,  PRODUCES,          ownership
                    RETURN                   RELEASES,          
                                             CONTROL_REACHES    

  Use After Free    RELEASE,                 RELEASES,          alias
                    READ/WRITE/DEREFERENCE   DATA_FLOW_TO,      
                                             CONTROL_REACHES    

  Null Dereference  NULL source, CHECK,      DATA_FLOW_TO,      branch
                    DEREFERENCE              CHECKS,            
                                             CONTROL_REACHES    

  Double Free       RELEASE, RELEASE         RELEASES,          resource identity
                                             CONTROL_REACHES,   
                                             MAY_ALIAS          

  Deadlock          LOCK, UNLOCK             ACQUIRES,          lock order
                                             CONTROL_REACHES    

  Missing Error     CALL, CHECK, RETURN      PRODUCES, CHECKS,  API semantics
  Check                                      CONTROL_REACHES    

  Tainted Sink      INPUT/SOURCE, SINK       DATA_FLOW_TO       sanitizer/check
  -------------------------------------------------------------------------------

最终 36 类很可能共享约 20--30 种 Event 和有限的 Relation。

------------------------------------------------------------------------

## 10. Race Condition 的目标图

代码：

``` cpp
void onComplete() {
    completedCgNum++;
}

void finish() {
    if (completedCgNum == totalCgNum) {
        ...
    }
}
```

目标不是仅保存：

``` text
Method:onComplete
Method:finish
```

而是：

``` text
Method:onComplete
      │
   CONTAINS
      ▼
WriteEvent #1
      │
    WRITES
      ▼
Variable:completedCgNum

Method:finish
      │
   CONTAINS
      ▼
ReadEvent #2
      │
     READS
      ▼
Variable:completedCgNum
```

进一步：

``` text
WriteEvent #1 ──EXECUTES_IN──> WorkerThread
ReadEvent  #2 ──EXECUTES_IN──> CallbackThread

WriteEvent #1 ──PROTECTED_BY──> Mutex M
ReadEvent  #2 ──PROTECTED_BY──> none

Variable:completedCgNum
    atomic = false
```

Defect Query 得到：

``` text
shared variable = completedCgNum
writers = [...]
readers = [...]
execution contexts = [...]
common lock = none
atomic = false
parallelism = ambiguous/resolved
```

再交给 AI 判断。

------------------------------------------------------------------------

## 11. Resource Leak 的目标图

代码：

``` cpp
void foo() {
    char *p = malloc(1024);

    if (error()) {
        return;
    }

    free(p);
}
```

图：

``` text
ALLOC(p)
   │
   ▼
BRANCH(error)
 /           \
true         false
 │             │
RETURN      RELEASE(p)
```

查询：

``` text
ResourceLifetimeQuery(p)
```

目标是寻找：

``` text
ALLOC
  ↓ CONTROL_REACHES*
EXIT
```

且该路径上不存在：

``` text
RELEASE(same resource)
```

AI 得到的是候选泄漏路径，而不是整个函数 AST。

------------------------------------------------------------------------

## 12. 热 / 冷 / 冻三层存储

### 12.1 Hot：Semantic Topology

热层只存高频遍历信息：

``` text
Code KG nodes
Semantic Event nodes
Call edges
Sparse CFG edges
Sparse DFG edges
Semantic relations
```

推荐常驻内存。

持久化 ID 仍使用 ProvenLattice 的 SHA-256 stable
identity，但运行时映射为整数：

``` text
persistent SHA-256 ID → runtime uint32 ID
```

内存边：

``` text
src:uint32
dst:uint32
edge_type:uint8/uint16
flags:uint8/uint16
```

推荐 CSR / adjacency arrays。

优势：

-   traversal 不再产生 SQLite N-hop 往返；
-   不受 SQLite `IN (...)` 参数数量限制；
-   大幅减少字符串比较；
-   可以按 edge type 快速过滤；
-   遍历顺序可显式排序，保持确定性。

### 12.2 Cold：Evidence

冷层保存：

``` text
raw_references
candidate symbols
source spans
source snippets（可按需）
resolver provenance
semantic extraction evidence
compressed DFG path
ambiguous/unresolved evidence
rule hits
```

候选实现：

``` text
Parquet
或 SQLite 冷表
```

原则：

> 默认不进入 Agent 的图遍历，只在需要解释、验证和生成 citation 时按 id
> 获取。

### 12.3 Frozen：Snapshot

继续采用：

``` text
immutable shard
+
manifest
+
generation
```

支持：

-   金标实验；
-   full/incremental parity；
-   回归测试；
-   可复现分析；
-   snapshot diff；
-   overlay。

------------------------------------------------------------------------

## 13. 不建议把所有 Event 都无条件建图

Semantic Event 也应该分级。

### Level 0：始终提取

低成本、高价值：

``` text
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

### Level 1：按缺陷规则触发

例如：

``` text
READ
WRITE
DEREFERENCE
CHECK
BRANCH
```

只针对：

-   候选共享变量；
-   resource handle；
-   pointer；
-   tainted value；
-   sensitive state。

### Level 2：按查询临时展开

复杂 alias / deeper DFG / detailed CFG：

``` text
Agent/Detector 发现候选
        ↓
针对 1~N 个 Method
        ↓
重新读取源码 + AST
        ↓
临时构建 Detailed Local Graph
        ↓
完成检测后丢弃或缓存
```

因此整个系统可以形成：

**Global Sparse Graph + Local Deep Analysis**

这是空间和检测能力之间非常重要的平衡。

------------------------------------------------------------------------

## 14. 查询层不要以通用 N-hop BFS 为核心

当前通用：

``` text
get_subgraph(node, max_hops=N)
```

仍然保留给探索型 Agent。

但缺陷检测应该增加 typed query：

``` text
RaceQuery(variable)
ResourceLifetimeQuery(resource)
NullFlowQuery(value)
UseAfterFreeQuery(resource)
DoubleFreeQuery(resource)
LockOrderQuery(lock)
TaintPathQuery(source, sink)
ErrorHandlingQuery(call)
```

例如：

``` text
RaceQuery
  ↓
找到 Variable
  ↓
READS/WRITES 反向索引
  ↓
Access Events
  ↓
EXECUTES_IN
PROTECTED_BY
ATOMIC
MAY_PARALLEL
  ↓
Evidence Bundle
```

这样避免无差别扩张到整个"小世界"图。

------------------------------------------------------------------------

## 15. Defect Evidence Bundle

AI 的输入不应该默认是整个 subgraph。

统一定义：

``` json
{
  "defect_type": "race_condition",
  "subject": {
    "kind": "Variable",
    "name": "completedCgNum"
  },
  "facts": [],
  "uncertain_facts": [],
  "paths": [],
  "source_evidence": [],
  "missing_evidence": []
}
```

Race 示例：

``` json
{
  "defect_type": "race_condition",
  "subject": {
    "kind": "Variable",
    "name": "completedCgNum"
  },
  "facts": [
    {
      "event": "WRITE",
      "method": "onComplete",
      "atomic": false,
      "locks": []
    },
    {
      "event": "READ",
      "method": "finish",
      "atomic": false,
      "locks": []
    }
  ],
  "uncertain_facts": [
    {
      "relation": "MAY_PARALLEL",
      "status": "ambiguous"
    }
  ],
  "source_evidence": [
    "foo.cpp:182-184",
    "foo.cpp:271-274"
  ],
  "missing_evidence": [
    "runtime scheduling relationship"
  ]
}
```

AI 的任务变成：

1.  判断结构化事实是否满足缺陷条件；
2.  阅读少量对应源码；
3.  处理语言语义和业务语义；
4.  明确缺失证据；
5.  给出结论与解释。

而不是让 AI 自己从大段源码中完成所有静态分析工作。

------------------------------------------------------------------------

## 16. 三态证据扩展到语义图

现有：

``` text
resolved
ambiguous
unresolved
```

应该继续作为 V2 核心契约。

例如：

### DATA_FLOW

``` text
resolved:
A 确定流向 B
```

``` text
ambiguous:
A 可能流向 B/C
```

``` text
unresolved:
存在传播，但静态分析无法确定目标
```

### MAY_ALIAS

别名分析天然可能不确定，因此不要强制制造：

``` text
A ──ALIAS──> B
```

而应记录：

``` text
candidate relation
status = ambiguous
evidence = ...
```

### MAY_PARALLEL

线程、callback、异步框架同样如此。

原则：

> 不确定关系是 Evidence，不是 Fact Edge。

------------------------------------------------------------------------

## 17. 索引设计

Hot Graph 至少需要：

``` text
node_id → outgoing edges
node_id → incoming edges
edge_type → adjacency
method_id → semantic events
symbol_id → READ events
symbol_id → WRITE events
resource_id → lifecycle events
lock_id → lock events
event_id → evidence id
```

针对缺陷检测增加反向索引：

``` text
Variable → Readers
Variable → Writers

Resource → Allocators
Resource → Releasers
Resource → Users

Lock → Acquirers

Method → Execution Context

Source → Data-flow Sinks
```

这样 Race / Leak / UAF 等查询不需要全图 BFS。

------------------------------------------------------------------------

## 18. 空间优化原则

### 不存

``` text
完整 AST
所有 Identifier
所有 Literal
所有 Expression
所有普通 Statement
完整 CFG 中间节点
完整 DFG 中间表达式
大量重复 source text
```

### 存

``` text
稳定代码实体
缺陷相关 Event
高价值语义 Edge
Event source span
Evidence ID
必要 flags
```

### 压缩

``` text
SHA ID → runtime uint32
event type → uint8/uint16
edge type → uint8/uint16
flags → bitset
adjacency → CSR
冷证据 → Parquet dictionary/RLE
```

------------------------------------------------------------------------

## 19. 增量更新

继续利用现有 stable identity 和 file-level incremental update。

推荐流程：

``` text
File changed
    ↓
删除/失效该 File 对应 Semantic Events
    ↓
tree-sitter parse
    ↓
重建该 File 的 events
    ↓
重新解析局部 semantic relations
    ↓
检查 boundary/public fingerprint
    ↓
必要时重算跨文件关系
    ↓
更新 Hot Graph delta
```

避免每次重新生成整个 semantic graph。

------------------------------------------------------------------------

## 20. Local Deep Analysis

某些缺陷无法仅靠稀疏图可靠判断。

例如：

-   复杂 alias；
-   pointer arithmetic；
-   跨过程 ownership；
-   exception path；
-   template / macro；
-   virtual dispatch；
-   complicated lock state。

对此不应把全球图永久升级成完整 CPG。

使用：

``` text
Sparse Graph
    ↓
发现 Candidate
    ↓
定位 1~5 个相关 Method
    ↓
临时构建 Local AST/CFG/DFG
    ↓
生成更强 Evidence
    ↓
AI 判断
    ↓
临时图释放/缓存
```

这形成：

> **全局图负责找问题，局部深图负责证明问题。**

------------------------------------------------------------------------

## 21. AI 与静态规则的职责边界

### Parser / deterministic analyzer

负责确定事实：

``` text
这里调用 malloc
这里写变量 X
这里调用 mutex.lock
这里存在 return
这里存在 branch
```

### Rule / semantic extractor

负责形成候选语义：

``` text
X 可能是共享状态
Y 可能是资源 handle
Z 可能是敏感 sink
```

### Graph

负责：

``` text
连接事实
压缩路径
快速检索
保存 provenance
表达不确定性
```

### AI

负责：

``` text
语言/业务语义理解
复杂上下文判断
候选缺陷确认
误报过滤
解释
缺失证据识别
```

避免让 AI 去做机器更擅长的机械遍历，也避免让静态规则硬编码所有业务语义。

------------------------------------------------------------------------

## 22. 推荐实施阶段

### Phase 0：定义 36 类 Evidence Matrix

先不要改图。

为每个 defect 定义：

``` text
Defect
Required Events
Required Relations
Optional Evidence
Disqualifying Evidence
AI-required Semantics
```

这是整个 V2 Schema 的真实需求来源。

### Phase 1：Semantic Event MVP

优先支持两到四个价值最高、最能验证架构的缺陷族：

``` text
Race Condition
Resource Leak
Use After Free / Double Free
Null Dereference
```

先实现：

``` text
READ
WRITE
ALLOC
RELEASE
LOCK
UNLOCK
ATOMIC
BRANCH
RETURN
DEREFERENCE
CHECK
```

### Phase 2：Sparse CFG

只在 semantic events 之间建立：

``` text
CONTROL_REACHES
```

首先解决：

``` text
ALLOC → RETURN without RELEASE
CHECK → DEREFERENCE
FREE → USE
```

### Phase 3：Sparse DFG

增加：

``` text
DATA_FLOW_TO
PRODUCES
CONSUMES
MAY_ALIAS
```

优先覆盖 resource/pointer/input/sink。

### Phase 4：Typed Defect Query

实现：

``` text
RaceQuery
ResourceLifetimeQuery
NullFlowQuery
UseAfterFreeQuery
LockOrderQuery
```

### Phase 5：Hot CSR

将高频拓扑从 SQLite 查询路径迁移到内存 integer graph。

SQLite/Parquet 继续负责 persistence/evidence。

### Phase 6：Local Deep Analysis

为高价值候选动态构建局部 CFG/DFG，提高难例准确率。

------------------------------------------------------------------------

## 23. 推荐的最终 Schema

### Structural Nodes

``` text
Repository
Directory
File
Namespace
Class
Interface
Type
Method
Function
Variable（只针对重要变量）
Resource（语义资源）
Lock（语义同步对象）
ExecutionContext
Document
Requirement
```

### Semantic Event Nodes

``` text
ReadEvent
WriteEvent
AssignEvent
DereferenceEvent

AllocEvent
ReleaseEvent
AcquireEvent
OpenEvent
CloseEvent
CreateEvent
DestroyEvent

LockEvent
UnlockEvent
AtomicEvent
WaitEvent
SignalEvent
ThreadSpawnEvent
ThreadJoinEvent

BranchEvent
ReturnEvent
ThrowEvent

CheckEvent
CallEvent
InputEvent
OutputEvent
SourceEvent
SinkEvent
```

实现上不一定需要每种 Event 一种数据库 node kind；可以统一：

``` text
kind = SemanticEvent
event_type = READ / WRITE / ALLOC / ...
```

这样 schema 更稳定。

### Edges

``` text
CONTAINS
CALLS
REFERENCES
IMPORTS
IMPLEMENTS
INHERITS

READS
WRITES
PRODUCES
CONSUMES
ACQUIRES
RELEASES

PROTECTED_BY
EXECUTES_IN
MAY_PARALLEL

CONTROL_REACHES
DATA_FLOW_TO
MAY_ALIAS

CHECKS
RETURNS
THROWS_TO

DESCRIBES
CONSTRAINS
IMPLEMENTED_BY
VERIFIED_BY
```

------------------------------------------------------------------------

## 24. 一条完整的缺陷检测链

以 Race 为例：

``` text
Source Code
    ↓
tree-sitter
    ↓
发现 completedCgNum++
    ↓
WRITE Event
    ↓
关键词/命名规则判断为 shared-state candidate
    ↓
反查其他 READ/WRITE
    ↓
关联 Method / Call Graph / Execution Context
    ↓
提取 LOCK / ATOMIC
    ↓
形成 RaceQuery Result
    ↓
按需读取 raw evidence + source span
    ↓
Defect Evidence Bundle
    ↓
AI
    ↓
confirmed / likely / insufficient evidence / rejected
```

注意最后一层 AI 的缺陷结论状态，与底层 resolver 的
resolved/ambiguous/unresolved 不应混为一个概念。

底层三态描述：

> 图关系是否能被可靠解析。

AI 结论描述：

> 当前证据是否支持缺陷判断。

两者应分别建模。

------------------------------------------------------------------------

## 25. 核心设计原则总结

1.  **不做完整 CPG，只做缺陷导向的稀疏程序图。**
2.  **Method-level Code KG 保留，作为全局骨架。**
3.  **增加 Semantic Event，作为真正的缺陷分析粒度。**
4.  **AST 临时使用，不永久存储。**
5.  **CFG 只保留关键 Event 之间的控制可达关系。**
6.  **DFG 只保留缺陷相关 value flow。**
7.  **关键词从"Bug 判定器"变成"候选/事件发现器"。**
8.  **36 类缺陷反向决定 Schema。**
9.  **确定事实进入 Hot Graph；不确定关系进入 Evidence。**
10. **raw_references 是冷证据，不参与常规多跳。**
11. **热拓扑使用 integer ID + CSR/adjacency。**
12. **持久化继续保留 SHA-256 stable identity。**
13. **缺陷检测使用 Typed Query，而不是无差别 N-hop BFS。**
14. **给 AI 的是 Evidence Bundle，而不是整个图。**
15. **复杂问题采用 Global Sparse Graph + Local Deep Analysis。**
16. **保留 ProvenLattice
    的确定性、三态证据、增量一致性和跨层知识能力。**

------------------------------------------------------------------------

## 26. 最终定位

ProvenLattice V2 不需要成为 Joern 的替代品。

它更适合形成自己的定位：

> **A deterministic, evidence-preserving, defect-oriented sparse
> semantic program graph for AI-assisted code analysis.**

中文可以描述为：

> **面向 AI
> 代码缺陷检测的、确定性且保留证据与不确定性的稀疏语义程序图。**

它的核心竞争力不在于"存了多少 AST 节点"，而在于：

``` text
代码结构
+
缺陷语义事件
+
稀疏控制流
+
稀疏数据流
+
可信证据
+
文档↔代码跨层知识
+
AI 语义判断
```

最终目标是让 AI 不再主要依靠：

``` text
变量名像不像有问题
API 名像不像危险函数
```

而是获得：

``` text
谁创建了资源
谁释放了资源
哪些路径可能绕过释放

谁读写共享状态
在哪些执行上下文
是否有共同锁
是否 atomic

值从哪里来
经过什么关键语义操作
最终流向什么危险点
```

也就是把检测范式从：

**Keyword → AI Guess**

升级为：

**Candidate Rule → Semantic Graph → Evidence Path → AI Judgment**

这应该是 ProvenLattice 面向 AI 缺陷检测最值得发展的主线。

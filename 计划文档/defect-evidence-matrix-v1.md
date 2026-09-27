# ProvenLattice 缺陷证据矩阵 V1 —— 9 大类 38 小类

> 2026-09-20 · 按**代码操作种类**分类，CWE 编号作为**并列参考列**

## 分类依据

本表按「**代码里的哪种操作出了问题**」切分，不再按 CWE 根因切分。

理由：本项目的检测能力来自代码图（Semantic Event + Sparse CFG/DFG）。每个操作类对应一组不同的图特征，按操作分类能让「类别 ↔ 图能力」直接对齐。CWE 是按根因切分的另一条轴，两套轴不可能一一对齐。

因此 CWE 编号在本表中退化为**参考列**，用途是查证与对外引用，**不是分类依据**。

三条由此产生的结果：

- 一个操作类可能引用多个 CWE（如 `6.5` → CWE-131 + CWE-469）
- 一个 CWE 可能被多个操作类引用（如 CWE-457 同时出现在 `5.3` 与 `7.4`）
- 部分操作类没有直接对应的 CWE（如 `1.2 原子性缺失`、`2.4 浮点精度与不安全比较`）

## 关于 CWE 编号

**CWE = Common Weakness Enumeration**，MITRE 维护的软件弱点标准目录，可在 `cwe.mitre.org` 按编号检索条目官方定义。

四级说明：

**1. 数字本身没有内在含义。** 它纯粹是词条号（类似字典页码），不是编码、不代表严重程度、不代表出现频率。`CWE-480` 只有一种读法：去查第 480 条。

**2. 编号区间有历史性的粗略分组，但不可靠。** 大致上 100 段偏内存/缓冲区（787 越界写、125 越界读、120 复制无边界），400 段偏资源管理（401 泄漏、415 双释放、416 释放后使用）。但 `362`（竞态）与 `369`（除零）同在 300 段而主题毫不相关 —— **不能靠数字猜内容**。

**3. CWE 是分层的**，一条具体编号处在某个抽象层级上：

```text
CWE-664  Pillar  资源生命周期的控制不当（最抽象）
   └─ CWE-404  Class   资源关闭或释放不当
        ├─ CWE-401  Base    内存资源未释放（= 内存泄漏）
        └─ CWE-772  Base    资源在其有效生命周期后未释放
```

本表使用的是**最具体的那一层**。

**4. 每个条目页面上有**：描述、常见后果、缓解措施、代码示例、父子关系。

### 两个易混条目的对照

| 编号 | 官方名称 | 含义 | 例子 |
|---|---|---|---|
| CWE-480 | Use of Incorrect Operator | **运算符用错** —— 该用的符号写成了另一个 | `if (a = b)`（该 `==` 写成 `=`）、`a & b`（该 `&&`）、`x - 1`（该 `+ 1`） |
| CWE-697 | Incorrect Comparison | **比较写错** —— 符号对但比的东西或方向不对 | 比错字段、`<` 该 `<=`、两个不该比的对象互比 |

两者近亲但不等价：480 是「符号打错」，697 是「比较写错」（含符号正确但对象错）。`7.1` 同时引用两者，因为这类缺陷常从「打错一个符号」滑到「比错一个对象」，边界模糊。

> ⚠️ **本表 CWE 编号尚未逐个核对 cwe.mitre.org**（2026-09-20 复核工作中止，仅完成 1 条）。
>
> 已确认一条错误：**`7.2` 引用的 CWE-374 实为 "Passing Mutable Objects to an Untrusted Method"**（把可变对象交给不受信方法），与浅拷贝 / 深拷贝无关 —— 该行编号必须替换，替换目标尚未查证。
>
> 其余编号在正式对外引用前仍需逐条复核。

## 能力分级

| 级 | 含义 |
|---|---|
| **A** | 只需 Semantic Event + Sparse CFG |
| **B** | 还需 Sparse DFG |
| **C** | 稀疏图不够，需 Local Deep Analysis |

> ⚠️ **本轮分级为初判。** 该分级轴只回答「哪一层图提供证据」，不回答「图之外还需要多少外部语义（API 契约、ownership 规则、执行上下文）」。后者是隐藏维度，补完各类的 Required Events / Required Relations / Optional Evidence / Disqualifying Evidence / AI-required Semantics 五个字段后需整体重评。

### 这条轴怎么读

它只回答**一个问题**：要判定这一类缺陷，**最少需要图的哪一层**。它是**成本轴** —— 决定「实现这类检测必须把图建到哪一层」，不是难度轴。

**A —— 事件 + 控制流就够。** 只需知道「发生了哪些关键操作」和「这些操作之间控制流能否走到」。

- `4.1 内存泄漏`：有 `ALLOC`，从它出发控制流可达 `RETURN`，且这条路径上没有 `RELEASE` —— 候选即成立。**不需要知道值怎么流动。**
- `1.4 重复加锁`：同一把锁上出现两次 `LOCK`，中间没有 `UNLOCK`。

**B —— 控制流不够，必须上数据流。** 必须知道「这个值和那个值是不是同一个东西」。

- `4.3 释放后使用`：必须确认 `free(p)` 的 `p` 与后面 `p->field` 的 `p` 指向同一对象 —— 这是**别名**问题，控制流看不出来。
- `3.1 空指针解引用`：必须知道 `p = get()` 的返回值流到了 `p->field`，且中间经过 `if (p)` 检查。

**C —— 稀疏图证据不足，要局部深图。** 必须针对 1~5 个候选方法**临时重建局部 AST/CFG/DFG**。

- `8.1 类型转换错误`：需要真正的类型模型，tree-sitter 只有签名文本。

> **它是必要条件轴，不是充分条件轴。** 例：`1.1 共享数据竞态` 是 A 级 —— 事件 + 控制流足以定位「谁读了、谁写了、有没有共同锁」。但要判定它**真的是**竞态，还需要 API 契约（这把 mutex 真保护这个变量吗）与执行上下文（这两个方法真并行吗），这两样图里没有。

**当前分布（A 13 / B 23 / C 2）本身是个结论**：**六成缺陷落在 B 级，即需要 DFG**。这正是设计文档最大的未验证假设 —— 「稀疏图足以支撑缺陷判定」—— 的暴露点：如果 B 类真的都需要 DFG，DFG 就不是可选项；反之若阶段 4 的 `RaceQuery` / `ResourceLifetimeQuery` / `LockOrderQuery` 能用 Event+CFG 跑通，说明 B 类划分偏保守，DFG 的范围可以收窄。

---

## 1. 并发安全类（5）

| # | 小类 | CWE | 级 |
|---|---|---|---|
| 1.1 | 共享数据竞态（共享变量无保护读写） | 362 | A |
| 1.2 | 原子性缺失（复合操作未原子化，check-then-act / `++` 失原子） | — | A |
| 1.3 | 死锁 / 锁序错误（死锁是效果，锁序是成因，判据共用同一组图特征） | 833 / 696 | B |
| 1.4 | 重复加锁 / 锁不可重入 | 764 | A |
| 1.5 | 同步原语误用 | 821 | B |

## 2. 数值计算类（4）

| # | 小类 | CWE | 级 |
|---|---|---|---|
| 2.1 | 整数溢出 / 回绕（含下溢） | 190 / 191 | B |
| 2.2 | 中间表达式溢出（`a*b/c` 中 `a*b` 先溢出，最终结果本可容纳） | 190 变体 | B |
| 2.3 | 除零 / 取模零 | 369 | A |
| 2.4 | 浮点精度损失与不安全比较（`==` 比较浮点、累加误差） | — | C |

## 3. 指针操作类（5）

| # | 小类 | CWE | 级 |
|---|---|---|---|
| 3.1 | 空指针解引用 | 476 | B |
| 3.2 | 未初始化指针访问 | 824 | B |
| 3.3 | 悬垂指针解引用（含返回局部变量地址） | 825 / 562 | B |
| 3.4 | 空值检查缺陷（检查被绕过 / 检查后又置空） | 476 变体 | A |
| 3.5 | 函数指针与回调误用 | 824 / 456 | B |

## 4. 资源管理类（6）

| # | 小类 | CWE | 级 |
|---|---|---|---|
| 4.1 | 内存泄漏 | 401 | A |
| 4.2 | 双重释放 | 415 | B |
| 4.3 | 释放后使用 | 416 | B |
| 4.4 | 非堆内存 / 非法指针释放 | 590 | B |
| 4.5 | 非内存资源泄漏与关闭不当 | 772 / 404 | A |
| 4.6 | 错误路径清理不完整（含锁未释放） | 459 / 667 | A |

## 5. 内存操作类（4）

> 范围：对**活内存**做内容操作时的 API 用法错误。生命周期问题（分配↔释放配对）归 `4 资源管理类`。

| # | 小类 | CWE | 级 |
|---|---|---|---|
| 5.1 | 内存复制区域重叠（`memcpy` 应 `memmove`） | 120 族 | B |
| 5.2 | 内存 API 长度 / 大小参数错误（`sizeof(ptr)`、元素数当字节数） | 467 / 120 | A |
| 5.3 | 未初始化内存读取（缓冲区级） | 457 | B |
| 5.4 | 分配大小与写入大小不一致 | 131 | B |

## 6. 内存计算类（5）

> 范围：**地址 / 大小 / 偏移 / 索引的算术**错误。

| # | 小类 | CWE | 级 |
|---|---|---|---|
| 6.1 | 越界写 | 787 | B |
| 6.2 | 越界读 | 125 | B |
| 6.3 | off-by-one 边界错误 | 193 | B |
| 6.4 | 索引 / 长度未校验 | 129 | A |
| 6.5 | 大小计算溢出与指针算术越界 | 131 / 469 | B |

## 7. 赋值与引用类（4）

| # | 小类 | CWE | 级 |
|---|---|---|---|
| 7.1 | 赋值目标错误（错变量 / 复制粘贴 / `=` 与 `==` 混淆） | 480 / 697 | B |
| 7.2 | 浅拷贝与深拷贝混淆（指针成员浅拷贝） | 374 ⚠️待核 | B |
| 7.3 | 引用生命周期错误（返回局部 / 临时对象的引用） | 562 | A |
| 7.4 | 未初始化变量使用（变量级） | 457 | B |

> **`5.3` 与 `7.4` 共用 CWE-457，必须分列**：一个是缓冲区级（`malloc` 后未初始化即读），一个是变量级（局部变量声明未赋值即读）。判据与所需证据不同，编号相同容易混。

## 8. 类型系统类（1）

| # | 小类 | CWE | 级 |
|---|---|---|---|
| 8.1 | 类型转换错误（单位转换）—— 例如应该用毫秒的地方用了秒；扇区计算、单位运算错误 | — | C |

> ⚠️ **整类为 C 级。** tree-sitter 只提供签名文本，**没有语义类型模型**。本类的核心判据（两个类型是否可安全转换）超出现有架构能力，需要 libclang 级前端。**V2 范围内本类不可实现**，此处仅作**架构边界**的登记。

## 9. 错误处理类（4）

| # | 小类 | CWE | 级 |
|---|---|---|---|
| 9.1 | 未检查返回值 | 252 | A |
| 9.2 | 错误条件未处理 | 391 | B |
| 9.3 | 缺少错误传播 / 报告 | 392 | A |
| 9.4 | 异常未捕获与异常安全 | 248 | B |

---

## 分级汇总

| 级 | 小类数 |
|---|---:|
| A | 13 |
| B | 23 |
| C | 2 |
| **合计** | **38** |

---

## 优先族五字段展开（附录 B 阶段 1 执行 · 2026-09-21）

> 执行上文裁决 #6：五个证据字段**只对 4 个优先族（5 条小类）展开**，其余 33 条明确不铺，进入对应 typed query 实施时再补。
>
> **消费方**：阶段 3（Sparse CFG）/ 阶段 4（Typed Query 第一批）/ 阶段 5（Sparse DFG）。阶段 4 的 `RaceQuery` / `NullFlowQuery` / `ResourceLifetimeQuery` / `DoubleFreeQuery` / `UseAfterFreeQuery` 按本节验收。
>
> **事实锚定**：
> - Level 0 词表（`semantics/vocabularies/cpp.toml`）现有事件：`CALL / RETURN / THROW / ALLOC / RELEASE / LOCK / UNLOCK / ATOMIC / THREAD_SPAWN / THREAD_JOIN`。
> - `READ / WRITE` **不在** Level 0 —— 按设计文档 §13 属 Level 1（按缺陷规则触发），下文标「⚠️ 缺口」。
> - Defect Semantic Relations（`WRITES / READS / PRODUCES / CONSUMES / RELEASES / ACQUIRES / PROTECTED_BY / MAY_PARALLEL / EXECUTES_IN / DATA_FLOW_TO / CONTROL_REACHES / CHECKS / DOMINATES_CHECK / MAY_ALIAS / RETURNS / THROWS_TO`）**均不存在**——它们是设计文档 §5.3/§10/§11/§16 的定义，本节就是它们的需求出处。
> - 三态契约（§16）继续适用：所有「可能关系」（`MAY_ALIAS` / `MAY_PARALLEL` / 不确定的 `PROTECTED_BY`）必须以 resolved / ambiguous / unresolved 表达，不把推测伪装成事实。
> - 分工（§15/§21）：确定性图谱只做**候选生成**（产出证据束：facts + uncertain_facts + missing_evidence）；**判定**归 AI。

### 1.1 共享数据竞态（初判 A）→ `RaceQuery`

| 字段 | 内容 |
|---|---|
| Required Events | `READ` / `WRITE`（⚠️ 缺口，Level 1）；`LOCK` / `UNLOCK`；`ATOMIC`；`THREAD_SPAWN` / `THREAD_JOIN`（均已落库） |
| Required Relations | `WRITES` / `READS`（Access Event → Variable）；`EXECUTES_IN`（Access → 执行上下文）；`PROTECTED_BY`（Access → Mutex，三态）；`MAY_PARALLEL`（Method ↔ Method，三态，预期多为 ambiguous） |
| Optional Evidence | `CONTAINS`（定位方法）；`THREAD_SPAWN` 调用点（入口函数 → 与执行上下文对账，收窄 `MAY_PARALLEL`） |
| Disqualifying Evidence | 两侧 `PROTECTED_BY` resolved 且指向**同一** Mutex；任一侧 `ATOMIC` resolved；`MAY_PARALLEL` resolved = false（同上下文串行） |
| AI-required Semantics | 锁 ↔ 变量的保护约定（这把 mutex 是否真守护这个变量——API/ownership 契约）；两上下文是否真并发（回调注册、线程池复用）；竞态后果是否实际有害（计数器容忍弱一致 vs 一致性敏感） |

**判定**：候选生成只需 Event + `CONTROL_REACHES` —— **A 维持**。⚠️ 两段性：两侧访问拼写不同（`p->field` vs `obj.field`）时 Variable 归一需要轻量别名（DFG 域），**确认阶段滑向 B**；候选生成不需要。

### 3.1 空指针解引用（初判 B）→ `NullFlowQuery`

| 字段 | 内容 |
|---|---|
| Required Events | `CALL` / `RETURN`（潜在 null 源与传播）；`READ` / `WRITE`（解引用点，⚠️ 缺口）；`THROW`（错误路径传播） |
| Required Relations | `DATA_FLOW_TO`（null 源 → 解引用点，三态）；`CHECKS`（解引用前判空）；`DOMINATES_CHECK`（判空支配解引用 → 已防护）；`RETURNS`（null 沿返回值传播） |
| Optional Evidence | 同方法内 `CHECKS` 全集（判定「部分路径未检查」）；`CALLS`（null 是否来自跨函数返回） |
| Disqualifying Evidence | 到解引用的每条 `CONTROL_REACHES` 路径上 `DOMINATES_CHECK` 成立；源不可能为 null（`new`（非 nothrow）、构造语义——由 AI 侧 API 契约给出） |
| AI-required Semantics | API 可空性契约（哪些函数能返回 NULL：`malloc` 会、`pthread_mutex_lock` 不会）；仓库错误处理风格（错误码 vs 异常）；变量初始化不变量 |

**判定**：必须回答「流到解引用点的值，是不是那个可能为 null 的值」——**B 维持**（Sparse DFG 前置）。

### 4.1 内存泄漏（初判 A）→ `ResourceLifetimeQuery`

| 字段 | 内容 |
|---|---|
| Required Events | `ALLOC`；`RELEASE`；`RETURN` / `THROW`（非局部出口：控制流离开即视为生命周期终点） |
| Required Relations | `PRODUCES`（ALLOC → Resource）；`RELEASES`（RELEASE → Resource）；`CONTROL_REACHES`（ALLOC → 出口，带 `branch` / `exception` flags）；`RETURNS` / `CONSUMES`（所有权转移出方法 = 不泄漏） |
| Optional Evidence | `CALLS`（释放封装在 callee 内）；`LOCK` / `UNLOCK`（`4.6` 错误路径锁未释放共用本判据） |
| Disqualifying Evidence | 每条 ALLOC→出口路径被 `RELEASES`（同资源）支配；资源经 `RETURNS` / `CONSUMES` 转移出去 |
| AI-required Semantics | 所有权约定（callee 是否接管：容器接管元素、`g_object_*` floating ref / sink、Out 参数移交）；RAII 封装（`unique_ptr` 无显式 RELEASE——作用域退出即释放，图谱只见构造） |

**判定**：候选生成只需「ALLOC 可达出口且路径上无 RELEASE」——**A 维持**。⚠️ 两段性：重赋值（`p = realloc(p,…)`）与别名释放（`q = p; free(q)`）的资源同一性属 DFG 域，**确认阶段滑向 B**；候选生成不需要。

### 4.2 双重释放（初判 B）→ `DoubleFreeQuery`

| 字段 | 内容 |
|---|---|
| Required Events | `ALLOC`；`RELEASE` ×2；`THROW`（异常路径重复清理） |
| Required Relations | 两条 `RELEASES` 指向同一 Resource；`CONTROL_REACHES`（第一 RELEASE → 第二 RELEASE，同一路径）；`MAY_ALIAS`（两个指针表达式可能同一对象，三态）；`DATA_FLOW_TO`（指针复制链 `q = p`） |
| Optional Evidence | 两次 RELEASE 之间的 `CALLS`（释放型封装）；`loop_back` flag（跨迭代重复释放） |
| Disqualifying Evidence | 两次 RELEASE 分支互斥（`branch=true` / `branch=false`）；之间有对同一资源的再 `ALLOC` |
| AI-required Semantics | 所有权移交后原指针失效的仓库惯例（`free(p)` 后是否置 NULL）；释放封装函数语义（`my_free(p)` 内部是否置空、是否只释放一半） |

**判定**：核心是「这两次释放是不是同一个对象」——值同一性/别名，**B 维持**。

### 4.3 释放后使用（初判 B）→ `UseAfterFreeQuery`

| 字段 | 内容 |
|---|---|
| Required Events | `RELEASE`；`READ` / `WRITE`（解引用型使用，⚠️ 缺口）；`CALL`（把指针传给 callee 也是使用）；`RETURN` / `THROW` |
| Required Relations | `CONTROL_REACHES`（RELEASE → USE，同一路径）；`DATA_FLOW_TO` / `MAY_ALIAS`（使用的表达式与被释放的是否同一对象）；`CHECKS`（`free(p); p = NULL` 惯用法 = 已防护） |
| Optional Evidence | RELEASE 与 USE 之间的 `CALLS`（callee 内重分配）；`loop_back`（跨迭代 UAF） |
| Disqualifying Evidence | RELEASE 与 USE 之间有同资源再 `ALLOC`；USE 只读**指针值**（赋值、比较、传给释放函数均合法——非法的是解引用型使用）；置空守卫生效 |
| AI-required Semantics | 「使用」的精确定义需 AI 区分：读指针值合法、读 pointee 非法；封装释放语义；句柄类（fd / socket 的 close-then-use 同判据不同 API 词表） |

**判定**：同 4.2，同一性判定 —— **B 维持**。

### 复核结论

| 小类 | 初判 | 复核 | 备注 |
|---|---|---|---|
| 1.1 竞态 | A | **维持 A** | 两段性：候选 A / 别名确认滑向 B |
| 3.1 空指针 | B | **维持 B** | 最小集 = `DATA_FLOW_TO` + `DOMINATES_CHECK` |
| 4.1 泄漏 | A | **维持 A** | 两段性：候选 A / 重赋值与别名确认滑向 B |
| 4.2 双释放 | B | **维持 B** | 同一性 = `MAY_ALIAS` + `DATA_FLOW_TO` |
| 4.3 UAF | B | **维持 B** | 「使用」定义需区分指针值 / pointee |

> **「两段性」修正了初判的一句话表述**：A 类不是「完全不需要 DFG」，而是「**候选生成**不需要，**确认**可能需要」。这与上文「当前分布」一节的预期互相印证：阶段 4 第一批 typed query 按 A 类候选语义实现即可，不阻塞在 Sparse DFG 上；若候选→确认的滑移面过大，再回头收窄/扩宽 DFG 范围。

---

## 明确不在范围内

| 项 | 理由 |
|---|---|
| 命令注入（CWE-78）、SQL 注入（CWE-89） | 属安全域，需完整 taint 分析（SOURCE/SINK + `DATA_FLOW_TO` + 净化点识别），V2 范围外 |
| 格式化字符串（CWE-134） | 同上，按 V1 决策整类删除 |
| 空终止符缺失（CWE-170） | 同上，按 V1 决策整类删除 |
| 线程内竞态（CWE-366） | 信号处理场景，目标仓中罕见 |
| 完整 CPG | 见设计文档 §2 |

---

## 裁决记录（2026-09-20）

| # | 议题 | 裁决 |
|---|---|---|
| 1 | `4.3 释放后使用` 的归属 | **留在 `4 资源管理类`** —— 与 `4.2 双重释放` 同属「分配↔释放配对」违例，拆开会割裂 |
| 2 | `1.3 死锁` 与 `1.5 锁序错误` | **合并为一条** `1.3 死锁 / 锁序错误`。死锁是效果、锁序是成因，判据共用同一组图特征。合并后 `1.6` 顺延为 `1.5`，本类 6 → 5 条 |
| 3 | `8 类型系统类` 是否保留 | **保留**，但压成单条 `8.1 类型转换错误（单位转换）`。整类仍标注 C 级 / V2 不可实现，作用是**登记架构边界**。「明确不在范围内」中的「单位转换错误」一行随之删除，避免同一项两处并存 |
| 4 | A/B/C 分级轴 | **保留并沿用**。它是**成本轴**，不是难度轴，也不是充分条件轴 —— 见上节「这条轴怎么读」 |
| 5 | CWE 编号核对 | **中止**（2026-09-20）。仅确认 `7.2` 的 CWE-374 有误，其余保持待核 |
| 6 | 五个字段 | **本轮不补**。留到进入阶段 2 之前，只对优先族（竞态 / 泄漏 / 双释放·UAF / 空指针）展开，不一次铺满 38 条 |

> ⚠️ **本轮 38 条 A/B/C 分级均为初判**，待补完五字段后需整体重评。

---

## 执行记录（2026-09-21 · 附录 B 阶段 1）

- **裁决 #6 已执行**：优先族五字段展开完成（见「优先族五字段展开」一节，5 条小类），其余 33 条按裁决不铺，留待对应 typed query 实施时展开。
- **A/B/C 复核**：5 条初判全部维持；1.1 与 4.1 登记「候选生成 A / 确认滑向 B」的两段性注记。
- **实现缺口登记**（即本矩阵作为需求来源的产出，均尚不存在）：
  - `READ / WRITE` 事件 —— Level 1（设计文档 §13，按缺陷规则触发），阶段 4 五条 typed query 的共同前置；
  - 全部 Defect Semantic Relations（§5.3 清单）—— 阶段 3（`CONTROL_REACHES`）/ 阶段 5（`DATA_FLOW_TO` / `MAY_ALIAS`）的产出；
  - `CHECKS` / `DOMINATES_CHECK` 的支配关系计算 —— 阶段 3 语义。
- **CWE 编号**：按「暂不核对」约束未动；`7.2` 的 CWE-374 错误标记保留原样。

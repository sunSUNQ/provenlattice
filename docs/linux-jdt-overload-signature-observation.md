# 重载调用点 signature 展示口径观察（不修改行为的正式记录）

> 性质：观察记录 + 待查清单。**不构成修复，不下结论**；是否修复由
> Owner 另立决策。关联：Issue Pilot #8 · docs/linux-jdt-verification-report.md §4。

## 1. 现象

`revalidation/linux-jdt-verify` fixture（`g.greet("ci")` 与 `g.greet()` 同行两个调用）
在 `java-semantic --mode full` 的行级绑定输出中：

| 字段 | 两个调用点 |
|---|---|
| `state` | resolved / resolved |
| `decl` | com.example.Greeter / com.example.Greeter |
| `signature` | **greet() / greet()** |
| `expr` | greet / greet |

`g.greet("ci")` 的 `signature` 期望为 `greet(String)`，实测报告 `greet()`。
merge audit 视角下两调用合并为单 site（file+line+expr 相同），JDT 绑定行
显示同一 `greet()`。

## 2. 精确复现

```bash
# 在 provenlattice 仓库根（含 revalidation/linux-jdt-verify）
python revalidation/linux-jdt-verify/verify_linux_jdt.py \
  --jdk "$JAVA_HOME" --jars-dir <signature-stripped JDT jars> \
  --out <out-dir>
# 查看 <out-dir>/step3-full-raw.json 的 bindings 与
# merge_audit.sites[].jdt.signature；亦可直接：
provenlattice index revalidation/linux-jdt-verify/fixture
provenlattice java-semantic revalidation/linux-jdt-verify/fixture \
  --mode full --json
```

## 3. 证据

- Windows 基线与 Linux CI 均复现（跨平台一致）：
  PR #14 CI run [39368175665](https://github.com/sunSUNQ/provenlattice/actions/runs/39368175665)，
  artifact `linux-jdt-verify-raw`（step3-full-raw.json / step4-fail-closed.json）。
- L1 层对照：两调用在 L1 raw_references 中均为 ambiguous（R1 demote，
  `receiver_type_unknown`），JDT 恢复计入 `recovered_by_jdt`。

## 4. 待查口径（不是结论）

1. `signature` 字段在 P2bDriver 中的构造来源（IMethodBinding 的哪个 API）；
2. T9-B 21 gold 记录中重载 case 的 signature 口径（当时是否区分重载）；
3. 该字段是"展示口径"还是"解析结果"——`decl`/`state` 正确，若仅展示层
   简写，影响面为 UX；若绑定本身未区分重载，则为正确性问题候选。
4. 若需修复：涉及 src（P2bDriver / java_semantic），须另立 Issue + Owner
   批准（本记录按合同未触碰 src）。

## 5. 建议

另立 `type:research` Issue 复核 P2bDriver 的 binding→signature 构造路径，
先以 T9-B gold 重放判定"展示 vs 解析"，再决定是否修复；修复后应在
linux-jdt-verify fixture 上固化为断言（当前断言仅要求 resolved≥2，不校验
signature 文本，避免把待查口径冻结进 golden）。

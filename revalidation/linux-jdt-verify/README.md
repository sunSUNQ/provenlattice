# Linux JDT Verification (Issue Pilot #3)

目标：在受控 Linux 环境完成 Stage-0 定义的 6 步 JDT 兼容性验证
（`docs/java-beta-stage0-report.md` Phase 1，补测条件第 27 行），把
Linux JDT 从 `NOT_VERIFIED` 更新为实测结论。

## 环境

- Linux 执行环境 = GitHub Actions `ubuntu-latest`（CI 可自动化，
  Stage-0 Phase 4 A 项建议路径）
- JDK = Temurin 21（`actions/setup-java`）
- JDT 套件 = Maven Central 固定坐标重建（`jdt-suite-pom.xml`），
  重建后剥离 META-INF 签名（T9-B workaround，
  `strip_signatures.py`）。坐标来源：
  `docs/java-overnight-longrun-v1/t9b/comparison.json`（3.37.0 套件）
  + 归档 jar 内 `pom.properties` 恢复的精确版本。

## 步骤定义（`verify_linux_jdt.py`）

| 步骤 | 内容 | 通过标准 |
|---|---|---|
| S1 index | fixture 全量建图 | 命令 rc=0 且 nodes/edges/raw_references 计数 = golden |
| S7 parse-error | `analyze ast/cfg java`（tree-sitter 层，无 JVM） | `Broken.java`（语法错误反例）被 ast:java 部分提取；cfg:java 报告 `methods_skipped_parse_error >= 1` 且仅构建 3 个合法方法（Greeter×2、Runner×1）——解析错误方法显式跳过，不产出猜测 CFG |
| S2 status-only | 带 JDK+classpath → available；缺 JDK → unavailable/jdk_not_found | 显式状态，不静默 |
| S3 full | JDT full 模式逐调用点绑定 + L1 merge audit | status=available 且 fixture 调用点 resolved ≥ 2 |
| S4 fail-closed | classpath 中混入损坏 jar | status=failed 且 reason 非空，无部分成功 |
| S5 fingerprint | P2-C classpath 契约指纹重复构建 + 路径拼写变体 | 指纹字节一致 |
| S6 compare | 归一化 S3 输出 vs 提交的跨平台 golden（Windows/Temurin 21 生成） | 字节一致 |

S7 于 Issue Pilot #10 加入（PR #13 `methods_skipped_parse_error` 合同的
验证器可见性）；S1–S6 既有断言不变，golden 仅随 fixture 增加而追加新计数。

归一化规则：排除绝对路径与环境相关字段（classpath_fingerprint 等），
file 截断为 fixture 相对路径；原始输出不参与跨平台比较，仅归档。

## 运行

```bash
# 基线宿主（生成 golden）
python revalidation/linux-jdt-verify/verify_linux_jdt.py \
  --jdk "$JAVA_HOME" --jars-dir <stripped jars> \
  --out out --emit-golden

# 验证宿主（CI，ubuntu）
mvn -f revalidation/linux-jdt-verify/jdt-suite-pom.xml dependency:copy-dependencies \
  -DoutputDirectory=<jars> -DincludeScope=runtime
python revalidation/linux-jdt-verify/strip_signatures.py <jars>
python revalidation/linux-jdt-verify/verify_linux_jdt.py \
  --jdk "$JAVA_HOME" --jars-dir <jars> --out out
```

## 结果记录

- CI job：`.github/workflows/ci.yml` → `linux-jdt-verify`（raw 输出
  以 artifact 归档）
- 报告：`docs/linux-jdt-verification-report.md`

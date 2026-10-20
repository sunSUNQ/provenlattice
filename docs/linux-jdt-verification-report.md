# Linux JDT 兼容性验证报告（Issue Pilot #3）

**状态：`WINDOWS_BASELINE_COMPLETE` · Linux 结果待 CI 首跑填入**
日期：2026-10-20 · 关联：`docs/java-beta-stage0-report.md` Phase 1 / Phase 4 A 项

---

## 1. 方法

Stage-0 定义的补测条件（第 27 行）：Linux 环境 + Temurin 21 + JDT jar 集
+ provenlattice 安装 → 6 步验证。本验证的实现载体：

- **Linux 执行环境**：GitHub Actions `ubuntu-latest`
  （CI 新增 job `linux-jdt-verify`；对应 Stage-0 Phase 4 "CI 可自动化"）
- **JDT 套件**：Maven Central 固定坐标重建（`revalidation/linux-jdt-verify/jdt-suite-pom.xml`），
  重建后剥离 META-INF 签名（T9-B workaround，`strip_signatures.py`）。
  坐标来源：T9-B 记录（jdt.core 3.37.0 + ecj 3.37.0）+ 归档 jar 内
  `pom.properties` 恢复的精确版本（javaparser 3.26.4、guava 33.2.1-jre、
  slf4j 2.0.13、osgi.service.prefs 1.1.2）；Eclipse platform jars 由
  jdt.core 3.37.0 POM 的不可变依赖钉扎解析。
- **6 步定义**：`revalidation/linux-jdt-verify/README.md`
  （S1 index / S2 status-only / S3 full / S4 fail-closed / S5 fingerprint /
  S6 compare；比较用归一化 JSON，绝对路径与时序字段排除；原始输出归档）

## 2. Windows 基线（golden 宿主）

| 项 | 值 |
|---|---|
| 宿主 | Windows（本机） |
| JDK | Temurin 21.0.12.1 |
| JDT 套件 | T9-B 已验证归档 jar（签名已剥离，与 CI 重建套件同版本清单） |
| 结果 | **9/9 PASS**（S1 计数=golden、S2 available+fail-closed、S3 resolved≥2、S4 显式失败、S5 指纹字节稳定、S6 归一化 golden 一致） |
| fixture | `revalidation/linux-jdt-verify/fixture/`（2 文件：Greeter 重载对 + Runner 实例调用） |

## 3. Linux 结果（CI 首跑后填入）

| 步骤 | 结果 |
|---|---|
| S1–S6 | 待 `linux-jdt-verify` job 首次运行；raw 输出见 artifact `linux-jdt-verify-raw` |

补测条件中的"对比"实现为：Linux 归一化输出 vs 提交的 Windows golden
（S6），字节一致即跨平台确定性成立。

## 4. 观察（不阻断本 Issue；如实记录）

1. **JDT 恢复能力按预期工作**：L1 层因 R1 demote 为 ambiguous 的
   identifier-receiver 调用（`g.greet`），JDT 绑定后经 merge 计入
   `recovered_by_jdt`（fixture merge_audit counts.recovered_by_jdt = 1）。
2. **重载签名展示口径（建议另立 Issue 核查）**：fixture 中
   `g.greet("ci")` 与 `g.greet()` 两个调用点的行级绑定 `signature`
   字段均报告为 `greet()`；`state`/`decl` 均正确（resolved /
   com.example.Greeter）。该字段口径是否与 T9-B 记录一致、是否为驱动
   报告层问题，本 Issue 合同禁改 src，留待独立 Issue。

## 5. 交付物索引

| 文件 | 位置 |
|---|---|
| 6 步验证器 | `revalidation/linux-jdt-verify/verify_linux_jdt.py` |
| 套件钉扎 POM | `revalidation/linux-jdt-verify/jdt-suite-pom.xml` |
| 签名剥离 | `revalidation/linux-jdt-verify/strip_signatures.py` |
| fixture | `revalidation/linux-jdt-verify/fixture/` |
| Windows golden | `revalidation/linux-jdt-verify/goldens/` |
| CI job | `.github/workflows/ci.yml` → `linux-jdt-verify` |
| 本地基线原始输出 | 运行目录 `out/`（CI 以 artifact 归档） |

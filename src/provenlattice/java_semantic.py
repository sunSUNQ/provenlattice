"""P2-D: optional Eclipse JDT exact-resolution analyzer for Java.

Production form of the P2-B/P5 prototypes. Contract:

- **Opt-in only**: nothing here runs during the default index; there is no
  JVM dependency in the L1 path. The capability row is `semantic_java`
  (query-time, optional runtime jdk+jdt).
- **Fail-closed**: missing JDK / missing JDT classpath / invalid classpath
  contract / non-zero driver exit / timeout / unparseable output all yield
  ``status != "available"`` with an explicit reason. Nothing is written and
  the (post-P2-A) L1 reference statuses are never altered.
- **Recovered bindings are dropped** (T9-B: JDT invents ghost FQNs for
  missing dependencies). Ambiguous JDT results (resolved=null) stay
  ambiguous. No project-internal CALLS edge is fabricated when a reliable
  target mapping does not exist.
- **Freshness**: results carry the P2-C classpath fingerprint and the L1
  CALL_KIND_VERSION; a consumer must treat a mismatch as stale.

CLI: ``provenlattice java-semantic <repo> [--classpath-manifest FILE]``
(query-time command, defect-command precedent; MCP passthrough inherits it
without any frozen-contract change).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .classpath import ClasspathContract, build_classpath
from .resolver import CALL_KIND_VERSION  # freshness anchor (reference semantics)

DRIVER_SOURCE = Path(__file__).parent / "java_semantic_driver" / "P2bDriver.java"
DEFAULT_XMX = "1g"
DEFAULT_TIMEOUT_S = 900


def _find_jdk() -> str | None:
    """Locate a usable JDK (java/javac) without touching the L1 path."""
    override = os.environ.get("PL_JAVA_JDK")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(Path(java_home))
    found = shutil.which("java")
    if found:
        candidates.append(Path(found).parent.parent)  # .../bin/java -> home
    for candidate in candidates:
        javac = candidate / "bin" / ("javac.exe" if os.name == "nt" else "javac")
        java = candidate / "bin" / ("java.exe" if os.name == "nt" else "java")
        if javac.exists() and java.exists():
            return str(candidate)
        if candidate.name.endswith(".exe") or (candidate / "java.exe").exists():
            # `shutil.which` gave .../bin/java directly
            bin_dir = candidate if candidate.name == "bin" else candidate.parent
            if (bin_dir / "javac.exe").exists() or (bin_dir / "javac").exists():
                return str(bin_dir.parent)
    return None


def _jdt_classpath() -> str | None:
    """JDT jar list from PL_JAVA_JDT_CLASSPATH (';'/':'-separated) or None."""
    raw = os.environ.get("PL_JAVA_JDT_CLASSPATH", "").strip()
    return raw or None


@dataclass(slots=True)
class SemanticBinding:
    """One JDT-resolved call site, already filtered (recovered dropped)."""

    file: str
    line: int
    expr: str
    decl: str | None
    state: str  # "resolved" | "ambiguous" | "recovered_filtered"
    signature: str | None = None

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "expr": self.expr,
                "decl": self.decl, "state": self.state, "signature": self.signature}


@dataclass(slots=True)
class SemanticResult:
    status: str  # "available" | "unavailable" | "failed" | "stale"
    reason: str | None = None
    summary: dict = field(default_factory=dict)
    bindings: list[SemanticBinding] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status, "reason": self.reason,
            "summary": self.summary,
            "bindings": [b.to_dict() for b in self.bindings],
            "meta": self.meta,
        }


def availability() -> dict:
    """Report analyzer availability without running anything (fail-closed
    introspection for CLI/capability surfaces)."""
    jdk = _find_jdk()
    jdt = _jdt_classpath()
    return {
        "capability": "semantic_java",
        "jdk_found": jdk is not None,
        "jdk_path": jdk,
        "jdt_classpath_configured": jdt is not None,
        "driver_source": str(DRIVER_SOURCE),
        "status": "available" if (jdk and jdt) else "unavailable",
        "reason": None if (jdk and jdt) else (
            "jdk_not_found" if not jdk else "jdt_classpath_not_configured"),
        "call_kind_version": CALL_KIND_VERSION,
    }


def _ensure_driver_classes(cache_dir: Path, jdk: str, jdt_cp: str) -> Path:
    """Compile the bundled driver once into the cache dir (javac, offline)."""
    marker = cache_dir / "compiled.marker"
    if marker.exists():
        return cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [Path(jdk) / "bin" / ("javac.exe" if os.name == "nt" else "javac"),
         "-cp", jdt_cp, "-d", str(cache_dir), str(DRIVER_SOURCE)],
        capture_output=True, text=True, timeout=300, check=True)
    marker.write_text("ok\n", encoding="utf-8")
    return cache_dir


def run_jdt_analysis(
    repo: str | Path,
    *,
    classpath_manifest: str | Path | None = None,
    xmx: str = DEFAULT_XMX,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    mode: str = "full",
) -> SemanticResult:
    """Run the JDT analyzer once. Never raises for environmental failure."""
    repo = Path(repo).resolve()
    info = availability()
    if info["status"] != "available":
        return SemanticResult(status="unavailable", reason=info["reason"],
                              meta={"availability": info})

    base_dir = repo
    if classpath_manifest is not None:
        roots, deps = load_manifest(classpath_manifest)
        contract = build_classpath(project_roots=roots, dependencies=deps,
                                   base_dir=base_dir)
    else:
        contract = build_classpath()
    if not contract.usable:
        return SemanticResult(
            status="failed",
            reason="classpath_contract_invalid",
            meta={"issues": [i.__dict__ if hasattr(i, "__dict__") else str(i)
                             for i in contract.issues],
                  "classpath_fingerprint": contract.fingerprint})

    jdk = info["jdk_path"]
    jdt_cp = _jdt_classpath()
    try:
        classes = _ensure_driver_classes(_cache_dir(), jdk, jdt_cp)
    except (subprocess.SubprocessError, OSError) as error:
        return SemanticResult(status="failed", reason=f"driver_compile_failed: {error}")

    cp_entries = ";".join([*contract.dependencies, jdt_cp])
    out_file = Path(_cache_dir()) / f"p2d-{abs(hash((str(repo), contract.fingerprint)))}.jsonl"
    cmd = [Path(jdk) / "bin" / ("java.exe" if os.name == "nt" else "java"),
           f"-Xmx{xmx}", "-cp", f"{classes};{jdt_cp}" if os.name == "nt"
           else f"{classes}:{jdt_cp}",
           "P2bDriver", str(repo), mode, str(out_file), cp_entries]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return SemanticResult(status="failed", reason="timeout",
                              meta={"timeout_s": timeout_s,
                                    "classpath_fingerprint": contract.fingerprint})
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-600:]
        reason = "jdt_oom" if "OutOfMemoryError" in tail else "jdt_nonzero_exit"
        return SemanticResult(status="failed", reason=reason,
                              meta={"rc": proc.returncode, "stderr_tail": tail,
                                    "classpath_fingerprint": contract.fingerprint})
    summary = None
    detail_lines = []
    for line in out_file.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("{"):
            continue
        row = json.loads(line)
        if row.get("kind") == "summary":
            summary = row
        elif mode == "full" and "file" in row:
            detail_lines.append(row)
    if summary is None:
        return SemanticResult(status="failed", reason="driver_output_unparseable",
                              meta={"classpath_fingerprint": contract.fingerprint})

    bindings = [
        SemanticBinding(
            file=row["file"], line=row["line"], expr=row["expr"],
            decl=row.get("decl"),
            state="recovered_filtered" if row.get("recovered")
            else ("ambiguous" if not row.get("decl") else "resolved"),
            signature=row.get("signature"),
        )
        for row in detail_lines if row.get("kind") == "call"
    ]
    meta = {
        "backend": "eclipse-jdt",
        "backend_classpath": "PL_JAVA_JDT_CLASSPATH",
        "classpath_fingerprint": contract.fingerprint,
        "classpath_status": contract.status,
        "call_kind_version": CALL_KIND_VERSION,
        "xmx": xmx,
        "recovered_filtered": True,
    }
    return SemanticResult(status="available", summary=summary,
                          bindings=bindings, meta=meta)


def _cache_dir() -> Path:
    base = os.environ.get("PL_JAVA_SEMANTIC_CACHE")
    if base:
        path = Path(base)
    else:
        path = Path(tempfile.gettempdir()) / "provenlattice-java-semantic"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_manifest(manifest: str | Path) -> tuple[list[str], list[str]]:
    from .classpath import load_classpath_file

    return load_classpath_file(manifest)


def merge_with_l1(result: SemanticResult, l1_db: str | Path) -> dict:
    """Audit view: per JDT call site, the (post-P2-A) L1 status side by side.

    Batch implementation (P2-E): ONE bulk SQL query loads every CALLS
    raw-reference row (with resolved-target join) into memory; per-site
    matching is then done in-process. This removes the prototype's per-site
    N+1 queries (hikaricp 3.9k, gson 9k, jgit 60k+ sites) while keeping the
    matching semantics identical to the frozen prototype: a site matches L1
    rows on the same start_line whose raw_name ends with the call-root
    (SQL LIKE '%root' equivalence).

    Merge policy (P2-A/P2-D linked delivery):
    - L1 resolved (exact tiers) stays authoritative for its own row
    - JDT 'resolved' binds the site precisely; L1 ambiguous/unresolved rows
      for the same (file, line, expr-root) are reported as 'recovered_by_jdt'
    - JDT 'ambiguous'/'recovered_filtered' never fabricates a deterministic
      target; conflicts between L1 resolved and JDT resolved-decl are listed
      as 'conflict' (conservative: both kept, nothing overwritten)
    """
    import sqlite3
    from contextlib import closing

    sites: dict[tuple[str, int, str], dict] = {}
    for b in result.bindings:
        root = (b.expr or "").split(".")[-1]
        sites.setdefault((b.file, b.line, root), {"jdt": b, "l1": []})

    # one bulk query for all CALLS rows; in-memory matching replaces N+1
    bulk: dict[int, list[dict]] = {}
    with closing(sqlite3.connect(str(l1_db))) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            "SELECT f.path AS file, r.start_line AS line, r.raw_name, r.status, "
            "r.resolution_strategy, r.confidence, n.qualified_name AS target "
            "FROM raw_references r JOIN nodes n ON r.resolved_symbol_id=n.id "
            "JOIN files f ON r.file_id=f.file_id "
            "WHERE r.reference_type='CALLS'"
        ):
            bulk.setdefault(row["line"], []).append(dict(row))

    merged = []
    for (file, line, root), bucket in sites.items():
        jdt, _ = bucket["jdt"], bucket["l1"]
        # sqlite LIKE is case-insensitive for ASCII by default; the batch
        # matcher must replicate that exactly to stay equivalent to the
        # frozen prototype (P2-E equivalence harness caught this).
        root_lower = root.lower()
        l1rows = [
            r for r in bulk.get(line, [])
            if r["raw_name"].lower().endswith(root_lower)
        ]
        state = "jdt_resolved"
        if jdt.state != "resolved":
            state = f"jdt_{jdt.state}"
        else:
            l1_resolved = [r for r in l1rows if r["status"] == "resolved"]
            if l1_resolved:
                agree = any(
                    (r["target"] or "").split(".")[0] == (jdt.decl or "").split(".")[0]
                    or (jdt.decl or "").startswith((r["target"] or "").split("(")[0])
                    for r in l1_resolved)
                if not agree:
                    state = "conflict_conservative"
                else:
                    state = "l1_and_jdt_agree"
            else:
                state = "recovered_by_jdt"
        merged.append({
            "file": file, "line": line, "expr": root,
            "jdt": jdt.to_dict(), "l1": l1rows, "state": state,
            "provenance": "semantic:jdt-v1",
            "classpath_fingerprint": result.meta.get("classpath_fingerprint"),
        })
    return {"status": result.status, "sites": merged,
            "meta": result.meta,
            "counts": _counts(merged)}


def _counts(sites: list[dict]) -> dict:
    out: dict[str, int] = {}
    for s in sites:
        out[s["state"]] = out.get(s["state"], 0) + 1
    return out

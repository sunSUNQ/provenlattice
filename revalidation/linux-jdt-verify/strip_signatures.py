"""Strip META-INF signing entries from jars in a directory (in place).

The T9-B/P2-B verified JDT suite uses signature-stripped jars: cross-jar
signer conflicts between Eclipse platform jars break JDT resolution
(docs/java-overnight-longrun-v1/t9b/comparison.json). Maven Central jars
are signed, so the verification pipeline strips the same entries before
running the driver.
"""
import sys
import zipfile
from pathlib import Path

SUFFIXES = (".SF", ".RSA", ".DSA", ".EC")


def strip_jar(path: Path) -> int:
    entries = zipfile.ZipFile(path).namelist()
    drop = {n for n in entries
            if n.startswith("META-INF/") and n.upper().endswith(SUFFIXES)}
    if not drop:
        return 0
    with zipfile.ZipFile(path) as source:
        items = [(n, source.read(n)) for n in entries if n not in drop]
    tmp = path.with_suffix(".jar.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in items:
            target.writestr(name, data)
    tmp.replace(path)
    return len(drop)


def main() -> None:
    root = Path(sys.argv[1])
    jars = sorted(root.glob("*.jar"))
    for jar in jars:
        removed = strip_jar(jar)
        print(f"{jar.name}: stripped {removed} signature entries")
    if not jars:
        raise SystemExit(f"no jars found under {root}")


if __name__ == "__main__":
    main()

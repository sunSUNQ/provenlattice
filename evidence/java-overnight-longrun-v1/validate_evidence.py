import json
from pathlib import Path

base = Path("evidence/java-overnight-longrun-v1")
for name in ("preflight.json", "baseline-test-results.json", "p1-final-review.json",
             "stage-status.json"):
    p = base / name
    raw = p.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
        p.write_bytes(raw)
        fixed = " (BOM stripped)"
    else:
        fixed = ""
    json.loads(raw.decode("utf-8"))
    print(f"{name}: valid{fixed}")
# checkpoints: strip BOM from first line if present, validate each line
cp = base / "checkpoints.jsonl"
raw = cp.read_bytes()
if raw.startswith(b"\xef\xbb\xbf"):
    raw = raw[3:]
    cp.write_bytes(raw)
count = 0
for line in raw.decode("utf-8").splitlines():
    if line.strip():
        json.loads(line)
        count += 1
print(f"checkpoints.jsonl: {count} valid entries")

#!/usr/bin/env python3
"""Apply the release severity gate to a redacted live-run record."""
import json
import sys
from pathlib import Path

records = [json.loads(Path(value).read_text(encoding="utf-8")) for value in sys.argv[1:]]
blocked = []
for record in records:
    if record.get("result_version") != 1 or not isinstance(record.get("metadata"), dict):
        raise SystemExit("invalid live result")
    for finding in record.get("findings", []):
        if not finding.get("resolved") and finding.get("severity") in ("Critical", "Important"):
            blocked.append(finding)
if blocked:
    print(f"release blocked: {len(blocked)} unresolved Critical/Important finding(s)")
    raise SystemExit(1)
print("release gate passed")

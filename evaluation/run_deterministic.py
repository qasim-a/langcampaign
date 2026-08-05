#!/usr/bin/env python3
"""Validate deterministic release-scenario fixtures without a model call."""
import json
from pathlib import Path

root = Path(__file__).with_name("scenarios")
paths = sorted(root.glob("*.json"))
required = {"scenario_version", "id", "learner_request", "fresh_profile", "expected_operations", "required_properties", "prohibited_properties"}
if len(paths) != 10:
    raise SystemExit("expected exactly 10 scenarios")
ids = set()
for path in paths:
    data = json.loads(path.read_text(encoding="utf-8"))
    if set(data) != required or data["scenario_version"] != 1 or data["fresh_profile"] is not True:
        raise SystemExit(f"invalid scenario: {path.name}")
    if data["id"] in ids or not all(data[key] for key in ("expected_operations", "required_properties", "prohibited_properties")):
        raise SystemExit(f"invalid scenario: {path.name}")
    ids.add(data["id"])
print("10 deterministic scenarios valid")

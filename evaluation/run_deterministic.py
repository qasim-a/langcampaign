#!/usr/bin/env python3
"""Run fixed adapter traces from fresh profiles without a model call."""
from __future__ import annotations

import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from langcampaign.profile import load_or_create_profile
from langcampaign.protocol import decode_request, dispatch
from langcampaign.receipts import execute_idempotent
from tests.fixtures import mission_content_payload, setup_payload


def _request(operation, input_data, scenario_id, sequence, mutation=False):
    operation_id = str(uuid5(NAMESPACE_URL, f"{scenario_id}:{sequence}:{operation}")) if mutation else None
    raw = json.dumps({"protocol_version": 1, "operation": operation, "operation_id": operation_id, "input": input_data}, separators=(",", ":")).encode()
    return decode_request(raw)


def _execute(root, profile, request):
    action = lambda: dispatch(request, root / "learners", profile.learner_id)
    if request.mutation:
        return execute_idempotent(root, request.operation_id, request.operation.value, request.input, action)
    return action()


def _setup_input(campaign_id):
    payload = deepcopy(setup_payload())
    payload.pop("learner_id", None)
    payload["campaign"]["id"] = campaign_id
    payload["first_content"] = mission_content_payload()
    return payload


def _run_trace(scenario, root, profile):
    campaign_id = f"campaign-{scenario['id']}"
    setup = _setup_input(campaign_id)
    operations = scenario["expected_operations"]
    revision = 0
    trace = []
    if "setup" not in operations and scenario["id"] != "invalid-content":
        seeded = _request("setup", setup, scenario["id"], "seed", True)
        _execute(root, profile, seeded)
    for index, operation in enumerate(operations):
        mutation = operation not in {"check-install", "status", "list-campaigns", "show-roadmap", "validate-content", "export"}
        if operation == "check-install" or operation == "list-campaigns":
            input_data = {}
        elif operation == "status":
            input_data = {"campaign_id": campaign_id} if (root / "learners" / profile.learner_id / campaign_id).exists() else {}
        elif operation == "setup":
            input_data = setup
        elif operation == "validate-content":
            candidate = 1 if sum(item["operation"] == "validate-content" for item in trace) == 0 else 2
            content = mission_content_payload(candidate)
            if scenario["id"] == "invalid-content":
                content["rubric"][1]["weight"] = 40
            input_data = {"content": content}
        elif operation == "adjust-difficulty":
            input_data = {"campaign_id": campaign_id, "mission_id": "delayed-arrival", "attempt_number": 1, "expected_revision": revision, "adjustment": "prerequisite_support" if scenario["id"] == "too-hard" else "harder"}
        elif operation == "return-to-practice":
            for advance_index in range(2):
                advance = _request("advance-mission", {"campaign_id": campaign_id, "mission_id": "delayed-arrival", "attempt_number": 1, "expected_revision": revision}, scenario["id"], f"pre-{advance_index}", True)
                revision = _execute(root, profile, advance)["data"]["revision"]
            input_data = {"campaign_id": campaign_id, "mission_id": "delayed-arrival", "attempt_number": 1, "expected_revision": revision}
        elif operation == "submit-assessment":
            for advance_index in range(2):
                advance = _request("advance-mission", {"campaign_id": campaign_id, "mission_id": "delayed-arrival", "attempt_number": 1, "expected_revision": revision}, scenario["id"], f"pre-{advance_index}", True)
                revision = _execute(root, profile, advance)["data"]["revision"]
            input_data = {"campaign_id": campaign_id, "mission_id": "delayed-arrival", "attempt_number": 1, "expected_revision": revision, "criterion_scores": [{"criterion_id": "delay", "score": 60}, {"criterion_id": "time", "score": 60}], "independent": True, "modality": "text", "result_statement": "Partial independent performance"}
        elif operation == "transition":
            target = _setup_input(f"new-{campaign_id}")
            input_data = {**target, "source_campaign_id": campaign_id, "source_expected_revision": revision, "evidence_transfers": []}
            campaign_id = f"new-{campaign_id}"
        elif operation == "resume":
            original = f"campaign-{scenario['id']}"
            input_data = {"campaign_id": original, "expected_revision": 0}
            campaign_id = original
        else:
            raise SystemExit(f"scenario operation not supported: {operation}")
        request = _request(operation, input_data, scenario["id"], index, mutation)
        response = _execute(root, profile, request)
        if not response["success"]:
            raise SystemExit(f"scenario operation failed: {scenario['id']}:{operation}")
        revision = response.get("data", {}).get("revision", revision)
        if set(response) != {"protocol_version", "operation_id", "success", "data"}:
            raise SystemExit(f"invalid response envelope: {scenario['id']}:{operation}")
        trace.append({"operation": operation, "success": True, "data": response["data"]})
    if [item["operation"] for item in trace] != operations:
        raise SystemExit(f"trace mismatch: {scenario['id']}")
    by_operation = {item["operation"]: item["data"] for item in trace}
    scenario_id = scenario["id"]
    if scenario_id == "partial-performance":
        result = by_operation["submit-assessment"]["latest_result"]
        if result["score"] != 60 or result["outcome"] == "pass":
            raise SystemExit("partial-performance did not preserve partial credit")
    elif scenario_id == "too-hard":
        if by_operation["adjust-difficulty"]["session"]["adjustment"] != "prerequisite_support":
            raise SystemExit("too-hard did not select prerequisite support")
    elif scenario_id == "too-easy":
        if by_operation["adjust-difficulty"]["session"]["adjustment"] != "harder":
            raise SystemExit("too-easy did not select harder content")
    elif scenario_id == "accidental-help":
        if by_operation["return-to-practice"]["latest_result"] is not None:
            raise SystemExit("accidental-help recorded assessment evidence")
    elif scenario_id == "invalid-content":
        validations = [item["data"] for item in trace if item["operation"] == "validate-content"]
        if [item["correction_allowed"] for item in validations] != [True, False]:
            raise SystemExit("invalid-content correction bound was not enforced")
    elif scenario_id == "fresh-resume":
        status = by_operation["status"]
        if status["session"] is None or "content" not in status["session"]:
            raise SystemExit("fresh-resume did not reconstruct persisted content")


paths = sorted((ROOT / "evaluation/scenarios").glob("*.json"))
if len(paths) != 10:
    raise SystemExit("expected exactly 10 scenarios")
for path in paths:
    scenario = json.loads(path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        profile = load_or_create_profile(root, token_hex=lambda _: "ab" * 16)
        _run_trace(scenario, root, profile)
print("10 deterministic scenarios valid")

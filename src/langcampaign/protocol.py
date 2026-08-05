"""Versioned platform-neutral JSON protocol for LangCampaign adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

from .cli import run_command


PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 1024 * 1024
MAX_STRING_LENGTH = 20_000
MAX_COLLECTION_ITEMS = 1_000


class Operation(StrEnum):
    CHECK_INSTALL = "check-install"
    SETUP = "setup"
    STATUS = "status"
    LIST_CAMPAIGNS = "list-campaigns"
    SHOW_ROADMAP = "show-roadmap"
    VALIDATE_CONTENT = "validate-content"
    TRANSITION = "transition"
    RESUME = "resume"
    PAUSE = "pause"
    COMPLETE = "complete"
    START_MISSION = "start-mission"
    ADVANCE_MISSION = "advance-mission"
    ADJUST_DIFFICULTY = "adjust-difficulty"
    RETURN_TO_PRACTICE = "return-to-practice"
    SUBMIT_ASSESSMENT = "submit-assessment"
    EXPORT = "export"
    RESET = "reset"


class ProtocolErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    UNSUPPORTED_PROTOCOL = "UNSUPPORTED_PROTOCOL"
    UNKNOWN_OPERATION = "UNKNOWN_OPERATION"
    UNSUPPORTED_ENVIRONMENT = "UNSUPPORTED_ENVIRONMENT"
    NO_CAMPAIGN = "NO_CAMPAIGN"
    AMBIGUOUS_CAMPAIGN = "AMBIGUOUS_CAMPAIGN"
    INVALID_CONTENT = "INVALID_CONTENT"
    STALE_REVISION = "STALE_REVISION"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    STATE_CONFLICT = "STATE_CONFLICT"
    CORRUPT_STATE = "CORRUPT_STATE"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    UNSAFE_PATH = "UNSAFE_PATH"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ProtocolError(ValueError):
    def __init__(self, code: ProtocolErrorCode, message: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True)
class ProtocolRequest:
    protocol_version: int
    operation: Operation
    operation_id: str | None
    input: dict[str, Any]

    @property
    def mutation(self) -> bool:
        return self.operation not in _READS


_READS = {
    Operation.CHECK_INSTALL,
    Operation.STATUS,
    Operation.LIST_CAMPAIGNS,
    Operation.SHOW_ROADMAP,
    Operation.VALIDATE_CONTENT,
    Operation.EXPORT,
}

_INPUT_FIELDS = {
    Operation.CHECK_INSTALL: (set(), set()),
    Operation.SETUP: ({"campaign", "mission_plans", "roadmap", "prior_knowledge", "first_content"}, {"campaign", "mission_plans", "roadmap", "prior_knowledge", "first_content"}),
    Operation.STATUS: ({"campaign_id"}, set()),
    Operation.LIST_CAMPAIGNS: (set(), set()),
    Operation.SHOW_ROADMAP: ({"campaign_id"}, {"campaign_id"}),
    Operation.VALIDATE_CONTENT: ({"content"}, {"content"}),
    Operation.TRANSITION: ({"source_campaign_id", "source_expected_revision", "campaign", "mission_plans", "roadmap", "prior_knowledge", "evidence_transfers", "first_content"}, {"source_campaign_id", "source_expected_revision", "campaign", "mission_plans", "roadmap", "prior_knowledge", "evidence_transfers", "first_content"}),
    Operation.RESUME: ({"campaign_id", "expected_revision"}, {"campaign_id", "expected_revision"}),
    Operation.PAUSE: ({"campaign_id", "expected_revision"}, {"campaign_id", "expected_revision"}),
    Operation.COMPLETE: ({"campaign_id", "expected_revision"}, {"campaign_id", "expected_revision"}),
    Operation.START_MISSION: ({"campaign_id", "mission_id", "expected_revision", "content"}, {"campaign_id", "mission_id", "expected_revision", "content"}),
    Operation.ADVANCE_MISSION: ({"campaign_id", "mission_id", "attempt_number", "expected_revision", "replacement_content"}, {"campaign_id", "mission_id", "attempt_number", "expected_revision"}),
    Operation.ADJUST_DIFFICULTY: ({"campaign_id", "mission_id", "attempt_number", "expected_revision", "adjustment"}, {"campaign_id", "mission_id", "attempt_number", "expected_revision", "adjustment"}),
    Operation.RETURN_TO_PRACTICE: ({"campaign_id", "mission_id", "attempt_number", "expected_revision"}, {"campaign_id", "mission_id", "attempt_number", "expected_revision"}),
    Operation.SUBMIT_ASSESSMENT: ({"campaign_id", "mission_id", "attempt_number", "expected_revision", "criterion_scores", "independent", "modality", "result_statement"}, {"campaign_id", "mission_id", "attempt_number", "expected_revision", "criterion_scores", "independent", "modality", "result_statement"}),
    Operation.EXPORT: ({"destination_directory"}, {"destination_directory"}),
    Operation.RESET: ({"confirmation"}, {"confirmation"}),
}


def _validate_operation_input(operation: Operation, input_data: dict) -> None:
    def bounded(value, depth=0):
        if depth > 12:
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "input nesting is too deep")
        if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "input string is too long")
        if isinstance(value, (list, dict)) and len(value) > MAX_COLLECTION_ITEMS:
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "input collection is too large")
        if isinstance(value, list):
            for item in value: bounded(item, depth + 1)
        elif isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str) or not key or len(key) > 128:
                    raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "input field name is invalid")
                bounded(item, depth + 1)
    bounded(input_data)
    allowed, required = _INPUT_FIELDS[operation]
    if not required <= set(input_data) or not set(input_data) <= allowed:
        raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "operation input fields are invalid")
    for name in ("campaign_id", "source_campaign_id", "mission_id"):
        if name in input_data and (not isinstance(input_data[name], str) or not input_data[name].strip()):
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, f"{name} must be non-empty")
    for name in ("expected_revision", "source_expected_revision", "attempt_number"):
        if name in input_data and (type(input_data[name]) is not int or input_data[name] < (1 if name == "attempt_number" else 0)):
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, f"{name} is invalid")
    if operation in (Operation.SETUP, Operation.TRANSITION):
        campaign = input_data.get("campaign")
        if not isinstance(campaign, dict) or not isinstance(campaign.get("id"), str) or not campaign["id"].strip():
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "campaign.id is required for idempotent setup")
        campaign_allowed = {"id", "goal", "target_language", "target_date", "campaign_type", "curriculum_scope", "coaching_style", "missions"}
        if not set(campaign) <= campaign_allowed or not {"id", "goal", "target_language", "missions"} <= set(campaign):
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "campaign fields are invalid")
        if not isinstance(campaign["missions"], list) or not campaign["missions"]:
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "campaign missions are invalid")
        for mission in campaign["missions"]:
            if not isinstance(mission, dict) or not set(mission) <= {"id", "title", "weight"} or not {"id", "title"} <= set(mission):
                raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "campaign mission fields are invalid")
        plans = input_data.get("mission_plans")
        plan_fields = {"id", "title", "capability", "rationale", "priority", "prerequisite_ids", "target_vocabulary", "target_structures", "register_notes", "cultural_context", "common_failure_patterns", "practice", "assessment"}
        if not isinstance(plans, list) or not plans or any(not isinstance(plan, dict) or set(plan) != plan_fields for plan in plans):
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "mission plan fields are invalid")
        for plan in plans:
            if (
                not isinstance(plan["practice"], list) or not plan["practice"]
                or any(not isinstance(item, dict) or set(item) != {"kind", "instructions"} for item in plan["practice"])
                or not isinstance(plan["assessment"], dict)
                or set(plan["assessment"]) != {"prompt", "success_criteria"}
            ):
                raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "mission plan nested fields are invalid")
        roadmap = input_data.get("roadmap")
        if not isinstance(roadmap, dict) or set(roadmap) != {"phases", "active_phase_id", "assumptions"}:
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "roadmap fields are invalid")
        phase_fields = {"id", "title", "capability_summary", "mission_ids", "planned_review_after", "planned_simulation_after"}
        if not isinstance(roadmap["phases"], list) or not roadmap["phases"] or any(not isinstance(phase, dict) or set(phase) != phase_fields for phase in roadmap["phases"]):
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "roadmap phases are invalid")
    if operation in {Operation.SETUP, Operation.TRANSITION, Operation.VALIDATE_CONTENT, Operation.START_MISSION} or (operation is Operation.ADVANCE_MISSION and "replacement_content" in input_data):
        content = input_data.get("first_content", input_data.get("content", input_data.get("replacement_content")))
        content_fields = {"generation_id", "candidate_number", "capability", "scenario", "teaching_objectives", "essential_language", "guided_prompts", "assessment_prompt", "rubric"}
        if not isinstance(content, dict) or set(content) != content_fields:
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "content fields are invalid")
        if any(not isinstance(item, dict) or set(item) != {"id", "description", "weight"} for item in content["rubric"]):
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "content rubric fields are invalid")
        for name in ("teaching_objectives", "essential_language", "guided_prompts"):
            if not isinstance(content[name], list) or not content[name] or any(not isinstance(item, str) or not item for item in content[name]):
                raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, f"content {name} is invalid")
    if operation is Operation.SUBMIT_ASSESSMENT:
        scores = input_data.get("criterion_scores")
        if not isinstance(scores, list) or not scores or any(not isinstance(item, dict) or set(item) != {"criterion_id", "score"} for item in scores):
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "criterion scores are invalid")
        if input_data.get("independent") is not True:
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "independent must be true")
        if any(type(item["score"]) is not int or not 0 <= item["score"] <= 100 for item in scores):
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "criterion score must be an integer from 0 to 100")


def decode_request(raw: bytes) -> ProtocolRequest:
    if len(raw) > MAX_REQUEST_BYTES:
        raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "request exceeds 1 MiB")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError(
            ProtocolErrorCode.INVALID_REQUEST,
            "request must be one UTF-8 JSON object",
        ) from error
    if not isinstance(data, dict) or set(data) != {
        "protocol_version", "operation", "operation_id", "input"
    }:
        raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "request fields are invalid")
    if data["protocol_version"] != PROTOCOL_VERSION:
        raise ProtocolError(ProtocolErrorCode.UNSUPPORTED_PROTOCOL, "unsupported protocol version")
    try:
        operation = Operation(data["operation"])
    except (TypeError, ValueError) as error:
        raise ProtocolError(ProtocolErrorCode.UNKNOWN_OPERATION, "unknown operation") from error
    operation_id = data["operation_id"]
    if operation_id is not None:
        try:
            UUID(operation_id)
        except (AttributeError, TypeError, ValueError) as error:
            raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "operation_id must be a UUID or null") from error
    if operation not in _READS and operation_id is None:
        raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "operation_id is required for mutations")
    if not isinstance(data["input"], dict):
        raise ProtocolError(ProtocolErrorCode.INVALID_REQUEST, "input must be a JSON object")
    _validate_operation_input(operation, data["input"])
    return ProtocolRequest(PROTOCOL_VERSION, operation, operation_id, data["input"])


def encode_response(response: dict[str, Any]) -> bytes:
    return (json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def failure_response(error: ProtocolError, operation_id: str | None = None) -> dict:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "operation_id": operation_id,
        "success": False,
        "error": {
            "code": error.code.value,
            "message": str(error),
            "retryable": error.retryable,
        },
    }


_COMMANDS = {
    Operation.SETUP: "setup",
    Operation.LIST_CAMPAIGNS: "list-campaigns",
    Operation.SHOW_ROADMAP: "show-roadmap",
    Operation.VALIDATE_CONTENT: "validate-mission-content",
    Operation.TRANSITION: "transition-campaign",
    Operation.RESUME: "resume-campaign",
    Operation.PAUSE: "pause-campaign",
    Operation.COMPLETE: "complete-campaign",
    Operation.START_MISSION: "start-mission",
    Operation.ADVANCE_MISSION: "advance-mission",
    Operation.ADJUST_DIFFICULTY: "adjust-difficulty",
    Operation.RETURN_TO_PRACTICE: "return-to-practice",
    Operation.SUBMIT_ASSESSMENT: "submit-assessment",
}

_SNAPSHOT_FIELDS = {"revision", "session", "progress", "next_action", "rendered_progress", "latest_result"}
_SUCCESS_FIELDS = {
    Operation.SETUP: {"learner_id", "campaign_id", "next_priorities", "first_mission_id"},
    Operation.STATUS: _SNAPSHOT_FIELDS | {"campaigns"},
    Operation.LIST_CAMPAIGNS: {"campaigns"},
    Operation.SHOW_ROADMAP: {"summary"},
    Operation.VALIDATE_CONTENT: {"valid", "content", "correction_allowed", "issues"},
    Operation.TRANSITION: {"active_campaign_id"},
    Operation.RESUME: {"active_campaign_id"},
    Operation.PAUSE: {"paused_campaign_id", "revision"},
    Operation.COMPLETE: {"completed_campaign_id"},
    Operation.START_MISSION: _SNAPSHOT_FIELDS,
    Operation.ADVANCE_MISSION: _SNAPSHOT_FIELDS,
    Operation.ADJUST_DIFFICULTY: _SNAPSHOT_FIELDS,
    Operation.RETURN_TO_PRACTICE: _SNAPSHOT_FIELDS,
    Operation.SUBMIT_ASSESSMENT: _SNAPSHOT_FIELDS,
}

_SUCCESS_REQUIRED = {
    Operation.SETUP: _SUCCESS_FIELDS[Operation.SETUP],
    Operation.STATUS: set(),
    Operation.LIST_CAMPAIGNS: {"campaigns"},
    Operation.SHOW_ROADMAP: {"summary"},
    Operation.VALIDATE_CONTENT: {"valid", "content", "correction_allowed"},
    Operation.TRANSITION: {"active_campaign_id"},
    Operation.RESUME: {"active_campaign_id"},
    Operation.PAUSE: {"paused_campaign_id", "revision"},
    Operation.COMPLETE: {"completed_campaign_id"},
    Operation.START_MISSION: _SNAPSHOT_FIELDS,
    Operation.ADVANCE_MISSION: _SNAPSHOT_FIELDS,
    Operation.ADJUST_DIFFICULTY: _SNAPSHOT_FIELDS,
    Operation.RETURN_TO_PRACTICE: _SNAPSHOT_FIELDS,
    Operation.SUBMIT_ASSESSMENT: _SNAPSHOT_FIELDS,
}


def _validate_success_data(operation: Operation, data: dict) -> None:
    fields = set(data) if isinstance(data, dict) else set()
    required = _SUCCESS_REQUIRED[operation]
    if operation is Operation.STATUS:
        required = {"campaigns"} if "campaigns" in fields else _SNAPSHOT_FIELDS
    if not isinstance(data, dict) or not required <= fields <= _SUCCESS_FIELDS[operation]:
        raise ProtocolError(ProtocolErrorCode.INTERNAL_ERROR, "engine returned an invalid success payload")
    if "campaigns" in data and not isinstance(data["campaigns"], list):
        raise ProtocolError(ProtocolErrorCode.INTERNAL_ERROR, "engine returned invalid campaigns")
    if _SNAPSHOT_FIELDS <= fields:
        progress = data["progress"]
        if (
            type(data["revision"]) is not int
            or not isinstance(progress, dict) or set(progress) != {"percent", "bar"}
            or type(progress["percent"]) is not int or not 0 <= progress["percent"] <= 100
            or not isinstance(progress["bar"], str)
            or data["rendered_progress"] is not None and not isinstance(data["rendered_progress"], str)
            or data["session"] is not None and not isinstance(data["session"], dict)
            or data["next_action"] is not None and not isinstance(data["next_action"], dict)
            or data["latest_result"] is not None and not isinstance(data["latest_result"], dict)
        ):
            raise ProtocolError(ProtocolErrorCode.INTERNAL_ERROR, "engine returned an invalid runtime snapshot")
    if operation is Operation.VALIDATE_CONTENT:
        if type(data["valid"]) is not bool or type(data["correction_allowed"]) is not bool or not isinstance(data["content"], dict):
            raise ProtocolError(ProtocolErrorCode.INTERNAL_ERROR, "engine returned invalid content validation")
        if "issues" in data and not isinstance(data["issues"], list):
            raise ProtocolError(ProtocolErrorCode.INTERNAL_ERROR, "engine returned invalid content issues")


def dispatch(request: ProtocolRequest, learners_root: Path, learner_id: str) -> dict:
    if request.operation is Operation.CHECK_INSTALL:
        return {
            "protocol_version": 1,
            "operation_id": request.operation_id,
            "success": True,
            "data": {
                "python_compatible": True,
                "plugin_version": "0.1.0",
                "profile_ready": True,
            },
        }
    if request.operation is Operation.EXPORT:
        from .data_management import DataManagementError, export_profile
        try:
            result = export_profile(Path(learners_root).parent, Path(request.input.get("destination_directory", "")))
        except DataManagementError as error:
            raise ProtocolError(ProtocolErrorCode.UNSAFE_PATH, str(error)) from error
        return {"protocol_version": 1, "operation_id": request.operation_id, "success": True, "data": {"archive_path": str(result.archive_path), "manifest": result.manifest}}
    if request.operation is Operation.RESET:
        from .data_management import DataManagementError, reset_profile
        try:
            result = reset_profile(
                Path(learners_root).parent,
                request.input.get("confirmation"),
                operation_id=request.operation_id,
                lock=False,
            )
        except DataManagementError as error:
            raise ProtocolError(ProtocolErrorCode.STATE_CONFLICT, str(error)) from error
        return {"protocol_version": 1, "operation_id": request.operation_id, "success": True, "data": {"learner_id": result.profile.learner_id, "backup_path": str(result.backup_path), "recovery_path": str(result.recovery_path)}}
    payload = dict(request.input)
    if request.operation is Operation.STATUS:
        command = "mission-status" if "campaign_id" in payload else "list-campaign-status"
    else:
        command = _COMMANDS.get(request.operation)
    if command is None:
        raise ProtocolError(ProtocolErrorCode.UNKNOWN_OPERATION, "operation is not dispatchable")
    payload["learner_id"] = learner_id
    if request.mutation:
        from .data_management import DataManagementError, UnsupportedSchemaError, prepare_write
        try:
            prepare_write(
                Path(learners_root).parent,
                learner_id,
                request.operation_id,
                lock=False,
            )
        except UnsupportedSchemaError as error:
            raise ProtocolError(ProtocolErrorCode.UNSUPPORTED_SCHEMA, str(error)) from error
        except DataManagementError as error:
            raise ProtocolError(ProtocolErrorCode.PERSISTENCE_FAILURE, str(error), retryable=True) from error
    result = run_command(command, payload, learners_root)
    if not result.success:
        raw = result.error
        message = raw.get("message", raw.get("code", "request failed")) if isinstance(raw, dict) else str(raw)
        code = ProtocolErrorCode.INVALID_REQUEST
        if isinstance(raw, dict):
            code = {
                "invalid_content": ProtocolErrorCode.INVALID_CONTENT,
                "revision_conflict": ProtocolErrorCode.STALE_REVISION,
                "persistence_failed": ProtocolErrorCode.PERSISTENCE_FAILURE,
                "campaign_not_found": ProtocolErrorCode.NO_CAMPAIGN,
            }.get(raw.get("code"), ProtocolErrorCode.STATE_CONFLICT)
        elif "no active" in message or "does not exist" in message:
            code = ProtocolErrorCode.NO_CAMPAIGN
        elif "ambiguous" in message:
            code = ProtocolErrorCode.AMBIGUOUS_CAMPAIGN
        raise ProtocolError(code, message, retryable=code in {ProtocolErrorCode.STALE_REVISION, ProtocolErrorCode.PERSISTENCE_FAILURE})
    data = result.data or {}
    _validate_success_data(request.operation, data)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "operation_id": request.operation_id,
        "success": True,
        "data": data,
    }

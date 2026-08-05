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


def dispatch(request: ProtocolRequest, learners_root: Path, learner_id: str) -> dict:
    if request.operation in (Operation.EXPORT, Operation.RESET):
        raise ProtocolError(ProtocolErrorCode.UNKNOWN_OPERATION, "operation is not implemented yet")
    payload = dict(request.input)
    if request.operation is Operation.STATUS:
        command = "mission-status" if "campaign_id" in payload else "list-campaign-status"
    else:
        command = _COMMANDS.get(request.operation)
    if command is None:
        raise ProtocolError(ProtocolErrorCode.UNKNOWN_OPERATION, "operation is not dispatchable")
    payload["learner_id"] = learner_id
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
    return {
        "protocol_version": PROTOCOL_VERSION,
        "operation_id": request.operation_id,
        "success": True,
        "data": result.data or {},
    }

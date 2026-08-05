"""Persistent idempotency receipts for adapter mutations."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .profile import profile_lock
from .protocol import ProtocolError, ProtocolErrorCode


RECEIPT_VERSION = 1
MAX_RECEIPTS = 256


@dataclass(frozen=True)
class OperationReceipt:
    operation_id: str
    operation: str
    input_sha256: str
    response: dict[str, Any]


def canonical_input_digest(operation: str, input_data: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"operation": operation, "input": input_data},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _path(root: Path) -> Path:
    return Path(root) / "receipts.json"


def _load_unlocked(root: Path) -> list[dict[str, Any]]:
    path = _path(root)
    if path.is_symlink():
        raise ProtocolError(ProtocolErrorCode.UNSAFE_PATH, "receipt ledger must not be a symlink")
    if not path.exists():
        return []
    if not path.is_file():
        raise ProtocolError(ProtocolErrorCode.UNSAFE_PATH, "receipt ledger is not a regular file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"receipt_version", "completed"}:
            raise ValueError
        if data["receipt_version"] != RECEIPT_VERSION or not isinstance(data["completed"], list):
            raise ValueError
        for item in data["completed"]:
            if not isinstance(item, dict) or set(item) != {
                "operation_id", "operation", "input_sha256", "response"
            }:
                raise ValueError
        return data["completed"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ProtocolError(ProtocolErrorCode.CORRUPT_STATE, "receipt ledger is invalid") from error


def _save_unlocked(root: Path, completed: list[dict[str, Any]]) -> None:
    root = Path(root)
    path = _path(root)
    descriptor, temporary = tempfile.mkstemp(prefix=".receipts.", suffix=".tmp", dir=root)
    try:
        os.fchmod(descriptor, 0o600)
        payload = json.dumps(
            {"receipt_version": RECEIPT_VERSION, "completed": completed},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def replay_or_conflict(
    root: Path,
    operation_id: str,
    operation: str,
    input_data: dict[str, Any],
) -> dict[str, Any] | None:
    root = Path(root)
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    digest = canonical_input_digest(operation, input_data)
    with profile_lock(root):
        return _replay_unlocked(root, operation_id, operation, digest)


def _replay_unlocked(root, operation_id, operation, digest):
    for item in _load_unlocked(root):
        if item["operation_id"] != operation_id:
            continue
        if item["operation"] != operation or item["input_sha256"] != digest:
            raise ProtocolError(
                ProtocolErrorCode.IDEMPOTENCY_CONFLICT,
                "operation_id was already used with different input",
            )
        return item["response"]
    return None


def record_receipt(
    root: Path,
    operation_id: str,
    operation: str,
    input_data: dict[str, Any],
    response: dict[str, Any],
) -> None:
    root = Path(root)
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    digest = canonical_input_digest(operation, input_data)
    with profile_lock(root):
        _record_unlocked(root, operation_id, operation, digest, response)


def _record_unlocked(root, operation_id, operation, digest, response):
    completed = _load_unlocked(root)
    for item in completed:
        if item["operation_id"] == operation_id:
            if item["operation"] != operation or item["input_sha256"] != digest:
                raise ProtocolError(
                    ProtocolErrorCode.IDEMPOTENCY_CONFLICT,
                    "operation_id was already used with different input",
                )
            return
    completed.append({
            "operation_id": operation_id,
            "operation": operation,
            "input_sha256": digest,
            "response": response,
    })
    _save_unlocked(root, completed[-MAX_RECEIPTS:])


def execute_idempotent(
    root: Path,
    operation_id: str,
    operation: str,
    input_data: dict[str, Any],
    action: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    root = Path(root)
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    digest = canonical_input_digest(operation, input_data)
    with profile_lock(root):
        replay = _replay_unlocked(root, operation_id, operation, digest)
        if replay is not None:
            return replay
        response = action()
        _record_unlocked(root, operation_id, operation, digest, response)
        return response

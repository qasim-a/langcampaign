from uuid import uuid4

import pytest

from langcampaign.protocol import ProtocolError, ProtocolErrorCode
from langcampaign.receipts import (
    canonical_input_digest,
    execute_idempotent,
    record_receipt,
    replay_or_conflict,
)


def test_receipt_replays_identical_operation_after_fresh_load(tmp_path):
    operation_id = str(uuid4())
    input_data = {"campaign_id": "campaign-a", "expected_revision": 3}
    response = {
        "protocol_version": 1,
        "operation_id": operation_id,
        "success": True,
        "data": {"revision": 4},
    }

    record_receipt(tmp_path, operation_id, "pause", input_data, response)

    assert replay_or_conflict(tmp_path, operation_id, "pause", input_data) == response


def test_receipt_rejects_reused_id_with_different_semantic_input(tmp_path):
    operation_id = str(uuid4())
    record_receipt(tmp_path, operation_id, "pause", {"expected_revision": 3}, {"ok": True})

    with pytest.raises(ProtocolError) as raised:
        replay_or_conflict(tmp_path, operation_id, "pause", {"expected_revision": 4})

    assert raised.value.code is ProtocolErrorCode.IDEMPOTENCY_CONFLICT


def test_receipt_digest_is_canonical_and_ledger_is_bounded(tmp_path):
    assert canonical_input_digest("pause", {"b": 2, "a": 1}) == canonical_input_digest(
        "pause", {"a": 1, "b": 2}
    )
    ids = [str(uuid4()) for _ in range(257)]
    for index, operation_id in enumerate(ids):
        record_receipt(tmp_path, operation_id, "pause", {"index": index}, {"index": index})

    assert replay_or_conflict(tmp_path, ids[0], "pause", {"index": 0}) is None
    assert replay_or_conflict(tmp_path, ids[-1], "pause", {"index": 256}) == {"index": 256}


def test_receipt_rejects_symlinked_or_corrupt_ledger(tmp_path):
    target = tmp_path / "target"
    target.write_text("{}")
    (tmp_path / "receipts.json").symlink_to(target)
    with pytest.raises(ProtocolError) as linked:
        replay_or_conflict(tmp_path, str(uuid4()), "pause", {})
    assert linked.value.code is ProtocolErrorCode.UNSAFE_PATH


def test_execute_idempotent_runs_mutation_once_and_replays_response(tmp_path):
    operation_id = str(uuid4())
    calls = []

    def action():
        calls.append("called")
        return {"success": True, "data": {"revision": 1}}

    first = execute_idempotent(tmp_path, operation_id, "pause", {"x": 1}, action)
    second = execute_idempotent(tmp_path, operation_id, "pause", {"x": 1}, action)

    assert first == second
    assert calls == ["called"]


def test_execute_idempotent_does_not_receipt_failed_mutation(tmp_path):
    operation_id = str(uuid4())

    with pytest.raises(RuntimeError):
        execute_idempotent(
            tmp_path,
            operation_id,
            "pause",
            {},
            lambda: (_ for _ in ()).throw(RuntimeError("failed")),
        )

    assert replay_or_conflict(tmp_path, operation_id, "pause", {}) is None

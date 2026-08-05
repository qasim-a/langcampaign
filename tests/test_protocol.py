import json
from dataclasses import replace
from uuid import UUID

import pytest

from langcampaign.protocol import (
    Operation,
    ProtocolError,
    ProtocolErrorCode,
    ProtocolRequest,
    decode_request,
    dispatch,
    encode_response,
)


SCHEMA_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1] / "schemas"


def test_protocol_decodes_exact_versioned_read_request():
    request = decode_request(
        b'{"protocol_version":1,"operation":"list-campaigns","operation_id":null,"input":{}}'
    )

    assert request == ProtocolRequest(1, Operation.LIST_CAMPAIGNS, None, {})


def test_protocol_requires_uuid_for_mutation_and_rejects_unknown_fields():
    with pytest.raises(ProtocolError) as missing:
        decode_request(
            b'{"protocol_version":1,"operation":"pause","operation_id":null,"input":{}}'
        )
    assert missing.value.code is ProtocolErrorCode.INVALID_REQUEST

    with pytest.raises(ProtocolError) as extra:
        decode_request(
            b'{"protocol_version":1,"operation":"status","operation_id":null,"input":{},"extra":1}'
        )
    assert extra.value.code is ProtocolErrorCode.INVALID_REQUEST


def test_protocol_rejects_unknown_operation_input_and_unstable_setup():
    with pytest.raises(ProtocolError) as unknown:
        decode_request(
            b'{"protocol_version":1,"operation":"pause","operation_id":"8d626be1-4a80-4426-b06e-d17fb3f9bb19","input":{"campaign_id":"c","expected_revision":0,"extra":1}}'
        )
    assert unknown.value.code is ProtocolErrorCode.INVALID_REQUEST

    with pytest.raises(ProtocolError, match="campaign.id"):
        decode_request(
            b'{"protocol_version":1,"operation":"setup","operation_id":"8d626be1-4a80-4426-b06e-d17fb3f9bb19","input":{"campaign":{},"mission_plans":[],"roadmap":{},"prior_knowledge":"","first_content":{}}}'
        )


def test_protocol_rejects_unknown_nested_setup_fields():
    from tests.fixtures import mission_content_payload, setup_payload
    payload = setup_payload()
    payload.pop("learner_id")
    payload["campaign"]["id"] = "campaign-a"
    payload["first_content"] = mission_content_payload()
    payload["roadmap"]["phases"][0]["ignored"] = True
    raw = json.dumps({
        "protocol_version": 1, "operation": "setup",
        "operation_id": "8d626be1-4a80-4426-b06e-d17fb3f9bb19",
        "input": payload,
    }).encode()

    with pytest.raises(ProtocolError, match="roadmap phases"):
        decode_request(raw)


def test_protocol_rejects_unsupported_version_and_oversized_input():
    with pytest.raises(ProtocolError) as version:
        decode_request(
            b'{"protocol_version":2,"operation":"status","operation_id":null,"input":{}}'
        )
    assert version.value.code is ProtocolErrorCode.UNSUPPORTED_PROTOCOL

    with pytest.raises(ProtocolError, match="1 MiB"):
        decode_request(b" " * (1024 * 1024 + 1))


def test_protocol_response_encoding_is_exactly_one_compact_json_line():
    encoded = encode_response(
        {
            "protocol_version": 1,
            "operation_id": None,
            "success": True,
            "data": {"campaigns": []},
        }
    )

    assert encoded == b'{"protocol_version":1,"operation_id":null,"success":true,"data":{"campaigns":[]}}\n'


def test_protocol_ships_closed_envelope_and_operation_schemas():
    envelope = json.loads((SCHEMA_ROOT / "protocol-envelope-v1.json").read_text())
    assert envelope["properties"]["protocol_version"]["const"] == 1
    assert envelope["additionalProperties"] is False
    assert set(envelope["required"]) == {
        "protocol_version", "operation", "operation_id", "input"
    }

    names = {operation.value for operation in Operation}
    paths = {path.stem for path in (SCHEMA_ROOT / "operations").glob("*.json")}
    assert paths == names
    for name in names:
        schema = json.loads((SCHEMA_ROOT / "operations" / f"{name}.json").read_text())
        assert schema["properties"]["operation"]["const"] == name
        assert schema["additionalProperties"] is False
        assert schema["properties"]["input"]["additionalProperties"] is False


def test_protocol_export_and_reset_use_safe_data_management(tmp_path):
    from langcampaign.profile import load_or_create_profile

    root = tmp_path / "data"
    profile = load_or_create_profile(root)
    (root / "learners").mkdir()
    destination = tmp_path / "exports"
    destination.mkdir()
    exported = dispatch(
        ProtocolRequest(
            1,
            Operation.EXPORT,
            None,
            {"destination_directory": str(destination)},
        ),
        root / "learners",
        profile.learner_id,
    )
    reset = dispatch(
        ProtocolRequest(
            1,
            Operation.RESET,
            "8d626be1-4a80-4426-b06e-d17fb3f9bb19",
            {"confirmation": "RESET LANGCAMPAIGN"},
        ),
        root / "learners",
        profile.learner_id,
    )

    assert exported["success"] is True
    assert __import__("pathlib").Path(exported["data"]["archive_path"]).exists()
    assert reset["success"] is True
    assert __import__("pathlib").Path(reset["data"]["backup_path"]).exists()


def test_check_install_operation_reports_ready_profile(tmp_path):
    from langcampaign.profile import load_or_create_profile

    root = tmp_path / "data"
    profile = load_or_create_profile(root)
    response = dispatch(
        ProtocolRequest(1, Operation.CHECK_INSTALL, None, {}),
        root / "learners",
        profile.learner_id,
    )

    assert response == {
        "protocol_version": 1,
        "operation_id": None,
        "success": True,
        "data": {
            "python_compatible": True,
            "plugin_version": "0.1.0",
            "profile_ready": True,
        },
    }

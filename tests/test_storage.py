import json
import os
import stat
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

import langcampaign.storage as storage
from langcampaign.assessment import AssessmentEvidence
from langcampaign.models import (
    CampaignType,
    CoachingStyle,
    CurriculumScope,
    Mission,
    MissionStatus,
    new_campaign,
)
from langcampaign.storage import (
    CampaignState,
    CampaignStorageError,
    load_campaign,
    load_campaign_state,
    save_campaign,
    save_campaign_state,
)


def test_campaign_round_trips_through_versioned_json(tmp_path):
    campaign = new_campaign(
        "Travel independently",
        "French",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 9, 10),
    )
    campaign = replace(
        campaign,
        settings=replace(
            campaign.settings,
            curriculum_scope=CurriculumScope.FOUNDATIONAL,
            coaching_style=CoachingStyle.DIRECT,
            expected_minutes_per_week=240,
            minimum_minutes_per_week=90,
        ),
    ).with_missions(
        (
            Mission(
                "hotel",
                "Hotel check-in",
                2.0,
                MissionStatus.REVIEW_DUE,
            ),
        )
    )
    path = tmp_path / "campaign.json"

    save_campaign(path, campaign)
    loaded = load_campaign(path)
    payload = json.loads(path.read_text())

    assert loaded == campaign
    assert payload["schema_version"] == 1
    assert payload["campaign"]["settings"] == {
        "campaign_type": "targeted",
        "curriculum_scope": "foundational",
        "coaching_style": "direct",
        "target_date": "2026-09-10",
        "expected_minutes_per_week": 240,
        "minimum_minutes_per_week": 90,
    }
    assert payload["campaign"]["missions"][0] == {
        "id": "hotel",
        "title": "Hotel check-in",
        "weight": 2.0,
        "status": "review_due",
    }


def test_unknown_schema_version_is_rejected(tmp_path):
    path = tmp_path / "campaign.json"
    path.write_text('{"schema_version": 99, "campaign": {}}')

    with pytest.raises(
        CampaignStorageError,
        match="unsupported schema_version: 99",
    ):
        load_campaign(path)


@pytest.mark.parametrize("version", (True, 1.0, None))
def test_schema_version_must_be_an_exact_integer(tmp_path, version):
    campaign = new_campaign("Text friends", "Spanish")
    path = tmp_path / "campaign.json"
    save_campaign(path, campaign)
    payload = json.loads(path.read_text())
    payload["schema_version"] = version
    path.write_text(json.dumps(payload))

    with pytest.raises(
        CampaignStorageError,
        match="schema_version must be an integer",
    ):
        load_campaign(path)


@pytest.mark.parametrize(
    "contents",
    (
        "not json",
        "[]",
        '{"schema_version": 1}',
        '{"schema_version": 1, "campaign": []}',
    ),
)
def test_invalid_storage_envelopes_raise_consistent_error(tmp_path, contents):
    path = tmp_path / "campaign.json"
    path.write_text(contents)

    with pytest.raises(CampaignStorageError, match="invalid campaign storage"):
        load_campaign(path)


def test_non_utf8_storage_envelope_raises_consistent_error(tmp_path):
    path = tmp_path / "campaign.json"
    path.write_bytes(b"\xff")

    with pytest.raises(CampaignStorageError, match="invalid campaign storage"):
        load_campaign(path)


def test_deserialization_uses_domain_validation(tmp_path):
    path = tmp_path / "campaign.json"
    save_campaign(path, new_campaign("Text friends", "Spanish"))
    payload = json.loads(path.read_text())
    payload["campaign"]["goal"] = "  "
    path.write_text(json.dumps(payload))

    with pytest.raises(CampaignStorageError, match="invalid campaign storage"):
        load_campaign(path)


@pytest.mark.parametrize("invalid_date", (False, 0, ""))
def test_deserialization_rejects_falsey_non_null_target_date(
    tmp_path,
    invalid_date,
):
    path = tmp_path / "campaign.json"
    save_campaign(path, new_campaign("Text friends", "Spanish"))
    payload = json.loads(path.read_text())
    payload["campaign"]["settings"]["target_date"] = invalid_date
    path.write_text(json.dumps(payload))

    with pytest.raises(CampaignStorageError, match="invalid campaign storage"):
        load_campaign(path)


def test_campaign_state_round_trips_assessment_evidence(tmp_path):
    campaign = new_campaign("Text friends", "Spanish").with_missions(
        (
            Mission("chat", "Casual chat", 2.0, MissionStatus.DEMONSTRATED),
            Mission("replies", "Handle replies", 1.0),
        )
    )
    evidence = (
        AssessmentEvidence(
            "chat",
            82,
            True,
            "written_interaction",
            datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc),
            "A2",
        ),
        AssessmentEvidence(
            "replies",
            64,
            False,
            "written_interaction",
            datetime(2026, 7, 27, 9, 15, tzinfo=timezone.utc),
        ),
    )
    state = CampaignState(campaign, evidence)
    path = tmp_path / "campaign-state.json"

    save_campaign_state(path, state)
    loaded = load_campaign_state(path)
    payload = json.loads(path.read_text())

    assert loaded == state
    assert payload["schema_version"] == 2
    assert payload["assessment_evidence"] == [
        {
            "mission_id": "chat",
            "score": 82,
            "independent": True,
            "modality": "written_interaction",
            "assessed_at": "2026-07-20T14:30:00+00:00",
            "cefr": "A2",
        },
        {
            "mission_id": "replies",
            "score": 64,
            "independent": False,
            "modality": "written_interaction",
            "assessed_at": "2026-07-27T09:15:00+00:00",
            "cefr": None,
        },
    ]


def test_campaign_state_loader_accepts_legacy_campaign_file(tmp_path):
    campaign = new_campaign("Text friends", "Spanish")
    path = tmp_path / "campaign.json"
    save_campaign(path, campaign)

    state = load_campaign_state(path)

    assert state == CampaignState(campaign, ())


def test_atomic_save_uses_unique_temp_without_touching_fixed_temp(tmp_path):
    path = tmp_path / "campaign.json"
    fixed_temporary = path.with_suffix(path.suffix + ".tmp")
    fixed_temporary.write_text("belongs to another writer")

    save_campaign(path, new_campaign("Text friends", "Spanish"))

    assert fixed_temporary.read_text() == "belongs to another writer"
    assert tuple(tmp_path.glob(f".{path.name}.*.tmp")) == ()


def test_atomic_save_cleans_unique_temp_when_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "campaign.json"

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(storage.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        save_campaign(path, new_campaign("Text friends", "Spanish"))

    assert tuple(tmp_path.glob(f".{path.name}.*.tmp")) == ()


def test_atomic_save_fsyncs_file_and_parent_directory(tmp_path, monkeypatch):
    path = tmp_path / "campaign.json"
    fsync_targets = []

    def record_fsync(file_descriptor):
        fsync_targets.append(
            stat.S_ISDIR(os.fstat(file_descriptor).st_mode)
        )

    monkeypatch.setattr(storage.os, "fsync", record_fsync)

    save_campaign(path, new_campaign("Text friends", "Spanish"))

    expected_targets = [False, True] if os.name == "posix" else [False]
    assert fsync_targets == expected_targets

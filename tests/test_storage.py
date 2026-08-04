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
    CampaignLifecycle,
    CampaignState,
    CampaignStorageError,
    LearnerCampaignIndex,
    learner_index_from_dict,
    learner_index_to_dict,
    load_campaign,
    load_campaign_state,
    save_campaign,
    save_campaign_state,
)
from langcampaign.runtime import (
    ActiveMissionSession, AttemptKind, CriterionScore, DifficultyAdjustment,
    MissionAttemptRecord, MissionCheckpoint, MissionContent, MissionOutcome,
    RubricCriterion,
)
from tests.fixtures import delayed_arrival, roadmap


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
    assert payload["schema_version"] == 5
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


def test_version_four_state_round_trips_learner_content_and_roadmap(tmp_path):
    from langcampaign.missions import validate_mission_map
    from langcampaign.roadmaps import RoadmapPhase, validate_roadmap

    campaign = new_campaign("Handle hotel delays", "Spanish").with_missions(
        (Mission("delayed-arrival", "Explain a delayed arrival"),)
    )
    mission_plans = (delayed_arrival(),)
    stored_roadmap = replace(
        roadmap(),
        phases=(
            RoadmapPhase(
                "core-transactions",
                "Core transactions",
                "Handle routine hotel exchanges.",
                ("delayed-arrival",),
                True,
                False,
            ),
        ),
    )
    state = CampaignState(
        campaign=campaign,
        learner_id="qasim",
        mission_plans=mission_plans,
        roadmap=stored_roadmap,
    )
    path = tmp_path / "state.json"

    save_campaign_state(path, state)
    loaded = load_campaign_state(path)

    assert loaded == state
    assert json.loads(path.read_text())["schema_version"] == 5
    validate_mission_map(loaded.mission_plans, ("delayed-arrival",))
    validate_roadmap(loaded.roadmap, loaded.mission_plans)


def test_version_two_state_migrates_to_default_content_fields(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(existing_version_two_payload()))

    loaded = load_campaign_state(path)

    assert loaded.learner_id == "default"
    assert loaded.mission_plans == ()
    assert loaded.roadmap is None


def existing_version_two_payload():
    campaign = new_campaign("Read social media", "Japanese")
    return {
        "schema_version": 2,
        "campaign": storage.campaign_to_dict(campaign),
        "assessment_evidence": [],
    }


def existing_version_three_payload():
    campaign = new_campaign("Read social media", "Japanese")
    return {
        "schema_version": 3,
        "campaign": storage.campaign_to_dict(campaign),
        "assessment_evidence": [],
        "learner_id": "qasim",
        "mission_plans": [],
        "roadmap": None,
    }


def test_version_four_round_trips_prior_knowledge(tmp_path):
    state = CampaignState(
        new_campaign("Text friends", "Spanish"),
        learner_id="qasim",
        prior_knowledge="Can read casual messages but rarely speaks.",
    )
    path = tmp_path / "state.json"

    save_campaign_state(path, state)

    assert load_campaign_state(path) == state
    assert json.loads(path.read_text())["schema_version"] == 5


def _runtime_content():
    return MissionContent(
        "generation-1", 1, "Explain delay", "Hotel arrival", ("Explain",),
        ("llego tarde",), ("Say it",), "Respond without help",
        (RubricCriterion("delay", "States delay", 50), RubricCriterion("time", "Gives time", 50)),
    )


def test_version_five_round_trips_runtime_state_and_nested_records(tmp_path):
    campaign = new_campaign("Handle hotel delays", "Spanish").with_missions((Mission("reply", "Reply"),))
    content = _runtime_content()
    record = MissionAttemptRecord(
        "reply", 2, AttemptKind.RETRY, content.rubric,
        (CriterionScore("delay", 80), CriterionScore("time", 100)), 90,
        MissionOutcome.PASS, "text", "Clear reply", datetime(2026, 8, 4, tzinfo=timezone.utc),
    )
    plan = delayed_arrival(id="reply", title="Reply")
    stored_roadmap = replace(roadmap(), phases=(
        storage.RoadmapPhase("phase-1", "Phase", "Reply", ("reply",), True, False),
    ), active_phase_id="phase-1")
    state = CampaignState(campaign, (AssessmentEvidence("reply", 90, True, "text", record.assessed_at),), "qasim", (plan,), stored_roadmap, "", 7,
        ActiveMissionSession("reply", 3, AttemptKind.RETRY, MissionCheckpoint.CHECK_READY, DifficultyAdjustment.STANDARD, content),
        (record,), ("phase-1",))
    path = tmp_path / "state.json"

    save_campaign_state(path, state)
    payload = json.loads(path.read_text())

    assert load_campaign_state(path) == state
    assert payload["schema_version"] == 5
    assert payload["revision"] == 7
    assert payload["active_session"]["mission_id"] == "reply"
    assert payload["active_session"]["attempt_number"] == 3
    assert payload["mission_attempts"][0]["criterion_scores"] == [{"criterion_id": "delay", "score": 80}, {"criterion_id": "time", "score": 100}]
    assert payload["completed_review_phase_ids"] == ["phase-1"]


@pytest.mark.parametrize("version", (1, 2, 3, 4))
def test_historical_schemas_load_runtime_defaults_without_rewriting(tmp_path, version):
    payload = existing_version_two_payload() if version == 2 else existing_version_three_payload() if version == 3 else storage._campaign_state_payload(CampaignState(new_campaign("Text", "Spanish")))
    payload["schema_version"] = version
    if version == 1:
        payload.pop("assessment_evidence", None)
        payload.pop("learner_id", None)
        payload.pop("mission_plans", None)
        payload.pop("roadmap", None)
        payload.pop("prior_knowledge", None)
    if version == 2:
        payload.pop("learner_id", None); payload.pop("mission_plans", None); payload.pop("roadmap", None); payload.pop("prior_knowledge", None)
    if version == 3:
        payload.pop("prior_knowledge", None)
    path = tmp_path / "state.json"
    path.write_text(json.dumps(payload))
    before = path.read_bytes()

    loaded = load_campaign_state(path)

    assert (loaded.revision, loaded.active_session, loaded.mission_attempts, loaded.completed_review_phase_ids) == (0, None, (), ())
    assert path.read_bytes() == before


@pytest.mark.parametrize("revision", (True, -1, 1.2))
def test_campaign_state_rejects_non_integer_nonnegative_revision(revision):
    with pytest.raises(ValueError, match="revision"):
        CampaignState(new_campaign("Text", "Spanish"), revision=revision)


def test_version_three_migrates_with_empty_prior_knowledge(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(existing_version_three_payload()))

    assert load_campaign_state(path).prior_knowledge == ""


@pytest.mark.parametrize("value", (None, 1, [], {}))
def test_campaign_state_rejects_non_string_prior_knowledge(value):
    with pytest.raises(ValueError, match="prior_knowledge must be a string"):
        CampaignState(new_campaign("Text friends", "Spanish"), prior_knowledge=value)


def test_learner_index_is_immutable_and_has_one_active_campaign():
    index = LearnerCampaignIndex("campaign-a", ("campaign-b",))

    assert index.lifecycle_for("campaign-a") is CampaignLifecycle.ACTIVE
    assert index.lifecycle_for("campaign-b") is CampaignLifecycle.COMPLETED
    assert index.lifecycle_for("campaign-c") is CampaignLifecycle.PAUSED
    with pytest.raises(AttributeError):
        index.active_campaign_id = "campaign-c"


@pytest.mark.parametrize(
    "active_campaign_id, completed_campaign_ids",
    (
        (1, ()),
        ("campaign-a", ["campaign-b"]),
        ("campaign-a", (1,)),
        ("campaign-a", ("campaign-b", "campaign-b")),
        ("campaign-a", ("campaign-a",)),
    ),
)
def test_learner_index_rejects_invalid_identifier_boundaries(
    active_campaign_id, completed_campaign_ids
):
    with pytest.raises(ValueError):
        LearnerCampaignIndex(active_campaign_id, completed_campaign_ids)


def test_learner_index_converts_versioned_payload():
    index = LearnerCampaignIndex("campaign-a", ("campaign-b",))

    assert learner_index_to_dict(index) == {
        "schema_version": 1,
        "active_campaign_id": "campaign-a",
        "completed_campaign_ids": ["campaign-b"],
    }
    assert learner_index_from_dict(learner_index_to_dict(index)) == index


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"schema_version": 2, "active_campaign_id": None, "completed_campaign_ids": []},
        {"schema_version": 1, "active_campaign_id": [], "completed_campaign_ids": []},
        {"schema_version": 1, "active_campaign_id": None, "completed_campaign_ids": "x"},
    ),
)
def test_learner_index_rejects_unknown_or_malformed_payload(payload):
    with pytest.raises(CampaignStorageError):
        learner_index_from_dict(payload)


@pytest.mark.parametrize(
    "mutate_payload",
    (
        lambda payload: payload.update(learner_id=None),
        lambda payload: payload.update(mission_plans={}),
        lambda payload: payload.update(roadmap=[]),
        lambda payload: payload.update(mission_plans=[None]),
        lambda payload: payload["mission_plans"][0].update(priority="unknown"),
        lambda payload: payload.update(roadmap={"phases": [None]}),
        lambda payload: payload.update(assessment_evidence=[None]),
    ),
)
def test_malformed_version_three_content_raises_campaign_storage_error(
    tmp_path, mutate_payload
):
    campaign = new_campaign("Handle hotel delays", "Spanish").with_missions(
        (Mission("delayed-arrival", "Explain a delayed arrival"),)
    )
    state = CampaignState(campaign, mission_plans=(delayed_arrival(),))
    path = tmp_path / "state.json"
    save_campaign_state(path, state)
    payload = json.loads(path.read_text())
    mutate_payload(payload)
    path.write_text(json.dumps(payload))

    with pytest.raises(CampaignStorageError, match="invalid campaign storage"):
        load_campaign_state(path)


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

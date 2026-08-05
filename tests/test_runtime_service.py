from dataclasses import replace
from datetime import datetime, timezone

import pytest

import langcampaign.runtime_service as runtime_service
from langcampaign.learners import complete_campaign, create_and_activate_campaign, select_campaign
from langcampaign.models import Campaign, CampaignSettings, Mission, MissionStatus
from langcampaign.missions import MissionPriority
from langcampaign.roadmaps import CampaignRoadmap, RoadmapPhase
from langcampaign.runtime import AttemptKind, CriterionScore, DifficultyAdjustment, MissionCheckpoint, MissionContent, NextActionType, RubricCriterion
from langcampaign.runtime_service import MissionRuntimeError, RuntimeErrorCode, adjust_difficulty, advance_mission, mission_status, return_to_practice, start_mission, submit_assessment
from langcampaign.storage import CampaignState, CampaignStorageError
from tests.fixtures import delayed_arrival, roadmap


def _content():
    return MissionContent("g", 1, "Notify a hotel of a late arrival and answer one follow-up.", "Hotel", ("Explain",), ("retraso",), ("Prompt",), "Answer", (RubricCriterion("delay", "Delay", 50), RubricCriterion("time", "Time", 50)))


def _state():
    campaign = Campaign("campaign-a", "Hotel", "Spanish", CampaignSettings(), (Mission("delayed-arrival", "Delay"),))
    plan = delayed_arrival()
    current_roadmap = roadmap()
    from dataclasses import replace
    from langcampaign.roadmaps import RoadmapPhase
    current_roadmap = replace(current_roadmap, phases=(RoadmapPhase("core", "Core", "Core", ("delayed-arrival",), True, False),), active_phase_id="core")
    return CampaignState(campaign, learner_id="qasim", mission_plans=(plan,), roadmap=current_roadmap)


def test_runtime_service_persists_checkpoint_assessment_and_read_only_status(tmp_path):
    create_and_activate_campaign(tmp_path, _state())
    before = (tmp_path / "qasim" / "campaign-a" / "state.json").read_bytes()
    assert mission_status(tmp_path, "qasim", "campaign-a").session is None
    assert (tmp_path / "qasim" / "campaign-a" / "state.json").read_bytes() == before
    started = start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())
    guided = advance_mission(tmp_path, "qasim", "campaign-a", started.revision, "delayed-arrival", 1)
    ready = advance_mission(tmp_path, "qasim", "campaign-a", guided.revision, "delayed-arrival", 1)
    assessed = submit_assessment(tmp_path, "qasim", "campaign-a", ready.revision, "delayed-arrival", 1, (CriterionScore("delay", 80), CriterionScore("time", 80)), True, "text", "Clear", now=lambda: datetime(2026, 8, 4, tzinfo=timezone.utc))
    assert assessed.session.checkpoint is MissionCheckpoint.ASSESSED
    assert assessed.revision == 4


def test_runtime_mutations_reconcile_domain_commit_before_receipt_replay(tmp_path):
    create_and_activate_campaign(tmp_path, _state())
    started = start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())
    started_replay = start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())
    guided = advance_mission(tmp_path, "qasim", "campaign-a", 1, "delayed-arrival", 1)
    guided_replay = advance_mission(tmp_path, "qasim", "campaign-a", 1, "delayed-arrival", 1)
    adjusted = adjust_difficulty(tmp_path, "qasim", "campaign-a", 2, "delayed-arrival", 1, DifficultyAdjustment.HARDER)
    adjusted_replay = adjust_difficulty(tmp_path, "qasim", "campaign-a", 2, "delayed-arrival", 1, DifficultyAdjustment.HARDER)

    assert started_replay.revision == started.revision == 1
    assert guided_replay.revision == guided.revision == 2
    assert adjusted_replay.revision == adjusted.revision == 3


def test_difficulty_at_check_ready_requires_replacement_content(tmp_path):
    create_and_activate_campaign(tmp_path, _state())
    started = start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())
    guided = advance_mission(tmp_path, "qasim", "campaign-a", started.revision, "delayed-arrival", 1)
    ready = advance_mission(tmp_path, "qasim", "campaign-a", guided.revision, "delayed-arrival", 1)
    adjusted = adjust_difficulty(tmp_path, "qasim", "campaign-a", ready.revision, "delayed-arrival", 1, DifficultyAdjustment.HARDER)
    assert adjusted.session.checkpoint is MissionCheckpoint.GUIDED_PRACTICE
    assert adjusted.session.content_refresh_required is True


def test_accidental_help_returns_check_to_guided_practice_without_evidence(tmp_path):
    create_and_activate_campaign(tmp_path, _state())
    started = start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())
    guided = advance_mission(tmp_path, "qasim", "campaign-a", started.revision, "delayed-arrival", 1)
    ready = advance_mission(tmp_path, "qasim", "campaign-a", guided.revision, "delayed-arrival", 1)

    recovered = return_to_practice(
        tmp_path, "qasim", "campaign-a", ready.revision, "delayed-arrival", 1
    )
    replayed = return_to_practice(
        tmp_path, "qasim", "campaign-a", ready.revision, "delayed-arrival", 1
    )
    stored = select_campaign(tmp_path, "qasim", "campaign-a")

    assert recovered.session.checkpoint is MissionCheckpoint.GUIDED_PRACTICE
    assert recovered.session.content_refresh_required is True
    assert recovered.session.attempt_number == 1
    assert stored.assessment_evidence == ()
    assert stored.mission_attempts == ()
    assert replayed.revision == recovered.revision


def test_assessed_next_action_is_atomically_consumed_for_retry(tmp_path):
    create_and_activate_campaign(tmp_path, _state())
    started = start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())
    guided = advance_mission(tmp_path, "qasim", "campaign-a", started.revision, "delayed-arrival", 1)
    ready = advance_mission(tmp_path, "qasim", "campaign-a", guided.revision, "delayed-arrival", 1)
    assessed = submit_assessment(tmp_path, "qasim", "campaign-a", ready.revision, "delayed-arrival", 1, (CriterionScore("delay", 40), CriterionScore("time", 40)), True, "text", "Partial", now=lambda: datetime(2026, 8, 4, tzinfo=timezone.utc))
    retry = start_mission(tmp_path, "qasim", "campaign-a", assessed.revision, "delayed-arrival", _content())
    assert retry.session.attempt_number == 2
    assert retry.session.kind.value == "retry"


def test_initial_start_uses_setup_priority_and_prerequisite_policy(tmp_path):
    enrichment = delayed_arrival(id="enrichment", title="Enrichment", priority=MissionPriority.ENRICHMENT)
    critical = delayed_arrival(id="critical", title="Critical", priority=MissionPriority.CRITICAL)
    campaign = Campaign(
        "campaign-a", "Hotel", "Spanish", CampaignSettings(),
        (Mission("enrichment", "Enrichment"), Mission("critical", "Critical")),
    )
    ordered = CampaignRoadmap(
        (RoadmapPhase("core", "Core", "Core", ("enrichment", "critical"), False, False),),
        "core",
        (),
    )
    create_and_activate_campaign(
        tmp_path,
        CampaignState(campaign, learner_id="qasim", mission_plans=(enrichment, critical), roadmap=ordered),
    )

    started = start_mission(tmp_path, "qasim", "campaign-a", 0, "critical", _content())

    assert started.session.mission_id == "critical"


def test_initial_start_rejects_an_arbitrary_later_mission(tmp_path):
    critical = delayed_arrival(id="critical", title="Critical", priority=MissionPriority.CRITICAL)
    later = delayed_arrival(id="later", title="Later", priority=MissionPriority.CRITICAL)
    campaign = Campaign(
        "campaign-a", "Hotel", "Spanish", CampaignSettings(),
        (Mission("critical", "Critical"), Mission("later", "Later")),
    )
    ordered = CampaignRoadmap(
        (RoadmapPhase("core", "Core", "Core", ("critical", "later"), False, False),),
        "core",
        (),
    )
    create_and_activate_campaign(
        tmp_path,
        CampaignState(campaign, learner_id="qasim", mission_plans=(critical, later), roadmap=ordered),
    )

    with pytest.raises(MissionRuntimeError) as raised:
        start_mission(tmp_path, "qasim", "campaign-a", 0, "later", _content())

    assert raised.value.code is RuntimeErrorCode.INVALID_TRANSITION


def test_single_mission_planned_review_is_selected_before_goal_readiness(tmp_path):
    create_and_activate_campaign(tmp_path, _state())
    started = start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())
    guided = advance_mission(tmp_path, "qasim", "campaign-a", started.revision, "delayed-arrival", 1)
    ready = advance_mission(tmp_path, "qasim", "campaign-a", guided.revision, "delayed-arrival", 1)

    assessed = submit_assessment(
        tmp_path, "qasim", "campaign-a", ready.revision, "delayed-arrival", 1,
        (CriterionScore("delay", 90), CriterionScore("time", 90)), True, "text", "Passed",
        now=lambda: datetime(2026, 8, 4, tzinfo=timezone.utc),
    )

    assert assessed.session.next_action.kind is NextActionType.REVIEW
    assert select_campaign(tmp_path, "qasim", "campaign-a").campaign.missions[0].status is MissionStatus.REVIEW_DUE


def test_low_review_stays_due_and_retry_remains_a_review_attempt(tmp_path):
    state = replace(
        _state(),
        campaign=_state().campaign.with_missions((Mission("delayed-arrival", "Delay", status=MissionStatus.REVIEW_DUE),)),
        active_session=runtime_service.ActiveMissionSession(
            "delayed-arrival", 1, AttemptKind.REVIEW, MissionCheckpoint.CHECK_READY,
            DifficultyAdjustment.STANDARD, _content(),
        ),
    )
    create_and_activate_campaign(tmp_path, state)

    assessed = submit_assessment(
        tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", 1,
        (CriterionScore("delay", 60), CriterionScore("time", 60)), True, "text", "Needs review",
        now=lambda: datetime(2026, 8, 4, tzinfo=timezone.utc),
    )
    retry = start_mission(tmp_path, "qasim", "campaign-a", assessed.revision, "delayed-arrival", _content())

    assert select_campaign(tmp_path, "qasim", "campaign-a").campaign.missions[0].status is MissionStatus.REVIEW_DUE
    assert retry.session.kind is AttemptKind.REVIEW


def test_all_planned_reviews_complete_phase_once_without_rewinding_active_phase(tmp_path):
    first = delayed_arrival(id="first", title="First")
    second = delayed_arrival(id="second", title="Second")
    campaign = Campaign(
        "campaign-a", "Hotel", "Spanish", CampaignSettings(),
        (Mission("first", "First", status=MissionStatus.REVIEW_DUE), Mission("second", "Second", status=MissionStatus.REVIEW_DUE)),
    )
    phases = CampaignRoadmap(
        (
            RoadmapPhase("review-phase", "Review", "Review", ("first", "second"), True, False),
            RoadmapPhase("active-phase", "Active", "Active", (), False, False),
        ),
        "active-phase",
        (),
    )
    state = CampaignState(
        campaign, learner_id="qasim", mission_plans=(first, second), roadmap=phases,
        active_session=runtime_service.ActiveMissionSession(
            "first", 1, AttemptKind.REVIEW, MissionCheckpoint.CHECK_READY,
            DifficultyAdjustment.STANDARD, replace(_content(), capability=first.capability),
        ),
    )
    create_and_activate_campaign(tmp_path, state)
    scores = (CriterionScore("delay", 90), CriterionScore("time", 90))

    first_result = submit_assessment(
        tmp_path, "qasim", "campaign-a", 0, "first", 1, scores, True, "text", "First passed",
        now=lambda: datetime(2026, 8, 4, 10, tzinfo=timezone.utc),
    )
    second_started = start_mission(
        tmp_path, "qasim", "campaign-a", first_result.revision, "second",
        replace(_content(), capability=second.capability),
    )
    second_guided = advance_mission(tmp_path, "qasim", "campaign-a", second_started.revision, "second", 1)
    second_ready = advance_mission(tmp_path, "qasim", "campaign-a", second_guided.revision, "second", 1)
    submit_assessment(
        tmp_path, "qasim", "campaign-a", second_ready.revision, "second", 1, scores, True, "text", "Second passed",
        now=lambda: datetime(2026, 8, 4, 11, tzinfo=timezone.utc),
    )
    stored = select_campaign(tmp_path, "qasim", "campaign-a")

    assert stored.completed_review_phase_ids == ("review-phase",)
    assert stored.roadmap.active_phase_id == "active-phase"


def test_teaching_adjustment_requires_refreshed_persisted_content(tmp_path):
    create_and_activate_campaign(tmp_path, _state())
    started = start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())

    adjusted = adjust_difficulty(
        tmp_path, "qasim", "campaign-a", started.revision, "delayed-arrival", 1,
        DifficultyAdjustment.HARDER,
    )

    assert adjusted.session.content_refresh_required is True


def test_adjusted_replacement_is_compared_with_pre_replacement_capability(tmp_path):
    create_and_activate_campaign(tmp_path, _state())
    started = start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())
    guided = advance_mission(tmp_path, "qasim", "campaign-a", started.revision, "delayed-arrival", 1)
    ready = advance_mission(tmp_path, "qasim", "campaign-a", guided.revision, "delayed-arrival", 1)
    adjusted = adjust_difficulty(tmp_path, "qasim", "campaign-a", ready.revision, "delayed-arrival", 1, DifficultyAdjustment.HARDER)

    with pytest.raises(MissionRuntimeError) as raised:
        advance_mission(
            tmp_path, "qasim", "campaign-a", adjusted.revision, "delayed-arrival", 1,
            replace(_content(), capability="A different capability"),
        )

    assert raised.value.code is RuntimeErrorCode.INVALID_CONTENT


def test_assessed_status_renders_stored_result_and_consuming_action_clears_it(tmp_path):
    create_and_activate_campaign(tmp_path, _state())
    started = start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())
    guided = advance_mission(tmp_path, "qasim", "campaign-a", started.revision, "delayed-arrival", 1)
    ready = advance_mission(tmp_path, "qasim", "campaign-a", guided.revision, "delayed-arrival", 1)
    assessed = submit_assessment(
        tmp_path, "qasim", "campaign-a", ready.revision, "delayed-arrival", 1,
        (CriterionScore("delay", 40), CriterionScore("time", 40)), True, "text",
        "Stored evidence-based result",
        now=lambda: datetime(2026, 8, 4, tzinfo=timezone.utc),
    )

    fresh = mission_status(tmp_path, "qasim", "campaign-a")
    retry = start_mission(tmp_path, "qasim", "campaign-a", assessed.revision, "delayed-arrival", _content())

    assert fresh.latest_result.result_statement == "Stored evidence-based result"
    assert "Stored evidence-based result" in fresh.rendered_progress
    assert retry.next_action is None


def test_completed_campaign_and_expected_persistence_failures_are_typed(tmp_path, monkeypatch):
    create_and_activate_campaign(tmp_path, _state())
    complete_campaign(tmp_path, "qasim", "campaign-a")

    with pytest.raises(MissionRuntimeError) as completed:
        mission_status(tmp_path, "qasim", "campaign-a")
    assert completed.value.code is RuntimeErrorCode.CAMPAIGN_COMPLETED

    create_and_activate_campaign(tmp_path / "other", _state())
    monkeypatch.setattr(
        runtime_service,
        "mutate_learner_campaign",
        lambda *args, **kwargs: (_ for _ in ()).throw(CampaignStorageError("disk state failed")),
    )
    with pytest.raises(MissionRuntimeError) as persistence:
        start_mission(tmp_path / "other", "qasim", "campaign-a", 0, "delayed-arrival", _content())
    assert persistence.value.code is RuntimeErrorCode.PERSISTENCE_FAILED


def test_runtime_does_not_hide_injected_programmer_fault(tmp_path, monkeypatch):
    create_and_activate_campaign(tmp_path, _state())
    monkeypatch.setattr(
        runtime_service,
        "mutate_learner_campaign",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("programmer fault")),
    )

    with pytest.raises(ValueError, match="programmer fault"):
        start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())


def test_assessment_does_not_hide_injected_scoring_programmer_fault(tmp_path, monkeypatch):
    create_and_activate_campaign(tmp_path, _state())
    started = start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())
    guided = advance_mission(tmp_path, "qasim", "campaign-a", started.revision, "delayed-arrival", 1)
    ready = advance_mission(tmp_path, "qasim", "campaign-a", guided.revision, "delayed-arrival", 1)
    monkeypatch.setattr(
        runtime_service,
        "derive_score",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("scoring programmer fault")),
    )

    with pytest.raises(ValueError, match="scoring programmer fault") as raised:
        submit_assessment(
            tmp_path, "qasim", "campaign-a", ready.revision, "delayed-arrival", 1,
            (CriterionScore("delay", 80), CriterionScore("time", 80)), True, "text", "Valid",
        )

    assert type(raised.value) is ValueError


def test_runtime_revalidates_active_state_when_completion_wins_race(tmp_path, monkeypatch):
    create_and_activate_campaign(tmp_path, _state())
    original_mutate = runtime_service.mutate_learner_campaign

    def complete_before_locked_reload(root, learner_id, campaign_id, *args, **kwargs):
        complete_campaign(root, learner_id, campaign_id)
        return original_mutate(root, learner_id, campaign_id, *args, **kwargs)

    monkeypatch.setattr(runtime_service, "mutate_learner_campaign", complete_before_locked_reload)

    with pytest.raises(MissionRuntimeError) as raised:
        start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())

    assert raised.value.code is RuntimeErrorCode.CAMPAIGN_COMPLETED
    assert select_campaign(tmp_path, "qasim", "campaign-a").revision == 0


@pytest.mark.parametrize(
    ("learner_id", "campaign_id"),
    (("###", "campaign-a"), ("qasim", "../campaign-a")),
)
def test_read_status_translates_malformed_repository_ids_to_invalid_request(
    tmp_path, learner_id, campaign_id
):
    with pytest.raises(MissionRuntimeError) as raised:
        mission_status(tmp_path, learner_id, campaign_id)

    assert raised.value.code is RuntimeErrorCode.INVALID_REQUEST

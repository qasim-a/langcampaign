from datetime import datetime, timezone

from langcampaign.learners import create_and_activate_campaign
from langcampaign.models import Campaign, CampaignSettings, Mission
from langcampaign.runtime import CriterionScore, DifficultyAdjustment, MissionCheckpoint, MissionContent, RubricCriterion
from langcampaign.runtime_service import adjust_difficulty, advance_mission, mission_status, start_mission, submit_assessment
from langcampaign.storage import CampaignState
from tests.fixtures import delayed_arrival, roadmap


def _content():
    return MissionContent("g", 1, "Notify a hotel of a late arrival and answer one follow-up.", "Hotel", ("Explain",), ("retraso",), ("Prompt",), "Answer", (RubricCriterion("delay", "Delay", 50), RubricCriterion("time", "Time", 50)))


def _state():
    campaign = Campaign("campaign-a", "Hotel", "Spanish", CampaignSettings(), (Mission("delayed-arrival", "Delay"),))
    plan = delayed_arrival()
    current_roadmap = roadmap()
    from dataclasses import replace
    from langcampaign.roadmaps import RoadmapPhase
    current_roadmap = replace(current_roadmap, phases=(RoadmapPhase("core", "Core", "Core", ("delayed-arrival",), False, False),), active_phase_id="core")
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


def test_difficulty_at_check_ready_requires_replacement_content(tmp_path):
    create_and_activate_campaign(tmp_path, _state())
    started = start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())
    guided = advance_mission(tmp_path, "qasim", "campaign-a", started.revision, "delayed-arrival", 1)
    ready = advance_mission(tmp_path, "qasim", "campaign-a", guided.revision, "delayed-arrival", 1)
    adjusted = adjust_difficulty(tmp_path, "qasim", "campaign-a", ready.revision, "delayed-arrival", 1, DifficultyAdjustment.HARDER)
    assert adjusted.session.checkpoint is MissionCheckpoint.GUIDED_PRACTICE
    assert adjusted.session.content_refresh_required is True


def test_assessed_next_action_is_atomically_consumed_for_retry(tmp_path):
    create_and_activate_campaign(tmp_path, _state())
    started = start_mission(tmp_path, "qasim", "campaign-a", 0, "delayed-arrival", _content())
    guided = advance_mission(tmp_path, "qasim", "campaign-a", started.revision, "delayed-arrival", 1)
    ready = advance_mission(tmp_path, "qasim", "campaign-a", guided.revision, "delayed-arrival", 1)
    assessed = submit_assessment(tmp_path, "qasim", "campaign-a", ready.revision, "delayed-arrival", 1, (CriterionScore("delay", 40), CriterionScore("time", 40)), True, "text", "Partial", now=lambda: datetime(2026, 8, 4, tzinfo=timezone.utc))
    retry = start_mission(tmp_path, "qasim", "campaign-a", assessed.revision, "delayed-arrival", _content())
    assert retry.session.attempt_number == 2
    assert retry.session.kind.value == "retry"

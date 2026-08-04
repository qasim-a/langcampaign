from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from langcampaign.assessment import AssessmentEvidence
from langcampaign.models import Campaign, CampaignSettings, Mission, MissionStatus
from langcampaign.missions import MissionPriority
from langcampaign.roadmaps import CampaignRoadmap, RoadmapPhase
from langcampaign.runtime import (
    ActiveMissionSession,
    AttemptKind,
    CriterionScore,
    DifficultyAdjustment,
    MissionAttemptRecord,
    MissionCheckpoint,
    MissionContent,
    MissionOutcome,
    NextAction,
    NextActionType,
    RubricCriterion,
    best_independent_scores,
    derive_score,
    outcome_for_score,
    render_runtime_progress,
    runtime_progress,
    select_next_action,
)
from tests.fixtures import delayed_arrival, plans


def _content(**changes):
    values = dict(
        generation_id="g-1", candidate_number=1, capability="Reply politely",
        scenario="A hotel calls", teaching_objectives=("State delay",),
        essential_language=("Voy tarde",), guided_prompts=("Try it",),
        assessment_prompt="Reply without help",
        rubric=(RubricCriterion("delay", "States the delay", 40), RubricCriterion("time", "Gives a time", 60)),
    )
    values.update(changes)
    return MissionContent(**values)


def _campaign(*, statuses=()):
    defaults = (MissionStatus.NOT_ASSESSED,) * 3
    statuses = statuses or defaults
    return Campaign("campaign", "Travel", "Spanish", CampaignSettings(), (
        Mission("delayed-arrival", "Delay", 1, statuses[0]),
        Mission("hotel-check-in", "Check in", 2, statuses[1]),
        Mission("train-options", "Train", 1, statuses[2]),
    ), datetime(2026, 1, 1, tzinfo=timezone.utc))


def _roadmap():
    return CampaignRoadmap((
        RoadmapPhase("one", "One", "Core", ("delayed-arrival", "hotel-check-in"), True, False),
        RoadmapPhase("two", "Two", "More", ("train-options",), False, False),
    ), "one", ())


def test_runtime_records_are_immutable_and_validate_boundaries():
    assert [item.value for item in MissionCheckpoint] == ["teaching", "guided_practice", "check_ready", "assessed"]
    assert [item.value for item in DifficultyAdjustment] == ["standard", "harder", "prerequisite_support"]
    assert [item.value for item in AttemptKind] == ["initial", "retry", "prerequisite_supported", "review"]
    assert [item.value for item in MissionOutcome] == ["pass", "partial", "retry"]
    assert [item.value for item in NextActionType] == ["prerequisite_support", "focused_retry", "review", "next_mission", "goal_ready_to_complete"]
    content = _content()
    with pytest.raises(FrozenInstanceError):
        content.scenario = "changed"
    with pytest.raises(ValueError, match="weights"):
        _content(rubric=(RubricCriterion("only", "Only", 99),))
    with pytest.raises(ValueError, match="candidate"):
        _content(candidate_number=3)
    with pytest.raises(ValueError, match="mission_id"):
        NextAction(NextActionType.NEXT_MISSION)
    with pytest.raises(ValueError, match="must not"):
        NextAction(NextActionType.GOAL_READY_TO_COMPLETE, "delayed-arrival")


def test_score_and_attempt_records_require_exact_rubric_coverage():
    rubric = _content().rubric
    scores = (CriterionScore("delay", 39), CriterionScore("time", 40))
    assert derive_score(rubric, scores) == 40
    assert outcome_for_score(39) is MissionOutcome.RETRY
    assert outcome_for_score(40) is MissionOutcome.PARTIAL
    assert outcome_for_score(79) is MissionOutcome.PARTIAL
    assert outcome_for_score(80) is MissionOutcome.PASS
    with pytest.raises(ValueError, match="integer"):
        outcome_for_score(True)
    with pytest.raises(ValueError, match="coverage"):
        derive_score(rubric, (CriterionScore("delay", 80),))
    with pytest.raises(ValueError, match="timezone"):
        MissionAttemptRecord("delayed-arrival", 1, AttemptKind.INITIAL, rubric, scores, 40, MissionOutcome.PARTIAL, "text", "Result", datetime.now())


def test_best_independent_scores_and_weighted_half_up_runtime_progress():
    campaign = _campaign()
    evidence = (
        AssessmentEvidence("delayed-arrival", 40, True, "text", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        AssessmentEvidence("delayed-arrival", 90, True, "text", datetime(2026, 1, 2, tzinfo=timezone.utc)),
        AssessmentEvidence("hotel-check-in", 100, False, "text", datetime(2026, 1, 2, tzinfo=timezone.utc)),
        AssessmentEvidence("train-options", 9, True, "text", datetime(2026, 1, 2, tzinfo=timezone.utc)),
    )
    assert best_independent_scores(campaign, evidence) == {"delayed-arrival": 90, "train-options": 9}
    progress = runtime_progress(campaign, evidence)
    assert progress.percent == 25
    assert progress.best_scores == (("delayed-arrival", 90), ("train-options", 9))


@pytest.mark.parametrize(("percent", "bar"), [(0, "░" * 10), (9, "░" * 10), (10, "█" + "░" * 9), (40, "█" * 4 + "░" * 6), (99, "█" * 9 + "░"), (100, "█" * 10)])
def test_runtime_progress_rendering_uses_floor_ten_segment_bar(percent, bar):
    from langcampaign.runtime import RuntimeProgress
    output = render_runtime_progress(MissionOutcome.PASS, "Recorded.", RuntimeProgress(percent, ()), "Continue.")
    assert output == f"✅ Mission passed\n\nRecorded.\n\nProgress  {bar}  {percent}%\n\nNext: Continue."


def test_next_action_prioritizes_retry_partial_reviews_missions_and_goal():
    current = ActiveMissionSession("delayed-arrival", 1, AttemptKind.INITIAL, MissionCheckpoint.CHECK_READY, DifficultyAdjustment.STANDARD, _content())
    assert select_next_action(_campaign(), plans(), _roadmap(), (), current, MissionOutcome.RETRY).kind is NextActionType.PREREQUISITE_SUPPORT
    assert select_next_action(_campaign(), plans(), _roadmap(), (), current, MissionOutcome.PARTIAL).kind is NextActionType.FOCUSED_RETRY
    review_campaign = _campaign(statuses=(MissionStatus.DEMONSTRATED, MissionStatus.REVIEW_DUE, MissionStatus.NOT_ASSESSED))
    assert select_next_action(review_campaign, plans(), _roadmap(), (), current, MissionOutcome.PASS).mission_id == "hotel-check-in"
    assert select_next_action(_campaign(), plans(), _roadmap(), (), current, MissionOutcome.PASS).mission_id == "hotel-check-in"
    done = _campaign(statuses=(MissionStatus.DEMONSTRATED, MissionStatus.DEMONSTRATED, MissionStatus.NOT_ASSESSED))
    assert select_next_action(done, plans(), _roadmap(), ("one",), current, MissionOutcome.PASS) == NextAction(NextActionType.GOAL_READY_TO_COMPLETE)

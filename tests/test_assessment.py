from datetime import datetime, timezone

import pytest

from langcampaign.assessment import (
    AssessmentEvidence,
    calculate_readiness,
    summarize_cefr,
)
from langcampaign.models import Mission, new_campaign


def test_readiness_uses_weighted_assessment_evidence_only():
    campaign = new_campaign("Text friends", "Spanish").with_missions(
        (Mission("chat", "Casual chat", 2.0), Mission("posts", "Read posts", 1.0))
    )
    evidence = (
        AssessmentEvidence(
            mission_id="chat",
            score=80,
            independent=True,
            modality="written_interaction",
            assessed_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
            cefr="A2",
        ),
    )

    result = calculate_readiness(campaign, evidence)

    assert result.percent == 53
    assert result.unassessed_mission_ids == ("posts",)


def test_cefr_summary_is_affirmative_and_modality_specific():
    evidence = tuple(
        AssessmentEvidence(
            mission_id=str(index),
            score=75,
            independent=True,
            modality="written_interaction",
            assessed_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
            cefr="A2",
        )
        for index in range(4)
    )

    assert summarize_cefr(evidence, "written_interaction") == (
        "You demonstrated approximately A2 written interaction "
        "across 4 independent assessments."
    )


@pytest.mark.parametrize("score", (0, 100))
def test_assessment_evidence_accepts_integer_score_boundaries(score):
    evidence = AssessmentEvidence(
        mission_id="chat",
        score=score,
        independent=True,
        modality="written_interaction",
        assessed_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
    )

    assert evidence.score == score


@pytest.mark.parametrize("score", (-1, 101, 50.5, True))
def test_assessment_evidence_rejects_scores_outside_integer_percentage_range(score):
    with pytest.raises(ValueError, match="score must be an integer from 0 through 100"):
        AssessmentEvidence(
            mission_id="chat",
            score=score,
            independent=True,
            modality="written_interaction",
            assessed_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
        )

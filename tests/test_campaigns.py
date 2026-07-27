from datetime import date

import pytest

from langcampaign.campaigns import CampaignChange, revise_campaign
from langcampaign.models import (
    CampaignType,
    CoachingStyle,
    CurriculumScope,
    Mission,
    new_campaign,
)


def test_style_and_scope_change_preserves_missions():
    original = new_campaign("Text friends", "French")
    original = original.with_missions((Mission("chat", "Casual chat"),))

    revision = revise_campaign(
        original,
        CampaignChange(
            coaching_style=CoachingStyle.DIRECT,
            curriculum_scope=CurriculumScope.FOUNDATIONAL,
        ),
    )

    assert revision.campaign.missions == original.missions
    assert revision.campaign.settings.coaching_style is CoachingStyle.DIRECT
    assert "Coaching style changed" in revision.effects


def test_switch_to_targeted_requires_date_and_confirmation():
    original = new_campaign("Read posts", "Japanese")

    with pytest.raises(ValueError, match="confirmation_required"):
        revise_campaign(
            original,
            CampaignChange(
                campaign_type=CampaignType.TARGETED,
                target_date=date(2026, 10, 1),
            ),
        )

    revision = revise_campaign(
        original,
        CampaignChange(
            campaign_type=CampaignType.TARGETED,
            target_date=date(2026, 10, 1),
            confirm_restructure=True,
        ),
    )
    assert revision.campaign.settings.target_date == date(2026, 10, 1)


def test_goal_date_and_time_changes_describe_their_effects():
    original = new_campaign(
        "Read posts",
        "Japanese",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 10, 1),
    )

    revision = revise_campaign(
        original,
        CampaignChange(
            goal="Discuss books",
            target_date=date(2026, 11, 1),
            expected_minutes_per_week=120,
            minimum_minutes_per_week=60,
        ),
    )

    assert revision.campaign.goal == "Discuss books"
    assert revision.campaign.settings.target_date == date(2026, 11, 1)
    assert revision.campaign.settings.expected_minutes_per_week == 120
    assert revision.campaign.settings.minimum_minutes_per_week == 60
    assert "Goal changed" in revision.effects
    assert "Target date changed; planning timeline will be recalculated." in revision.effects
    assert "Expected weekly time changed; planning workload will be recalculated." in revision.effects
    assert "Minimum weekly time changed; planning workload will be recalculated." in revision.effects


def test_flexible_campaign_rejects_target_date_change():
    original = new_campaign("Read posts", "Japanese")

    with pytest.raises(ValueError, match="target_date is only valid for targeted campaigns"):
        revise_campaign(
            original,
            CampaignChange(target_date=date(2026, 10, 1)),
        )


@pytest.mark.parametrize(
    ("change", "message"),
    (
        (CampaignChange(goal="  "), "goal must be non-empty"),
        (
            CampaignChange(expected_minutes_per_week=True),
            "expected_minutes_per_week must be a nonnegative integer",
        ),
        (
            CampaignChange(minimum_minutes_per_week=-1),
            "minimum_minutes_per_week must be a nonnegative integer",
        ),
        (
            CampaignChange(campaign_type=False),
            "campaign_type must be a CampaignType",
        ),
        (
            CampaignChange(curriculum_scope=""),
            "curriculum_scope must be a CurriculumScope",
        ),
        (
            CampaignChange(coaching_style=False),
            "coaching_style must be a CoachingStyle",
        ),
    ),
)
def test_revision_uses_domain_record_validation(change, message):
    original = new_campaign("Read posts", "Japanese")

    with pytest.raises(ValueError, match=message):
        revise_campaign(original, change)

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

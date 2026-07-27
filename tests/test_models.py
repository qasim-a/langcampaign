from datetime import date

import pytest

from langcampaign.models import (
    CampaignType,
    CoachingStyle,
    CurriculumScope,
    new_campaign,
)


def test_new_campaign_uses_flexible_balanced_supportive_defaults():
    campaign = new_campaign("Chat with friends", "Spanish")

    assert campaign.settings.campaign_type is CampaignType.FLEXIBLE
    assert campaign.settings.curriculum_scope is CurriculumScope.BALANCED
    assert campaign.settings.coaching_style is CoachingStyle.SUPPORTIVE
    assert campaign.settings.target_date is None


def test_targeted_campaign_requires_target_date():
    with pytest.raises(ValueError, match="target_date is required"):
        new_campaign(
            "Handle a hotel stay",
            "Spanish",
            campaign_type=CampaignType.TARGETED,
        )


def test_flexible_campaign_rejects_target_date():
    with pytest.raises(ValueError, match="target_date is only valid"):
        new_campaign(
            "Read social media",
            "Japanese",
            target_date=date(2026, 9, 1),
        )

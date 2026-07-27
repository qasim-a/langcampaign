from datetime import date, datetime, timezone

import pytest

from langcampaign.models import (
    Campaign,
    CampaignSettings,
    CampaignType,
    CoachingStyle,
    CurriculumScope,
    Mission,
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


@pytest.mark.parametrize(
    ("factory", "message"),
    (
        (lambda: Mission("", "Casual chat"), "mission id must be non-empty"),
        (lambda: Mission("chat", "  "), "mission title must be non-empty"),
        (
            lambda: Campaign(
                "",
                "Text friends",
                "Spanish",
                CampaignSettings(),
            ),
            "campaign id must be non-empty",
        ),
        (
            lambda: Campaign(
                "campaign",
                "  ",
                "Spanish",
                CampaignSettings(),
            ),
            "goal must be non-empty",
        ),
        (
            lambda: Campaign(
                "campaign",
                "Text friends",
                123,
                CampaignSettings(),
            ),
            "target_language must be non-empty",
        ),
    ),
)
def test_domain_records_reject_empty_or_non_string_identity_fields(
    factory,
    message,
):
    with pytest.raises(ValueError, match=message):
        factory()


@pytest.mark.parametrize("weight", (True, 0, -1, float("nan"), float("inf"), "1"))
def test_mission_rejects_non_finite_non_positive_or_non_numeric_weight(weight):
    with pytest.raises(ValueError, match="weight must be a finite positive number"):
        Mission("chat", "Casual chat", weight)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("expected_minutes_per_week", True),
        ("expected_minutes_per_week", 1.5),
        ("expected_minutes_per_week", -1),
        ("minimum_minutes_per_week", True),
        ("minimum_minutes_per_week", 1.5),
        ("minimum_minutes_per_week", -1),
    ),
)
def test_campaign_settings_reject_invalid_weekly_minutes(field, value):
    arguments = {field: value}

    with pytest.raises(
        ValueError,
        match=f"{field} must be a nonnegative integer",
    ):
        CampaignSettings(**arguments)


def test_campaign_settings_centralize_targeted_date_coupling():
    with pytest.raises(ValueError, match="target_date is required"):
        CampaignSettings(campaign_type=CampaignType.TARGETED)

    with pytest.raises(ValueError, match="target_date is only valid"):
        CampaignSettings(target_date=date(2026, 9, 1))

    with pytest.raises(ValueError, match="target_date must be a date"):
        CampaignSettings(
            campaign_type=CampaignType.TARGETED,
            target_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )


def test_campaign_rejects_naive_created_at():
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        Campaign(
            "campaign",
            "Text friends",
            "Spanish",
            CampaignSettings(),
            created_at=datetime(2026, 7, 27),
        )


def test_campaign_rejects_duplicate_mission_ids():
    with pytest.raises(ValueError, match="mission ids must be unique"):
        new_campaign("Text friends", "Spanish").with_missions(
            (
                Mission("chat", "Casual chat"),
                Mission("chat", "Handle replies"),
            )
        )


def test_campaign_rejects_mutable_or_invalid_mission_collections():
    mutable_missions = [Mission("chat", "Casual chat")]

    with pytest.raises(ValueError, match="missions must be a tuple"):
        Campaign(
            "campaign",
            "Text friends",
            "Spanish",
            CampaignSettings(),
            missions=mutable_missions,
        )

    with pytest.raises(ValueError, match="missions must contain Mission records"):
        Campaign(
            "campaign",
            "Text friends",
            "Spanish",
            CampaignSettings(),
            missions=("not a mission",),
        )

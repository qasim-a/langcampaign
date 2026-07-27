from dataclasses import replace
from datetime import date, datetime

import pytest

from langcampaign.forecasting import forecast_campaign
from langcampaign.models import CampaignType, new_campaign


def test_flexible_campaign_has_no_target_date_forecast():
    campaign = new_campaign("Read posts", "Japanese")

    assert forecast_campaign(
        campaign,
        readiness=40,
        minutes_studied=100,
        elapsed_days=7,
        today=date(2026, 7, 27),
    ) is None


def test_targeted_campaign_reports_risk_and_specific_time_recovery():
    campaign = new_campaign(
        "Handle a hotel stay",
        "Spanish",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 8, 10),
    )
    campaign = replace(
        campaign,
        settings=replace(campaign.settings, expected_minutes_per_week=200),
    )

    forecast = forecast_campaign(
        campaign,
        readiness=40,
        minutes_studied=100,
        elapsed_days=7,
        today=date(2026, 7, 27),
    )

    assert forecast.status == "at_risk"
    assert forecast.projected_readiness == 70
    assert forecast.recovery_actions[0].additional_minutes_per_week == 34


def test_at_risk_campaign_above_planned_pace_recommends_required_time_recovery():
    campaign = new_campaign(
        "Handle a hotel stay",
        "Spanish",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 8, 3),
    )
    campaign = replace(
        campaign,
        settings=replace(campaign.settings, expected_minutes_per_week=100),
    )

    forecast = forecast_campaign(
        campaign,
        readiness=40,
        minutes_studied=100,
        elapsed_days=7,
        today=date(2026, 7, 27),
    )

    assert forecast.status == "at_risk"
    assert forecast.recovery_actions[0].additional_minutes_per_week == 167


def test_at_risk_campaign_with_no_time_left_recommends_goal_or_date_change():
    campaign = new_campaign(
        "Handle a hotel stay",
        "Spanish",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 7, 27),
    )

    forecast = forecast_campaign(
        campaign,
        readiness=40,
        minutes_studied=100,
        elapsed_days=7,
        today=date(2026, 7, 27),
    )

    assert forecast.status == "at_risk"
    assert all(
        action.additional_minutes_per_week == 0
        for action in forecast.recovery_actions
    )
    assert forecast.recovery_actions[0].message == (
        "Narrow the goal or revise the target date because no time remains for "
        "a meaningful time recovery."
    )
    assert forecast.recovery_actions[1].message == (
        "Narrow optional context before removing mission-critical work."
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("readiness", True, "readiness must be an integer from 0 through 100"),
        ("readiness", 40.0, "readiness must be an integer from 0 through 100"),
        ("readiness", -1, "readiness must be an integer from 0 through 100"),
        ("readiness", 101, "readiness must be an integer from 0 through 100"),
        ("minutes_studied", True, "minutes_studied must be a nonnegative integer"),
        ("minutes_studied", 1.5, "minutes_studied must be a nonnegative integer"),
        ("minutes_studied", -1, "minutes_studied must be a nonnegative integer"),
        ("elapsed_days", True, "elapsed_days must be a nonnegative integer"),
        ("elapsed_days", 1.5, "elapsed_days must be a nonnegative integer"),
        ("elapsed_days", -1, "elapsed_days must be a nonnegative integer"),
        ("today", datetime(2026, 7, 27), "today must be a date"),
        ("today", "2026-07-27", "today must be a date"),
    ),
)
def test_forecast_rejects_invalid_runtime_inputs(field, value, message):
    campaign = new_campaign(
        "Handle a hotel stay",
        "Spanish",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 8, 10),
    )
    arguments = {
        "readiness": 40,
        "minutes_studied": 100,
        "elapsed_days": 7,
        "today": date(2026, 7, 27),
    }
    arguments[field] = value

    with pytest.raises(ValueError, match=message):
        forecast_campaign(campaign, **arguments)


def test_zero_elapsed_days_with_no_study_uses_zero_observed_weekly_pace():
    campaign = new_campaign(
        "Handle a hotel stay",
        "Spanish",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 8, 3),
    )

    forecast = forecast_campaign(
        campaign,
        readiness=40,
        minutes_studied=0,
        elapsed_days=0,
        today=date(2026, 7, 27),
    )

    assert forecast.assumed_minutes_per_week == 0
    assert forecast.projected_readiness == 40
    assert forecast.recovery_actions[0].additional_minutes_per_week == 267


def test_zero_elapsed_days_rejects_study_time_without_an_observation_window():
    campaign = new_campaign(
        "Handle a hotel stay",
        "Spanish",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 8, 3),
    )

    with pytest.raises(
        ValueError,
        match="minutes_studied must be zero when elapsed_days is zero",
    ):
        forecast_campaign(
            campaign,
            readiness=40,
            minutes_studied=1,
            elapsed_days=0,
            today=date(2026, 7, 27),
        )


def test_current_readiness_at_target_is_reported_as_target_met():
    campaign = new_campaign(
        "Handle a hotel stay",
        "Spanish",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 8, 3),
    )

    forecast = forecast_campaign(
        campaign,
        readiness=80,
        minutes_studied=0,
        elapsed_days=7,
        today=date(2026, 7, 27),
    )

    assert forecast.status == "target_met"
    assert forecast.projected_readiness == 80
    assert forecast.recovery_actions == ()


def test_projected_readiness_at_target_boundary_is_on_track():
    campaign = new_campaign(
        "Handle a hotel stay",
        "Spanish",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 8, 3),
    )

    forecast = forecast_campaign(
        campaign,
        readiness=50,
        minutes_studied=200,
        elapsed_days=7,
        today=date(2026, 7, 27),
    )

    assert forecast.status == "on_track"
    assert forecast.projected_readiness == 80
    assert forecast.recovery_actions == ()


def test_implausible_required_pace_recommends_goal_or_date_change():
    campaign = new_campaign(
        "Handle a hotel stay",
        "Spanish",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 7, 28),
    )

    forecast = forecast_campaign(
        campaign,
        readiness=0,
        minutes_studied=0,
        elapsed_days=7,
        today=date(2026, 7, 27),
    )

    assert forecast.status == "at_risk"
    assert all(
        action.additional_minutes_per_week == 0
        for action in forecast.recovery_actions
    )
    assert "Narrow the goal or revise the target date" in (
        forecast.recovery_actions[0].message
    )
    assert "3734" not in "\n".join(
        action.message for action in forecast.recovery_actions
    )

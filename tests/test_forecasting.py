from dataclasses import replace
from datetime import date

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
    assert forecast.recovery_actions[0].additional_minutes_per_week == 100

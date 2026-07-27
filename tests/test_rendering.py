from dataclasses import replace

from langcampaign.assessment import ReadinessResult
from langcampaign.forecasting import Forecast
from langcampaign.models import CoachingStyle, new_campaign
from langcampaign.rendering import ProgressReport, render_progress


def report_for(style):
    campaign = new_campaign("Text friends", "Spanish")
    campaign = replace(
        campaign,
        settings=replace(campaign.settings, coaching_style=style),
    )
    return ProgressReport(
        campaign=campaign,
        readiness=ReadinessResult(59, ("chat",), ("replies",)),
        forecast=None,
        completed_minutes=120,
        planned_minutes=300,
        demonstrated=("Casual greeting",),
        developing=("Unexpected replies",),
        next_action="Practice a 10-minute group-chat simulation.",
    )


def test_supportive_report_is_expressive_and_labels_emoji():
    output = render_progress(report_for(CoachingStyle.SUPPORTIVE))

    assert "🌟 Great work" in output
    assert "mission complete" not in output
    assert "✅ Demonstrated: Casual greeting" in output
    assert "🟡 Developing: Unexpected replies" in output


def test_direct_report_is_compact_without_celebration():
    output = render_progress(report_for(CoachingStyle.DIRECT))

    assert "MISSION REPORT" in output
    assert "Great work" not in output
    assert len(output.splitlines()) <= 10


def test_boot_camp_report_emphasizes_next_action():
    output = render_progress(report_for(CoachingStyle.BOOT_CAMP))

    assert "MISSION CHECK" in output
    assert "NEXT ACTION" in output


def test_report_renders_training_progress_separately_from_readiness_and_forecast():
    report = replace(
        report_for(CoachingStyle.DIRECT),
        forecast=Forecast(72, "at_risk", 120, ()),
    )

    output = render_progress(report)

    assert "Readiness" in output
    assert "59%" in output
    assert "Training completed [████████░░░░░░░░░░░░] 120/300 min (40%)" in output
    assert "Forecast: 72% (at risk)" in output


def test_report_renders_zero_planned_training_minutes_without_division_error():
    report = replace(
        report_for(CoachingStyle.DIRECT),
        completed_minutes=0,
        planned_minutes=0,
    )

    output = render_progress(report)

    assert "Training completed [░░░░░░░░░░░░░░░░░░░░] 0/0 min (0%)" in output

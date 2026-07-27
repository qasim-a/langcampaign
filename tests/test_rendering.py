from dataclasses import replace

from langcampaign.assessment import ReadinessResult
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

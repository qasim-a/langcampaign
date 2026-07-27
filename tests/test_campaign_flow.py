from datetime import date, datetime, timezone

import langcampaign
from langcampaign.assessment import (
    AssessmentEvidence,
    calculate_readiness,
    summarize_cefr,
)
from langcampaign.forecasting import forecast_campaign
from langcampaign.models import CampaignType, Mission, new_campaign
from langcampaign.rendering import ProgressReport, render_progress
from langcampaign.storage import (
    CampaignState,
    load_campaign,
    load_campaign_state,
    save_campaign_state,
)


def test_targeted_campaign_flow(tmp_path):
    expected_exports = {
        "AssessmentScenario",
        "CampaignRoadmap",
        "Campaign",
        "CampaignState",
        "CampaignType",
        "CoachingStyle",
        "CurriculumScope",
        "MissionPlan",
        "MissionPriority",
        "PracticeActivity",
        "RoadmapPhase",
        "calculate_readiness",
        "forecast_campaign",
        "load_campaign",
        "load_campaign_state",
        "new_campaign",
        "render_progress",
        "revise_campaign",
        "save_campaign",
        "save_campaign_state",
        "summarize_cefr",
    }
    public_api = (
        langcampaign.new_campaign,
        langcampaign.revise_campaign,
        langcampaign.calculate_readiness,
        langcampaign.summarize_cefr,
        langcampaign.forecast_campaign,
        langcampaign.save_campaign,
        langcampaign.load_campaign,
        langcampaign.load_campaign_state,
        langcampaign.render_progress,
        langcampaign.save_campaign_state,
    )
    assert expected_exports <= set(langcampaign.__all__)
    assert all(callable(entry) for entry in public_api)

    campaign = new_campaign(
        "Handle a hotel stay",
        "Spanish",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 8, 10),
    ).with_missions(
        (
            Mission("hotel", "Hotel check-in", 2.0),
            Mission("replies", "Handle an unexpected reply"),
        )
    )
    evidence = (
        AssessmentEvidence(
            "hotel",
            80,
            True,
            "written_interaction",
            datetime(2026, 7, 27, tzinfo=timezone.utc),
            "A2",
        ),
        AssessmentEvidence(
            "replies",
            65,
            True,
            "written_interaction",
            datetime(2026, 7, 27, 13, tzinfo=timezone.utc),
            "A2",
        ),
    )
    readiness = calculate_readiness(campaign, evidence)
    cefr_summary = summarize_cefr(evidence, "written_interaction")
    forecast = forecast_campaign(
        campaign,
        readiness=readiness.percent,
        minutes_studied=100,
        elapsed_days=7,
        today=date(2026, 7, 27),
    )
    output = render_progress(
        ProgressReport(
            campaign,
            readiness,
            forecast,
            100,
            300,
            ("Hotel check-in",),
            (),
            "Practice an unfamiliar reply.",
        )
    )
    path = tmp_path / "campaign-state.json"
    save_campaign_state(path, CampaignState(campaign, evidence))
    loaded_state = load_campaign_state(path)
    reloaded_readiness = calculate_readiness(
        loaded_state.campaign,
        loaded_state.assessment_evidence,
    )
    reloaded_cefr_summary = summarize_cefr(
        loaded_state.assessment_evidence,
        "written_interaction",
    )

    assert "Readiness" in output
    assert loaded_state == CampaignState(campaign, evidence)
    assert load_campaign(path) == campaign
    assert reloaded_readiness == readiness
    assert reloaded_cefr_summary == cefr_summary
    assert reloaded_cefr_summary == (
        "You demonstrated approximately A2 written interaction "
        "across 2 independent assessments."
    )

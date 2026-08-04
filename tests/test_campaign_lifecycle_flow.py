from dataclasses import replace
from datetime import datetime, timezone

from langcampaign.assessment import AssessmentEvidence
from langcampaign.cli import run_command
from langcampaign.learners import campaign_state_path, save_learner_campaign, select_campaign
from tests.fixtures import setup_payload


def _transition_payload(source_campaign_id: str) -> dict:
    payload = setup_payload()
    payload["campaign"].update(
        {
            "id": "read-posts",
            "goal": "Read casual Spanish posts",
            "missions": [{"id": "read-post", "title": "Read a casual post"}],
        }
    )
    payload["mission_plans"][0].update(
        {"id": "read-post", "title": "Read a casual post"}
    )
    payload["roadmap"]["phases"][0]["mission_ids"] = ["read-post"]
    payload["source_campaign_id"] = source_campaign_id
    payload["evidence_transfers"] = [
        {"source_mission_id": "delayed-arrival", "target_mission_id": "read-post"}
    ]
    return payload


def test_defaulted_setup_transition_and_resume_preserve_campaign_states(tmp_path):
    setup = run_command("setup", setup_payload(), tmp_path)
    source_campaign_id = setup.data["campaign_id"]
    source = select_campaign(tmp_path, "Qasim Ali", source_campaign_id)
    evidence = AssessmentEvidence(
        "delayed-arrival",
        91,
        True,
        "written_interaction",
        datetime(2026, 8, 3, tzinfo=timezone.utc),
        "A2",
    )
    source = replace(source, assessment_evidence=(evidence,))
    source_path = save_learner_campaign(tmp_path, source)
    source_bytes = source_path.read_bytes()

    transitioned = run_command(
        "transition-campaign", _transition_payload(source_campaign_id), tmp_path
    )
    target_campaign_id = transitioned.data["active_campaign_id"]
    target_path = campaign_state_path(tmp_path, "Qasim Ali", target_campaign_id)
    target_bytes = target_path.read_bytes()

    statuses = run_command(
        "list-campaign-status", {"learner_id": "Qasim Ali"}, tmp_path
    )
    resumed = run_command(
        "resume-campaign",
        {"learner_id": "Qasim Ali", "campaign_id": source_campaign_id},
        tmp_path,
    )

    assert setup.success is True
    assert transitioned.to_dict() == {
        "success": True,
        "data": {"active_campaign_id": target_campaign_id},
    }
    assert statuses.to_dict() == {
        "success": True,
        "data": {
            "campaigns": [
                {
                    "id": source_campaign_id,
                    "goal": "Handle a delayed hotel arrival",
                    "status": "paused",
                },
                {
                    "id": target_campaign_id,
                    "goal": "Read casual Spanish posts",
                    "status": "active",
                },
            ]
        },
    }
    assert select_campaign(tmp_path, "Qasim Ali", target_campaign_id).assessment_evidence == (
        replace(evidence, mission_id="read-post"),
    )
    assert resumed.to_dict() == {
        "success": True,
        "data": {"active_campaign_id": source_campaign_id},
    }
    assert source_path.read_bytes() == source_bytes
    assert target_path.read_bytes() == target_bytes

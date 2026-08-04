import langcampaign.cli as cli
from langcampaign.cli import run_command
from tests.fixtures import setup_payload


def test_setup_persists_hidden_roadmap_and_subsequent_command_can_reveal_summary(tmp_path):
    created = run_command("setup", setup_payload(), tmp_path)
    campaign_id = created.data["campaign_id"]
    assert created.to_dict() == {
        "success": True,
        "data": {
            "learner_id": "qasim-ali",
            "campaign_id": campaign_id,
            "next_priorities": ["Explain a delayed arrival"],
            "first_mission_id": "delayed-arrival",
        },
    }

    learner_id = created.data["learner_id"]
    resumed = run_command(
        "validate-state",
        {"learner_id": learner_id, "campaign_id": campaign_id},
        tmp_path,
    )
    listed = run_command("list-campaigns", {"learner_id": learner_id}, tmp_path)
    revealed = run_command(
        "show-roadmap",
        {"learner_id": learner_id, "campaign_id": campaign_id},
        tmp_path,
    )

    assert resumed.to_dict() == {
        "success": True,
        "data": {"valid": True, "campaign_id": campaign_id},
    }
    assert listed.to_dict() == {
        "success": True,
        "data": {
            "campaigns": [
                {"id": campaign_id, "goal": "Handle a delayed hotel arrival"}
            ]
        },
    }
    for normal in (created, resumed, listed):
        assert "roadmap" not in normal.to_dict().get("data", {})
        assert "assumptions" not in normal.to_dict().get("data", {})
    assert tuple(cli.COMMANDS) == (
        "setup",
        "list-campaigns",
        "validate-state",
        "validate-mission-map",
        "show-roadmap",
    )
    assert revealed.to_dict() == {
        "success": True,
        "data": {
            "summary": "CAMPAIGN ROADMAP\n"
            "- Core hotel exchanges (current): Handle routine hotel communication."
        },
    }

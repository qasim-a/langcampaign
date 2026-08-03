from langcampaign.cli import run_command
from tests.fixtures import setup_payload


def test_setup_persists_hidden_roadmap_and_subsequent_command_can_reveal_summary(tmp_path):
    created = run_command("setup", setup_payload(), tmp_path)
    assert created.success is True

    learner_id = created.data["learner_id"]
    campaign_id = created.data["campaign_id"]
    resumed = run_command(
        "validate-state",
        {"learner_id": learner_id, "campaign_id": campaign_id},
        tmp_path,
    )
    revealed = run_command(
        "show-roadmap",
        {"learner_id": learner_id, "campaign_id": campaign_id},
        tmp_path,
    )

    assert resumed.data == {"valid": True, "campaign_id": campaign_id}
    assert "Core hotel exchanges (current)" in revealed.data["summary"]
    assert "The learner reads Latin script" not in revealed.data["summary"]

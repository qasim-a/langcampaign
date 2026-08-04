from langcampaign.cli import COMMANDS, run_command
from tests.fixtures import mission_content_payload, setup_payload


def test_runtime_commands_are_registered_and_support_resumable_flow(tmp_path):
    assert len(COMMANDS) == 15
    setup = run_command("setup", setup_payload(), tmp_path)
    assert setup.success
    identity = {"learner_id": "qasim-ali", "campaign_id": setup.data["campaign_id"]}
    content = mission_content_payload()
    validation = run_command("validate-mission-content", {"content": content}, tmp_path)
    assert validation.to_dict()["data"]["valid"] is True
    status = run_command("mission-status", identity, tmp_path)
    assert status.data["session"] is None
    started = run_command("start-mission", {**identity, "expected_revision": 0, "mission_id": "delayed-arrival", "content": content}, tmp_path)
    assert started.data["session"]["checkpoint"] == "teaching"
    run_command("advance-mission", {**identity, "expected_revision": 1, "mission_id": "delayed-arrival", "attempt_number": 1}, tmp_path)
    run_command("advance-mission", {**identity, "expected_revision": 2, "mission_id": "delayed-arrival", "attempt_number": 1}, tmp_path)
    assessed = run_command("submit-assessment", {**identity, "expected_revision": 3, "mission_id": "delayed-arrival", "attempt_number": 1, "criterion_scores": [{"criterion_id": "delay", "score": 80}, {"criterion_id": "time", "score": 80}], "independent": True, "modality": "text", "result_statement": "Clear reply"}, tmp_path)
    assert assessed.success
    assert assessed.data["session"]["checkpoint"] == "assessed"
    assert run_command("mission-status", identity, tmp_path).data["revision"] == 4

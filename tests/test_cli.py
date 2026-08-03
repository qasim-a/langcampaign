import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import langcampaign.cli as cli
from langcampaign.cli import run_command
from langcampaign.learners import save_learner_campaign, select_campaign
from langcampaign.storage import CampaignState
from tests.fixtures import setup_payload


def _module_environment():
    source_root = Path(__file__).parents[1] / "src"
    return {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            filter(None, (str(source_root), os.environ.get("PYTHONPATH")))
        ),
    }


def test_setup_writes_valid_state_and_returns_next_priorities(tmp_path):
    result = run_command("setup", setup_payload(), tmp_path)

    assert result.success is True
    assert result.data["learner_id"] == "qasim-ali"
    assert result.data["next_priorities"] == ["Explain a delayed arrival"]
    assert result.data["first_mission_id"] == "delayed-arrival"
    assert list(tmp_path.glob("qasim-ali/*/state.json"))


def test_setup_first_mission_uses_active_phase_priority_not_payload_order(tmp_path):
    payload = setup_payload()
    supporting = payload["mission_plans"][0]
    supporting["priority"] = "supporting"
    critical = {**supporting, "id": "hotel-check-in", "title": "Check in"}
    critical["priority"] = "critical"
    payload["campaign"]["missions"].append(
        {"id": "hotel-check-in", "title": "Check in", "weight": 1.0}
    )
    payload["mission_plans"].append(critical)
    payload["roadmap"]["phases"][0]["mission_ids"].append("hotel-check-in")

    result = run_command("setup", payload, tmp_path)

    assert result.success is True
    assert result.data["first_mission_id"] == "hotel-check-in"
    assert result.data["next_priorities"] == ["Check in", "Explain a delayed arrival"]


def test_invalid_setup_leaves_no_partial_state(tmp_path):
    payload = setup_payload()
    payload["mission_plans"][0]["priority"] = "unknown"

    result = run_command("setup", payload, tmp_path)

    assert result.success is False
    assert "priority" in result.error
    assert list(tmp_path.rglob("state.json")) == []


def test_empty_active_phase_leaves_no_partial_state(tmp_path):
    payload = setup_payload()
    payload["roadmap"]["phases"][0]["mission_ids"] = []

    result = run_command("setup", payload, tmp_path)

    assert result.success is False
    assert result.error == "active roadmap phase has no missions"
    assert list(tmp_path.rglob("state.json")) == []


def test_command_errors_have_a_stable_failure_envelope(tmp_path):
    result = run_command("unknown-command", [], tmp_path)

    assert result.to_dict() == {
        "success": False,
        "error": "unknown command: unknown-command",
    }


def test_list_campaigns_returns_saved_campaigns(tmp_path):
    setup = run_command("setup", setup_payload(), tmp_path)

    result = run_command("list-campaigns", {"learner_id": "Qasim Ali"}, tmp_path)

    assert result.to_dict() == {
        "success": True,
        "data": {
            "campaigns": [
                {
                    "id": setup.data["campaign_id"],
                    "goal": "Handle a delayed hotel arrival",
                }
            ]
        },
    }


def test_list_campaigns_rejects_a_missing_learner_id(tmp_path):
    result = run_command("list-campaigns", {}, tmp_path)

    assert result.to_dict() == {
        "success": False,
        "error": "missing field: learner_id",
    }


def test_validate_state_returns_the_selected_campaign_id(tmp_path):
    setup = run_command("setup", setup_payload(), tmp_path)

    result = run_command(
        "validate-state",
        {"learner_id": "Qasim Ali", "campaign_id": setup.data["campaign_id"]},
        tmp_path,
    )

    assert result.to_dict() == {
        "success": True,
        "data": {"valid": True, "campaign_id": setup.data["campaign_id"]},
    }


def test_validate_state_returns_a_failure_for_an_unknown_campaign(tmp_path):
    result = run_command(
        "validate-state",
        {"learner_id": "Qasim Ali", "campaign_id": "missing"},
        tmp_path,
    )

    assert result.to_dict() == {
        "success": False,
        "error": "campaign does not exist",
    }


def test_validate_mission_map_accepts_matching_missions_and_plans(tmp_path):
    payload = setup_payload()

    result = run_command(
        "validate-mission-map",
        {"missions": payload["campaign"]["missions"], "mission_plans": payload["mission_plans"]},
        tmp_path,
    )

    assert result.to_dict() == {"success": True, "data": {"valid": True}}


def test_validate_mission_map_returns_a_failure_for_malformed_plans(tmp_path):
    payload = setup_payload()
    payload["mission_plans"][0]["assessment"] = []

    result = run_command(
        "validate-mission-map",
        {"missions": payload["campaign"]["missions"], "mission_plans": payload["mission_plans"]},
        tmp_path,
    )

    assert result.success is False
    assert result.error


def test_show_roadmap_returns_the_selected_campaign_summary(tmp_path):
    setup = run_command("setup", setup_payload(), tmp_path)

    result = run_command(
        "show-roadmap",
        {"learner_id": "Qasim Ali", "campaign_id": setup.data["campaign_id"]},
        tmp_path,
    )

    assert result.to_dict() == {
        "success": True,
        "data": {
            "summary": "CAMPAIGN ROADMAP\n"
            "- Core hotel exchanges (current): Handle routine hotel communication."
        },
    }


def test_show_roadmap_returns_a_failure_when_campaign_has_no_roadmap(tmp_path):
    setup = run_command("setup", setup_payload(), tmp_path)
    state = select_campaign(tmp_path, "Qasim Ali", setup.data["campaign_id"])
    save_learner_campaign(
        tmp_path,
        CampaignState(
            campaign=state.campaign,
            learner_id=state.learner_id,
            mission_plans=state.mission_plans,
        ),
    )

    result = run_command(
        "show-roadmap",
        {"learner_id": "Qasim Ali", "campaign_id": setup.data["campaign_id"]},
        tmp_path,
    )

    assert result.to_dict() == {
        "success": False,
        "error": "campaign has no roadmap",
    }


@pytest.mark.parametrize("error_type", (AttributeError, TypeError))
def test_run_command_does_not_hide_a_handler_programmer_error(
    tmp_path, monkeypatch, error_type
):
    def broken_handler(payload, learners_root):
        del payload, learners_root
        raise error_type("programmer fault")

    monkeypatch.setitem(cli.COMMANDS, "list-campaigns", broken_handler)

    with pytest.raises(error_type, match="programmer fault"):
        run_command("list-campaigns", {"learner_id": "Qasim Ali"}, tmp_path)


def test_module_entrypoint_returns_json_envelope(tmp_path):
    completed = subprocess.run(
        [sys.executable, "-m", "langcampaign", "setup", "--learners-root", str(tmp_path)],
        input=json.dumps(setup_payload()),
        text=True,
        capture_output=True,
        check=False,
        env=_module_environment(),
    )
    envelope = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert envelope["success"] is True
    assert completed.stderr == ""


def test_module_entrypoint_returns_one_json_error_envelope(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "langcampaign",
            "validate-mission-map",
            "--learners-root",
            str(tmp_path),
        ],
        input="[]",
        text=True,
        capture_output=True,
        check=False,
        env=_module_environment(),
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout) == {
        "success": False,
        "error": "command input must be a JSON object",
    }
    assert completed.stdout.count("\n") == 1


def test_module_entrypoint_returns_one_json_envelope_for_malformed_json(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "langcampaign",
            "list-campaigns",
            "--learners-root",
            str(tmp_path),
        ],
        input="{not-json",
        text=True,
        capture_output=True,
        check=False,
        env=_module_environment(),
    )

    envelope = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert envelope["success"] is False
    assert envelope["error"]
    assert completed.stdout.count("\n") == 1

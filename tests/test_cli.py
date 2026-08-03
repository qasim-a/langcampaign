import json
import os
import subprocess
import sys
from pathlib import Path

from langcampaign.cli import run_command
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

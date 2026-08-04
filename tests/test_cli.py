import json
import io
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

import langcampaign.cli as cli
from langcampaign.assessment import AssessmentEvidence
from langcampaign.cli import run_command
from langcampaign.learners import save_learner_campaign, select_campaign
from langcampaign.models import CampaignType, CoachingStyle, CurriculumScope
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


def test_setup_silently_applies_defaults_and_stores_prior_knowledge(tmp_path):
    payload = setup_payload()

    result = run_command("setup", payload, tmp_path)
    state = select_campaign(tmp_path, "Qasim Ali", result.data["campaign_id"])

    assert result.success is True
    assert state.campaign.settings.campaign_type is CampaignType.FLEXIBLE
    assert state.campaign.settings.curriculum_scope is CurriculumScope.BALANCED
    assert state.campaign.settings.coaching_style is CoachingStyle.SUPPORTIVE
    assert state.prior_knowledge == "Can read casual messages but rarely speaks."


def test_setup_target_date_alone_selects_a_targeted_campaign(tmp_path):
    payload = setup_payload()
    payload["campaign"]["target_date"] = "2026-10-01"

    result = run_command("setup", payload, tmp_path)

    assert result.success is True
    assert select_campaign(
        tmp_path, "Qasim Ali", result.data["campaign_id"]
    ).campaign.settings.campaign_type is CampaignType.TARGETED


@pytest.mark.parametrize("value", (None, 0, [], {}))
def test_setup_rejects_non_string_prior_knowledge(tmp_path, value):
    payload = setup_payload()
    payload["prior_knowledge"] = value

    result = run_command("setup", payload, tmp_path)

    assert result.to_dict() == {
        "success": False,
        "error": "prior_knowledge must be a string",
    }


def test_setup_returns_a_json_failure_for_an_invalid_legacy_campaign_type(tmp_path):
    payload = setup_payload()
    payload["campaign"]["campaign_type"] = "not-a-type"

    result = run_command("setup", payload, tmp_path)

    assert result.to_dict() == {
        "success": False,
        "error": "'not-a-type' is not a valid campaign type",
    }


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


def test_setup_places_a_supporting_prerequisite_before_its_critical_dependent(tmp_path):
    payload = setup_payload()
    prerequisite = payload["mission_plans"][0]
    prerequisite["id"] = "supporting-prerequisite"
    prerequisite["title"] = "Handle a supporting exchange"
    prerequisite["priority"] = "supporting"
    dependent = {
        **prerequisite,
        "id": "critical-dependent",
        "title": "Handle the critical exchange",
        "priority": "critical",
        "prerequisite_ids": ["supporting-prerequisite"],
    }
    payload["campaign"]["missions"] = [
        {"id": "supporting-prerequisite", "title": prerequisite["title"]},
        {"id": "critical-dependent", "title": dependent["title"]},
    ]
    payload["mission_plans"] = [prerequisite, dependent]
    payload["roadmap"]["phases"][0]["mission_ids"] = [
        "critical-dependent",
        "supporting-prerequisite",
    ]

    result = run_command("setup", payload, tmp_path)

    assert result.to_dict()["data"]["first_mission_id"] == "supporting-prerequisite"
    assert result.to_dict()["data"]["next_priorities"] == [
        "Handle a supporting exchange",
        "Handle the critical exchange",
    ]


@pytest.mark.parametrize("invalid_roadmap", ("omitted-plan", "later-prerequisite"))
def test_setup_rejects_invalid_roadmap_coverage_or_phase_placement(
    tmp_path, invalid_roadmap
):
    payload = setup_payload()
    prerequisite = payload["mission_plans"][0]
    prerequisite["id"] = "supporting-prerequisite"
    prerequisite["priority"] = "supporting"
    dependent = {
        **prerequisite,
        "id": "critical-dependent",
        "title": "Handle the critical exchange",
        "priority": "critical",
        "prerequisite_ids": ["supporting-prerequisite"],
    }
    payload["campaign"]["missions"] = [
        {"id": "supporting-prerequisite", "title": prerequisite["title"]},
        {"id": "critical-dependent", "title": dependent["title"]},
    ]
    payload["mission_plans"] = [prerequisite, dependent]
    payload["roadmap"]["phases"][0]["mission_ids"] = ["critical-dependent"]
    if invalid_roadmap == "later-prerequisite":
        payload["roadmap"]["phases"].append(
            {
                "id": "later-support",
                "title": "Later support",
                "capability_summary": "Build prerequisite support.",
                "mission_ids": ["supporting-prerequisite"],
                "planned_review_after": False,
                "planned_simulation_after": False,
            }
        )

    result = run_command("setup", payload, tmp_path)

    assert result.success is False
    assert list(tmp_path.rglob("state.json")) == []


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


def test_setup_does_not_hide_a_save_dependency_value_error(tmp_path, monkeypatch):
    def broken_save(*args, **kwargs):
        del args, kwargs
        raise ValueError("save programmer fault")

    monkeypatch.setattr(cli, "create_and_activate_campaign", broken_save)

    with pytest.raises(ValueError, match="save programmer fault"):
        run_command("setup", setup_payload(), tmp_path)


def test_list_does_not_hide_a_repository_dependency_value_error(tmp_path, monkeypatch):
    def broken_list(*args, **kwargs):
        del args, kwargs
        raise ValueError("list programmer fault")

    monkeypatch.setattr(cli, "list_learner_campaigns", broken_list)

    with pytest.raises(ValueError, match="list programmer fault"):
        run_command("list-campaigns", {"learner_id": "Qasim Ali"}, tmp_path)


def test_selection_does_not_hide_a_repository_dependency_value_error(
    tmp_path, monkeypatch
):
    def broken_select(*args, **kwargs):
        del args, kwargs
        raise ValueError("select programmer fault")

    monkeypatch.setattr(cli, "select_campaign", broken_select)

    with pytest.raises(ValueError, match="select programmer fault"):
        run_command("validate-state", {"learner_id": "Qasim Ali"}, tmp_path)


def test_setup_is_create_only_and_preserves_existing_state_and_evidence(tmp_path):
    payload = setup_payload()
    payload["campaign"]["id"] = "hotel-arrival"
    created = run_command("setup", payload, tmp_path)
    original = select_campaign(tmp_path, "Qasim Ali", "hotel-arrival")
    evidence = AssessmentEvidence(
        "delayed-arrival",
        91,
        True,
        "written_interaction",
        datetime(2026, 8, 3, tzinfo=timezone.utc),
        "A2",
    )
    with_evidence = replace(original, assessment_evidence=(evidence,))
    path = save_learner_campaign(tmp_path, with_evidence)
    original_bytes = path.read_bytes()

    duplicate = run_command("setup", payload, tmp_path)

    assert created.success is True
    assert duplicate.to_dict() == {
        "success": False,
        "error": "campaign already exists",
    }
    assert path.read_bytes() == original_bytes
    assert select_campaign(tmp_path, "Qasim Ali", "hotel-arrival") == with_evidence


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


def test_module_entrypoint_returns_one_json_envelope_for_invalid_campaign_type(tmp_path):
    payload = setup_payload()
    payload["campaign"]["campaign_type"] = "not-a-type"
    completed = subprocess.run(
        [sys.executable, "-m", "langcampaign", "setup", "--learners-root", str(tmp_path)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        env=_module_environment(),
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout) == {
        "success": False,
        "error": "'not-a-type' is not a valid campaign type",
    }
    assert completed.stdout.count("\n") == 1
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


def test_main_does_not_hide_a_handler_value_error(tmp_path, monkeypatch):
    def broken_handler(payload, learners_root):
        del payload, learners_root
        raise ValueError("handler programmer fault")

    monkeypatch.setitem(cli.COMMANDS, "list-campaigns", broken_handler)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("{}"))

    with pytest.raises(ValueError, match="handler programmer fault"):
        cli.main(
            ["list-campaigns", "--learners-root", str(tmp_path)]
        )


@pytest.mark.parametrize(
    "arguments",
    [
        ["unknown", "--learners-root", "ROOT"],
        ["list-campaigns"],
        ["list-campaigns", "--learners-root"],
        ["list-campaigns", "--learners-root", "ROOT", "--unknown-option"],
    ],
)
def test_argparse_invocation_errors_return_exactly_one_json_envelope(
    tmp_path, arguments
):
    resolved = [str(tmp_path) if item == "ROOT" else item for item in arguments]
    completed = subprocess.run(
        [sys.executable, "-m", "langcampaign", *resolved],
        input="{}",
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
    assert completed.stderr == ""


def test_command_boundary_exposes_exactly_the_five_foundation_commands():
    assert tuple(cli.COMMANDS) == (
        "setup",
        "list-campaigns",
        "validate-state",
        "validate-mission-map",
        "show-roadmap",
        "list-campaign-status",
        "transition-campaign",
        "resume-campaign",
        "complete-campaign",
    )


def test_lifecycle_commands_return_their_stable_success_envelopes(tmp_path):
    created = run_command("setup", setup_payload(), tmp_path)
    campaign_id = created.data["campaign_id"]

    statuses = run_command(
        "list-campaign-status", {"learner_id": "Qasim Ali"}, tmp_path
    )
    completed = run_command(
        "complete-campaign",
        {"learner_id": "Qasim Ali", "campaign_id": campaign_id},
        tmp_path,
    )

    assert statuses.to_dict() == {
        "success": True,
        "data": {
            "campaigns": [
                {
                    "id": campaign_id,
                    "goal": "Handle a delayed hotel arrival",
                    "status": "active",
                }
            ]
        },
    }
    assert completed.to_dict() == {
        "success": True,
        "data": {"completed_campaign_id": campaign_id},
    }


def _transition_payload(source_campaign_id, learner_id="Qasim Ali"):
    payload = setup_payload()
    payload["learner_id"] = learner_id
    payload["campaign"]["id"] = "new-campaign"
    payload["source_campaign_id"] = source_campaign_id
    payload["evidence_transfers"] = []
    return payload


def test_transition_command_returns_error_envelopes_for_missing_and_invalid_inputs(tmp_path):
    created = run_command("setup", setup_payload(), tmp_path)
    source_campaign_id = created.data["campaign_id"]

    missing = run_command("transition-campaign", setup_payload(), tmp_path)
    mismatched = run_command(
        "transition-campaign",
        _transition_payload(source_campaign_id, "Other Learner"),
        tmp_path,
    )
    duplicate = _transition_payload(source_campaign_id)
    duplicate["evidence_transfers"] = [
        {"source_mission_id": "delayed-arrival", "target_mission_id": "delayed-arrival"},
        {"source_mission_id": "delayed-arrival", "target_mission_id": "delayed-arrival"},
    ]
    duplicate_result = run_command("transition-campaign", duplicate, tmp_path)
    invalid = _transition_payload(source_campaign_id)
    invalid["evidence_transfers"] = [
        {"source_mission_id": "missing", "target_mission_id": "delayed-arrival"}
    ]
    invalid_result = run_command("transition-campaign", invalid, tmp_path)

    assert missing.success is False
    assert mismatched.success is False
    assert duplicate_result.to_dict() == {
        "success": False,
        "error": "duplicate source mission mapping",
    }
    assert invalid_result.to_dict() == {
        "success": False,
        "error": "source mission does not exist",
    }


def test_completed_campaign_cannot_be_resumed_through_the_command_boundary(tmp_path):
    created = run_command("setup", setup_payload(), tmp_path)
    campaign_id = created.data["campaign_id"]
    run_command(
        "complete-campaign",
        {"learner_id": "Qasim Ali", "campaign_id": campaign_id},
        tmp_path,
    )

    result = run_command(
        "resume-campaign",
        {"learner_id": "Qasim Ali", "campaign_id": campaign_id},
        tmp_path,
    )

    assert result.to_dict() == {
        "success": False,
        "error": "completed campaigns cannot be activated",
    }


def test_transition_command_does_not_hide_a_dependency_programmer_fault(
    tmp_path, monkeypatch
):
    created = run_command("setup", setup_payload(), tmp_path)

    def broken_transition(*args, **kwargs):
        del args, kwargs
        raise ValueError("transition programmer fault")

    monkeypatch.setattr(cli, "transition_campaign", broken_transition)

    with pytest.raises(ValueError, match="transition programmer fault"):
        run_command(
            "transition-campaign", _transition_payload(created.data["campaign_id"]), tmp_path
        )

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

from .learners import (
    LearnerRepositoryError,
    EvidenceTransfer,
    activate_campaign,
    complete_campaign,
    create_and_activate_campaign,
    list_learner_campaigns,
    list_campaign_summaries,
    normalize_learner_id,
    select_active_campaign,
    select_campaign,
    transition_campaign,
)
from .missions import validate_mission_map
from .models import (
    Campaign,
    CampaignSettings,
    CampaignType,
    CoachingStyle,
    CurriculumScope,
    Mission,
)
from .roadmaps import next_priority_ids, render_roadmap_summary, validate_roadmap
from .storage import (
    CampaignState,
    CampaignStorageError,
    mission_plan_from_dict,
    roadmap_from_dict,
)


@dataclass(frozen=True)
class CommandResult:
    success: bool
    data: dict | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        result = {"success": self.success}
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        return result


class CommandInputError(ValueError):
    """An expected command payload, parser, or domain validation failure."""


def _input_error(error: ValueError) -> CommandInputError:
    return CommandInputError(
        str(error).replace("MissionPriority", "mission priority")
    )


class _CommandArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        envelope = CommandResult(False, error=message)
        print(json.dumps(envelope.to_dict(), ensure_ascii=False))
        raise SystemExit(2)


def _field(data: dict, name: str) -> object:
    if name not in data:
        raise CommandInputError(f"missing field: {name}")
    return data[name]


def _object(value: object, name: str) -> dict:
    if not isinstance(value, dict):
        raise CommandInputError(f"{name} must be a JSON object")
    return value


def _array(value: object, name: str) -> list:
    if not isinstance(value, list):
        raise CommandInputError(f"{name} must be a JSON array")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise CommandInputError(f"{name} must be a string")
    return value


def _optional_string(data: dict, name: str, default: str | None = None) -> str | None:
    value = data.get(name, default)
    if value is not None:
        return _string(value, name)
    return None


def _string_array(value: object, name: str) -> list:
    return [_string(item, name) for item in _array(value, name)]


def _mission_plan_from_input(value: object):
    data = _object(value, "mission plan")
    for name in ("id", "title", "capability", "rationale", "priority"):
        _string(_field(data, name), name)
    for name in (
        "prerequisite_ids",
        "target_vocabulary",
        "target_structures",
        "register_notes",
        "cultural_context",
        "common_failure_patterns",
    ):
        _string_array(_field(data, name), name)
    for activity in _array(_field(data, "practice"), "practice"):
        activity_data = _object(activity, "practice activity")
        _string(_field(activity_data, "kind"), "practice kind")
        _string(_field(activity_data, "instructions"), "practice instructions")
    assessment = _object(_field(data, "assessment"), "assessment")
    _string(_field(assessment, "prompt"), "assessment prompt")
    _string_array(_field(assessment, "success_criteria"), "success_criteria")
    try:
        return mission_plan_from_dict(data)
    except ValueError as error:
        raise _input_error(error) from error


def _roadmap_from_input(value: object):
    data = _object(value, "roadmap")
    for phase in _array(_field(data, "phases"), "phases"):
        phase_data = _object(phase, "roadmap phase")
        for name in ("id", "title", "capability_summary"):
            _string(_field(phase_data, name), name)
        _string_array(_field(phase_data, "mission_ids"), "mission_ids")
        for name in ("planned_review_after", "planned_simulation_after"):
            if type(_field(phase_data, name)) is not bool:
                raise CommandInputError(f"{name} must be a bool")
    _string(_field(data, "active_phase_id"), "active_phase_id")
    _string_array(_field(data, "assumptions"), "assumptions")
    try:
        return roadmap_from_dict(data)
    except ValueError as error:
        raise _input_error(error) from error


def _campaign_from_input(value: object) -> Campaign:
    raw_campaign = _object(value, "campaign")
    raw_date = _optional_string(raw_campaign, "target_date")
    inferred_type = "targeted" if raw_date is not None else "flexible"
    campaign_type = CampaignType(raw_campaign.get("campaign_type", inferred_type))
    curriculum_scope = _optional_string(raw_campaign, "curriculum_scope", "balanced")
    coaching_style = _optional_string(raw_campaign, "coaching_style", "supportive")
    campaign_id = _optional_string(raw_campaign, "id")
    mission_inputs = _array(_field(raw_campaign, "missions"), "missions")
    try:
        missions = []
        for value in mission_inputs:
            data = _object(value, "mission")
            mission_id = _string(_field(data, "id"), "mission id")
            title = _string(_field(data, "title"), "mission title")
            missions.append(Mission(mission_id, title, data.get("weight", 1.0)))
        settings = CampaignSettings(
            campaign_type=campaign_type,
            curriculum_scope=CurriculumScope(curriculum_scope),
            coaching_style=CoachingStyle(coaching_style),
            target_date=date.fromisoformat(raw_date) if raw_date is not None else None,
            expected_minutes_per_week=raw_campaign.get("expected_minutes_per_week", 0),
            minimum_minutes_per_week=raw_campaign.get("minimum_minutes_per_week", 0),
        )
        return Campaign(
            id=campaign_id or uuid4().hex,
            goal=_string(_field(raw_campaign, "goal"), "goal"),
            target_language=_string(
                _field(raw_campaign, "target_language"), "target_language"
            ),
            settings=settings,
            missions=tuple(missions),
        )
    except ValueError as error:
        raise _input_error(error) from error


def _state_from_setup_payload(payload: dict) -> CampaignState:
    campaign = _campaign_from_input(_field(payload, "campaign"))
    mission_plans = tuple(
        _mission_plan_from_input(item)
        for item in _array(_field(payload, "mission_plans"), "mission_plans")
    )
    roadmap = _roadmap_from_input(_field(payload, "roadmap"))
    active_phase = next(
        (phase for phase in roadmap.phases if phase.id == roadmap.active_phase_id),
        None,
    )
    if active_phase is not None and not active_phase.mission_ids:
        raise CommandInputError("active roadmap phase has no missions")
    try:
        validate_mission_map(
            mission_plans, tuple(mission.id for mission in campaign.missions)
        )
        validate_roadmap(roadmap, mission_plans)
    except ValueError as error:
        raise _input_error(error) from error
    try:
        learner_id = normalize_learner_id(
            _string(_field(payload, "learner_id"), "learner_id")
        )
    except LearnerRepositoryError as error:
        raise _input_error(error) from error
    prior_knowledge = (
        _string(payload["prior_knowledge"], "prior_knowledge").strip()
        if "prior_knowledge" in payload
        else ""
    )
    try:
        return CampaignState(
            campaign=campaign,
            learner_id=learner_id,
            mission_plans=mission_plans,
            roadmap=roadmap,
            prior_knowledge=prior_knowledge,
        )
    except ValueError as error:
        raise _input_error(error) from error


def _setup(payload: dict, learners_root: Path) -> dict:
    state = _state_from_setup_payload(payload)
    priority_ids = next_priority_ids(state.roadmap, state.mission_plans)
    if not priority_ids:
        raise CommandInputError("active roadmap phase has no missions")
    plan_by_id = {plan.id: plan for plan in state.mission_plans}
    priorities = [plan_by_id[mission_id].title for mission_id in priority_ids]
    try:
        create_and_activate_campaign(learners_root, state)
    except (LearnerRepositoryError, CampaignStorageError) as error:
        raise _input_error(error) from error
    return {
        "learner_id": state.learner_id,
        "campaign_id": state.campaign.id,
        "next_priorities": priorities,
        "first_mission_id": priority_ids[0],
    }


def _list_campaigns(payload: dict, learners_root: Path) -> dict:
    learner_id = _string(_field(payload, "learner_id"), "learner_id")
    try:
        entries = list_learner_campaigns(learners_root, learner_id)
    except (LearnerRepositoryError, CampaignStorageError) as error:
        raise _input_error(error) from error
    return {"campaigns": [{"id": item[0], "goal": item[1]} for item in entries]}


def _selected_state(payload: dict, learners_root: Path) -> CampaignState:
    campaign_id = _optional_string(payload, "campaign_id")
    learner_id = _string(_field(payload, "learner_id"), "learner_id")
    try:
        return select_campaign(
            learners_root,
            learner_id,
            campaign_id,
        )
    except (LearnerRepositoryError, CampaignStorageError) as error:
        raise _input_error(error) from error


def _validate_state(payload: dict, learners_root: Path) -> dict:
    state = _selected_state(payload, learners_root)
    return {"valid": True, "campaign_id": state.campaign.id}


def _show_roadmap(payload: dict, learners_root: Path) -> dict:
    state = _selected_state(payload, learners_root)
    if state.roadmap is None:
        raise CommandInputError("campaign has no roadmap")
    return {"summary": render_roadmap_summary(state.roadmap, state.mission_plans)}


def _validate_map(payload: dict, learners_root: Path) -> dict:
    del learners_root
    readiness_ids = tuple(
        _string(_field(_object(item, "mission"), "id"), "mission id")
        for item in _array(_field(payload, "missions"), "missions")
    )
    plans = tuple(
        _mission_plan_from_input(item)
        for item in _array(_field(payload, "mission_plans"), "mission_plans")
    )
    try:
        validate_mission_map(plans, readiness_ids)
    except ValueError as error:
        raise _input_error(error) from error
    return {"valid": True}


def _list_campaign_status(payload: dict, learners_root: Path) -> dict:
    learner_id = _string(_field(payload, "learner_id"), "learner_id")
    try:
        summaries = list_campaign_summaries(learners_root, learner_id)
    except (LearnerRepositoryError, CampaignStorageError) as error:
        raise _input_error(error) from error
    return {
        "campaigns": [
            {"id": item.id, "goal": item.goal, "status": item.lifecycle.value}
            for item in summaries
        ]
    }


def _transfers_from_input(payload: dict) -> tuple[EvidenceTransfer, ...]:
    values = _array(_field(payload, "evidence_transfers"), "evidence_transfers")
    try:
        return tuple(
            EvidenceTransfer(
                _string(_field(_object(value, "evidence transfer"), "source_mission_id"), "source_mission_id"),
                _string(_field(_object(value, "evidence transfer"), "target_mission_id"), "target_mission_id"),
            )
            for value in values
        )
    except ValueError as error:
        raise _input_error(error) from error


def _transition_campaign(payload: dict, learners_root: Path) -> dict:
    new_state = _state_from_setup_payload(payload)
    source_campaign_id = _string(
        _field(payload, "source_campaign_id"), "source_campaign_id"
    )
    transfers = _transfers_from_input(payload)
    try:
        active = select_active_campaign(learners_root, new_state.learner_id)
        if active.campaign.id != source_campaign_id:
            raise CommandInputError("source_campaign_id is not the active campaign")
        persisted = transition_campaign(
            learners_root, new_state.learner_id, new_state, transfers
        )
    except (LearnerRepositoryError, CampaignStorageError) as error:
        raise _input_error(error) from error
    return {"active_campaign_id": persisted.campaign.id}


def _resume_campaign(payload: dict, learners_root: Path) -> dict:
    learner_id = _string(_field(payload, "learner_id"), "learner_id")
    campaign_id = _string(_field(payload, "campaign_id"), "campaign_id")
    try:
        active = activate_campaign(learners_root, learner_id, campaign_id)
    except (LearnerRepositoryError, CampaignStorageError) as error:
        raise _input_error(error) from error
    return {"active_campaign_id": active.campaign.id}


def _complete_campaign(payload: dict, learners_root: Path) -> dict:
    learner_id = _string(_field(payload, "learner_id"), "learner_id")
    campaign_id = _string(_field(payload, "campaign_id"), "campaign_id")
    try:
        completed = complete_campaign(learners_root, learner_id, campaign_id)
    except (LearnerRepositoryError, CampaignStorageError) as error:
        raise _input_error(error) from error
    return {"completed_campaign_id": completed.campaign.id}


COMMANDS = {
    "setup": _setup,
    "list-campaigns": _list_campaigns,
    "validate-state": _validate_state,
    "validate-mission-map": _validate_map,
    "show-roadmap": _show_roadmap,
    "list-campaign-status": _list_campaign_status,
    "transition-campaign": _transition_campaign,
    "resume-campaign": _resume_campaign,
    "complete-campaign": _complete_campaign,
}


def run_command(command: str, payload: dict, learners_root: Path) -> CommandResult:
    if not isinstance(command, str) or command not in COMMANDS:
        return CommandResult(False, error=f"unknown command: {command}")
    if not isinstance(payload, dict):
        return CommandResult(False, error="command input must be a JSON object")
    try:
        root = Path(learners_root)
    except TypeError:
        return CommandResult(False, error="learners_root must be a path")
    try:
        return CommandResult(True, data=COMMANDS[command](payload, root))
    except CommandInputError as error:
        return CommandResult(False, error=str(error))


def main(argv: list[str] | None = None) -> int:
    parser = _CommandArgumentParser(prog="langcampaign")
    parser.add_argument("command", choices=tuple(COMMANDS))
    parser.add_argument("--learners-root", type=Path, required=True)
    parser.add_argument("--learner-id")
    parser.add_argument("--campaign-id")
    arguments = parser.parse_args(argv)
    try:
        raw_input = sys.stdin.read()
        payload = json.loads(raw_input) if raw_input.strip() else {}
    except json.JSONDecodeError as error:
        result = CommandResult(False, error=str(error))
    else:
        if not isinstance(payload, dict):
            result = CommandResult(
                False,
                error="command input must be a JSON object",
            )
        else:
            if arguments.learner_id is not None:
                payload.setdefault("learner_id", arguments.learner_id)
            if arguments.campaign_id is not None:
                payload.setdefault("campaign_id", arguments.campaign_id)
            result = run_command(
                arguments.command,
                payload,
                arguments.learners_root,
            )
    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0 if result.success else 2

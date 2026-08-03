from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

from .learners import (
    list_learner_campaigns,
    normalize_learner_id,
    save_learner_campaign,
    select_campaign,
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
from .storage import CampaignState, mission_plan_from_dict, roadmap_from_dict


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


def _setup(payload: dict, learners_root: Path) -> dict:
    raw_campaign = payload["campaign"]
    raw_date = raw_campaign.get("target_date")
    settings = CampaignSettings(
        campaign_type=CampaignType(raw_campaign["campaign_type"]),
        curriculum_scope=CurriculumScope(
            raw_campaign.get("curriculum_scope", "balanced")
        ),
        coaching_style=CoachingStyle(raw_campaign.get("coaching_style", "supportive")),
        target_date=date.fromisoformat(raw_date) if raw_date is not None else None,
        expected_minutes_per_week=raw_campaign.get("expected_minutes_per_week", 0),
        minimum_minutes_per_week=raw_campaign.get("minimum_minutes_per_week", 0),
    )
    missions = tuple(
        Mission(item["id"], item["title"], item.get("weight", 1.0))
        for item in raw_campaign["missions"]
    )
    campaign = Campaign(
        id=raw_campaign.get("id") or uuid4().hex,
        goal=raw_campaign["goal"],
        target_language=raw_campaign["target_language"],
        settings=settings,
        missions=missions,
    )
    mission_plans = tuple(
        mission_plan_from_dict(item) for item in payload["mission_plans"]
    )
    roadmap = roadmap_from_dict(payload["roadmap"])
    validate_mission_map(mission_plans, tuple(mission.id for mission in missions))
    validate_roadmap(roadmap, mission_plans)
    priority_ids = next_priority_ids(roadmap, mission_plans)
    if not priority_ids:
        raise ValueError("active roadmap phase has no missions")
    plan_by_id = {plan.id: plan for plan in mission_plans}
    priorities = [plan_by_id[mission_id].title for mission_id in priority_ids]
    state = CampaignState(
        campaign=campaign,
        learner_id=normalize_learner_id(payload["learner_id"]),
        mission_plans=mission_plans,
        roadmap=roadmap,
    )
    save_learner_campaign(learners_root, state)
    return {
        "learner_id": state.learner_id,
        "campaign_id": campaign.id,
        "next_priorities": priorities,
        "first_mission_id": priority_ids[0],
    }


def _list_campaigns(payload: dict, learners_root: Path) -> dict:
    entries = list_learner_campaigns(learners_root, payload["learner_id"])
    return {"campaigns": [{"id": item[0], "goal": item[1]} for item in entries]}


def _selected_state(payload: dict, learners_root: Path) -> CampaignState:
    return select_campaign(
        learners_root,
        payload["learner_id"],
        payload.get("campaign_id"),
    )


def _validate_state(payload: dict, learners_root: Path) -> dict:
    state = _selected_state(payload, learners_root)
    return {"valid": True, "campaign_id": state.campaign.id}


def _show_roadmap(payload: dict, learners_root: Path) -> dict:
    state = _selected_state(payload, learners_root)
    if state.roadmap is None:
        raise ValueError("campaign has no roadmap")
    return {"summary": render_roadmap_summary(state.roadmap, state.mission_plans)}


def _validate_map(payload: dict, learners_root: Path) -> dict:
    del learners_root
    readiness_ids = tuple(item["id"] for item in payload["missions"])
    plans = tuple(mission_plan_from_dict(item) for item in payload["mission_plans"])
    validate_mission_map(plans, readiness_ids)
    return {"valid": True}


COMMANDS = {
    "setup": _setup,
    "list-campaigns": _list_campaigns,
    "validate-state": _validate_state,
    "validate-mission-map": _validate_map,
    "show-roadmap": _show_roadmap,
}


def run_command(command: str, payload: dict, learners_root: Path) -> CommandResult:
    try:
        handler = COMMANDS[command]
    except (KeyError, TypeError):
        return CommandResult(False, error=f"unknown command: {command}")
    if not isinstance(payload, dict):
        return CommandResult(False, error="command input must be a JSON object")
    try:
        return CommandResult(True, data=handler(payload, Path(learners_root)))
    except KeyError as error:
        return CommandResult(False, error=f"missing field: {error.args[0]}")
    except (AttributeError, TypeError, ValueError) as error:
        return CommandResult(
            False,
            error=str(error).replace("MissionPriority", "mission priority"),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langcampaign")
    parser.add_argument("command", choices=tuple(COMMANDS))
    parser.add_argument("--learners-root", type=Path, required=True)
    parser.add_argument("--learner-id")
    parser.add_argument("--campaign-id")
    arguments = parser.parse_args(argv)
    try:
        raw_input = sys.stdin.read()
        payload = json.loads(raw_input) if raw_input.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("command input must be a JSON object")
        if arguments.learner_id is not None:
            payload.setdefault("learner_id", arguments.learner_id)
        if arguments.campaign_id is not None:
            payload.setdefault("campaign_id", arguments.campaign_id)
        result = run_command(arguments.command, payload, arguments.learners_root)
    except (json.JSONDecodeError, ValueError) as error:
        result = CommandResult(False, error=str(error))
    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0 if result.success else 2

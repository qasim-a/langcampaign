import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .assessment import AssessmentEvidence
from .missions import (
    AssessmentScenario,
    MissionPlan,
    MissionPriority,
    PracticeActivity,
    validate_mission_map,
)
from .models import (
    Campaign,
    CampaignSettings,
    CampaignType,
    CoachingStyle,
    CurriculumScope,
    Mission,
    MissionStatus,
    _require_non_empty_string,
)
from .roadmaps import CampaignRoadmap, RoadmapPhase, validate_roadmap


SCHEMA_VERSION = 1
CAMPAIGN_STATE_SCHEMA_VERSION = 2
CAMPAIGN_CONTENT_SCHEMA_VERSION = 3
SUPPORTED_SCHEMA_VERSIONS = (
    SCHEMA_VERSION,
    CAMPAIGN_STATE_SCHEMA_VERSION,
    CAMPAIGN_CONTENT_SCHEMA_VERSION,
)


class CampaignStorageError(ValueError):
    """A stored campaign envelope or payload is invalid."""


@dataclass(frozen=True)
class CampaignState:
    campaign: Campaign
    assessment_evidence: tuple[AssessmentEvidence, ...] = ()
    learner_id: str = "default"
    mission_plans: tuple[MissionPlan, ...] = ()
    roadmap: CampaignRoadmap | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.campaign, Campaign):
            raise ValueError("campaign must be a Campaign")
        if type(self.assessment_evidence) is not tuple:
            raise ValueError("assessment_evidence must be a tuple")
        if type(self.mission_plans) is not tuple:
            raise ValueError("mission_plans must be a tuple")
        _require_non_empty_string(self.learner_id, "learner_id")
        readiness_ids = tuple(mission.id for mission in self.campaign.missions)
        for item in self.assessment_evidence:
            if not isinstance(item, AssessmentEvidence):
                raise ValueError("assessment evidence must be AssessmentEvidence")
            if item.mission_id not in set(readiness_ids):
                raise ValueError(
                    "assessment evidence must reference a campaign mission"
                )
        if self.mission_plans:
            validate_mission_map(self.mission_plans, readiness_ids)
        if self.roadmap is not None:
            if not isinstance(self.roadmap, CampaignRoadmap):
                raise ValueError("roadmap must be a CampaignRoadmap")
            if not self.mission_plans:
                raise ValueError("roadmap requires mission plans")
            validate_roadmap(self.roadmap, self.mission_plans)


def campaign_to_dict(campaign: Campaign) -> dict:
    return {
        "id": campaign.id,
        "goal": campaign.goal,
        "target_language": campaign.target_language,
        "created_at": campaign.created_at.isoformat(),
        "settings": {
            "campaign_type": campaign.settings.campaign_type.value,
            "curriculum_scope": campaign.settings.curriculum_scope.value,
            "coaching_style": campaign.settings.coaching_style.value,
            "target_date": (
                campaign.settings.target_date.isoformat()
                if campaign.settings.target_date is not None
                else None
            ),
            "expected_minutes_per_week": campaign.settings.expected_minutes_per_week,
            "minimum_minutes_per_week": campaign.settings.minimum_minutes_per_week,
        },
        "missions": [
            {
                "id": mission.id,
                "title": mission.title,
                "weight": mission.weight,
                "status": mission.status.value,
            }
            for mission in campaign.missions
        ],
    }


def campaign_from_dict(data: dict) -> Campaign:
    raw_settings = data["settings"]
    raw_date = raw_settings["target_date"]
    settings = CampaignSettings(
        campaign_type=CampaignType(raw_settings["campaign_type"]),
        curriculum_scope=CurriculumScope(raw_settings["curriculum_scope"]),
        coaching_style=CoachingStyle(raw_settings["coaching_style"]),
        target_date=(
            date.fromisoformat(raw_date)
            if raw_date is not None
            else None
        ),
        expected_minutes_per_week=raw_settings["expected_minutes_per_week"],
        minimum_minutes_per_week=raw_settings["minimum_minutes_per_week"],
    )
    missions = tuple(
        Mission(
            id=item["id"],
            title=item["title"],
            weight=item["weight"],
            status=MissionStatus(item["status"]),
        )
        for item in data["missions"]
    )
    return Campaign(
        id=data["id"],
        goal=data["goal"],
        target_language=data["target_language"],
        settings=settings,
        missions=missions,
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def _assessment_evidence_to_dict(
    evidence: AssessmentEvidence,
) -> dict:
    return {
        "mission_id": evidence.mission_id,
        "score": evidence.score,
        "independent": evidence.independent,
        "modality": evidence.modality,
        "assessed_at": evidence.assessed_at.isoformat(),
        "cefr": evidence.cefr,
    }


def _assessment_evidence_from_dict(data: dict) -> AssessmentEvidence:
    return AssessmentEvidence(
        mission_id=data["mission_id"],
        score=data["score"],
        independent=data["independent"],
        modality=data["modality"],
        assessed_at=datetime.fromisoformat(data["assessed_at"]),
        cefr=data["cefr"],
    )


def mission_plan_to_dict(plan: MissionPlan) -> dict:
    return {
        "id": plan.id,
        "title": plan.title,
        "capability": plan.capability,
        "rationale": plan.rationale,
        "priority": plan.priority.value,
        "prerequisite_ids": list(plan.prerequisite_ids),
        "target_vocabulary": list(plan.target_vocabulary),
        "target_structures": list(plan.target_structures),
        "register_notes": list(plan.register_notes),
        "cultural_context": list(plan.cultural_context),
        "practice": [
            {"kind": item.kind, "instructions": item.instructions}
            for item in plan.practice
        ],
        "assessment": {
            "prompt": plan.assessment.prompt,
            "success_criteria": list(plan.assessment.success_criteria),
        },
        "common_failure_patterns": list(plan.common_failure_patterns),
    }


def mission_plan_from_dict(data: dict) -> MissionPlan:
    assessment = data["assessment"]
    return MissionPlan(
        id=data["id"],
        title=data["title"],
        capability=data["capability"],
        rationale=data["rationale"],
        priority=MissionPriority(data["priority"]),
        prerequisite_ids=tuple(data["prerequisite_ids"]),
        target_vocabulary=tuple(data["target_vocabulary"]),
        target_structures=tuple(data["target_structures"]),
        register_notes=tuple(data["register_notes"]),
        cultural_context=tuple(data["cultural_context"]),
        practice=tuple(
            PracticeActivity(item["kind"], item["instructions"])
            for item in data["practice"]
        ),
        assessment=AssessmentScenario(
            assessment["prompt"], tuple(assessment["success_criteria"])
        ),
        common_failure_patterns=tuple(data["common_failure_patterns"]),
    )


def roadmap_to_dict(roadmap: CampaignRoadmap) -> dict:
    return {
        "phases": [
            {
                "id": phase.id,
                "title": phase.title,
                "capability_summary": phase.capability_summary,
                "mission_ids": list(phase.mission_ids),
                "planned_review_after": phase.planned_review_after,
                "planned_simulation_after": phase.planned_simulation_after,
            }
            for phase in roadmap.phases
        ],
        "active_phase_id": roadmap.active_phase_id,
        "assumptions": list(roadmap.assumptions),
    }


def roadmap_from_dict(data: dict) -> CampaignRoadmap:
    return CampaignRoadmap(
        phases=tuple(
            RoadmapPhase(
                id=item["id"],
                title=item["title"],
                capability_summary=item["capability_summary"],
                mission_ids=tuple(item["mission_ids"]),
                planned_review_after=item["planned_review_after"],
                planned_simulation_after=item["planned_simulation_after"],
            )
            for item in data["phases"]
        ),
        active_phase_id=data["active_phase_id"],
        assumptions=tuple(data["assumptions"]),
    )


def _fsync_directory(directory: Path) -> None:
    if os.name != "posix":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        directory_descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(directory_descriptor)
    except OSError:
        # Some POSIX filesystems do not support directory fsync.
        pass
    finally:
        os.close(directory_descriptor)


def _write_payload(path: Path, payload: dict) -> None:
    path = Path(path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_campaign(path: Path, campaign: Campaign) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "campaign": campaign_to_dict(campaign),
    }
    _write_payload(path, payload)


def save_campaign_state(path: Path, state: CampaignState) -> None:
    payload = {
        "schema_version": CAMPAIGN_CONTENT_SCHEMA_VERSION,
        "campaign": campaign_to_dict(state.campaign),
        "assessment_evidence": [
            _assessment_evidence_to_dict(item)
            for item in state.assessment_evidence
        ],
        "learner_id": state.learner_id,
        "mission_plans": [mission_plan_to_dict(item) for item in state.mission_plans],
        "roadmap": roadmap_to_dict(state.roadmap) if state.roadmap else None,
    }
    _write_payload(path, payload)


def _read_envelope(path: Path) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CampaignStorageError(
            "invalid campaign storage: malformed JSON"
        ) from error
    if not isinstance(payload, dict):
        raise CampaignStorageError(
            "invalid campaign storage: envelope must be an object"
        )
    version = payload.get("schema_version")
    if type(version) is not int:
        raise CampaignStorageError(
            "invalid campaign storage: schema_version must be an integer"
        )
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise CampaignStorageError(
            f"unsupported schema_version: {version}"
        )
    if not isinstance(payload.get("campaign"), dict):
        raise CampaignStorageError(
            "invalid campaign storage: campaign must be an object"
        )
    if (
        version in (CAMPAIGN_STATE_SCHEMA_VERSION, CAMPAIGN_CONTENT_SCHEMA_VERSION)
        and not isinstance(payload.get("assessment_evidence"), list)
    ):
        raise CampaignStorageError(
            "invalid campaign storage: assessment_evidence must be a list"
        )
    if version == CAMPAIGN_CONTENT_SCHEMA_VERSION:
        if not isinstance(payload.get("learner_id"), str):
            raise CampaignStorageError(
                "invalid campaign storage: learner_id must be a string"
            )
        if not isinstance(payload.get("mission_plans"), list):
            raise CampaignStorageError(
                "invalid campaign storage: mission_plans must be a list"
            )
        if payload.get("roadmap") is not None and not isinstance(
            payload.get("roadmap"), dict
        ):
            raise CampaignStorageError(
                "invalid campaign storage: roadmap must be an object or null"
            )
    return payload


def load_campaign_state(path: Path) -> CampaignState:
    payload = _read_envelope(path)
    try:
        campaign = campaign_from_dict(payload["campaign"])
        evidence = (
            tuple(
                _assessment_evidence_from_dict(item)
                for item in payload["assessment_evidence"]
            )
            if payload["schema_version"]
            in (CAMPAIGN_STATE_SCHEMA_VERSION, CAMPAIGN_CONTENT_SCHEMA_VERSION)
            else ()
        )
        if payload["schema_version"] == CAMPAIGN_CONTENT_SCHEMA_VERSION:
            return CampaignState(
                campaign=campaign,
                assessment_evidence=evidence,
                learner_id=payload["learner_id"],
                mission_plans=tuple(
                    mission_plan_from_dict(item)
                    for item in payload["mission_plans"]
                ),
                roadmap=(
                    roadmap_from_dict(payload["roadmap"])
                    if payload["roadmap"] is not None
                    else None
                ),
            )
        return CampaignState(campaign, evidence)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise CampaignStorageError(
            "invalid campaign storage: invalid campaign payload"
        ) from error


def load_campaign(path: Path) -> Campaign:
    return load_campaign_state(path).campaign

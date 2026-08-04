import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import TextIO

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
from .runtime import (
    ActiveMissionSession,
    AttemptKind,
    CriterionScore,
    DifficultyAdjustment,
    MissionAttemptRecord,
    MissionCheckpoint,
    MissionContent,
    MissionOutcome,
    NextAction,
    NextActionType,
    RubricCriterion,
)


SCHEMA_VERSION = 1
CAMPAIGN_STATE_SCHEMA_VERSION = 2
CAMPAIGN_CONTENT_SCHEMA_VERSION = 3
CAMPAIGN_LEARNER_CONTEXT_SCHEMA_VERSION = 4
CAMPAIGN_RUNTIME_SCHEMA_VERSION = 5
SUPPORTED_SCHEMA_VERSIONS = (
    SCHEMA_VERSION,
    CAMPAIGN_STATE_SCHEMA_VERSION,
    CAMPAIGN_CONTENT_SCHEMA_VERSION,
    CAMPAIGN_LEARNER_CONTEXT_SCHEMA_VERSION,
    CAMPAIGN_RUNTIME_SCHEMA_VERSION,
)


class CampaignStorageError(ValueError):
    """A stored campaign envelope or payload is invalid."""


class CampaignLifecycle(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


@dataclass(frozen=True)
class LearnerCampaignIndex:
    active_campaign_id: str | None = None
    completed_campaign_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.active_campaign_id is not None and type(self.active_campaign_id) is not str:
            raise ValueError("active_campaign_id must be a string or None")
        if type(self.completed_campaign_ids) is not tuple:
            raise ValueError("completed_campaign_ids must be a tuple")
        if any(type(campaign_id) is not str for campaign_id in self.completed_campaign_ids):
            raise ValueError("completed_campaign_ids must contain strings")
        if len(set(self.completed_campaign_ids)) != len(self.completed_campaign_ids):
            raise ValueError("completed_campaign_ids must be unique")
        if self.active_campaign_id in self.completed_campaign_ids:
            raise ValueError("active campaign cannot be completed")

    def lifecycle_for(self, campaign_id: str) -> CampaignLifecycle:
        if campaign_id == self.active_campaign_id:
            return CampaignLifecycle.ACTIVE
        if campaign_id in self.completed_campaign_ids:
            return CampaignLifecycle.COMPLETED
        return CampaignLifecycle.PAUSED


LEARNER_CAMPAIGN_INDEX_SCHEMA_VERSION = 1


def learner_index_to_dict(index: LearnerCampaignIndex) -> dict:
    if not isinstance(index, LearnerCampaignIndex):
        raise ValueError("index must be a LearnerCampaignIndex")
    return {
        "schema_version": LEARNER_CAMPAIGN_INDEX_SCHEMA_VERSION,
        "active_campaign_id": index.active_campaign_id,
        "completed_campaign_ids": list(index.completed_campaign_ids),
    }


def learner_index_from_dict(data: dict) -> LearnerCampaignIndex:
    if not isinstance(data, dict):
        raise CampaignStorageError("invalid learner index: envelope must be an object")
    if data.get("schema_version") != LEARNER_CAMPAIGN_INDEX_SCHEMA_VERSION or type(
        data.get("schema_version")
    ) is not int:
        raise CampaignStorageError("invalid learner index: unsupported schema_version")
    active_campaign_id = data.get("active_campaign_id")
    completed_campaign_ids = data.get("completed_campaign_ids")
    if active_campaign_id is not None and type(active_campaign_id) is not str:
        raise CampaignStorageError(
            "invalid learner index: active_campaign_id must be a string or null"
        )
    if not isinstance(completed_campaign_ids, list) or any(
        type(campaign_id) is not str for campaign_id in completed_campaign_ids
    ):
        raise CampaignStorageError(
            "invalid learner index: completed_campaign_ids must be a list of strings"
        )
    try:
        return LearnerCampaignIndex(active_campaign_id, tuple(completed_campaign_ids))
    except ValueError as error:
        raise CampaignStorageError("invalid learner index") from error


@dataclass(frozen=True)
class CampaignState:
    campaign: Campaign
    assessment_evidence: tuple[AssessmentEvidence, ...] = ()
    learner_id: str = "default"
    mission_plans: tuple[MissionPlan, ...] = ()
    roadmap: CampaignRoadmap | None = None
    prior_knowledge: str = ""
    revision: int = 0
    active_session: ActiveMissionSession | None = None
    mission_attempts: tuple[MissionAttemptRecord, ...] = ()
    completed_review_phase_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.campaign, Campaign):
            raise ValueError("campaign must be a Campaign")
        if type(self.assessment_evidence) is not tuple:
            raise ValueError("assessment_evidence must be a tuple")
        if type(self.mission_plans) is not tuple:
            raise ValueError("mission_plans must be a tuple")
        _require_non_empty_string(self.learner_id, "learner_id")
        if type(self.prior_knowledge) is not str:
            raise ValueError("prior_knowledge must be a string")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("revision must be a nonnegative integer")
        if type(self.mission_attempts) is not tuple:
            raise ValueError("mission_attempts must be a tuple")
        if type(self.completed_review_phase_ids) is not tuple:
            raise ValueError("completed_review_phase_ids must be a tuple")
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
        mission_ids = set(readiness_ids)
        if self.active_session is not None:
            if not isinstance(self.active_session, ActiveMissionSession):
                raise ValueError("active_session must be an ActiveMissionSession or None")
            if self.active_session.mission_id not in mission_ids:
                raise ValueError("active_session must reference a campaign mission")
        identities = set()
        for attempt in self.mission_attempts:
            if not isinstance(attempt, MissionAttemptRecord):
                raise ValueError("mission_attempts must contain MissionAttemptRecord")
            if attempt.mission_id not in mission_ids:
                raise ValueError("mission_attempt must reference a campaign mission")
            identity = (attempt.mission_id, attempt.attempt_number)
            if identity in identities:
                raise ValueError("mission attempt identities must be unique")
            identities.add(identity)
            matching_evidence = tuple(
                evidence.mission_id == attempt.mission_id
                and evidence.score == attempt.score
                and evidence.independent is True
                and evidence.modality == attempt.modality
                and evidence.assessed_at == attempt.assessed_at
                for evidence in self.assessment_evidence
            )
            if sum(matching_evidence) != 1:
                raise ValueError("mission attempts require exactly one independent matching assessment evidence")
        if self.active_session is not None:
            if self.mission_plans:
                plan = next(
                    item for item in self.mission_plans
                    if item.id == self.active_session.mission_id
                )
                if self.active_session.content.capability != plan.capability:
                    raise ValueError("active session content capability must match mission plan")
            if self.active_session.next_action is not None:
                action = self.active_session.next_action
                if action.mission_id is not None and action.mission_id not in mission_ids:
                    raise ValueError("next action must reference a campaign mission")
                if action.target_phase_id is not None:
                    if self.roadmap is None:
                        raise ValueError("next action phase requires a roadmap")
                    target_phase = next(
                        (phase for phase in self.roadmap.phases if phase.id == action.target_phase_id),
                        None,
                    )
                    if target_phase is None:
                        raise ValueError("next action must reference a roadmap phase")
                    if action.mission_id is not None and action.mission_id not in target_phase.mission_ids:
                        raise ValueError("next action mission must belong to its target phase")
            completed = [item.attempt_number for item in self.mission_attempts if item.mission_id == self.active_session.mission_id]
            if completed and self.active_session.attempt_number <= max(completed):
                matching = any(
                    item.mission_id == self.active_session.mission_id
                    and item.attempt_number == self.active_session.attempt_number
                    for item in self.mission_attempts
                )
                if not (self.active_session.checkpoint is MissionCheckpoint.ASSESSED and matching):
                    raise ValueError("active session attempt must follow completed attempts")
            if self.active_session.checkpoint is MissionCheckpoint.ASSESSED:
                if self.active_session.next_action is None:
                    raise ValueError("assessed session requires a persisted next action")
                matching_attempt = next((
                    item for item in self.mission_attempts
                    if item.mission_id == self.active_session.mission_id
                    and item.attempt_number == self.active_session.attempt_number
                ), None)
                if matching_attempt is None:
                    raise ValueError("assessed session requires a matching mission attempt")
                if matching_attempt.outcome is not self.active_session.latest_outcome:
                    raise ValueError("assessed session outcome must match stored attempt")
                if matching_attempt.kind is not self.active_session.kind:
                    raise ValueError("assessed session kind must match stored attempt")
                if matching_attempt.rubric != self.active_session.content.rubric:
                    raise ValueError("assessed session rubric must match stored attempt")
                if self.active_session.adjustment is not DifficultyAdjustment.STANDARD:
                    raise ValueError("assessed session adjustment must be standard")
                if self.active_session.content_refresh_required:
                    raise ValueError("assessed session cannot require refreshed content")
        if len(set(self.completed_review_phase_ids)) != len(self.completed_review_phase_ids):
            raise ValueError("completed_review_phase_ids must be unique")
        if self.roadmap is None:
            if self.completed_review_phase_ids:
                raise ValueError("completed reviews require a roadmap")
        else:
            phase_ids = {phase.id for phase in self.roadmap.phases}
            for phase_id in self.completed_review_phase_ids:
                _require_non_empty_string(phase_id, "completed review phase id")
                if phase_id not in phase_ids:
                    raise ValueError("completed review phase must exist")


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


def _runtime_object(value: object, name: str, keys: set[str]) -> dict:
    if type(value) is not dict:
        raise ValueError(f"{name} must be an object")
    if set(value) != keys:
        raise ValueError(f"{name} fields are invalid")
    return value


def _runtime_array(value: object, name: str) -> list:
    if type(value) is not list:
        raise ValueError(f"{name} must be an array")
    return value


def _runtime_string_array(value: object, name: str) -> tuple[str, ...]:
    values = _runtime_array(value, name)
    if any(type(item) is not str for item in values):
        raise ValueError(f"{name} must contain strings")
    return tuple(values)


def rubric_criterion_to_dict(item: RubricCriterion) -> dict:
    return {"id": item.id, "description": item.description, "weight": item.weight}


def rubric_criterion_from_dict(data: dict) -> RubricCriterion:
    _runtime_object(data, "rubric criterion", {"id", "description", "weight"})
    return RubricCriterion(data["id"], data["description"], data["weight"])


def mission_content_to_dict(content: MissionContent) -> dict:
    return {
        "generation_id": content.generation_id, "candidate_number": content.candidate_number,
        "capability": content.capability, "scenario": content.scenario,
        "teaching_objectives": list(content.teaching_objectives),
        "essential_language": list(content.essential_language),
        "guided_prompts": list(content.guided_prompts),
        "assessment_prompt": content.assessment_prompt,
        "rubric": [rubric_criterion_to_dict(item) for item in content.rubric],
    }


def mission_content_from_dict(data: dict) -> MissionContent:
    _runtime_object(data, "mission content", {
        "generation_id", "candidate_number", "capability", "scenario",
        "teaching_objectives", "essential_language", "guided_prompts",
        "assessment_prompt", "rubric",
    })
    teaching_objectives = _runtime_string_array(data["teaching_objectives"], "teaching_objectives")
    essential_language = _runtime_string_array(data["essential_language"], "essential_language")
    guided_prompts = _runtime_string_array(data["guided_prompts"], "guided_prompts")
    rubric = _runtime_array(data["rubric"], "rubric")
    return MissionContent(
        data["generation_id"], data["candidate_number"], data["capability"], data["scenario"],
        teaching_objectives, essential_language,
        guided_prompts, data["assessment_prompt"],
        tuple(rubric_criterion_from_dict(item) for item in rubric),
    )


def criterion_score_to_dict(item: CriterionScore) -> dict:
    return {"criterion_id": item.criterion_id, "score": item.score}


def criterion_score_from_dict(data: dict) -> CriterionScore:
    _runtime_object(data, "criterion score", {"criterion_id", "score"})
    return CriterionScore(data["criterion_id"], data["score"])


def next_action_to_dict(action: NextAction) -> dict:
    return {"kind": action.kind.value, "mission_id": action.mission_id, "target_phase_id": action.target_phase_id}


def next_action_from_dict(data: dict) -> NextAction:
    _runtime_object(data, "next action", {"kind", "mission_id", "target_phase_id"})
    return NextAction(NextActionType(data["kind"]), data.get("mission_id"), data.get("target_phase_id"))


def mission_attempt_to_dict(item: MissionAttemptRecord) -> dict:
    return {
        "mission_id": item.mission_id, "attempt_number": item.attempt_number, "kind": item.kind.value,
        "rubric": [rubric_criterion_to_dict(value) for value in item.rubric],
        "criterion_scores": [criterion_score_to_dict(value) for value in item.criterion_scores],
        "score": item.score, "outcome": item.outcome.value, "modality": item.modality,
        "result_statement": item.result_statement, "assessed_at": item.assessed_at.isoformat(),
    }


def mission_attempt_from_dict(data: dict) -> MissionAttemptRecord:
    _runtime_object(data, "mission attempt", {
        "mission_id", "attempt_number", "kind", "rubric", "criterion_scores",
        "score", "outcome", "modality", "result_statement", "assessed_at",
    })
    rubric = _runtime_array(data["rubric"], "rubric")
    scores = _runtime_array(data["criterion_scores"], "criterion_scores")
    return MissionAttemptRecord(
        data["mission_id"], data["attempt_number"], AttemptKind(data["kind"]),
        tuple(rubric_criterion_from_dict(item) for item in rubric),
        tuple(criterion_score_from_dict(item) for item in scores),
        data["score"], MissionOutcome(data["outcome"]), data["modality"], data["result_statement"],
        datetime.fromisoformat(data["assessed_at"]),
    )


def active_session_to_dict(session: ActiveMissionSession) -> dict:
    return {
        "mission_id": session.mission_id, "attempt_number": session.attempt_number,
        "kind": session.kind.value, "checkpoint": session.checkpoint.value,
        "adjustment": session.adjustment.value, "content": mission_content_to_dict(session.content),
        "latest_outcome": session.latest_outcome.value if session.latest_outcome else None,
        "next_action": next_action_to_dict(session.next_action) if session.next_action else None,
        "content_refresh_required": session.content_refresh_required,
    }


def active_session_from_dict(data: dict) -> ActiveMissionSession:
    _runtime_object(data, "active session", {
        "mission_id", "attempt_number", "kind", "checkpoint", "adjustment",
        "content", "latest_outcome", "next_action", "content_refresh_required",
    })
    return ActiveMissionSession(
        data["mission_id"], data["attempt_number"], AttemptKind(data["kind"]),
        MissionCheckpoint(data["checkpoint"]), DifficultyAdjustment(data["adjustment"]),
        mission_content_from_dict(data["content"]),
        MissionOutcome(data["latest_outcome"]) if data.get("latest_outcome") is not None else None,
        next_action_from_dict(data["next_action"]) if data.get("next_action") is not None else None,
        data["content_refresh_required"],
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
    _write_payload(path, _campaign_state_payload(state))


def _campaign_state_payload(state: CampaignState) -> dict:
    return {
        "schema_version": CAMPAIGN_RUNTIME_SCHEMA_VERSION,
        "campaign": campaign_to_dict(state.campaign),
        "assessment_evidence": [
            _assessment_evidence_to_dict(item)
            for item in state.assessment_evidence
        ],
        "learner_id": state.learner_id,
        "mission_plans": [mission_plan_to_dict(item) for item in state.mission_plans],
        "roadmap": roadmap_to_dict(state.roadmap) if state.roadmap else None,
        "prior_knowledge": state.prior_knowledge,
        "revision": state.revision,
        "active_session": (
            active_session_to_dict(state.active_session)
            if state.active_session is not None else None
        ),
        "mission_attempts": [mission_attempt_to_dict(item) for item in state.mission_attempts],
        "completed_review_phase_ids": list(state.completed_review_phase_ids),
    }


def save_campaign_state_at(directory_fd: int, state: CampaignState) -> None:
    """Atomically save state inside an already-open directory descriptor."""
    temporary = f".state.json.{secrets.token_hex(16)}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            json.dump(_campaign_state_payload(state), stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(
            temporary,
            "state.json",
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        temporary = ""
        if os.name == "posix":
            try:
                os.fsync(directory_fd)
            except OSError:
                # Some POSIX filesystems do not support directory fsync.
                pass
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass


def create_campaign_state_at(directory_fd: int, state: CampaignState) -> None:
    """Create state inside an open directory without replacing any entry."""
    temporary = f".state.json.{secrets.token_hex(16)}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            json.dump(_campaign_state_payload(state), stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(
            temporary,
            "state.json",
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        if os.name == "posix":
            try:
                os.fsync(directory_fd)
            except OSError:
                # Some POSIX filesystems do not support directory fsync.
                pass


def save_learner_index_at(directory_fd: int, index: LearnerCampaignIndex) -> None:
    """Atomically save a learner index inside an already-open directory."""
    temporary = f".index.json.{secrets.token_hex(16)}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            json.dump(learner_index_to_dict(index), stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(
            temporary,
            "index.json",
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        temporary = ""
        if os.name == "posix":
            try:
                os.fsync(directory_fd)
            except OSError:
                pass
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass


def _read_envelope_text(text: str) -> dict:
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CampaignStorageError(
            "invalid campaign storage: malformed JSON"
        ) from error
    if type(payload) is not dict:
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
    if type(payload.get("campaign")) is not dict:
        raise CampaignStorageError(
            "invalid campaign storage: campaign must be an object"
        )
    if (
        version
        in (
            CAMPAIGN_STATE_SCHEMA_VERSION,
            CAMPAIGN_CONTENT_SCHEMA_VERSION,
            CAMPAIGN_LEARNER_CONTEXT_SCHEMA_VERSION,
            CAMPAIGN_RUNTIME_SCHEMA_VERSION,
        )
        and type(payload.get("assessment_evidence")) is not list
    ):
        raise CampaignStorageError(
            "invalid campaign storage: assessment_evidence must be a list"
        )
    if version in (
        CAMPAIGN_CONTENT_SCHEMA_VERSION,
        CAMPAIGN_LEARNER_CONTEXT_SCHEMA_VERSION,
        CAMPAIGN_RUNTIME_SCHEMA_VERSION,
    ):
        if not isinstance(payload.get("learner_id"), str):
            raise CampaignStorageError(
                "invalid campaign storage: learner_id must be a string"
            )
        if type(payload.get("mission_plans")) is not list:
            raise CampaignStorageError(
                "invalid campaign storage: mission_plans must be a list"
            )
        if payload.get("roadmap") is not None and type(payload.get("roadmap")) is not dict:
            raise CampaignStorageError(
                "invalid campaign storage: roadmap must be an object or null"
            )
    if version in (CAMPAIGN_LEARNER_CONTEXT_SCHEMA_VERSION, CAMPAIGN_RUNTIME_SCHEMA_VERSION) and not isinstance(
        payload.get("prior_knowledge"), str
    ):
        raise CampaignStorageError(
            "invalid campaign storage: prior_knowledge must be a string"
        )
    if version == CAMPAIGN_RUNTIME_SCHEMA_VERSION:
        if type(payload.get("revision")) is not int or payload["revision"] < 0:
            raise CampaignStorageError("invalid campaign storage: revision must be a nonnegative integer")
        if payload.get("active_session") is not None and type(payload.get("active_session")) is not dict:
            raise CampaignStorageError("invalid campaign storage: active_session must be an object or null")
        if type(payload.get("mission_attempts")) is not list:
            raise CampaignStorageError("invalid campaign storage: mission_attempts must be a list")
        if type(payload.get("completed_review_phase_ids")) is not list:
            raise CampaignStorageError("invalid campaign storage: completed_review_phase_ids must be a list")
    return payload


def _read_envelope(path: Path) -> dict:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise CampaignStorageError(
            "invalid campaign storage: malformed JSON"
        ) from error
    return _read_envelope_text(text)


def _read_envelope_file(stream: TextIO) -> dict:
    try:
        text = stream.read()
    except UnicodeDecodeError as error:
        raise CampaignStorageError(
            "invalid campaign storage: malformed JSON"
        ) from error
    return _read_envelope_text(text)


def _campaign_state_from_payload(payload: dict) -> CampaignState:
    try:
        campaign = campaign_from_dict(payload["campaign"])
        evidence = (
            tuple(
                _assessment_evidence_from_dict(item)
                for item in payload["assessment_evidence"]
            )
            if payload["schema_version"]
            in (
                CAMPAIGN_STATE_SCHEMA_VERSION,
                CAMPAIGN_CONTENT_SCHEMA_VERSION,
                CAMPAIGN_LEARNER_CONTEXT_SCHEMA_VERSION,
                CAMPAIGN_RUNTIME_SCHEMA_VERSION,
            )
            else ()
        )
        if payload["schema_version"] in (
            CAMPAIGN_CONTENT_SCHEMA_VERSION,
            CAMPAIGN_LEARNER_CONTEXT_SCHEMA_VERSION,
            CAMPAIGN_RUNTIME_SCHEMA_VERSION,
        ):
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
                prior_knowledge=(payload["prior_knowledge"] if payload["schema_version"] in (CAMPAIGN_LEARNER_CONTEXT_SCHEMA_VERSION, CAMPAIGN_RUNTIME_SCHEMA_VERSION) else ""),
                revision=(payload["revision"] if payload["schema_version"] == CAMPAIGN_RUNTIME_SCHEMA_VERSION else 0),
                active_session=(active_session_from_dict(payload["active_session"]) if payload["schema_version"] == CAMPAIGN_RUNTIME_SCHEMA_VERSION and payload["active_session"] is not None else None),
                mission_attempts=(tuple(mission_attempt_from_dict(item) for item in payload["mission_attempts"]) if payload["schema_version"] == CAMPAIGN_RUNTIME_SCHEMA_VERSION else ()),
                completed_review_phase_ids=(tuple(payload["completed_review_phase_ids"]) if payload["schema_version"] == CAMPAIGN_RUNTIME_SCHEMA_VERSION else ()),
            )
        return CampaignState(campaign, evidence)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError, StopIteration) as error:
        raise CampaignStorageError(
            "invalid campaign storage: invalid campaign payload"
        ) from error


def load_campaign_state(path: Path) -> CampaignState:
    return _campaign_state_from_payload(_read_envelope(path))


def load_campaign_state_file(stream: TextIO) -> CampaignState:
    return _campaign_state_from_payload(_read_envelope_file(stream))


def load_learner_index_file(stream: TextIO) -> LearnerCampaignIndex:
    try:
        text = stream.read()
    except UnicodeDecodeError as error:
        raise CampaignStorageError("invalid learner index: malformed JSON") from error
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CampaignStorageError("invalid learner index: malformed JSON") from error
    return learner_index_from_dict(payload)


def load_campaign(path: Path) -> Campaign:
    return load_campaign_state(path).campaign

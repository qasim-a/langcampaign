"""Pure, storage-independent mission runtime policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from decimal import Decimal, ROUND_HALF_UP

from .assessment import AssessmentEvidence
from .missions import MissionPlan, MissionPriority
from .models import Campaign, MissionStatus, _require_aware_datetime, _require_non_empty_string
from .roadmaps import CampaignRoadmap


def _tuple(value: object, name: str) -> tuple:
    if type(value) is not tuple:
        raise ValueError(f"{name} must be a tuple")
    return value


def _positive_int(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _score(value: object, name: str = "score") -> int:
    if type(value) is not int or not 0 <= value <= 100:
        raise ValueError(f"{name} must be an integer from 0 through 100")
    return value


class MissionCheckpoint(StrEnum):
    TEACHING = "teaching"
    GUIDED_PRACTICE = "guided_practice"
    CHECK_READY = "check_ready"
    ASSESSED = "assessed"


class DifficultyAdjustment(StrEnum):
    STANDARD = "standard"
    HARDER = "harder"
    PREREQUISITE_SUPPORT = "prerequisite_support"


class AttemptKind(StrEnum):
    INITIAL = "initial"
    RETRY = "retry"
    PREREQUISITE_SUPPORTED = "prerequisite_supported"
    REVIEW = "review"


class MissionOutcome(StrEnum):
    PASS = "pass"
    PARTIAL = "partial"
    RETRY = "retry"


class NextActionType(StrEnum):
    PREREQUISITE_SUPPORT = "prerequisite_support"
    FOCUSED_RETRY = "focused_retry"
    REVIEW = "review"
    NEXT_MISSION = "next_mission"
    GOAL_READY_TO_COMPLETE = "goal_ready_to_complete"


@dataclass(frozen=True)
class RubricCriterion:
    id: str
    description: str
    weight: int

    def __post_init__(self) -> None:
        _require_non_empty_string(self.id, "criterion id")
        _require_non_empty_string(self.description, "criterion description")
        _positive_int(self.weight, "criterion weight")


def _validate_rubric(rubric: object) -> tuple[RubricCriterion, ...]:
    rubric = _tuple(rubric, "rubric")
    if not rubric:
        raise ValueError("rubric must not be empty")
    if any(not isinstance(item, RubricCriterion) for item in rubric):
        raise ValueError("rubric must contain RubricCriterion records")
    ids = tuple(item.id for item in rubric)
    if len(ids) != len(set(ids)):
        raise ValueError("rubric criterion ids must be unique")
    if sum(item.weight for item in rubric) != 100:
        raise ValueError("rubric weights must total 100")
    return rubric


@dataclass(frozen=True)
class MissionContent:
    generation_id: str
    candidate_number: int
    capability: str
    scenario: str
    teaching_objectives: tuple[str, ...]
    essential_language: tuple[str, ...]
    guided_prompts: tuple[str, ...]
    assessment_prompt: str
    rubric: tuple[RubricCriterion, ...]

    def __post_init__(self) -> None:
        for value, name in ((self.generation_id, "generation_id"), (self.capability, "capability"), (self.scenario, "scenario"), (self.assessment_prompt, "assessment_prompt")):
            _require_non_empty_string(value, name)
        if type(self.candidate_number) is not int or self.candidate_number not in (1, 2):
            raise ValueError("candidate_number must be 1 or 2")
        for values, name in ((self.teaching_objectives, "teaching_objectives"), (self.essential_language, "essential_language"), (self.guided_prompts, "guided_prompts")):
            _tuple(values, name)
            if not values:
                raise ValueError(f"{name} must not be empty")
            for item in values:
                _require_non_empty_string(item, name)
        _validate_rubric(self.rubric)


@dataclass(frozen=True)
class CriterionScore:
    criterion_id: str
    score: int

    def __post_init__(self) -> None:
        _require_non_empty_string(self.criterion_id, "criterion_id")
        _score(self.score)


@dataclass(frozen=True)
class NextAction:
    kind: NextActionType
    mission_id: str | None = None
    target_phase_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, NextActionType):
            raise ValueError("kind must be a NextActionType")
        needs_mission = self.kind is not NextActionType.GOAL_READY_TO_COMPLETE
        if needs_mission != (self.mission_id is not None):
            if needs_mission:
                raise ValueError("mission_id is required for mission actions")
            raise ValueError("mission_id must not be present for goal readiness")
        if self.mission_id is not None:
            _require_non_empty_string(self.mission_id, "mission_id")
        if self.target_phase_id is not None:
            _require_non_empty_string(self.target_phase_id, "target_phase_id")


def _validate_scores(rubric: tuple[RubricCriterion, ...], scores: object) -> tuple[CriterionScore, ...]:
    scores = _tuple(scores, "criterion_scores")
    if any(not isinstance(item, CriterionScore) for item in scores):
        raise ValueError("criterion_scores must contain CriterionScore records")
    score_ids = tuple(item.criterion_id for item in scores)
    if len(score_ids) != len(set(score_ids)) or set(score_ids) != {item.id for item in rubric}:
        raise ValueError("criterion score coverage must exactly match rubric")
    return scores


@dataclass(frozen=True)
class MissionAttemptRecord:
    mission_id: str
    attempt_number: int
    kind: AttemptKind
    rubric: tuple[RubricCriterion, ...]
    criterion_scores: tuple[CriterionScore, ...]
    score: int
    outcome: MissionOutcome
    modality: str
    result_statement: str
    assessed_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty_string(self.mission_id, "mission_id")
        _positive_int(self.attempt_number, "attempt_number")
        if not isinstance(self.kind, AttemptKind):
            raise ValueError("kind must be an AttemptKind")
        rubric = _validate_rubric(self.rubric)
        scores = _validate_scores(rubric, self.criterion_scores)
        score = _score(self.score)
        if score != derive_score(rubric, scores):
            raise ValueError("score must equal derived rubric score")
        if not isinstance(self.outcome, MissionOutcome) or self.outcome is not outcome_for_score(score):
            raise ValueError("outcome must match score")
        _require_non_empty_string(self.modality, "modality")
        _require_non_empty_string(self.result_statement, "result_statement")
        _require_aware_datetime(self.assessed_at, "assessed_at")


@dataclass(frozen=True)
class ActiveMissionSession:
    mission_id: str
    attempt_number: int
    kind: AttemptKind
    checkpoint: MissionCheckpoint
    adjustment: DifficultyAdjustment
    content: MissionContent
    latest_outcome: MissionOutcome | None = None
    next_action: NextAction | None = None
    content_refresh_required: bool = False

    def __post_init__(self) -> None:
        _require_non_empty_string(self.mission_id, "mission_id")
        _positive_int(self.attempt_number, "attempt_number")
        if not isinstance(self.kind, AttemptKind) or not isinstance(self.checkpoint, MissionCheckpoint) or not isinstance(self.adjustment, DifficultyAdjustment):
            raise ValueError("session enums are invalid")
        if not isinstance(self.content, MissionContent):
            raise ValueError("content must be MissionContent")
        if self.latest_outcome is not None and not isinstance(self.latest_outcome, MissionOutcome):
            raise ValueError("latest_outcome must be a MissionOutcome or None")
        if self.next_action is not None and not isinstance(self.next_action, NextAction):
            raise ValueError("next_action must be a NextAction or None")
        if type(self.content_refresh_required) is not bool:
            raise ValueError("content_refresh_required must be a bool")
        if (self.checkpoint is MissionCheckpoint.ASSESSED) != (self.latest_outcome is not None):
            raise ValueError("latest_outcome must match assessed checkpoint")
        if self.next_action is not None and self.checkpoint is not MissionCheckpoint.ASSESSED:
            raise ValueError("next_action requires assessed checkpoint")


@dataclass(frozen=True)
class RuntimeProgress:
    percent: int
    best_scores: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if type(self.percent) is not int or not 0 <= self.percent <= 100:
            raise ValueError("percent must be an integer from 0 through 100")
        _tuple(self.best_scores, "best_scores")

    @property
    def bar(self) -> str:
        return "█" * (self.percent // 10) + "░" * (10 - self.percent // 10)


def derive_score(rubric: tuple[RubricCriterion, ...], scores: tuple[CriterionScore, ...]) -> int:
    rubric = _validate_rubric(rubric)
    scores = _validate_scores(rubric, scores)
    scores_by_id = {item.criterion_id: item.score for item in scores}
    return (sum(item.weight * scores_by_id[item.id] for item in rubric) + 50) // 100


def outcome_for_score(score: int) -> MissionOutcome:
    score = _score(score)
    if score >= 80:
        return MissionOutcome.PASS
    if score >= 40:
        return MissionOutcome.PARTIAL
    return MissionOutcome.RETRY


def best_independent_scores(campaign: Campaign, evidence: tuple[AssessmentEvidence, ...]) -> dict[str, int]:
    if not isinstance(campaign, Campaign) or type(evidence) is not tuple:
        raise ValueError("campaign and evidence are invalid")
    mission_ids = {mission.id for mission in campaign.missions}
    best: dict[str, int] = {}
    for item in evidence:
        if not isinstance(item, AssessmentEvidence):
            raise ValueError("evidence must contain AssessmentEvidence")
        if item.mission_id not in mission_ids:
            raise ValueError("evidence references an unknown mission")
        if item.independent:
            best[item.mission_id] = max(best.get(item.mission_id, 0), item.score)
    return best


def runtime_progress(campaign: Campaign, evidence: tuple[AssessmentEvidence, ...]) -> RuntimeProgress:
    best = best_independent_scores(campaign, evidence)
    total = sum((Decimal(str(mission.weight)) for mission in campaign.missions), Decimal())
    earned = sum((Decimal(str(mission.weight)) * best.get(mission.id, 0) for mission in campaign.missions), Decimal())
    percent = int((earned / total).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if total else 0
    return RuntimeProgress(percent, tuple((mission.id, best[mission.id]) for mission in campaign.missions if mission.id in best))


def render_runtime_progress(outcome: MissionOutcome, statement: str, progress: RuntimeProgress, next_label: str) -> str:
    if not isinstance(outcome, MissionOutcome) or not isinstance(progress, RuntimeProgress):
        raise ValueError("outcome and progress are invalid")
    _require_non_empty_string(statement, "statement")
    _require_non_empty_string(next_label, "next_label")
    emoji, header = {MissionOutcome.PASS: ("✅", "Mission passed"), MissionOutcome.PARTIAL: ("🟡", "Mission partially complete"), MissionOutcome.RETRY: ("🔁", "Mission needs retry")}[outcome]
    return f"{emoji} {header}\n\n{statement}\n\nProgress  {progress.bar}  {progress.percent}%\n\nNext: {next_label}"


def select_next_action(campaign: Campaign, plans: tuple[MissionPlan, ...], roadmap: CampaignRoadmap, completed_review_phase_ids: tuple[str, ...], current_session: ActiveMissionSession, outcome: MissionOutcome) -> NextAction:
    """Choose the next durable action without reading or changing storage."""
    if not isinstance(campaign, Campaign) or type(plans) is not tuple or not isinstance(roadmap, CampaignRoadmap) or type(completed_review_phase_ids) is not tuple or not isinstance(current_session, ActiveMissionSession) or not isinstance(outcome, MissionOutcome):
        raise ValueError("invalid selection inputs")
    plan_by_id = {plan.id: plan for plan in plans}
    phase_by_id = {mission_id: phase for phase in roadmap.phases for mission_id in phase.mission_ids}
    if current_session.mission_id not in plan_by_id or set(plan_by_id) != set(phase_by_id):
        raise ValueError("plans must match roadmap and session")
    if outcome is MissionOutcome.RETRY or current_session.adjustment is DifficultyAdjustment.PREREQUISITE_SUPPORT:
        return NextAction(NextActionType.PREREQUISITE_SUPPORT, current_session.mission_id, phase_by_id[current_session.mission_id].id)
    if outcome is MissionOutcome.PARTIAL:
        return NextAction(NextActionType.FOCUSED_RETRY, current_session.mission_id, phase_by_id[current_session.mission_id].id)
    statuses = {mission.id: mission.status for mission in campaign.missions}
    statuses[current_session.mission_id] = MissionStatus.DEMONSTRATED
    ordered = tuple(mission_id for phase in roadmap.phases for mission_id in phase.mission_ids)
    for mission_id in ordered:
        if statuses.get(mission_id) is MissionStatus.REVIEW_DUE:
            return NextAction(NextActionType.REVIEW, mission_id, phase_by_id[mission_id].id)
    active_index = next(index for index, phase in enumerate(roadmap.phases) if phase.id == roadmap.active_phase_id)
    required = set()
    for plan in plans:
        if plan.priority is MissionPriority.CRITICAL:
            required.add(plan.id)
            required.update(plan.prerequisite_ids)
    for mission_id in ordered:
        if mission_id not in required or statuses.get(mission_id) is MissionStatus.DEMONSTRATED:
            continue
        plan = plan_by_id[mission_id]
        if all(statuses.get(pre) is MissionStatus.DEMONSTRATED for pre in plan.prerequisite_ids):
            return NextAction(NextActionType.NEXT_MISSION, mission_id, phase_by_id[mission_id].id)
    return NextAction(NextActionType.GOAL_READY_TO_COMPLETE)

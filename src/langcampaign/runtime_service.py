"""Stateful mission runtime operations built on the locked learner repository."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum

from .assessment import AssessmentEvidence
from .learners import (
    CampaignCompletedError,
    CampaignInactiveError,
    CampaignRevisionConflict,
    CampaignSelectionError,
    LearnerRepositoryError,
    mutate_learner_campaign,
    select_campaign_lifecycle,
)
from .models import MissionStatus
from .runtime import ActiveMissionSession, AttemptKind, CriterionScore, DifficultyAdjustment, MissionAttemptRecord, MissionCheckpoint, MissionContent, MissionOutcome, NextAction, RuntimeProgress, derive_score, outcome_for_score, render_runtime_progress, runtime_progress, select_next_action
from .storage import CampaignLifecycle, CampaignState, CampaignStorageError


class RuntimeErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"; INVALID_CONTENT = "invalid_content"; CAMPAIGN_NOT_FOUND = "campaign_not_found"; CAMPAIGN_NOT_ACTIVE = "campaign_not_active"; CAMPAIGN_COMPLETED = "campaign_completed"; MISSION_NOT_FOUND = "mission_not_found"; SESSION_NOT_STARTED = "session_not_started"; INVALID_TRANSITION = "invalid_transition"; ASSESSMENT_NOT_READY = "assessment_not_ready"; INDEPENDENCE_REQUIRED = "independence_required"; ATTEMPT_CONFLICT = "attempt_conflict"; DUPLICATE_CONFLICT = "duplicate_conflict"; REVISION_CONFLICT = "revision_conflict"; PERSISTENCE_FAILED = "persistence_failed"


class MissionRuntimeError(ValueError):
    def __init__(self, code: RuntimeErrorCode, message: str, issues=(), current_revision: int | None = None):
        self.code, self.issues, self.current_revision = code, issues, current_revision
        super().__init__(message)


@dataclass(frozen=True)
class ContentIssue:
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class ContentValidationResult:
    valid: bool
    content: MissionContent | None
    correction_allowed: bool
    issues: tuple[ContentIssue, ...] = ()


@dataclass(frozen=True)
class RuntimeSnapshot:
    revision: int
    session: ActiveMissionSession | None
    progress: RuntimeProgress
    rendered_progress: str | None
    next_action: NextAction | None
    latest_result: MissionAttemptRecord | None = None


def validate_mission_content(content: object) -> ContentValidationResult:
    candidate = getattr(content, "candidate_number", None)
    try:
        if not isinstance(content, MissionContent):
            raise ValueError("content must be a MissionContent")
        return ContentValidationResult(True, content, False)
    except ValueError as error:
        return ContentValidationResult(False, None, candidate == 1, (ContentIssue("content", "invalid_content", str(error)),))


def _snapshot(state: CampaignState) -> RuntimeSnapshot:
    progress = runtime_progress(state.campaign, state.assessment_evidence)
    session = state.active_session
    action = session.next_action if session else None
    rendered = None
    latest_result = None
    if session and session.latest_outcome:
        latest_result = next(
            item for item in state.mission_attempts
            if (item.mission_id, item.attempt_number)
            == (session.mission_id, session.attempt_number)
        )
        rendered = render_runtime_progress(
            session.latest_outcome,
            latest_result.result_statement,
            progress,
            action.kind.value if action else "continue",
        )
    return RuntimeSnapshot(state.revision, session, progress, rendered, action, latest_result)


def _active(root, learner_id, campaign_id) -> CampaignState:
    try:
        state, lifecycle = select_campaign_lifecycle(root, learner_id, campaign_id)
    except CampaignSelectionError as error:
        raise MissionRuntimeError(RuntimeErrorCode.CAMPAIGN_NOT_FOUND, str(error)) from error
    except LearnerRepositoryError as error:
        raise MissionRuntimeError(RuntimeErrorCode.INVALID_REQUEST, str(error)) from error
    except (CampaignStorageError, OSError) as error:
        raise MissionRuntimeError(RuntimeErrorCode.PERSISTENCE_FAILED, str(error)) from error
    if lifecycle is CampaignLifecycle.COMPLETED:
        raise MissionRuntimeError(RuntimeErrorCode.CAMPAIGN_COMPLETED, "campaign is completed")
    if lifecycle is not CampaignLifecycle.ACTIVE:
        raise MissionRuntimeError(RuntimeErrorCode.CAMPAIGN_NOT_ACTIVE, "campaign is not active")
    return state


def mission_status(root, learner_id: str, campaign_id: str) -> RuntimeSnapshot:
    return _snapshot(_active(root, learner_id, campaign_id))


def _mutate(root, learner_id, campaign_id, expected_revision, transform, *, idempotent_if=None) -> CampaignState:
    try:
        return mutate_learner_campaign(
            root,
            learner_id,
            campaign_id,
            expected_revision,
            transform,
            idempotent_if=idempotent_if,
            require_active=True,
        )
    except CampaignCompletedError as error:
        raise MissionRuntimeError(RuntimeErrorCode.CAMPAIGN_COMPLETED, str(error)) from error
    except CampaignInactiveError as error:
        raise MissionRuntimeError(RuntimeErrorCode.CAMPAIGN_NOT_ACTIVE, str(error)) from error
    except CampaignRevisionConflict as error:
        raise MissionRuntimeError(RuntimeErrorCode.REVISION_CONFLICT, str(error), current_revision=error.current.revision) from error
    except CampaignSelectionError as error:
        raise MissionRuntimeError(RuntimeErrorCode.CAMPAIGN_NOT_FOUND, str(error)) from error
    except (CampaignStorageError, OSError) as error:
        raise MissionRuntimeError(RuntimeErrorCode.PERSISTENCE_FAILED, str(error)) from error
    except LearnerRepositoryError as error:
        raise MissionRuntimeError(RuntimeErrorCode.INVALID_REQUEST, str(error)) from error


def _expected_session(state, mission_id, attempt_number) -> ActiveMissionSession:
    session = state.active_session
    if session is None:
        raise MissionRuntimeError(RuntimeErrorCode.SESSION_NOT_STARTED, "mission session has not started")
    if session.mission_id != mission_id or session.attempt_number != attempt_number:
        raise MissionRuntimeError(RuntimeErrorCode.ATTEMPT_CONFLICT, "mission or attempt does not match active session")
    return session


def _next_attempt_kind(action: NextAction | None) -> AttemptKind:
    if action is None: return AttemptKind.INITIAL
    return {"prerequisite_support": AttemptKind.PREREQUISITE_SUPPORTED, "focused_retry": AttemptKind.RETRY, "review": AttemptKind.REVIEW}.get(action.kind.value, AttemptKind.INITIAL)


def start_mission(root, learner_id, campaign_id, expected_revision: int, mission_id: str, content: MissionContent) -> RuntimeSnapshot:
    valid = validate_mission_content(content)
    if not valid.valid:
        raise MissionRuntimeError(RuntimeErrorCode.INVALID_CONTENT, "invalid mission content", valid.issues)
    def transform(state):
        plan_by_id = {plan.id: plan for plan in state.mission_plans}
        if mission_id not in plan_by_id:
            raise MissionRuntimeError(RuntimeErrorCode.MISSION_NOT_FOUND, "mission does not exist")
        if content.capability != plan_by_id[mission_id].capability:
            raise MissionRuntimeError(RuntimeErrorCode.INVALID_CONTENT, "content capability does not match mission")
        kind = AttemptKind.INITIAL
        if state.active_session is not None:
            previous = state.active_session
            if previous.checkpoint is not MissionCheckpoint.ASSESSED or previous.next_action is None:
                raise MissionRuntimeError(RuntimeErrorCode.INVALID_TRANSITION, "an active mission session already exists")
            action = previous.next_action
            if action.mission_id is None:
                return replace(state, active_session=None)
            if action.mission_id != mission_id:
                raise MissionRuntimeError(RuntimeErrorCode.INVALID_TRANSITION, "mission does not match persisted next action")
            kind = _next_attempt_kind(action)
            if next(item for item in state.campaign.missions if item.id == mission_id).status is MissionStatus.REVIEW_DUE:
                kind = AttemptKind.REVIEW
        else:
            # Initial activation uses the same stable priority/prerequisite order
            # shown by setup, filtered by already-demonstrated capabilities.
            from .roadmaps import next_priority_ids

            statuses = {item.id: item.status for item in state.campaign.missions}
            eligible = next(
                (
                    item for item in next_priority_ids(
                        state.roadmap, state.mission_plans, len(state.mission_plans)
                    )
                    if statuses[item] is not MissionStatus.DEMONSTRATED
                    and all(
                        statuses[prerequisite] is MissionStatus.DEMONSTRATED
                        for prerequisite in plan_by_id[item].prerequisite_ids
                    )
                ),
                None,
            )
            if eligible != mission_id:
                raise MissionRuntimeError(RuntimeErrorCode.INVALID_TRANSITION, "mission is not the next eligible mission")
        prior = [item.attempt_number for item in state.mission_attempts if item.mission_id == mission_id]
        return replace(state, active_session=ActiveMissionSession(mission_id, max(prior, default=0) + 1, kind, MissionCheckpoint.TEACHING, DifficultyAdjustment.STANDARD, content))
    def duplicate(state):
        session = state.active_session
        return (
            state.revision == expected_revision + 1
            and session is not None
            and session.mission_id == mission_id
            and session.checkpoint is MissionCheckpoint.TEACHING
            and session.content == content
        )
    return _snapshot(_mutate(root, learner_id, campaign_id, expected_revision, transform, idempotent_if=duplicate))


def advance_mission(root, learner_id, campaign_id, expected_revision: int, mission_id: str, attempt_number: int, replacement_content: MissionContent | None = None) -> RuntimeSnapshot:
    def transform(state):
        session = _expected_session(state, mission_id, attempt_number)
        if session.checkpoint is MissionCheckpoint.TEACHING:
            if replacement_content is not None: raise MissionRuntimeError(RuntimeErrorCode.INVALID_TRANSITION, "replacement content is only allowed before check ready")
            return replace(state, active_session=replace(session, checkpoint=MissionCheckpoint.GUIDED_PRACTICE))
        if session.checkpoint is MissionCheckpoint.GUIDED_PRACTICE:
            if session.content_refresh_required:
                if replacement_content is None or not validate_mission_content(replacement_content).valid:
                    raise MissionRuntimeError(RuntimeErrorCode.INVALID_CONTENT, "adjusted content is required")
                expected_capability = session.content.capability
                plan_capability = next(
                    plan.capability for plan in state.mission_plans
                    if plan.id == session.mission_id
                )
                if (
                    replacement_content.capability != expected_capability
                    or replacement_content.capability != plan_capability
                ):
                    raise MissionRuntimeError(RuntimeErrorCode.INVALID_CONTENT, "replacement content capability does not match active mission")
                session = replace(session, content=replacement_content, content_refresh_required=False)
            elif replacement_content is not None:
                raise MissionRuntimeError(RuntimeErrorCode.INVALID_TRANSITION, "replacement content is not required")
            return replace(state, active_session=replace(session, checkpoint=MissionCheckpoint.CHECK_READY))
        if session.checkpoint is MissionCheckpoint.ASSESSED and session.next_action and session.next_action.mission_id is None:
            return replace(state, active_session=None)
        raise MissionRuntimeError(RuntimeErrorCode.INVALID_TRANSITION, "checkpoint cannot advance")
    def duplicate(state):
        session = state.active_session
        if state.revision != expected_revision + 1 or session is None:
            return False
        if session.mission_id != mission_id or session.attempt_number != attempt_number:
            return False
        if session.checkpoint is MissionCheckpoint.GUIDED_PRACTICE:
            return replacement_content is None
        if session.checkpoint is MissionCheckpoint.CHECK_READY:
            return (
                not session.content_refresh_required
                and (replacement_content is None or session.content == replacement_content)
            )
        return False
    return _snapshot(_mutate(root, learner_id, campaign_id, expected_revision, transform, idempotent_if=duplicate))


def adjust_difficulty(root, learner_id, campaign_id, expected_revision: int, mission_id: str, attempt_number: int, adjustment: DifficultyAdjustment) -> RuntimeSnapshot:
    if not isinstance(adjustment, DifficultyAdjustment) or adjustment not in (DifficultyAdjustment.HARDER, DifficultyAdjustment.PREREQUISITE_SUPPORT):
        raise MissionRuntimeError(RuntimeErrorCode.INVALID_REQUEST, "adjustment must be harder or prerequisite_support")
    def transform(state):
        session = _expected_session(state, mission_id, attempt_number)
        if session.checkpoint is MissionCheckpoint.ASSESSED:
            raise MissionRuntimeError(RuntimeErrorCode.INVALID_TRANSITION, "cannot adjust an assessed mission")
        checkpoint = MissionCheckpoint.GUIDED_PRACTICE if session.checkpoint is MissionCheckpoint.CHECK_READY else session.checkpoint
        return replace(
            state,
            active_session=replace(
                session,
                adjustment=adjustment,
                checkpoint=checkpoint,
                content_refresh_required=True,
            ),
        )
    def duplicate(state):
        session = state.active_session
        return (
            state.revision == expected_revision + 1
            and session is not None
            and session.mission_id == mission_id
            and session.attempt_number == attempt_number
            and session.adjustment is adjustment
            and session.content_refresh_required
        )
    return _snapshot(_mutate(root, learner_id, campaign_id, expected_revision, transform, idempotent_if=duplicate))


def return_to_practice(
    root,
    learner_id,
    campaign_id,
    expected_revision: int,
    mission_id: str,
    attempt_number: int,
) -> RuntimeSnapshot:
    """Invalidate a helped check without recording assessment evidence."""
    def duplicate(state):
        session = _expected_session(state, mission_id, attempt_number)
        return (
            state.revision == expected_revision + 1
            and session.checkpoint is MissionCheckpoint.GUIDED_PRACTICE
            and session.content_refresh_required
        )

    def transform(state):
        session = _expected_session(state, mission_id, attempt_number)
        if session.checkpoint is not MissionCheckpoint.CHECK_READY:
            raise MissionRuntimeError(
                RuntimeErrorCode.INVALID_TRANSITION,
                "only a ready check can return to practice",
            )
        return replace(
            state,
            active_session=replace(
                session,
                checkpoint=MissionCheckpoint.GUIDED_PRACTICE,
                content_refresh_required=True,
            ),
        )

    return _snapshot(
        _mutate(
            root,
            learner_id,
            campaign_id,
            expected_revision,
            transform,
            idempotent_if=duplicate,
        )
    )


def _with_status(campaign, mission_id, outcome, kind):
    missions = []
    for mission in campaign.missions:
        if mission.id != mission_id: missions.append(mission); continue
        if outcome is MissionOutcome.PASS: status = MissionStatus.DEMONSTRATED
        elif mission.status in (MissionStatus.DEMONSTRATED, MissionStatus.REVIEW_DUE) or kind is AttemptKind.REVIEW: status = MissionStatus.REVIEW_DUE
        else: status = MissionStatus.DEVELOPING
        missions.append(replace(mission, status=status))
    return campaign.with_missions(tuple(missions))


def submit_assessment(root, learner_id, campaign_id, expected_revision: int, mission_id: str, attempt_number: int, criterion_scores: tuple[CriterionScore, ...], independent: bool, modality: str, result_statement: str, *, now=None) -> RuntimeSnapshot:
    if independent is not True: raise MissionRuntimeError(RuntimeErrorCode.INDEPENDENCE_REQUIRED, "independent assessment is required")
    if type(criterion_scores) is not tuple or any(not isinstance(item, CriterionScore) for item in criterion_scores):
        raise MissionRuntimeError(RuntimeErrorCode.INVALID_REQUEST, "criterion_scores must contain criterion score records")
    if not isinstance(modality, str) or not modality.strip():
        raise MissionRuntimeError(RuntimeErrorCode.INVALID_REQUEST, "modality must be non-empty")
    if not isinstance(result_statement, str) or not result_statement.strip():
        raise MissionRuntimeError(RuntimeErrorCode.INVALID_REQUEST, "result_statement must be non-empty")
    def duplicate(state):
        for item in state.mission_attempts:
            if (item.mission_id, item.attempt_number) == (mission_id, attempt_number):
                if item.criterion_scores == criterion_scores and item.modality == modality and item.result_statement == result_statement:
                    return state.revision == expected_revision + 1
                raise MissionRuntimeError(RuntimeErrorCode.DUPLICATE_CONFLICT, "assessment differs from stored attempt")
        return False
    def transform(state):
        session = _expected_session(state, mission_id, attempt_number)
        if session.checkpoint is not MissionCheckpoint.CHECK_READY:
            raise MissionRuntimeError(RuntimeErrorCode.ASSESSMENT_NOT_READY, "assessment requires check ready")
        when = (now or (lambda: datetime.now(timezone.utc)))()
        if when.tzinfo is None or when.utcoffset() is None:
            raise MissionRuntimeError(RuntimeErrorCode.INVALID_REQUEST, "service clock must return an aware datetime")
        score_ids = tuple(item.criterion_id for item in criterion_scores)
        rubric_ids = {item.id for item in session.content.rubric}
        if len(score_ids) != len(set(score_ids)) or set(score_ids) != rubric_ids:
            raise MissionRuntimeError(
                RuntimeErrorCode.INVALID_REQUEST,
                "criterion score coverage must exactly match rubric",
            )
        score = derive_score(session.content.rubric, criterion_scores)
        outcome = outcome_for_score(score)
        attempt = MissionAttemptRecord(mission_id, attempt_number, session.kind, session.content.rubric, criterion_scores, score, outcome, modality, result_statement, when)
        campaign = _with_status(state.campaign, mission_id, outcome, session.kind)
        completed_reviews = state.completed_review_phase_ids
        phase_by_mission = {item: phase for phase in state.roadmap.phases for item in phase.mission_ids}
        phase = phase_by_mission[mission_id]
        if session.kind is AttemptKind.REVIEW and outcome is MissionOutcome.PASS:
            critical = [item for item in phase.mission_ids if next(plan for plan in state.mission_plans if plan.id == item).priority.value == "critical"]
            statuses = {item.id: item.status for item in campaign.missions}
            if phase.id not in completed_reviews and all(statuses[item] is MissionStatus.DEMONSTRATED for item in critical):
                completed_reviews = (*completed_reviews, phase.id)
        elif outcome is MissionOutcome.PASS and phase.planned_review_after and phase.id not in completed_reviews:
            critical = [item for item in phase.mission_ids if next(plan for plan in state.mission_plans if plan.id == item).priority.value == "critical"]
            statuses = {item.id: item.status for item in campaign.missions}
            if critical and all(statuses[item] is MissionStatus.DEMONSTRATED for item in critical):
                campaign = campaign.with_missions(tuple(replace(item, status=MissionStatus.REVIEW_DUE) if item.id in critical else item for item in campaign.missions))
        assessed_session = replace(session, checkpoint=MissionCheckpoint.ASSESSED, adjustment=DifficultyAdjustment.STANDARD, latest_outcome=outcome)
        action = select_next_action(campaign, state.mission_plans, state.roadmap, completed_reviews, session, outcome)
        roadmap = state.roadmap
        if action.target_phase_id and roadmap and next(index for index, phase in enumerate(roadmap.phases) if phase.id == action.target_phase_id) > next(index for index, phase in enumerate(roadmap.phases) if phase.id == roadmap.active_phase_id):
            roadmap = replace(roadmap, active_phase_id=action.target_phase_id)
        return replace(
            state,
            campaign=campaign,
            assessment_evidence=(*state.assessment_evidence, AssessmentEvidence(mission_id, score, True, modality, when)),
            mission_attempts=(*state.mission_attempts, attempt),
            roadmap=roadmap,
            completed_review_phase_ids=completed_reviews,
            active_session=replace(assessed_session, next_action=action),
        )
    return _snapshot(_mutate(root, learner_id, campaign_id, expected_revision, transform, idempotent_if=duplicate))

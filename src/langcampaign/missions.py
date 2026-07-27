from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .models import _require_non_empty_string


class MissionPriority(StrEnum):
    CRITICAL = "critical"
    SUPPORTING = "supporting"
    ENRICHMENT = "enrichment"


@dataclass(frozen=True)
class PracticeActivity:
    kind: str
    instructions: str

    def __post_init__(self) -> None:
        _require_non_empty_string(self.kind, "practice kind")
        _require_non_empty_string(self.instructions, "practice instructions")


@dataclass(frozen=True)
class AssessmentScenario:
    prompt: str
    success_criteria: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string(self.prompt, "assessment prompt")
        if not self.success_criteria:
            raise ValueError("success_criteria must not be empty")
        for criterion in self.success_criteria:
            _require_non_empty_string(criterion, "success criterion")


@dataclass(frozen=True)
class MissionPlan:
    id: str
    title: str
    capability: str
    rationale: str
    priority: MissionPriority
    prerequisite_ids: tuple[str, ...]
    target_vocabulary: tuple[str, ...]
    target_structures: tuple[str, ...]
    register_notes: tuple[str, ...]
    cultural_context: tuple[str, ...]
    practice: tuple[PracticeActivity, ...]
    assessment: AssessmentScenario
    common_failure_patterns: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "mission plan id"),
            (self.title, "mission plan title"),
            (self.capability, "capability"),
            (self.rationale, "rationale"),
        ):
            _require_non_empty_string(value, name)
        if not isinstance(self.priority, MissionPriority):
            raise ValueError("priority must be a MissionPriority")
        if not self.practice:
            raise ValueError("practice must not be empty")
        for values, name in (
            (self.prerequisite_ids, "prerequisite id"),
            (self.target_vocabulary, "target vocabulary"),
            (self.target_structures, "target structure"),
            (self.register_notes, "register note"),
            (self.cultural_context, "cultural context"),
            (self.common_failure_patterns, "failure pattern"),
        ):
            for value in values:
                _require_non_empty_string(value, name)


def validate_mission_map(
    plans: tuple[MissionPlan, ...], readiness_ids: tuple[str, ...]
) -> None:
    plan_ids = tuple(plan.id for plan in plans)
    if len(plan_ids) != len(set(plan_ids)):
        raise ValueError("mission plan ids must be unique")
    if set(plan_ids) != set(readiness_ids) or len(plan_ids) != len(readiness_ids):
        raise ValueError("mission plan ids must match readiness mission ids")

    known = set(plan_ids)
    if any(
        prerequisite not in known
        for plan in plans
        for prerequisite in plan.prerequisite_ids
    ):
        raise ValueError("mission prerequisite does not exist")

    graph = {plan.id: plan.prerequisite_ids for plan in plans}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(mission_id: str) -> None:
        if mission_id in visiting:
            raise ValueError("mission prerequisites must be acyclic")
        if mission_id in visited:
            return
        visiting.add(mission_id)
        for prerequisite in graph[mission_id]:
            visit(prerequisite)
        visiting.remove(mission_id)
        visited.add(mission_id)

    for mission_id in plan_ids:
        visit(mission_id)

    if not any(plan.priority is MissionPriority.CRITICAL for plan in plans):
        raise ValueError("mission map must contain a critical mission")

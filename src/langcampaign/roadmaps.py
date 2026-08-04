from __future__ import annotations

from dataclasses import dataclass

from .missions import MissionPlan, MissionPriority
from .models import _require_non_empty_string, _require_nonnegative_integer


def _require_tuple(value: object, name: str) -> None:
    if type(value) is not tuple:
        raise ValueError(f"{name} must be a tuple")


@dataclass(frozen=True)
class RoadmapPhase:
    id: str
    title: str
    capability_summary: str
    mission_ids: tuple[str, ...]
    planned_review_after: bool
    planned_simulation_after: bool

    def __post_init__(self) -> None:
        _require_non_empty_string(self.id, "roadmap phase id")
        _require_non_empty_string(self.title, "roadmap phase title")
        _require_non_empty_string(self.capability_summary, "capability summary")
        _require_tuple(self.mission_ids, "mission_ids")
        if type(self.planned_review_after) is not bool:
            raise ValueError("planned_review_after must be a bool")
        if type(self.planned_simulation_after) is not bool:
            raise ValueError("planned_simulation_after must be a bool")
        if len(self.mission_ids) != len(set(self.mission_ids)):
            raise ValueError("mission ids must be unique within a roadmap phase")
        for mission_id in self.mission_ids:
            _require_non_empty_string(mission_id, "roadmap mission id")


@dataclass(frozen=True)
class CampaignRoadmap:
    phases: tuple[RoadmapPhase, ...]
    active_phase_id: str
    assumptions: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_tuple(self.phases, "phases")
        _require_tuple(self.assumptions, "assumptions")
        if not self.phases:
            raise ValueError("roadmap phases must not be empty")
        _require_non_empty_string(self.active_phase_id, "active_phase_id")
        for phase in self.phases:
            if not isinstance(phase, RoadmapPhase):
                raise ValueError("roadmap phase must be a RoadmapPhase")
        phase_ids = tuple(phase.id for phase in self.phases)
        if len(phase_ids) != len(set(phase_ids)):
            raise ValueError("roadmap phase ids must be unique")
        for assumption in self.assumptions:
            _require_non_empty_string(assumption, "roadmap assumption")


def _validate_inputs(
    roadmap: object, plans: object
) -> tuple[CampaignRoadmap, tuple[MissionPlan, ...]]:
    if not isinstance(roadmap, CampaignRoadmap):
        raise ValueError("roadmap must be a CampaignRoadmap")
    _require_tuple(plans, "plans")
    for plan in plans:
        if not isinstance(plan, MissionPlan):
            raise ValueError("plan must be a MissionPlan")
    return roadmap, plans


def validate_roadmap(
    roadmap: CampaignRoadmap, plans: tuple[MissionPlan, ...]
) -> None:
    roadmap, plans = _validate_inputs(roadmap, plans)
    phase_ids = {phase.id for phase in roadmap.phases}
    if roadmap.active_phase_id not in phase_ids:
        raise ValueError("active phase must exist")

    plan_ids = tuple(plan.id for plan in plans)
    if len(plan_ids) != len(set(plan_ids)):
        raise ValueError("mission plan ids must be unique")
    roadmap_ids = tuple(
        mission_id for phase in roadmap.phases for mission_id in phase.mission_ids
    )
    if any(mission_id not in plan_ids for mission_id in roadmap_ids):
        raise ValueError("roadmap mission ids must exist")
    if len(roadmap_ids) != len(set(roadmap_ids)):
        raise ValueError("roadmap mission ids must be unique across phases")
    if set(roadmap_ids) != set(plan_ids) or len(roadmap_ids) != len(plan_ids):
        raise ValueError("roadmap must contain every mission plan exactly once")

    phase_by_mission = {
        mission_id: phase_index
        for phase_index, phase in enumerate(roadmap.phases)
        for mission_id in phase.mission_ids
    }
    for plan in plans:
        for prerequisite_id in plan.prerequisite_ids:
            if prerequisite_id not in phase_by_mission:
                raise ValueError("mission prerequisite does not exist")
            if phase_by_mission[prerequisite_id] > phase_by_mission[plan.id]:
                raise ValueError(
                    "mission prerequisites must not be in later phases"
                )


def _require_count(count: object) -> int:
    _require_nonnegative_integer(count, "count")
    return count


def next_priority_ids(
    roadmap: CampaignRoadmap,
    plans: tuple[MissionPlan, ...],
    count: int = 3,
) -> tuple[str, ...]:
    validate_roadmap(roadmap, plans)
    count = _require_count(count)
    active = next(
        phase for phase in roadmap.phases if phase.id == roadmap.active_phase_id
    )
    by_id = {plan.id: plan for plan in plans}
    priority_order = {
        MissionPriority.CRITICAL: 0,
        MissionPriority.SUPPORTING: 1,
        MissionPriority.ENRICHMENT: 2,
    }
    declared_order = {
        mission_id: index for index, mission_id in enumerate(active.mission_ids)
    }
    active_phase_index = roadmap.phases.index(active)
    satisfied = {
        mission_id
        for phase in roadmap.phases[:active_phase_index]
        for mission_id in phase.mission_ids
    }
    remaining = list(active.mission_ids)
    ordered_ids = []
    while remaining:
        available = [
            mission_id
            for mission_id in remaining
            if all(
                prerequisite_id in satisfied
                for prerequisite_id in by_id[mission_id].prerequisite_ids
            )
        ]
        if not available:
            raise ValueError("active roadmap prerequisites must be acyclic")
        mission_id = min(
            available,
            key=lambda item: (
                priority_order[by_id[item].priority],
                declared_order[item],
            ),
        )
        ordered_ids.append(mission_id)
        satisfied.add(mission_id)
        remaining.remove(mission_id)
    return tuple(ordered_ids[:count])


def next_priorities(
    roadmap: CampaignRoadmap,
    plans: tuple[MissionPlan, ...],
    count: int = 3,
) -> tuple[str, ...]:
    validate_roadmap(roadmap, plans)
    priority_ids = next_priority_ids(roadmap, plans, count)
    by_id = {plan.id: plan for plan in plans}
    return tuple(by_id[mission_id].title for mission_id in priority_ids)


def render_roadmap_summary(
    roadmap: CampaignRoadmap, plans: tuple[MissionPlan, ...]
) -> str:
    validate_roadmap(roadmap, plans)
    lines = ["CAMPAIGN ROADMAP"]
    for phase in roadmap.phases:
        marker = " (current)" if phase.id == roadmap.active_phase_id else ""
        lines.append(f"- {phase.title}{marker}: {phase.capability_summary}")
    return "\n".join(lines)

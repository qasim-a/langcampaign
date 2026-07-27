# Campaign Content and State Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add validated mission content, a coarse internal roadmap, repository-local learner state, and a JSON command boundary that later Codex skills can use without editing JSON directly.

**Architecture:** New immutable content records remain separate from the existing readiness-oriented `Mission` record but share mission identifiers. `CampaignState` schema version 3 owns learner identity, mission plans, the internal roadmap, and assessment evidence while retaining version-1/2 compatibility. A pure learner repository resolves paths and campaign selection; a thin CLI exposes validation, setup, listing, and state inspection as stable JSON envelopes.

**Tech Stack:** Python 3.11+, standard-library `dataclasses`, `json`, `argparse`, `pathlib`, and existing atomic storage; `pytest` 8+

## Delivery decomposition

This is plan 1 of 4 for the approved Codex vertical slice:

1. **This plan:** campaign content, roadmap, learner state, and command foundation.
2. **Next:** deterministic planner, setup interview output, campaign brief, and roadmap adaptation.
3. **Then:** rubric assessment, review scheduling, teaching-session transactions, and simulations.
4. **Finally:** six Codex skills, bootstrap/health check, transcript fixtures, and operational README.

Each plan produces independently usable and tested software. Claude and other adapters remain outside this vertical slice.

## Global Constraints

- Mission titles describe observable capabilities, not textbook topics.
- The internal roadmap is coarse, persisted, hidden by default, and revealable as a learner-readable summary.
- The learner-facing view exposes exactly the next three priorities and one immediately actionable mission when at least that many priorities exist.
- Agent instructions and later Codex skills must never calculate readiness or edit learner JSON directly.
- Learner state is repository-local, versioned, validated, and written atomically.
- Existing schema-version 1 and 2 files remain loadable.
- Balanced curriculum, Supportive coaching, and Flexible campaigns remain defaults.
- No runtime dependency may be added.
- Existing public APIs remain backward compatible.
- Python 3.11 is the minimum supported version.

## File map

- `src/langcampaign/missions.py` — mission-content and assessment-scenario records plus graph validation.
- `src/langcampaign/roadmaps.py` — coarse roadmap phases, current position, and learner-readable summary.
- `src/langcampaign/storage.py` — schema-version 3 campaign-state serialization with v1/v2 migration.
- `src/langcampaign/learners.py` — safe learner identifiers, paths, listing, and campaign selection.
- `src/langcampaign/cli.py` — JSON command envelopes and command dispatch.
- `src/langcampaign/__main__.py` — `python -m langcampaign` entrypoint.
- `src/langcampaign/__init__.py` — public exports for new records and services.
- `.gitignore` — learner data exclusion.
- `learners/.gitkeep` — repository-local learner-data root.
- `tests/test_missions.py`, `tests/test_roadmaps.py`, `tests/test_learners.py`, `tests/test_cli.py` — focused new tests.
- `tests/test_storage.py`, `tests/test_campaign_flow.py` — persistence compatibility and integration.

---

### Task 1: Validated mission-content model

**Files:**
- Create: `src/langcampaign/missions.py`
- Create: `tests/__init__.py`
- Create: `tests/test_missions.py`

**Interfaces:**
- Consumes: existing mission identifiers from `models.Mission`.
- Produces: `MissionPriority`, `PracticeActivity`, `AssessmentScenario`, `MissionPlan`, and `validate_mission_map(plans: tuple[MissionPlan, ...], readiness_ids: tuple[str, ...]) -> None`.
- `MissionPlan.id` must match one readiness mission identifier exactly.

- [ ] **Step 1: Write failing tests for observable, linked mission plans**

Create an empty `tests/__init__.py` so later plan tasks can import the exact
fixture builders defined by earlier tasks.

```python
# tests/test_missions.py
import pytest

from langcampaign.missions import (
    AssessmentScenario,
    MissionPlan,
    MissionPriority,
    PracticeActivity,
    validate_mission_map,
)


def delayed_arrival(**changes):
    values = {
        "id": "delayed-arrival",
        "title": "Explain a delayed arrival",
        "capability": "Notify a hotel of a late arrival and answer one follow-up.",
        "rationale": "The learner expects to travel by train before hotel check-in.",
        "priority": MissionPriority.CRITICAL,
        "prerequisite_ids": (),
        "target_vocabulary": ("retraso", "llegar"),
        "target_structures": ("Voy a llegar a...",),
        "register_notes": ("Use polite usted forms with hotel staff.",),
        "cultural_context": (),
        "practice": (
            PracticeActivity("guided", "Complete two delayed-arrival messages."),
        ),
        "assessment": AssessmentScenario(
            prompt="Tell the hotel your train is late and answer when you will arrive.",
            success_criteria=(
                "States that the train is delayed.",
                "Provides a revised arrival time.",
                "Answers one unfamiliar follow-up without a hint.",
            ),
        ),
        "common_failure_patterns": ("States the delay but omits the new time.",),
    }
    values.update(changes)
    return MissionPlan(**values)


def test_valid_mission_map_links_content_to_readiness_missions():
    plan = delayed_arrival()
    validate_mission_map((plan,), ("delayed-arrival",))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"capability": "Learn the future tense"}, "capability must describe an observable action"),
        ({"practice": ()}, "practice must not be empty"),
        (
            {"assessment": AssessmentScenario("Respond appropriately.", ())},
            "success_criteria must not be empty",
        ),
    ],
)
def test_mission_plan_rejects_unassessable_content(changes, message):
    with pytest.raises(ValueError, match=message):
        delayed_arrival(**changes)


def test_mission_map_requires_exactly_one_plan_per_readiness_mission():
    with pytest.raises(ValueError, match="mission plan ids must match readiness mission ids"):
        validate_mission_map((delayed_arrival(),), ("delayed-arrival", "hotel-check-in"))


def test_mission_map_rejects_missing_and_circular_prerequisites():
    first = delayed_arrival(prerequisite_ids=("hotel-check-in",))
    second = delayed_arrival(
        id="hotel-check-in",
        title="Complete a hotel check-in",
        capability="Complete a hotel check-in and respond to a reservation question.",
        prerequisite_ids=("delayed-arrival",),
    )
    with pytest.raises(ValueError, match="mission prerequisites must be acyclic"):
        validate_mission_map((first, second), ("delayed-arrival", "hotel-check-in"))
```

- [ ] **Step 2: Run the mission tests and verify the module is absent**

Run: `python -m pytest tests/test_missions.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'langcampaign.missions'`.

- [ ] **Step 3: Implement immutable mission content and graph validation**

```python
# src/langcampaign/missions.py
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
        if not any(token in self.capability.lower() for token in (
            "ask", "answer", "complete", "explain", "follow", "notify",
            "read", "respond", "understand", "write",
        )):
            raise ValueError("capability must describe an observable action")
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
    if any(prerequisite not in known for plan in plans for prerequisite in plan.prerequisite_ids):
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
```

- [ ] **Step 4: Run focused and full tests**

Run: `python -m pytest tests/test_missions.py -v`

Expected: `6 passed`.

Run: `python -m pytest -v`

Expected: existing 90 tests plus the new mission tests pass.

- [ ] **Step 5: Commit mission content**

```bash
git add src/langcampaign/missions.py tests/__init__.py tests/test_missions.py
git commit -m "feat: add validated mission content"
```

---

### Task 2: Coarse internal campaign roadmap

**Files:**
- Create: `src/langcampaign/roadmaps.py`
- Create: `tests/test_roadmaps.py`

**Interfaces:**
- Consumes: `MissionPlan` identifiers and priorities from Task 1.
- Produces: `RoadmapPhase`, `CampaignRoadmap`, `validate_roadmap(roadmap, plans)`, `next_priorities(roadmap, plans, count=3)`, and `render_roadmap_summary(roadmap, plans) -> str`.

- [ ] **Step 1: Write failing roadmap validation and visibility tests**

```python
# tests/test_roadmaps.py
import pytest

from langcampaign.missions import MissionPriority
from langcampaign.roadmaps import (
    CampaignRoadmap,
    RoadmapPhase,
    next_priorities,
    render_roadmap_summary,
    validate_roadmap,
)
from tests.test_missions import delayed_arrival


def roadmap():
    return CampaignRoadmap(
        phases=(
            RoadmapPhase(
                id="core-transactions",
                title="Core transactions",
                capability_summary="Handle routine hotel and transport exchanges.",
                mission_ids=("delayed-arrival", "hotel-check-in", "train-options"),
                planned_review_after=True,
                planned_simulation_after=False,
            ),
            RoadmapPhase(
                id="problem-recovery",
                title="Problem recovery",
                capability_summary="Correct misunderstandings and request alternatives.",
                mission_ids=(),
                planned_review_after=True,
                planned_simulation_after=True,
            ),
        ),
        active_phase_id="core-transactions",
        assumptions=("The learner can read Latin script.",),
    )


def plans():
    return (
        delayed_arrival(),
        delayed_arrival(
            id="hotel-check-in",
            title="Complete a hotel check-in",
            capability="Complete a hotel check-in and answer a reservation question.",
            priority=MissionPriority.CRITICAL,
        ),
        delayed_arrival(
            id="train-options",
            title="Ask for another train",
            capability="Ask for another train and understand the departure time.",
            priority=MissionPriority.SUPPORTING,
        ),
    )


def test_roadmap_is_valid_and_exposes_only_next_three_priorities():
    current = roadmap()
    current_plans = plans()
    validate_roadmap(current, current_plans)
    assert next_priorities(current, current_plans) == (
        "Explain a delayed arrival",
        "Complete a hotel check-in",
        "Ask for another train",
    )


def test_roadmap_summary_is_revealable_without_internal_assumptions():
    output = render_roadmap_summary(roadmap(), plans())
    assert "Core transactions (current)" in output
    assert "Problem recovery" in output
    assert "The learner can read Latin script" not in output


def test_roadmap_rejects_unknown_active_phase_and_unknown_detailed_mission():
    with pytest.raises(ValueError, match="active phase must exist"):
        validate_roadmap(
            CampaignRoadmap(roadmap().phases, "missing", ()),
            plans(),
        )
    broken = CampaignRoadmap(
        (
            RoadmapPhase(
                "core", "Core", "Handle core exchanges.", ("unknown",), False, False
            ),
        ),
        "core",
        (),
    )
    with pytest.raises(ValueError, match="roadmap mission ids must exist"):
        validate_roadmap(broken, plans())
```

- [ ] **Step 2: Run roadmap tests and verify the module is absent**

Run: `python -m pytest tests/test_roadmaps.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'langcampaign.roadmaps'`.

- [ ] **Step 3: Implement the roadmap records and learner-readable view**

```python
# src/langcampaign/roadmaps.py
from dataclasses import dataclass

from .missions import MissionPlan, MissionPriority
from .models import _require_non_empty_string


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
        if len(self.mission_ids) != len(set(self.mission_ids)):
            raise ValueError("mission ids must be unique within a roadmap phase")


@dataclass(frozen=True)
class CampaignRoadmap:
    phases: tuple[RoadmapPhase, ...]
    active_phase_id: str
    assumptions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.phases:
            raise ValueError("roadmap phases must not be empty")
        _require_non_empty_string(self.active_phase_id, "active_phase_id")
        phase_ids = tuple(phase.id for phase in self.phases)
        if len(phase_ids) != len(set(phase_ids)):
            raise ValueError("roadmap phase ids must be unique")
        for assumption in self.assumptions:
            _require_non_empty_string(assumption, "roadmap assumption")


def validate_roadmap(
    roadmap: CampaignRoadmap, plans: tuple[MissionPlan, ...]
) -> None:
    phase_ids = {phase.id for phase in roadmap.phases}
    if roadmap.active_phase_id not in phase_ids:
        raise ValueError("active phase must exist")
    plan_ids = {plan.id for plan in plans}
    roadmap_ids = [mission_id for phase in roadmap.phases for mission_id in phase.mission_ids]
    if any(mission_id not in plan_ids for mission_id in roadmap_ids):
        raise ValueError("roadmap mission ids must exist")
    if len(roadmap_ids) != len(set(roadmap_ids)):
        raise ValueError("roadmap mission ids must be unique across phases")


def next_priorities(
    roadmap: CampaignRoadmap,
    plans: tuple[MissionPlan, ...],
    count: int = 3,
) -> tuple[str, ...]:
    active = next(phase for phase in roadmap.phases if phase.id == roadmap.active_phase_id)
    by_id = {plan.id: plan for plan in plans}
    candidates = [by_id[item] for item in active.mission_ids]
    order = {
        MissionPriority.CRITICAL: 0,
        MissionPriority.SUPPORTING: 1,
        MissionPriority.ENRICHMENT: 2,
    }
    candidates.sort(key=lambda item: (order[item.priority], active.mission_ids.index(item.id)))
    return tuple(item.title for item in candidates[:count])


def render_roadmap_summary(
    roadmap: CampaignRoadmap, plans: tuple[MissionPlan, ...]
) -> str:
    lines = ["CAMPAIGN ROADMAP"]
    for phase in roadmap.phases:
        marker = " (current)" if phase.id == roadmap.active_phase_id else ""
        lines.append(f"- {phase.title}{marker}: {phase.capability_summary}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run roadmap and mission tests**

Run: `python -m pytest tests/test_missions.py tests/test_roadmaps.py -v`

Expected: all mission and roadmap tests pass.

- [ ] **Step 5: Commit the internal roadmap**

```bash
git add src/langcampaign/roadmaps.py tests/test_roadmaps.py
git commit -m "feat: add adaptive campaign roadmap"
```

---

### Task 3: Schema-version 3 learner campaign state

**Files:**
- Modify: `src/langcampaign/storage.py`
- Modify: `src/langcampaign/__init__.py`
- Modify: `tests/test_storage.py`
- Modify: `tests/test_campaign_flow.py`

**Interfaces:**
- Consumes: `MissionPlan`, `CampaignRoadmap`, existing `Campaign`, and `AssessmentEvidence`.
- Changes `CampaignState` additively with defaulted fields: `learner_id: str = "default"`, `mission_plans: tuple[MissionPlan, ...] = ()`, `roadmap: CampaignRoadmap | None = None`.
- Produces schema version 3 through `save_campaign_state`; `load_campaign_state` migrates versions 1 and 2 to defaulted new fields.

- [ ] **Step 1: Write failing version-3 round-trip and migration tests**

Add to `tests/test_storage.py`:

```python
def test_version_three_state_round_trips_learner_content_and_roadmap(tmp_path):
    from langcampaign.missions import validate_mission_map
    from langcampaign.roadmaps import RoadmapPhase, validate_roadmap
    from tests.test_missions import delayed_arrival
    from tests.test_roadmaps import roadmap

    campaign = new_campaign("Handle hotel delays", "Spanish").with_missions(
        (Mission("delayed-arrival", "Explain a delayed arrival"),)
    )
    mission_plans = (delayed_arrival(),)
    stored_roadmap = replace(
        roadmap(),
        phases=(
            RoadmapPhase(
                "core-transactions",
                "Core transactions",
                "Handle routine hotel exchanges.",
                ("delayed-arrival",),
                True,
                False,
            ),
        ),
    )
    state = CampaignState(
        campaign=campaign,
        learner_id="qasim",
        mission_plans=mission_plans,
        roadmap=stored_roadmap,
    )
    path = tmp_path / "state.json"

    save_campaign_state(path, state)
    loaded = load_campaign_state(path)

    assert loaded == state
    assert json.loads(path.read_text())["schema_version"] == 3
    validate_mission_map(loaded.mission_plans, ("delayed-arrival",))
    validate_roadmap(loaded.roadmap, loaded.mission_plans)


def test_version_two_state_migrates_to_default_content_fields(tmp_path):
    path = tmp_path / "state.json"
    payload = existing_version_two_payload()
    path.write_text(json.dumps(payload))

    loaded = load_campaign_state(path)

    assert loaded.learner_id == "default"
    assert loaded.mission_plans == ()
    assert loaded.roadmap is None


def existing_version_two_payload():
    campaign = new_campaign("Read social media", "Japanese")
    return {
        "schema_version": 2,
        "campaign": storage.campaign_to_dict(campaign),
        "assessment_evidence": [],
    }
```

Update the existing state round-trip assertion from schema version `2` to
schema version `3`; version 2 becomes a read-compatibility fixture, not the
format produced by new saves.

- [ ] **Step 2: Run the new storage tests and verify missing fields/version fail**

Run: `python -m pytest tests/test_storage.py -v`

Expected: version-3 assertions fail because `CampaignState` lacks the new fields and state saves still use schema version 2.

- [ ] **Step 3: Implement version-3 serialization and validated loading**

In `src/langcampaign/storage.py`:

```python
CAMPAIGN_CONTENT_SCHEMA_VERSION = 3
SUPPORTED_SCHEMA_VERSIONS = (
    SCHEMA_VERSION,
    CAMPAIGN_STATE_SCHEMA_VERSION,
    CAMPAIGN_CONTENT_SCHEMA_VERSION,
)


@dataclass(frozen=True)
class CampaignState:
    campaign: Campaign
    assessment_evidence: tuple[AssessmentEvidence, ...] = ()
    learner_id: str = "default"
    mission_plans: tuple[MissionPlan, ...] = ()
    roadmap: CampaignRoadmap | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.learner_id, "learner_id")
        readiness_ids = tuple(mission.id for mission in self.campaign.missions)
        if any(
            item.mission_id not in set(readiness_ids)
            for item in self.assessment_evidence
        ):
            raise ValueError("assessment evidence must reference a campaign mission")
        if self.mission_plans:
            validate_mission_map(self.mission_plans, readiness_ids)
        if self.roadmap is not None:
            if not self.mission_plans:
                raise ValueError("roadmap requires mission plans")
            validate_roadmap(self.roadmap, self.mission_plans)
```

Add explicit conversion helpers for every Task 1 and Task 2 field:

```python
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
```

Implement the inverse helpers using the exact constructors from Tasks 1 and 2:

```python
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
```

Change `save_campaign_state()` to write schema version 3 and these fields:

```python
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
```

Update `_read_envelope()` with exact version-3 envelope checks:

```python
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
```

Parse assessment evidence for both state-bearing versions:

```python
evidence = (
    tuple(
        _assessment_evidence_from_dict(item)
        for item in payload["assessment_evidence"]
    )
    if payload["schema_version"] in (
        CAMPAIGN_STATE_SCHEMA_VERSION,
        CAMPAIGN_CONTENT_SCHEMA_VERSION,
    )
    else ()
)
```

Construct version-3 state with:

```python
return CampaignState(
    campaign=campaign,
    assessment_evidence=evidence,
    learner_id=payload["learner_id"],
    mission_plans=tuple(
        mission_plan_from_dict(item) for item in payload["mission_plans"]
    ),
    roadmap=(
        roadmap_from_dict(payload["roadmap"])
        if payload["roadmap"] is not None
        else None
    ),
)
```

Versions 1 and 2 construct `CampaignState(campaign, evidence)` and therefore
receive the declared default learner ID, empty mission plans, and no roadmap.

- [ ] **Step 4: Run storage and integration tests**

Run: `python -m pytest tests/test_storage.py tests/test_campaign_flow.py -v`

Expected: all persistence and integration tests pass, including version-1/2 migration and version-3 round trip.

Run: `python -m pytest -v`

Expected: the complete suite passes.

- [ ] **Step 5: Export the new records and commit schema version 3**

Export `MissionPlan`, `MissionPriority`, `PracticeActivity`, `AssessmentScenario`, `CampaignRoadmap`, and `RoadmapPhase` from `src/langcampaign/__init__.py` and add them to `__all__`.

```bash
git add src/langcampaign/storage.py src/langcampaign/__init__.py tests/test_storage.py tests/test_campaign_flow.py
git commit -m "feat: persist learner campaign content"
```

---

### Task 4: Repository-local learner and campaign selection

**Files:**
- Create: `src/langcampaign/learners.py`
- Create: `tests/test_learners.py`
- Modify: `.gitignore`
- Create: `learners/.gitkeep`

**Interfaces:**
- Consumes: `CampaignState`, `save_campaign_state`, and `load_campaign_state`.
- Produces: `normalize_learner_id`, `campaign_state_path`, `save_learner_campaign`, `list_learner_campaigns`, and `select_campaign`.

- [ ] **Step 1: Write failing path-safety and selection tests**

```python
# tests/test_learners.py
from pathlib import Path

import pytest

from langcampaign.learners import (
    campaign_state_path,
    list_learner_campaigns,
    normalize_learner_id,
    save_learner_campaign,
    select_campaign,
)
from langcampaign.models import new_campaign
from langcampaign.storage import CampaignState


def state(goal="Text friends", learner="Qasim Ali"):
    return CampaignState(new_campaign(goal, "Spanish"), learner_id=learner)


def test_learner_id_is_normalized_and_cannot_escape_root(tmp_path):
    assert normalize_learner_id(" Qasim Ali ") == "qasim-ali"
    with pytest.raises(ValueError, match="learner_id must contain letters or numbers"):
        normalize_learner_id("../../")
    path = campaign_state_path(tmp_path, "Qasim Ali", "campaign-1")
    assert path == tmp_path / "qasim-ali" / "campaign-1" / "state.json"


def test_repository_lists_and_selects_the_only_campaign(tmp_path):
    stored = state()
    save_learner_campaign(tmp_path, stored)

    campaigns = list_learner_campaigns(tmp_path, "Qasim Ali")

    assert campaigns == ((stored.campaign.id, "Text friends"),)
    assert select_campaign(tmp_path, "Qasim Ali") == stored


def test_selection_never_guesses_between_multiple_campaigns(tmp_path):
    save_learner_campaign(tmp_path, state("Text friends"))
    save_learner_campaign(tmp_path, state("Read social media"))

    with pytest.raises(ValueError, match="campaign selection is ambiguous"):
        select_campaign(tmp_path, "Qasim Ali")
```

- [ ] **Step 2: Run learner tests and verify the module is absent**

Run: `python -m pytest tests/test_learners.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'langcampaign.learners'`.

- [ ] **Step 3: Implement normalized paths and deterministic selection**

```python
# src/langcampaign/learners.py
import re
from pathlib import Path

from .storage import CampaignState, load_campaign_state, save_campaign_state


def normalize_learner_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("learner_id must be a string")
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("learner_id must contain letters or numbers")
    return normalized


def _safe_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise ValueError(f"{name} contains unsafe characters")
    return value


def campaign_state_path(
    root: Path, learner_id: str, campaign_id: str
) -> Path:
    return Path(root) / normalize_learner_id(learner_id) / _safe_id(campaign_id, "campaign_id") / "state.json"


def save_learner_campaign(root: Path, state: CampaignState) -> Path:
    path = campaign_state_path(root, state.learner_id, state.campaign.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_campaign_state(path, state)
    return path


def list_learner_campaigns(
    root: Path, learner_id: str
) -> tuple[tuple[str, str], ...]:
    directory = Path(root) / normalize_learner_id(learner_id)
    if not directory.exists():
        return ()
    entries = []
    for path in sorted(directory.glob("*/state.json")):
        state = load_campaign_state(path)
        entries.append((state.campaign.id, state.campaign.goal))
    return tuple(entries)


def select_campaign(
    root: Path, learner_id: str, campaign_id: str | None = None
) -> CampaignState:
    if campaign_id is not None:
        path = campaign_state_path(root, learner_id, campaign_id)
        if not path.exists():
            raise ValueError("campaign does not exist")
        return load_campaign_state(path)
    available = list_learner_campaigns(root, learner_id)
    if not available:
        raise ValueError("learner has no campaigns")
    if len(available) > 1:
        raise ValueError("campaign selection is ambiguous")
    return load_campaign_state(
        campaign_state_path(root, learner_id, available[0][0])
    )
```

- [ ] **Step 4: Ignore learner state and run tests**

Append to `.gitignore`:

```gitignore
learners/*
!learners/.gitkeep
```

Create an empty `learners/.gitkeep` using `touch learners/.gitkeep` during implementation.

Run: `python -m pytest tests/test_learners.py tests/test_storage.py -v`

Expected: all learner repository and storage tests pass.

- [ ] **Step 5: Commit the learner repository**

```bash
git add src/langcampaign/learners.py tests/test_learners.py .gitignore learners/.gitkeep
git commit -m "feat: add local learner campaign repository"
```

---

### Task 5: Stable JSON command boundary

**Files:**
- Create: `src/langcampaign/cli.py`
- Create: `src/langcampaign/__main__.py`
- Modify: `src/langcampaign/__init__.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: mission/roadmap conversion helpers, `CampaignState`, learner repository services, and existing campaign conversion.
- Produces: `CommandResult`, `run_command(command, payload, learners_root) -> CommandResult`, and `python -m langcampaign`.
- Commands in this plan: `validate-mission-map`, `setup`, `list-campaigns`, `validate-state`, and `show-roadmap`.

- [ ] **Step 1: Write failing command-envelope and rollback tests**

```python
# tests/test_cli.py
import json
import subprocess
import sys

from langcampaign.cli import run_command


def setup_payload():
    return {
        "learner_id": "Qasim Ali",
        "campaign": {
            "goal": "Handle a delayed hotel arrival",
            "target_language": "Spanish",
            "campaign_type": "flexible",
            "missions": [
                {"id": "delayed-arrival", "title": "Explain a delayed arrival", "weight": 1.0}
            ],
        },
        "mission_plans": [
            {
                "id": "delayed-arrival",
                "title": "Explain a delayed arrival",
                "capability": "Notify a hotel of a late arrival and answer one follow-up.",
                "rationale": "The learner will travel by train.",
                "priority": "critical",
                "prerequisite_ids": [],
                "target_vocabulary": ["retraso"],
                "target_structures": ["Voy a llegar a..."],
                "register_notes": ["Use polite forms."],
                "cultural_context": [],
                "practice": [{"kind": "guided", "instructions": "Complete two messages."}],
                "assessment": {
                    "prompt": "Tell the hotel you will arrive late.",
                    "success_criteria": ["Explains the delay.", "Provides a new time."],
                },
                "common_failure_patterns": ["Omits the new time."],
            }
        ],
        "roadmap": {
            "phases": [
                {
                    "id": "core",
                    "title": "Core hotel exchanges",
                    "capability_summary": "Handle routine hotel communication.",
                    "mission_ids": ["delayed-arrival"],
                    "planned_review_after": True,
                    "planned_simulation_after": False,
                }
            ],
            "active_phase_id": "core",
            "assumptions": ["The learner reads Latin script."],
        },
    }


def test_setup_writes_valid_state_and_returns_next_priorities(tmp_path):
    result = run_command("setup", setup_payload(), tmp_path)

    assert result.success is True
    assert result.data["learner_id"] == "qasim-ali"
    assert result.data["next_priorities"] == ["Explain a delayed arrival"]
    assert result.data["first_mission_id"] == "delayed-arrival"
    assert list(tmp_path.glob("qasim-ali/*/state.json"))


def test_invalid_setup_leaves_no_partial_state(tmp_path):
    payload = setup_payload()
    payload["mission_plans"][0]["priority"] = "unknown"

    result = run_command("setup", payload, tmp_path)

    assert result.success is False
    assert "priority" in result.error
    assert list(tmp_path.rglob("state.json")) == []


def test_module_entrypoint_returns_json_envelope(tmp_path):
    completed = subprocess.run(
        [sys.executable, "-m", "langcampaign", "setup", "--learners-root", str(tmp_path)],
        input=json.dumps(setup_payload()),
        text=True,
        capture_output=True,
        check=False,
    )
    envelope = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert envelope["success"] is True
```

- [ ] **Step 2: Run CLI tests and verify the module is absent**

Run: `python -m pytest tests/test_cli.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'langcampaign.cli'`.

- [ ] **Step 3: Implement command results, parsing, and setup transaction**

```python
# src/langcampaign/cli.py
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .learners import list_learner_campaigns, normalize_learner_id, save_learner_campaign, select_campaign
from .missions import validate_mission_map
from .models import (
    Campaign,
    CampaignSettings,
    CampaignType,
    CoachingStyle,
    CurriculumScope,
    Mission,
)
from .roadmaps import next_priorities, render_roadmap_summary, validate_roadmap
from .storage import CampaignState


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
    raw = payload["campaign"]
    from datetime import date
    from uuid import uuid4

    raw_date = raw.get("target_date")
    settings = CampaignSettings(
        campaign_type=CampaignType(raw["campaign_type"]),
        curriculum_scope=CurriculumScope(raw.get("curriculum_scope", "balanced")),
        coaching_style=CoachingStyle(raw.get("coaching_style", "supportive")),
        target_date=date.fromisoformat(raw_date) if raw_date is not None else None,
        expected_minutes_per_week=raw.get("expected_minutes_per_week", 0),
        minimum_minutes_per_week=raw.get("minimum_minutes_per_week", 0),
    )
    missions = tuple(
        Mission(item["id"], item["title"], item.get("weight", 1.0))
        for item in raw["missions"]
    )
    campaign = Campaign(
        id=raw.get("id") or uuid4().hex,
        goal=raw["goal"],
        target_language=raw["target_language"],
        settings=settings,
        missions=missions,
    )
    mission_plans = tuple(mission_plan_from_dict(item) for item in payload["mission_plans"])
    roadmap = roadmap_from_dict(payload["roadmap"])
    validate_mission_map(mission_plans, tuple(item.id for item in missions))
    validate_roadmap(roadmap, mission_plans)
    state = CampaignState(
        campaign=campaign,
        learner_id=normalize_learner_id(payload["learner_id"]),
        mission_plans=mission_plans,
        roadmap=roadmap,
    )
    save_learner_campaign(learners_root, state)
    priorities = next_priorities(roadmap, mission_plans)
    return {
        "learner_id": state.learner_id,
        "campaign_id": campaign.id,
        "next_priorities": list(priorities),
        "first_mission_id": mission_plans[0].id,
    }
```

Import `mission_plan_from_dict` and `roadmap_from_dict` from storage so the
command boundary reuses one parser. Add these complete dispatch functions:

```python
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


def run_command(
    command: str, payload: dict, learners_root: Path
) -> CommandResult:
    try:
        handler = COMMANDS[command]
        return CommandResult(True, data=handler(payload, Path(learners_root)))
    except KeyError as error:
        missing = error.args[0]
        return CommandResult(False, error=f"missing or unknown field: {missing}")
    except (TypeError, ValueError) as error:
        return CommandResult(False, error=str(error))


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
```

`run_command()` catches command and payload errors without writing state before
all construction and validation succeeds. Command result data are:

- `setup`: the dictionary above.
- `list-campaigns`: `{"campaigns": [{"id": id, "goal": goal}, ...]}`.
- `validate-state`: `{"valid": True, "campaign_id": ...}` after `select_campaign` loads successfully.
- `validate-mission-map`: `{"valid": True}` after parsing supplied campaign missions and plans.
- `show-roadmap`: `{"summary": render_roadmap_summary(...)}`; this is the only command that reveals the normally hidden roadmap.

Implement `main()` with `argparse` positional `command`, required `--learners-root`, optional `--learner-id` and `--campaign-id`, and JSON from stdin. Print exactly one JSON envelope. Exit 0 for success and 2 for a command error.

```python
# src/langcampaign/__main__.py
from .cli import main

raise SystemExit(main())
```

- [ ] **Step 4: Run CLI integration and the complete suite**

Run: `python -m pytest tests/test_cli.py tests/test_learners.py tests/test_storage.py -v`

Expected: all command, learner repository, and storage tests pass.

Run: `python -m pytest -v`

Expected: the complete suite passes with no warnings.

Run: `python -m langcampaign list-campaigns --learners-root learners --learner-id smoke-test`

Expected JSON:

```json
{"success": true, "data": {"campaigns": []}}
```

- [ ] **Step 5: Export the command boundary and commit**

Export `CommandResult` and `run_command` from `src/langcampaign/__init__.py`.

```bash
git add src/langcampaign/cli.py src/langcampaign/__main__.py src/langcampaign/__init__.py tests/test_cli.py
git commit -m "feat: add agent command boundary"
```

---

### Task 6: Foundation acceptance and documentation

**Files:**
- Modify: `README.md`
- Create: `tests/test_content_state_flow.py`

**Interfaces:**
- Consumes: all Tasks 1–5.
- Produces: a documented internal-roadmap foundation and an end-to-end acceptance test proving setup → persist → fresh load → learner roadmap summary.

- [ ] **Step 1: Write the failing acceptance flow**

```python
# tests/test_content_state_flow.py
from langcampaign.cli import run_command
from tests.test_cli import setup_payload


def test_setup_persists_hidden_roadmap_and_fresh_process_can_reveal_summary(tmp_path):
    created = run_command("setup", setup_payload(), tmp_path)
    assert created.success is True

    learner_id = created.data["learner_id"]
    campaign_id = created.data["campaign_id"]
    resumed = run_command(
        "validate-state",
        {"learner_id": learner_id, "campaign_id": campaign_id},
        tmp_path,
    )
    revealed = run_command(
        "show-roadmap",
        {"learner_id": learner_id, "campaign_id": campaign_id},
        tmp_path,
    )

    assert resumed.data == {"valid": True, "campaign_id": campaign_id}
    assert "Core hotel exchanges (current)" in revealed.data["summary"]
    assert "The learner reads Latin script" not in revealed.data["summary"]
```

- [ ] **Step 2: Run the acceptance test against the integrated interfaces**

Run: `python -m pytest tests/test_content_state_flow.py -v`

Expected: PASS. If it fails, treat the named assertion as a defect in the task
that produced that interface and correct that interface without changing the
acceptance test.

- [ ] **Step 3: Update status documentation**

Add this paragraph under `README.md` Current status:

```markdown
The campaign-content foundation now validates generated mission maps, stores a
coarse internal roadmap, keeps learner state under `learners/`, and exposes a
structured command boundary for upcoming Codex skills. The roadmap remains out
of normal session output but can be summarized when a learner asks to see it.
```

Do not describe Codex setup/learn commands as operational until plan 4 installs those skills.

- [ ] **Step 4: Run final foundation verification**

Run: `python -m pytest -v`

Expected: all tests pass.

Run: `python -m pip install -e '.[test]'`

Expected: editable install succeeds.

Run: `python -m compileall -q src`

Expected: exit 0 with no output.

Run: `git diff --check`

Expected: exit 0 with no output.

- [ ] **Step 5: Commit the accepted foundation**

```bash
git add README.md tests/test_content_state_flow.py
git commit -m "docs: describe campaign content foundation"
```

## Follow-on plan contracts

The next plan may rely on these stable interfaces:

- Validated `MissionPlan` tuples keyed one-to-one to `Campaign.missions`.
- A persisted `CampaignRoadmap` with a single active phase.
- `next_priorities()` for the learner-facing next-three view.
- `render_roadmap_summary()` only for explicit learner requests.
- Schema-version 3 `CampaignState` with learner identity, content, roadmap, and evidence.
- Repository-local learner selection that never guesses between campaigns.
- Stable JSON command envelopes and atomic setup transactions.

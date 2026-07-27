# Core Campaign Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a platform-neutral Python MVP that creates, edits, assesses, forecasts, persists, and renders LangCampaign campaigns.

**Architecture:** A small typed domain package owns campaign state and pure calculations; JSON persistence and terminal rendering sit at the edges. Targeted and flexible campaigns share one state model, while forecasts are produced only for targeted campaigns. Platform-specific skills and lifecycle hooks are deliberately deferred until the core semantics are stable.

**Tech Stack:** Python 3.11+, standard library runtime, `pytest` 8+ for tests, JSON files for persistence

## Global Constraints

- Balanced curriculum scope and Supportive coaching are defaults.
- Campaign type is either `targeted` or `flexible`; only targeted campaigns require a target date.
- Curriculum scope and coaching style vary independently.
- Mission readiness, target-date forecast, and training progress remain separate values.
- Attendance alone cannot increase mission readiness.
- CEFR output is approximate, modality-specific, evidence-based, and achievement-forward.
- Campaign edits preserve historical evidence and explain material effects.
- Colored emoji are favored; emoji frequency follows coaching style and never replaces essential text.
- Core state and calculations must not depend on Claude, Codex, or a particular chat interface.

## File map

- `pyproject.toml` — packaging, Python floor, and pytest configuration.
- `src/langcampaign/__init__.py` — stable public imports.
- `src/langcampaign/models.py` — enums and immutable domain records.
- `src/langcampaign/campaigns.py` — campaign creation and reconfiguration rules.
- `src/langcampaign/assessment.py` — evidence aggregation, readiness, and CEFR summaries.
- `src/langcampaign/forecasting.py` — targeted-campaign pace forecasts and recovery actions.
- `src/langcampaign/storage.py` — versioned JSON serialization and atomic persistence.
- `src/langcampaign/rendering.py` — coaching-aware plain-text progress cards.
- `tests/` — focused unit and integration tests matching the module boundaries.

---

### Task 1: Typed campaign domain and defaults

**Files:**
- Create: `pyproject.toml`
- Create: `src/langcampaign/__init__.py`
- Create: `src/langcampaign/models.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Produces: `CampaignType`, `CurriculumScope`, `CoachingStyle`, `MissionStatus`, `Mission`, `CampaignSettings`, `Campaign`, and `new_campaign()`.
- `new_campaign(goal: str, target_language: str, *, campaign_type: CampaignType = CampaignType.FLEXIBLE, target_date: date | None = None) -> Campaign`.

- [ ] **Step 1: Add packaging and write the failing default-model tests**

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "langcampaign"
version = "0.1.0"
requires-python = ">=3.11"

[project.optional-dependencies]
test = ["pytest>=8,<9"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

```python
# tests/test_models.py
from datetime import date

import pytest

from langcampaign.models import (
    CampaignType,
    CoachingStyle,
    CurriculumScope,
    new_campaign,
)


def test_new_campaign_uses_flexible_balanced_supportive_defaults():
    campaign = new_campaign("Chat with friends", "Spanish")

    assert campaign.settings.campaign_type is CampaignType.FLEXIBLE
    assert campaign.settings.curriculum_scope is CurriculumScope.BALANCED
    assert campaign.settings.coaching_style is CoachingStyle.SUPPORTIVE
    assert campaign.settings.target_date is None


def test_targeted_campaign_requires_target_date():
    with pytest.raises(ValueError, match="target_date is required"):
        new_campaign(
            "Handle a hotel stay",
            "Spanish",
            campaign_type=CampaignType.TARGETED,
        )


def test_flexible_campaign_rejects_target_date():
    with pytest.raises(ValueError, match="target_date is only valid"):
        new_campaign(
            "Read social media",
            "Japanese",
            target_date=date(2026, 9, 1),
        )
```

- [ ] **Step 2: Run the model tests and verify they fail because the package is absent**

Run: `python -m pytest tests/test_models.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'langcampaign'`.

- [ ] **Step 3: Implement the enums, records, validation, and constructor**

```python
# src/langcampaign/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import uuid4


class CampaignType(StrEnum):
    TARGETED = "targeted"
    FLEXIBLE = "flexible"


class CurriculumScope(StrEnum):
    MISSION_FOCUSED = "mission_focused"
    BALANCED = "balanced"
    FOUNDATIONAL = "foundational"


class CoachingStyle(StrEnum):
    SUPPORTIVE = "supportive"
    DIRECT = "direct"
    BOOT_CAMP = "boot_camp"


class MissionStatus(StrEnum):
    NOT_ASSESSED = "not_assessed"
    DEVELOPING = "developing"
    DEMONSTRATED = "demonstrated"
    REVIEW_DUE = "review_due"


@dataclass(frozen=True)
class Mission:
    id: str
    title: str
    weight: float = 1.0
    status: MissionStatus = MissionStatus.NOT_ASSESSED


@dataclass(frozen=True)
class CampaignSettings:
    campaign_type: CampaignType = CampaignType.FLEXIBLE
    curriculum_scope: CurriculumScope = CurriculumScope.BALANCED
    coaching_style: CoachingStyle = CoachingStyle.SUPPORTIVE
    target_date: date | None = None
    expected_minutes_per_week: int = 0
    minimum_minutes_per_week: int = 0


@dataclass(frozen=True)
class Campaign:
    id: str
    goal: str
    target_language: str
    settings: CampaignSettings
    missions: tuple[Mission, ...] = field(default_factory=tuple)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


def new_campaign(
    goal: str,
    target_language: str,
    *,
    campaign_type: CampaignType = CampaignType.FLEXIBLE,
    target_date: date | None = None,
) -> Campaign:
    if campaign_type is CampaignType.TARGETED and target_date is None:
        raise ValueError("target_date is required for targeted campaigns")
    if campaign_type is CampaignType.FLEXIBLE and target_date is not None:
        raise ValueError("target_date is only valid for targeted campaigns")
    return Campaign(
        id=str(uuid4()),
        goal=goal.strip(),
        target_language=target_language.strip(),
        settings=CampaignSettings(
            campaign_type=campaign_type,
            target_date=target_date,
        ),
    )
```

```python
# src/langcampaign/__init__.py
from .models import Campaign, CampaignType, CoachingStyle, CurriculumScope

__all__ = ["Campaign", "CampaignType", "CoachingStyle", "CurriculumScope"]
```

- [ ] **Step 4: Run the model tests and verify all three pass**

Run: `python -m pytest tests/test_models.py -v`

Expected: `3 passed`.

- [ ] **Step 5: Commit the domain model**

```bash
git add pyproject.toml src/langcampaign/__init__.py src/langcampaign/models.py tests/test_models.py
git commit -m "feat: add campaign domain model"
```

---

### Task 2: Campaign editing with preserved history

**Files:**
- Modify: `src/langcampaign/models.py`
- Create: `src/langcampaign/campaigns.py`
- Create: `tests/test_campaigns.py`

**Interfaces:**
- Consumes: `Campaign`, `CampaignSettings`, and their enums from Task 1.
- Produces: `CampaignChange`, `CampaignRevision`, and `revise_campaign(campaign: Campaign, change: CampaignChange) -> CampaignRevision`.
- A revision returns the updated campaign plus human-readable effects; it never mutates or deletes the input campaign.

- [ ] **Step 1: Write failing tests for editable settings and structural confirmation**

```python
# tests/test_campaigns.py
from datetime import date

import pytest

from langcampaign.campaigns import CampaignChange, revise_campaign
from langcampaign.models import (
    CampaignType,
    CoachingStyle,
    CurriculumScope,
    Mission,
    new_campaign,
)


def test_style_and_scope_change_preserves_missions():
    original = new_campaign("Text friends", "French")
    original = original.with_missions((Mission("chat", "Casual chat"),))

    revision = revise_campaign(
        original,
        CampaignChange(
            coaching_style=CoachingStyle.DIRECT,
            curriculum_scope=CurriculumScope.FOUNDATIONAL,
        ),
    )

    assert revision.campaign.missions == original.missions
    assert revision.campaign.settings.coaching_style is CoachingStyle.DIRECT
    assert "Coaching style changed" in revision.effects


def test_switch_to_targeted_requires_date_and_confirmation():
    original = new_campaign("Read posts", "Japanese")

    with pytest.raises(ValueError, match="confirmation_required"):
        revise_campaign(
            original,
            CampaignChange(
                campaign_type=CampaignType.TARGETED,
                target_date=date(2026, 10, 1),
            ),
        )

    revision = revise_campaign(
        original,
        CampaignChange(
            campaign_type=CampaignType.TARGETED,
            target_date=date(2026, 10, 1),
            confirm_restructure=True,
        ),
    )
    assert revision.campaign.settings.target_date == date(2026, 10, 1)
```

- [ ] **Step 2: Run the campaign tests and verify the missing APIs fail**

Run: `python -m pytest tests/test_campaigns.py -v`

Expected: collection fails because `langcampaign.campaigns` does not exist.

- [ ] **Step 3: Add the immutable mission helper and revision service**

Add to `Campaign` in `src/langcampaign/models.py`:

```python
    def with_missions(self, missions: tuple[Mission, ...]) -> "Campaign":
        from dataclasses import replace

        return replace(self, missions=missions)
```

Create `src/langcampaign/campaigns.py` with:

```python
from dataclasses import dataclass, replace
from datetime import date

from .models import Campaign, CampaignType, CoachingStyle, CurriculumScope


@dataclass(frozen=True)
class CampaignChange:
    goal: str | None = None
    campaign_type: CampaignType | None = None
    target_date: date | None = None
    expected_minutes_per_week: int | None = None
    minimum_minutes_per_week: int | None = None
    curriculum_scope: CurriculumScope | None = None
    coaching_style: CoachingStyle | None = None
    confirm_restructure: bool = False


@dataclass(frozen=True)
class CampaignRevision:
    campaign: Campaign
    effects: str


def revise_campaign(campaign: Campaign, change: CampaignChange) -> CampaignRevision:
    old = campaign.settings
    new_type = change.campaign_type or old.campaign_type
    new_date = change.target_date if change.target_date is not None else old.target_date
    structural = new_type is not old.campaign_type
    if structural and not change.confirm_restructure:
        raise ValueError("confirmation_required: campaign type change restructures planning")
    if new_type is CampaignType.TARGETED and new_date is None:
        raise ValueError("target_date is required for targeted campaigns")
    if new_type is CampaignType.FLEXIBLE:
        new_date = None
    updated_settings = replace(
        old,
        campaign_type=new_type,
        target_date=new_date,
        expected_minutes_per_week=(
            change.expected_minutes_per_week
            if change.expected_minutes_per_week is not None
            else old.expected_minutes_per_week
        ),
        minimum_minutes_per_week=(
            change.minimum_minutes_per_week
            if change.minimum_minutes_per_week is not None
            else old.minimum_minutes_per_week
        ),
        curriculum_scope=change.curriculum_scope or old.curriculum_scope,
        coaching_style=change.coaching_style or old.coaching_style,
    )
    updated = replace(
        campaign,
        goal=change.goal.strip() if change.goal is not None else campaign.goal,
        settings=updated_settings,
    )
    effects = []
    if old.coaching_style is not updated_settings.coaching_style:
        effects.append("Coaching style changed; assessment standards are unchanged.")
    if old.curriculum_scope is not updated_settings.curriculum_scope:
        effects.append("Curriculum priorities will be recalculated.")
    if structural:
        effects.append("Campaign type changed; existing mission evidence was preserved.")
    return CampaignRevision(updated, " ".join(effects) or "No material change.")
```

- [ ] **Step 4: Run model and campaign tests**

Run: `python -m pytest tests/test_models.py tests/test_campaigns.py -v`

Expected: `5 passed`.

- [ ] **Step 5: Commit editable campaign behavior**

```bash
git add src/langcampaign/models.py src/langcampaign/campaigns.py tests/test_campaigns.py
git commit -m "feat: support reversible campaign changes"
```

---

### Task 3: Evidence-based readiness and CEFR summaries

**Files:**
- Create: `src/langcampaign/assessment.py`
- Create: `tests/test_assessment.py`

**Interfaces:**
- Consumes: mission identifiers from `Campaign.missions`.
- Produces: `AssessmentEvidence`, `ReadinessResult`, `calculate_readiness(campaign, evidence)`, and `summarize_cefr(evidence, modality)`.
- Scores are integers from 0 through 100; unassessed missions remain explicitly unassessed.

- [ ] **Step 1: Write failing tests that separate attendance from evidence**

```python
# tests/test_assessment.py
from datetime import datetime, timezone

from langcampaign.assessment import (
    AssessmentEvidence,
    calculate_readiness,
    summarize_cefr,
)
from langcampaign.models import Mission, new_campaign


def test_readiness_uses_weighted_assessment_evidence_only():
    campaign = new_campaign("Text friends", "Spanish").with_missions(
        (Mission("chat", "Casual chat", 2.0), Mission("posts", "Read posts", 1.0))
    )
    evidence = (
        AssessmentEvidence(
            mission_id="chat",
            score=80,
            independent=True,
            modality="written_interaction",
            assessed_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
            cefr="A2",
        ),
    )

    result = calculate_readiness(campaign, evidence)

    assert result.percent == 53
    assert result.unassessed_mission_ids == ("posts",)


def test_cefr_summary_is_affirmative_and_modality_specific():
    evidence = tuple(
        AssessmentEvidence(
            mission_id=str(index),
            score=75,
            independent=True,
            modality="written_interaction",
            assessed_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
            cefr="A2",
        )
        for index in range(4)
    )

    assert summarize_cefr(evidence, "written_interaction") == (
        "You demonstrated approximately A2 written interaction "
        "across 4 independent assessments."
    )
```

- [ ] **Step 2: Run assessment tests and verify the module is missing**

Run: `python -m pytest tests/test_assessment.py -v`

Expected: collection fails because `langcampaign.assessment` does not exist.

- [ ] **Step 3: Implement readiness aggregation and CEFR evidence reporting**

```python
# src/langcampaign/assessment.py
from dataclasses import dataclass
from datetime import datetime

from .models import Campaign


CEFR_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}


@dataclass(frozen=True)
class AssessmentEvidence:
    mission_id: str
    score: int
    independent: bool
    modality: str
    assessed_at: datetime
    cefr: str | None = None


@dataclass(frozen=True)
class ReadinessResult:
    percent: int
    assessed_mission_ids: tuple[str, ...]
    unassessed_mission_ids: tuple[str, ...]


def calculate_readiness(
    campaign: Campaign,
    evidence: tuple[AssessmentEvidence, ...],
) -> ReadinessResult:
    latest = {}
    for item in sorted(evidence, key=lambda value: value.assessed_at):
        latest[item.mission_id] = item
    total_weight = sum(mission.weight for mission in campaign.missions)
    earned = sum(
        mission.weight * latest[mission.id].score / 100
        for mission in campaign.missions
        if mission.id in latest
    )
    assessed = tuple(m.id for m in campaign.missions if m.id in latest)
    unassessed = tuple(m.id for m in campaign.missions if m.id not in latest)
    percent = round(100 * earned / total_weight) if total_weight else 0
    return ReadinessResult(percent, assessed, unassessed)


def summarize_cefr(
    evidence: tuple[AssessmentEvidence, ...],
    modality: str,
) -> str:
    independent = [
        item
        for item in evidence
        if item.modality == modality and item.independent and item.cefr in CEFR_ORDER
    ]
    if len(independent) < 2:
        return f"Not enough independent evidence to estimate {modality.replace('_', ' ')}."
    supported_levels = [
        level
        for level in CEFR_ORDER
        if sum(item.cefr == level for item in independent) >= 2
    ]
    if not supported_levels:
        return f"Not enough consistent evidence to estimate {modality.replace('_', ' ')}."
    supported = max(supported_levels, key=CEFR_ORDER.__getitem__)
    label = modality.replace("_", " ")
    count = sum(item.cefr == supported for item in independent)
    return (
        f"You demonstrated approximately {supported} {label} "
        f"across {count} independent assessments."
    )
```

- [ ] **Step 4: Run assessment tests and the full suite**

Run: `python -m pytest -v`

Expected: `7 passed`.

- [ ] **Step 5: Commit the assessment engine**

```bash
git add src/langcampaign/assessment.py tests/test_assessment.py
git commit -m "feat: calculate evidence-based readiness"
```

---

### Task 4: Target-date forecast and recovery actions

**Files:**
- Create: `src/langcampaign/forecasting.py`
- Create: `tests/test_forecasting.py`

**Interfaces:**
- Consumes: `Campaign`, current readiness, actual minutes studied, and elapsed campaign days.
- Produces: `Forecast`, `RecoveryAction`, and `forecast_campaign(campaign, *, readiness, minutes_studied, elapsed_days, today) -> Forecast | None`.
- Flexible campaigns return `None`; targeted campaigns return a projected readiness and status.

- [ ] **Step 1: Write failing tests for flexible omission and targeted risk**

```python
# tests/test_forecasting.py
from dataclasses import replace
from datetime import date

from langcampaign.forecasting import forecast_campaign
from langcampaign.models import CampaignType, new_campaign


def test_flexible_campaign_has_no_target_date_forecast():
    campaign = new_campaign("Read posts", "Japanese")
    assert forecast_campaign(
        campaign,
        readiness=40,
        minutes_studied=100,
        elapsed_days=7,
        today=date(2026, 7, 27),
    ) is None


def test_targeted_campaign_reports_risk_and_specific_time_recovery():
    campaign = new_campaign(
        "Handle a hotel stay",
        "Spanish",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 8, 10),
    )
    campaign = replace(
        campaign,
        settings=replace(campaign.settings, expected_minutes_per_week=200),
    )

    forecast = forecast_campaign(
        campaign,
        readiness=40,
        minutes_studied=100,
        elapsed_days=7,
        today=date(2026, 7, 27),
    )

    assert forecast.status == "at_risk"
    assert forecast.projected_readiness == 70
    assert forecast.recovery_actions[0].additional_minutes_per_week == 100
```

- [ ] **Step 2: Run forecast tests and verify the module is missing**

Run: `python -m pytest tests/test_forecasting.py -v`

Expected: collection fails because `langcampaign.forecasting` does not exist.

- [ ] **Step 3: Implement an explicit, deterministic MVP forecast**

```python
# src/langcampaign/forecasting.py
from dataclasses import dataclass
from datetime import date

from .models import Campaign, CampaignType


@dataclass(frozen=True)
class RecoveryAction:
    message: str
    additional_minutes_per_week: int = 0


@dataclass(frozen=True)
class Forecast:
    projected_readiness: int
    status: str
    assumed_minutes_per_week: int
    recovery_actions: tuple[RecoveryAction, ...]


def forecast_campaign(
    campaign: Campaign,
    *,
    readiness: int,
    minutes_studied: int,
    elapsed_days: int,
    today: date,
) -> Forecast | None:
    if campaign.settings.campaign_type is CampaignType.FLEXIBLE:
        return None
    if campaign.settings.target_date is None:
        raise ValueError("targeted campaign is missing target_date")
    actual_weekly = round(minutes_studied * 7 / max(elapsed_days, 1))
    planned_weekly = campaign.settings.expected_minutes_per_week
    remaining_weeks = max((campaign.settings.target_date - today).days / 7, 0)
    # MVP heuristic: every 100 future study minutes can add up to 15 readiness points.
    projected_gain = round(actual_weekly * remaining_weeks * 15 / 100)
    projected = min(100, readiness + projected_gain)
    status = "on_track" if projected >= 80 else "at_risk"
    actions = ()
    if status == "at_risk":
        additional = max(planned_weekly - actual_weekly, 0)
        actions = (
            RecoveryAction(
                f"Add {additional} study minutes per week to restore the planned pace.",
                additional,
            ),
            RecoveryAction("Narrow optional context before removing mission-critical work."),
        )
    return Forecast(projected, status, actual_weekly, actions)
```

- [ ] **Step 4: Run forecast tests and the full suite**

Run: `python -m pytest -v`

Expected: `9 passed`.

- [ ] **Step 5: Commit forecasting behavior**

```bash
git add src/langcampaign/forecasting.py tests/test_forecasting.py
git commit -m "feat: forecast targeted campaign readiness"
```

---

### Task 5: Versioned JSON persistence

**Files:**
- Create: `src/langcampaign/storage.py`
- Create: `tests/test_storage.py`

**Interfaces:**
- Consumes: the `Campaign` records from Task 1.
- Produces: `campaign_to_dict(campaign)`, `campaign_from_dict(data)`, `save_campaign(path, campaign)`, and `load_campaign(path)`.
- JSON has top-level `schema_version: 1`; saves use a sibling temporary file followed by `Path.replace()`.

- [ ] **Step 1: Write a failing round-trip and schema-version test**

```python
# tests/test_storage.py
import json
from datetime import date

import pytest

from langcampaign.models import CampaignType, Mission, new_campaign
from langcampaign.storage import load_campaign, save_campaign


def test_campaign_round_trips_through_versioned_json(tmp_path):
    campaign = new_campaign(
        "Travel independently",
        "French",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 9, 10),
    ).with_missions((Mission("hotel", "Hotel check-in", 2.0),))
    path = tmp_path / "campaign.json"

    save_campaign(path, campaign)
    loaded = load_campaign(path)

    assert loaded == campaign
    assert json.loads(path.read_text())["schema_version"] == 1


def test_unknown_schema_version_is_rejected(tmp_path):
    path = tmp_path / "campaign.json"
    path.write_text('{"schema_version": 99, "campaign": {}}')

    with pytest.raises(ValueError, match="unsupported schema_version: 99"):
        load_campaign(path)
```

- [ ] **Step 2: Run storage tests and verify the module is missing**

Run: `python -m pytest tests/test_storage.py -v`

Expected: collection fails because `langcampaign.storage` does not exist.

- [ ] **Step 3: Implement explicit JSON conversion and atomic saves**

```python
# src/langcampaign/storage.py
import json
from datetime import date, datetime
from pathlib import Path

from .models import (
    Campaign,
    CampaignSettings,
    CampaignType,
    CoachingStyle,
    CurriculumScope,
    Mission,
    MissionStatus,
)


SCHEMA_VERSION = 1


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
        target_date=date.fromisoformat(raw_date) if raw_date else None,
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


def save_campaign(path: Path, campaign: Campaign) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "campaign": campaign_to_dict(campaign),
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_campaign(path: Path) -> Campaign:
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {version}")
    return campaign_from_dict(payload["campaign"])
```

- [ ] **Step 4: Run storage tests and the full suite**

Run: `python -m pytest -v`

Expected: `11 passed`.

- [ ] **Step 5: Commit persistence**

```bash
git add src/langcampaign/storage.py tests/test_storage.py
git commit -m "feat: persist campaigns as versioned json"
```

---

### Task 6: Coaching-aware progress cards

**Files:**
- Create: `src/langcampaign/rendering.py`
- Create: `tests/test_rendering.py`

**Interfaces:**
- Consumes: `Campaign`, `ReadinessResult`, optional `Forecast`, completed/planned minutes, and mission labels.
- Produces: `ProgressReport` and `render_progress(report: ProgressReport) -> str`.
- Supportive is colorful and celebratory, Direct is compact, and Boot Camp is bold/action-oriented; all contain text labels for semantic emoji.

- [ ] **Step 1: Write failing snapshot-style tests for the three coaching styles**

```python
# tests/test_rendering.py
from dataclasses import replace

from langcampaign.assessment import ReadinessResult
from langcampaign.models import CoachingStyle, new_campaign
from langcampaign.rendering import ProgressReport, render_progress


def report_for(style):
    campaign = new_campaign("Text friends", "Spanish")
    campaign = replace(
        campaign,
        settings=replace(campaign.settings, coaching_style=style),
    )
    return ProgressReport(
        campaign=campaign,
        readiness=ReadinessResult(59, ("chat",), ("replies",)),
        forecast=None,
        completed_minutes=120,
        planned_minutes=300,
        demonstrated=("Casual greeting",),
        developing=("Unexpected replies",),
        next_action="Practice a 10-minute group-chat simulation.",
    )


def test_supportive_report_is_expressive_and_labels_emoji():
    output = render_progress(report_for(CoachingStyle.SUPPORTIVE))
    assert "🌟 Great work" in output
    assert "✅ Demonstrated: Casual greeting" in output
    assert "🟡 Developing: Unexpected replies" in output


def test_direct_report_is_compact_without_celebration():
    output = render_progress(report_for(CoachingStyle.DIRECT))
    assert "MISSION REPORT" in output
    assert "Great work" not in output
    assert len(output.splitlines()) <= 10


def test_boot_camp_report_emphasizes_next_action():
    output = render_progress(report_for(CoachingStyle.BOOT_CAMP))
    assert "MISSION CHECK" in output
    assert "NEXT ACTION" in output
```

- [ ] **Step 2: Run rendering tests and verify the module is missing**

Run: `python -m pytest tests/test_rendering.py -v`

Expected: collection fails because `langcampaign.rendering` does not exist.

- [ ] **Step 3: Implement a shared progress bar and three presentation templates**

```python
# src/langcampaign/rendering.py
from dataclasses import dataclass

from .assessment import ReadinessResult
from .forecasting import Forecast
from .models import Campaign, CoachingStyle


@dataclass(frozen=True)
class ProgressReport:
    campaign: Campaign
    readiness: ReadinessResult
    forecast: Forecast | None
    completed_minutes: int
    planned_minutes: int
    demonstrated: tuple[str, ...]
    developing: tuple[str, ...]
    next_action: str


def progress_bar(percent: int, width: int = 20) -> str:
    filled = round(width * max(0, min(percent, 100)) / 100)
    return "█" * filled + "░" * (width - filled)


def render_progress(report: ProgressReport) -> str:
    style = report.campaign.settings.coaching_style
    heading = {
        CoachingStyle.SUPPORTIVE: "🌟 Great work — mission complete!",
        CoachingStyle.DIRECT: "MISSION REPORT",
        CoachingStyle.BOOT_CAMP: "MISSION CHECK",
    }[style]
    lines = [heading, f"Readiness [{progress_bar(report.readiness.percent)}] {report.readiness.percent}%"]
    if report.forecast is not None:
        lines.append(
            f"Forecast: {report.forecast.projected_readiness}% ({report.forecast.status.replace('_', ' ')})"
        )
    if style is CoachingStyle.SUPPORTIVE:
        lines.extend(f"✅ Demonstrated: {item}" for item in report.demonstrated)
        lines.extend(f"🟡 Developing: {item}" for item in report.developing)
    else:
        lines.extend(f"PASS  {item}" for item in report.demonstrated)
        lines.extend(f"RETRY {item}" for item in report.developing)
    if style is CoachingStyle.BOOT_CAMP:
        lines.extend(("NEXT ACTION", report.next_action))
    else:
        lines.append(f"Next: {report.next_action}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run rendering tests and the full suite**

Run: `python -m pytest -v`

Expected: `14 passed`.

- [ ] **Step 5: Commit the renderer**

```bash
git add src/langcampaign/rendering.py tests/test_rendering.py
git commit -m "feat: render coaching-aware progress reports"
```

---

### Task 7: End-to-end core campaign integration

**Files:**
- Modify: `src/langcampaign/__init__.py`
- Create: `tests/test_campaign_flow.py`
- Create: `README.md`

**Interfaces:**
- Consumes: all public interfaces from Tasks 1–6.
- Produces: a documented public Python API and one end-to-end test proving create → assess → forecast → render → save → load.

- [ ] **Step 1: Write the failing end-to-end test**

```python
# tests/test_campaign_flow.py
from datetime import date, datetime, timezone

from langcampaign.assessment import AssessmentEvidence, calculate_readiness
from langcampaign.forecasting import forecast_campaign
from langcampaign.models import CampaignType, Mission, new_campaign
from langcampaign.rendering import ProgressReport, render_progress
from langcampaign.storage import load_campaign, save_campaign


def test_targeted_campaign_flow(tmp_path):
    campaign = new_campaign(
        "Handle a hotel stay",
        "Spanish",
        campaign_type=CampaignType.TARGETED,
        target_date=date(2026, 8, 10),
    ).with_missions((Mission("hotel", "Hotel check-in"),))
    evidence = (
        AssessmentEvidence(
            "hotel", 80, True, "written_interaction",
            datetime(2026, 7, 27, tzinfo=timezone.utc), "A2",
        ),
    )
    readiness = calculate_readiness(campaign, evidence)
    forecast = forecast_campaign(
        campaign,
        readiness=readiness.percent,
        minutes_studied=100,
        elapsed_days=7,
        today=date(2026, 7, 27),
    )
    output = render_progress(
        ProgressReport(
            campaign, readiness, forecast, 100, 300,
            ("Hotel check-in",), (), "Practice an unfamiliar reply.",
        )
    )
    path = tmp_path / "campaign.json"
    save_campaign(path, campaign)

    assert "Readiness" in output
    assert load_campaign(path) == campaign
```

- [ ] **Step 2: Run the flow test before exporting the public API**

Run: `python -m pytest tests/test_campaign_flow.py -v`

Expected: the test exposes any import, serialization, or interface mismatch between the completed modules.

- [ ] **Step 3: Fix only integration mismatches and document the MVP**

Update `src/langcampaign/__init__.py` to export `new_campaign`, `revise_campaign`, `calculate_readiness`, `summarize_cefr`, `forecast_campaign`, `save_campaign`, `load_campaign`, and `render_progress`.

Create `README.md` with:

````markdown
# LangCampaign

Goal-driven language campaigns for AI agents.

LangCampaign supports targeted campaigns with honest target-date forecasts and
flexible campaigns for goals such as texting friends, reading social media, and
participating in online communities. Its core engine keeps demonstrated mission
readiness separate from projected readiness and completed training time.

## Development

```bash
python -m pip install -e '.[test]'
python -m pytest -v
```
````

- [ ] **Step 4: Run all tests and packaging checks**

Run: `python -m pytest -v`

Expected: `15 passed`.

Run: `python -m pip install -e '.[test]'`

Expected: editable install completes without errors.

Run: `python -m compileall -q src`

Expected: exit code 0 with no output.

- [ ] **Step 5: Commit the integrated core MVP**

```bash
git add src/langcampaign/__init__.py tests/test_campaign_flow.py README.md
git commit -m "docs: document core campaign workflow"
```

## Deferred follow-on plans

The following independently testable subsystems require their own designs or plans after the core MVP:

1. Mission generation and curriculum-content authoring.
2. Interactive agent session orchestration and review scheduling.
3. Codex and Claude platform adapters, including skill discovery and lifecycle automation.
4. A richer learned forecasting model to replace the explicitly labeled MVP heuristic.

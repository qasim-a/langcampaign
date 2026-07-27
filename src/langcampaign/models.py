from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from math import isfinite
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


def _require_non_empty_string(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _require_nonnegative_integer(value: object, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def _require_aware_datetime(value: object, name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class Mission:
    id: str
    title: str
    weight: float = 1.0
    status: MissionStatus = MissionStatus.NOT_ASSESSED

    def __post_init__(self) -> None:
        _require_non_empty_string(self.id, "mission id")
        _require_non_empty_string(self.title, "mission title")
        if (
            isinstance(self.weight, bool)
            or not isinstance(self.weight, (int, float))
            or not isfinite(self.weight)
            or self.weight <= 0
        ):
            raise ValueError("weight must be a finite positive number")


@dataclass(frozen=True)
class CampaignSettings:
    campaign_type: CampaignType = CampaignType.FLEXIBLE
    curriculum_scope: CurriculumScope = CurriculumScope.BALANCED
    coaching_style: CoachingStyle = CoachingStyle.SUPPORTIVE
    target_date: date | None = None
    expected_minutes_per_week: int = 0
    minimum_minutes_per_week: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.campaign_type, CampaignType):
            raise ValueError("campaign_type must be a CampaignType")
        if not isinstance(self.curriculum_scope, CurriculumScope):
            raise ValueError("curriculum_scope must be a CurriculumScope")
        if not isinstance(self.coaching_style, CoachingStyle):
            raise ValueError("coaching_style must be a CoachingStyle")
        if self.target_date is not None and type(self.target_date) is not date:
            raise ValueError("target_date must be a date")
        if (
            self.campaign_type is CampaignType.TARGETED
            and self.target_date is None
        ):
            raise ValueError("target_date is required for targeted campaigns")
        if (
            self.campaign_type is CampaignType.FLEXIBLE
            and self.target_date is not None
        ):
            raise ValueError(
                "target_date is only valid for targeted campaigns"
            )
        _require_nonnegative_integer(
            self.expected_minutes_per_week,
            "expected_minutes_per_week",
        )
        _require_nonnegative_integer(
            self.minimum_minutes_per_week,
            "minimum_minutes_per_week",
        )


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

    def __post_init__(self) -> None:
        _require_non_empty_string(self.id, "campaign id")
        _require_non_empty_string(self.goal, "goal")
        _require_non_empty_string(self.target_language, "target_language")
        _require_aware_datetime(self.created_at, "created_at")
        mission_ids = tuple(mission.id for mission in self.missions)
        if len(mission_ids) != len(set(mission_ids)):
            raise ValueError("mission ids must be unique within a campaign")

    def with_missions(self, missions: tuple[Mission, ...]) -> "Campaign":
        from dataclasses import replace

        return replace(self, missions=missions)


def new_campaign(
    goal: str,
    target_language: str,
    *,
    campaign_type: CampaignType = CampaignType.FLEXIBLE,
    target_date: date | None = None,
) -> Campaign:
    return Campaign(
        id=str(uuid4()),
        goal=goal.strip() if isinstance(goal, str) else goal,
        target_language=(
            target_language.strip()
            if isinstance(target_language, str)
            else target_language
        ),
        settings=CampaignSettings(
            campaign_type=campaign_type,
            target_date=target_date,
        ),
    )

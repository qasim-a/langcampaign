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

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

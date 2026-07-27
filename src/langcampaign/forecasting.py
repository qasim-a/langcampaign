from dataclasses import dataclass
from datetime import date
from math import ceil

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
    remaining_weeks = max((campaign.settings.target_date - today).days / 7, 0)
    projected_gain = round(actual_weekly * remaining_weeks * 15 / 100)
    projected = min(100, readiness + projected_gain)
    status = "on_track" if projected >= 80 else "at_risk"
    actions: tuple[RecoveryAction, ...] = ()
    if status == "at_risk":
        if remaining_weeks:
            required_weekly = ceil(
                (80 - readiness) * 100 / (remaining_weeks * 15)
            )
            additional = required_weekly - actual_weekly
            actions = (
                RecoveryAction(
                    f"Add {additional} study minutes per week to reach 80 readiness by the target date.",
                    additional,
                ),
                RecoveryAction(
                    "Narrow optional context before removing mission-critical work."
                ),
            )
        else:
            actions = (
                RecoveryAction(
                    "Narrow the goal or revise the target date because no time remains for "
                    "a meaningful time recovery."
                ),
                RecoveryAction(
                    "Narrow optional context before removing mission-critical work."
                ),
            )
    return Forecast(projected, status, actual_weekly, actions)

from dataclasses import dataclass
from datetime import date
from math import ceil

from .models import Campaign, CampaignType


TARGET_READINESS = 80
# Deterministic MVP capacity: at most two study hours per day, every day.
MAX_PLAUSIBLE_MINUTES_PER_WEEK = 14 * 60


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


def _validate_percentage(name: str, value: int) -> None:
    if type(value) is not int or not 0 <= value <= 100:
        raise ValueError(f"{name} must be an integer from 0 through 100")


def _validate_nonnegative_integer(name: str, value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def forecast_campaign(
    campaign: Campaign,
    *,
    readiness: int,
    minutes_studied: int,
    elapsed_days: int,
    today: date,
) -> Forecast | None:
    _validate_percentage("readiness", readiness)
    _validate_nonnegative_integer("minutes_studied", minutes_studied)
    _validate_nonnegative_integer("elapsed_days", elapsed_days)
    if type(today) is not date:
        raise ValueError("today must be a date")
    if elapsed_days == 0 and minutes_studied:
        raise ValueError(
            "minutes_studied must be zero when elapsed_days is zero"
        )

    if campaign.settings.campaign_type is CampaignType.FLEXIBLE:
        return None
    if campaign.settings.target_date is None:
        raise ValueError("targeted campaign is missing target_date")

    actual_weekly = (
        round(minutes_studied * 7 / elapsed_days) if elapsed_days else 0
    )
    remaining_weeks = max((campaign.settings.target_date - today).days / 7, 0)
    projected_gain = round(actual_weekly * remaining_weeks * 15 / 100)
    projected = min(100, readiness + projected_gain)
    if readiness >= TARGET_READINESS:
        status = "target_met"
    elif projected >= TARGET_READINESS:
        status = "on_track"
    else:
        status = "at_risk"
    actions: tuple[RecoveryAction, ...] = ()
    if status == "at_risk":
        if remaining_weeks:
            required_weekly = ceil(
                (TARGET_READINESS - readiness) * 100
                / (remaining_weeks * 15)
            )
            if required_weekly <= MAX_PLAUSIBLE_MINUTES_PER_WEEK:
                additional = required_weekly - actual_weekly
                actions = (
                    RecoveryAction(
                        f"Add {additional} study minutes per week to reach "
                        f"{TARGET_READINESS} readiness by the target date.",
                        additional,
                    ),
                    RecoveryAction(
                        "Narrow optional context before removing mission-critical work."
                    ),
                )
            else:
                actions = (
                    RecoveryAction(
                        "Narrow the goal or revise the target date because the "
                        "required recovery pace is not plausible."
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

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
    assessed = tuple(mission.id for mission in campaign.missions if mission.id in latest)
    unassessed = tuple(
        mission.id for mission in campaign.missions if mission.id not in latest
    )
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

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
    if new_type is CampaignType.FLEXIBLE and change.target_date is not None:
        raise ValueError("target_date is only valid for targeted campaigns")
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
    if campaign.goal != updated.goal:
        effects.append("Goal changed; mission priorities will be recalculated.")
    if old.target_date != updated_settings.target_date:
        effects.append("Target date changed; planning timeline will be recalculated.")
    if old.expected_minutes_per_week != updated_settings.expected_minutes_per_week:
        effects.append("Expected weekly time changed; planning workload will be recalculated.")
    if old.minimum_minutes_per_week != updated_settings.minimum_minutes_per_week:
        effects.append("Minimum weekly time changed; planning workload will be recalculated.")
    if old.coaching_style is not updated_settings.coaching_style:
        effects.append("Coaching style changed; assessment standards are unchanged.")
    if old.curriculum_scope is not updated_settings.curriculum_scope:
        effects.append("Curriculum priorities will be recalculated.")
    if structural:
        effects.append("Campaign type changed; existing mission evidence was preserved.")
    return CampaignRevision(updated, " ".join(effects) or "No material change.")

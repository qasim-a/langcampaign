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
        CoachingStyle.SUPPORTIVE: "🌟 Great work — keep building your mission!",
        CoachingStyle.DIRECT: "MISSION REPORT",
        CoachingStyle.BOOT_CAMP: "MISSION CHECK",
    }[style]
    training_percent = (
        round(100 * report.completed_minutes / report.planned_minutes)
        if report.planned_minutes
        else 0
    )
    lines = [
        heading,
        f"Readiness [{progress_bar(report.readiness.percent)}] {report.readiness.percent}%",
        (
            f"Training completed [{progress_bar(training_percent)}] "
            f"{report.completed_minutes}/{report.planned_minutes} min "
            f"({training_percent}%)"
        ),
    ]
    if report.forecast is not None:
        lines.append(
            f"Forecast: {report.forecast.projected_readiness}% "
            f"({report.forecast.status.replace('_', ' ')})"
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

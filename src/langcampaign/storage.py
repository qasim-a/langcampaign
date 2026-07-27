import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .assessment import AssessmentEvidence
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
CAMPAIGN_STATE_SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = (SCHEMA_VERSION, CAMPAIGN_STATE_SCHEMA_VERSION)


class CampaignStorageError(ValueError):
    """A stored campaign envelope or payload is invalid."""


@dataclass(frozen=True)
class CampaignState:
    campaign: Campaign
    assessment_evidence: tuple[AssessmentEvidence, ...] = ()


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
        target_date=(
            date.fromisoformat(raw_date)
            if raw_date is not None
            else None
        ),
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


def _assessment_evidence_to_dict(
    evidence: AssessmentEvidence,
) -> dict:
    return {
        "mission_id": evidence.mission_id,
        "score": evidence.score,
        "independent": evidence.independent,
        "modality": evidence.modality,
        "assessed_at": evidence.assessed_at.isoformat(),
        "cefr": evidence.cefr,
    }


def _assessment_evidence_from_dict(data: dict) -> AssessmentEvidence:
    return AssessmentEvidence(
        mission_id=data["mission_id"],
        score=data["score"],
        independent=data["independent"],
        modality=data["modality"],
        assessed_at=datetime.fromisoformat(data["assessed_at"]),
        cefr=data["cefr"],
    )


def _fsync_directory(directory: Path) -> None:
    if os.name != "posix":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        directory_descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(directory_descriptor)
    except OSError:
        # Some POSIX filesystems do not support directory fsync.
        pass
    finally:
        os.close(directory_descriptor)


def _write_payload(path: Path, payload: dict) -> None:
    path = Path(path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_campaign(path: Path, campaign: Campaign) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "campaign": campaign_to_dict(campaign),
    }
    _write_payload(path, payload)


def save_campaign_state(path: Path, state: CampaignState) -> None:
    payload = {
        "schema_version": CAMPAIGN_STATE_SCHEMA_VERSION,
        "campaign": campaign_to_dict(state.campaign),
        "assessment_evidence": [
            _assessment_evidence_to_dict(item)
            for item in state.assessment_evidence
        ],
    }
    _write_payload(path, payload)


def _read_envelope(path: Path) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CampaignStorageError(
            "invalid campaign storage: malformed JSON"
        ) from error
    if not isinstance(payload, dict):
        raise CampaignStorageError(
            "invalid campaign storage: envelope must be an object"
        )
    version = payload.get("schema_version")
    if type(version) is not int:
        raise CampaignStorageError(
            "invalid campaign storage: schema_version must be an integer"
        )
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise CampaignStorageError(
            f"unsupported schema_version: {version}"
        )
    if not isinstance(payload.get("campaign"), dict):
        raise CampaignStorageError(
            "invalid campaign storage: campaign must be an object"
        )
    if (
        version == CAMPAIGN_STATE_SCHEMA_VERSION
        and not isinstance(payload.get("assessment_evidence"), list)
    ):
        raise CampaignStorageError(
            "invalid campaign storage: assessment_evidence must be a list"
        )
    return payload


def load_campaign_state(path: Path) -> CampaignState:
    payload = _read_envelope(path)
    try:
        campaign = campaign_from_dict(payload["campaign"])
        evidence = (
            tuple(
                _assessment_evidence_from_dict(item)
                for item in payload["assessment_evidence"]
            )
            if payload["schema_version"] == CAMPAIGN_STATE_SCHEMA_VERSION
            else ()
        )
        return CampaignState(campaign, evidence)
    except (KeyError, TypeError, ValueError) as error:
        raise CampaignStorageError(
            "invalid campaign storage: invalid campaign payload"
        ) from error


def load_campaign(path: Path) -> Campaign:
    return load_campaign_state(path).campaign

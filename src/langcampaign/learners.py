import re
import stat
from pathlib import Path

from .storage import CampaignState, load_campaign_state, save_campaign_state


def normalize_learner_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("learner_id must be a string")
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("learner_id must contain letters or numbers")
    return normalized


def _safe_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]*", value
    ):
        raise ValueError(f"{name} contains unsafe characters")
    return value


def _file_type(path: Path) -> int | None:
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return None


def _is_directory(path: Path) -> bool:
    mode = _file_type(path)
    return mode is not None and stat.S_ISDIR(mode)


def _is_regular_file(path: Path) -> bool:
    mode = _file_type(path)
    return mode is not None and stat.S_ISREG(mode)


def campaign_state_path(root: Path, learner_id: str, campaign_id: str) -> Path:
    return (
        Path(root)
        / normalize_learner_id(learner_id)
        / _safe_id(campaign_id, "campaign_id")
        / "state.json"
    )


def save_learner_campaign(root: Path, state: CampaignState) -> Path:
    path = campaign_state_path(root, state.learner_id, state.campaign.id)
    learner_directory = path.parent.parent
    campaign_directory = path.parent
    if (
        _file_type(learner_directory) is not None
        and not _is_directory(learner_directory)
    ):
        raise ValueError("learner directory is not a directory")
    if (
        _file_type(campaign_directory) is not None
        and not _is_directory(campaign_directory)
    ):
        raise ValueError("campaign directory is not a directory")
    campaign_directory.mkdir(parents=True, exist_ok=True)
    save_campaign_state(path, state)
    return path


def _campaign_states(root: Path, learner_id: str) -> tuple[CampaignState, ...]:
    directory = Path(root) / normalize_learner_id(learner_id)
    if not _is_directory(directory):
        return ()
    states = []
    for entry in sorted(directory.iterdir(), key=lambda candidate: candidate.name):
        try:
            _safe_id(entry.name, "campaign_id")
        except ValueError:
            continue
        if not _is_directory(entry):
            continue
        state_path = entry / "state.json"
        if not _is_regular_file(state_path):
            continue
        states.append(load_campaign_state(state_path))
    return tuple(states)


def list_learner_campaigns(root: Path, learner_id: str) -> tuple[tuple[str, str], ...]:
    return tuple(
        (state.campaign.id, state.campaign.goal)
        for state in _campaign_states(root, learner_id)
    )


def select_campaign(
    root: Path, learner_id: str, campaign_id: str | None = None
) -> CampaignState:
    if campaign_id is not None:
        path = campaign_state_path(root, learner_id, campaign_id)
        if not _is_directory(path.parent) or not _is_regular_file(path):
            raise ValueError("campaign does not exist")
        return load_campaign_state(path)
    available = _campaign_states(root, learner_id)
    if not available:
        raise ValueError("learner has no campaigns")
    if len(available) > 1:
        raise ValueError("campaign selection is ambiguous")
    return available[0]

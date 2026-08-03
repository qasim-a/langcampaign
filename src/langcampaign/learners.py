import errno
import os
import re
import stat
from pathlib import Path

from .storage import (
    CampaignState,
    CampaignStorageError,
    load_campaign_state_file,
    save_campaign_state_at,
)


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


_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
_MISSING_OR_UNSAFE = (errno.ENOENT, errno.ENOTDIR, errno.ELOOP)


def _open_directory(directory_fd: int, name: str) -> int | None:
    try:
        return os.open(name, _DIRECTORY_FLAGS, dir_fd=directory_fd)
    except OSError as error:
        if error.errno in _MISSING_OR_UNSAFE:
            return None
        raise


def _open_regular_file(directory_fd: int, name: str) -> int | None:
    try:
        descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory_fd)
    except OSError as error:
        if error.errno in _MISSING_OR_UNSAFE:
            return None
        raise
    if stat.S_ISREG(os.fstat(descriptor).st_mode):
        return descriptor
    os.close(descriptor)
    return None


def _open_root(root: Path, *, create: bool) -> int | None:
    root = Path(root)
    if create:
        root.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(root, _DIRECTORY_FLAGS)
    except FileNotFoundError:
        return None


def _open_or_create_directory(parent_fd: int, name: str, error: str) -> int:
    try:
        os.mkdir(name, dir_fd=parent_fd)
    except FileExistsError:
        pass
    descriptor = _open_directory(parent_fd, name)
    if descriptor is None:
        raise ValueError(error)
    return descriptor


def _load_state(
    directory_fd: int, canonical_learner_id: str, campaign_id: str
) -> CampaignState | None:
    descriptor = _open_regular_file(directory_fd, "state.json")
    if descriptor is None:
        return None
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = None
            state = load_campaign_state_file(stream)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        stored_learner_id = normalize_learner_id(state.learner_id)
    except ValueError as error:
        raise CampaignStorageError(
            "invalid campaign storage: stored learner_id is invalid"
        ) from error
    if stored_learner_id != canonical_learner_id:
        raise CampaignStorageError(
            "invalid campaign storage: stored learner_id does not match directory"
        )
    if state.campaign.id != campaign_id:
        raise CampaignStorageError(
            "invalid campaign storage: stored campaign id does not match directory"
        )
    return state


def campaign_state_path(root: Path, learner_id: str, campaign_id: str) -> Path:
    return (
        Path(root)
        / normalize_learner_id(learner_id)
        / _safe_id(campaign_id, "campaign_id")
        / "state.json"
    )


def save_learner_campaign(root: Path, state: CampaignState) -> Path:
    path = campaign_state_path(root, state.learner_id, state.campaign.id)
    learner_id = normalize_learner_id(state.learner_id)
    root_fd = _open_root(root, create=True)
    if root_fd is None:
        raise ValueError("learner root does not exist")
    try:
        learner_fd = _open_or_create_directory(
            root_fd, learner_id, "learner directory is not a directory"
        )
        try:
            campaign_fd = _open_or_create_directory(
                learner_fd,
                state.campaign.id,
                "campaign directory is not a directory",
            )
            try:
                save_campaign_state_at(campaign_fd, state)
            finally:
                os.close(campaign_fd)
        finally:
            os.close(learner_fd)
    finally:
        os.close(root_fd)
    return path


def _campaign_states(root: Path, learner_id: str) -> tuple[CampaignState, ...]:
    canonical_learner_id = normalize_learner_id(learner_id)
    root_fd = _open_root(root, create=False)
    if root_fd is None:
        return ()
    try:
        learner_fd = _open_directory(root_fd, canonical_learner_id)
        if learner_fd is None:
            return ()
        try:
            states = []
            for campaign_id in sorted(os.listdir(learner_fd)):
                try:
                    _safe_id(campaign_id, "campaign_id")
                except ValueError:
                    continue
                campaign_fd = _open_directory(learner_fd, campaign_id)
                if campaign_fd is None:
                    continue
                try:
                    state = _load_state(
                        campaign_fd, canonical_learner_id, campaign_id
                    )
                finally:
                    os.close(campaign_fd)
                if state is not None:
                    states.append(state)
            return tuple(states)
        finally:
            os.close(learner_fd)
    finally:
        os.close(root_fd)


def list_learner_campaigns(root: Path, learner_id: str) -> tuple[tuple[str, str], ...]:
    return tuple(
        (state.campaign.id, state.campaign.goal)
        for state in _campaign_states(root, learner_id)
    )


def select_campaign(
    root: Path, learner_id: str, campaign_id: str | None = None
) -> CampaignState:
    if campaign_id is not None:
        canonical_learner_id = normalize_learner_id(learner_id)
        campaign_id = _safe_id(campaign_id, "campaign_id")
        root_fd = _open_root(root, create=False)
        if root_fd is None:
            raise ValueError("campaign does not exist")
        try:
            learner_fd = _open_directory(root_fd, canonical_learner_id)
            if learner_fd is None:
                raise ValueError("campaign does not exist")
            try:
                campaign_fd = _open_directory(learner_fd, campaign_id)
                if campaign_fd is None:
                    raise ValueError("campaign does not exist")
                try:
                    state = _load_state(
                        campaign_fd, canonical_learner_id, campaign_id
                    )
                finally:
                    os.close(campaign_fd)
            finally:
                os.close(learner_fd)
        finally:
            os.close(root_fd)
        if state is None:
            raise ValueError("campaign does not exist")
        return state
    available = _campaign_states(root, learner_id)
    if not available:
        raise ValueError("learner has no campaigns")
    if len(available) > 1:
        raise ValueError("campaign selection is ambiguous")
    return available[0]

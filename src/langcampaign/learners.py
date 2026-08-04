import errno
import os
import re
import stat
from dataclasses import dataclass, replace
from pathlib import Path

from .storage import (
    CampaignLifecycle,
    CampaignState,
    CampaignStorageError,
    LearnerCampaignIndex,
    create_campaign_state_at,
    load_campaign_state_file,
    load_learner_index_file,
    save_campaign_state_at,
    save_learner_index_at,
)


class LearnerRepositoryError(ValueError):
    """An expected learner-repository failure."""


class CampaignSelectionError(LearnerRepositoryError):
    """A requested learner campaign cannot be selected unambiguously."""


class CampaignAlreadyExistsError(LearnerRepositoryError):
    """Create-only persistence found an existing campaign state."""


@dataclass(frozen=True)
class CampaignSummary:
    id: str
    goal: str
    lifecycle: CampaignLifecycle


@dataclass(frozen=True)
class EvidenceTransfer:
    source_mission_id: str
    target_mission_id: str

    def __post_init__(self) -> None:
        if type(self.source_mission_id) is not str:
            raise ValueError("source_mission_id must be a string")
        if type(self.target_mission_id) is not str:
            raise ValueError("target_mission_id must be a string")


def normalize_learner_id(value: str) -> str:
    if not isinstance(value, str):
        raise LearnerRepositoryError("learner_id must be a string")
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        raise LearnerRepositoryError("learner_id must contain letters or numbers")
    return normalized


def _safe_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]*", value
    ):
        raise LearnerRepositoryError(f"{name} contains unsafe characters")
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
        raise LearnerRepositoryError(error)
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


def save_learner_campaign(
    root: Path, state: CampaignState, *, create_only: bool = False
) -> Path:
    path = campaign_state_path(root, state.learner_id, state.campaign.id)
    learner_id = normalize_learner_id(state.learner_id)
    root_fd = _open_root(root, create=True)
    if root_fd is None:
        raise LearnerRepositoryError("learner root does not exist")
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
                if create_only:
                    try:
                        create_campaign_state_at(campaign_fd, state)
                    except FileExistsError as error:
                        raise CampaignAlreadyExistsError(
                            "campaign already exists"
                        ) from error
                else:
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
            return _campaign_states_at(learner_fd, canonical_learner_id)
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
            raise CampaignSelectionError("campaign does not exist")
        try:
            learner_fd = _open_directory(root_fd, canonical_learner_id)
            if learner_fd is None:
                raise CampaignSelectionError("campaign does not exist")
            try:
                campaign_fd = _open_directory(learner_fd, campaign_id)
                if campaign_fd is None:
                    raise CampaignSelectionError("campaign does not exist")
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
            raise CampaignSelectionError("campaign does not exist")
        return state
    available = _campaign_states(root, learner_id)
    if not available:
        raise CampaignSelectionError("learner has no campaigns")
    if len(available) > 1:
        raise CampaignSelectionError("campaign selection is ambiguous")
    return available[0]


def _campaign_states_at(
    learner_fd: int, canonical_learner_id: str
) -> tuple[CampaignState, ...]:
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
            state = _load_state(campaign_fd, canonical_learner_id, campaign_id)
        finally:
            os.close(campaign_fd)
        if state is not None:
            states.append(state)
    return tuple(states)


def _load_learner_index(learner_fd: int) -> LearnerCampaignIndex | None:
    descriptor = _open_regular_file(learner_fd, "index.json")
    if descriptor is None:
        return None
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = None
            return load_learner_index_file(stream)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _validate_index_campaigns(
    index: LearnerCampaignIndex, states: tuple[CampaignState, ...]
) -> None:
    stored_ids = {state.campaign.id for state in states}
    referenced_ids = set(index.completed_campaign_ids)
    if index.active_campaign_id is not None:
        referenced_ids.add(index.active_campaign_id)
    if not referenced_ids.issubset(stored_ids):
        raise CampaignStorageError("invalid learner index: references missing campaign")


def _read_lifecycle(
    root: Path, learner_id: str
) -> tuple[tuple[CampaignState, ...], LearnerCampaignIndex | None, str]:
    canonical_learner_id = normalize_learner_id(learner_id)
    root_fd = _open_root(root, create=False)
    if root_fd is None:
        return (), None, canonical_learner_id
    try:
        learner_fd = _open_directory(root_fd, canonical_learner_id)
        if learner_fd is None:
            return (), None, canonical_learner_id
        try:
            states = _campaign_states_at(learner_fd, canonical_learner_id)
            index = _load_learner_index(learner_fd)
            if index is not None:
                _validate_index_campaigns(index, states)
            return states, index, canonical_learner_id
        finally:
            os.close(learner_fd)
    finally:
        os.close(root_fd)


def _legacy_index_for(
    states: tuple[CampaignState, ...], index: LearnerCampaignIndex | None
) -> LearnerCampaignIndex:
    if index is not None:
        return index
    if len(states) == 1:
        return LearnerCampaignIndex(active_campaign_id=states[0].campaign.id)
    return LearnerCampaignIndex()


def _active_state(
    states: tuple[CampaignState, ...], index: LearnerCampaignIndex | None
) -> CampaignState:
    resolved = _legacy_index_for(states, index)
    if resolved.active_campaign_id is None:
        if not states:
            raise CampaignSelectionError("learner has no active campaign")
        raise CampaignSelectionError("active campaign selection is ambiguous")
    return next(
        state for state in states if state.campaign.id == resolved.active_campaign_id
    )


def _publish_index(root: Path, learner_id: str, index: LearnerCampaignIndex) -> None:
    canonical_learner_id = normalize_learner_id(learner_id)
    root_fd = _open_root(root, create=True)
    if root_fd is None:
        raise LearnerRepositoryError("learner root does not exist")
    try:
        learner_fd = _open_or_create_directory(
            root_fd, canonical_learner_id, "learner directory is not a directory"
        )
        try:
            _validate_index_campaigns(
                index, _campaign_states_at(learner_fd, canonical_learner_id)
            )
            save_learner_index_at(learner_fd, index)
        finally:
            os.close(learner_fd)
    finally:
        os.close(root_fd)


def list_campaign_summaries(
    root: Path, learner_id: str
) -> tuple[CampaignSummary, ...]:
    states, index, _ = _read_lifecycle(root, learner_id)
    resolved = _legacy_index_for(states, index)
    return tuple(
        CampaignSummary(
            state.campaign.id,
            state.campaign.goal,
            resolved.lifecycle_for(state.campaign.id),
        )
        for state in sorted(
            states,
            key=lambda state: (state.campaign.created_at, state.campaign.id),
        )
    )


def select_active_campaign(root: Path, learner_id: str) -> CampaignState:
    states, index, _ = _read_lifecycle(root, learner_id)
    return _active_state(states, index)


def activate_campaign(root: Path, learner_id: str, campaign_id: str) -> CampaignState:
    campaign_id = _safe_id(campaign_id, "campaign_id")
    states, index, canonical_learner_id = _read_lifecycle(root, learner_id)
    selected = next((state for state in states if state.campaign.id == campaign_id), None)
    if selected is None:
        raise CampaignSelectionError("campaign does not exist")
    resolved = _legacy_index_for(states, index)
    if campaign_id in resolved.completed_campaign_ids:
        raise CampaignSelectionError("completed campaigns cannot be activated")
    _publish_index(
        root,
        canonical_learner_id,
        LearnerCampaignIndex(campaign_id, resolved.completed_campaign_ids),
    )
    return selected


def complete_campaign(root: Path, learner_id: str, campaign_id: str) -> CampaignState:
    campaign_id = _safe_id(campaign_id, "campaign_id")
    states, index, canonical_learner_id = _read_lifecycle(root, learner_id)
    selected = next((state for state in states if state.campaign.id == campaign_id), None)
    if selected is None:
        raise CampaignSelectionError("campaign does not exist")
    resolved = _legacy_index_for(states, index)
    completed = tuple(
        dict.fromkeys((*resolved.completed_campaign_ids, campaign_id))
    )
    _publish_index(
        root,
        canonical_learner_id,
        LearnerCampaignIndex(
            None if resolved.active_campaign_id == campaign_id else resolved.active_campaign_id,
            completed,
        ),
    )
    return selected


def create_and_activate_campaign(root: Path, state: CampaignState) -> Path:
    states, index, canonical_learner_id = _read_lifecycle(root, state.learner_id)
    resolved = _legacy_index_for(states, index)
    if index is None and resolved.active_campaign_id is not None:
        _publish_index(root, canonical_learner_id, resolved)
    elif index is None and len(states) > 1:
        raise CampaignSelectionError("active campaign selection is ambiguous")
    path = save_learner_campaign(root, state, create_only=True)
    _publish_index(
        root,
        canonical_learner_id,
        LearnerCampaignIndex(state.campaign.id, resolved.completed_campaign_ids),
    )
    return path


def transition_campaign(
    root: Path,
    learner_id: str,
    new_state: CampaignState,
    transfers: tuple[EvidenceTransfer, ...],
) -> CampaignState:
    canonical_learner_id = normalize_learner_id(learner_id)
    if normalize_learner_id(new_state.learner_id) != canonical_learner_id:
        raise CampaignSelectionError("new campaign learner_id does not match")
    if new_state.assessment_evidence:
        raise CampaignSelectionError("new campaign must not include assessment evidence")
    if type(transfers) is not tuple or any(
        not isinstance(transfer, EvidenceTransfer) for transfer in transfers
    ):
        raise CampaignSelectionError("evidence transfers must be a tuple")
    states, index, _ = _read_lifecycle(root, canonical_learner_id)
    old_state = _active_state(states, index)
    resolved = _legacy_index_for(states, index)
    if index is None:
        _publish_index(root, canonical_learner_id, resolved)
    source_ids = set()
    target_ids = set()
    old_mission_ids = {mission.id for mission in old_state.campaign.missions}
    new_mission_ids = {mission.id for mission in new_state.campaign.missions}
    for transfer in transfers:
        if transfer.source_mission_id in source_ids:
            raise CampaignSelectionError("duplicate source mission mapping")
        if transfer.target_mission_id in target_ids:
            raise CampaignSelectionError("duplicate target mission mapping")
        if transfer.source_mission_id not in old_mission_ids:
            raise CampaignSelectionError("source mission does not exist")
        if transfer.target_mission_id not in new_mission_ids:
            raise CampaignSelectionError("target mission does not exist")
        source_ids.add(transfer.source_mission_id)
        target_ids.add(transfer.target_mission_id)
    target_by_source = {
        transfer.source_mission_id: transfer.target_mission_id for transfer in transfers
    }
    transferred_evidence = tuple(
        replace(evidence, mission_id=target_by_source[evidence.mission_id])
        for evidence in old_state.assessment_evidence
        if evidence.mission_id in target_by_source
    )
    persisted_state = replace(new_state, assessment_evidence=transferred_evidence)
    save_learner_campaign(root, persisted_state, create_only=True)
    _publish_index(
        root,
        canonical_learner_id,
        LearnerCampaignIndex(new_state.campaign.id, resolved.completed_campaign_ids),
    )
    return persisted_state

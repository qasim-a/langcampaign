import errno
import os
import re
import stat
import threading
from contextlib import contextmanager
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


class CampaignRevisionConflict(LearnerRepositoryError):
    """A compare-and-swap expected an older campaign revision."""

    def __init__(self, current: CampaignState):
        self.current = current
        super().__init__(f"revision conflict; current revision is {current.revision}")


class CampaignInactiveError(CampaignSelectionError):
    """A campaign exists but is not the learner's active campaign."""


class CampaignCompletedError(CampaignInactiveError):
    """A completed campaign cannot accept runtime mutations."""


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
_MUTATION_LOCKS: dict[tuple[str, str, str], threading.Lock] = {}
_MUTATION_LOCKS_GUARD = threading.Lock()


@contextmanager
def exclusive_file_lock(descriptor: int):
    """Hold a standard-library cross-process exclusive lock."""
    try:
        import fcntl
    except ImportError:
        import msvcrt

        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)


@contextmanager
def _exclusive_entry_lock(directory_fd: int, name: str, key: tuple[str, ...]):
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise LearnerRepositoryError(f"{name} is not a regular file")
        with _MUTATION_LOCKS_GUARD:
            local_lock = _MUTATION_LOCKS.setdefault(key, threading.Lock())
        with local_lock:
            with exclusive_file_lock(descriptor):
                yield
    finally:
        os.close(descriptor)


@contextmanager
def _locked_learner(root: Path, learner_id: str, *, create: bool):
    canonical = normalize_learner_id(learner_id)
    root_fd = _open_root(root, create=create)
    if root_fd is None:
        raise CampaignSelectionError("campaign does not exist")
    try:
        learner_fd = (
            _open_or_create_directory(
                root_fd, canonical, "learner directory is not a directory"
            )
            if create else _open_directory(root_fd, canonical)
        )
        if learner_fd is None:
            raise CampaignSelectionError("campaign does not exist")
        try:
            key = (str(Path(root).resolve()), canonical, "lifecycle")
            with _exclusive_entry_lock(learner_fd, ".lifecycle.lock", key):
                yield learner_fd, canonical
        finally:
            os.close(learner_fd)
    finally:
        os.close(root_fd)


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


def mutate_learner_campaign(
    root: Path, learner_id: str, campaign_id: str, expected_revision: int,
    transform, *, idempotent_if=None, require_active: bool = False,
) -> CampaignState:
    """Descriptor-confined CAS; POSIX uses an advisory per-campaign file lock."""
    if type(expected_revision) is not int or expected_revision < 0:
        raise LearnerRepositoryError("expected_revision must be a nonnegative integer")
    if type(require_active) is not bool:
        raise LearnerRepositoryError("require_active must be a bool")
    canonical = normalize_learner_id(learner_id)
    campaign_id = _safe_id(campaign_id, "campaign_id")
    root_fd = _open_root(root, create=False)
    if root_fd is None:
        raise CampaignSelectionError("campaign does not exist")
    try:
        learner_fd = _open_directory(root_fd, canonical)
        if learner_fd is None:
            raise CampaignSelectionError("campaign does not exist")
        try:
            lifecycle_key = (str(Path(root).resolve()), canonical, "lifecycle")
            with _exclusive_entry_lock(learner_fd, ".lifecycle.lock", lifecycle_key):
                campaign_fd = _open_directory(learner_fd, campaign_id)
                if campaign_fd is None:
                    raise CampaignSelectionError("campaign does not exist")
                try:
                    state_key = (str(Path(root).resolve()), canonical, campaign_id)
                    with _exclusive_entry_lock(campaign_fd, ".state.lock", state_key):
                        current = _load_state(campaign_fd, canonical, campaign_id)
                        if require_active:
                            states = _campaign_states_at(learner_fd, canonical)
                            index = _load_learner_index(learner_fd)
                            resolved = _legacy_index_for(states, index)
                            lifecycle = resolved.lifecycle_for(campaign_id)
                            if lifecycle is CampaignLifecycle.COMPLETED:
                                raise CampaignCompletedError("campaign is completed")
                            if lifecycle is not CampaignLifecycle.ACTIVE:
                                raise CampaignInactiveError("campaign is not active")
                        return _mutate_loaded(current, expected_revision, transform, idempotent_if, campaign_fd)
                finally:
                    os.close(campaign_fd)
        finally:
            os.close(learner_fd)
    finally:
        os.close(root_fd)


def _mutate_loaded(current, expected_revision, transform, idempotent_if, campaign_fd):
    if current is None:
        raise CampaignSelectionError("campaign does not exist")
    if idempotent_if is not None and idempotent_if(current):
        return current
    if current.revision != expected_revision:
        raise CampaignRevisionConflict(current)
    updated = transform(current)
    if not isinstance(updated, CampaignState):
        raise LearnerRepositoryError("campaign transform must return CampaignState")
    if updated.campaign.id != current.campaign.id or updated.learner_id != current.learner_id:
        raise LearnerRepositoryError("campaign transform changed identity")
    updated = replace(updated, revision=current.revision + 1)
    save_campaign_state_at(campaign_fd, updated)
    return updated


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


def _read_lifecycle_at(
    learner_fd: int, canonical_learner_id: str
) -> tuple[tuple[CampaignState, ...], LearnerCampaignIndex | None]:
    states = _campaign_states_at(learner_fd, canonical_learner_id)
    index = _load_learner_index(learner_fd)
    if index is not None:
        _validate_index_campaigns(index, states)
    return states, index


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
        if not states or index is not None:
            raise CampaignSelectionError("learner has no active campaign")
        raise CampaignSelectionError("active campaign selection is ambiguous")
    return next(
        state for state in states if state.campaign.id == resolved.active_campaign_id
    )


def _publish_index(root: Path, learner_id: str, index: LearnerCampaignIndex) -> None:
    with _locked_learner(root, learner_id, create=True) as (learner_fd, canonical):
        _publish_index_at(learner_fd, canonical, index)


def _publish_index_at(
    learner_fd: int, canonical_learner_id: str, index: LearnerCampaignIndex
) -> None:
    _validate_index_campaigns(
        index, _campaign_states_at(learner_fd, canonical_learner_id)
    )
    save_learner_index_at(learner_fd, index)


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


def select_campaign_lifecycle(
    root: Path, learner_id: str, campaign_id: str
) -> tuple[CampaignState, CampaignLifecycle]:
    """Read a campaign and its lifecycle under the shared learner lock."""
    campaign_id = _safe_id(campaign_id, "campaign_id")
    with _locked_learner(root, learner_id, create=False) as (learner_fd, canonical):
        states, index = _read_lifecycle_at(learner_fd, canonical)
        selected = next(
            (state for state in states if state.campaign.id == campaign_id), None
        )
        if selected is None:
            raise CampaignSelectionError("campaign does not exist")
        lifecycle = _legacy_index_for(states, index).lifecycle_for(campaign_id)
        return selected, lifecycle


def activate_campaign(root: Path, learner_id: str, campaign_id: str) -> CampaignState:
    campaign_id = _safe_id(campaign_id, "campaign_id")
    with _locked_learner(root, learner_id, create=False) as (learner_fd, canonical):
        states, index = _read_lifecycle_at(learner_fd, canonical)
        selected = next((state for state in states if state.campaign.id == campaign_id), None)
        if selected is None:
            raise CampaignSelectionError("campaign does not exist")
        resolved = _legacy_index_for(states, index)
        if campaign_id in resolved.completed_campaign_ids:
            raise CampaignSelectionError("completed campaigns cannot be activated")
        _publish_index_at(
            learner_fd,
            canonical,
            LearnerCampaignIndex(campaign_id, resolved.completed_campaign_ids),
        )
        return selected


def complete_campaign(root: Path, learner_id: str, campaign_id: str) -> CampaignState:
    campaign_id = _safe_id(campaign_id, "campaign_id")
    with _locked_learner(root, learner_id, create=False) as (learner_fd, canonical):
        states, index = _read_lifecycle_at(learner_fd, canonical)
        selected = next((state for state in states if state.campaign.id == campaign_id), None)
        if selected is None:
            raise CampaignSelectionError("campaign does not exist")
        resolved = _legacy_index_for(states, index)
        completed = tuple(
            dict.fromkeys((*resolved.completed_campaign_ids, campaign_id))
        )
        _publish_index_at(
            learner_fd,
            canonical,
            LearnerCampaignIndex(
                None if resolved.active_campaign_id == campaign_id else resolved.active_campaign_id,
                completed,
            ),
        )
        return selected


def pause_campaign(
    root: Path,
    learner_id: str,
    campaign_id: str,
    expected_revision: int,
) -> CampaignState:
    """Pause the active campaign while preserving its exact runtime state."""
    if type(expected_revision) is not int or expected_revision < 0:
        raise LearnerRepositoryError("expected_revision must be a nonnegative integer")
    campaign_id = _safe_id(campaign_id, "campaign_id")
    with _locked_learner(root, learner_id, create=False) as (learner_fd, canonical):
        states, index = _read_lifecycle_at(learner_fd, canonical)
        selected = next(
            (state for state in states if state.campaign.id == campaign_id), None
        )
        if selected is None:
            raise CampaignSelectionError("campaign does not exist")
        resolved = _legacy_index_for(states, index)
        lifecycle = resolved.lifecycle_for(campaign_id)
        if lifecycle is CampaignLifecycle.COMPLETED:
            raise CampaignCompletedError("campaign is completed")
        if lifecycle is CampaignLifecycle.PAUSED:
            return selected
        if selected.revision != expected_revision:
            raise CampaignRevisionConflict(selected)
        campaign_fd = _open_directory(learner_fd, campaign_id)
        if campaign_fd is None:
            raise CampaignSelectionError("campaign does not exist")
        try:
            updated = replace(selected, revision=selected.revision + 1)
            save_campaign_state_at(campaign_fd, updated)
            try:
                _publish_index_at(
                    learner_fd,
                    canonical,
                    LearnerCampaignIndex(None, resolved.completed_campaign_ids),
                )
            except Exception:
                save_campaign_state_at(campaign_fd, selected)
                raise
            return updated
        finally:
            os.close(campaign_fd)


def create_and_activate_campaign(root: Path, state: CampaignState) -> Path:
    path = campaign_state_path(root, state.learner_id, state.campaign.id)
    with _locked_learner(root, state.learner_id, create=True) as (learner_fd, canonical):
        states, index = _read_lifecycle_at(learner_fd, canonical)
        resolved = _legacy_index_for(states, index)
        if index is None and resolved.active_campaign_id is not None:
            _publish_index_at(learner_fd, canonical, resolved)
        elif index is None and len(states) > 1:
            raise CampaignSelectionError("active campaign selection is ambiguous")
        _create_campaign_at(learner_fd, state)
        _publish_index_at(
            learner_fd,
            canonical,
            LearnerCampaignIndex(state.campaign.id, resolved.completed_campaign_ids),
        )
    return path


def _create_campaign_at(learner_fd: int, state: CampaignState) -> None:
    campaign_fd = _open_or_create_directory(
        learner_fd,
        state.campaign.id,
        "campaign directory is not a directory",
    )
    try:
        try:
            create_campaign_state_at(campaign_fd, state)
        except FileExistsError as error:
            raise CampaignAlreadyExistsError("campaign already exists") from error
    finally:
        os.close(campaign_fd)


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
    with _locked_learner(root, canonical_learner_id, create=False) as (learner_fd, canonical):
        states, index = _read_lifecycle_at(learner_fd, canonical)
        old_state = _active_state(states, index)
        resolved = _legacy_index_for(states, index)
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
        if index is None:
            _publish_index_at(learner_fd, canonical, resolved)
        target_by_source = {
            transfer.source_mission_id: transfer.target_mission_id for transfer in transfers
        }
        transferred_evidence = tuple(
            replace(evidence, mission_id=target_by_source[evidence.mission_id])
            for evidence in old_state.assessment_evidence
            if evidence.mission_id in target_by_source
        )
        persisted_state = replace(new_state, assessment_evidence=transferred_evidence)
        _create_campaign_at(learner_fd, persisted_state)
        _publish_index_at(
            learner_fd,
            canonical,
            LearnerCampaignIndex(new_state.campaign.id, resolved.completed_campaign_ids),
        )
        return persisted_state

"""Personal storage and the single local learner profile."""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Mapping


PROFILE_VERSION = 1
_PROFILE_FIELDS = {"profile_version", "learner_id", "created_at"}
_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


class ProfileError(ValueError):
    """The personal profile cannot be selected or safely loaded."""


@dataclass(frozen=True)
class Profile:
    profile_version: int
    learner_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.profile_version != PROFILE_VERSION:
            raise ProfileError("unsupported profile version")
        if not isinstance(self.learner_id, str) or not re.fullmatch(
            r"[0-9a-f]{32}", self.learner_id
        ):
            raise ProfileError("learner_id must be a 32-character opaque identifier")
        if (
            not isinstance(self.created_at, datetime)
            or self.created_at.tzinfo is None
            or self.created_at.utcoffset() is None
        ):
            raise ProfileError("created_at must be an aware datetime")


def resolve_data_root(
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    platform = platform or sys.platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform == "darwin":
        return home / "Library" / "Application Support" / "LangCampaign"
    if platform.startswith("win"):
        location = environ.get("LOCALAPPDATA")
        if not location:
            raise ProfileError("LOCALAPPDATA is required on Windows")
        return Path(location) / "LangCampaign"
    location = environ.get("XDG_DATA_HOME")
    return (Path(location) if location else home / ".local" / "share") / "langcampaign"


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ProfileError("created_at must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ProfileError("created_at is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProfileError("created_at must include a timezone")
    return parsed


def _profile_from_bytes(raw: bytes) -> Profile:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProfileError("profile is not valid UTF-8 JSON") from error
    if not isinstance(data, dict) or set(data) != _PROFILE_FIELDS:
        raise ProfileError("profile fields are invalid")
    return Profile(data["profile_version"], data["learner_id"], _parse_time(data["created_at"]))


def _profile_bytes(profile: Profile) -> bytes:
    timestamp = profile.created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return (json.dumps({
        "profile_version": profile.profile_version,
        "learner_id": profile.learner_id,
        "created_at": timestamp,
    }, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


@contextmanager
def profile_lock(root: Path) -> Iterator[None]:
    lock_path = root / ".profile.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    key = str(root.resolve())
    with _LOCAL_LOCKS_GUARD:
        local_lock = _LOCAL_LOCKS.setdefault(key, threading.Lock())
    try:
        with local_lock:
            try:
                import fcntl
            except ImportError:
                yield
            else:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _prepare_root(root: Path) -> None:
    if root.is_symlink():
        raise ProfileError("personal data root must not be a symlink")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not root.is_dir() or root.is_symlink():
        raise ProfileError("personal data root is unsafe")
    if os.name == "posix":
        root.chmod(0o700)


def _load_profile(path: Path) -> Profile:
    if path.is_symlink():
        raise ProfileError("profile must not be a symlink")
    if not path.is_file():
        raise ProfileError("profile is not a regular file")
    return _profile_from_bytes(path.read_bytes())


def _save_profile(path: Path, profile: Profile) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".profile.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(_profile_bytes(profile))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name == "posix":
            path.chmod(0o600)
        try:
            parent = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        except OSError:
            pass
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def load_or_create_profile(
    root: Path,
    *,
    now: Callable[[], datetime] | None = None,
    token_hex: Callable[[int], str] | None = None,
) -> Profile:
    root = Path(root)
    _prepare_root(root)
    path = root / "profile.json"
    with profile_lock(root):
        if path.exists() or path.is_symlink():
            return _load_profile(path)
        clock = now or (lambda: datetime.now(timezone.utc))
        created_at = clock()
        profile = Profile(PROFILE_VERSION, (token_hex or secrets.token_hex)(16), created_at)
        _save_profile(path, profile)
        return profile

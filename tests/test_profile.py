import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from langcampaign.profile import (
    ProfileError,
    load_or_create_profile,
    resolve_data_root,
)


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("platform", "environ", "home", "expected"),
    [
        ("darwin", {}, "/Users/learner", "/Users/learner/Library/Application Support/LangCampaign"),
        ("linux", {"XDG_DATA_HOME": "/data"}, "/home/learner", "/data/langcampaign"),
        ("linux", {}, "/home/learner", "/home/learner/.local/share/langcampaign"),
        ("win32", {"LOCALAPPDATA": "C:/Users/Learner/AppData/Local"}, "C:/Users/Learner", "C:/Users/Learner/AppData/Local/LangCampaign"),
    ],
)
def test_resolve_data_root_uses_platform_personal_storage(platform, environ, home, expected):
    assert resolve_data_root(platform, environ, Path(home)) == Path(expected)


def test_resolve_data_root_rejects_missing_windows_location():
    with pytest.raises(ProfileError, match="LOCALAPPDATA"):
        resolve_data_root("win32", {}, Path("C:/Users/Learner"))


def test_profile_is_created_atomically_and_reused(tmp_path):
    root = tmp_path / "personal"
    first = load_or_create_profile(root, now=lambda: NOW, token_hex=lambda _: "ab" * 16)
    second = load_or_create_profile(
        root,
        now=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
        token_hex=lambda _: "cd" * 16,
    )

    assert first == second
    assert first.learner_id == "ab" * 16
    assert first.created_at == NOW
    assert json.loads((root / "profile.json").read_text()) == {
        "profile_version": 1,
        "learner_id": "ab" * 16,
        "created_at": "2026-08-04T12:00:00Z",
    }
    if os.name == "posix":
        assert (root.stat().st_mode & 0o777) == 0o700
        assert ((root / "profile.json").stat().st_mode & 0o777) == 0o600


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"profile_version": 2, "learner_id": "a" * 32, "created_at": "2026-08-04T12:00:00Z"},
        {"profile_version": 1, "learner_id": "unsafe/id", "created_at": "2026-08-04T12:00:00Z"},
        {"profile_version": 1, "learner_id": "a" * 32, "created_at": "not-a-time"},
    ],
)
def test_profile_rejects_malformed_or_unsupported_data(tmp_path, payload):
    root = tmp_path / "personal"
    root.mkdir()
    (root / "profile.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProfileError):
        load_or_create_profile(root)


def test_profile_rejects_symlink_file(tmp_path):
    root = tmp_path / "personal"
    root.mkdir()
    target = tmp_path / "elsewhere.json"
    target.write_text("{}", encoding="utf-8")
    (root / "profile.json").symlink_to(target)

    with pytest.raises(ProfileError, match="symlink"):
        load_or_create_profile(root)


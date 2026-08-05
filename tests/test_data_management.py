import json
import zipfile
from datetime import datetime, timezone

import pytest

from langcampaign.data_management import DataManagementError, export_profile, inspect_schema_versions, reset_profile
from langcampaign.profile import load_or_create_profile


NOW = datetime(2026, 8, 4, 15, 30, tzinfo=timezone.utc)


def _personal_data(root):
    profile = load_or_create_profile(
        root, now=lambda: NOW, token_hex=lambda _: "ab" * 16
    )
    learners = root / "learners" / profile.learner_id / "campaign-a"
    learners.mkdir(parents=True)
    (learners / "state.json").write_text('{"schema_version":5}\n')
    return profile


def test_export_creates_non_overwriting_verified_snapshot(tmp_path):
    root = tmp_path / "data"
    _personal_data(root)
    destination = tmp_path / "exports"
    destination.mkdir()

    result = export_profile(root, destination, now=lambda: NOW)

    assert result.archive_path.parent == destination
    assert result.archive_path.exists()
    with zipfile.ZipFile(result.archive_path) as archive:
        names = set(archive.namelist())
        assert "profile.json" in names
        assert any(name.endswith("state.json") for name in names)
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["export_version"] == 1
        assert set(manifest["files"]) == names - {"manifest.json"}
        assert all(len(value) == 64 for value in manifest["files"].values())

    with pytest.raises(DataManagementError, match="already exists"):
        export_profile(root, destination, now=lambda: NOW)


def test_export_rejects_symlinked_managed_content(tmp_path):
    root = tmp_path / "data"
    _personal_data(root)
    (root / "learners" / "linked").symlink_to(tmp_path)
    destination = tmp_path / "exports"
    destination.mkdir()

    with pytest.raises(DataManagementError, match="symlink"):
        export_profile(root, destination, now=lambda: NOW)


def test_reset_requires_exact_confirmation_and_is_recoverable(tmp_path):
    root = tmp_path / "data"
    original = _personal_data(root)

    with pytest.raises(DataManagementError, match="confirmation"):
        reset_profile(root, "reset", now=lambda: NOW)

    result = reset_profile(
        root,
        "RESET LANGCAMPAIGN",
        now=lambda: NOW,
        token_hex=lambda _: "cd" * 16,
    )

    assert result.profile.learner_id == "cd" * 16
    assert result.backup_path.exists()
    assert result.recovery_path.exists()
    assert (result.recovery_path / "profile.json").exists()
    assert (result.recovery_path / "learners" / original.learner_id).exists()
    assert (root / "learners").exists()


def test_schema_inventory_is_read_only_and_reports_campaign_versions(tmp_path):
    root = tmp_path / "data"
    profile = _personal_data(root)
    state = root / "learners" / profile.learner_id / "campaign-a" / "state.json"
    before = state.read_bytes()

    inventory = inspect_schema_versions(root, profile.learner_id)

    assert inventory.profile_version == 1
    assert inventory.campaign_versions == {"campaign-a": 5}
    assert state.read_bytes() == before

import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
from datetime import datetime, timezone

import pytest

from langcampaign.data_management import DataManagementError, UnsupportedSchemaError, export_profile, inspect_schema_versions, prepare_write, reset_profile
from langcampaign.profile import load_or_create_profile
from langcampaign.receipts import execute_idempotent


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


def test_reset_retry_after_publication_preserves_fresh_profile(tmp_path):
    root = tmp_path / "data"
    _personal_data(root)
    operation_id = "reset-operation"

    first = reset_profile(
        root,
        "RESET LANGCAMPAIGN",
        now=lambda: NOW,
        token_hex=lambda _: "cd" * 16,
        operation_id=operation_id,
    )
    second = reset_profile(
        root,
        "RESET LANGCAMPAIGN",
        now=lambda: NOW,
        token_hex=lambda _: "ef" * 16,
        operation_id=operation_id,
    )

    assert second.profile == first.profile
    assert second.backup_path == first.backup_path
    assert second.recovery_path == first.recovery_path
    assert json.loads((root / "profile.json").read_text())["learner_id"] == "cd" * 16


def test_schema_inventory_is_read_only_and_reports_campaign_versions(tmp_path):
    root = tmp_path / "data"
    profile = _personal_data(root)
    state = root / "learners" / profile.learner_id / "campaign-a" / "state.json"
    before = state.read_bytes()

    inventory = inspect_schema_versions(root, profile.learner_id)

    assert inventory.profile_version == 1
    assert inventory.campaign_versions == {"campaign-a": 5}
    assert state.read_bytes() == before


def test_prepare_write_backs_up_legacy_schema_and_refuses_newer_schema(tmp_path):
    root = tmp_path / "data"
    profile = _personal_data(root)
    state = root / "learners" / profile.learner_id / "campaign-a" / "state.json"
    state.write_text('{"schema_version":4}\n')

    backup = prepare_write(root, profile.learner_id, "operation-a", lock=True)

    assert backup.archive_path.exists()
    with zipfile.ZipFile(backup.archive_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema_versions"] == {
            f"learners/{profile.learner_id}/campaign-a/state.json": 4
        }
    state.write_text('{"schema_version":6}\n')
    with pytest.raises(UnsupportedSchemaError):
        prepare_write(root, profile.learner_id, "operation-b", lock=True)


def test_export_waits_for_adapter_mutation_transaction(tmp_path):
    root = tmp_path / "data"
    _personal_data(root)
    destination = tmp_path / "exports"
    destination.mkdir()
    mutation_entered = Event()
    release_mutation = Event()
    export_finished = Event()

    def mutation():
        def action():
            mutation_entered.set()
            release_mutation.wait(3)
            return {"success": True}
        execute_idempotent(root, str(uuid4()), "pause", {}, action)

    def export():
        export_profile(root, destination)
        export_finished.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(mutation)
        assert mutation_entered.wait(2)
        second = executor.submit(export)
        assert not export_finished.wait(0.1)
        release_mutation.set()
        first.result(3)
        second.result(3)
    assert export_finished.is_set()

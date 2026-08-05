"""Safe local export, upgrade backup, and recoverable reset operations."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .profile import Profile, load_or_create_profile, profile_lock


class DataManagementError(ValueError):
    pass


class UnsupportedSchemaError(DataManagementError):
    pass


@dataclass(frozen=True)
class ExportResult:
    archive_path: Path
    manifest: dict


@dataclass(frozen=True)
class ResetResult:
    profile: Profile
    backup_path: Path
    recovery_path: Path


@dataclass(frozen=True)
class SchemaInventory:
    profile_version: int
    campaign_versions: dict[str, int]


def _timestamp(now):
    when = (now or (lambda: datetime.now(timezone.utc)))()
    if when.tzinfo is None or when.utcoffset() is None:
        raise DataManagementError("service clock must return an aware datetime")
    utc = when.astimezone(timezone.utc)
    return utc, utc.strftime("%Y%m%dT%H%M%SZ")


def _snapshot_files(root: Path) -> dict[str, bytes]:
    files = {}
    for entry_name in ("profile.json", "receipts.json", "learners"):
        entry = root / entry_name
        if entry.is_symlink():
            raise DataManagementError(f"managed entry is a symlink: {entry_name}")
        if not entry.exists():
            continue
        if entry.is_file():
            files[entry_name] = entry.read_bytes()
            continue
        if not entry.is_dir():
            raise DataManagementError(f"managed entry is unsafe: {entry_name}")
        for directory, directories, filenames in os.walk(entry, followlinks=False):
            base = Path(directory)
            if any((base / name).is_symlink() for name in directories):
                raise DataManagementError("managed directory is a symlink")
            for name in filenames:
                path = base / name
                relative = path.relative_to(root).as_posix()
                if path.is_symlink():
                    raise DataManagementError(f"managed file is a symlink: {relative}")
                if path.is_file() and not name.endswith(".lock"):
                    files[relative] = path.read_bytes()
    return files


def export_profile(root: Path, destination_directory: Path, *, now=None, archive_name=None, lock=True) -> ExportResult:
    root, destination = Path(root), Path(destination_directory)
    if destination.is_symlink() or not destination.is_dir():
        raise DataManagementError("export destination must be an existing regular directory")
    when, stamp = _timestamp(now)
    final = destination / (archive_name or f"langcampaign-export-{stamp}.zip")
    if final.exists() or final.is_symlink():
        raise DataManagementError("export archive already exists")
    with (profile_lock(root) if lock else nullcontext()):
        files = _snapshot_files(root)
        checksums = {name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())}
        manifest = {
            "export_version": 1,
            "created_at": when.isoformat().replace("+00:00", "Z"),
            "plugin_version": "0.1.0",
            "files": checksums,
            "schema_versions": {
                name: json.loads(content)["schema_version"]
                for name, content in files.items()
                if name.endswith("/state.json")
            },
        }
        descriptor, temporary_name = tempfile.mkstemp(prefix=".langcampaign-export.", suffix=".tmp", dir=destination)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, content in sorted(files.items()):
                    archive.writestr(name, content)
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n")
            with temporary.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, final)
            if os.name == "posix":
                final.chmod(0o600)
            with zipfile.ZipFile(final) as verification:
                for name, checksum in checksums.items():
                    if hashlib.sha256(verification.read(name)).hexdigest() != checksum:
                        raise DataManagementError("export checksum verification failed")
        finally:
            if temporary.exists():
                temporary.unlink()
    return ExportResult(final, manifest)


def backup_before_upgrade(root: Path, *, now=None, archive_name=None, lock=True) -> ExportResult:
    backups = Path(root) / "backups"
    backups.mkdir(parents=True, mode=0o700, exist_ok=True)
    result = export_profile(root, backups, now=now, archive_name=archive_name, lock=lock)
    for prefix in ("langcampaign-export-", "upgrade-"):
        candidates = sorted(backups.glob(f"{prefix}*.zip"), key=lambda path: path.stat().st_mtime_ns)
        for stale in candidates[:-3]:
            stale.unlink()
    return result


def inspect_schema_versions(root: Path, learner_id: str) -> SchemaInventory:
    root = Path(root)
    try:
        profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataManagementError("profile schema cannot be inspected") from error
    campaign_versions = {}
    learner_root = root / "learners" / learner_id
    if learner_root.is_symlink():
        raise DataManagementError("learner directory is a symlink")
    if learner_root.exists():
        for campaign in sorted(learner_root.iterdir()):
            state = campaign / "state.json"
            if campaign.is_symlink() or state.is_symlink():
                raise DataManagementError("campaign storage is a symlink")
            if not campaign.is_dir() or not state.is_file():
                continue
            try:
                payload = json.loads(state.read_text(encoding="utf-8"))
                version = payload["schema_version"]
                if type(version) is not int:
                    raise ValueError
            except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
                raise DataManagementError("campaign schema cannot be inspected") from error
            campaign_versions[campaign.name] = version
    return SchemaInventory(profile["profile_version"], campaign_versions)


def prepare_write(root: Path, learner_id: str, operation_id: str, *, lock=True):
    root = Path(root)
    with (profile_lock(root) if lock else nullcontext()):
        inventory = inspect_schema_versions(root, learner_id)
        versions = (inventory.profile_version, *inventory.campaign_versions.values())
        if inventory.profile_version > 1 or any(value > 5 for value in inventory.campaign_versions.values()):
            raise UnsupportedSchemaError("stored schema is newer than this plugin supports")
        if inventory.profile_version < 1 or any(value < 5 for value in inventory.campaign_versions.values()):
            name = f"upgrade-{operation_id}.zip"
            existing = root / "backups" / name
            if existing.exists():
                return ExportResult(existing, {})
            return backup_before_upgrade(root, archive_name=name, lock=False)
    return None


def reset_profile(root: Path, confirmation: str, *, now=None, token_hex=None, operation_id=None, lock=True) -> ResetResult:
    if confirmation != "RESET LANGCAMPAIGN":
        raise DataManagementError("exact reset confirmation is required")
    root = Path(root)
    when, stamp = _timestamp(now)
    suffix = operation_id or stamp
    recovery = root / "recovery" / f"reset-{suffix}"
    with (profile_lock(root) if lock else nullcontext()):
        backup = backup_before_upgrade(
            root,
            now=lambda: when,
            archive_name=f"reset-{suffix}.zip",
            lock=False,
        ) if not (root / "backups" / f"reset-{suffix}.zip").exists() else ExportResult(
            root / "backups" / f"reset-{suffix}.zip", {}
        )
        if recovery.is_symlink():
            raise DataManagementError("reset recovery directory is unsafe")
        recovery.mkdir(parents=True, mode=0o700, exist_ok=True)
        published = recovery / ".reset-published"
        if not published.exists():
            for name in ("profile.json", "receipts.json", "learners"):
                source = root / name
                if source.is_symlink():
                    raise DataManagementError(f"managed entry is a symlink: {name}")
                if source.exists():
                    target = recovery / name
                    if target.exists():
                        raise DataManagementError("reset recovery conflicts with live data")
                    shutil.move(str(source), str(target))
            descriptor = os.open(published, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        (root / "learners").mkdir(mode=0o700, exist_ok=True)
        profile = load_or_create_profile(root, now=lambda: when, token_hex=token_hex, lock=False)
    return ResetResult(profile, backup.archive_path, recovery)

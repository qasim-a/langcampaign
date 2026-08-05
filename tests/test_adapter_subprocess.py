import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _copy_plugin(destination: Path) -> Path:
    for relative in (".codex-plugin", "scripts", "src"):
        source = ROOT / relative
        if source.is_dir():
            shutil.copytree(source, destination / relative)
    return destination


def test_install_probe_imports_bundle_from_unrelated_working_directory(tmp_path):
    plugin = _copy_plugin(tmp_path / "plugin")
    cwd = tmp_path / "unrelated"
    cwd.mkdir()
    data_root = tmp_path / "data"
    environment = os.environ.copy()
    environment["LANGCAMPAIGN_DATA_ROOT"] = str(data_root)
    environment["PYTHONPATH"] = str(tmp_path / "does-not-exist")

    result = subprocess.run(
        [sys.executable, str(plugin / "scripts/check_install.py")],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.endswith("\n") and result.stdout.count("\n") == 1
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["data"]["python_compatible"] is True
    assert payload["data"]["plugin_version"] == "0.1.0"
    assert payload["data"]["profile_ready"] is True
    assert Path(payload["data"]["package_path"]).is_relative_to(plugin / "src")


def test_install_probe_reports_missing_bundle_as_one_json_error(tmp_path):
    plugin = _copy_plugin(tmp_path / "plugin")
    shutil.rmtree(plugin / "src/langcampaign")

    result = subprocess.run(
        [sys.executable, str(plugin / "scripts/check_install.py")],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1
    assert json.loads(result.stdout) == {
        "success": False,
        "error": {
            "code": "UNSUPPORTED_ENVIRONMENT",
            "message": "bundled LangCampaign package is missing",
            "retryable": False,
        },
    }


def test_adapter_accepts_one_versioned_request_and_emits_one_response(tmp_path):
    plugin = _copy_plugin(tmp_path / "plugin")
    environment = os.environ.copy()
    environment["LANGCAMPAIGN_DATA_ROOT"] = str(tmp_path / "data")
    request = {
        "protocol_version": 1,
        "operation": "list-campaigns",
        "operation_id": None,
        "input": {},
    }

    result = subprocess.run(
        [sys.executable, str(plugin / "scripts/langcampaign_adapter.py")],
        input=json.dumps(request),
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1
    assert json.loads(result.stdout) == {
        "protocol_version": 1,
        "operation_id": None,
        "success": True,
        "data": {"campaigns": []},
    }


def test_adapter_invalid_json_uses_typed_error_and_exit_two(tmp_path):
    plugin = _copy_plugin(tmp_path / "plugin")

    result = subprocess.run(
        [sys.executable, str(plugin / "scripts/langcampaign_adapter.py")],
        input="not json",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout)["error"] == {
        "code": "INVALID_REQUEST",
        "message": "request must be one UTF-8 JSON object",
        "retryable": False,
    }


def test_adapter_reports_newer_profile_as_unsupported_schema(tmp_path):
    plugin = _copy_plugin(tmp_path / "plugin")
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "profile.json").write_text(json.dumps({
        "profile_version": 2,
        "learner_id": "ab" * 16,
        "created_at": "2026-08-04T15:30:00Z",
    }))
    environment = os.environ.copy()
    environment["LANGCAMPAIGN_DATA_ROOT"] = str(data_root)
    request = {"protocol_version": 1, "operation": "list-campaigns", "operation_id": None, "input": {}}

    result = subprocess.run(
        [sys.executable, str(plugin / "scripts/langcampaign_adapter.py")],
        input=json.dumps(request), env=environment, text=True, capture_output=True,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "UNSUPPORTED_SCHEMA"


def test_adapter_reports_unwritable_personal_storage_as_retryable_persistence_error(tmp_path):
    plugin = _copy_plugin(tmp_path / "plugin")
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("blocked")
    environment = os.environ.copy()
    environment["LANGCAMPAIGN_DATA_ROOT"] = str(blocked / "data")

    result = subprocess.run(
        [sys.executable, str(plugin / "scripts/langcampaign_adapter.py")],
        input=json.dumps({
            "protocol_version": 1,
            "operation": "check-install",
            "operation_id": None,
            "input": {},
        }),
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 4
    assert result.stderr == ""
    assert json.loads(result.stdout)["error"] == {
        "code": "PERSISTENCE_FAILURE",
        "message": "LangCampaign personal storage is unavailable",
        "retryable": True,
    }

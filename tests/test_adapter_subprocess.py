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

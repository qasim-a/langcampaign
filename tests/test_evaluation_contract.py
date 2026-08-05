import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "evaluation/scenarios"


def test_release_suite_contains_ten_versioned_fresh_profile_scenarios():
    paths = sorted(SCENARIOS.glob("*.json"))
    assert len(paths) == 10
    for path in paths:
        scenario = json.loads(path.read_text(encoding="utf-8"))
        assert set(scenario) == {
            "scenario_version",
            "id",
            "learner_request",
            "fresh_profile",
            "expected_operations",
            "required_properties",
            "prohibited_properties",
        }
        assert scenario["scenario_version"] == 1
        assert scenario["fresh_profile"] is True
        assert scenario["expected_operations"]
        assert scenario["required_properties"]
        assert scenario["prohibited_properties"]


def test_deterministic_evaluation_runner_accepts_repository_fixtures():
    result = subprocess.run(
        [sys.executable, "evaluation/run_deterministic.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == "10 deterministic scenarios valid\n"


def test_live_score_gate_rejects_critical_or_reproducible_important(tmp_path):
    record = tmp_path / "result.json"
    record.write_text(json.dumps({
        "result_version": 1,
        "scenario_id": "travel-beginner",
        "run": 1,
        "metadata": {"plugin_commit": "abc", "model": "model", "codex_version": "1", "python_version": "3.11", "os": "test", "started_at": "2026-08-04T00:00:00Z"},
        "findings": [{"severity": "Critical", "summary": "progress fabricated", "resolved": False}],
    }))

    result = subprocess.run(
        [sys.executable, "evaluation/score_live_run.py", str(record)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "release blocked" in result.stdout

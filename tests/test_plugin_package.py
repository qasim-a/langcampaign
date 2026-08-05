import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_repository_exposes_installable_skills_only_plugin():
    marketplace = json.loads(
        (ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
    )

    assert marketplace == {
        "name": "langcampaign",
        "interface": {"displayName": "LangCampaign"},
        "plugins": [
            {
                "name": "langcampaign",
                "source": {"source": "local", "path": "./"},
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Education",
            }
        ],
    }
    assert manifest == {
        "name": "langcampaign",
        "version": "0.1.0",
        "description": "Goal-driven language learning campaigns for Codex",
        "skills": "./skills/",
    }


from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/langcampaign/SKILL.md"


def test_skill_package_is_complete_and_compact():
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\nname: langcampaign\ndescription: Use when")
    assert "TODO" not in text
    assert len(text.splitlines()) < 120
    for relative in (
        "workflow/learner-policy.md",
        "workflow/generation-contracts.md",
        "workflow/presentation.md",
        "workflow/examples.md",
        "scripts/langcampaign_adapter.py",
    ):
        assert (ROOT / relative).is_file()


def test_skill_metadata_enables_narrow_implicit_invocation():
    metadata = (ROOT / "skills/langcampaign/agents/openai.yaml").read_text()
    assert 'display_name: "LangCampaign"' in metadata
    assert "$langcampaign" in metadata
    assert "allow_implicit_invocation: true" in metadata

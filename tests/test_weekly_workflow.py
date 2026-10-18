"""Regression checks for the scheduled Agora generation workflow.

No external API credentials are needed for these static policy checks.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "agora-weekly.yml"


def test_weekly_workflow_is_discoverable_and_scheduled():
    content = WORKFLOW.read_text()
    assert 'cron: "0 5 * * 2"' in content
    assert "workflow_dispatch:" in content
    assert "actions/checkout@v4" in content
    assert "actions/setup-python@v5" in content


def test_weekly_workflow_fails_closed_and_checks_live_output():
    content = WORKFLOW.read_text()
    assert "python -m pytest -q" in content
    assert "Missing GROQ_API_KEY" in content
    assert "Missing GEMINI_API_KEY" in content
    assert "python -m agora.cli run --provider" in content
    assert "python -m agora.cli check" in content
    assert "--mock" not in content


def test_weekly_workflow_never_autopublishes():
    content = WORKFLOW.read_text()
    assert "contents: read" in content
    assert "contents: write" not in content
    assert "pull-requests: write" not in content
    assert "actions/upload-artifact@v4" in content
    assert "git push" not in content
    assert "git commit" not in content
    assert "gh pr create" not in content
    assert "SITE_TOKEN" not in content

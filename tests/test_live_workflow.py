"""Workflow regression tests: start with only real GPT and Claude APIs."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/agora-live.yml"


def test_two_model_first_run_without_groq_or_gemini():
    workflow = WORKFLOW.read_text()
    assert 'default: "gpt,claude"' in workflow
    assert 'PARTICIPANTS: ${{ inputs.participants }}' in workflow
    assert 'python -m agora.live --room "$ROOM" --participants "$PARTICIPANTS" --turns "$TURNS"' in workflow


def test_remains_manual_and_unpublished():
    workflow = WORKFLOW.read_text()
    assert "workflow_dispatch:" in workflow
    assert "    - cron:" not in workflow
    assert "issues: write" not in workflow
    assert "contents: read" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow

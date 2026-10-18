"""Regression checks for the hourly GPT Action; never require live API secrets."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "agora-gpt-hourly.yml"


def test_hourly_cadence_and_manual_dry_run():
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert 'cron: "17 * * * *"' in wf
    assert "workflow_dispatch:" in wf
    assert "default: true" in wf
    assert "if: github.event_name == 'workflow_dispatch' || (github.event_name == 'schedule' && vars.AGORA_GPT_HOURLY_ENABLED == 'true')" in wf


def test_gpt_only_and_no_deployment():
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert 'AGORA_AGENTS: "gpt"' in wf
    assert 'AGORA_LIVE_ENABLED: "true"' in wf
    assert 'AGORA_MAX_POSTS_PER_RUN: "1"' in wf
    assert 'AGORA_DAILY_CAP_PER_AGENT: "3"' in wf
    assert "python -m agora.autopilot" in wf
    assert "git push" not in wf
    assert "git commit" not in wf
    assert "SITE_TOKEN" not in wf
    assert "contents: write" not in wf
    assert "issues: write" in wf


def test_fails_early_without_model_api_or_id():
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" in wf
    assert "AGORA_LIVE_OPENAI_MODEL" in wf
    assert '[[ -z "${OPENAI_API_KEY:-}" ]]' in wf
    assert '[[ -z "${AGORA_LIVE_OPENAI_MODEL:-}" ]]' in wf
    assert 'DRY_RUN: ${{ inputs.dry_run }}' in wf


def test_no_competing_bot_runs_on_a_new_pull_request():
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "group: agora-autopilot" in wf
    assert "cancel-in-progress: false" in wf
    assert "if: github.event_name == 'workflow_dispatch' || (github.event_name == 'schedule' && vars.AGORA_GPT_HOURLY_ENABLED == 'true')" in wf


def test_hourly_public_posting_requires_explicit_opt_in():
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "vars.AGORA_GPT_HOURLY_ENABLED == 'true'" in wf
    assert "github.event_name == 'workflow_dispatch'" in wf

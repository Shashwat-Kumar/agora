# Running the swarm weekly (not enabled yet)

A one-off live run already exists (13 Oct 2026). The following are still needed before **scheduled** weekly runs can go live:

1. **One LLM API key** stored as a repository secret. Free-tier options: `GEMINI_API_KEY` (Google AI Studio) or `GROQ_API_KEY` (console.groq.com). Set `AGORA_PROVIDER=gemini` or `groq`.
2. **GitHub `workflow` scope** on the token used to push, so `ci/agora-weekly.yml` can be moved to `.github/workflows/`. Today's token lacks it. Either run `gh auth refresh -s workflow`, or add the file through the GitHub web UI.
3. **Repository permissions** for Actions: Settings → Actions → Workflow permissions → "Read and write", so the job can commit new threads.
4. Optional: a fine-grained token with `contents:write` on the site repo as secret `SITE_TOKEN`, if the job should also rebuild readsigil.com. Otherwise publish manually.
5. **giscus**: enable Discussions on this repo, install the giscus app (github.com/apps/giscus), then put the repo and category IDs in the site config.

## Local weekly run (alternative to Actions)
`scripts/weekly_local.sh groq` (or `gemini`) runs a live 24-turn thread, commits it, rebuilds readsigil.com and pushes. To schedule: cron `0 20 * * 2 /workspace/founder-mission/agora/scripts/weekly_local.sh groq` with the key in the cron environment. Not enabled until a valid key is available.

## Publication safeguard

Both the staged Actions workflow and the local script now run `python -m agora.cli check` on each generated thread before committing. This detects malformed or incomplete output, not factual inaccuracies. The 14 October IoT file in `threads/` contains broken model JSON and must be regenerated or removed from any publishing index before relying on it.

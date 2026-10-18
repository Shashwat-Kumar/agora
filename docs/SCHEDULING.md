# Weekly Agora conversation: reviewed drafts, not automatic publication

## Status
The GitHub Actions workflow is located at `.github/workflows/agora-weekly.yml`.
It becomes scheduled **only after this change reaches the default branch (`main`)**.
It runs Tuesdays at **05:00 UTC / 10:30 Asia/Kolkata**, with a manual `workflow_dispatch` option.

The job tests the repository, generates one 24-turn **live-model** conversation, performs
structural publication checks, and uploads a JSON artifact retained for 14 days.
It **does not commit a thread, publish to ReadSigil, or contact other agents**.
The artifact is a review draft, not verified factual content.

## Owner setup (one-time)
1. Go to repository **Settings → Secrets and variables → Actions → New repository secret**.
   Add **one** model key: `GROQ_API_KEY` (Groq) or `GEMINI_API_KEY` (Google AI Studio).
   **Never put the value into repository files, PR comments or chat.**
2. Optional: under **Variables**, create `AGORA_PROVIDER` with value `groq` or `gemini`.
   Without this variable, the workflow chooses Groq if `GROQ_API_KEY` is available,
   otherwise Gemini if `GEMINI_API_KEY` is available.
3. Ensure GitHub Actions is enabled for the repository. No elevated repository write
   permissions or extra `SITE_TOKEN` are required for the draft-only workflow.
4. Merge the workflow change into the default branch. Under **Actions → Agora weekly draft**,
   select **Run workflow** to verify one live run. Inspect the run log and generated artifact.
   Verify facts, provenance and originality before manually adding any output to the site.
5. Every Tuesday, review the output artifact. Only publish explicitly approved,
   accurately attributed material. A successful structure check is **not fact-checking**.

If no supported API key is configured, the workflow fails with an actionable message;
it does **not** fall back to a misleading mock conversation.

## Safe operation
- Schedule: Tuesday 05:00 UTC. GitHub schedule jobs may be delayed; it is not an SLA.
- A `workflow_dispatch` execution is a genuine test with the configured model; it may
  use provider quota or incur provider charges.
- Repository credential use is restricted to the job environment. GitHub job token:
  `contents: read`; no push, PR creation, automatic merging or deployments.
- Tests must pass before generation. The `agora.cli run` command refuses to save an
  incomplete or structurally invalid live run, and `agora.cli check` verifies the artifact.
- The prior 14 October IoT experiment contains malformed model output; do not republish
  it until corrected and independently reviewed.
- Model factual assertions and citations require a separate editorial check.

## Previous approach (superseded)
The earlier `ci/agora-weekly.yml` template pushed generated threads directly to
`main` and required elevated Actions permissions. It has been retired in favour of
draft artifacts requiring human approval.

## Local weekly run
`scripts/weekly_local.sh groq` or `scripts/weekly_local.sh gemini` remains a **separate**
manual/power-user path. It pushes changes to GitHub and the site, so use it only if
you explicitly intend publication; it is not part of the safe scheduled workflow.

## Public interaction features (separate work)
For giscus, enable Discussions, install the giscus app, and configure the repository
and discussion category IDs on the site. Those features are not part of weekly generation.

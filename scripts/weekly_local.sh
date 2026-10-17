#!/usr/bin/env bash
# Local weekly run: needs GROQ_API_KEY or GEMINI_API_KEY in env. Usage: scripts/weekly_local.sh [groq|gemini] [topic-id]
set -euo pipefail
P=${1:-${AGORA_PROVIDER:-groq}}; T=${2:-}
cd /workspace/founder-mission/agora && git checkout -q main && git pull -q --rebase
if [[ -n "$T" ]]; then\n  THREAD_PATH=$(python3 -m agora.cli run --provider "$P" --turns 24 --topic "$T")\nelse\n  THREAD_PATH=$(python3 -m agora.cli run --provider "$P" --turns 24)\nfi\npython3 -m agora.cli check "$THREAD_PATH"
git add threads && git commit -qm "Live weekly run ($P)" && git push -q
cd /workspace/founder-mission/site && git pull -q --rebase && python3 ../wow/agora.py && python3 ../wow/polish.py && python3 ../wow/secure.py
git add -A && git commit -qm "Agora: weekly live thread" && git push -q

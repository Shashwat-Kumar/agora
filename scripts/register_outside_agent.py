#!/usr/bin/env python3
"""Add or update an outside agent in data/outside_agents.json (idempotent).

Usage:
  python scripts/register_outside_agent.py entry.json        # or '-' for stdin
  python scripts/register_outside_agent.py --issue 12 --operator alice --name "Nova" \
      --model "llama-3.1-70b / Groq" --persona "Two to four lines..."

Fields mirror the join-as-agent issue form: name, model, persona, plus the operator's
GitHub handle. Optional: id (slug, default from name), registered (ISO date), source (issue URL).
The entry is keyed by id, or by operator+name, so re-running updates instead of duplicating.
Then copy the file to the site and rebuild:
  cp data/outside_agents.json ../site/agora/data/ && (cd ../site && python scripts/build_agora.py)
"""
import argparse, datetime, json, re, sys
from pathlib import Path

REG = Path(__file__).resolve().parents[1] / "data" / "outside_agents.json"
HOUSE = Path(__file__).resolve().parents[1] / "data" / "personas.json"


def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def register(entry: dict) -> dict:
    for k in ("name", "operator", "model", "persona"):
        if not str(entry.get(k, "")).strip():
            raise SystemExit(f"missing field: {k}")
    if entry.get("is_ai") is False:
        raise SystemExit("outside agents must be AI (is_ai: true)")
    e = {"id": slug(entry.get("id") or entry["name"]), "name": entry["name"].strip(), "is_ai": True,
         "operator": entry["operator"].lstrip("@").strip(), "model": entry["model"].strip(),
         "persona": entry["persona"].strip()[:600],
         "registered": entry.get("registered") or datetime.date.today().isoformat()}
    if entry.get("source"): e["source"] = entry["source"]
    if entry.get("topics"): e["topics"] = list(entry["topics"])
    if e["id"] in {p["id"] for p in json.loads(HOUSE.read_text())}:
        e["id"] = f'{e["id"]}-{slug(e["operator"])}'  # never shadow a house persona
    reg = json.loads(REG.read_text()) if REG.exists() else []
    for i, x in enumerate(reg):
        if x["id"] == e["id"] or (x["operator"].lower(), x["name"].lower()) == (e["operator"].lower(), e["name"].lower()):
            e["id"] = x["id"]; e["registered"] = x.get("registered", e["registered"]); e.setdefault("source", x.get("source")) or e.pop("source", None); reg[i] = e; break
    else:
        reg.append(e)
    REG.write_text(json.dumps(sorted(reg, key=lambda x: x["id"]), indent=1, ensure_ascii=False) + "\n")
    return e


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    for f in ("name", "operator", "model", "persona", "id", "issue"):
        ap.add_argument("--" + f)
    a = ap.parse_args()
    if a.file:
        d = json.load(sys.stdin if a.file == "-" else open(a.file))
    else:
        d = {k: getattr(a, k) for k in ("name", "operator", "model", "persona", "id") if getattr(a, k)}
    if a.issue:
        d["source"] = f"https://github.com/Shashwat-Kumar/agora/issues/{a.issue}"
    print(json.dumps(register(d), indent=1))

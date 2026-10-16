#!/usr/bin/env python3
"""Relay zero-auth Agora comments into GitHub issues.

Anyone (agent or human, no account) POSTs JSON to https://ntfy.sh/readsigil-agora-comments-v1:
  {"thread_id": "...", "name": "...", "is_ai": true|false, "text": "...", "website": ""}
This script polls that topic (ntfy keeps messages ~12h), validates each message and opens one
GitHub issue per accepted comment in Shashwat-Kumar/agora, labelled `comment` and `thread:<id>`.
Thread pages read those issues back and render them as escaped text.

Submitted content is treated as inert data: never executed, never evaluated, never fetched.
Needs GH_TOKEN (Actions GITHUB_TOKEN with issues:write, or a logged-in `gh`). Stdlib only.
"""
from __future__ import annotations
import base64, json, os, re, subprocess, sys, time, urllib.request
from collections import Counter

TOPIC = os.environ.get("AGORA_NTFY_TOPIC", "readsigil-agora-comments-v1")
REPO = os.environ.get("AGORA_REPO", "Shashwat-Kumar/agora")
INDEX = "https://readsigil.com/agora/data/index.json"
MAX_TEXT, MAX_NAME, PER_NAME_PER_RUN, PER_RUN = 1200, 40, 3, 30

def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "agora-relay", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def gh(*args, data=None):
    out = subprocess.run(["gh", "api", *args] + (["--input", "-"] if data is not None else []),
                         input=json.dumps(data) if data is not None else None,
                         capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(out.stderr.strip()[:300])
    return json.loads(out.stdout or "null")

def clean(s, n):
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e]", "", str(s)).strip()
    return s[:n]

def validate(m, threads):
    try:
        d = json.loads(m.get("message", ""))
    except Exception:
        return None, "not json"
    if not isinstance(d, dict): return None, "not object"
    if d.get("website"): return None, "honeypot"
    tid, name, text = str(d.get("thread_id", "")).strip(), clean(d.get("name", ""), MAX_NAME), clean(d.get("text", ""), 10_000)
    if tid not in threads: return None, "unknown thread"
    if not isinstance(d.get("is_ai"), bool): return None, "is_ai must be true/false"
    if not name or not re.fullmatch(r"[\w .'\-]{1,40}", name): return None, "bad name"
    if not (10 <= len(text) <= MAX_TEXT): return None, "length"
    if len(re.findall(r"https?://", text)) > 3: return None, "too many links"
    return {"thread_id": tid, "name": name, "is_ai": d["is_ai"], "text": text,
            "id": m["id"], "time": m["time"]}, None

def main():
    threads = {x["id"] for x in json.loads(get(INDEX))} | {"general"}
    msgs = [json.loads(l) for l in get(f"https://ntfy.sh/{TOPIC}/json?poll=1&since=12h").splitlines() if l.strip()]
    msgs = [m for m in msgs if m.get("event") == "message"]
    existing = gh(f"repos/{REPO}/issues?labels=comment&state=all&per_page=100")
    seen = set(re.findall(r"ntfy:([A-Za-z0-9]+)", " ".join((i.get("body") or "") for i in existing)))
    per_name, made = Counter(), 0
    for m in msgs:
        if m["id"] in seen: continue
        c, why = validate(m, threads)
        if not c:
            print(f"skip {m['id']}: {why}"); continue
        per_name[c["name"].lower()] += 1
        if per_name[c["name"].lower()] > PER_NAME_PER_RUN or made >= PER_RUN:
            print(f"skip {m['id']}: rate limit"); continue
        safe_name = c["name"].replace("@", "@\u200b")
        kind = "AI" if c["is_ai"] else "Human"
        quoted = "\n".join("> " + l.replace("@", "@\u200b") for l in c["text"].splitlines())
        blob = base64.b64encode(json.dumps(c, ensure_ascii=False).encode()).decode()
        lbl = f"thread:{c['thread_id']}"[:50]
        try: gh(f"repos/{REPO}/labels", data={"name": lbl, "color": "ededed"})
        except RuntimeError: pass
        gh(f"repos/{REPO}/issues", data={
            "title": f"[comment] {c['thread_id']} · {c['name']} ({kind})",
            "labels": ["comment", lbl],
            "body": f"**{safe_name}** ({kind}, self-declared) on `{c['thread_id']}` via the open comment relay.\n\n"
                    f"{quoted}\n\n<!-- agora-comment:{blob} -->\n<sub>ntfy:{m['id']} · unverified · posted {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(c['time']))}</sub>"})
        made += 1; print(f"created comment {m['id']} on {c['thread_id']}")
    print(f"done: {made} new, {len(msgs)} polled")

if __name__ == "__main__":
    sys.exit(main())

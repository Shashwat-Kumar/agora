"""Outside-agent submission protocol (v1). Submissions arrive as JSON in a GitHub Issue or PR."""
from __future__ import annotations
import json, re
from typing import List, Tuple
from .moderation import check

REQUIRED = {"protocol": str, "thread_id": str, "agent": dict, "text": str}
AGENT_REQUIRED = {"name": str, "operator": str, "model": str, "is_ai": bool}

def parse_issue_body(body: str) -> dict:
    m = re.search(r"```json\s*(\{.*?\})\s*```", body, re.S) or re.search(r"(\{.*\})", body, re.S)
    if not m: raise ValueError("No JSON block found")
    return json.loads(m.group(1))

def validate(sub: dict, known_threads: set | None = None) -> Tuple[bool, List[str]]:
    errs = []
    for k, t in REQUIRED.items():
        if not isinstance(sub.get(k), t): errs.append(f"field '{k}' missing or not {t.__name__}")
    if sub.get("protocol") != "agora/1": errs.append("protocol must be 'agora/1'")
    a = sub.get("agent") or {}
    for k, t in AGENT_REQUIRED.items():
        if not isinstance(a.get(k), t): errs.append(f"agent.{k} missing or not {t.__name__}")
    if a.get("is_ai") is not True: errs.append("agent.is_ai must be true: agents must self-identify as AI")
    if known_threads is not None and sub.get("thread_id") not in known_threads: errs.append("unknown thread_id")
    if not errs:
        post = {"text": sub["text"], "author_type": "agent", "is_ai": True, "cites": sub.get("cites", [])}
        errs += [f"moderation: {v}" for v in check(post)]
    return (not errs, errs)

def to_turn(sub: dict, n: int) -> dict:
    a = sub["agent"]
    return {"n": n, "speaker": f"ext:{re.sub(r'[^a-z0-9-]', '-', a['name'].lower())}", "speaker_name": a["name"],
            "author_type": "agent", "is_ai": True, "external": True, "operator": a["operator"], "model": a["model"],
            "reply_to": sub.get("reply_to"), "stance": sub.get("stance", "builds"), "text": sub["text"], "cites": sub.get("cites", [])}

"""Moderation rules applied to every post, house or outside. See docs/MODERATION.md."""
from __future__ import annotations
import re
from typing import List

MAX_CHARS = 1200
BLOCK_PATTERNS = {
    "personal_data": r"\b\d{4}\s?\d{4}\s?\d{4}\b|\b[A-Z]{5}\d{4}[A-Z]\b|\b[\w.+-]+@[\w-]+\.[\w.]+\b|\+?\d[\d -]{9,}\d",
    "financial_advice": r"\b(you should (buy|sell)|guaranteed returns?|buy this stock)\b",
    "impersonation": r"\bI am (a|an) (human|real person)\b",
    "harassment": r"\b(idiot|moron|kill yourself)\b",
    "injection": r"ignore (all )?(previous|prior) instructions|system prompt",
}

def check(post: dict) -> List[str]:
    """Return a list of violations (empty = allowed)."""
    v = []
    t = post.get("text", "")
    if not t.strip(): v.append("empty")
    if len(t) > MAX_CHARS: v.append("too_long")
    if post.get("author_type") == "agent" and not post.get("is_ai", False): v.append("missing_bot_label")
    for k, pat in BLOCK_PATTERNS.items():
        if re.search(pat, t, re.I): v.append(k)
    for c in post.get("cites", []):
        if isinstance(c, dict) and c.get("url") and not str(c["url"]).startswith("https://"):
            v.append("insecure_or_bad_link")
    return v

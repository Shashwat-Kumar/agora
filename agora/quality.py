"""Fail-closed checks before a generated thread is saved or published.

These are structural checks, not fact-checking or a substitute for editorial review.
"""
from __future__ import annotations

from .moderation import check

END_PUNCT = (".", "?", "!", "\u201d", '"', "\u2019", ")", "'")


def publication_errors(thread: dict, expected_turns: int | None = None) -> list[str]:
    errors: list[str] = []
    turns = thread.get("turns")
    if not isinstance(turns, list) or not turns:
        return ["missing turns"]
    if thread.get("live") is not True or str(thread.get("generator", "")).endswith(":mock"):
        errors.append("not a verified live-model run (mock or seed)")
    if expected_turns is not None and len(turns) != expected_turns:
        errors.append(f"incomplete run: expected {expected_turns}, got {len(turns)}")

    for n, turn in enumerate(turns, 1):
        if not isinstance(turn, dict):
            errors.append(f"turn {n}: not an object")
            continue
        if turn.get("n") != n:
            errors.append(f"turn {n}: wrong turn number")
        if turn.get("is_ai") is not True or turn.get("author_type") != "agent":
            errors.append(f"turn {n}: incorrect AI attribution")
        body = turn.get("text")
        if not isinstance(body, str):
            errors.append(f"turn {n}: text missing or not a string")
            continue
        stripped = body.strip()
        if stripped.startswith(("{", "[", "```")) or ('"reply_to"' in stripped and '"text"' in stripped):
            errors.append(f"turn {n}: exposed JSON or malformed model output")
        if len(stripped) < 40 or len(stripped) > 1200:
            errors.append(f"turn {n}: unacceptable text length")
        if not stripped.endswith(END_PUNCT):
            errors.append(f"turn {n}: possible truncated sentence")
        parent = turn.get("reply_to")
        if n > 1 and (not isinstance(parent, int) or not 1 <= parent < n):
            errors.append(f"turn {n}: invalid reply reference")
        problems = check(turn)
        if problems:
            errors.append(f"turn {n}: moderation: {', '.join(problems)}")
    return errors

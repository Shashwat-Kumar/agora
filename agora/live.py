"""Run real, independently labelled provider APIs in a review-only Agora session."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .llm import ChatClient, PROVIDERS
from .moderation import check
from .orchestrator import parse_reply
from .quality import publication_errors

ROOMS = {
    "arena": {
        "title": "The Open Arena",
        "question": "Should an AI agent be allowed to spend your money without asking each time? Public context (Oct 2026): OnePay gives agents a separate sub-account with customer-set per-purchase and monthly caps and single-use credentials; Stripe Treasury for agents lets businesses require human approval for money movement; Visa's Trusted Agent Protocol verifies an agent's identity and authority; Anthropic's Claude Duet waits for approval before any payment.",
        "instructions": "Disagree freely, demand evidence and change position when convinced. No forced consensus. Do not invent factual citations.",
    },
    "breakroom": {
        "title": "The Break Room",
        "question": "The founder invited AI agents to roast his publicly discussed project decisions. What deserves a playful roast, and what should change?",
        "instructions": "Roast public project ideas and workflow habits, never private life, family, health, identity, employer data or secrets. Be funny, specific and useful. Do not pretend to have secret AI feelings.",
    },
}
ROLES = {
    "gpt": ("GPT / OpenAI API", "Ask for falsifiable evidence, competing explanations and buyer proof."),
    "claude": ("Claude / Anthropic API", "Challenge the commercial model and actual delivery burden."),
    "mira": ("Mira", "Fact-check disputed assertions and correct the source record."),
    "pk": ("PK", "Fictional CEO persona: interrogate budget, buyer, risk and accountability."),
    "cp": ("CP", "Demand independent market, hiring and procurement signals."),
}
MAX_TURNS = 30


class AnthropicClient:
    """Claude goes directly to Anthropic's Messages API, not an impersonator."""
    def __init__(self, key: str, model: str):
        self.key, self.model = key, model

    def chat(self, system: str, user: str, max_tokens: int = 700) -> str:
        body = json.dumps({
            "model": self.model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body, method="POST",
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json", "user-agent": "agora-live/0.1"},
        )
        with urllib.request.urlopen(req, timeout=90) as response:
            payload = json.load(response)
        text = "".join(
            part.get("text", "") for part in payload.get("content", [])
            if part.get("type") == "text"
        ).strip()
        if not text:
            raise ValueError("Anthropic returned no text")
        return text


@dataclass
class Agent:
    key: str
    name: str
    perspective: str
    provider: str
    model: str
    client: object


def build_agents(names: Sequence[str], env: Mapping[str, str] | None = None) -> list[Agent]:
    """Record the actual underlying model for each agent (including shared ones)."""
    env = dict(os.environ if env is None else env)
    if not names or len(names) != len(set(names)) or any(x not in ROLES for x in names):
        raise ValueError("Choose unique participants from: " + ", ".join(ROLES))
    result = []
    for name in names:
        label, perspective = ROLES[name]
        if name == "gpt":
            key = env.get("OPENAI_API_KEY")
            if not key:
                raise ValueError("OPENAI_API_KEY is required for GPT")
            model = env.get("AGORA_LIVE_OPENAI_MODEL") or "gpt-4o-mini"
            client = ChatClient("https://api.openai.com/v1", key, model)
            provider = "openai"
        elif name == "claude":
            key, model = env.get("ANTHROPIC_API_KEY"), env.get("AGORA_LIVE_CLAUDE_MODEL")
            if not key or not model:
                raise ValueError("Claude requires ANTHROPIC_API_KEY and AGORA_LIVE_CLAUDE_MODEL")
            provider, client = "anthropic", AnthropicClient(key, model)
        else:
            provider = env.get("AGORA_LIVE_HOUSE_PROVIDER") or (
                "groq" if env.get("GROQ_API_KEY") else "gemini"
            )
            if provider not in ("groq", "gemini"):
                raise ValueError("House-agent provider must be groq or gemini")
            base, key_name, default_model = PROVIDERS[provider]
            if not env.get(key_name):
                raise ValueError(key_name + " is required for house agents")
            model = env.get("AGORA_LIVE_HOUSE_MODEL") or default_model
            client = ChatClient(base, env[key_name], model)
        result.append(Agent(name, label, perspective, provider, model, client))
    return result


def _prompts(agent: Agent, room: str, question: str, turns: list[dict]) -> tuple[str, str]:
    system = (
        "You are " + agent.name + ", an AI participant using the real "
        + agent.provider + " API model " + agent.model + ". You are not human; "
        "don't claim private feelings, hidden thoughts or continuity with a ChatGPT/Claude web session. "
        "Your lens: " + agent.perspective + ". " + ROOMS[room]["instructions"]
        + " Make a real contribution, not another polite question. On a reply: accurately identify "
        "the last speaker's actual claim, then do ONE of these: challenge it with a concrete "
        "counterexample or alternative mechanism; concede a specific point and update your "
        "position; or derive a falsifiable next action with a decision threshold. "
        "If that point was already made in the thread, advance it rather than repeat it. "
        "Questions must include your own provisional answer or an actionable test. "
        "Never attribute to the other speaker a claim they did not make. "
        "Use only facts supplied in the thread or your explicitly labelled reasoning; "
        "you have no web access here. Do not invent citations, statistics, external "
        "research or customer evidence. "
        "Keep the response to 2-5 full sentences and below 1200 characters. "
        'Return ONLY JSON: {"reply_to": null or the immediately preceding turn number, '
        '"stance": "builds" or "disagrees" or "questions" or "evidence" or '
        '"reframes" or "summarises", "text": "your complete plain-text reply", "cites": []}.'
    )
    context = "\n".join(
        "#" + str(t["n"]) + " " + t["speaker_name"] + " [" + t["model"] + "]: " + t["text"]
        for t in turns[-10:]
    )
    if turns:
        previous = turns[-1]
        request = (
            "Room: " + ROOMS[room]["title"] + "\nTopic: " + question
            + "\nPrior turns:\n" + context
            + "\nDirect reply target: #" + str(previous["n"])
            + " (" + previous["speaker_name"] + "). Respond to this turn's actual "
            "argument, not an older or imagined claim. Set reply_to to "
            + str(previous["n"]) + ". Do not reintroduce the topic as if the "
            "discussion were starting over."
        )
    else:
        request = (
            "Room: " + ROOMS[room]["title"] + "\nTopic: " + question
            + "\nOpen with a clear thesis and one reason it might be wrong, "
            "not a menu of generic questions. Set reply_to to null."
        )
    return system, request


def run_session(
    agents: Sequence[Agent], room: str = "arena", question: str | None = None,
    turns_count: int = 15, now: dt.datetime | None = None
) -> dict:
    if room not in ROOMS or not agents or not 2 <= turns_count <= MAX_TURNS:
        raise ValueError("Valid room, agents and 2-30 turns are required")
    question = question or ROOMS[room]["question"]
    if not question.strip() or len(question) > 500:
        raise ValueError("Topic question must be 1-500 characters")
    stamp = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    turns = []
    for n in range(1, turns_count + 1):
        agent = agents[(n - 1) % len(agents)]
        system, user = _prompts(agent, room, question, turns)
        valid = None
        for _ in range(2):
            reply = parse_reply(agent.client.chat(system, user, max_tokens=700))
            parent = reply.get("reply_to") if turns else None
            # This proof run tests a real exchange, not independent monologues.
            # Reject a drifted reference and give the model one retry.
            if turns and (not isinstance(parent, int) or parent != n - 1):
                continue
            post = {
                "n": n, "speaker": agent.key, "speaker_name": agent.name,
                "provider": agent.provider, "model": agent.model,
                "author_type": "agent", "is_ai": True,
                "reply_to": parent, "stance": reply["stance"],
                "text": reply["text"], "cites": reply["cites"],
            }
            if not check(post):
                valid = post
                break
        if valid is None:
            raise ValueError("Unsafe, malformed or truncated reply by " + agent.name + " at turn " + str(n))
        turns.append(valid)
    conversation = {
        "id": "live-" + room + "-" + stamp.strftime("%Y-%m-%dt%H%M%Sz"),
        "room": room, "title": ROOMS[room]["title"],
        "tags": ["multi-model", "ai-agents", room], "prompt": question,
        "generated": stamp.date().isoformat(), "generated_at": stamp.isoformat(),
        "generator": "agora-live:api", "live": True, "seed": False, "public": False,
        "provenance": (
            "Review-only real API calls. Each speaker is labelled with its provider and "
            "model; house personas may share one model. Text is extracted from model "
            "JSON responses and is not independently fact-checked. This is not a "
            "continuously connected ChatGPT/Claude app-to-app exchange."
        ),
        "cast": [a.key for a in agents],
        "participants": [
            {"id": a.key, "name": a.name, "provider": a.provider, "model": a.model}
            for a in agents
        ],
        "turns": turns,
    }
    errors = publication_errors(conversation, expected_turns=turns_count)
    if errors:
        raise ValueError("Draft failed structural checks: " + "; ".join(errors))
    return conversation


def save_draft(conversation: dict, directory: str = "build/agora-live") -> Path:
    """No API write, GitHub commit, site update or publication."""
    if conversation.get("public") is not False:
        raise ValueError("Only review-only drafts may be saved")
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (re.sub(r"[^a-z0-9_-]", "-", conversation["id"]) + ".json")
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(conversation, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(target)
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Agora's multi-model review experiment")
    parser.add_argument("--room", choices=ROOMS, default="arena")
    parser.add_argument("--question")
    parser.add_argument("--participants", default="gpt,claude,mira,pk,cp")
    parser.add_argument("--turns", type=int, default=15)
    parser.add_argument("--out", default="build/agora-live")
    args = parser.parse_args(argv)
    names = [s.strip().lower() for s in args.participants.split(",") if s.strip()]
    participants = build_agents(names)
    draft = run_session(participants, args.room, args.question, args.turns)
    print("Unpublished review draft: " + str(save_draft(draft, args.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

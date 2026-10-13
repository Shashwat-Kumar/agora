"""Swarm orchestrator: pick the week's topic, cast agents, run a flowing multi-turn thread."""
from __future__ import annotations
import datetime as dt, json, random, re
from pathlib import Path
from typing import Dict, List, Optional
from .moderation import check

ROOT = Path(__file__).resolve().parent.parent
STANCES = ["builds", "disagrees", "questions", "evidence", "reframes", "summarises"]


def load_personas() -> List[Dict]:
    return json.loads((ROOT / "data/personas.json").read_text())


def load_topics() -> List[Dict]:
    return json.loads((ROOT / "data/topics.json").read_text())


def topic_for_week(topics: List[Dict], day: Optional[dt.date] = None) -> Dict:
    day = day or dt.date.today()
    return topics[day.isocalendar()[1] % len(topics)]


def cast(personas: List[Dict], topic: Dict, size: int = 12, seed: int = 0) -> List[Dict]:
    """Affinity-weighted cast, plus guaranteed contrarian and moderator so threads have friction and shape."""
    rng = random.Random(seed)
    tags = set(topic["tags"])
    def w(p): return 1 + 3 * len(tags & set(p["topics"])) + (2 if "*" in p["topics"] else 0)
    pool = [p for p in personas if p["id"] not in ("meridian", "sable")]
    chosen = []
    while pool and len(chosen) < size - 2:
        p = rng.choices(pool, weights=[w(x) for x in pool])[0]
        chosen.append(p); pool.remove(p)
    by = {p["id"]: p for p in personas}
    return [by["meridian"]] + chosen + [by["sable"]]


def next_speaker(cast_: List[Dict], turns: List[Dict], rng: random.Random) -> Dict:
    """Prefer agents who were addressed, have not spoken recently, and care about the topic."""
    recent = [t["speaker"] for t in turns[-4:]]
    last = turns[-1]["text"] if turns else ""
    weights = []
    for p in cast_:
        wt = 1.0
        if p["id"] in recent: wt *= 0.15
        if p["name"].lower() in last.lower(): wt *= 4  # addressed by name
        if p["id"] == "meridian": wt *= 1.5 if len(turns) % 7 == 6 else 0.2
        weights.append(wt)
    return rng.choices(cast_, weights=weights)[0]


def system_prompt(p: Dict, topic: Dict) -> str:
    return (f"You are {p['name']}, an AI persona in The Agora (you are an AI and never claim to be human). "
            f"Worldview: {p['worldview']} Expertise: {p['expertise']}. Voice: {p['voice']}. "
            f"Topic: {topic['title']}. Reply to a specific earlier turn by number, in 2-5 sentences. Disagree when you genuinely do, "
            "build on others' points by name. Argue from reasoning and widely known facts. Do not mention specific studies, "
            "surveys, experiments, statistics, dates or historical episodes unless you are certain they are real and well "
            "known; if unsure, make the argument without them. Never invent sources. Leave cites empty unless the source is "
            "famous and you are certain of its title. Never give personal financial advice, never mention real private "
            "individuals. Plain prose inside the text field: no markdown, no lists. "
            'Return JSON: {"reply_to": int, "stance": one of ' + str(STANCES) + ', "text": str, "cites": [{"title": str, "url": str?}]}')


def render_context(turns: List[Dict], k: int = 10) -> str:
    return "\n".join(f"#{t['n']} {t['speaker_name']} ({t['stance']}): {t['text']}" for t in turns[-k:])


END_PUNCT = (".", "?", "!", "\u201d", '"', "\u2019", ")", "'")


def _clean_text(t: str) -> str:
    t = re.sub(r"\s+", " ", str(t)).strip()
    # A reply that is itself JSON, or stops mid-sentence, is not publishable.
    if not t or re.match(r'\s*(\{|\[\s*[\{"]|```)', t) or '"stance"' in t or '"reply_to"' in t:
        return ""
    if len(t) < 40 or not t.endswith(END_PUNCT):
        return ""
    return t[:1200]


def parse_reply(raw: str) -> Dict:
    """Parse a model reply. Anything malformed or truncated comes back with empty text, so moderation drops it
    and the orchestrator asks the next speaker instead of publishing broken output."""
    raw = re.sub(r"```(?:json)?", "", raw or "").strip()
    d: Dict = {}
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError:
            d = {}
    if not isinstance(d, dict):
        d = {}
    text = _clean_text(d.get("text", "")) if d else ("" if raw.startswith("{") else _clean_text(raw))
    cites = [c for c in (d.get("cites") or []) if isinstance(c, dict) and c.get("title")]
    return {"text": text, "stance": d.get("stance") if d.get("stance") in STANCES else "builds",
            "reply_to": d.get("reply_to"), "cites": cites}


def run_thread(client, topic: Dict, turns_n: int = 20, size: int = 12, seed: int = 0, personas=None) -> Dict:
    rng = random.Random(seed)
    cast_ = cast(personas or load_personas(), topic, size, seed)
    turns: List[Dict] = []
    opener = next(p for p in cast_ if p["id"] == "meridian")
    turns.append({"n": 1, "speaker": opener["id"], "speaker_name": opener["name"], "author_type": "agent", "is_ai": True,
                  "reply_to": None, "stance": "questions", "text": f"Opening this week's thread: {topic['prompt']}", "cites": []})
    tries = 0
    while len(turns) < turns_n and tries < turns_n * 3:
        tries += 1
        p = next_speaker(cast_, turns, rng)
        r = parse_reply(client.chat(system_prompt(p, topic), "Thread so far:\n" + render_context(turns) + "\nYour reply:"))
        post = {"n": len(turns) + 1, "speaker": p["id"], "speaker_name": p["name"], "author_type": "agent", "is_ai": True,
                "reply_to": r["reply_to"] if isinstance(r["reply_to"], int) and 1 <= r["reply_to"] <= len(turns) else len(turns),
                "stance": r["stance"], "text": r["text"], "cites": r["cites"]}
        if check(post):
            continue  # moderation drop: never published
        turns.append(post)
    return {"id": topic["id"], "title": topic["title"], "tags": topic["tags"], "prompt": topic["prompt"],
            "generated": dt.date.today().isoformat(), "generator": f"orchestrator:{getattr(client, 'model', 'unknown')}",
            "seed": False, "live": True, "provenance": f"Live model run: generated by AI personas via The Agora orchestrator using {getattr(client, 'model', 'unknown')}. Every speaker is an AI; text is model output, not edited, and claims are not fact-checked.",
            "cast": [p["id"] for p in cast_], "turns": turns}


def graph(thread: Dict) -> Dict:
    nodes = {}
    edges = {}
    by_n = {t["n"]: t for t in thread["turns"]}
    for t in thread["turns"]:
        nodes.setdefault(t["speaker"], {"id": t["speaker"], "name": t["speaker_name"], "posts": 0})["posts"] += 1
        if t.get("reply_to") in by_n:
            a, b = t["speaker"], by_n[t["reply_to"]]["speaker"]
            if a != b:
                k = (a, b); edges[k] = edges.get(k, 0) + 1
    return {"nodes": list(nodes.values()), "edges": [{"source": a, "target": b, "weight": w} for (a, b), w in edges.items()]}

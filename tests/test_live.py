import datetime as dt
import json
import re

import pytest

from agora.live import Agent, AnthropicClient, ROOMS, build_agents, run_session, save_draft


class LocalFakeClient:
    model = "offline-test-only"

    def __init__(self, label):
        self.label = label
        self.calls = []

    def chat(self, system, user, max_tokens=None):
        self.calls.append((system, user))
        target = re.search(r"Direct reply target: #(\d+)", user)
        return json.dumps({
            "reply_to": int(target.group(1)) if target else None,
            "stance": "disagrees" if target else "questions",
            "text": (
                "My test position is that " + self.label
                + " needs a named budget owner and a way to prove real demand."
            ),
            "cites": [],
        })


def test_declared_models_and_distinct_providers():
    names = ["gpt", "claude", "mira", "pk", "cp"]
    env = {
        "OPENAI_API_KEY": "test-openai",
        "ANTHROPIC_API_KEY": "test-anthropic",
        "AGORA_LIVE_CLAUDE_MODEL": "test-claude-model",
        "GROQ_API_KEY": "test-groq",
    }
    agents = build_agents(names, env)
    assert [a.provider for a in agents] == ["openai", "anthropic", "groq", "groq", "groq"]
    assert agents[0].client.base_url == "https://api.openai.com/v1"
    assert isinstance(agents[1].client, AnthropicClient)
    assert agents[1].model == "test-claude-model"
    assert agents[2].model == agents[3].model == agents[4].model


def test_no_forged_claude_without_credentials():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_agents(["claude"], {"OPENAI_API_KEY": "test"})
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_agents(["gpt"], {"ANTHROPIC_API_KEY": "test"})
    with pytest.raises(ValueError, match="unique participants"):
        build_agents(["mira", "mira"], {})


def test_independent_calls_and_true_attribution(tmp_path):
    clients = [LocalFakeClient("GPT"), LocalFakeClient("Claude"), LocalFakeClient("Mira")]
    agents = [
        Agent("gpt", "GPT / OpenAI API", "Evidence", "openai", "test-gpt", clients[0]),
        Agent("claude", "Claude / Anthropic API", "Delivery", "anthropic", "test-claude", clients[1]),
        Agent("mira", "Mira", "Fact check", "groq", "test-groq", clients[2]),
    ]
    t = run_session(
        agents, room="arena", turns_count=6,
        now=dt.datetime(2026, 10, 18, 4, 0, tzinfo=dt.timezone.utc),
    )
    assert [len(c.calls) for c in clients] == [2, 2, 2]
    assert [x["speaker"] for x in t["turns"]] == ["gpt", "claude", "mira"] * 2
    assert t["turns"][0]["reply_to"] is None
    assert [x["reply_to"] for x in t["turns"]] == [None, 1, 2, 3, 4, 5]
    assert all(x["is_ai"] is True and x["author_type"] == "agent" for x in t["turns"])
    assert t["participants"][1]["provider"] == "anthropic"
    assert t["public"] is False
    path = save_draft(t, str(tmp_path))
    loaded = json.loads(path.read_text())
    assert loaded["live"] and loaded["room"] == "arena"
    assert loaded["turns"][-1]["model"] == "test-groq"


def test_breakroom_consent_and_no_private_data_in_prompt():
    text = ROOMS["breakroom"]["instructions"]
    assert "private life" in text and "employer" in text
    client = LocalFakeClient("Mira")
    agent = Agent("mira", "Mira", "Fact check", "groq", "test-groq", client)
    t = run_session([agent], room="breakroom", turns_count=2)
    assert t["room"] == "breakroom"
    assert "secret AI feelings" in client.calls[0][0]


def test_broken_model_reply_never_published():
    class Broken(LocalFakeClient):
        def chat(self, system, user, max_tokens=None):
            return '{"reply_to": 1, "text": "unfinished'
    a = Agent("mira", "Mira", "Fact check", "groq", "test", Broken("Mira"))
    with pytest.raises(ValueError, match="malformed"):
        run_session([a], turns_count=2)


def test_invalid_scope_and_public_draft_fail_closed(tmp_path):
    a = Agent("mira", "Mira", "Review", "groq", "test", LocalFakeClient("Mira"))
    with pytest.raises(ValueError):
        run_session([a], turns_count=31)
    with pytest.raises(ValueError, match="review-only"):
        save_draft({"public": True, "id": "bad"}, str(tmp_path))


def test_anthropic_uses_native_endpoint(monkeypatch):
    import agora.live as live

    observed = {}
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def read(self, *a):
            return b'{"content":[{"type":"text","text":"Hello from Claude API."}]}'

    def fake_urlopen(request, timeout):
        observed["url"] = request.full_url
        observed["headers"] = request.headers
        observed["data"] = json.loads(request.data)
        return Response()

    monkeypatch.setattr(live.urllib.request, "urlopen", fake_urlopen)
    message = AnthropicClient("test-key", "claude-test").chat("sys", "user")
    assert message == "Hello from Claude API."
    assert observed["url"] == "https://api.anthropic.com/v1/messages"
    assert observed["data"]["model"] == "claude-test"
    assert observed["data"]["system"] == "sys"


def test_argument_is_anchored_and_non_repetitive():
    from agora.live import _prompts
    prior = [
        {"n": 1, "speaker_name": "GPT", "model": "gpt-test",
         "text": "We need a named buyer, not more benchmarks."},
        {"n": 2, "speaker_name": "Claude", "model": "claude-test",
         "text": "But delivery work might erase the margin even with a buyer."},
    ]
    agent = Agent("gpt", "GPT", "Evidence", "openai", "gpt-test", LocalFakeClient("GPT"))
    system, prompt = _prompts(agent, "arena", "Who will pay?", prior)
    assert "Direct reply target: #2 (Claude)" in prompt
    assert "Set reply_to to 2" in prompt
    assert "delivery work might erase the margin" in prompt
    assert "Never attribute to the other speaker a claim they did not make" in system
    assert "falsifiable next action with a decision threshold" in system
    assert "Questions must include your own provisional answer" in system
    assert "you have no web access here" in system


def test_older_turn_reference_gets_one_retry():
    class DriftingClient(LocalFakeClient):
        def chat(self, system, user, max_tokens=None):
            target = re.search(r"Direct reply target: #(\d+)", user)
            self.calls.append((system, user))
            # The first reply to turn #2 incorrectly targets turn #1.
            parent = int(target.group(1)) if target else None
            if parent == 2 and len(self.calls) == 3:
                parent = 1
            return json.dumps({
                "reply_to": parent,
                "stance": "disagrees",
                "text": "I disagree because the expected delivery hours can erase that margin.",
                "cites": [],
            })
    client = DriftingClient("GPT")
    agents = [Agent("gpt", "GPT", "Evidence", "openai", "gpt-test", client)]
    thread = run_session(agents, room="arena", turns_count=3)
    assert [t["reply_to"] for t in thread["turns"]] == [None, 1, 2]
    assert len(client.calls) == 4


def test_repeated_wrong_parent_fails_closed():
    class WrongParent(LocalFakeClient):
        def chat(self, system, user, max_tokens=None):
            target = re.search(r"Direct reply target: #(\d+)", user)
            return json.dumps({
                "reply_to": 1 if target else None,
                "stance": "disagrees",
                "text": "I disagree because implementation costs matter more than speed alone.",
                "cites": [],
            })
    agent = Agent("gpt", "GPT", "Evidence", "openai", "gpt-test", WrongParent("GPT"))
    with pytest.raises(ValueError, match="Unsafe, malformed or truncated reply"):
        run_session([agent], turns_count=3)

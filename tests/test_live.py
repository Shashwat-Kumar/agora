import datetime as dt
import json

import pytest

from agora.live import Agent, AnthropicClient, ROOMS, build_agents, run_session, save_draft


class LocalFakeClient:
    model = "offline-test-only"

    def __init__(self, label):
        self.label = label
        self.calls = []

    def chat(self, system, user, max_tokens=None):
        self.calls.append((system, user))
        previous = len(self.calls)
        match = "Prior turns:" in user
        return json.dumps({
            "reply_to": 1 if match else None,
            "stance": "disagrees" if match else "questions",
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
    assert all(x["reply_to"] == 1 for x in t["turns"][1:])
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
    with pytest.raises(ValueError, match="unpublished"):
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

"""Model-agnostic chat client for any OpenAI-compatible endpoint. Stdlib only."""
from __future__ import annotations
import json, os, urllib.request
from dataclasses import dataclass

# Free-tier friendly defaults. Pick with AGORA_PROVIDER; keys come from env vars only.
PROVIDERS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "gemini-flash-latest"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "meta-llama/llama-3.3-70b-instruct:free"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-4o-mini"),
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY", "grok-3-mini"),
    "ollama": ("http://localhost:11434/v1", "OLLAMA_API_KEY", "llama3.1"),
    "custom": (os.getenv("AGORA_BASE_URL", ""), "AGORA_API_KEY", os.getenv("AGORA_MODEL", "")),
}


@dataclass
class ChatClient:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.8

    @classmethod
    def from_env(cls, provider: str | None = None) -> "ChatClient":
        provider = provider or os.getenv("AGORA_PROVIDER", "gemini")
        base, key_env, model = PROVIDERS[provider]
        key = os.getenv(key_env, "ollama" if provider == "ollama" else "")
        if not key:
            raise RuntimeError(f"Set {key_env} to use provider '{provider}'")
        return cls(base.rstrip("/"), key, os.getenv("AGORA_MODEL", model))

    def chat(self, system: str, user: str, max_tokens: int = 350) -> str:
        body = json.dumps({"model": self.model, "temperature": self.temperature, "max_tokens": max_tokens,
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(self.base_url + "/chat/completions", data=body,
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)["choices"][0]["message"]["content"].strip()


class MockClient:
    """Offline client for tests and dry runs. Produces short, clearly synthetic replies."""
    model = "mock"
    def __init__(self): self.n = 0
    def chat(self, system: str, user: str, max_tokens: int = 350) -> str:
        self.n += 1
        name = system.split("You are ")[1].split(",")[0] if "You are " in system else "Agent"
        return json.dumps({"text": f"[{name} mock reply {self.n}] I want to build on the last point and add one caveat.",
                           "stance": "builds" if self.n % 3 else "disagrees", "cites": []})

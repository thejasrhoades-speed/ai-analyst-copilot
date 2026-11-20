"""LLM providers with throttling, retry/backoff on rate limits, and a disk cache.

Providers: gemini (google-genai SDK), groq and openrouter (OpenAI-compatible HTTP).
Keys come from environment variables / a .env file. Swap with PROVIDER=... in .env.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

CACHE_DIR = Path(".cache/llm")


class LLMError(Exception):
    pass


class Provider:
    name = "base"

    def __init__(self, model: str, min_interval: float = 6.0, max_retries: int = 5, use_cache: bool = True):
        self.model = model
        self.min_interval = min_interval  # seconds between calls (6s = 10 calls/minute)
        self.max_retries = max_retries
        self.use_cache = use_cache
        self._last_call = 0.0
        self.calls_made = 0
        self.cache_hits = 0

    # subclasses implement the raw call
    def _call(self, prompt: str) -> str:
        raise NotImplementedError

    def _key(self, prompt: str) -> Path:
        h = hashlib.sha256(f"{self.name}|{self.model}|{prompt}".encode()).hexdigest()
        return CACHE_DIR / f"{h}.json"

    def generate(self, prompt: str) -> str:
        if self.use_cache and self._key(prompt).exists():
            self.cache_hits += 1
            return json.loads(self._key(prompt).read_text())["text"]
        delay = 10.0
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            try:
                text = self._call(prompt)
                self.calls_made += 1
                if self.use_cache:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    self._key(prompt).write_text(json.dumps({"text": text}))
                return text
            except Exception as e:  # rate limit or transient error -> back off and retry
                msg = str(e).lower()
                retryable = any(s in msg for s in ("429", "rate", "quota", "resource_exhausted", "503", "overloaded", "timeout"))
                if not retryable or attempt == self.max_retries:
                    raise LLMError(str(e)) from e
                time.sleep(delay)
                delay = min(delay * 2, 120)
        raise LLMError("unreachable")


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, model=None, **kw):
        super().__init__(model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), **kw)
        from google import genai  # pip install google-genai

        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise LLMError("Set GEMINI_API_KEY in your .env file.")
        self._client = genai.Client(api_key=key)

    def _call(self, prompt: str) -> str:
        r = self._client.models.generate_content(model=self.model, contents=prompt)
        return r.text or ""


class OpenAICompatProvider(Provider):
    """Groq / OpenRouter / any OpenAI-compatible chat endpoint."""

    def __init__(self, name, base_url, key_env, model, **kw):
        super().__init__(model, **kw)
        self.name = name
        self.base_url = base_url
        self._key_env = key_env
        if not os.getenv(key_env):
            raise LLMError(f"Set {key_env} in your .env file.")

    def _call(self, prompt: str) -> str:
        import requests

        r = requests.post(
            self.base_url,
            headers={"Authorization": f"Bearer {os.environ[self._key_env]}"},
            json={"model": self.model, "temperature": 0,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        if r.status_code != 200:
            raise RuntimeError(f"{r.status_code} {r.text[:200]}")
        return r.json()["choices"][0]["message"]["content"]


class FunctionProvider(Provider):
    """Wraps a plain function (prompt -> text). Used for tests, no API needed."""
    name = "function"

    def __init__(self, fn, model="test"):
        super().__init__(model, min_interval=0, use_cache=False)
        self._fn = fn

    def _call(self, prompt: str) -> str:
        return self._fn(prompt)


def get_provider(name: str | None = None, model: str | None = None, **kw) -> Provider:
    name = (name or os.getenv("PROVIDER", "groq")).lower()
    if name == "gemini":
        return GeminiProvider(model, **kw)
    if name == "groq":
        return OpenAICompatProvider("groq", "https://api.groq.com/openai/v1/chat/completions",
                                    "GROQ_API_KEY", model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), **kw)
    if name == "openrouter":
        return OpenAICompatProvider("openrouter", "https://openrouter.ai/api/v1/chat/completions",
                                    "OPENROUTER_API_KEY", model or os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"), **kw)
    raise LLMError(f"Unknown provider: {name}")

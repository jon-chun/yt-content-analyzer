"""Live API connectivity probe — run manually after setting up .env.

Usage:
    python -m pytest tests/test_api_connectivity.py -v -s

Requires API keys in environment or .env file. Each test makes a single
minimal API call and validates the response structure. Skips providers
whose keys are not set.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

from yt_content_analyzer.enrich.llm_client import (
    PROVIDER_BASE_URLS,
)

# Try loading .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Provider configs: (provider, model, env_key)
# ---------------------------------------------------------------------------
CHAT_PROVIDERS = [
    ("openai", "gpt-4o-mini", "OPENAI_API_KEY"),
    ("anthropic", "claude-haiku-4-5-20251001", "ANTHROPIC_API_KEY"),
    ("xai", "grok-4-1-fast-non-reasoning", "XAI_API_KEY"),
    ("deepseek", "deepseek-chat", "DEEPSEEK_API_KEY"),
    ("fireworks", "accounts/fireworks/models/deepseek-v3p2", "FIREWORKS_API_KEY"),
    ("together", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "TOGETHER_API_KEY"),
]

EMBEDDING_PROVIDERS = [
    ("openai", "text-embedding-3-small", "OPENAI_API_KEY"),
]


def _has_key(env_key: str) -> bool:
    return bool(os.environ.get(env_key, "").strip())


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 30) -> dict:
    body = json.dumps(payload).encode("utf-8")
    headers.setdefault("User-Agent", "yt-content-analyzer/test")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ===========================================================================
# Chat completion probes
# ===========================================================================

@pytest.mark.parametrize("provider,model,env_key", CHAT_PROVIDERS, ids=[p[0] for p in CHAT_PROVIDERS])
def test_chat_completion_probe(provider, model, env_key):
    if not _has_key(env_key):
        pytest.skip(f"{env_key} not set")

    api_key = os.environ[env_key]
    base_url = PROVIDER_BASE_URLS.get(provider, "")
    assert base_url, f"No known base URL for {provider}"

    # Anthropic uses a different API format
    if provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": model,
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "Say 'hello' and nothing else."}],
        }
        data = _post_json(url, payload, headers)
        assert "content" in data, f"Unexpected response: {data}"
        text = data["content"][0]["text"]
    else:
        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "max_tokens": 32,
            "temperature": 0,
            "messages": [{"role": "user", "content": "Say 'hello' and nothing else."}],
        }
        data = _post_json(url, payload, headers)
        assert "choices" in data, f"Unexpected response: {data}"
        text = data["choices"][0]["message"]["content"]

    assert len(text) > 0, "Empty response from model"
    print(f"\n  {provider}/{model}: '{text.strip()[:80]}'")


# ===========================================================================
# Embedding probes
# ===========================================================================

@pytest.mark.parametrize("provider,model,env_key", EMBEDDING_PROVIDERS, ids=[p[0] for p in EMBEDDING_PROVIDERS])
def test_embedding_probe(provider, model, env_key):
    if not _has_key(env_key):
        pytest.skip(f"{env_key} not set")

    api_key = os.environ[env_key]
    base_url = PROVIDER_BASE_URLS.get(provider, "")
    url = f"{base_url}/embeddings"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "input": ["test connectivity"],
    }

    data = _post_json(url, payload, headers)
    assert "data" in data, f"Unexpected response: {data}"
    assert len(data["data"]) == 1
    embedding = data["data"][0]["embedding"]
    assert isinstance(embedding, list)
    assert len(embedding) > 0
    print(f"\n  {provider}/{model}: {len(embedding)}-dim embedding")

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from typing import Any

from ..config import Settings, resolve_api_key

logger = logging.getLogger(__name__)

# Known base URLs per provider (OpenAI-compatible endpoints)
PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "xai": "https://api.x.ai/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
}


def _resolve_base_url(provider: str, endpoint: str | None) -> str:
    """Resolve the base URL for a provider."""
    if provider in ("local", "ollama") and endpoint:
        return endpoint.rstrip("/")
    if endpoint:
        return endpoint.rstrip("/")
    return PROVIDER_BASE_URLS.get(provider, "http://localhost:11434/v1")


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict[str, Any]:
    """POST JSON and return parsed response dict."""
    body = json.dumps(payload).encode("utf-8")
    headers.setdefault("User-Agent", "yt-content-analyzer")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return result


def chat_completion(
    cfg: Settings,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> str:
    """Send a chat completion request to an OpenAI-compatible API.

    Returns the assistant message content string.
    """
    provider = cfg.LLM_PROVIDER or "local"
    base_url = _resolve_base_url(provider, cfg.LLM_ENDPOINT)
    url = f"{base_url}/chat/completions"

    api_key = resolve_api_key(provider)
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if cfg.LLM_MODEL:
        payload["model"] = cfg.LLM_MODEL

    max_retries = cfg.API_MAX_RETRIES
    backoff = cfg.BACKOFF_BASE_SECONDS
    timeout = cfg.API_TIMEOUT_S

    for attempt in range(max_retries + 1):
        try:
            data = _post_json(url, payload, headers, timeout)
            content: str = data["choices"][0]["message"]["content"]
            return content
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                wait = min(backoff * (2 ** attempt), cfg.BACKOFF_MAX_SECONDS)
                logger.warning(
                    "LLM request %d/%d got HTTP %d, retrying in %.1fs",
                    attempt + 1, max_retries + 1, e.code, wait,
                )
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < max_retries:
                wait = min(backoff * (2 ** attempt), cfg.BACKOFF_MAX_SECONDS)
                logger.warning(
                    "LLM request %d/%d failed (%s), retrying in %.1fs",
                    attempt + 1, max_retries + 1, e, wait,
                )
                time.sleep(wait)
                continue
            raise

    raise RuntimeError("Exhausted retries for chat_completion")


def get_embeddings(cfg: Settings, texts: list[str]) -> list[list[float]]:
    """Get embeddings from an OpenAI-compatible /v1/embeddings endpoint.

    Returns a list of embedding vectors (one per input text).
    """
    provider = cfg.EMBEDDINGS_PROVIDER or "local"
    base_url = _resolve_base_url(provider, cfg.EMBEDDINGS_ENDPOINT)
    url = f"{base_url}/embeddings"

    api_key = resolve_api_key(provider)
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict[str, Any] = {"input": texts}
    if cfg.EMBEDDINGS_MODEL:
        payload["model"] = cfg.EMBEDDINGS_MODEL

    timeout = cfg.EMBEDDINGS_TIMEOUT_S

    data = _post_json(url, payload, headers, timeout)
    # Sort by index to ensure order matches input
    sorted_data = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in sorted_data]


def parse_json_response(text: str) -> Any:
    """Parse a JSON response from an LLM, handling common quirks.

    Strips markdown code fences, extracts first JSON object or array.
    """
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*\n?", "", text)
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract first JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Extract first JSON array
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}")

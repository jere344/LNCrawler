"""LLM adjudication for gray-band merge candidates (optional, pluggable).

Any OpenAI-compatible chat-completions endpoint works (Gemini, Groq, Mistral,
OpenAI, Ollama). Swap providers by changing ``MERGE_LLM_PROVIDER`` or pointing
``MERGE_LLM_BASE_URL`` at a custom endpoint. With no API key configured the
service reports ``is_configured() == False`` and everything degrades to the
deterministic review queue.

Calls are made from the ``judge_merge_candidates`` command, which runs as a
bounded scheduler task so a slow or rate-limited provider can never block the
rest of the maintenance loop.
"""

import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger("lncrawler_api.merge")

PROVIDER_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "ollama": "http://localhost:11434/v1/chat/completions",
}

# Providers that run locally and need no API key.
KEYLESS_PROVIDERS = {"ollama"}

SYSTEM_PROMPT = (
    "You decide whether two light-novel catalogue entries from different "
    "sources describe the SAME underlying work. Titles may be translated or "
    "carry series/volume suffixes; different sources may use different "
    "languages. Judge the work identity, not the surface spelling. Respond with "
    'a single JSON object: {"same": true|false, "confidence": 0..1, '
    '"reason": "short explanation"}.'
)


class LLMError(Exception):
    pass


class RateLimited(LLMError):
    def __init__(self, retry_after=None):
        super().__init__("rate limited")
        self.retry_after = retry_after


def provider_url(provider=None):
    override = getattr(settings, "MERGE_LLM_BASE_URL", "")
    if override:
        return override
    provider = provider or getattr(settings, "MERGE_LLM_PROVIDER", "gemini")
    return PROVIDER_URLS.get(provider)


def is_configured():
    provider = getattr(settings, "MERGE_LLM_PROVIDER", "gemini")
    if not provider_url(provider):
        return False
    if provider in KEYLESS_PROVIDERS:
        return True
    return bool(getattr(settings, "MERGE_LLM_API_KEY", ""))


def _render_profile(profile):
    title = profile.get("title", "")
    lines = [f"Title: {title}"]
    others = [t for t in profile.get("titles", []) if t and t != title]
    if others:
        lines.append("Other titles: " + "; ".join(others))
    if profile.get("alternative_titles"):
        lines.append("Alternative titles: " + "; ".join(profile["alternative_titles"]))
    if profile.get("authors"):
        lines.append("Author(s): " + "; ".join(profile["authors"]))
    if profile.get("languages"):
        lines.append("Language(s): " + ", ".join(profile["languages"]))
    if profile.get("synopsis"):
        lines.append("Synopsis: " + profile["synopsis"])
    return "\n".join(lines)


def build_messages(profile_a, profile_b):
    user = (
        "Entry A:\n"
        + _render_profile(profile_a)
        + "\n\nEntry B:\n"
        + _render_profile(profile_b)
        + "\n\nAre these the same novel?"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _as_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return bool(value)


def _parse_content(content):
    text = (content or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise LLMError(f"unparseable LLM content: {content[:300]!r}") from exc
    if not isinstance(data, dict):
        raise LLMError(f"unexpected LLM content shape: {content[:300]!r}")
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "same": _as_bool(data.get("same")),
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": str(data.get("reason", ""))[:1000],
    }


def judge(profile_a, profile_b, provider=None, model=None, timeout=None, session=None):
    """Return ``{"same", "confidence", "reason"}`` for one candidate pair."""
    provider = provider or getattr(settings, "MERGE_LLM_PROVIDER", "gemini")
    url = provider_url(provider)
    if not url:
        raise LLMError(f"unknown LLM provider: {provider}")
    model = model or getattr(settings, "MERGE_LLM_MODEL", "openai/gpt-oss-20b")
    timeout = timeout or getattr(settings, "MERGE_LLM_TIMEOUT", 30)

    headers = {"Content-Type": "application/json"}
    key = getattr(settings, "MERGE_LLM_API_KEY", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 300,
        "messages": build_messages(profile_a, profile_b),
    }

    poster = (session or requests).post
    resp = poster(url, headers=headers, json=body, timeout=timeout)
    if resp.status_code == 429:
        raise RateLimited(retry_after=resp.headers.get("Retry-After"))
    if resp.status_code >= 400:
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise LLMError(f"non-JSON response (HTTP {resp.status_code}): {resp.text[:300]}") from exc
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"unexpected response shape: {payload}") from exc
    return _parse_content(content)

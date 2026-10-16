"""Text embeddings for tag names (optional, pluggable).

Any OpenAI-compatible ``/embeddings`` endpoint works (Mistral, Jina, OpenAI).
Swap providers with ``TAG_EMBED_PROVIDER`` or point ``TAG_EMBED_BASE_URL`` at a
custom endpoint. With no API key the service reports ``is_configured() == False``
and tag clustering falls back to the trigram and co-occurrence signals.

Errors reuse the ``llm_service`` exception types so callers handle rate limits
the same way for both services.
"""

import numpy as np
import requests
from django.conf import settings

from . import llm_service

PROVIDER_URLS = {
    "mistral": "https://api.mistral.ai/v1/embeddings",
    "jina": "https://api.jina.ai/v1/embeddings",
    "openai": "https://api.openai.com/v1/embeddings",
    "voyage": "https://api.voyageai.com/v1/embeddings",
}


def provider_url():
    override = getattr(settings, "TAG_EMBED_BASE_URL", "")
    if override:
        return override
    return PROVIDER_URLS.get(getattr(settings, "TAG_EMBED_PROVIDER", "mistral"))


def is_configured():
    return bool(provider_url()) and bool(getattr(settings, "TAG_EMBED_API_KEY", ""))


def embed(texts, session=None):
    """Return a ``(len(texts), dim)`` float32 array, one row per input text."""
    texts = list(texts)
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    url = provider_url()
    if not url:
        raise llm_service.LLMError(
            f"unknown embedding provider: {getattr(settings, 'TAG_EMBED_PROVIDER', '')}"
        )

    headers = {"Content-Type": "application/json"}
    key = getattr(settings, "TAG_EMBED_API_KEY", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = {"model": settings.TAG_EMBED_MODEL, "input": texts}
    if getattr(settings, "TAG_EMBED_PROVIDER", "") == "jina":
        # Jina v5 (jina-embeddings-v5-omni-small, checked against the live API) takes a
        # task type; text-matching suits name-to-name similarity.
        body["task"] = "text-matching"

    poster = (session or requests).post
    resp = poster(
        url, headers=headers, json=body, timeout=getattr(settings, "TAG_EMBED_TIMEOUT", 30)
    )
    if resp.status_code == 429:
        raise llm_service.RateLimited(retry_after=resp.headers.get("Retry-After"))
    if resp.status_code >= 400:
        raise llm_service.LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        payload = resp.json()
        items = sorted(payload["data"], key=lambda item: item["index"])
        vectors = [item["embedding"] for item in items]
    except (ValueError, KeyError, TypeError) as exc:
        raise llm_service.LLMError(f"unexpected embedding response: {resp.text[:300]}") from exc
    if len(vectors) != len(texts):
        raise llm_service.LLMError(
            f"embedding count mismatch: sent {len(texts)}, got {len(vectors)}"
        )
    return np.asarray(vectors, dtype=np.float32)

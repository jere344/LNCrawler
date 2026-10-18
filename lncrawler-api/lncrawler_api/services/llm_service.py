"""LLM adjudication for gray-band merge candidates (optional, pluggable).

Any OpenAI-compatible chat-completions endpoint works (Gemini, Groq, Mistral,
OpenAI, Ollama). Swap providers by changing ``LLM_PROVIDER`` or pointing
``LLM_BASE_URL`` at a custom endpoint. With no API key configured the
service reports ``is_configured() == False`` and everything degrades to the
deterministic review queue.

Calls are made from the ``judge_merge_candidates`` command, which runs as a
bounded scheduler task so a slow or rate-limited provider can never block the
rest of the maintenance loop.
"""

import json
import logging
import re

import requests
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from ..models import LLMUsage

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
    '"reason": "short explanation"}. Keep "reason" under 25 words.'
)


class LLMError(Exception):
    pass


class LLMParseError(LLMError):
    """The model answered, but the answer is not the JSON object we asked for."""


class LLMTruncated(LLMParseError):
    """The reply was cut off (finish_reason "length") or came back empty.

    Reasoning models spend hidden tokens against max_tokens, so this usually
    means the reply budget ran out before the answer was written.
    """


class RateLimited(LLMError):
    def __init__(self, retry_after=None):
        super().__init__("rate limited")
        self.retry_after = retry_after


def provider_url(provider=None):
    override = getattr(settings, "LLM_BASE_URL", "")
    if override:
        return override
    provider = provider or getattr(settings, "LLM_PROVIDER", "gemini")
    return PROVIDER_URLS.get(provider)


def is_configured():
    provider = getattr(settings, "LLM_PROVIDER", "gemini")
    if not provider_url(provider):
        return False
    if provider in KEYLESS_PROVIDERS:
        return True
    return bool(getattr(settings, "LLM_API_KEY", ""))


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


def _normalize(data):
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "same": _as_bool(data.get("same")),
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": str(data.get("reason", ""))[:1000],
    }


# Salvage the verdict from truncated/malformed JSON (a long "reason" can hit the
# token cap before the closing brace, which would otherwise discard a valid
# "same"/"confidence").
_BOOL_RE = re.compile(r'"same"\s*:\s*(true|false)', re.IGNORECASE)
_CONF_RE = re.compile(r'"confidence"\s*:\s*([0-9]*\.?[0-9]+)')
_REASON_RE = re.compile(r'"reason"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)


def _parse_content(content):
    text = (content or "").strip()
    start, end = text.find("{"), text.rfind("}")
    snippet = text[start : end + 1] if start >= 0 and end > start else text
    try:
        data = json.loads(snippet)
    except ValueError:
        data = None
    if isinstance(data, dict):
        return _normalize(data)

    same = _BOOL_RE.search(text)
    conf = _CONF_RE.search(text)
    if same is None and conf is None:
        raise LLMError(f"unparseable LLM content: {content[:300]!r}")
    reason = _REASON_RE.search(text)
    return _normalize(
        {
            "same": same.group(1) if same else False,
            "confidence": conf.group(1) if conf else 0.0,
            "reason": reason.group(1) if reason else "",
        }
    )


def _total_tokens(payload):
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return 0
    try:
        return int(usage.get("total_tokens") or 0)
    except (TypeError, ValueError):
        return 0


def _post_chat(messages, max_tokens, purpose, provider=None, model=None, timeout=None, session=None):
    """POST one chat-completions request. Returns ``(content, total_tokens)``.

    Every response the provider returned (HTTP 200, truncated ones included)
    is written to ``LLMUsage`` under ``purpose``. A 429 or other HTTP error is
    not charged and writes nothing. A reply cut off by the token cap, or
    empty, raises ``LLMTruncated``.
    """
    provider = provider or getattr(settings, "LLM_PROVIDER", "gemini")
    url = provider_url(provider)
    if not url:
        raise LLMError(f"unknown LLM provider: {provider}")
    model = model or getattr(settings, "LLM_MODEL", "openai/gpt-oss-20b")
    timeout = timeout or getattr(settings, "LLM_TIMEOUT", 30)

    headers = {"Content-Type": "application/json"}
    key = getattr(settings, "LLM_API_KEY", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    reasoning_effort = getattr(settings, "LLM_REASONING_EFFORT", "low")
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort

    poster = (session or requests).post
    resp = poster(url, headers=headers, json=body, timeout=timeout)
    if resp.status_code == 429:
        raise RateLimited(retry_after=resp.headers.get("Retry-After"))
    if resp.status_code >= 400:
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        payload = resp.json()
    except ValueError as exc:
        LLMUsage.objects.create(purpose=purpose, tokens=0)
        raise LLMError(f"non-JSON response (HTTP {resp.status_code}): {resp.text[:300]}") from exc

    total_tokens = _total_tokens(payload)
    LLMUsage.objects.create(purpose=purpose, tokens=total_tokens)
    try:
        choice = payload["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"unexpected response shape: {payload}") from exc
    finish_reason = choice.get("finish_reason")
    if finish_reason == "length" or not isinstance(content, str) or not content.strip():
        completion = (payload.get("usage") or {}).get("completion_tokens")
        raise LLMTruncated(
            f"LLM reply truncated or empty (finish_reason={finish_reason!r}, "
            f"completion_tokens={completion}, total_tokens={total_tokens})"
        )
    return content, total_tokens


def tokens_used_today():
    """Tokens charged today across both judges (novel and tag)."""
    today = timezone.localdate()
    used = LLMUsage.objects.filter(created_at__date=today).aggregate(total=Sum("tokens"))
    return used["total"] or 0


def token_budget_left():
    """Tokens left in today's shared budget. Negative once it is overspent."""
    return settings.LLM_DAILY_TOKENS - tokens_used_today()


# Every workflow calls the same API, so they all draw on the one daily budget
# (LLM_DAILY_TOKENS). A request is only started when the budget can cover
# its worst case: the reply cap (reasoning counts toward it) plus a reserve for
# the prompt, which depends on how much each workflow packs into one call.
PROMPT_TOKEN_RESERVE = {
    LLMUsage.PURPOSE_NOVEL: 1500,  # two novel profiles
    LLMUsage.PURPOSE_TAG: 3000,    # ~30 tags in clusters, with usage counts
    LLMUsage.PURPOSE_R18: 1500,    # ~50 short tag names
}
REPLY_CAP_SETTING = {
    LLMUsage.PURPOSE_NOVEL: "MERGE_LLM_MAX_TOKENS",
    LLMUsage.PURPOSE_TAG: "TAG_LLM_MAX_TOKENS",
    LLMUsage.PURPOSE_R18: "TAG_R18_LLM_MAX_TOKENS",
}


def estimated_tokens(purpose):
    """Worst-case tokens one request of ``purpose`` can cost."""
    return getattr(settings, REPLY_CAP_SETTING[purpose]) + PROMPT_TOKEN_RESERVE[purpose]


def requests_used_today():
    """Provider replies received today across every workflow (one LLMUsage row each)."""
    return LLMUsage.objects.filter(created_at__date=timezone.localdate()).count()


def can_afford(purpose):
    """Whether today's shared budgets still cover one request of ``purpose``.

    Providers cap both requests and tokens per day; a request only starts when
    it fits under both (LLM_DAILY_REQUESTS and LLM_DAILY_TOKENS).
    """
    return (
        requests_used_today() < settings.LLM_DAILY_REQUESTS
        and token_budget_left() >= estimated_tokens(purpose)
    )


def budget_status():
    """Today's usage of both shared budgets, for log lines."""
    return (
        f"{requests_used_today()}/{settings.LLM_DAILY_REQUESTS} requests, "
        f"{tokens_used_today()}/{settings.LLM_DAILY_TOKENS} tokens"
    )


def judge(profile_a, profile_b, provider=None, model=None, timeout=None, session=None):
    """Return ``{"same", "confidence", "reason"}`` for one candidate pair."""
    content, _tokens = _post_chat(
        build_messages(profile_a, profile_b),
        getattr(settings, "MERGE_LLM_MAX_TOKENS", 2048),
        LLMUsage.PURPOSE_NOVEL,
        provider,
        model,
        timeout,
        session,
    )
    return _parse_content(content)


def chat_json(messages, max_tokens=4096, provider=None, model=None, timeout=None, session=None,
              purpose=LLMUsage.PURPOSE_TAG):
    """Return the JSON object the model wrote, for callers that need a richer shape.

    Takes the text between the first "{" and the last "}" so code fences or a
    short preamble do not matter. Raises ``LLMParseError`` if no object parses.
    """
    content, _tokens = _post_chat(
        messages, max_tokens, purpose, provider, model, timeout, session
    )
    text = (content or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise LLMParseError(f"no JSON object in LLM content: {text[:300]!r}")
    try:
        data = json.loads(text[start : end + 1])
    except ValueError as exc:
        raise LLMParseError(f"invalid JSON in LLM content: {text[:300]!r}") from exc
    if not isinstance(data, dict):
        raise LLMParseError("LLM content is not a JSON object")
    return data

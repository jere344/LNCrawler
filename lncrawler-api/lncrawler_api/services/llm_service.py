"""LLM adjudication for gray-band merge candidates (optional, pluggable).

Any OpenAI-compatible chat-completions endpoint works (Cloudflare, Cerebras, Gemini, Groq, Mistral,
OpenAI, Ollama). Providers form an ordered fallback chain (``LLM_PROVIDERS``, see
``providers()``): a call goes to the first provider that is configured, not cooling
down and under its limits. A 429 or an outage puts that provider on cooldown
(``LLMProviderCooldown``) and the same call is sent to the next one. With no chain
configured (``LLM_PROVIDERS`` empty, or no API key on any provider) the service
reports ``is_configured() == False`` and everything degrades to the deterministic
review queue. A task's JSON schema is sent as ``response_format``
(structured output) unless the provider sets ``json_schema`` to false.

Calls are made from the LLM workflows in services/llm_tasks.py (run through the
``Candidate`` queue). They run as bounded
scheduler tasks so a slow or rate-limited provider can never block the rest of
the maintenance loop.
"""

import json
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import timedelta

import requests
from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone

from ..models import LLMCall, LLMProviderCooldown

logger = logging.getLogger("lncrawler_api.merge")

PROVIDER_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "ollama": "http://localhost:11434/v1/chat/completions",
    "cerebras": "https://api.cerebras.ai/v1/chat/completions",
}

# Providers that run locally and need no API key.
KEYLESS_PROVIDERS = {"ollama"}

# A provider that is down or refuses the key (401/402/403/5xx/network) is skipped this long.
UNAVAILABLE_COOLDOWN = 300
# Provider of the LLMCall rows migration 0097 copied from the old request log (history only).
REQUEST_LOG_PROVIDER = "(request log)"

# No authors in the profiles: one author writes many novels, and a shared author name
# made the judge call different works the same at full confidence. Candidate search
# already uses authors; the judge decides from titles and synopses only.
SYSTEM_PROMPT = (
    "You decide whether two catalogue entries from different web/light-novel sites are the SAME "
    "work (the same story, possibly translated, retitled or another edition) or DIFFERENT works.\n"
    "Evidence, strongest first:\n"
    "- Synopsis: the same premise, main characters, names and events mean the same work; a "
    "different protagonist, premise or setting means different works.\n"
    "- Titles: the same title, its translation or romanization, or the same title plus a subtitle "
    "or volume suffix.\n"
    "Similar or generic titles prove nothing on their own: many different novels share words "
    "('Reincarnated as', 'The Strongest', 'Villainess'). A sequel, prequel, side story or "
    "spin-off is a DIFFERENT work. A shared premise is not enough either: many novels copy the "
    "same tropes (a modern genius transmigrates, a broken engagement, a system, revenge), so "
    "similar premises with no shared names or specific events are different works.\n"
    "Judge only from the text of the two entries. Do not use what you remember about novels, "
    "their alternative titles or their characters: such memories are often wrong.\n"
    "Confidence is how sure you are of your answer, same or different:\n"
    "- 0.95 to 1.0 for same only when both entries show a specific match: the same character "
    "name, the same distinctive title or its translation, or the same specific events, written "
    "in BOTH entries. A detail found in only one entry is not a match: never carry a name or "
    "event from one entry over to the other. For different, 0.95 to 1.0 only when the synopses "
    "clearly tell different stories;\n"
    "- 0.6 to 0.9 when the evidence is partial, for example a synopsis is missing or vague and you "
    "rely on the titles;\n"
    "- below 0.6 when you are mostly guessing.\n"
    "When either synopsis is missing, never go above 0.85.\n"
    'Respond with a single JSON object: {"same": true|false, "confidence": 0..1, '
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


class ProviderUnavailable(LLMError):
    """The provider is down or refuses the key; the chain skips it for a while."""


@dataclass(frozen=True)
class Provider:
    """One entry of the fallback chain. A cap of None means no cap."""

    name: str
    url: str
    api_key: str
    model: str
    reasoning_effort: str
    daily_requests: int | None
    daily_tokens: int | None
    requests_per_minute: int | None
    tokens_per_minute: int | None
    cooldown: int
    # Provider-specific fields merged into every request body (e.g. turning thinking off).
    extra_body: dict = field(default_factory=dict)
    # False for a provider that rejects response_format.
    json_schema: bool = True

    @property
    def configured(self):
        return bool(self.url and self.model) and (self.name in KEYLESS_PROVIDERS or bool(self.api_key))


def providers():
    """The fallback chain, in the order it is tried. Empty when no LLM_PROVIDERS are set."""
    chain = []
    for name in settings.LLM_PROVIDERS:
        entry = settings.LLM_PROVIDER_SETTINGS[name]
        chain.append(Provider(
            name=name,
            url=entry["base_url"] or PROVIDER_URLS.get(name),
            api_key=entry["api_key"],
            model=entry["model"],
            reasoning_effort=entry["reasoning_effort"],
            daily_requests=entry["daily_requests"],
            daily_tokens=entry["daily_tokens"],
            requests_per_minute=entry["requests_per_minute"],
            tokens_per_minute=entry["tokens_per_minute"],
            cooldown=entry["cooldown"],
            extra_body=entry.get("extra_body") or {},
            json_schema=entry.get("json_schema", True),
        ))
    return chain


def is_configured():
    return any(provider.configured for provider in providers())


def _render_profile(profile):
    title = profile.get("title", "")
    lines = [f"Title: {title}"]
    others = [t for t in profile.get("titles", []) if t and t != title]
    if others:
        lines.append("Other titles: " + "; ".join(others))
    if profile.get("alternative_titles"):
        lines.append("Alternative titles: " + "; ".join(profile["alternative_titles"]))
    if profile.get("languages"):
        lines.append("Language(s): " + ", ".join(profile["languages"]))
    lines.append("Synopsis: " + (profile.get("synopsis") or "(none)"))
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


def parse_confidence(value, default=0.0, strict=False):
    """Clamp a model's confidence to 0..1, or return ``default`` when it is unusable.

    Lenient (the default) takes whatever ``float()`` accepts, strings and bools
    included. ``strict`` takes only an int or float and rejects bools. Both modes
    reject NaN and infinity: ``json.loads`` accepts NaN, which jsonb does not
    store, and ``min(1.0, nan)`` would turn it into 1.0.
    """
    if strict and (not isinstance(value, (int, float)) or isinstance(value, bool)):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return max(0.0, min(1.0, number))


def _normalize(data):
    return {
        "same": _as_bool(data.get("same")),
        "confidence": parse_confidence(data.get("confidence")),
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


def _log_call(purpose, provider, model, prompt_version, candidate_ids, tokens, raw_response, error=""):
    """Write the LLMCall of one provider reply: the call history and the budget read it."""
    return LLMCall.objects.create(
        kind=purpose,
        provider=provider.name,
        model=model,
        prompt_version=prompt_version,
        tokens=tokens,
        raw_response=raw_response,
        error=error,
        candidate_ids=list(candidate_ids or []),
    )


def _post_chat(messages, max_tokens, purpose, provider, session=None, response_schema=None,
               candidate_ids=None, prompt_version=""):
    """POST one chat-completions request to ``provider``. Returns ``(content, total_tokens, call)``.

    ``response_schema`` is sent as structured output when the provider takes it. Every
    response the provider returned (HTTP 200, truncated ones included) is written as an
    ``LLMCall`` under ``purpose`` (the task name), with the provider that answered and
    ``candidate_ids``. A 429 or other HTTP error is not charged and writes nothing. A
    reply cut off by the token cap, or empty, raises ``LLMTruncated``. A 429 raises
    ``RateLimited``; a 401/402/403, 5xx or network error raises ``ProviderUnavailable``.
    """
    if not provider.url:
        raise LLMError(f"unknown LLM provider: {provider.name}")

    headers = {"Content-Type": "application/json"}
    key = provider.api_key
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = {
        "model": provider.model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if response_schema is not None and provider.json_schema:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": purpose, "strict": True, "schema": response_schema},
        }
    reasoning_effort = provider.reasoning_effort
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    body.update(provider.extra_body)

    poster = (session or requests).post
    try:
        resp = poster(provider.url, headers=headers, json=body, timeout=settings.LLM_TIMEOUT)
    except requests.RequestException as exc:
        raise ProviderUnavailable(f"{type(exc).__name__}: {exc}") from exc
    if resp.status_code == 429:
        raise RateLimited(retry_after=resp.headers.get("Retry-After"))
    if resp.status_code in (401, 402, 403) or resp.status_code >= 500:
        raise ProviderUnavailable(f"HTTP {resp.status_code}: {resp.text[:300]}")
    if resp.status_code >= 400:
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        payload = resp.json()
    except ValueError as exc:
        error = f"non-JSON response (HTTP {resp.status_code}): {resp.text[:300]}"
        _log_call(purpose, provider, provider.model, prompt_version, candidate_ids, 0, resp.text, error)
        raise LLMError(error) from exc

    total_tokens = _total_tokens(payload)
    try:
        choice = payload["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        error = f"unexpected response shape: {payload}"
        _log_call(purpose, provider, provider.model, prompt_version, candidate_ids, total_tokens, resp.text, error)
        raise LLMError(error) from exc
    finish_reason = choice.get("finish_reason")
    if finish_reason == "length" or not isinstance(content, str) or not content.strip():
        completion = (payload.get("usage") or {}).get("completion_tokens")
        error = (
            f"LLM reply truncated or empty (finish_reason={finish_reason!r}, "
            f"completion_tokens={completion}, total_tokens={total_tokens})"
        )
        _log_call(purpose, provider, provider.model, prompt_version, candidate_ids, total_tokens, resp.text, error)
        raise LLMTruncated(error)
    call = _log_call(purpose, provider, provider.model, prompt_version, candidate_ids, total_tokens, resp.text)
    return content, total_tokens, call


def _usage(provider=None):
    """LLMCall rows charged to ``provider``, or every row when None (the admin's global view).

    Rows of the old request log copied by migration 0097 (``REQUEST_LOG_PROVIDER``)
    are not counted: the copied usage rows of the same replies already are.
    """
    if provider is None:
        return LLMCall.objects.exclude(provider=REQUEST_LOG_PROVIDER)
    return LLMCall.objects.filter(provider=provider.name)


def tokens_used_today(provider=None):
    """Tokens charged today across every workflow, or by ``provider`` alone."""
    today = timezone.localdate()
    used = _usage(provider).filter(created_at__date=today).aggregate(total=Sum("tokens"))
    return used["total"] or 0


def token_budget_left(provider):
    """Tokens left in today's budget of ``provider``. Negative once it is overspent.

    Its daily_tokens cap, which must not be None.
    """
    return provider.daily_tokens - tokens_used_today(provider)


# Worst-case tokens of one call (prompt + reply), charged by the budget checks. The
# largest call is a ~100-tag tag merge batch (measured ~2.4K tokens).
CALL_TOKENS = 2500


def requests_used_today(provider=None):
    """Provider replies received today across every workflow (one LLMCall row each)."""
    return _usage(provider).filter(created_at__date=timezone.localdate()).count()


def minute_usage(provider=None):
    """``(requests, tokens)`` charged in the last 60 seconds, for the per-minute caps."""
    since = timezone.now() - timedelta(seconds=60)
    used = _usage(provider).filter(created_at__gte=since).aggregate(
        requests=Count("pk"), tokens=Sum("tokens"),
    )
    return used["requests"], used["tokens"] or 0


def _affordable(provider):
    """Whether the limits of ``provider`` still cover one more call. A None cap is no cap.

    Providers cap requests and tokens per day and per minute. A call only starts when
    it fits under every cap that is set, charged at CALL_TOKENS.
    """
    minute_requests, minute_tokens = minute_usage(provider)
    if provider.daily_requests is not None and requests_used_today(provider) >= provider.daily_requests:
        return False
    if provider.daily_tokens is not None and token_budget_left(provider) < CALL_TOKENS:
        return False
    if provider.requests_per_minute is not None and minute_requests >= provider.requests_per_minute:
        return False
    if provider.tokens_per_minute is not None and minute_tokens + CALL_TOKENS > provider.tokens_per_minute:
        return False
    return True


def cooldown_until(provider):
    """When ``provider`` stops cooling down, or None when it is ready."""
    cooling = LLMProviderCooldown.objects.filter(name=provider.name, until__gt=timezone.now()).first()
    return cooling.until if cooling else None


def start_cooldown(provider, seconds, reason):
    """Skip ``provider`` in the chain for ``seconds``."""
    LLMProviderCooldown.objects.update_or_create(
        name=provider.name,
        defaults={"until": timezone.now() + timedelta(seconds=seconds), "reason": reason[:1000]},
    )
    logger.warning("LLM provider %s cooling down for %ss: %s", provider.name, seconds, reason)


def _cooldown_seconds(retry_after, default):
    """Seconds a 429 asks to wait: its Retry-After, or ``default`` when it has none."""
    try:
        return max(int(retry_after), 1)
    except (TypeError, ValueError):
        return default


def can_afford(provider=None):
    """Whether one more call fits the limits of ``provider``.

    Without a provider: whether any configured provider is not cooling down and is
    under its limits. This is what the queue runner checks before each call.
    """
    if provider is not None:
        return _affordable(provider)
    return any(
        p.configured and cooldown_until(p) is None and _affordable(p)
        for p in providers()
    )


def chat(messages, max_tokens, purpose, session=None, response_schema=None, candidate_ids=None,
         prompt_version=""):
    """Send one call to the first provider of the chain that takes it.

    Returns ``(content, total_tokens, provider, call)``, ``call`` being the LLMCall of
    the reply used. ``candidate_ids`` and ``prompt_version`` are logged on every
    LLMCall of the request. A 429 cools the provider down for
    its Retry-After (or its cooldown when there is none), an outage for
    UNAVAILABLE_COOLDOWN, and the next provider is tried. Parse and truncation errors
    are the request's fault, not the provider's, so they propagate. Another HTTP error
    (a 400 for a bad model or an unsupported field) tries the next provider without a
    cooldown, and the last one is raised if no provider answers. Otherwise, when no
    provider answers, raises ``RateLimited`` with the wait until the earliest cooldown
    ends and the reasons in its message.
    """
    error = None
    reasons = []
    for provider in providers():
        if not provider.configured or cooldown_until(provider) or not _affordable(provider):
            continue
        try:
            content, tokens, call = _post_chat(
                messages, max_tokens, purpose, provider=provider, session=session,
                response_schema=response_schema, candidate_ids=candidate_ids,
                prompt_version=prompt_version,
            )
        except RateLimited as exc:
            start_cooldown(provider, _cooldown_seconds(exc.retry_after, provider.cooldown), "HTTP 429")
            reasons.append(f"{provider.name}: HTTP 429")
            continue
        except ProviderUnavailable as exc:
            start_cooldown(provider, UNAVAILABLE_COOLDOWN, str(exc))
            reasons.append(f"{provider.name}: {exc}")
            continue
        except LLMParseError:
            raise
        except LLMError as exc:
            logger.warning("LLM provider %s failed, trying the next one: %s", provider.name, exc)
            error = exc
            continue
        return content, tokens, provider, call

    if error is not None:
        raise error
    ends = [until for until in (cooldown_until(p) for p in providers() if p.configured) if until]
    retry_after = None
    if ends:
        retry_after = max(math.ceil((min(ends) - timezone.now()).total_seconds()), 1)
    exc = RateLimited(retry_after=retry_after)
    exc.reason = "; ".join(reasons)
    raise exc

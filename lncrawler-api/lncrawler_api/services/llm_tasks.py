"""Registry and runner for LLM workflows that go through ``LLMRequest``.

A workflow subclasses ``LLMTask``, registers itself with ``@register`` and gets
queueing, retries, rate-limit handling and budget checks from ``run_task``.
Domain tables keep their own decisions; this module only drives the queue.
"""
import json
import math
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..models import LLMRequest, LLMUsage, Tag
from ..models.sources_models import refresh_adult_for_tags
from . import llm_service
from .llm_service import LLMError, LLMParseError, RateLimited

logger = logging.getLogger("lncrawler_api.merge")

# A RUNNING request whose claim is older than this lost its worker mid-call.
STUCK_RUNNING_AFTER = timedelta(minutes=30)
# Used when a 429 carries no numeric Retry-After header.
DEFAULT_RETRY_AFTER = 60


class LLMTask:
    """Base for one LLM workflow. Subclasses set the class attributes and implement the hooks."""

    name = ""
    target_type = ""
    prompt_version = "1"
    usage_purpose = ""  # LLMUsage purpose passed to llm_service._post_chat
    max_tokens = 2048
    max_attempts = 3

    def calls_per_tick(self):
        """Default number of requests processed per scheduler tick."""
        raise NotImplementedError

    def enqueue(self, limit):
        """Create pending ``LLMRequest`` rows for work not yet queued. Returns how many."""
        raise NotImplementedError

    def build_messages(self, request):
        """Chat messages for one request, or None when there is nothing left to ask."""
        raise NotImplementedError

    def parse(self, request, content):
        """Turn the raw reply into a result dict. Raise ``LLMParseError`` if it is unusable."""
        raise NotImplementedError

    def apply(self, request, result):
        """Write the result to the domain tables. Must be idempotent (admin re-applies it)."""
        raise NotImplementedError


REGISTRY = {}


def register(task_cls):
    """Class decorator: add one instance of ``task_cls`` to ``REGISTRY`` under its name."""
    REGISTRY[task_cls.name] = task_cls()
    return task_cls


def _retry_after_seconds(value):
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER


def _reset_stuck(task_name, now):
    """Put RUNNING requests whose worker died back in the queue.

    ``not_before`` is set to the claim time when a request starts running, so it
    doubles as the start timestamp while the status is RUNNING.
    """
    LLMRequest.objects.filter(
        task=task_name,
        status=LLMRequest.STATUS_RUNNING,
        not_before__lt=now - STUCK_RUNNING_AFTER,
    ).update(status=LLMRequest.STATUS_PENDING, not_before=None)


def _claim(task_name, now):
    """Atomically take the oldest due PENDING request of ``task_name``. None if there is none."""
    with transaction.atomic():
        req = (
            LLMRequest.objects.select_for_update(skip_locked=True)
            .filter(task=task_name, status=LLMRequest.STATUS_PENDING)
            .filter(Q(not_before__isnull=True) | Q(not_before__lte=now))
            .order_by("created_at")
            .first()
        )
        if req is None:
            return None
        req.status = LLMRequest.STATUS_RUNNING
        req.attempts += 1
        req.model = settings.LLM_MODEL
        req.not_before = now
        req.save(update_fields=["status", "attempts", "model", "not_before"])
    return req


def run_task(task_name, limit, session=None, stdout=None):
    """Enqueue then process up to ``limit`` due requests of one task."""
    if not llm_service.is_configured():
        return {"skipped": "not configured"}
    task = REGISTRY[task_name]
    now = timezone.now()
    counts = {"done": 0, "failed": 0, "retry": 0, "rate_limited": False}

    _reset_stuck(task_name, now)
    task.enqueue(limit)

    for _ in range(limit):
        # One budget for every workflow; stop once it can't cover this task's worst case.
        if not llm_service.can_afford(task.usage_purpose):
            break
        req = _claim(task_name, timezone.now())
        if req is None:
            break
        try:
            messages = task.build_messages(req)
            if messages is None:
                # Nothing left to ask: close the request without a call.
                req.status = LLMRequest.STATUS_DONE
                req.response = {"skipped": "no targets left"}
                req.not_before = None
                req.finished_at = timezone.now()
                req.save()
                continue
            content, tokens = llm_service._post_chat(
                messages,
                task.max_tokens,
                task.usage_purpose,
                session=session,
            )
            req.raw_response = content
            req.tokens = tokens
            result = task.parse(req, content)
            task.apply(req, result)
            req.status = LLMRequest.STATUS_DONE
            req.response = result
            req.error = ""
            req.not_before = None
            req.finished_at = timezone.now()
            req.save()
            counts["done"] += 1
        except RateLimited as exc:
            # Not the request's fault: give the attempt back and stop this run.
            req.status = LLMRequest.STATUS_PENDING
            req.attempts -= 1
            req.not_before = timezone.now() + timedelta(seconds=_retry_after_seconds(exc.retry_after))
            req.save()
            counts["rate_limited"] = True
            break
        except Exception as exc:  # LLMError, network errors, a bug in apply...
            # Anything else would leave the row RUNNING until _reset_stuck.
            req.error = f"{type(exc).__name__}: {exc}"[:2000]
            if isinstance(exc, LLMError):
                logger.warning("LLM request %s (%s) failed: %s", req.pk, task_name, req.error)
            else:
                logger.exception("LLM request %s (%s) crashed", req.pk, task_name)
            if req.attempts >= task.max_attempts:
                req.status = LLMRequest.STATUS_FAILED
                req.not_before = None
                req.finished_at = timezone.now()
                counts["failed"] += 1
            else:
                req.status = LLMRequest.STATUS_PENDING
                req.not_before = timezone.now() + timedelta(minutes=2 ** req.attempts)
                counts["retry"] += 1
            req.save()
            if stdout:
                stdout.write(f"request {req.pk}: {req.status}: {req.error[:200]}")
    return counts


@register
class TagR18Task(LLMTask):
    """Flag tags whose name itself implies sexually explicit content as adult (R18)."""

    name = "tag_r18"
    target_type = "tag"
    prompt_version = "1"
    usage_purpose = LLMUsage.PURPOSE_R18
    max_tokens = settings.TAG_R18_LLM_MAX_TOKENS

    SYSTEM_PROMPT = (
        "You classify light-novel tags. For each tag, answer r18 true only when the "
        "tag itself names sexually explicit content (for example 'Smut', 'Hentai', "
        "'Explicit Sex'). Content ratings and mature or suggestive themes are NOT "
        "R18: 'Adult', 'Mature', 'Ecchi', 'Gore', 'Violence', 'Romance', 'Harem' all "
        "answer false, because sites use them for works that are not explicit. When "
        "unsure, answer false with low confidence. "
        'Reply with JSON only, in the form {"tags": [{"id": <int>, "r18": true|false, '
        '"confidence": <0..1>}]}.'
    )

    def calls_per_tick(self):
        return settings.TAG_R18_LLM_CALLS_PER_TICK

    def enqueue(self, limit):
        per_call = settings.TAG_R18_LLM_TAGS_PER_CALL
        covered = set()
        # FAILED batches count as covered too: a batch that fails deterministically
        # would otherwise be re-enqueued every tick. Requeue it from the admin.
        for ids in LLMRequest.objects.filter(
            task=self.name, prompt_version=self.prompt_version,
        ).values_list("target_ids", flat=True):
            covered.update(ids or [])
        candidates = list(
            Tag.objects.filter(is_adult=False)
            .exclude(pk__in=covered)
            .order_by("pk")
            .values_list("pk", flat=True)[: limit * per_call]
        )
        created = 0
        for start in range(0, len(candidates), per_call):
            LLMRequest.objects.create(
                task=self.name,
                target_type=self.target_type,
                target_ids=candidates[start:start + per_call],
                prompt_version=self.prompt_version,
            )
            created += 1
        return created

    def build_messages(self, request):
        tags = Tag.objects.filter(pk__in=request.target_ids, is_adult=False).order_by("pk")
        payload = [{"id": tag.pk, "name": tag.name} for tag in tags]
        if not payload:
            return None  # every tag was deleted or flagged since the batch was queued
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

    def parse(self, request, content):
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end <= start:
            raise LLMParseError("no JSON object in reply")
        try:
            data = json.loads(content[start:end + 1])
        except ValueError as exc:
            raise LLMParseError(f"invalid JSON: {exc}") from exc
        items = data.get("tags") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise LLMParseError("missing tags list")

        allowed = set(request.target_ids)
        tags = []
        for item in items:
            if not isinstance(item, dict):
                continue
            tag_id, r18, confidence = item.get("id"), item.get("r18"), item.get("confidence")
            if type(tag_id) is not int or tag_id not in allowed or not isinstance(r18, bool):
                continue
            if (
                not isinstance(confidence, (int, float)) or isinstance(confidence, bool)
                or not math.isfinite(confidence)  # json.loads accepts NaN; jsonb does not
            ):
                confidence = 0.0
            tags.append({
                "id": tag_id,
                "r18": r18,
                "confidence": min(max(float(confidence), 0.0), 1.0),
            })
        if not tags:
            raise LLMParseError("no valid tag entries in reply")
        return {"tags": tags}

    def apply(self, request, result):
        min_confidence = settings.TAG_R18_LLM_MIN_CONFIDENCE
        ids = [t["id"] for t in result["tags"] if t["r18"] and t["confidence"] >= min_confidence]
        if not ids:
            return
        Tag.objects.filter(pk__in=ids, is_adult=False).update(is_adult=True)
        refresh_adult_for_tags(ids)

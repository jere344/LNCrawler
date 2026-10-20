"""Registry and runner for LLM workflows that go through ``LLMRequest``.

A workflow subclasses ``LLMTask``, registers itself with ``@register`` and gets
queueing, retries, rate-limit handling and budget checks from ``run_task``.
Domain tables keep their own decisions; this module only drives the queue.
"""
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..models import Author, AuthorMergeCandidate, LLMRequest, LLMUsage, MergeCandidate, Tag
from ..models.sources_models import refresh_adult_for_tags
from . import llm_service
from .author_merge_service import merge_candidate
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
                # Nothing left to ask: close the request without a call. A requeued
                # done request keeps the result it already had.
                req.status = LLMRequest.STATUS_DONE
                if req.response is None:
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

    RATINGS = ("explicit", "suggestive", "none")

    SYSTEM_PROMPT = (
        "You classify light-novel tags by how sexual the tag name itself is. Rate each tag "
        "'explicit', 'suggestive' or 'none'. "
        "explicit: the tag names a sex act, sexual body parts in a sexual context, or a "
        "pornographic genre, so the tag alone makes the work porn (for example 'Smut', "
        "'Hentai', 'Explicit Sex', 'Gangbang', 'Blowjob'). "
        "suggestive: sex appeal, attractiveness, character archetypes, fan service or "
        "mature themes without naming explicit sex (for example 'Sexy', 'Hot', 'MILF', "
        "'Lewd', 'Fan Service', 'Big Breasts', 'Seductive', 'Succubus', 'Ecchi', 'Adult', "
        "'Mature'). "
        "none: everything else, including 'Gore', 'Violence', 'Romance', 'Harem'. "
        "Only explicit tags hide a novel from most readers, so a wrong explicit rating is "
        "costly: answer explicit only when the tag is unambiguously pornographic, and "
        "answer suggestive whenever you hesitate between the two. "
        'Reply with JSON only, in the form {"tags": [{"id": <int>, "rating": '
        '"explicit"|"suggestive"|"none", "confidence": <0..1>}]}.'
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
            tag_id, rating, confidence = item.get("id"), item.get("rating"), item.get("confidence")
            if type(tag_id) is not int or tag_id not in allowed:
                continue
            if not isinstance(rating, str) or rating not in self.RATINGS:
                continue
            tags.append({
                "id": tag_id,
                "rating": rating,
                "r18": rating == "explicit",
                "confidence": llm_service.parse_confidence(confidence, strict=True),
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


def _novel_profile(novel):
    titles = [novel.title] if novel.title else []
    alts, authors, languages = set(), set(), set()
    synopsis = ""
    for src in novel.sources.all():
        if src.title and src.title not in titles:
            titles.append(src.title)
        if src.language:
            languages.add(src.language)
        if not synopsis and src.synopsis:
            synopsis = src.synopsis
        for author in src.authors.all():
            authors.add(author.name)
        for alt in src.alternative_titles.all():
            alts.add(alt.name)
    return {
        "title": novel.title or (titles[0] if titles else ""),
        "titles": titles,
        "alternative_titles": sorted(alts),
        "authors": sorted(authors),
        "languages": sorted(languages),
        "synopsis": (synopsis or "")[:600],
    }


@register
class NovelMergeTask(LLMTask):
    """Judge whether a gray-band merge candidate pairs two copies of the same novel."""

    name = "novel_merge"
    target_type = "merge_candidate"
    prompt_version = "1"
    usage_purpose = LLMUsage.PURPOSE_NOVEL
    max_tokens = settings.MERGE_LLM_MAX_TOKENS

    def calls_per_tick(self):
        return settings.MERGE_LLM_LIMIT_PER_TICK

    def enqueue(self, limit):
        covered = set()
        # PENDING, RUNNING and FAILED requests count as covered: a FAILED one would
        # otherwise be re-enqueued every tick. Requeue it from the admin. DONE ones
        # do not: a DONE request sets llm_checked_at, so an unchecked candidate
        # again means someone cleared it on purpose to re-judge.
        for ids in LLMRequest.objects.filter(
            task=self.name,
            prompt_version=self.prompt_version,
            status__in=[LLMRequest.STATUS_PENDING, LLMRequest.STATUS_RUNNING, LLMRequest.STATUS_FAILED],
        ).values_list("target_ids", flat=True):
            covered.update(ids or [])
        candidates = list(
            MergeCandidate.objects.filter(
                status=MergeCandidate.STATUS_PENDING,
                decision=MergeCandidate.DECISION_REVIEW,
                llm_checked_at__isnull=True,
                novel_a__isnull=False,
                novel_b__isnull=False,
            )
            .exclude(pk__in=covered)
            .order_by("-certainty")
            .values_list("pk", flat=True)[:limit]
        )
        for pk in candidates:
            LLMRequest.objects.create(
                task=self.name,
                target_type=self.target_type,
                target_ids=[str(pk)],
                prompt_version=self.prompt_version,
            )
        return len(candidates)

    def build_messages(self, request):
        candidate = (
            MergeCandidate.objects.filter(pk__in=request.target_ids)
            .select_related("novel_a", "novel_b")
            .prefetch_related(
                "novel_a__sources__authors",
                "novel_a__sources__alternative_titles",
                "novel_b__sources__authors",
                "novel_b__sources__alternative_titles",
            )
            .first()
        )
        if (
            candidate is None
            or candidate.status != MergeCandidate.STATUS_PENDING
            or candidate.decision != MergeCandidate.DECISION_REVIEW
            or candidate.llm_checked_at is not None
            or candidate.novel_a is None
            or candidate.novel_b is None
        ):
            return None  # gone, decided, already judged, or a novel was deleted since queued
        return llm_service.build_messages(
            _novel_profile(candidate.novel_a), _novel_profile(candidate.novel_b)
        )

    def parse(self, request, content):
        return llm_service._parse_content(content)

    def apply(self, request, result):
        candidate = MergeCandidate.objects.filter(pk__in=request.target_ids).first()
        if candidate is None:
            return
        candidate.llm_verdict = result
        candidate.llm_reason = result.get("reason", "")
        candidate.llm_model = request.model
        candidate.llm_checked_at = request.finished_at or timezone.now()
        update_fields = ["llm_verdict", "llm_reason", "llm_model", "llm_checked_at", "updated_at"]
        # A confident "different" on a weak candidate is noise for the reviewer:
        # skip it. Strong deterministic matches stay queued even when the LLM
        # disagrees, so a human still decides them. Only while still pending, so
        # a re-apply never overrides a decision already made.
        dismiss_confidence = settings.MERGE_LLM_DISMISS_CONFIDENCE
        dismiss_max_certainty = settings.MERGE_LLM_DISMISS_MAX_CERTAINTY
        confidence = float(result.get("confidence") or 0.0)
        if (
            candidate.status == MergeCandidate.STATUS_PENDING
            and not result.get("same")
            and confidence >= dismiss_confidence
            and candidate.certainty < dismiss_max_certainty
        ):
            candidate.status = MergeCandidate.STATUS_SKIPPED
            update_fields.append("status")
        candidate.save(update_fields=update_fields)


def _author_profile(author):
    novels = [
        {"title": src.title, "language": src.language}
        for src in author.novels.order_by("pk")[:3]
    ]
    return {
        "name": author.name,
        "aliases": list(author.aliases.order_by("name").values_list("name", flat=True)),
        "novels": novels,
    }


@register
class AuthorMergeTask(LLMTask):
    """Judge whether two author names from the finder refer to the same person."""

    name = "author_merge"
    target_type = "author_merge_candidate"
    prompt_version = "2"
    usage_purpose = LLMUsage.PURPOSE_NOVEL
    max_tokens = settings.MERGE_LLM_MAX_TOKENS

    SYSTEM_PROMPT = (
        "You decide whether two author names refer to the same person: pen names, "
        "translations and romanizations of one name across languages are the same person. "
        "Illustrators, translators and other credited staff are different people. "
        "A name that lists several people (for example 'Okina Baba and Tsukasa Kiryu') "
        "is NEVER the same as one of the people it lists: answer different. "
        'Reply with JSON only, in the form {"results": [{"id": <candidate id>, '
        '"verdict": "same"|"different", "confidence": <0..1>}]}.'
    )

    def calls_per_tick(self):
        return settings.MERGE_LLM_LIMIT_PER_TICK

    def enqueue(self, limit):
        per_call = settings.AUTHOR_MERGE_LLM_BATCH
        covered = set()
        # PENDING, RUNNING and FAILED requests count as covered: a FAILED one would
        # otherwise be re-enqueued every tick. Requeue it from the admin. DONE ones
        # do not: a DONE request stores llm_response, so an unanswered candidate
        # again means someone cleared it on purpose to re-judge.
        for ids in LLMRequest.objects.filter(
            task=self.name,
            prompt_version=self.prompt_version,
            status__in=[LLMRequest.STATUS_PENDING, LLMRequest.STATUS_RUNNING, LLMRequest.STATUS_FAILED],
        ).values_list("target_ids", flat=True):
            covered.update(ids or [])
        candidates = list(
            AuthorMergeCandidate.objects.filter(
                status=AuthorMergeCandidate.STATUS_PENDING,
                llm_response__isnull=True,
            )
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
        payload = []
        candidates = AuthorMergeCandidate.objects.filter(
            pk__in=request.target_ids,
            status=AuthorMergeCandidate.STATUS_PENDING,
            llm_response__isnull=True,
        ).order_by("pk")
        for candidate in candidates:
            authors = list(Author.objects.filter(pk__in=candidate.author_ids).order_by("pk"))
            if len(authors) != 2:
                # An author was deleted or merged since the batch was queued.
                candidate.status = AuthorMergeCandidate.STATUS_ERROR
                candidate.reason = "author merged away"
                candidate.save(update_fields=["status", "reason", "updated_at"])
                continue
            payload.append({
                "id": candidate.pk,
                "authors": [_author_profile(author) for author in authors],
                "signals": candidate.signals,
            })
        if not payload:
            return None
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
        items = data.get("results") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise LLMParseError("missing results list")

        allowed = set(request.target_ids)
        results = []
        for item in items:
            if not isinstance(item, dict):
                continue
            candidate_id, verdict = item.get("id"), item.get("verdict")
            if type(candidate_id) is not int or candidate_id not in allowed:
                continue
            if verdict not in ("same", "different"):
                continue
            results.append({
                "id": candidate_id,
                "verdict": verdict,
                "confidence": llm_service.parse_confidence(item.get("confidence"), strict=True),
            })
        if not results:
            raise LLMParseError("no valid author entries in reply")
        return {"results": results}

    def apply(self, request, result):
        min_confidence = settings.AUTHOR_MERGE_LLM_MIN_CONFIDENCE
        for item in result["results"]:
            candidate = AuthorMergeCandidate.objects.filter(pk=item["id"]).first()
            # Only pending candidates are judged: a decided one keeps its decision on re-apply.
            if candidate is None or candidate.status != AuthorMergeCandidate.STATUS_PENDING:
                continue
            candidate.llm_response = item
            candidate.llm_model = request.model
            candidate.save(update_fields=["llm_response", "llm_model", "updated_at"])

            if item["verdict"] == "different":
                candidate.status = AuthorMergeCandidate.STATUS_REJECTED
                candidate.decided_at = timezone.now()
                candidate.save(update_fields=["status", "decided_at", "updated_at"])
                continue
            if item["confidence"] < min_confidence:
                candidate.status = AuthorMergeCandidate.STATUS_REVIEW
                candidate.save(update_fields=["status", "updated_at"])
                continue

            merge_candidate(candidate)

        # A candidate the model left out of its reply is not judged: flag it, don't leave it pending.
        for candidate in AuthorMergeCandidate.objects.filter(
            pk__in=request.target_ids, status=AuthorMergeCandidate.STATUS_PENDING,
        ):
            candidate.status = AuthorMergeCandidate.STATUS_ERROR
            candidate.reason = "no llm answer"
            candidate.save(update_fields=["status", "reason", "updated_at"])

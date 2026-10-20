"""Registry and runner for LLM workflows that go through ``LLMRequest``.

A workflow subclasses ``LLMTask``, registers itself with ``@register`` and gets
queueing, retries, rate-limit handling and budget checks from ``run_queue``.
Domain tables keep their own decisions; this module only drives the queue.
"""
import json
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..models import Author, AuthorMergeCandidate, LLMRequest, MergeCandidate, Tag, TagCluster
from ..models.sources_models import refresh_adult_for_tags
from . import llm_service
from . import tag_merge_service as tms
from .author_merge_service import merge_candidate
from .merge_service import MergeError, merge_novels, pick_merge_survivor
from .llm_service import LLMError, LLMParseError, RateLimited

logger = logging.getLogger("lncrawler_api.merge")

# A RUNNING request whose claim is older than this lost its worker mid-call.
STUCK_RUNNING_AFTER = timedelta(minutes=30)
# Used when a 429 carries no numeric Retry-After header.
DEFAULT_RETRY_AFTER = 60
# Pending requests kept queued per task by each run.
QUEUE_BACKLOG = 5


class LLMTask:
    """Base for one LLM workflow. Subclasses set the class attributes and implement the hooks."""

    name = ""
    label = ""  # admin display name
    target_type = ""
    prompt_version = "1"
    # Hard-coded per task, sized so one call costs about llm_service.CALL_TOKENS.
    batch_size = 1  # targets packed into one call
    max_tokens = 2048
    max_attempts = 3

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

    def on_failed(self, request):
        """Called once when ``request`` reaches FAILED (attempts exhausted). Default: nothing."""


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


def _top_up(task, limit):
    """Enqueue so ``task`` has ``QUEUE_BACKLOG`` (or ``limit``) pending requests. Returns how many were created."""
    pending = LLMRequest.objects.filter(task=task.name, status=LLMRequest.STATUS_PENDING).count()
    missing = max(QUEUE_BACKLOG, limit or 0) - pending
    if missing <= 0:
        return 0
    return task.enqueue(missing)


def _process(task, req, session, stdout):
    """Run one claimed request. Returns "done", "skipped", "retry", "failed" or "rate_limited"."""
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
            return "skipped"
        content, tokens = llm_service._post_chat(
            messages,
            task.max_tokens,
            task.name,
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
        return "done"
    except RateLimited as exc:
        # Not the request's fault: give the attempt back and stop this run.
        req.status = LLMRequest.STATUS_PENDING
        req.attempts -= 1
        req.not_before = timezone.now() + timedelta(seconds=_retry_after_seconds(exc.retry_after))
        req.save()
        return "rate_limited"
    except Exception as exc:  # LLMError, network errors, a bug in apply...
        # Anything else would leave the row RUNNING until _reset_stuck.
        req.error = f"{type(exc).__name__}: {exc}"[:2000]
        if isinstance(exc, LLMError):
            logger.warning("LLM request %s (%s) failed: %s", req.pk, task.name, req.error)
        else:
            logger.exception("LLM request %s (%s) crashed", req.pk, task.name)
        if req.attempts >= task.max_attempts:
            req.status = LLMRequest.STATUS_FAILED
            req.not_before = None
            req.finished_at = timezone.now()
            outcome = "failed"
        else:
            req.status = LLMRequest.STATUS_PENDING
            req.not_before = timezone.now() + timedelta(minutes=2 ** req.attempts)
            outcome = "retry"
        req.save()
        if req.status == LLMRequest.STATUS_FAILED:
            try:
                task.on_failed(req)
            except Exception:
                logger.exception("on_failed for LLM request %s (%s) crashed", req.pk, task.name)
        if stdout:
            stdout.write(f"request {req.pk}: {req.status}: {req.error[:200]}")
        return outcome


def run_queue(task_names=None, limit=None, session=None, stdout=None):
    """Process pending requests of ``task_names`` (default: every task), taking turns.

    Each turn claims one request of the next task still having work. Stops after
    ``limit`` requests, when the provider limits (``llm_service.can_afford``) are
    reached, on a 429, or when every queue is empty.
    """
    if not llm_service.is_configured():
        return {"skipped": "not configured"}
    names = task_names or list(REGISTRY)
    counts = {"done": 0, "failed": 0, "retry": 0, "rate_limited": False}

    for name in names:
        _reset_stuck(name, timezone.now())
        _top_up(REGISTRY[name], limit)

    active = list(names)
    processed = 0
    stop = False
    while active and not stop:
        for name in list(active):
            if (limit is not None and processed >= limit) or not llm_service.can_afford():
                stop = True
                break
            req = _claim(name, timezone.now())
            if req is None:
                active.remove(name)
                continue
            processed += 1
            outcome = _process(REGISTRY[name], req, session, stdout)
            if outcome == "rate_limited":
                counts["rate_limited"] = True
                stop = True
                break
            if outcome in ("done", "failed", "retry"):
                counts[outcome] += 1
    return counts


def run_task(task_name, limit, session=None, stdout=None):
    """Process up to ``limit`` requests of one task. See ``run_queue``."""
    return run_queue([task_name], limit, session, stdout)


@register
class TagR18Task(LLMTask):
    """Flag tags whose name itself implies sexually explicit content as adult (R18)."""

    name = "tag_r18"
    label = "Tag R18 classifier"
    target_type = "tag"
    prompt_version = "1"
    batch_size = 50
    max_tokens = 4096

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

    def enqueue(self, limit):
        per_call = self.batch_size
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
    label = "Novel merge judge"
    target_type = "merge_candidate"
    prompt_version = "1"
    batch_size = 1  # the prompt is per pair
    max_tokens = 2048

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
        # A confident "same" merges the pair right away, whatever its certainty.
        if (
            candidate.status == MergeCandidate.STATUS_PENDING
            and result.get("same")
            and confidence >= settings.MERGE_LLM_AUTO_CONFIDENCE
        ):
            _auto_merge_candidate(candidate)


def _auto_merge_candidate(candidate):
    """Merge the pair of ``candidate`` and mark it merged (decision auto).

    A novel that is also in another pending pair may belong to a chain (A-B-C):
    the pair then stays queued for a human, as does one whose merge fails.
    """
    a, b = candidate.novel_a, candidate.novel_b
    if a is None or b is None:
        return
    ids = (a.pk, b.pk)
    in_chain = (
        MergeCandidate.objects.filter(status=MergeCandidate.STATUS_PENDING)
        .filter(Q(novel_a_id__in=ids) | Q(novel_b_id__in=ids))
        .exclude(pk=candidate.pk)
        .exists()
    )
    if in_chain:
        return
    target = pick_merge_survivor(a, b)
    source = b if target.pk == a.pk else a
    # merge_novels is atomic and moves files immediately (with its own undo
    # journal), so no outer transaction: a rollback of ours would leave the
    # moved files behind.
    try:
        merge_novels(source, target)
    except MergeError as exc:
        logger.warning("Auto-merge of candidate %s failed: %s", candidate.pk, exc)
        return
    # By pk: merge_novels deleted the source novel, so one FK is now NULL.
    MergeCandidate.objects.filter(pk=candidate.pk).update(
        status=MergeCandidate.STATUS_MERGED, decision=MergeCandidate.DECISION_AUTO,
    )


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
    label = "Author merge judge"
    target_type = "author_merge_candidate"
    prompt_version = "2"
    batch_size = 20
    max_tokens = 2048

    SYSTEM_PROMPT = (
        "You decide whether two author names refer to the same person: pen names, "
        "translations and romanizations of one name across languages are the same person. "
        "Illustrators, translators and other credited staff are different people. "
        "A name that lists several people (for example 'Okina Baba and Tsukasa Kiryu') "
        "is NEVER the same as one of the people it lists: answer different. "
        'Reply with JSON only, in the form {"results": [{"id": <candidate id>, '
        '"verdict": "same"|"different", "confidence": <0..1>}]}.'
    )

    def enqueue(self, limit):
        per_call = self.batch_size
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


def _tag_batch(request):
    """``(cluster, tags)`` for the still-pending clusters of ``request``, in ``target_ids`` order.

    A cluster with fewer than two tags left has nothing to merge: it is closed as no_merge.
    """
    clusters = {
        cluster.pk: cluster
        for cluster in TagCluster.objects.filter(
            pk__in=request.target_ids, status=TagCluster.STATUS_PENDING,
        )
    }
    batch = []
    for pk in request.target_ids:
        cluster = clusters.get(pk)
        if cluster is None:
            continue
        tags = tms.refresh_cluster_members(cluster)
        if len(tags) < 2:
            cluster.status = TagCluster.STATUS_NO_MERGE
            cluster.save(update_fields=["status", "updated_at"])
            continue
        batch.append((cluster, tags))
    return batch


def _label_groups(batch):
    """Judge-prompt groups and the ``{label: tag pk}`` maps that read the reply back."""
    usage = tms.tag_usage([tag.pk for _cluster, tags in batch for tag in tags])
    groups, label_maps = [], []
    for _cluster, tags in batch:
        labelled = [(f"t{number}", tag) for number, tag in enumerate(tags, 1)]
        groups.append([(label, tag.name, usage.get(tag.pk, 0)) for label, tag in labelled])
        label_maps.append({label: tag.pk for label, tag in labelled})
    return groups, label_maps


@register
class TagMergeTask(LLMTask):
    """Judge which tags in pending tag clusters are interchangeable, then apply the merges it is sure of."""

    name = "tag_merge"
    label = "Tag merge judge"
    target_type = "tag_cluster"
    prompt_version = "1"
    batch_size = 50
    max_tokens = 4096

    # Pending clusters inspected per packing pass.
    PACK_WINDOW = 200

    def enqueue(self, limit):
        covered = set()
        # PENDING and RUNNING requests cover their clusters. FAILED ones do not: on_failed
        # moves their clusters back to pending, so they must be queued again.
        for ids in LLMRequest.objects.filter(
            task=self.name,
            status__in=[LLMRequest.STATUS_PENDING, LLMRequest.STATUS_RUNNING],
        ).values_list("target_ids", flat=True):
            covered.update(ids or [])
        pending = (
            TagCluster.objects.filter(status=TagCluster.STATUS_PENDING)
            .exclude(pk__in=covered)
            .order_by("requeue_count", "created_at", "pk")
        )
        per_call = self.batch_size
        batches, batch, total = [], [], 0
        # Fresh clusters first; clusters sent back after a failed call go to the back.
        for cluster in list(pending[: self.PACK_WINDOW]):
            if len(batches) >= limit:
                break
            tags = tms.refresh_cluster_members(cluster)
            if len(tags) < 2:
                cluster.status = TagCluster.STATUS_NO_MERGE
                cluster.save(update_fields=["status", "updated_at"])
                continue
            if cluster.requeue_count and batch:
                batches.append(batch)
                batch, total = [], 0
            batch.append(cluster.pk)
            total += len(tags)
            # A requeued cluster is judged alone, so a truncation caused by packing heals itself.
            if cluster.requeue_count or total >= per_call:
                batches.append(batch)
                batch, total = [], 0
        if batch and len(batches) < limit:
            batches.append(batch)
        batches = batches[:limit]
        for target_ids in batches:
            LLMRequest.objects.create(
                task=self.name,
                target_type=self.target_type,
                target_ids=target_ids,
                prompt_version=self.prompt_version,
            )
        return len(batches)

    def build_messages(self, request):
        batch = _tag_batch(request)
        if not batch:
            return None  # clusters were judged, cleared or merged since the request was queued
        groups, label_maps = _label_groups(batch)
        # Frozen for parse: the labels only describe the tags sent in this call.
        request._tag_judge = ([cluster.pk for cluster, _tags in batch], label_maps)
        return tms.build_judge_messages(groups)

    def parse(self, request, content):
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end <= start:
            raise LLMParseError("no JSON object in reply")
        try:
            data = json.loads(content[start:end + 1])
        except ValueError as exc:
            raise LLMParseError(f"invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMParseError("reply is not a JSON object")

        judged = getattr(request, "_tag_judge", None)
        if judged is None:
            raise LLMParseError("no label map for this request")
        cluster_pks, label_maps = judged
        results = tms.parse_judge_response(data, label_maps)
        return {"clusters": [
            {"id": pk, "sets": sets}
            for pk, sets in zip(cluster_pks, results)
        ]}

    def apply(self, request, result):
        batch_id = uuid.uuid4()
        now = timezone.now()
        for item in result["clusters"]:
            cluster = TagCluster.objects.filter(pk=item["id"]).first()
            # Only pending clusters not judged yet: a decided one keeps its decision, and a
            # second answer (re-apply, overlapping request) never overwrites the first.
            if cluster is None or cluster.status != TagCluster.STATUS_PENDING or cluster.llm_batch is not None:
                continue
            cluster.llm_response = {"sets": item["sets"]}
            cluster.llm_model = request.model or settings.LLM_MODEL
            cluster.llm_batch = batch_id
            cluster.judged_at = now
            cluster.save(update_fields=[
                "llm_response", "llm_model", "llm_batch", "judged_at", "updated_at"
            ])
            tms.apply_cluster(cluster)

    def on_failed(self, request):
        reason = f"LLM request {request.pk} failed: {request.error}"[:500]
        for cluster in TagCluster.objects.filter(
            pk__in=request.target_ids, status=TagCluster.STATUS_PENDING,
        ):
            if len(request.target_ids) > 1:
                # Back to pending with requeue_count set, so it is judged alone next time.
                tms._requeue(cluster, reason)
            else:
                cluster.status = TagCluster.STATUS_ERROR
                cluster.error = reason
                cluster.save(update_fields=["status", "error", "updated_at"])

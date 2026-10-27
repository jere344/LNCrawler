"""Registry and runner for the LLM judged kinds, which go through the ``Candidate`` queue.

A kind subclasses ``LLMTask``, registers itself with ``@register`` and gets claiming,
retries, rate-limit handling and budget checks from ``run_queue``. The rule that turns
an answer into a decision is ``decide``, shared by every kind. The change itself is
made by the kind's ``apply_change`` and reverted by ``candidate_service``.
"""
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.html import strip_tags

from ..models import Author, Candidate, Novel, Tag
from ..models.sources_models import refresh_adult_for_tags
from ..utils.author_names import is_bracketed_original, normalize_author, romanization_fits
from . import llm_service
from . import tag_merge_service as tms
from .author_merge_service import merge_authors, pick_target
from .llm_service import LLMError, LLMParseError, RateLimited
from .merge_service import MergeError, merge_novels, pick_merge_survivor
from .tag_merge_service import NeedsReview, PlanChanged

logger = logging.getLogger("lncrawler_api.merge")

# A claim older than this lost its worker mid-call: the candidates go back to the pool.
STUCK_CLAIM_AFTER = timedelta(minutes=30)
# Used when a 429 carries no numeric Retry-After header.
DEFAULT_RETRY_AFTER = 60


class LLMTask:
    """Base for one judged kind. Subclasses set the class attributes and implement the hooks.

    ``name`` is the ``Candidate.kind`` the task works on. The hooks are called in this
    order for each claimed batch: ``prepare``, ``build_messages``, ``parse``, ``verify``,
    then per candidate ``safeguards`` and ``apply_change`` (through ``decide``).
    """

    name = ""
    label = ""  # admin display name
    prompt_version = "1"
    # Hard-coded per kind, sized so one call stays under llm_service.CALL_TOKENS.
    batch_size = 1  # candidates packed into one call
    pack_window = 200  # pending candidates inspected per claim
    max_tokens = 2048
    max_attempts = 3
    # Setting holding the confidence a "yes" or "no" needs to be decided on its own.
    confidence_setting = ""
    # False: a "no" is rejected whatever its confidence (only R18 uses it).
    review_uncertain_no = True
    # JSON schema the reply must follow, sent as response_format; None sends none.
    response_schema = None
    # True: the change runs inside the candidate's lock, in one transaction. False: the
    # change opens its own transactions (novel merges move folders), so it runs with no
    # lock held, between two writes of the decision (see ``_settle_two_phase``).
    apply_in_transaction = True

    def threshold(self):
        return getattr(settings, self.confidence_setting)

    def pack(self, candidates):
        """Group the claimed candidates into calls. The runner sends the first group."""
        return [
            candidates[start:start + self.batch_size]
            for start in range(0, len(candidates), self.batch_size)
        ]

    def prepare(self, batch):
        """Return ``(kept, context)``: the candidates still worth asking, and what the
        other hooks need from the same look. Candidates whose targets are gone are
        deleted here (``_drop``) and left out of ``kept``."""
        return batch, None

    def build_messages(self, kept, context):
        """Chat messages asking about ``kept``."""
        raise NotImplementedError

    def parse(self, kept, context, content):
        """Return ``{candidate pk: judgement}`` for the candidates the reply answers.

        A judgement holds ``answer`` ("yes", "no" or "unsure"), ``confidence``, ``reason``
        and the kind's own fields: it is stored as the candidate's ``verdict``. A
        candidate left out is not judged (it is retried). Raise ``LLMParseError`` when
        the reply is unusable.
        """
        raise NotImplementedError

    def verify(self, kept, context, judged, send):
        """Return ``judged``, optionally checked by a second call. ``send(messages, response_schema)``
        makes one call and returns the chat result. Raise ``LLMParseError`` when the reply is unusable."""
        return judged

    def has_nothing_left(self, candidate, judgement):
        """True when a "yes" has nothing left to change now: it is then a "no", rejected by the LLM."""
        return False

    def safeguards(self, candidate, judgement):
        """Reasons that send a "yes" to review. Empty list: none fired."""
        return []

    def apply_change(self, candidate, judgement, by_human=False):
        """Make the change of an applied candidate. Returns its undo entries.

        Raises ``MergeError`` (or ``NeedsReview``, ``PlanChanged``) to refuse it.
        ``by_human`` is True when a reviewer applies it: the reviewer is the safeguard,
        so a task that re-checks its safeguards here skips them.
        """
        raise NotImplementedError


REGISTRY = {}


def register(task_cls):
    """Class decorator: add one instance of ``task_cls`` to ``REGISTRY`` under its name."""
    REGISTRY[task_cls.name] = task_cls()
    return task_cls


def decide(answer, confidence, threshold, safeguard_reasons, review_uncertain_no=True):
    """The one rule every kind follows. Returns ``(status, reason)``.

    A confident "yes" is applied unless a safeguard fired, which sends it to review.
    A confident "no" is rejected. Anything else waits for a human. A missing
    confidence counts as 0. Safeguards never reject.
    """
    confidence = confidence or 0.0
    if answer == "yes":
        if confidence < threshold:
            return Candidate.STATUS_REVIEW, f"low confidence ({confidence:.2f})"
        if safeguard_reasons:
            return Candidate.STATUS_REVIEW, "; ".join(safeguard_reasons)
        return Candidate.STATUS_APPLIED, ""
    if answer == "no":
        if confidence >= threshold or not review_uncertain_no:
            return Candidate.STATUS_REJECTED, ""
        return Candidate.STATUS_REVIEW, f"low confidence ({confidence:.2f})"
    return Candidate.STATUS_REVIEW, "unsure"


def _judge(task, candidate, judgement):
    """Store the verdict on ``candidate`` and work out its status. Returns ``(status, reason)``.

    Nothing is applied here.
    """
    candidate.verdict = judgement
    candidate.confidence = judgement.get("confidence")
    candidate.not_before = None
    if judgement["answer"] == "yes" and task.has_nothing_left(candidate, judgement):
        return Candidate.STATUS_REJECTED, "nothing left to change"
    safeguards = task.safeguards(candidate, judgement) if judgement["answer"] == "yes" else []
    return decide(
        judgement["answer"], judgement.get("confidence"), task.threshold(), safeguards,
        task.review_uncertain_no,
    )


def _record(candidate, status, reason, judgement, decided_by, now):
    """Set the final status, reason and decider on ``candidate`` (not saved)."""
    candidate.status = status
    candidate.reason = "; ".join(part for part in (reason, judgement.get("reason", "")) if part)
    if status == Candidate.STATUS_REVIEW:
        candidate.decided_by, candidate.decided_at = "", None
    else:
        candidate.decided_by, candidate.decided_at = decided_by, now


def settle(task, candidate, judgement, decided_by=Candidate.DECIDED_LLM):
    """Store ``judgement`` on ``candidate``, decide it and apply it when applied.

    The caller holds the candidate's lock. For a task with ``apply_in_transaction`` the
    change runs in a savepoint: a refused change (``MergeError``, ``NeedsReview``)
    leaves nothing behind and the candidate goes to review with the reason.
    ``PlanChanged`` propagates, so the caller can retry the candidate. Returns the new
    status.
    """
    now = timezone.now()
    candidate.claimed_at = None
    status, reason = _judge(task, candidate, judgement)
    if status == Candidate.STATUS_APPLIED:
        try:
            with transaction.atomic():
                entries = task.apply_change(candidate, judgement)
            candidate.undo = [*candidate.undo, *entries]
        except (MergeError, NeedsReview) as exc:
            status, reason = Candidate.STATUS_REVIEW, str(exc)
    _record(candidate, status, reason, judgement, decided_by, now)
    candidate.save()
    return status


def _retry_after_seconds(value):
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER


def _reset_stuck(task_name, now):
    """Clear claims whose worker died, so the candidates are claimed again."""
    Candidate.objects.filter(
        kind=task_name,
        status=Candidate.STATUS_PENDING,
        claimed_at__lt=now - STUCK_CLAIM_AFTER,
    ).update(claimed_at=None)


def _claim(task, now):
    """Claim one batch of due pending candidates of ``task``. Empty when there is none.

    Fresh candidates are packed together; a candidate that already failed is sent
    alone, so one bad answer cannot drag its neighbours down again.
    """
    with transaction.atomic():
        rows = list(
            Candidate.objects.select_for_update(skip_locked=True)
            .filter(kind=task.name, status=Candidate.STATUS_PENDING, claimed_at__isnull=True)
            .filter(Q(not_before__isnull=True) | Q(not_before__lte=now))
            .order_by("attempts", "created_at", "pk")[: task.pack_window]
        )
        if not rows:
            return []
        fresh = [candidate for candidate in rows if candidate.attempts == 0]
        batches = task.pack(fresh or rows[:1])
        batch = batches[0]
        # The claim token: a write only lands while the candidate still carries it.
        Candidate.objects.filter(pk__in=[candidate.pk for candidate in batch]).update(claimed_at=now)
    for candidate in batch:
        candidate.claimed_at = now
    return batch


def _drop(candidate, reason):
    """Delete a claimed candidate whose target is gone. It was not sent, so no decision is kept."""
    logger.info("Candidate %s (%s) dropped: %s", candidate.pk, candidate.kind, reason)
    candidate.delete()


def _release(task, pk, token, *, reason, attempt, not_before=None):
    """Give a claimed candidate back to the pool. Returns its new status, or None if the claim was lost.

    With ``attempt`` the try counts: the candidate waits ``2 ** attempts`` minutes, or
    goes to ``error`` at ``max_attempts``. Without it (a 429) ``not_before`` is used.
    """
    now = timezone.now()
    with transaction.atomic():
        candidate = (
            Candidate.objects.select_for_update()
            .filter(pk=pk, status=Candidate.STATUS_PENDING, claimed_at=token)
            .first()
        )
        if candidate is None:
            return None
        candidate.claimed_at = None
        candidate.reason = reason or candidate.reason
        if attempt:
            candidate.attempts += 1
            if candidate.attempts >= task.max_attempts:
                candidate.status = Candidate.STATUS_ERROR
                candidate.not_before = None
                candidate.decided_at = now
            else:
                candidate.not_before = now + timedelta(minutes=2 ** candidate.attempts)
        else:
            candidate.not_before = not_before
        candidate.save()
        return candidate.status


def _fail_one(task, pk, token, reason, counts, stdout):
    status = _release(task, pk, token, reason=reason, attempt=True)
    if status is None:
        return
    counts["failed" if status == Candidate.STATUS_ERROR else "retry"] += 1
    if stdout:
        stdout.write(f"candidate {pk}: {status}: {reason[:200]}")


def _fail_all(task, kept, token, exc, counts, stdout):
    reason = f"{type(exc).__name__}: {exc}"[:2000]
    if isinstance(exc, LLMError):
        logger.warning("LLM batch of %s (%s) failed: %s", [c.pk for c in kept], task.name, reason)
    else:
        logger.exception("LLM batch of %s (%s) crashed", [c.pk for c in kept], task.name)
    for candidate in kept:
        _fail_one(task, candidate.pk, token, reason, counts, stdout)


def _claimed(pk, token):
    """The candidate ``pk`` still pending under claim ``token``, locked for the caller's transaction."""
    return (
        Candidate.objects.select_for_update()
        .filter(pk=pk, status=Candidate.STATUS_PENDING, claimed_at=token)
        .first()
    )


def _settle_one(task, pk, token, judgement, call, counts, stdout):
    if not task.apply_in_transaction:
        return _settle_two_phase(task, pk, token, judgement, call, counts, stdout)
    try:
        with transaction.atomic():
            candidate = _claimed(pk, token)
            if candidate is None:
                # A human decided it, or a stuck reset took the claim, while the call ran.
                logger.info("LLM answer for candidate %s dropped: the claim was lost", pk)
                return
            candidate.llm_call = call
            settle(task, candidate, judgement)
    except PlanChanged:
        _fail_one(task, pk, token, "tags changed while the answer was pending", counts, stdout)
        return
    except Exception as exc:
        logger.exception("Candidate %s (%s) crashed while settling", pk, task.name)
        _fail_one(task, pk, token, f"{type(exc).__name__}: {exc}"[:2000], counts, stdout)
        return
    counts["done"] += 1


def _settle_two_phase(task, pk, token, judgement, call, counts, stdout):
    """Settle a candidate whose change must run outside any transaction.

    1. Under the lock, the verdict and the status are stored; the claim is kept, so
       nobody else takes the candidate while the change runs.
    2. The change runs with no lock held: it opens its own transactions.
    3. The outcome is written if the claim is still ours. A refused change goes to review.
    """
    now = timezone.now()
    try:
        with transaction.atomic():
            candidate = _claimed(pk, token)
            if candidate is None:
                logger.info("LLM answer for candidate %s dropped: the claim was lost", pk)
                return
            candidate.llm_call = call
            status, reason = _judge(task, candidate, judgement)
            candidate.save()
    except Exception as exc:
        logger.exception("Candidate %s (%s) crashed while settling", pk, task.name)
        _fail_one(task, pk, token, f"{type(exc).__name__}: {exc}"[:2000], counts, stdout)
        return

    entries = []
    if status == Candidate.STATUS_APPLIED:
        try:
            entries = task.apply_change(candidate, judgement)
        except (MergeError, NeedsReview) as exc:
            status, reason = Candidate.STATUS_REVIEW, str(exc)
        except Exception as exc:
            logger.exception("Candidate %s (%s) crashed while applying", pk, task.name)
            _fail_one(task, pk, token, f"{type(exc).__name__}: {exc}"[:2000], counts, stdout)
            return

    _record(candidate, status, reason, judgement, Candidate.DECIDED_LLM, now)
    rows = Candidate.objects.filter(pk=pk)
    if not entries:
        # Nothing changed: the outcome only lands while the claim is still ours.
        rows = rows.filter(status=Candidate.STATUS_PENDING, claimed_at=token)
    # A change that ran is recorded even if a stuck reset took the claim meanwhile:
    # without its undo entries the merge could not be undone.
    written = rows.update(
        claimed_at=None,
        status=candidate.status,
        reason=candidate.reason,
        decided_by=candidate.decided_by,
        decided_at=candidate.decided_at,
        undo=[*candidate.undo, *entries],
        updated_at=now,
    )
    if not written:
        if entries:
            logger.error("Candidate %s (%s) vanished while applying; undo entries %s", pk, task.name, entries)
        return
    counts["done"] += 1


def _rate_limited(task, kept, token, exc):
    """Give the batch back after a 429. Not the candidates' fault: no attempt is counted and the run stops."""
    reason = f"no provider available: {exc.reason}"[:2000] if getattr(exc, "reason", "") else ""
    not_before = timezone.now() + timedelta(seconds=_retry_after_seconds(exc.retry_after))
    for candidate in kept:
        _release(task, candidate.pk, token, reason=reason, attempt=False, not_before=not_before)
    return "rate_limited"


def _process(task, batch, session, stdout, counts):
    """Run one claimed batch: one LLM call, then each candidate is settled or backed off.

    Returns "rate_limited" when every provider is out of reach, else "done".
    """
    token = batch[0].claimed_at
    try:
        kept, context = task.prepare(batch)
        if not kept:
            return "done"
        messages = task.build_messages(kept, context)
    except Exception as exc:  # a bug or a malformed row: release the batch instead of leaving it claimed
        _fail_all(task, batch, token, exc, counts, stdout)
        return "done"
    def send(messages, response_schema):
        return llm_service.chat(
            messages,
            task.max_tokens,
            task.name,
            session=session,
            response_schema=response_schema,
            candidate_ids=[candidate.pk for candidate in kept],
            prompt_version=task.prompt_version,
        )

    try:
        content, _tokens, _provider, call = send(messages, task.response_schema)
    except RateLimited as exc:
        return _rate_limited(task, kept, token, exc)
    except Exception as exc:  # LLMError (non-JSON, truncated, no provider answered), network errors
        _fail_all(task, kept, token, exc, counts, stdout)
        return "done"
    try:
        judged = task.parse(kept, context, content)
    except Exception as exc:  # LLMParseError, or a bug in parse
        _fail_all(task, kept, token, exc, counts, stdout)
        return "done"
    try:
        judged = task.verify(kept, context, judged, send)
    except RateLimited as exc:
        return _rate_limited(task, kept, token, exc)
    except Exception as exc:  # LLMParseError from the verification reply, or a bug in verify
        _fail_all(task, kept, token, exc, counts, stdout)
        return "done"
    for candidate in kept:
        judgement = judged.get(candidate.pk)
        if judgement is None:
            # Left out of the reply: retried alone, like any unusable answer.
            _fail_one(task, candidate.pk, token, "no llm answer", counts, stdout)
        else:
            _settle_one(task, candidate.pk, token, judgement, call, counts, stdout)
    return "done"


def run_queue(task_names=None, limit=None, session=None, stdout=None):
    """Process pending candidates of ``task_names`` (default: every kind), taking turns.

    Each turn claims one batch of the next kind still having work. Stops after
    ``limit`` calls, when the provider limits (``llm_service.can_afford``) are
    reached, on a 429, or when every queue is empty.
    """
    if not llm_service.is_configured():
        return {"skipped": "not configured"}
    names = task_names or list(REGISTRY)
    counts = {"done": 0, "failed": 0, "retry": 0, "rate_limited": False}

    now = timezone.now()
    for name in names:
        _reset_stuck(name, now)

    active = list(names)
    processed = 0
    stop = False
    while active and not stop:
        for name in list(active):
            if (limit is not None and processed >= limit) or not llm_service.can_afford():
                stop = True
                break
            batch = _claim(REGISTRY[name], timezone.now())
            if not batch:
                active.remove(name)
                continue
            processed += 1
            outcome = _process(REGISTRY[name], batch, session, stdout, counts)
            if outcome == "rate_limited":
                counts["rate_limited"] = True
                stop = True
                break
    return counts


def _pair_novels(candidate):
    """The two novels of a novel_merge candidate, in ``target_ids`` order. None for a gone one."""
    found = {
        str(novel.pk): novel
        for novel in Novel.objects.filter(pk__in=candidate.target_ids)
        .prefetch_related("sources__alternative_titles")
    }
    return [found.get(str(pk)) for pk in candidate.target_ids]


def _pair_authors(candidate):
    return list(Author.objects.filter(pk__in=candidate.target_ids).order_by("pk"))


@register
class TagR18Task(LLMTask):
    """Flag tags whose name itself implies sexually explicit content as adult (R18)."""

    name = "tag_r18"
    label = "Tag R18 classifier"
    prompt_version = "1"
    batch_size = 50
    max_tokens = 4096
    confidence_setting = "TAG_R18_AUTO_CONFIDENCE"
    # Only an "explicit" flags the tag. Most tags are omitted from the reply, and an
    # omitted tag is a "no" whatever the confidence.
    review_uncertain_no = False

    RATINGS = ("explicit", "suggestive", "none")

    response_schema = {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "rating": {"type": "string", "enum": list(RATINGS)},
                        "confidence": {"type": "number"},
                    },
                    "required": ["id", "rating", "confidence"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["tags"],
        "additionalProperties": False,
    }

    # Only explicit ratings are applied, so the reply lists the few explicit or
    # suggestive tags and omits the rest (most of a batch), which keeps it short.
    SYSTEM_PROMPT = (
        "You flag light-novel tags whose name alone means the novel is pornographic. Rate each tag:\n"
        "explicit: it names a sex act, sexual body parts in a sexual context, or a pornographic genre "
        "('Smut', 'Hentai', 'Explicit Sex', 'Gangbang', 'Blowjob').\n"
        "suggestive: sexual themes, fan service, attractiveness, archetypes, or an age or maturity rating "
        "('R18', '18+', 'Adult', 'Mature', 'Ecchi', 'Lewd', 'MILF', 'Sexy', 'Succubus'). Age ratings are "
        "suggestive, never explicit: they also cover violence.\n"
        "none: everything else, including 'Gore', 'Violence', 'Romance', 'Harem'.\n"
        "An explicit rating hides the novel from most readers, so a wrong one is very costly: answer "
        "suggestive whenever you hesitate.\n"
        "List only the tags you rate explicit or suggestive and omit every other tag. Reply with compact JSON: "
        '{"tags":[{"id":<int>,"rating":"explicit"|"suggestive","confidence":<0..1>}]}'
    )

    def prepare(self, batch):
        kept = []
        for candidate in batch:
            if Tag.objects.filter(pk=candidate.target_ids[0], is_adult=False).exists():
                kept.append(candidate)
            else:
                _drop(candidate, "tag gone or already R18")
        return kept, None

    def build_messages(self, kept, context):
        tags = Tag.objects.filter(pk__in=[candidate.target_ids[0] for candidate in kept]).order_by("pk")
        payload = [{"id": tag.pk, "name": tag.name} for tag in tags]
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

    def parse(self, kept, context, content):
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

        by_tag = {candidate.target_ids[0]: candidate for candidate in kept}
        ratings = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            tag_id, rating, confidence = item.get("id"), item.get("rating"), item.get("confidence")
            if type(tag_id) is not int or tag_id not in by_tag:
                continue
            if not isinstance(rating, str) or rating not in self.RATINGS:
                continue
            ratings[tag_id] = (rating, llm_service.parse_confidence(confidence, strict=True))
        if items and not ratings:
            raise LLMParseError("no valid tag entries in reply")

        judged = {}
        for tag_id, candidate in by_tag.items():
            rating, confidence = ratings.get(tag_id, ("omitted", None))
            judged[candidate.pk] = {
                "answer": "yes" if rating == "explicit" else "no",
                "confidence": confidence,
                "reason": "",
                "rating": rating,
            }
        return judged

    def safeguards(self, candidate, judgement):
        usage = tms.tag_usage(candidate.target_ids).get(candidate.target_ids[0], 0)
        if usage >= settings.TAG_R18_REVIEW_NOVELS:
            return [f"tag on {usage} novels"]
        return []

    def apply_change(self, candidate, judgement, by_human=False):
        tag_id = candidate.target_ids[0]
        if not Tag.objects.filter(pk=tag_id, is_adult=False).update(is_adult=True):
            return []
        refresh_adult_for_tags([tag_id])
        return [{"type": "tag_r18", "tag_id": tag_id}]


def _novel_profile(novel):
    titles = [novel.title] if novel.title else []
    alts, languages = set(), set()
    synopsis = ""
    for src in novel.sources.all():
        if src.title and src.title not in titles:
            titles.append(src.title)
        if src.language:
            languages.add(src.language)
        if not synopsis and src.synopsis:
            synopsis = src.synopsis
        for alt in src.alternative_titles.all():
            alts.add(alt.name)
    return {
        "title": novel.title or (titles[0] if titles else ""),
        "titles": titles,
        "alternative_titles": sorted(alts),
        "languages": sorted(languages),
        # Synopses are stored as HTML: the tags only cost tokens.
        "synopsis": " ".join(strip_tags(synopsis or "").split())[:600],
    }


@register
class NovelMergeTask(LLMTask):
    """Judge whether a novel_merge candidate pairs two copies of the same novel."""

    name = "novel_merge"
    label = "Novel merge judge"
    prompt_version = "3"
    batch_size = 1  # the prompt is per pair
    max_tokens = 2048
    confidence_setting = "NOVEL_MERGE_AUTO_CONFIDENCE"
    # merge_novels moves folders and runs its own transaction: it must not sit in ours.
    apply_in_transaction = False

    response_schema = {
        "type": "object",
        "properties": {
            "same": {"type": "boolean"},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["same", "confidence", "reason"],
        "additionalProperties": False,
    }

    def prepare(self, batch):
        kept = []
        for candidate in batch:
            novels = _pair_novels(candidate)
            if len(novels) == 2 and all(novels):
                kept.append(candidate)
            else:
                _drop(candidate, "a novel of the pair no longer exists")
        return kept, None

    def build_messages(self, kept, context):
        novel_a, novel_b = _pair_novels(kept[0])
        return llm_service.build_messages(_novel_profile(novel_a), _novel_profile(novel_b))

    def parse(self, kept, context, content):
        result = llm_service._parse_content(content)
        return {kept[0].pk: {
            "answer": "yes" if result["same"] else "no",
            "confidence": float(result.get("confidence") or 0.0),
            "reason": result.get("reason", ""),
        }}

    def safeguards(self, candidate, judgement):
        # A novel that is also in another open pair may belong to a chain (A-B-C): the
        # pair stays with a human. Novel ids are stored as strings in target_ids.
        shares = Q()
        for pk in candidate.target_ids:
            shares |= Q(target_ids__contains=[str(pk)])
        in_chain = (
            Candidate.objects.filter(
                kind=self.name, status__in=[Candidate.STATUS_PENDING, Candidate.STATUS_REVIEW],
            )
            .filter(shares)
            .exclude(pk=candidate.pk)
            .exists()
        )
        return ["pair in a chain (another open pair shares a novel)"] if in_chain else []

    def apply_change(self, candidate, judgement, by_human=False):
        novel_a, novel_b = _pair_novels(candidate)
        if novel_a is None or novel_b is None:
            raise MergeError("a novel of the pair no longer exists")
        target = pick_merge_survivor(novel_a, novel_b)
        source = novel_b if target.pk == novel_a.pk else novel_a
        # The source is gone after the merge (Django clears its pk on delete): its undo data is read first.
        source_id = str(source.pk)
        snapshot = {
            "title": source.title,
            "slug": source.slug,
            "is_dmca": source.is_dmca,
            "added_by": source.added_by_id,
        }
        _target, moves = merge_novels(source, target, return_moves=True, candidate=candidate)
        return [{
            "type": "novel_merge",
            "source_id": source_id,
            "target_id": str(target.pk),
            "moved_source_ids": moves["moved_source_ids"],
            **snapshot,
        }]


def _author_payload(candidate, authors):
    """Names only, plus known aliases: the shared novel and the finder signals prove nothing."""
    entry = {"id": candidate.pk, "names": [author.name for author in authors]}
    aliases = [list(author.aliases.order_by("name").values_list("name", flat=True)) for author in authors]
    if any(aliases):
        entry["aliases"] = aliases
    return entry


def _names_match(candidate, item):
    """True when the reply names the candidate's own two authors. A reply about another row does not."""
    names = {normalize_author(name) for name in candidate.target_names}
    parts = str(item.get("names") or "").split(" / ", 1)
    return len(parts) == 2 and {normalize_author(part) for part in parts} == names


def _author_merge_refusal(candidate, item):
    """Why a judged "yes" must not merge (the name checks), or None when it may."""
    first, second = candidate.target_names[:2]
    if item["relation"] == "bracketed_original" and not is_bracketed_original(first, second):
        return "not a bracketed original"
    if item["relation"] in ("romanization", "same_name") and not romanization_fits(first, second):
        return "romanization does not match the character count"
    return None


@register
class AuthorMergeTask(LLMTask):
    """Judge how two author names from the finder relate; only name-based relations merge."""

    name = "author_merge"
    label = "Author merge judge"
    prompt_version = "6"
    batch_size = 20
    max_tokens = 4096
    confidence_setting = "AUTHOR_MERGE_AUTO_CONFIDENCE"

    RELATIONS = (
        "other_party", "bracketed_original", "romanization", "translation", "same_name",
        "different", "unsure",
    )
    MERGE_RELATIONS = {"bracketed_original", "romanization", "translation", "same_name"}
    REJECT_RELATIONS = {"different", "other_party"}

    response_schema = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "names": {"type": "string"},
                        "evidence": {"type": "string"},
                        "relation": {"type": "string", "enum": list(RELATIONS)},
                        "confidence": {"type": "number"},
                    },
                    "required": ["id", "names", "evidence", "relation", "confidence"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["results"],
        "additionalProperties": False,
    }

    # Relations are listed in the order the model must test them: other_party first,
    # otherwise it reads a translation group's name as a translation of the author's.
    SYSTEM_PROMPT = (
        "Two author names were credited on the same novel by different sources. Decide whether they "
        "name the same author: a person, or a group or team credited as the author. Sharing a novel "
        "proves nothing: sources also credit translators, illustrators, publishers and websites. "
        "Judge from the names only, and answer with the first relation that applies:\n"
        "1. other_party: one name is a website, platform, publisher, translation or scanlation group, "
        "a placeholder ('Unknown', 'Admin'), lists several people, or is a member of a group named by "
        "the other ('Barrista Lee' / 'Team Barrista').\n"
        "2. bracketed_original: one is the other plus its original form in brackets "
        "('Lucky Old Cat' / 'Lucky Old Cat (天运老猫)').\n"
        "3. romanization: one is the romanization of the other, every character accounted for "
        "('Er Gen' / '耳根', not 'Li Xian' / '李闲鱼').\n"
        "4. translation: one is the meaning of the other in another language "
        "('I Eat Tomatoes' / '我吃西红柿').\n"
        "5. same_name: the same name spelled differently: typo, other romanization or long vowels, "
        "accents, word order, spacing, punctuation, or added label text such as 'Author:', "
        "'Written by', a leading article or 'Team' ('Yuu Kamiya' / 'Yu Kamiya', "
        "'Team Barrista' / 'Barrista'). Any other word added or missing makes them different "
        "('Tomato Fan' / 'Tomato', 'Mr. Mo' / 'Mo').\n"
        "6. different: different names, even one syllable apart ('Wang Yu' / 'Wang Yi').\n"
        "7. unsure: anything else, including names you only guess are pen names of each other.\n"
        "Give a confidence from 0 to 1 for the relation you chose.\n"
        'Reply with JSON only: {"results": [{"id": <id>, "names": "<A> / <B>", '
        '"evidence": "<a few words: what differs>", "relation": "<relation>", "confidence": <0..1>}]}.'
    )

    def prepare(self, batch):
        kept = []
        for candidate in batch:
            if len(_pair_authors(candidate)) == 2:
                kept.append(candidate)
            else:
                _drop(candidate, "an author of the pair no longer exists")
        return kept, None

    def build_messages(self, kept, context):
        payload = [_author_payload(candidate, _pair_authors(candidate)) for candidate in kept]
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

    def parse(self, kept, context, content):
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

        by_pk = {candidate.pk: candidate for candidate in kept}
        judged = {}
        valid = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            candidate_id, relation = item.get("id"), item.get("relation")
            if type(candidate_id) is not int or candidate_id not in by_pk:
                continue
            if relation not in self.RELATIONS:
                continue
            valid += 1
            if not _names_match(by_pk[candidate_id], item):
                # The reply names other authors than this pair: it does not judge the pair,
                # so the candidate is left out and retried like any missing answer.
                continue
            if relation in self.MERGE_RELATIONS:
                answer = "yes"
            elif relation in self.REJECT_RELATIONS:
                answer = "no"
            else:
                answer = "unsure"
            judged[candidate_id] = {
                "answer": answer,
                "confidence": llm_service.parse_confidence(item.get("confidence")),
                "reason": str(item.get("evidence") or "")[:200],
                "relation": relation,
                "names": str(item.get("names") or ""),
            }
        if not valid:
            raise LLMParseError("no valid author entries in reply")
        return judged

    def safeguards(self, candidate, judgement):
        refusal = _author_merge_refusal(candidate, judgement)
        return [refusal] if refusal else []

    def apply_change(self, candidate, judgement, by_human=False):
        authors = _pair_authors(candidate)
        if len(authors) != 2:
            raise MergeError("an author of the pair no longer exists")
        target = pick_target(*authors)
        source = next(author for author in authors if author.pk != target.pk)
        return [merge_authors(source, target, candidate=candidate)]


def _label_groups(tag_lists):
    """Judge-prompt groups and the ``{label: tag pk}`` maps that read the reply back."""
    usage = tms.tag_usage([tag.pk for tags in tag_lists for tag in tags])
    groups, label_maps = [], []
    for tags in tag_lists:
        labelled = [(f"t{number}", tag) for number, tag in enumerate(tags, 1)]
        groups.append([(label, tag.name, usage.get(tag.pk, 0)) for label, tag in labelled])
        label_maps.append({label: tag.pk for label, tag in labelled})
    return groups, label_maps


@register
class TagMergeTask(LLMTask):
    """Judge which tags of a tag_merge candidate are interchangeable, then apply the merges it is sure of."""

    name = "tag_merge"
    label = "Tag merge judge"
    prompt_version = "3"
    # Tags per call (a batch closes once it reaches this, so up to one candidate more).
    # Measured on gemma: ~100 tags per call finds as many duplicates as 50 for ~22% fewer
    # tokens (the prompt is shared); at ~150 it starts missing obvious translations.
    batch_size = 90
    max_tokens = 4096
    confidence_setting = "TAG_MERGE_AUTO_CONFIDENCE"
    # Proposed sets per verification call.
    verify_sets = 40

    response_schema = {
        "type": "object",
        "properties": {
            "groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "group": {"type": "integer"},
                        # Literal English meaning of the non-English tags, written before the
                        # sets so translations are compared by meaning. Not stored.
                        "glosses": {"type": "string"},
                        "sets": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "members": {"type": "array", "items": {"type": "string"}},
                                    "canonical": {"type": "string"},
                                    "confidence": {"type": "number"},
                                },
                                "required": ["members", "canonical", "confidence"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["group", "glosses", "sets"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["groups"],
        "additionalProperties": False,
    }

    verify_schema = {
        "type": "object",
        "properties": {
            "sets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "set": {"type": "string"},
                        "keep": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["set", "keep"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["sets"],
        "additionalProperties": False,
    }

    def pack(self, candidates):
        """Packs candidates until their tags reach ``batch_size``; the candidate that reaches it closes the call."""
        batches, batch, total = [], [], 0
        for candidate in candidates:
            batch.append(candidate)
            total += len(candidate.target_ids)
            if total >= self.batch_size:
                batches.append(batch)
                batch, total = [], 0
        if batch:
            batches.append(batch)
        return batches

    def prepare(self, batch):
        kept, tag_lists = [], []
        for candidate in batch:
            found = Tag.objects.in_bulk(candidate.target_ids)
            tags = [found[pk] for pk in candidate.target_ids if pk in found]
            if len(tags) < 2:
                _drop(candidate, "fewer than 2 tags left")
                continue
            # Keep the snapshot to the tags that still exist.
            ids = [tag.pk for tag in tags]
            names = [tag.name for tag in tags]
            if ids != candidate.target_ids or names != candidate.target_names:
                candidate.target_ids = ids
                candidate.target_names = names
                candidate.save(update_fields=["target_ids", "target_names", "updated_at"])
            kept.append(candidate)
            tag_lists.append(tags)
        if not kept:
            return [], None
        return kept, _label_groups(tag_lists)

    def build_messages(self, kept, context):
        groups, _label_maps = context
        return tms.build_judge_messages(groups)

    def parse(self, kept, context, content):
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end <= start:
            raise LLMParseError("no JSON object in reply")
        try:
            data = json.loads(content[start:end + 1])
        except ValueError as exc:
            raise LLMParseError(f"invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMParseError("reply is not a JSON object")

        _groups, label_maps = context
        results = tms.parse_judge_response(data, label_maps)
        if any(proposed["confidence"] is None for raw_sets in results for proposed in raw_sets):
            raise LLMParseError("a proposed set has no usable confidence")
        # A group the reply does not mention is a missing answer, not a "no set". So is a
        # group whose sets were all unusable (labels the prompt never sent): a "no" would
        # reject the cluster on a malformed answer.
        answered, proposed_any, glosses = set(), set(), {}
        for item in data.get("groups") or []:
            if isinstance(item, dict):
                try:
                    index = int(item.get("group")) - 1
                except (TypeError, ValueError):
                    continue
                answered.add(index)
                if isinstance(item.get("sets"), list) and item["sets"]:
                    proposed_any.add(index)
                if isinstance(item.get("glosses"), str):
                    glosses[index] = item["glosses"]
        judged = {}
        for index, candidate in enumerate(kept):
            if index not in answered:
                continue
            raw_sets = results[index]
            if not raw_sets and index in proposed_any:
                continue
            # Sets below the confidence floor are dropped; a group left with none is a "no".
            sets = [
                proposed for proposed in raw_sets
                if proposed["confidence"] >= settings.TAG_MERGE_MIN_CONFIDENCE
            ]
            if sets:
                judged[candidate.pk] = {
                    "answer": "yes",
                    # A candidate is only as sure as its least sure set.
                    "confidence": min(proposed["confidence"] for proposed in sets),
                    "reason": "",
                    "sets": sets,
                    "glosses": glosses.get(index, ""),
                }
            else:
                reason = "no set proposed"
                if raw_sets:
                    reason = "all proposed sets below the confidence floor"
                judged[candidate.pk] = {
                    "answer": "no",
                    "confidence": 1.0,
                    "reason": reason,
                    "sets": [],
                    "glosses": glosses.get(index, ""),
                }
        return judged

    def verify(self, kept, context, judged, send):
        """Ask the model once more, per call of at most ``verify_sets`` sets, which members of the
        proposed sets really name the canonical concept. It can only remove members."""
        groups, label_maps = context
        # Each proposed "yes" set with its candidate, its member labels and the labelled members.
        proposals = []
        for index, candidate in enumerate(kept):
            judgement = judged.get(candidate.pk)
            if judgement is None or judgement["answer"] != "yes":
                continue
            label_of = {pk: label for label, pk in label_maps[index].items()}
            names = {label: name for label, name, _usage in groups[index]}
            glosses = tms.parse_glosses(judgement["glosses"])
            for proposed in judgement["sets"]:
                labels = [label_of[pk] for pk in proposed["members"]]
                members = [(label, names[label], glosses.get(label, "")) for label in labels]
                proposals.append((candidate.pk, proposed, labels, members))
        if not proposals:
            return judged

        # Sets are numbered across the whole batch, so each reply maps back to one set.
        set_ids = [f"s{number}" for number in range(1, len(proposals) + 1)]
        answers = {}
        for start in range(0, len(proposals), self.verify_sets):
            chunk_ids = set_ids[start:start + self.verify_sets]
            sets = [
                (set_id, proposed["canonical"], members)
                for set_id, (_pk, proposed, _labels, members)
                in zip(chunk_ids, proposals[start:start + self.verify_sets])
            ]
            content, _tokens, _provider, _call = send(
                tms.build_verify_messages(sets), self.verify_schema,
            )
            answers.update(tms.parse_verify_response(content, chunk_ids))

        survivors = {}
        for set_id, (pk, proposed, labels, _members) in zip(set_ids, proposals):
            keep = answers[set_id]
            members = [tag_pk for label, tag_pk in zip(labels, proposed["members"]) if label in keep]
            if len(members) >= 2:
                survivors.setdefault(pk, []).append({**proposed, "members": members})

        for candidate in kept:
            judgement = judged.get(candidate.pk)
            if judgement is None or judgement["answer"] != "yes":
                continue
            sets = survivors.get(candidate.pk, [])
            if sets:
                judged[candidate.pk] = {
                    **judgement,
                    "confidence": min(proposed["confidence"] for proposed in sets),
                    "sets": sets,
                }
            else:
                judged[candidate.pk] = {
                    "answer": "no",
                    "confidence": 1.0,
                    "reason": "verification removed every set",
                    "sets": [],
                    "glosses": judgement["glosses"],
                }
        return judged

    def has_nothing_left(self, candidate, judgement):
        plans, _usage = tms.plan_sets(judgement["sets"])
        return not plans

    def safeguards(self, candidate, judgement):
        plans, usage = tms.plan_sets(judgement["sets"])
        return tms.review_reasons(plans, usage)

    def apply_change(self, candidate, judgement, by_human=False):
        return tms.apply_sets(candidate, check_safeguards=not by_human)


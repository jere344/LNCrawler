"""Author merge: fold one author into another, and undo it.

Mirrors ``merge_service.merge_tags`` and ``undo_tag_merge`` for authors. The
finder (``find_author_candidates``) and the LLM judge (``AuthorMergeTask``) both
call ``merge_authors``, which refuses a merge that would leave an alias name in use.
"""
import hashlib
import logging

from django.db import transaction
from django.utils import timezone

from ..models import Author, AuthorAlias, AuthorMerge, AuthorMergeCandidate, NovelFromSource
from ..utils.author_names import normalize_author
from .merge_service import MergeError

logger = logging.getLogger("lncrawler_api.merge")


class AuthorMergeRefused(MergeError):
    """A merge that stays refused until the data changes: same author, alias name in use."""


def pair_signature(author_ids):
    """Stable hash of a pair of author ids, the same whatever their order."""
    return hashlib.sha1(
        ",".join(str(pk) for pk in sorted(author_ids)).encode()
    ).hexdigest()


def pick_target(a, b):
    """The author with more novel sources survives; a tie keeps the lower pk."""
    return min((a, b), key=lambda author: (-author.novels.count(), author.pk))


def merge_authors(source, target, candidate=None):
    """Fold ``source`` into ``target`` and remember the old name.

    Every novel source credited to the duplicate is credited to the target, and an
    ``AuthorAlias`` records the discarded name so a future import of it resolves
    to the target. The change is stored as an ``AuthorMerge`` so
    ``undo_author_merge`` can reverse it.
    """
    if source.pk == target.pk:
        raise AuthorMergeRefused("An author cannot be merged into itself.")

    with transaction.atomic():
        # Lock both rows before reading links: a concurrent import must not credit
        # new sources to the source author between the read and the delete.
        locked = set(
            Author.objects.select_for_update()
            .filter(pk__in=[source.pk, target.pk])
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        if len(locked) != 2:
            raise MergeError("An author was merged away concurrently; reload and try again.")

        source_name = source.name
        source_pk = source.pk
        # The alias for the old name must be new, so undo can delete it safely.
        if AuthorAlias.objects.filter(name=source_name).exclude(author=source).exists():
            raise AuthorMergeRefused("alias name already in use")
        source_ids = list(source.novels.values_list("pk", flat=True))
        target_ids = set(target.novels.values_list("pk", flat=True))
        moved_alias_ids = list(
            AuthorAlias.objects.filter(author=source).values_list("pk", flat=True)
        )
        AuthorAlias.objects.filter(pk__in=moved_alias_ids).update(author=target)
        target.novels.add(*source_ids)
        source.delete()
        # Pending or waiting pairs that name the source now point at a missing author.
        stale = AuthorMergeCandidate.objects.filter(
            status__in=[AuthorMergeCandidate.STATUS_PENDING, AuthorMergeCandidate.STATUS_REVIEW],
            author_ids__contains=[source_pk],
        )
        if candidate is not None:
            stale = stale.exclude(pk=candidate.pk)
        stale.update(
            status=AuthorMergeCandidate.STATUS_ERROR,
            reason="author merged away",
            updated_at=timezone.now(),
        )
        # Same key as the target: the target already resolves that name, no alias needed.
        alias_created = False
        if normalize_author(source_name) != target.normalized:
            _, alias_created = AuthorAlias.objects.update_or_create(
                name=source_name, defaults={"author": target}
            )
        merge = AuthorMerge.objects.create(
            candidate=candidate,
            source_name=source_name,
            source_id=source_pk,
            target=target,
            target_name=target.name,
            source_ids=source_ids,
            added_source_ids=[pk for pk in source_ids if pk not in target_ids],
            moved_alias_ids=moved_alias_ids,
            alias_created=alias_created,
        )
        if candidate is not None:
            candidate.status = AuthorMergeCandidate.STATUS_APPLIED
            candidate.decided_at = timezone.now()
            candidate.save(update_fields=["status", "decided_at", "updated_at"])

    logger.info("Merged author '%s' into '%s'", source_name, target.name)
    return merge


def undo_author_merge(merge):
    """Reverse one ``AuthorMerge``: recreate the merged-away author and its links."""
    if merge.undone_at is not None:
        raise MergeError("This change was already undone.")
    if merge.target is None:
        # The target was merged away later. Its own merge must be undone first.
        later = (
            AuthorMerge.objects.filter(
                source_name=merge.target_name,
                undone_at__isnull=True,
                created_at__gt=merge.created_at,
            )
            .exclude(pk=merge.pk)
            .order_by("created_at")
            .first()
        )
        if later is not None:
            raise MergeError(
                f"Undo the later merge of '{later.source_name}' into "
                f"'{later.target_name}' (#{later.pk}) first"
            )
        raise MergeError("The target author no longer exists.")

    with transaction.atomic():
        locked = set(
            Author.objects.select_for_update()
            .filter(pk=merge.target_id)
            .values_list("pk", flat=True)
        )
        if merge.target_id not in locked:
            raise MergeError("The target author was merged away; reload and try again.")
        target = merge.target

        if merge.source_id is not None:
            source = Author.objects.create(pk=merge.source_id, name=merge.source_name)
        else:
            source = Author.objects.create(name=merge.source_name)
        # Aliases first, then drop the alias the merge itself created for the old
        # name (an alias that was moved back to the source keeps its row).
        AuthorAlias.objects.filter(pk__in=merge.moved_alias_ids, author=target).update(author=source)
        if merge.alias_created:
            AuthorAlias.objects.filter(name=merge.source_name, author=target).delete()

        # A later merge may have taken this name away (this author was its target).
        # Point those records at the restored author so they can be undone in turn.
        AuthorMerge.objects.filter(
            target__isnull=True, target_name=merge.source_name, undone_at__isnull=True
        ).update(target=source)

        restored = list(
            NovelFromSource.objects.filter(pk__in=merge.source_ids).values_list("pk", flat=True)
        )
        source.novels.add(*restored)
        target.novels.remove(*merge.added_source_ids)

        merge.undone_at = timezone.now()
        merge.save(update_fields=["undone_at"])
        if merge.candidate_id is not None:
            candidate = merge.candidate
            candidate.status = AuthorMergeCandidate.STATUS_UNDONE
            candidate.save(update_fields=["status", "updated_at"])
        else:
            # No row for this pair (admin merge): record it as undone so the finder skips it.
            first, second = sorted((source, target), key=lambda author: author.pk)
            candidate, created = AuthorMergeCandidate.objects.get_or_create(
                signature=pair_signature([first.pk, second.pk]),
                defaults={
                    "author_ids": [first.pk, second.pk],
                    "author_names": [first.name, second.name],
                    "reason": "manual",
                    "status": AuthorMergeCandidate.STATUS_UNDONE,
                },
            )
            if not created:
                candidate.status = AuthorMergeCandidate.STATUS_UNDONE
                candidate.save(update_fields=["status", "updated_at"])

    logger.info("Undid author merge: %s", merge)
    return merge


def merge_candidate(candidate, target=None):
    """Merge the two authors of a candidate and record the outcome on the candidate.

    ``target`` defaults to ``pick_target``. Returns "merged", "rejected" (a refused
    merge: the candidate is rejected) or "error" (a merge error, or an author that no
    longer exists: the candidate is flagged).
    """
    authors = list(Author.objects.filter(pk__in=candidate.author_ids).order_by("pk"))
    if len(authors) != 2:
        candidate.status = AuthorMergeCandidate.STATUS_ERROR
        candidate.reason = "author merged away"
        candidate.save(update_fields=["status", "reason", "updated_at"])
        return "error"
    if target is None:
        target = pick_target(*authors)
    source = next(author for author in authors if author.pk != target.pk)
    try:
        merge_authors(source, target, candidate=candidate)
    except AuthorMergeRefused as exc:
        candidate.signals = {**candidate.signals, "merge_error": str(exc)}
        candidate.status = AuthorMergeCandidate.STATUS_REJECTED
        candidate.decided_at = timezone.now()
        candidate.save(update_fields=["status", "signals", "decided_at", "updated_at"])
        return "rejected"
    except MergeError as exc:
        candidate.signals = {**candidate.signals, "merge_error": str(exc)}
        candidate.status = AuthorMergeCandidate.STATUS_ERROR
        candidate.save(update_fields=["status", "signals", "updated_at"])
        return "error"
    return "merged"

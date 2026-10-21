"""Author blocklist: a blocked author is hidden everywhere and never imported again.

Blocking is a soft delete. The author is unlinked from its sources (the sources
stay), its open merge candidates are rejected, and ``Author.resolve`` refuses its
name, so a re-import leaves it out.
"""
import logging

from django.db import transaction
from django.utils import timezone

from ..models import Author, AuthorMergeCandidate

logger = logging.getLogger("lncrawler_api.merge")


def block_authors(pks):
    """Block the authors in ``pks`` and return how many were blocked."""
    with transaction.atomic():
        authors = list(
            Author.all_objects.select_for_update()
            .filter(pk__in=pks, is_blocked=False)
            .order_by("pk")
        )
        for author in authors:
            author.novels.clear()
            author.is_blocked = True
            author.save(update_fields=["is_blocked"])
        blocked_pks = [author.pk for author in authors]
        for pk in blocked_pks:
            AuthorMergeCandidate.objects.filter(
                status__in=[AuthorMergeCandidate.STATUS_PENDING, AuthorMergeCandidate.STATUS_REVIEW],
                author_ids__contains=[pk],
            ).update(
                status=AuthorMergeCandidate.STATUS_REJECTED,
                reason="author blocked",
                decided_at=timezone.now(),
                updated_at=timezone.now(),
            )

    logger.info("Blocked %d author(s): %s", len(blocked_pks), blocked_pks)
    return len(blocked_pks)


def unblock_authors(pks):
    """Make the blocked authors in ``pks`` visible again and return how many.

    Source links are not restored: they come back when a source is re-imported.
    """
    return Author.all_objects.filter(pk__in=pks, is_blocked=True).update(is_blocked=False)

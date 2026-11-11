"""Keeps a novel folder from moving while a crawl writes into it.

Rule 1: writers never recreate a missing folder (see utils/folders.py), so a process
holding an outdated path fails loudly instead of splitting a novel in two folders.

Rule 2: crawls register, movers lock. A crawl records its novel
in ``Job.novel``. A mover runs inside ``locked_move``, which holds the novel rows
and refuses while a crawl of that novel is active. Only row locks are used: no lock
files, no advisory locks, no marker column.
"""

from contextlib import contextmanager

from django.db import OperationalError, transaction

from ..db_locks import lock_pks
from ..models import Job, Novel

BUSY_MESSAGE = "This novel is busy, try again later."

# A crawl is active from the moment it claims its novel until its download ends.
ACTIVE_CRAWL_STATUSES = (
    Job.STATUS_CREATED,
    Job.STATUS_SEARCHING,
    Job.STATUS_SEARCH_COMPLETED,
    Job.STATUS_DOWNLOADING,
)


class FolderBusy(Exception):
    """The novel folder cannot be moved now: a crawl writes into it, or another move holds it."""

    def __init__(self, message=BUSY_MESSAGE):
        super().__init__(message)


def register_crawl(job, novel):
    """Record ``novel`` as the target of ``job`` so that movers see the crawl.

    Waits for a move that holds the novel row, then sets ``Job.novel``. Returns
    False when the novel no longer exists (it was merged away): the caller
    re-reads where its source lives.
    """
    with transaction.atomic():
        if not lock_pks(Novel, [novel.pk]):
            return False
        job.novel = novel
        job.save(update_fields=["novel", "updated_at"])
    return True


def _novel_pks(novels):
    return sorted({novel.pk for novel in novels if novel is not None and novel.pk is not None})


@contextmanager
def locked(*novels):
    """Hold the rows of ``novels`` (blocking wait) without checking for crawls.

    For work that only adds files inside a novel folder and never moves the folder
    itself, such as a source folder placed in a novel: a crawl writing elsewhere in the
    folder does not conflict with it. Leaving the block commits.

    Raises ``Novel.DoesNotExist`` when one of the novels was deleted (a merge removed it):
    the caller re-reads what it needs.
    """
    pks = _novel_pks(novels)
    with transaction.atomic():
        present = lock_pks(Novel, pks)
        if len(present) != len(pks):
            raise Novel.DoesNotExist(f"Novel(s) {sorted(set(pks) - present)} no longer exist")
        yield


@contextmanager
def locked_move(*novels):
    """Hold the rows of ``novels`` for a folder move, and refuse while a crawl is active on them.

    Raises ``FolderBusy`` at once when a row is locked by another transaction, when a crawl
    of one of the novels is active, or when one of the novels no longer exists (a merge
    removed it: the caller's view is stale, so it retries like a busy novel). Leaving the
    block commits. An exception undoes the database work of the block; the caller keeps its
    disk changes in a ``FileJournal`` opened inside the block, so both sides roll back together.

    The caller re-reads ``novel_path`` after entering: a rename or merge may have run
    before the lock was taken.
    """
    pks = _novel_pks(novels)
    with transaction.atomic():
        try:
            present = lock_pks(Novel, pks, nowait=True)
        except OperationalError as exc:
            # Postgres: 55P03 lock_not_available, a row held by another transaction.
            raise FolderBusy() from exc
        if len(present) != len(pks):
            raise FolderBusy()
        if Job.objects.filter(novel_id__in=pks, status__in=ACTIVE_CRAWL_STATUSES).exists():
            raise FolderBusy()
        yield

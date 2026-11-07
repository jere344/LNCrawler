"""Stored chapter stats on NovelFromSource.

``chapters_count``, ``available_chapters_count`` and the first/latest available
chapter are read by every card, list and sort, so they are kept on the source
row instead of being counted per request. This module is their only writer.
Each writer that changes the chapters of a surviving source calls
``refresh_chapter_stats`` for that source; the hourly scheduler task refreshes
every source as a safety net for a write path that does not.
"""
import logging

from django.db import DatabaseError, connection, transaction

from ..models import Chapter, NovelFromSource

logger = logging.getLogger('lncrawler_api')

DEFAULT_BATCH_SIZE = 500
# How long a batch waits for a row another transaction holds. Short, so the
# scheduler gives up instead of queueing behind a long import.
LOCK_TIMEOUT = '2s'

# The stored columns, for ``refresh_from_db`` on an instance refreshed in place.
STAT_FIELDS = (
    'chapters_count', 'available_chapters_count',
    'first_available_chapter', 'latest_available_chapter',
)


def refresh_chapter_stats_sql(cursor, source_ids=None):
    """Recompute the stat columns of ``source_ids`` (every source when None) in one statement.

    Takes a cursor so a migration can run it on its own connection. The source
    table drives the query, so a source whose chapters were all deleted is
    reset to 0 / NULL. Only rows whose stored values differ are written. Returns
    the number of rows updated.
    """
    source = NovelFromSource._meta.db_table
    chapter = Chapter._meta.db_table
    where = ''
    params = []
    if source_ids is not None:
        where = 'WHERE s2.id = ANY(%s::bigint[])'
        params.append(list(source_ids))

    sql = f"""
        UPDATE {source} s
        SET chapters_count = x.total,
            available_chapters_count = x.available,
            first_available_chapter_id = x.first_id,
            latest_available_chapter_id = x.latest_id
        FROM (
            SELECT s2.id,
                   COALESCE(c.total, 0) AS total,
                   COALESCE(c.available, 0) AS available,
                   f.id AS first_id,
                   l.id AS latest_id
            FROM {source} s2
            LEFT JOIN LATERAL (
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE ch.has_content) AS available
                FROM {chapter} ch
                WHERE ch.novel_from_source_id = s2.id
            ) c ON true
            LEFT JOIN LATERAL (
                SELECT ch.id
                FROM {chapter} ch
                WHERE ch.novel_from_source_id = s2.id AND ch.has_content
                ORDER BY ch.chapter_id
                LIMIT 1
            ) f ON true
            LEFT JOIN LATERAL (
                SELECT ch.id
                FROM {chapter} ch
                WHERE ch.novel_from_source_id = s2.id AND ch.has_content
                ORDER BY ch.chapter_id DESC
                LIMIT 1
            ) l ON true
            {where}
        ) x
        WHERE s.id = x.id
          AND (s.chapters_count, s.available_chapters_count,
               s.first_available_chapter_id, s.latest_available_chapter_id)
              IS DISTINCT FROM (x.total, x.available, x.first_id, x.latest_id)
    """
    cursor.execute(sql, params)
    return cursor.rowcount


def _batches(source_ids, batch_size):
    """Yield source ids in id order, ``batch_size`` at a time.

    Given ids are sorted and sliced. With None the table is walked by id, so
    sources created while the pass runs are picked up too.
    """
    if source_ids is not None:
        ids = sorted(set(source_ids))
        for start in range(0, len(ids), batch_size):
            yield ids[start:start + batch_size]
        return
    table = NovelFromSource._meta.db_table
    last = 0
    while True:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT id FROM {table} WHERE id > %s ORDER BY id LIMIT %s",
                [last, batch_size],
            )
            ids = [row[0] for row in cursor.fetchall()]
        if not ids:
            return
        last = ids[-1]
        yield ids


def refresh_chapter_stats(source_ids=None, *, batch_size=None, skip_locked=False):
    """Refresh the stored chapter stats of ``source_ids`` (every source when None).

    Works in batches of ``batch_size`` sources, id order, each batch its own
    transaction, so a full pass never holds one long lock across the table.
    With ``skip_locked`` a batch first locks its source rows without waiting
    (SKIP LOCKED): a source another transaction is writing is left out, since an
    import refreshes its own source. The statement after that waits at most
    ``LOCK_TIMEOUT``; what it can wait on is the foreign-key key-share check on
    chapter rows, which an import holds while it deletes or reassigns chapters.
    A batch that fails with a DatabaseError (a chapter deleted meanwhile, or the
    timeout) is logged and skipped, and the next batch still runs.
    Returns the number of rows updated.
    """
    batch_size = batch_size or DEFAULT_BATCH_SIZE
    table = NovelFromSource._meta.db_table
    updated = 0
    failed = 0
    for ids in _batches(source_ids, batch_size):
        first_id, last_id = ids[0], ids[-1]
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                if skip_locked:
                    cursor.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
                    cursor.execute(
                        f"SELECT id FROM {table} WHERE id = ANY(%s::bigint[]) "
                        "ORDER BY id FOR UPDATE SKIP LOCKED",
                        [ids],
                    )
                    ids = [row[0] for row in cursor.fetchall()]
                if ids:
                    updated += refresh_chapter_stats_sql(cursor, ids)
        except DatabaseError as error:
            failed += 1
            logger.warning(
                "Chapter stats not refreshed for sources %s to %s: %s",
                first_id, last_id, error,
            )
    if failed:
        logger.warning("Chapter stats refresh skipped %d batch(es)", failed)
    return updated

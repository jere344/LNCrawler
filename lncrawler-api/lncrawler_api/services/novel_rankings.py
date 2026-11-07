"""Projected novel rankings used by search sorts, and the per-name novel counts.

Novel.rank_* columns hold each novel's summed source views, average rating and
latest chapter update. They are refreshed here by the refresh_novel_rankings
scheduler task, so the values can be up to one scheduler interval stale. Tag.novel_count and Author.novel_count are refreshed the same way
by refresh_name_counts, for the autocomplete.
"""
from django.db import connection

from ..models import Author, Novel, NovelFromSource, NovelRating, Tag, WeeklySourceView


def refresh_novel_rankings():
    """Recompute Novel.rank_* in one set-based pass and return rows updated.

    Only rows whose values changed are written (keeps WAL/vacuum churn low).
    """
    novel = Novel._meta.db_table
    source = NovelFromSource._meta.db_table
    views = WeeklySourceView._meta.db_table
    rating = NovelRating._meta.db_table

    sql = f"""
        UPDATE {novel} n
        SET rank_total_views = x.tv,
            rank_week_views = x.wv,
            rank_avg_rating = x.ar,
            rank_last_update = x.lu
        FROM (
            SELECT n2.id,
                   COALESCE(s.tv, 0) AS tv,
                   COALESCE(w.wv, 0) AS wv,
                   COALESCE(r.ar, 0) AS ar,
                   s.lu AS lu
            FROM {novel} n2
            LEFT JOIN (
                SELECT novel_id, SUM(total_views) AS tv, MAX(last_chapter_update) AS lu
                FROM {source}
                GROUP BY novel_id
            ) s ON s.novel_id = n2.id
            LEFT JOIN (
                SELECT src.novel_id, SUM(v.views) AS wv
                FROM {views} v
                JOIN {source} src ON src.id = v.source_id
                WHERE v.granularity = %s AND v.day >= %s
                GROUP BY src.novel_id
            ) w ON w.novel_id = n2.id
            LEFT JOIN (
                SELECT novel_id, AVG(rating) AS ar
                FROM {rating}
                GROUP BY novel_id
            ) r ON r.novel_id = n2.id
        ) x
        WHERE n.id = x.id
          AND (n.rank_total_views, n.rank_week_views, n.rank_avg_rating, n.rank_last_update)
              IS DISTINCT FROM (x.tv, x.wv, x.ar, x.lu)
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [WeeklySourceView.DAY, WeeklySourceView.window_start()])
        return cursor.rowcount


def refresh_name_counts():
    """Recompute Tag.novel_count and Author.novel_count, return rows updated.

    A count is the number of distinct novels with a source carrying the tag or
    author. It is not adult or DMCA filtered, and blocked authors are counted too
    (autocomplete hides them). Counts lag up to one refresh: tag merges, imports and
    other link changes show in the counts only after the next run, which the
    refresh_novel_rankings scheduler task does every 5 minutes. Names going to zero
    novels are set to 0. Only rows whose count changed are written.
    """
    source = NovelFromSource._meta.db_table
    tag_updated = _refresh_name_count(
        Tag._meta.db_table, NovelFromSource.tags.through._meta.db_table, "tag_id", source,
    )
    author_updated = _refresh_name_count(
        Author._meta.db_table, NovelFromSource.authors.through._meta.db_table, "author_id", source,
    )
    return tag_updated + author_updated


def _refresh_name_count(table, link, column, source):
    sql = f"""
        UPDATE {table} t
        SET novel_count = x.cnt
        FROM (
            SELECT t2.id, COALESCE(c.cnt, 0) AS cnt
            FROM {table} t2
            LEFT JOIN (
                SELECT l.{column} AS id, COUNT(DISTINCT s.novel_id) AS cnt
                FROM {link} l
                JOIN {source} s ON s.id = l.novelfromsource_id
                GROUP BY l.{column}
            ) c ON c.id = t2.id
        ) x
        WHERE t.id = x.id
          AND t.novel_count IS DISTINCT FROM x.cnt
    """
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.rowcount

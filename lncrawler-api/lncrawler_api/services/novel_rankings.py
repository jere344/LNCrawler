"""Projected novel rankings used by search sorts.

Novel.rank_* columns hold the sums and average that search used to aggregate
on every request. They are refreshed here by the refresh_novel_rankings
scheduler task, so the values can be up to one scheduler interval stale.
"""
from django.db import connection

from ..models import Novel, NovelFromSource, NovelRating, WeeklySourceView


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
            rank_avg_rating = x.ar
        FROM (
            SELECT n2.id,
                   COALESCE(s.tv, 0) AS tv,
                   COALESCE(w.wv, 0) AS wv,
                   COALESCE(r.ar, 0) AS ar
            FROM {novel} n2
            LEFT JOIN (
                SELECT novel_id, SUM(total_views) AS tv
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
          AND (n.rank_total_views, n.rank_week_views, n.rank_avg_rating)
              IS DISTINCT FROM (x.tv, x.wv, x.ar)
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [WeeklySourceView.DAY, WeeklySourceView.window_start()])
        return cursor.rowcount

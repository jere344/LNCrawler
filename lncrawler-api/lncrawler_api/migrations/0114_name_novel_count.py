"""Store the number of novels per tag and per author for autocomplete.

Tag.novel_count and Author.novel_count are the distinct novels with a source
carrying the tag or author. They are refreshed by the refresh_name_counts
scheduler task, so the values can be up to one scheduler interval stale. The
backfill is one UPDATE per table with the same aggregate, so the migration does
not import the app. Names without any novel stay at 0. Reversing the backfill is
a no-op; the columns themselves are dropped by the reverse of AddField.
"""
from django.db import migrations, models

BACKFILL_TAG_SQL = """
    UPDATE lncrawler_api_tag t
    SET novel_count = x.cnt
    FROM (
        SELECT t2.id, COALESCE(c.cnt, 0) AS cnt
        FROM lncrawler_api_tag t2
        LEFT JOIN (
            SELECT l.tag_id, COUNT(DISTINCT s.novel_id) AS cnt
            FROM lncrawler_api_novelfromsource_tags l
            JOIN lncrawler_api_novelfromsource s ON s.id = l.novelfromsource_id
            GROUP BY l.tag_id
        ) c ON c.tag_id = t2.id
    ) x
    WHERE t.id = x.id
      AND t.novel_count IS DISTINCT FROM x.cnt
"""

BACKFILL_AUTHOR_SQL = """
    UPDATE lncrawler_api_author a
    SET novel_count = x.cnt
    FROM (
        SELECT a2.id, COALESCE(c.cnt, 0) AS cnt
        FROM lncrawler_api_author a2
        LEFT JOIN (
            SELECT l.author_id, COUNT(DISTINCT s.novel_id) AS cnt
            FROM lncrawler_api_novelfromsource_authors l
            JOIN lncrawler_api_novelfromsource s ON s.id = l.novelfromsource_id
            GROUP BY l.author_id
        ) c ON c.author_id = a2.id
    ) x
    WHERE a.id = x.id
      AND a.novel_count IS DISTINCT FROM x.cnt
"""


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0113_novel_rank_last_update'),
    ]

    operations = [
        migrations.AddField(
            model_name='tag',
            name='novel_count',
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
        migrations.AddField(
            model_name='author',
            name='novel_count',
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
        migrations.RunSQL(
            sql=BACKFILL_TAG_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=BACKFILL_AUTHOR_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

"""Store the most recent source update of a novel for the last_updated search sort.

rank_last_update = MAX(sources.last_chapter_update) per novel, refreshed by the
refresh_novel_rankings scheduler task. The backfill is one UPDATE with the same
aggregate, so the migration does not import the app. Novels without any updated
source stay NULL. Reversing the backfill is a no-op; the column itself is dropped
by the reverse of AddField.
"""
from django.db import migrations, models

BACKFILL_SQL = """
    UPDATE lncrawler_api_novel n
    SET rank_last_update = x.last_update
    FROM (
        SELECT s.novel_id, MAX(s.last_chapter_update) AS last_update
        FROM lncrawler_api_novelfromsource s
        GROUP BY s.novel_id
    ) x
    WHERE n.id = x.novel_id
      AND n.rank_last_update IS DISTINCT FROM x.last_update
"""


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0112_novel_is_adult'),
    ]

    operations = [
        migrations.AddField(
            model_name='novel',
            name='rank_last_update',
            field=models.DateTimeField(editable=False, null=True),
        ),
        migrations.RunSQL(
            sql=BACKFILL_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

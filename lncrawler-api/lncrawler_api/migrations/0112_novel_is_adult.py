"""Store the adult flag of a novel: adult when more than half of its sources are.

The backfill is one UPDATE with the majority rule written out, so the migration
does not import the app (the rule itself lives in refresh_novel_adult). Only the
adult novels need a write: the column starts at False. Reversing the backfill is
a no-op; the column itself is dropped by the reverse of AddField.
"""
from django.db import migrations, models

BACKFILL_SQL = """
    UPDATE lncrawler_api_novel n
    SET is_adult = TRUE
    WHERE n.id IN (
        SELECT s.novel_id
        FROM lncrawler_api_novelfromsource s
        GROUP BY s.novel_id
        HAVING count(*) < 2 * count(*) FILTER (WHERE s.is_adult)
    )
"""


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0111_remove_part_leases'),
    ]

    operations = [
        migrations.AddField(
            model_name='novel',
            name='is_adult',
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.RunSQL(
            sql=BACKFILL_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

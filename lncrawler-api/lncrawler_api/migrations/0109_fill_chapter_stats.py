"""Fill the chapter stat columns of NovelFromSource from its chapters.

Not atomic, and batched: each batch of sources is its own statement, committed
on its own, so the fill does not hold row locks on the whole source table, and
imports can run in between batches. The SQL is frozen here (table names
written out, no import from the app), so a later change to the service cannot
rewrite what this migration did. Running it again writes nothing when the stats
are already right. Reversing is a no-op: the columns are dropped by 0108.
"""
from django.db import migrations

BATCH_SIZE = 500

FILL_SQL = """
    UPDATE lncrawler_api_novelfromsource s
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
        FROM lncrawler_api_novelfromsource s2
        LEFT JOIN LATERAL (
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE ch.has_content) AS available
            FROM lncrawler_api_chapter ch
            WHERE ch.novel_from_source_id = s2.id
        ) c ON true
        LEFT JOIN LATERAL (
            SELECT ch.id
            FROM lncrawler_api_chapter ch
            WHERE ch.novel_from_source_id = s2.id AND ch.has_content
            ORDER BY ch.chapter_id
            LIMIT 1
        ) f ON true
        LEFT JOIN LATERAL (
            SELECT ch.id
            FROM lncrawler_api_chapter ch
            WHERE ch.novel_from_source_id = s2.id AND ch.has_content
            ORDER BY ch.chapter_id DESC
            LIMIT 1
        ) l ON true
        WHERE s2.id = ANY(%s::bigint[])
    ) x
    WHERE s.id = x.id
      AND (s.chapters_count, s.available_chapters_count,
           s.first_available_chapter_id, s.latest_available_chapter_id)
          IS DISTINCT FROM (x.total, x.available, x.first_id, x.latest_id)
"""


def fill_chapter_stats(apps, schema_editor):
    last_id = 0
    with schema_editor.connection.cursor() as cursor:
        while True:
            cursor.execute(
                "SELECT id FROM lncrawler_api_novelfromsource WHERE id > %s ORDER BY id LIMIT %s",
                [last_id, BATCH_SIZE],
            )
            ids = [row[0] for row in cursor.fetchall()]
            if not ids:
                return
            cursor.execute(FILL_SQL, [ids])
            last_id = ids[-1]


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('lncrawler_api', '0108_novelfromsource_chapter_stats'),
    ]

    operations = [
        migrations.RunPython(fill_chapter_stats, migrations.RunPython.noop),
    ]

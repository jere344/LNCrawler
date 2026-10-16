from django.db import migrations


class Migration(migrations.Migration):
    """Keep the high-churn tables compact.

    ``chapter`` (bulk-inserted/updated by the crawler) and
    ``weeklysourceview`` (written on every chapter read) accumulate dead
    tuples far faster than the default 20% scale factor reclaims them. A
    bloated heap silently breaks index-only scans (every index lookup becomes
    a heap fetch), which is what made the source prefetch ~150x slower on
    prod. Tighter autovacuum thresholds keep the visibility map fresh.
    """

    dependencies = [
        ('lncrawler_api', '0053_novel_is_dmca'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE lncrawler_api_chapter SET ("
                "autovacuum_vacuum_scale_factor = 0.02, "
                "autovacuum_analyze_scale_factor = 0.01, "
                "autovacuum_vacuum_insert_scale_factor = 0.05);",
                "ALTER TABLE lncrawler_api_weeklysourceview SET ("
                "autovacuum_vacuum_scale_factor = 0.02, "
                "autovacuum_analyze_scale_factor = 0.01);",
            ],
            reverse_sql=[
                "ALTER TABLE lncrawler_api_chapter RESET ("
                "autovacuum_vacuum_scale_factor, autovacuum_analyze_scale_factor, "
                "autovacuum_vacuum_insert_scale_factor);",
                "ALTER TABLE lncrawler_api_weeklysourceview RESET ("
                "autovacuum_vacuum_scale_factor, autovacuum_analyze_scale_factor);",
            ],
        ),
    ]

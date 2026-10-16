"""Add projected ranking columns to Novel and index them for search sorts.

rank_total_views, rank_week_views and rank_avg_rating are refreshed by the
refresh_novel_rankings scheduler task, so search can order by an index instead
of aggregating every novel's sources, weekly views and ratings per request.
No data migration: the task runs when it is first due and backfills the values.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0081_chapter_covering_unique_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='novel',
            name='rank_total_views',
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='novel',
            name='rank_week_views',
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='novel',
            name='rank_avg_rating',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddIndex(
            model_name='novel',
            index=models.Index(fields=['-rank_total_views', 'title'], name='novel_rank_views_idx'),
        ),
        migrations.AddIndex(
            model_name='novel',
            index=models.Index(fields=['-rank_week_views', 'title'], name='novel_rank_week_idx'),
        ),
        migrations.AddIndex(
            model_name='novel',
            index=models.Index(fields=['-rank_avg_rating', 'title'], name='novel_rank_rating_idx'),
        ),
    ]

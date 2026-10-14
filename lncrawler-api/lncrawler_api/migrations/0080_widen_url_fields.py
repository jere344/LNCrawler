"""Widen URL columns to 2048 so long scraped novel URLs are stored, not dropped.

HarvestCandidate.novel_url and Job.target_url were varchar(512). A longer URL
from a harvest scan made the bulk insert fail and aborted the whole scan.
Growing a varchar in Postgres does not rewrite the table.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0079_requeue_llm_failed_tag_clusters'),
    ]

    operations = [
        migrations.AlterField(
            model_name='harvestcandidate',
            name='novel_url',
            field=models.CharField(max_length=2048, unique=True),
        ),
        migrations.AlterField(
            model_name='job',
            name='target_url',
            field=models.CharField(blank=True, max_length=2048, null=True),
        ),
    ]

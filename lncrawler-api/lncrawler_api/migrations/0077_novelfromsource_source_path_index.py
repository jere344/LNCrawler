"""Index ``NovelFromSource.source_path``: folder ownership is looked up by path."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0076_backfill_novelfromsource_edition'),
    ]

    operations = [
        migrations.AlterField(
            model_name='novelfromsource',
            name='source_path',
            field=models.CharField(blank=True, db_index=True, max_length=500, null=True),
        ),
    ]

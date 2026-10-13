"""Add a free-form ``edition`` to sources.

The crawler now supplies the edition in meta.json. The rows imported before
that are backfilled from their title markers in 0076, which runs in its own
transaction (see 0073 for why schema and data steps are separate).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0074_unique_source_slug_per_novel_constraint'),
    ]

    operations = [
        migrations.AddField(
            model_name='novelfromsource',
            name='edition',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
    ]

"""Add the R18 flag to Tag.

Novels are flagged adult from tags by the import path, the admin and the
recompute_adult command; no data migration is needed here.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0082_novel_rank_columns'),
    ]

    operations = [
        migrations.AddField(
            model_name='tag',
            name='is_adult',
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]

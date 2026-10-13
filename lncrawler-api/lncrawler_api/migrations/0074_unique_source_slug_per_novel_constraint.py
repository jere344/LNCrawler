"""Add the per-novel unique constraint on ``source_slug``.

Runs after 0073 renamed any duplicate slugs. See 0073 for why this is a separate
migration.
"""
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0073_unique_source_slug_per_novel'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='novelfromsource',
            constraint=models.UniqueConstraint(
                condition=~Q(source_slug=''),
                fields=('novel', 'source_slug'),
                name='unique_source_slug_per_novel',
            ),
        ),
    ]

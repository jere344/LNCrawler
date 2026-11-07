"""Drop the part lease: a claim no longer expires, so the claim index no longer covers lease_until."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0110_simplify_audiobooks'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='audiobookpart',
            name='audiobook_part_claim_idx',
        ),
        migrations.AddIndex(
            model_name='audiobookpart',
            index=models.Index(fields=['status', '-priority'], name='audiobook_part_claim_idx'),
        ),
        migrations.RemoveField(
            model_name='audiobookpart',
            name='lease_until',
        ),
    ]

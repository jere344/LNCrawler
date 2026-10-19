"""Backfill ``Author.normalized`` for authors created before the field existed.

The key logic is copied here on purpose: a migration must not import app code
that may change after it was written. It must match ``utils/author_names.py``.
"""
import unicodedata

from django.db import migrations

BATCH_SIZE = 1000
_EDGE_CHARS = " !\"#$%&'*+,-./:;=?@\\^_`|~·・。，、；：！？…“”‘’—–"


def _normalize(name):
    text = " ".join(unicodedata.normalize("NFKC", name or "").casefold().split())
    return text.strip(_EDGE_CHARS)[:255]


def backfill_normalized(apps, schema_editor):
    Author = apps.get_model("lncrawler_api", "Author")

    last_pk = 0
    while True:
        batch = list(
            Author.objects.filter(pk__gt=last_pk).order_by("pk").only("id", "name")[:BATCH_SIZE]
        )
        if not batch:
            break
        for author in batch:
            author.normalized = _normalize(author.name)
        Author.objects.bulk_update(batch, ["normalized"], batch_size=BATCH_SIZE)
        last_pk = batch[-1].pk


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0089_author_merge'),
    ]

    operations = [
        migrations.RunPython(backfill_normalized, migrations.RunPython.noop),
    ]

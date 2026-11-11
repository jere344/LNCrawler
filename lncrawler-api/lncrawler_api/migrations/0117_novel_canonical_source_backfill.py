"""Set Novel.canonical_source from the source ranking, and delete novels that have no source.

The ranking is copied inline (migrations never import app code). It matches
services/novel_naming.choose_canonical with NAMING_LANGUAGE 'en'. Sources
imported before the blank-language fix carry '' and are set to 'en' first, as
import now does. Novels without a source go first, with their user data (the
cascade); reversing is a no-op, so the deleted rows are not restored.
"""
import logging
from itertools import groupby
from operator import itemgetter

from django.db import migrations

logger = logging.getLogger('lncrawler_api')

BATCH_SIZE = 1000
SHOWN_PKS = 50


def _rank(row):
    """Ranking key of a (source_id, novel_id, language, upvotes, downvotes, chapters, title) row."""
    _, _, language, upvotes, downvotes, chapters, title = row
    tier = 0 if language == 'en' else 1
    return (tier, -(upvotes - downvotes), -upvotes, -chapters, title)


def set_canonical_sources(apps, schema_editor):
    Novel = apps.get_model('lncrawler_api', 'Novel')
    NovelFromSource = apps.get_model('lncrawler_api', 'NovelFromSource')

    orphans = Novel.objects.exclude(pk__in=NovelFromSource.objects.values('novel_id'))
    orphan_count = orphans.count()
    if orphan_count:
        logger.warning(
            "Deleting %s novel(s) without a source, first pks: %s",
            orphan_count, list(orphans.order_by('pk').values_list('pk', flat=True)[:SHOWN_PKS]),
        )
    orphans.delete()
    NovelFromSource.objects.filter(language='').update(language='en')

    rows = (
        NovelFromSource.objects.order_by('novel_id')
        .values_list('pk', 'novel_id', 'language', 'upvotes', 'downvotes', 'available_chapters_count', 'title')
        .iterator(chunk_size=5000)
    )
    novels = [
        Novel(pk=novel_id, canonical_source_id=min(group, key=_rank)[0])
        for novel_id, group in groupby(rows, key=itemgetter(1))
    ]
    Novel.objects.bulk_update(novels, ['canonical_source'], batch_size=BATCH_SIZE)


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0116_novel_canonical_source'),
    ]

    operations = [
        migrations.RunPython(set_canonical_sources, migrations.RunPython.noop),
    ]

"""Data step for the per-novel unique source slug.

Renames duplicate ``(novel, source_slug)`` pairs so the unique constraint can be
added. The constraint itself is added in 0074. The two steps are separate
migrations on purpose: on PostgreSQL, a schema change (``ALTER TABLE``) in the
same transaction as the row updates above can fail with "pending trigger
events", so each step runs in its own transaction.

Reversing is a no-op: the renamed slugs are not restored to their old values,
and nothing needs undoing here because reversing 0074 already drops the
constraint. The renamed slugs are harmless to keep.
"""
from django.db import migrations


def rename_duplicate_slugs(apps, schema_editor):
    """Give every duplicate (novel, source_slug) a suffix; the oldest keeps its slug.

    The unique constraint below cannot be added while duplicates exist. Models
    are read from the migration state, so this does not depend on app code.
    """
    NovelFromSource = apps.get_model('lncrawler_api', 'NovelFromSource')

    taken = {}
    for novel_id, slug in NovelFromSource.objects.values_list('novel_id', 'source_slug'):
        taken.setdefault(novel_id, set()).add(slug)

    groups = {}
    rows = (
        NovelFromSource.objects.exclude(source_slug='')
        .order_by('created_at', 'pk')
        .values_list('pk', 'novel_id', 'source_slug')
    )
    for pk, novel_id, slug in rows:
        groups.setdefault((novel_id, slug), []).append(pk)

    for (novel_id, slug), pks in groups.items():
        for pk in pks[1:]:
            n = 2
            while True:
                suffix = f'-{n}'
                candidate = slug[:100 - len(suffix)] + suffix
                if candidate not in taken[novel_id]:
                    break
                n += 1
            taken[novel_id].add(candidate)
            NovelFromSource.objects.filter(pk=pk).update(source_slug=candidate)


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0072_tag_llm_call_and_requeue'),
    ]

    operations = [
        migrations.RunPython(rename_duplicate_slugs, migrations.RunPython.noop),
    ]

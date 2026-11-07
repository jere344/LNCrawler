"""Drop the audiobook publish, feature, cast and approval flags. A book is public when it is not retired and has a
listenable part, and first_published_at is set from the first completed part where it is missing."""
from django.db import migrations
from django.db.models import Min, OuterRef, Subquery


def fill_first_published_at(apps, schema_editor):
    Audiobook = apps.get_model('lncrawler_api', 'Audiobook')
    AudiobookPart = apps.get_model('lncrawler_api', 'AudiobookPart')
    first_done = (
        AudiobookPart.objects.filter(audiobook=OuterRef('pk'), status__in=['done', 'stale'])
        .order_by()
        .values('audiobook')
        .annotate(first=Min('completed_at'))
        .values('first')[:1]
    )
    Audiobook.objects.filter(first_published_at__isnull=True).update(first_published_at=Subquery(first_done))


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0109_fill_chapter_stats'),
    ]

    operations = [
        migrations.RunPython(fill_first_published_at, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='audiobook',
            name='published',
        ),
        migrations.RemoveField(
            model_name='audiobook',
            name='featured',
        ),
        migrations.RemoveField(
            model_name='audiobook',
            name='cast',
        ),
        migrations.RemoveField(
            model_name='audiobookpart',
            name='cast',
        ),
        migrations.RemoveField(
            model_name='audiobookpart',
            name='approved',
        ),
    ]

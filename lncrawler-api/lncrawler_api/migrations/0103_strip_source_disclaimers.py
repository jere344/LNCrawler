"""Remove the "Disclaimer" paragraphs that wuxiaworld.site synopses carry, from the synopses already stored."""
import re

from django.db import migrations

DISCLAIMER_PARAGRAPH = re.compile(
    r'<p>\s*(?:<strong>|<b>)?\s*Disclaimer\s*(?:</strong>|</b>)?\s*:.*?</p>', re.I | re.S,
)


def strip_disclaimers(synopsis):
    """The synopsis without its disclaimer paragraphs."""
    return DISCLAIMER_PARAGRAPH.sub('', synopsis).strip()


def forwards(apps, schema_editor):
    NovelFromSource = apps.get_model('lncrawler_api', 'NovelFromSource')
    rows = NovelFromSource.objects.filter(synopsis__icontains='Disclaimer')
    for source in rows.iterator():
        source.synopsis = strip_disclaimers(source.synopsis)
        source.save(update_fields=['synopsis'])


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0102_worker_languages'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

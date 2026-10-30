"""Reset the word counts of Chinese and Japanese chapters: they are counted by character now, so they are recounted lazily."""
from django.db import migrations


def forwards(apps, schema_editor):
    Chapter = apps.get_model('lncrawler_api', 'Chapter')
    Chapter.objects.filter(novel_from_source__language__in=['zh', 'ja']).exclude(word_count=None).update(word_count=None)


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0104_remove_engine_profiles'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

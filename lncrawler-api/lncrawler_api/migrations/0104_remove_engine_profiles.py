from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0103_strip_source_disclaimers'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='audiobook',
            name='engine_profile',
        ),
        migrations.RemoveField(
            model_name='audiobookpart',
            name='engine_profile',
        ),
        migrations.RemoveField(
            model_name='audiobookworker',
            name='engine_profiles',
        ),
    ]

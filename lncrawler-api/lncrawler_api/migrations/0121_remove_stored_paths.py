"""Drop the stored full paths and make Novel.novel_path required.

0120 has filled every new field and every novel_path, so this only changes the schema.
Its own transaction, apart from the data migration.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0120_split_stored_paths'),
    ]

    operations = [
        migrations.AlterField(
            model_name='novel',
            name='novel_path',
            field=models.CharField(max_length=500),
        ),
        migrations.RemoveField(
            model_name='novelfromsource',
            name='source_path',
        ),
        migrations.RemoveField(
            model_name='novelfromsource',
            name='cover_path',
        ),
        migrations.RemoveField(
            model_name='novelfromsource',
            name='cover_min_path',
        ),
        migrations.RemoveField(
            model_name='novelfromsource',
            name='overview_picture_path',
        ),
        migrations.RemoveField(
            model_name='novelfromsource',
            name='meta_file_path',
        ),
        migrations.RemoveField(
            model_name='audiobook',
            name='cover_path',
        ),
        # Give the field a default first, so reversing the removal can add it to a table with rows.
        migrations.AlterField(
            model_name='audiobookchapter',
            name='file_path',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.RemoveField(
            model_name='audiobookchapter',
            name='file_path',
        ),
    ]

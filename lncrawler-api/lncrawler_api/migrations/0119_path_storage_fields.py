"""Add the relative path fields. 0120 fills them, 0121 drops the old ones."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0118_drop_novel_title'),
    ]

    operations = [
        migrations.AddField(
            model_name='novelfromsource',
            name='source_folder',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='novelfromsource',
            name='cover_file',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='novelfromsource',
            name='cover_min_file',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='novelfromsource',
            name='overview_picture_file',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='audiobook',
            name='cover_file',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='audiobookchapter',
            name='file_in_source',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
    ]

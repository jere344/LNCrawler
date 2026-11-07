"""Add the chapter stat columns to NovelFromSource. They are filled by 0109."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0107_readersettingsslot'),
    ]

    operations = [
        migrations.AddField(
            model_name='novelfromsource',
            name='available_chapters_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='novelfromsource',
            name='chapters_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='novelfromsource',
            name='first_available_chapter',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='lncrawler_api.chapter'),
        ),
        migrations.AddField(
            model_name='novelfromsource',
            name='latest_available_chapter',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='lncrawler_api.chapter'),
        ),
    ]

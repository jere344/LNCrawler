"""Reading history points at where the user is: the chapter being read and the position inside it.

``last_read_chapter`` becomes ``current_chapter``. Existing rows meant "finished that chapter", so they
get position 1 (the end) and Continue keeps going to the next chapter. New rows default to 0 (the top).
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0114_name_novel_count'),
    ]

    operations = [
        migrations.RenameField(
            model_name='readinghistory',
            old_name='last_read_chapter',
            new_name='current_chapter',
        ),
        migrations.AlterField(
            model_name='readinghistory',
            name='current_chapter',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='current_readers', to='lncrawler_api.chapter'),
        ),
        migrations.AddField(
            model_name='readinghistory',
            name='position',
            field=models.FloatField(default=1),
        ),
        migrations.AlterField(
            model_name='readinghistory',
            name='position',
            field=models.FloatField(default=0),
        ),
    ]

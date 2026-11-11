"""Index Novel.novel_path: the folder-owner lookups of the source paths filter on it."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0121_remove_stored_paths'),
    ]

    operations = [
        migrations.AlterField(
            model_name='novel',
            name='novel_path',
            field=models.CharField(db_index=True, max_length=500),
        ),
    ]

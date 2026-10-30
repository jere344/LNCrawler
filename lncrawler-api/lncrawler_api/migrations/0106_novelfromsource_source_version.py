from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0105_recount_cjk_word_counts'),
    ]

    operations = [
        migrations.AddField(
            model_name='novelfromsource',
            name='source_version',
            field=models.PositiveIntegerField(default=1),
        ),
    ]

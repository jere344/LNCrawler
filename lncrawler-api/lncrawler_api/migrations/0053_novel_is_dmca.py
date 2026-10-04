from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0052_friendship_unique_pair'),
    ]

    operations = [
        migrations.AddField(
            model_name='novel',
            name='is_dmca',
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]

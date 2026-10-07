from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0061_job_job_claim_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='novelfromsource',
            name='is_adult',
            field=models.BooleanField(default=False),
        ),
    ]

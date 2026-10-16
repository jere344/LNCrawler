from django.db import migrations, models


class Migration(migrations.Migration):
    """Track how many times a job has been retried after a crash/stall.

    The crawler supervisor requeues a job whose process died or whose row went
    stale, so a permanently broken job must not loop forever.
    """

    dependencies = [
        ('lncrawler_api', '0054_tune_autovacuum'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='retry_count',
            field=models.PositiveIntegerField(default=0),
        ),
    ]

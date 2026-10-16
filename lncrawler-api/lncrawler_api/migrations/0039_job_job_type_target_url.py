from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lncrawler_api", "0038_scheduledtask"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="job_type",
            field=models.CharField(
                choices=[("search", "Search"), ("download", "Download")],
                default="search",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="target_url",
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lncrawler_api", "0039_job_job_type_target_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="progress_unit",
            field=models.CharField(default="chapters", max_length=20),
        ),
    ]

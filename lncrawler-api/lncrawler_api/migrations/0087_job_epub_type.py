from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lncrawler_api", "0086_novelfromsource_adult_from_source"),
    ]

    operations = [
        migrations.AlterField(
            model_name="job",
            name="job_type",
            field=models.CharField(
                choices=[
                    ("search", "Search"),
                    ("download", "Download"),
                    ("epub", "EPUB"),
                ],
                default="search",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="job",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("job_type", "epub"),
                    ("status__in", ["created", "downloading"]),
                ),
                fields=("query",),
                name="job_unique_active_epub",
            ),
        ),
    ]

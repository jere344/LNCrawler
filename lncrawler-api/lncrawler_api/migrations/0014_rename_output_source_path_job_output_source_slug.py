# Generated by Django 5.2.1 on 2025-05-13 11:42

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("lncrawler_api", "0013_rename_output_novel_url_job_output_source_path"),
    ]

    operations = [
        migrations.RenameField(
            model_name="job",
            old_name="output_source_path",
            new_name="output_source_slug",
        ),
    ]

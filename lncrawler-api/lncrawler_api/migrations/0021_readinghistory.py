# Generated by Django 5.2.1 on 2025-05-20 07:22

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lncrawler_api", "0020_novel_comment_count"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReadingHistory",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("last_read_at", models.DateTimeField(auto_now=True)),
                (
                    "last_read_chapter",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="last_read_by_users",
                        to="lncrawler_api.chapter",
                    ),
                ),
                (
                    "novel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reading_histories",
                        to="lncrawler_api.novel",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="read_by_users",
                        to="lncrawler_api.novelfromsource",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reading_histories",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Reading novel histories",
                "ordering": ["-last_read_at"],
                "unique_together": {("user", "novel")},
            },
        ),
    ]

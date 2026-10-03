from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auth_app", "0006_customuser_word_read"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="preferred_ui_language",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
        migrations.AddField(
            model_name="customuser",
            name="preferred_languages",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="customuser",
            name="language_filter_enabled",
            field=models.BooleanField(default=True),
        ),
    ]

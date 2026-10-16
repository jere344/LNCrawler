from django.db import migrations, models


def clear_weekly_views(apps, schema_editor):
    # Per-week buckets cannot be mapped cleanly onto per-day buckets, so the
    # old rolling-window counts are dropped. Total all-time views are unaffected.
    WeeklyNovelView = apps.get_model("lncrawler_api", "WeeklyNovelView")
    WeeklyNovelView.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("lncrawler_api", "0042_remove_chapter_word_count_alter_chapter_images_and_more"),
    ]

    operations = [
        migrations.RunPython(clear_weekly_views, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name="weeklynovelview",
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name="weeklynovelview",
            name="year_week",
        ),
        migrations.AddField(
            model_name="weeklynovelview",
            name="day",
            field=models.DateField(null=True),
        ),
        migrations.AddField(
            model_name="weeklynovelview",
            name="granularity",
            field=models.CharField(
                choices=[("day", "day"), ("week", "week")],
                default="day",
                max_length=4,
            ),
        ),
        migrations.AlterField(
            model_name="weeklynovelview",
            name="day",
            field=models.DateField(),
        ),
        migrations.AlterUniqueTogether(
            name="weeklynovelview",
            unique_together={("novel", "granularity", "day")},
        ),
    ]
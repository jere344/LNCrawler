from django.db import migrations


def delete_task_row(apps, schema_editor):
    ScheduledTask = apps.get_model('lncrawler_api', 'ScheduledTask')
    ScheduledTask.objects.filter(name='update_popular_sources').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0123_job_novel'),
    ]

    operations = [
        migrations.RunPython(delete_task_row, migrations.RunPython.noop),
    ]

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0062_novelfromsource_is_adult'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='novelfromsource',
            name='is_rtl',
        ),
        migrations.RemoveField(
            model_name='novelfromsource',
            name='has_manga',
        ),
        migrations.RemoveField(
            model_name='novelfromsource',
            name='has_mtl',
        ),
    ]

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0106_novelfromsource_source_version'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ReaderSettingsSlot',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('slot', models.CharField(choices=[('mobile', 'Mobile'), ('desktop', 'Desktop')], max_length=16)),
                ('data', models.JSONField(default=dict)),
                ('schema_version', models.PositiveIntegerField(default=1)),
                ('revision', models.PositiveIntegerField(default=1)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reader_settings_slots', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('user', 'slot')},
            },
        ),
    ]

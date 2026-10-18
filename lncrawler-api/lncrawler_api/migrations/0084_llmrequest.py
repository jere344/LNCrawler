"""Shared LLM request queue and log, plus the R18 usage purpose."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0083_tag_is_adult'),
    ]

    operations = [
        migrations.CreateModel(
            name='LLMRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task', models.CharField(db_index=True, max_length=50)),
                ('target_type', models.CharField(max_length=50)),
                ('target_ids', models.JSONField(default=list)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('done', 'Done'), ('failed', 'Failed')], db_index=True, default='pending', max_length=10)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('not_before', models.DateTimeField(blank=True, null=True)),
                ('model', models.CharField(blank=True, default='', max_length=100)),
                ('prompt_version', models.CharField(max_length=20)),
                ('response', models.JSONField(blank=True, null=True)),
                ('raw_response', models.TextField(blank=True, default='')),
                ('error', models.TextField(blank=True, default='')),
                ('tokens', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['task', 'status', 'not_before'], name='llmrequest_queue_idx')],
            },
        ),
        migrations.AlterField(
            model_name='llmusage',
            name='purpose',
            field=models.CharField(choices=[('novel', 'Novel judge'), ('tag', 'Tag judge'), ('tag_r18', 'Tag R18 classifier')], max_length=10),
        ),
    ]

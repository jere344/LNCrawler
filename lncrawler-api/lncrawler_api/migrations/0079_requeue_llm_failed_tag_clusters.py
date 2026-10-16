"""Send tag clusters that errored on a bad LLM reply back to pending.

Before the tag judge requeued failed batches, a truncated or unusable reply
sent every cluster in the batch to ``error``. The stored messages are:

- from ``llm_service.chat_json``: "no JSON object in LLM content: ...",
  "invalid JSON in LLM content: ..." and "LLM content is not a JSON object"
  (all contain "LLM content");
- from ``tag_merge_service.parse_judge_response``: "LLM answer has no 'groups'
  list" (contains "no 'groups' list").
"""
from django.db import migrations
from django.db.models import Q
from django.utils import timezone


def requeue_llm_failed_clusters(apps, schema_editor):
    TagCluster = apps.get_model("lncrawler_api", "TagCluster")
    TagCluster.objects.filter(
        Q(error__contains="LLM content") | Q(error__contains="no 'groups' list"),
        status="error",
    ).update(
        status="pending",
        requeue_count=0,
        error="",
        llm_response=None,
        llm_batch=None,
        judged_at=None,
        updated_at=timezone.now(),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0078_llmusage'),
    ]

    operations = [
        migrations.RunPython(requeue_llm_failed_clusters, migrations.RunPython.noop),
    ]

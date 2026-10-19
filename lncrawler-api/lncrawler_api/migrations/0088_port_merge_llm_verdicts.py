from django.db import migrations

BATCH_SIZE = 500


def port_verdicts(apps, schema_editor):
    """Turn judged merge candidates into done LLMRequest rows of the novel_merge task.

    The usage ledger (LLMUsage) already has these calls, so no rows are added there.
    """
    LLMRequest = apps.get_model("lncrawler_api", "LLMRequest")
    MergeCandidate = apps.get_model("lncrawler_api", "MergeCandidate")

    judged = MergeCandidate.objects.filter(
        llm_checked_at__isnull=False, llm_verdict__isnull=False,
    ).order_by("pk")
    batch = []
    for candidate in judged.iterator(chunk_size=BATCH_SIZE):
        batch.append(LLMRequest(
            task="novel_merge",
            target_type="merge_candidate",
            target_ids=[str(candidate.pk)],
            status="done",
            attempts=1,
            model=candidate.llm_model,
            prompt_version="1",
            response=candidate.llm_verdict,
            raw_response="",
            tokens=0,
            finished_at=candidate.llm_checked_at,
        ))
        if len(batch) >= BATCH_SIZE:
            _flush(LLMRequest, batch)
            batch = []
    if batch:
        _flush(LLMRequest, batch)


def _flush(LLMRequest, batch):
    created = LLMRequest.objects.bulk_create(batch, batch_size=BATCH_SIZE)
    # created_at is auto_now_add, so set it after the insert to the time of the verdict.
    for req in created:
        req.created_at = req.finished_at
    LLMRequest.objects.bulk_update(created, ["created_at"], batch_size=BATCH_SIZE)


def unport_verdicts(apps, schema_editor):
    LLMRequest = apps.get_model("lncrawler_api", "LLMRequest")
    LLMRequest.objects.filter(task="novel_merge").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("lncrawler_api", "0087_job_epub_type"),
    ]

    operations = [
        migrations.RunPython(port_verdicts, unport_verdicts),
    ]

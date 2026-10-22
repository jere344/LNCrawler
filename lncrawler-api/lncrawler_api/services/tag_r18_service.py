"""Queue tags for the R18 classifier: one ``tag_r18`` candidate per tag, made here.

The LLM judges each candidate (``TagR18Task`` in ``llm_tasks``). A tag that already has a
candidate in any status is skipped, so a rejected or applied tag is never queued again.
"""
from ..models import Candidate, Tag
from .merge_common import sorted_pk_signature


def queue_r18_candidates(limit):
    """Create a pending ``tag_r18`` candidate for up to ``limit`` non-adult tags that have none.

    Tags are taken in pk order. Returns the number of candidates created.
    """
    covered = set(
        Candidate.objects.filter(kind=Candidate.KIND_TAG_R18).values_list("signature", flat=True)
    )
    rows = []
    for tag in Tag.objects.filter(is_adult=False).order_by("pk").only("pk", "name").iterator(chunk_size=2000):
        if len(rows) >= limit:
            break
        signature = sorted_pk_signature([tag.pk])
        if signature in covered:
            continue
        rows.append(Candidate(
            kind=Candidate.KIND_TAG_R18,
            signature=signature,
            target_ids=[tag.pk],
            target_names=[tag.name],
        ))
    # A concurrent run may have queued some of these tags: the unique signature skips them.
    Candidate.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)

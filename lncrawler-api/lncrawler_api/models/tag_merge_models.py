
from django.db import models
from django.db.models.functions import Greatest, Least

from .novels_models import Tag


class TagCluster(models.Model):
    """A group of tags that might be the same concept, awaiting judgement.

    Produced by ``find_tag_merge_candidates`` from embedding similarity,
    cross-source co-occurrence and trigram similarity. ``signature`` is a hash
    of the member ids so an unchanged group is never stored twice, whatever its
    status. The LLM answer lives in ``llm_response`` and is applied (or held
    for review) by ``tag_merge_service.apply_cluster``.
    """

    STATUS_PENDING = "pending"
    STATUS_APPLIED = "applied"
    STATUS_NO_MERGE = "no_merge"
    STATUS_REVIEW = "review"
    STATUS_REJECTED = "rejected"
    STATUS_UNDONE = "undone"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPLIED, "Applied"),
        (STATUS_NO_MERGE, "No merge"),
        (STATUS_REVIEW, "Review"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_UNDONE, "Undone"),
        (STATUS_ERROR, "Error"),
    ]

    signature = models.CharField(max_length=40, unique=True)
    tag_ids = models.JSONField(default=list)
    tag_names = models.JSONField(default=list)
    signals = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )

    llm_response = models.JSONField(null=True, blank=True)
    llm_model = models.CharField(max_length=100, blank=True, default="")
    llm_batch = models.UUIDField(null=True, blank=True, db_index=True)
    judged_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    # Times this cluster went back to pending because its plan changed under the lock.
    requeue_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{' / '.join(self.tag_names)} ({self.status})"


class TagMerge(models.Model):
    """One reversible change made by a tag merge or rename.

    A ``merge`` folds ``source_name`` into ``target``; the ``all_source_ids``,
    ``added_source_ids`` and ``moved_alias_ids`` lists are what undo needs to put
    the links and aliases back. A ``rename`` changes the name of ``target``.
    """

    KIND_MERGE = "merge"
    KIND_RENAME = "rename"
    KIND_CHOICES = [
        (KIND_MERGE, "Merge"),
        (KIND_RENAME, "Rename"),
    ]

    cluster = models.ForeignKey(
        TagCluster,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merges",
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_MERGE)
    source_name = models.CharField(max_length=100, blank=True, default="")
    target = models.ForeignKey(
        Tag,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merges_into",
    )
    target_name = models.CharField(max_length=100, blank=True, default="")
    all_source_ids = models.JSONField(default=list, blank=True)
    added_source_ids = models.JSONField(default=list, blank=True)
    moved_alias_ids = models.JSONField(default=list, blank=True)
    renamed_from = models.CharField(max_length=100, blank=True, default="")
    # R18 flags of both tags before a merge (which copies the flag onto the
    # target), so undo can put them back. NULL on merges recorded before them.
    source_was_adult = models.BooleanField(null=True, blank=True)
    target_was_adult = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    undone_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        if self.kind == self.KIND_RENAME:
            return f"rename '{self.renamed_from}' -> '{self.target_name}'"
        return f"merge '{self.source_name}' -> '{self.target_name}'"


class TagNoMerge(models.Model):
    """A pair of tags reviewers or undo have ruled out as duplicates.

    Dropped before clustering so a rejected pair is never proposed again.
    """

    tag_a = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="no_merge_as_a")
    tag_b = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="no_merge_as_b")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Unordered pair: one row per (A, B) regardless of argument order.
            models.UniqueConstraint(
                Least("tag_a", "tag_b"),
                Greatest("tag_a", "tag_b"),
                name="tagnomerge_unique_pair",
            ),
        ]

    def __str__(self):
        return f"{self.tag_a_id} !~ {self.tag_b_id}"

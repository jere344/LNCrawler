
from django.db import models

from .novels_models import Author


class AuthorMergeCandidate(models.Model):
    """A pair of authors that might be the same person, awaiting judgement.

    Produced by ``find_author_candidates`` from normalized equality, mixed-script
    names and cross-source pairing. ``signature`` is a hash of the two author ids
    so a pair is never stored twice, whatever its status. The LLM answer lives in
    ``llm_response`` and is applied by ``AuthorMergeTask``.
    """

    STATUS_PENDING = "pending"
    STATUS_APPLIED = "applied"
    STATUS_REVIEW = "review"
    STATUS_REJECTED = "rejected"
    STATUS_UNDONE = "undone"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPLIED, "Applied"),
        (STATUS_REVIEW, "Review"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_UNDONE, "Undone"),
        (STATUS_ERROR, "Error"),
    ]

    REASON_NORMALIZED = "normalized"
    REASON_MIXED_SCRIPT = "mixed_script"
    REASON_CROSS_SOURCE = "cross_source"

    signature = models.CharField(max_length=64, unique=True)
    author_ids = models.JSONField(default=list)
    author_names = models.JSONField(default=list)
    signals = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    reason = models.CharField(max_length=100, blank=True, default="")

    llm_response = models.JSONField(null=True, blank=True)
    llm_model = models.CharField(max_length=100, blank=True, default="")
    decided_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{' / '.join(self.author_names)} ({self.status})"


class AuthorMerge(models.Model):
    """One reversible author merge: ``source_name`` was folded into ``target``.

    ``source_ids``, ``added_source_ids`` and ``moved_alias_ids`` are what undo needs
    to put the links and aliases back.
    """

    candidate = models.ForeignKey(
        AuthorMergeCandidate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merges",
    )
    source_name = models.CharField(max_length=255, blank=True, default="")
    # Pk of the merged-away author (Author pk is a BigAutoField), so undo restores it.
    source_id = models.BigIntegerField(null=True)
    target = models.ForeignKey(
        Author,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merges_into",
    )
    target_name = models.CharField(max_length=255, blank=True, default="")
    source_ids = models.JSONField(default=list, blank=True)
    added_source_ids = models.JSONField(default=list, blank=True)
    moved_alias_ids = models.JSONField(default=list, blank=True)
    # True when the merge created the alias for the old name, so undo may delete it.
    alias_created = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    undone_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"merge '{self.source_name}' -> '{self.target_name}'"

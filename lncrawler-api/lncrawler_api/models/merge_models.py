import uuid

from django.db import models
from django.db.models.functions import Least, Greatest

from .novels_models import Novel


class MergeCandidate(models.Model):
    """A pair of novels flagged as probable duplicates.

    Produced by the ``find_merge_candidates`` command after cheap deterministic
    blocking and scoring. ``certainty`` is a normalized 0..1 score; the raw
    per-signal breakdown lives in ``signals`` so the admin can explain *why* a
    pair was flagged. Nothing is merged unless ``certainty`` clears
    ``settings.MERGE_AUTO_SCORE`` (default >1, so auto-merge is off until the
    threshold is tuned against real data); everything else waits for review.

    The FKs are ``SET_NULL`` so a row survives as an audit record after a merge
    deletes one of the novels; the ``*_snapshot`` fields keep the pair readable
    once the FK is gone.
    """

    DECISION_AUTO = "auto"
    DECISION_REVIEW = "review"
    DECISION_CHOICES = [
        (DECISION_AUTO, "Auto"),
        (DECISION_REVIEW, "Review"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_MERGED = "merged"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_MERGED, "Merged"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    novel_a = models.ForeignKey(
        Novel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merge_candidates_as_a",
    )
    novel_b = models.ForeignKey(
        Novel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merge_candidates_as_b",
    )
    novel_a_id_snapshot = models.UUIDField(null=True, blank=True)
    novel_b_id_snapshot = models.UUIDField(null=True, blank=True)
    title_a = models.CharField(max_length=255, blank=True, default="")
    title_b = models.CharField(max_length=255, blank=True, default="")

    certainty = models.FloatField(default=0.0, db_index=True)
    signals = models.JSONField(default=dict, blank=True)
    decision = models.CharField(
        max_length=10, choices=DECISION_CHOICES, default=DECISION_REVIEW, db_index=True
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )

    # Filled in by the LLM gray-band pass (phase 3); nullable so the queue works
    # with no LLM at all.
    llm_verdict = models.JSONField(null=True, blank=True)
    llm_reason = models.TextField(blank=True, default="")
    llm_model = models.CharField(max_length=100, blank=True, default="")
    llm_checked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "lncrawler_api_mergecandidate"
        ordering = ["-certainty"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(novel_a=models.F("novel_b")),
                name="mergecandidate_no_self",
            ),
            # Unordered pair: one row per (A, B) regardless of argument order.
            models.UniqueConstraint(
                Least("novel_a", "novel_b"),
                Greatest("novel_a", "novel_b"),
                name="mergecandidate_unique_pair",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-certainty"], name="mergecand_status_cert_idx"),
        ]

    def __str__(self):
        return f"{self.title_a or self.novel_a_id_snapshot} ~ {self.title_b or self.novel_b_id_snapshot} ({self.certainty:.2f})"

    def mark_merged(self):
        self.status = self.STATUS_MERGED
        self.save(update_fields=["status", "updated_at"])

    def mark_rejected(self):
        self.status = self.STATUS_REJECTED
        self.save(update_fields=["status", "updated_at"])

    def mark_skipped(self):
        self.status = self.STATUS_SKIPPED
        self.save(update_fields=["status", "updated_at"])

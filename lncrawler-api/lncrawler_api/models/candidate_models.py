from django.db import models
from django.utils import timezone


class Candidate(models.Model):
    """One proposed change for one LLM task: work item, queue slot and undo journal.

    ``kind`` is the task name. A candidate exists once per ``(kind, signature)``:
    the finder creates it ``pending``, the LLM runner judges it (``verdict``,
    ``confidence``, then ``decide``), and a human can apply, reject or re-judge it.
    ``undo`` lists what each applied change moved, so it can be reverted in reverse
    order. ``claimed_at`` marks a candidate in flight, ``not_before`` a backoff.

    ``target_ids`` / ``target_names`` are a snapshot of the targets: they still name
    the pair once a merge has deleted one of the rows.
    """

    KIND_NOVEL_MERGE = "novel_merge"
    KIND_AUTHOR_MERGE = "author_merge"
    KIND_TAG_MERGE = "tag_merge"
    KIND_TAG_R18 = "tag_r18"
    KIND_CHOICES = [
        (KIND_NOVEL_MERGE, "Novel merge"),
        (KIND_AUTHOR_MERGE, "Author merge"),
        (KIND_TAG_MERGE, "Tag merge"),
        (KIND_TAG_R18, "Tag R18"),
    ]

    STATUS_PENDING = "pending"
    STATUS_REVIEW = "review"
    STATUS_APPLIED = "applied"
    STATUS_REJECTED = "rejected"
    STATUS_UNDONE = "undone"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_REVIEW, "Review"),
        (STATUS_APPLIED, "Applied"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_UNDONE, "Undone"),
        (STATUS_ERROR, "Error"),
    ]

    # Open statuses wait for a decision or a retry. A candidate that names a merged-away
    # target is deleted instead (drop_open_naming).
    OPEN_STATUSES = (STATUS_PENDING, STATUS_REVIEW, STATUS_ERROR)

    DECIDED_LLM = "llm"
    DECIDED_HUMAN = "human"
    # Not written any more: rows copied from the old tables may still carry it.
    DECIDED_SYSTEM = "system"
    DECIDED_BY_CHOICES = [
        (DECIDED_LLM, "LLM"),
        (DECIDED_HUMAN, "Human"),
        (DECIDED_SYSTEM, "System"),
    ]

    kind = models.CharField(max_length=30, choices=KIND_CHOICES, db_index=True)
    # Primary keys of the targets: ints, or UUID strings for novels.
    target_ids = models.JSONField(default=list)
    target_names = models.JSONField(default=list)
    signature = models.CharField(max_length=64)
    signals = models.JSONField(default=dict, blank=True)
    # Finder score (novels only), used to order the review list.
    certainty = models.FloatField(default=0.0, db_index=True)

    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    # This candidate's part of the LLM answer, as the model gave it.
    verdict = models.JSONField(null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    decided_by = models.CharField(
        max_length=10, choices=DECIDED_BY_CHOICES, blank=True, default=""
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    # The LLM call that answered this candidate last.
    llm_call = models.ForeignKey(
        "LLMCall",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="candidates",
    )

    attempts = models.PositiveSmallIntegerField(default=0)
    # Backoff or Retry-After: the candidate is not claimed before this time.
    not_before = models.DateTimeField(null=True, blank=True)
    # Set while a runner holds the candidate in a call; cleared when it is released.
    claimed_at = models.DateTimeField(null=True, blank=True)

    # What each applied change moved, oldest first. Undo walks it in reverse.
    undo = models.JSONField(default=list, blank=True)
    undone_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "signature"],
                name="candidate_unique_kind_signature",
            ),
        ]
        indexes = [
            models.Index(fields=["kind", "status", "not_before"], name="candidate_queue_idx"),
        ]

    @classmethod
    def drop_open_naming(cls, pks, kinds, exclude_pk=None):
        """Delete the open candidates of ``kinds`` that name one of ``pks``. Returns the count.

        Called when a target is merged away: an open candidate naming it can no longer be
        judged or applied, so it is deleted rather than kept as a decision. Novel ids are
        stored as strings and the others as ints, so both forms are matched. ``exclude_pk``
        is the candidate being applied: its caller saves it afterwards.
        """
        if not pks:
            return 0
        match = models.Q()
        for pk in pks:
            match |= models.Q(target_ids__contains=[str(pk)])
            if isinstance(pk, int):
                match |= models.Q(target_ids__contains=[pk])
        rows = cls.objects.filter(kind__in=kinds, status__in=cls.OPEN_STATUSES).filter(match)
        if exclude_pk is not None:
            rows = rows.exclude(pk=exclude_pk)
        return rows.delete()[0]

    def __str__(self):
        return f"{self.kind}: {' / '.join(self.target_names)} ({self.status})"


class LLMCall(models.Model):
    """One reply from one LLM provider, as logged for the call history and the budget.

    Written for every reply the provider returned, truncated and non-JSON ones
    included. ``candidate_ids`` are the candidates the request covered. The daily
    token budget sums ``tokens``, so ``created_at`` is the real call time (a copied
    row keeps its original date).
    """

    kind = models.CharField(max_length=50, db_index=True)
    provider = models.CharField(max_length=50, blank=True, default="")
    model = models.CharField(max_length=100, blank=True, default="")
    prompt_version = models.CharField(max_length=20, blank=True, default="")
    tokens = models.PositiveIntegerField(default=0)
    raw_response = models.TextField(blank=True, default="")
    error = models.TextField(blank=True, default="")
    candidate_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind} via {self.provider or '-'}: {self.tokens} tokens at {self.created_at}"

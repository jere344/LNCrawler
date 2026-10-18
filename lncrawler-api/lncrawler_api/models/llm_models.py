from django.db import models


class LLMRequest(models.Model):
    """One call to the LLM for any workflow (see services/llm_tasks.py).

    Domain tables keep their own decisions; this is the shared queue and log:
    what was asked, what came back, what it cost, and the retry state.
    """

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_DONE, "Done"),
        (STATUS_FAILED, "Failed"),
    ]

    task = models.CharField(max_length=50, db_index=True)
    target_type = models.CharField(max_length=50)
    # Primary keys of the rows this request covers (a batch).
    target_ids = models.JSONField(default=list)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    # Backoff or Retry-After: the request is not claimed before this time.
    not_before = models.DateTimeField(null=True, blank=True)
    model = models.CharField(max_length=100, blank=True, default="")
    prompt_version = models.CharField(max_length=20)
    # Parsed result, kept so an admin can re-apply it.
    response = models.JSONField(null=True, blank=True)
    raw_response = models.TextField(blank=True, default="")
    error = models.TextField(blank=True, default="")
    tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task", "status", "not_before"], name="llmrequest_queue_idx"),
        ]

    def __str__(self):
        return f"LLMRequest #{self.pk} {self.task} ({self.status})"

from django.db import models
from django.utils import timezone


class HarvestCandidate(models.Model):
    """A novel URL discovered by a harvest (browse) scan, waiting to be queued.

    One row per novel URL. ``browse_novels`` only returns titles/URLs, so a
    candidate is promoted to a download job and, on success, an
    ``NovelFromSource`` is created by the regular download import path.
    """

    STATUS_PENDING = "pending"
    STATUS_QUEUED = "queued"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_DONE, "Done"),
        (STATUS_FAILED, "Failed"),
    ]

    source_name = models.CharField(max_length=255, db_index=True)
    novel_url = models.CharField(max_length=512, unique=True)
    title = models.CharField(max_length=512, blank=True, default="")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    # The Job this candidate was queued as (kept as a plain UUID, not an FK, so
    # job retention can delete old Jobs without cascading candidates).
    job_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "lncrawler_api_harvestcandidate"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "source_name"]),
        ]

    def __str__(self):
        return f"{self.source_name}: {self.title or self.novel_url}"

    def mark_queued(self, job_id):
        self.status = self.STATUS_QUEUED
        self.job_id = job_id
        self.save(update_fields=["status", "job_id", "updated_at"])

    def mark_done(self):
        self.status = self.STATUS_DONE
        self.save(update_fields=["status", "updated_at"])

    def mark_failed(self):
        self.status = self.STATUS_FAILED
        self.save(update_fields=["status", "updated_at"])

    def mark_pending(self):
        self.status = self.STATUS_PENDING
        self.job_id = None
        self.save(update_fields=["status", "job_id", "updated_at"])


class HarvestConfig(models.Model):
    """Singleton row controlling the background harvest feeder.

    Edited from the admin (start/stop, mute sources, concurrency); the feeder
    process is always running and reads this row each loop. It is never
    controlled through .env so start/stop needs no container restart.
    """

    enabled = models.BooleanField(default=False)
    muted_sources = models.JSONField(default=list, blank=True)
    max_concurrent = models.PositiveIntegerField(default=3)
    last_harvest_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "lncrawler_api_harvestconfig"

    def __str__(self):
        return f"HarvestConfig(enabled={self.enabled}, max_concurrent={self.max_concurrent})"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def is_muted(self, source_name):
        return source_name in (self.muted_sources or [])

    def mute(self, source_name):
        muted = set(self.muted_sources or [])
        muted.add(source_name)
        self.muted_sources = sorted(muted)
        self.save(update_fields=["muted_sources", "updated_at"])

    def unmute(self, source_name):
        self.muted_sources = sorted(
            name for name in (self.muted_sources or []) if name != source_name
        )
        self.save(update_fields=["muted_sources", "updated_at"])

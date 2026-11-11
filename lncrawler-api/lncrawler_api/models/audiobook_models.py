import os
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

LISTENABLE_STATUSES = ('done', 'stale')  # part statuses whose audio can be played and downloaded
LISTENABLE_PART_Q = Q(status__in=LISTENABLE_STATUSES)


class Audiobook(models.Model):
    """
    An audio version of a novel, built from one English source
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('retired', 'Retired'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    novel = models.ForeignKey('lncrawler_api.Novel', on_delete=models.CASCADE, related_name='audiobooks')
    language = models.CharField(max_length=10, default='en')
    source = models.ForeignKey('lncrawler_api.NovelFromSource', on_delete=models.CASCADE, related_name='audiobooks')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    worker_id = models.CharField(max_length=64, blank=True, default='')
    cover_file = models.CharField(max_length=500, blank=True, default='')  # relative to the source folder
    tags_hash = models.CharField(max_length=64, blank=True, default='')  # compute_tags_hash at the last retag
    total_duration_s = models.FloatField(default=0)
    total_size_bytes = models.BigIntegerField(default=0)
    parts_done = models.PositiveIntegerField(default=0)
    credits = models.JSONField(default=dict, blank=True)
    first_published_at = models.DateTimeField(null=True, blank=True)
    last_part_at = models.DateTimeField(null=True, blank=True)
    last_enqueued_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['novel', 'language'], name='audiobook_novel_language_uniq'),
        ]

    @property
    def cover_path(self):
        """The 1400 px cover, relative to LNCRAWL_OUTPUT_PATH ('' while no cover was built)."""
        folder = self.source.source_path
        return os.path.join(folder, self.cover_file) if folder and self.cover_file else ''

    @property
    def display_title(self):
        """The title of the source it is made from: the novel's title may be in another language."""
        return self.source.title

    def __str__(self):
        return self.display_title

    def refresh_totals(self):
        """Recompute the denormalised totals from the done and stale parts"""
        totals = self.parts.filter(status__in=['done', 'stale']).aggregate(
            duration=Sum('duration_s'),
            size=Sum('size_bytes'),
            count=models.Count('id'),
        )
        self.total_duration_s = totals['duration'] or 0
        self.total_size_bytes = totals['size'] or 0
        self.parts_done = totals['count'] or 0
        self.save(update_fields=['total_duration_s', 'total_size_bytes', 'parts_done', 'updated_at'])


class AudiobookPart(models.Model):
    """
    A run of whole chapters of an audiobook. It is also the job a worker claims
    """
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('claimed', 'Claimed'),
        ('done', 'Done'),
        ('failed', 'Failed'),
        ('stale', 'Stale'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audiobook = models.ForeignKey(Audiobook, on_delete=models.CASCADE, related_name='parts')
    index = models.PositiveIntegerField()
    chapter_start = models.IntegerField()
    chapter_end = models.IntegerField()
    word_count = models.PositiveIntegerField(default=0)
    estimated_duration_s = models.FloatField(default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='queued')
    priority = models.IntegerField(default=0)
    engine = models.CharField(max_length=128, blank=True, default='')
    engine_version = models.CharField(max_length=255, blank=True, default='')
    worker_id = models.CharField(max_length=64, blank=True, default='')
    claimed_at = models.DateTimeField(null=True, blank=True)
    progress = models.FloatField(default=0)
    stage = models.CharField(max_length=64, blank=True, default='')
    attempts = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    content_hash = models.CharField(max_length=64, blank=True, default='')
    chapter_ids = models.JSONField(default=list, blank=True)  # Chapter pks of the cut, in order, frozen at enqueue
    generation = models.PositiveIntegerField(default=0)  # incremented on each claim; uploads go to its own folder
    uploads = models.JSONField(default=dict, blank=True)  # {str(chapter pk): file, sha256, duration, size} of this generation
    qa = models.JSONField(default=dict, blank=True)
    qa_passed = models.BooleanField(null=True)
    duration_s = models.FloatField(default=0)
    size_bytes = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['audiobook', 'index']
        constraints = [
            models.UniqueConstraint(fields=['audiobook', 'index'], name='audiobook_part_index_uniq'),
        ]
        indexes = [
            models.Index(fields=['status', '-priority'], name='audiobook_part_claim_idx'),
        ]

    def __str__(self):
        return f"{self.audiobook} — part {self.index}"

    def upload_path(self, upload):
        """Path relative to LNCRAWL_OUTPUT_PATH of an entry of ``uploads``, '' when the source has no folder."""
        folder = self.audiobook.source.source_path
        return os.path.join(folder, upload['file_in_source']) if folder else ''

    def is_listenable(self):
        """Done or stale. QA is recorded for the admin, it does not hide the part"""
        return self.status in LISTENABLE_STATUSES


class AudiobookChapter(models.Model):
    """
    The audio file of one chapter inside a part
    """
    part = models.ForeignKey(AudiobookPart, on_delete=models.CASCADE, related_name='chapters')
    chapter = models.OneToOneField('lncrawler_api.Chapter', on_delete=models.CASCADE, related_name='audio')
    file_in_source = models.CharField(max_length=500, blank=True, default='')  # relative to the source folder
    duration_s = models.FloatField()
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    offset_s = models.FloatField(default=0)

    class Meta:
        ordering = ['part', 'chapter__chapter_id']

    @property
    def file_path(self):
        """The audio file, relative to LNCRAWL_OUTPUT_PATH ('' when the source has no folder)."""
        folder = self.part.audiobook.source.source_path
        return os.path.join(folder, self.file_in_source) if folder else ''


class AudiobookWorker(models.Model):
    """
    A machine that generates audio parts, seen through its pings and claims
    """
    worker_id = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    version = models.CharField(max_length=64, blank=True, default='')
    languages = models.JSONField(default=list, blank=True)
    available = models.BooleanField(default=True)
    message = models.TextField(blank=True, default='')

    @property
    def is_online(self):
        return self.last_seen_at is not None and self.last_seen_at >= timezone.now() - timedelta(minutes=15)

    def __str__(self):
        return self.worker_id


class ListeningProgress(models.Model):
    """
    Where a user stopped listening to an audiobook
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='listening_progress')
    audiobook = models.ForeignKey(Audiobook, on_delete=models.CASCADE, related_name='progress')
    chapter = models.ForeignKey('lncrawler_api.Chapter', on_delete=models.SET_NULL, null=True, blank=True)
    position_s = models.FloatField(default=0)
    speed = models.FloatField(default=1.0)
    finished = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'audiobook'], name='listening_progress_uniq'),
        ]


class AudiobookDailyStat(models.Model):
    """
    Plays, downloads and listened seconds of an audiobook for one day
    """
    audiobook = models.ForeignKey(Audiobook, on_delete=models.CASCADE, related_name='daily_stats')
    date = models.DateField()
    plays = models.PositiveIntegerField(default=0)
    downloads = models.PositiveIntegerField(default=0)
    listen_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['audiobook', 'date'], name='audiobook_daily_stat_uniq'),
        ]

    @classmethod
    def bump(cls, audiobook_id, plays=0, downloads=0, listen_seconds=0):
        """Add to today's row with a single upsert (no read-back)"""
        from django.db import connection

        table = cls._meta.db_table
        cols = ['audiobook_id', 'date', 'plays', 'downloads', 'listen_seconds']
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) "
                f"VALUES (%s, %s, %s, %s, %s) "
                f"ON CONFLICT (audiobook_id, date) "
                f"DO UPDATE SET plays = {table}.plays + EXCLUDED.plays, "
                f"downloads = {table}.downloads + EXCLUDED.downloads, "
                f"listen_seconds = {table}.listen_seconds + EXCLUDED.listen_seconds",
                [audiobook_id, timezone.localdate(), plays, downloads, listen_seconds],
            )

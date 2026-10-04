from django.db import models
import uuid
from django.conf import settings
from django.db.models import F


class Novel(models.Model):
    """
    Main novel model that groups together different sources of the same novel
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    novel_path = models.CharField(max_length=500, null=True, blank=True)  # Path relative to settings.LNCRAWL_OUTPUT_PATH
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    comment_count = models.PositiveIntegerField(default=0)
    is_dmca = models.BooleanField(default=False, db_index=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['-created_at'], name='novel_created_at_idx'),
        ]
    
    def __str__(self):
        return self.title
    
    @property
    def sources_count(self):
        return self.sources.count()
        
    def increment_comment_count(self):
        """
        Increment the comment count for the novel
        """
        Novel.objects.filter(pk=self.pk).update(
            comment_count=F('comment_count') + 1
        )
        # Refresh from database to get the latest values
        self.refresh_from_db()


class NovelAlias(models.Model):
    """
    Redirect from an obsolete novel slug to the canonical novel it was merged
    into.

    ``NovelFromSource.from_meta_json`` identifies a novel by the slugified name
    of its output folder. When two folders hold the same story and are merged,
    a future crawl of the old folder name would otherwise recreate a fresh
    ``Novel`` and undo the merge. Recording the old slug here makes that future
    crawl attach to the surviving novel instead.
    """
    slug = models.SlugField(max_length=255, unique=True)
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='aliases')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Novel alias'
        verbose_name_plural = 'Novel aliases'
        ordering = ['slug']

    def __str__(self):
        return f"{self.slug} -> {self.novel.slug}"


class Person(models.Model):
    """Base model for people involved with novels (authors, editors, translators)"""
    name = models.CharField(max_length=255)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class Author(Person):
    """Author of a novel"""
    pass


class Editor(Person):
    """Editor of a novel"""
    pass


class Translator(Person):
    """Translator of a novel"""
    pass


class Tag(models.Model):
    """Tags for novels"""
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

    @classmethod
    def resolve(cls, name):
        """Return the tag named ``name``, following a merged-away alias first.

        Keeps re-imports from recreating a tag that was merged into another.
        """
        alias = TagAlias.objects.filter(name=name).select_related('tag').first()
        if alias is not None:
            return alias.tag
        tag, _ = cls.objects.get_or_create(name=name)
        return tag


class TagAlias(models.Model):
    """A merged-away tag name pointing at its canonical Tag."""
    name = models.CharField(max_length=100, unique=True)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='aliases')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'tag alias'
        verbose_name_plural = 'tag aliases'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} -> {self.tag.name}"


class AlternativeTitle(models.Model):
    """Alternative / native title a novel is known by on a given source."""
    name = models.CharField(max_length=500, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class NovelRating(models.Model):
    """
    Tracks user ratings for novels (1-5 stars)
    """
    RATING_CHOICES = [
        (1, '1 Star'),
        (2, '2 Stars'),
        (3, '3 Stars'),
        (4, '4 Stars'),
        (5, '5 Stars'),
    ]
    
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='ratings')
    # Logged-in users are keyed by user; anonymous visitors fall back to IP.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True, related_name='novel_ratings',
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    rating = models.IntegerField(choices=RATING_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['novel', 'user'],
                condition=models.Q(user__isnull=False),
                name='unique_rating_per_user',
            ),
            models.UniqueConstraint(
                fields=['novel', 'ip_address'],
                condition=models.Q(user__isnull=True),
                name='unique_rating_per_anon_ip',
            ),
        ]
        
    def __str__(self):
        who = self.user.username if self.user_id else self.ip_address
        return f"Rating {self.rating} for {self.novel.title} by {who}"


class WeeklySourceView(models.Model):
    """
    Views for one source (NovelFromSource) as time buckets. Recent views are
    stored one row per day (granularity='day', day = the calendar day); buckets
    older than the consolidation window are rolled up by
    ``consolidate_source_views`` into one row per ISO week (granularity='week',
    day = that week's Monday).

    Views are tracked per source because a novel can be available in several
    languages and popularity must be attributable to a language. The all-time
    total is a rebuildable projection kept on NovelFromSource.total_views, so
    this table stays the single event record.

    The trailing WINDOW_DAYS days of daily buckets are summed to produce the
    rolling "weekly views" shown in the UI, so the number slides day by day
    instead of resetting at the start of each calendar week.
    """
    WINDOW_DAYS = 7
    CONSOLIDATION_DAYS = 30  # Keep daily buckets this long before rolling up

    DAY = 'day'
    WEEK = 'week'
    GRANULARITY_CHOICES = [(DAY, 'day'), (WEEK, 'week')]

    source = models.ForeignKey(
        'NovelFromSource', on_delete=models.CASCADE, related_name='weekly_views'
    )
    day = models.DateField()  # Day for daily rows, Monday for weekly rows
    granularity = models.CharField(max_length=4, choices=GRANULARITY_CHOICES, default=DAY)
    views = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('source', 'granularity', 'day')
        indexes = [
            models.Index(fields=['granularity', 'day']),
            models.Index(fields=['source', 'granularity', 'day']),
        ]

    def __str__(self):
        period = self.day if self.granularity == self.DAY else f"week of {self.day}"
        return f"{self.source.title}: {self.views} views ({period})"

    @classmethod
    def window_start(cls):
        """First day included in the trailing window (today inclusive)."""
        from datetime import date, timedelta
        return date.today() - timedelta(days=cls.WINDOW_DAYS - 1)

    @classmethod
    def increment_for_source(cls, source):
        """
        Increment today's view count for a source and its all-time projection.
        """
        from datetime import date
        from django.db import transaction

        from .sources_models import NovelFromSource

        today = date.today()
        with transaction.atomic():
            daily_view, _ = cls.objects.get_or_create(
                source=source,
                granularity=cls.DAY,
                day=today,
                defaults={'views': 0}
            )
            cls.objects.filter(pk=daily_view.pk).update(views=F('views') + 1)

            NovelFromSource.objects.filter(pk=source.pk).update(
                total_views=F('total_views') + 1
            )

        # Refresh from database to get the latest values
        daily_view.refresh_from_db()
        return daily_view


class FeaturedNovel(models.Model):
    """
    Tracks which novels are featured on the site
    """
    novel = models.OneToOneField(Novel, on_delete=models.CASCADE, related_name='featured')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    description = models.TextField(blank=True, help_text="Reason why this novel is featured")
    
    def __str__(self):
        return f"Featured: {self.novel.title}"
    
    class Meta:
        verbose_name = "Featured Novel"
        verbose_name_plural = "Featured Novels"


class NovelSimilarity(models.Model):
    """
    Stores similarity scores between novels
    """
    from_novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='similar_to')
    to_novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='similar_from')
    similarity = models.FloatField(default=0.0, help_text="Similarity score between 0 and 1")
    
    class Meta:
        unique_together = ('from_novel', 'to_novel')
        verbose_name_plural = "Novel Similarities"
    
    def __str__(self):
        return f"{self.from_novel.title} → {self.to_novel.title}: {self.similarity}"
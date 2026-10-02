from django.db import models
import uuid
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
    ip_address = models.GenericIPAddressField()
    rating = models.IntegerField(choices=RATING_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('novel', 'ip_address')
        
    def __str__(self):
        return f"Rating {self.rating} for {self.novel.title} by {self.ip_address}"


class NovelViewCount(models.Model):
    """
    Tracks the total view count for a novel across all sources
    """
    novel = models.OneToOneField(Novel, on_delete=models.CASCADE, related_name='view_count')
    views = models.BigIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.novel.title}: {self.views} views"

    def increment(self):
        """
        Increment the all-time view count for the novel
        """
        NovelViewCount.objects.filter(pk=self.pk).update(
            views=F('views') + 1
        )
        
        # Refresh from database to get the latest values
        self.refresh_from_db()


class WeeklyNovelView(models.Model):
    """
    Tracks novel views as time buckets. Recent views are stored one row per day
    (granularity='day', day = the calendar day); buckets older than the
    consolidation window are rolled up by ``consolidate_novel_views`` into one
    row per ISO week (granularity='week', day = that week's Monday).

    The trailing WINDOW_DAYS days of daily buckets are summed to produce the
    rolling "weekly views" shown in the UI, so the number slides day by day
    instead of resetting at the start of each calendar week.
    """
    WINDOW_DAYS = 7
    CONSOLIDATION_DAYS = 30  # Keep daily buckets this long before rolling up

    DAY = 'day'
    WEEK = 'week'
    GRANULARITY_CHOICES = [(DAY, 'day'), (WEEK, 'week')]

    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='weekly_views')
    day = models.DateField()  # Day for daily rows, Monday for weekly rows
    granularity = models.CharField(max_length=4, choices=GRANULARITY_CHOICES, default=DAY)
    views = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ('novel', 'granularity', 'day')
    
    def __str__(self):
        period = self.day if self.granularity == self.DAY else f"week of {self.day}"
        return f"{self.novel.title}: {self.views} views ({period})"

    @classmethod
    def window_start(cls):
        """First day included in the trailing window (today inclusive)."""
        from datetime import date, timedelta
        return date.today() - timedelta(days=cls.WINDOW_DAYS - 1)

    @classmethod
    def increment_for_novel(cls, novel):
        """
        Increment today's view count for a novel
        """
        from datetime import date
        today = date.today()
        daily_view, _ = cls.objects.get_or_create(
            novel=novel,
            granularity=cls.DAY,
            day=today,
            defaults={'views': 0}
        )

        cls.objects.filter(pk=daily_view.pk).update(views=F('views') + 1)

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
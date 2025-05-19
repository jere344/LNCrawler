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
    
    def __str__(self):
        return self.title
    
    @property
    def sources_count(self):
        return self.sources.count()


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


class Genre(models.Model):
    """Genres for novels"""
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
    Tracks weekly view counts for novels
    The year_week field stores the ISO year and week number (YYYYWW format)
    """
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='weekly_views')
    year_week = models.CharField(max_length=6)  # Format: YYYYWW
    views = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ('novel', 'year_week')
    
    def __str__(self):
        return f"{self.novel.title}: {self.views} views in week {self.year_week}"

    @classmethod
    def increment_for_novel(cls, novel):
        """
        Increment the weekly view count for a novel
        """
        from datetime import datetime
        # Get current ISO year and week number
        current_date = datetime.now()
        year_week = f"{current_date.isocalendar()[0]}{current_date.isocalendar()[1]:02d}"
        
        # Get or create the weekly record
        weekly_view, created = cls.objects.get_or_create(
            novel=novel,
            year_week=year_week,
            defaults={'views': 0}
        )
        
        cls.objects.filter(pk=weekly_view.pk).update(views=F('views') + 1)
        
        # Refresh from database to get the latest values
        weekly_view.refresh_from_db()
        
        return weekly_view


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
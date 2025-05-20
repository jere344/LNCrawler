from django.db import models
import uuid
from django.conf import settings
from .novels_models import Novel
from .sources_models import NovelFromSource, Chapter

class NovelBookmark(models.Model):
    """
    Tracks user bookmarks for novels
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='novel_bookmarks')
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='bookmarked_by_users')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'novel')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} bookmarked {self.novel.title}"


class ReadingHistory(models.Model):
    """
    Tracks user reading progress within a novel source
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reading_histories')
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='reading_histories')
    source = models.ForeignKey(NovelFromSource, on_delete=models.CASCADE, related_name='read_by_users')
    last_read_chapter = models.ForeignKey(Chapter, on_delete=models.SET_NULL, null=True, blank=True, related_name='last_read_by_users')
    last_read_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('user', 'novel')
        ordering = ['-last_read_at']
        verbose_name_plural = "Reading novel histories"
    
    def __str__(self):
        return f"{self.user.username} - {self.source.name}"
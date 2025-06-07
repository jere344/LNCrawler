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
        return f"{self.user.username}"


class ReadingList(models.Model):
    """
    User-created list of novels
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reading_lists')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.title} by {self.user.username}"


class ReadingListItem(models.Model):
    """
    An item in a reading list with optional note
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reading_list = models.ForeignKey(ReadingList, on_delete=models.CASCADE, related_name='items')
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='in_reading_lists')
    note = models.TextField(blank=True, null=True)
    position = models.PositiveIntegerField(default=0)
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('reading_list', 'novel')
        ordering = ['position', 'added_at']
    
    def __str__(self):
        return f"{self.novel.title} in {self.reading_list.title}"
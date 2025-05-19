from django.db import models
import uuid
from django.conf import settings
from .novels_models import Novel

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

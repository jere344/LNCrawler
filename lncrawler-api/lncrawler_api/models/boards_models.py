import uuid
from django.db import models
from django.utils.text import slugify

class Board(models.Model):
    """
    Represents a chat board where users can post comments
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    comment_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def increment_comment_count(self):
        """Increment comment count by 1"""
        self.comment_count = models.F('comment_count') + 1
        self.save(update_fields=['comment_count'])
        self.refresh_from_db()

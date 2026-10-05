import uuid
from django.db import models
from django.conf import settings


class ChatMessage(models.Model):
    """
    A message in the single global chat feed.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_messages',
    )
    author_name = models.CharField(max_length=100)
    message = models.TextField()
    contains_spoiler = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    edited = models.BooleanField(default=False)

    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at'], name='chatmessage_created_at_idx'),
        ]

    def __str__(self):
        author_display = self.user.username if self.user else self.author_name
        return f"Chat message by {author_display}"

    def save(self, *args, **kwargs):
        if self.user:
            self.author_name = self.user.username
        super().save(*args, **kwargs)

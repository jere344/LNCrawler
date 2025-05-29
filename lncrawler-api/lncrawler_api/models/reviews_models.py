from django.db import models
import uuid
from django.db.models import F, Case, When, Value
from auth_app.models import CustomUser
from .novels_models import Novel


class Review(models.Model):
    """
    User reviews for novels
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='reviews')
    title = models.CharField(max_length=200)
    content = models.TextField()
    rating = models.IntegerField(choices=[(i, f'{i} Star{"s" if i > 1 else ""}') for i in range(1, 6)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('novel', 'user')
        ordering = ['-created_at']
    
    @property
    def get_reaction_count(self):
        """
        Returns the count of reactions for this review
        """
        return self.reactions.count()
        
    def __str__(self):
        return f"Review by {self.user.username} for {self.novel.title}"


class ReviewReaction(models.Model):
    """
    Emoji reactions to reviews, supports both authenticated and anonymous users
    """
    REACTION_CHOICES = [
        ('sparkle', '✨ Nice'),
        ('heart', '❤️ Love it'),
        ('laugh', '😂 Funny'),
        ('eyebrow', '🤨 Confusing'),
        ('lightbulb', '💡 Informative'),
        ('write', '📝 Well written'),
        ('paint', '🎨 Creative'),
        ('sick', '🤢 Disgusting'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True, related_name='review_reactions')
    ip_address = models.GenericIPAddressField()
    reaction = models.CharField(max_length=20, choices=REACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        # Ensure one reaction per user per review, or one per IP if anonymous
        constraints = [
            models.UniqueConstraint(
                fields=['review', 'user'],
                condition=models.Q(user__isnull=False),
                name='unique_user_reaction_per_review'
            ),
            models.UniqueConstraint(
                fields=['review', 'ip_address'],
                condition=models.Q(user__isnull=True),
                name='unique_ip_reaction_per_review'
            )
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        reactor = self.user.username if self.user else f"Anonymous ({self.ip_address})"
        return f"{self.get_reaction_display()} by {reactor} on review {self.review.id}"
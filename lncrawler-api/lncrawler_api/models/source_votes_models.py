from django.db import models

from .sources_models import NovelFromSource


class SourceVote(models.Model):
    """
    Tracks upvotes and downvotes for novel sources
    """
    VOTE_CHOICES = [
        ('up', 'Upvote'),
        ('down', 'Downvote'),
    ]
    
    source = models.ForeignKey('NovelFromSource', on_delete=models.CASCADE, related_name='votes')
    ip_address = models.GenericIPAddressField()
    vote_type = models.CharField(max_length=4, choices=VOTE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('source', 'ip_address')
        
    def __str__(self):
        return f"{self.get_vote_type_display()} for {self.source.title} by {self.ip_address}"
    
    def save(self, *args, **kwargs):
        is_new = self._state.adding
        old_vote_type = None

        if not is_new:
            try:
                old_vote_type = SourceVote.objects.get(pk=self.pk).vote_type
            except SourceVote.DoesNotExist:
                is_new = True

        super().save(*args, **kwargs)

        # Update counts atomically so concurrent votes don't lose increments.
        source_pk = self.source_id

        if is_new:
            if self.vote_type == 'up':
                NovelFromSource.objects.filter(pk=source_pk).update(
                    upvotes=models.F('upvotes') + 1
                )
            else:
                NovelFromSource.objects.filter(pk=source_pk).update(
                    downvotes=models.F('downvotes') + 1
                )
        elif old_vote_type and old_vote_type != self.vote_type:
            if self.vote_type == 'up':
                NovelFromSource.objects.filter(pk=source_pk).update(
                    upvotes=models.F('upvotes') + 1,
                    downvotes=models.F('downvotes') - 1,
                )
            else:
                NovelFromSource.objects.filter(pk=source_pk).update(
                    downvotes=models.F('downvotes') + 1,
                    upvotes=models.F('upvotes') - 1,
                )

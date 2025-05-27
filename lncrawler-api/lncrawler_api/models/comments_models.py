import uuid
from django.db import models
from django.conf import settings

class Comment(models.Model):
    """
    Represents a comment on a novel, chapter, or board
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Use string reference to avoid circular import issues at definition time
    novel = models.ForeignKey('lncrawler_api.Novel', on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    chapter = models.ForeignKey('lncrawler_api.Chapter', on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    board = models.ForeignKey('lncrawler_api.Board', on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='comments'
    )
    author_name = models.CharField(max_length=100) # Will store username if user is linked, or provided name if anonymous
    message = models.TextField()
    contains_spoiler = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)  # To prevent spam
    edited = models.BooleanField(default=False)
    
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    
    upvotes = models.IntegerField(default=0)
    downvotes = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        if self.novel:
            target = f"Novel: {self.novel.title}"
        elif self.chapter:
            target = f"Chapter: {self.chapter.title}"
        elif self.board:
            target = f"Board: {self.board.name}"
        else:
            target = "Unknown target"
        
        author_display = self.user.username if self.user else self.author_name
        return f"Comment by {author_display} on {target}"
    
    @property
    def vote_score(self):
        return self.upvotes - self.downvotes
    
    def save(self, *args, **kwargs):
        # Check that comment is associated with exactly one target
        targets = [self.novel, self.chapter, self.board]
        active_targets = [target for target in targets if target is not None]
        
        if len(active_targets) != 1:
            raise ValueError("Comment must be associated with exactly one of: novel, chapter, or board")
        
        if self.user: # If a user is linked to this comment
            self.author_name = self.user.username # Set/update author_name to their current username
            
        if self.parent:
            if self.novel and self.parent.novel_id != self.novel_id:
                raise ValueError("Reply must be to a comment on the same novel")
            if self.chapter and self.parent.chapter_id != self.chapter_id:
                raise ValueError("Reply must be to a comment on the same chapter")
            if self.board and self.parent.board_id != self.board_id:
                raise ValueError("Reply must be to a comment on the same board")
            
        super().save(*args, **kwargs)

class CommentVote(models.Model):
    """
    Tracks upvotes and downvotes for comments.
    """
    VOTE_CHOICES = [
        ('up', 'Upvote'),
        ('down', 'Downvote'),
    ]
    
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='votes')
    ip_address = models.GenericIPAddressField()
    vote_type = models.CharField(max_length=4, choices=VOTE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('comment', 'ip_address')
        
    def __str__(self):
        return f"{self.get_vote_type_display()} for comment {self.comment_id} by {self.ip_address}"

    def save(self, *args, **kwargs):
        old_vote_type = None
        is_new = self._state.adding

        if not is_new:
            try:
                old_instance = CommentVote.objects.get(pk=self.pk)
                old_vote_type = old_instance.vote_type
            except CommentVote.DoesNotExist:
                is_new = True # Treat as new if somehow not found

        super().save(*args, **kwargs)

        comment_pk = self.comment_id # Use self.comment_id to avoid fetching the comment object here

        if is_new:
            if self.vote_type == 'up':
                Comment.objects.filter(pk=comment_pk).update(upvotes=models.F('upvotes') + 1)
            elif self.vote_type == 'down':
                Comment.objects.filter(pk=comment_pk).update(downvotes=models.F('downvotes') + 1)
        elif old_vote_type and old_vote_type != self.vote_type:
            # Vote changed
            if self.vote_type == 'up':  # Was down, now up
                Comment.objects.filter(pk=comment_pk).update(
                    upvotes=models.F('upvotes') + 1,
                    downvotes=models.F('downvotes') - 1
                )
            elif self.vote_type == 'down':  # Was up, now down
                Comment.objects.filter(pk=comment_pk).update(
                    downvotes=models.F('downvotes') + 1,
                    upvotes=models.F('upvotes') - 1
                )

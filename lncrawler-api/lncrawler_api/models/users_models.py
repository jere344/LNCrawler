from django.db import models
import uuid
from django.conf import settings
from django.db.models.functions import Least, Greatest
from .novels_models import Novel
from .sources_models import NovelFromSource, Chapter

class LibraryFolder(models.Model):
    """
    A flat, user-created folder used to organize library bookmarks.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='library_folders')
    name = models.CharField(max_length=255)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'name')
        ordering = ['position', 'created_at']

    def __str__(self):
        return f"{self.name} ({self.user.username})"


class NovelBookmark(models.Model):
    """
    Tracks user bookmarks for novels
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='novel_bookmarks')
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='bookmarked_by_users')
    folder = models.ForeignKey(LibraryFolder, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookmarks')
    note = models.TextField(blank=True, null=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'novel')
        ordering = ['position', '-created_at']

    def __str__(self):
        return f"{self.user.username} bookmarked {self.novel.title}"


class ReadingHistory(models.Model):
    """
    Tracks where a user is in a novel: one row per (user, novel), pointing at the chapter being read
    and how far into it the user is.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reading_histories')
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='reading_histories')
    source = models.ForeignKey(NovelFromSource, on_delete=models.CASCADE, related_name='read_by_users')
    current_chapter = models.ForeignKey(Chapter, on_delete=models.SET_NULL, null=True, blank=True, related_name='current_readers')
    # How far into current_chapter the user is: 0 is the top, 1 is the end.
    position = models.FloatField(default=0)
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
    is_public = models.BooleanField(default=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reading_lists')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.title} by {self.user.username}"


class ReadingListCollaborator(models.Model):
    """
    Grants a user editor or reader access to a reading list.
    """
    EDITOR = 'editor'
    READER = 'reader'
    ROLE_CHOICES = [
        (EDITOR, 'Editor'),
        (READER, 'Reader'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reading_list = models.ForeignKey(ReadingList, on_delete=models.CASCADE, related_name='collaborators')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reading_list_collaborations')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=EDITOR)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('reading_list', 'user')
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.user.username} ({self.role}) on {self.reading_list.title}"


class ProfilePinnedNovel(models.Model):
    """
    A novel the user chose to pin on their public profile.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='pinned_novels')
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='pinned_by_users')
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'novel')
        ordering = ['position', 'created_at']

    def __str__(self):
        return f"{self.user.username} pinned {self.novel.title}"


class Friendship(models.Model):
    """
    A friendship request between two users. Accepted rows are the friend graph;
    a declined/cancelled request is deleted (no stale status to leak).
    """
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (ACCEPTED, 'Accepted'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='friend_requests_sent')
    addressee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='friend_requests_received')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('requester', 'addressee')
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(requester=models.F('addressee')),
                name='friendship_no_self',
            ),
            # A relationship is unordered: enforce one row per pair so two users
            # sending to each other concurrently cannot create A->B and B->A.
            models.UniqueConstraint(
                Least('requester', 'addressee'),
                Greatest('requester', 'addressee'),
                name='friendship_unique_pair',
            ),
        ]

    def __str__(self):
        return f"{self.requester.username} -> {self.addressee.username} ({self.status})"


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

class ReaderSettingsSlot(models.Model):
    """
    A user's reader settings for one device type. Phones and desktops keep separate copies.
    `revision` goes up on every save, so a device writing from an outdated copy is refused.
    """
    SLOT_CHOICES = [('mobile', 'Mobile'), ('desktop', 'Desktop')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reader_settings_slots')
    slot = models.CharField(max_length=16, choices=SLOT_CHOICES)
    data = models.JSONField(default=dict)
    schema_version = models.PositiveIntegerField(default=1)
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'slot')

    def __str__(self):
        return f"{self.user.username} reader settings ({self.slot}, r{self.revision})"

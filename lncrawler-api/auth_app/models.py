from django.contrib.auth.models import AbstractUser
from django.db import models
import hashlib
from django.utils import timezone
from datetime import timedelta

# Sections of a profile whose visibility is user-controlled.
PRIVACY_SECTIONS = [
    'library',
    'library_notes',
    'library_ratings',
    'reading_lists',
    'reviews',
    'comments',
    'stats',
    'reading_history',
    'friends',
]
PRIVACY_CHOICES = ['public', 'friends', 'private']
DEFAULT_PRIVACY = {section: 'private' for section in PRIVACY_SECTIONS}


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    profile_pic = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    banner = models.ImageField(upload_to='profile_banners/', blank=True, null=True)
    bio = models.TextField(blank=True, default='')
    # {mal: url, anilist: url, ...}; keys validated against SOCIAL_LINK_KEYS.
    social_links = models.JSONField(default=dict, blank=True)
    # {section: public|friends|private}; missing sections fall back to DEFAULT_PRIVACY.
    privacy_settings = models.JSONField(default=dict, blank=True)
    word_read = models.IntegerField(default=0)  # Total words read by the user
    # Interface language; empty means "detect from the browser".
    preferred_ui_language = models.CharField(max_length=10, blank=True, default='')
    # Content languages whose novels the user wants to see on the home page.
    preferred_languages = models.JSONField(default=list, blank=True)
    # When False, the home page ignores preferred_languages and mixes everything.
    language_filter_enabled = models.BooleanField(default=True)
    # When False, the user never appears in the user-search results used for
    # finding friends/collaborators. Existing accounts stay discoverable.
    discoverable = models.BooleanField(default=True)
    # How adult (R18) content is shown to this user across the site:
    # 'no' hides it, 'yes' shows it normally, 'blur' shows it with blurred
    # covers. Anonymous visitors fall back to 'no'.
    show_r18 = models.CharField(
        max_length=4,
        choices=[('yes', 'Yes'), ('no', 'No'), ('blur', 'Blur')],
        default='no',
    )

    def visibility(self, section):
        """Effective visibility of a profile section for this user."""
        stored = self.privacy_settings if isinstance(self.privacy_settings, dict) else {}
        value = stored.get(section)
        if value in PRIVACY_CHOICES:
            return value
        return DEFAULT_PRIVACY.get(section, 'private')

    def __str__(self):
        return self.username

class PasswordResetToken(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    # Only the sha256 of the emailed raw token is stored, so a DB leak cannot
    # be turned into a usable reset link.
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    @staticmethod
    def hash_token(raw_token):
        return hashlib.sha256(raw_token.encode()).hexdigest()

    def is_valid(self):
        return not self.used and self.created_at > timezone.now() - timedelta(hours=24)

    def __str__(self):
        return f"Reset token for {self.user.username}"
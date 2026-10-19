from django.db import models


class PlaceholderCover(models.Model):
    """A cover hash the source site uses as a stand-in image, not a real cover.

    Marked from the admin duplicate-covers page. Every source carrying the hash
    loses its cover, and ``cover_service.generate_cover_min`` drops the hash on
    future imports so the frontend falls back to our own default cover.
    ``sample_path`` keeps a copy of the thumbnail so the admin still shows what
    was blocked, even though the source covers are gone.
    """

    cover_phash = models.CharField(max_length=16, unique=True)
    sample_path = models.CharField(max_length=500, null=True, blank=True)
    removed_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "placeholder cover"

    def __str__(self):
        return self.cover_phash

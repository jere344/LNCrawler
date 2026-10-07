from django.db import models
from django.contrib.postgres.fields import ArrayField
from ..utils import chapter_utils


class Volume(models.Model):
    """
    Represents a volume within a novel from a specific source
    """
    novel_from_source = models.ForeignKey('lncrawler_api.NovelFromSource', on_delete=models.CASCADE, related_name='volumes', db_index=False)
    volume_id = models.IntegerField()
    title = models.CharField(max_length=500)
    start_chapter = models.IntegerField(null=True, blank=True)
    final_chapter = models.IntegerField(null=True, blank=True)
    chapter_count = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ('novel_from_source', 'volume_id')
    
    def __str__(self):
        return f"{self.title} - {self.novel_from_source.title}"


class Chapter(models.Model):
    """
    Represents a chapter within a novel from a specific source
    """
    novel_from_source = models.ForeignKey('lncrawler_api.NovelFromSource', on_delete=models.CASCADE, related_name='chapters', db_index=False)
    chapter_id = models.IntegerField()
    url = models.URLField(max_length=500)
    title = models.CharField(max_length=500)
    volume = models.IntegerField(default=0)
    volume_title = models.CharField(max_length=500, blank=True, null=True)
    images = ArrayField(models.CharField(max_length=500), default=list)  # store only image filenames
    has_content = models.BooleanField(default=False)  # New field to track content availability
    
    class Meta:
        unique_together = ('novel_from_source', 'chapter_id')
        ordering = ['chapter_id']
        indexes = [
            models.Index(
                fields=['novel_from_source', 'chapter_id'],
                name='chapter_source_chapter_idx',
                condition=models.Q(has_content=True),
            ),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.novel_from_source.title}"
    
    @property
    def body(self):
        """Read the chapter body from the file"""
        parsed_chapter = chapter_utils.get_chapter(self.novel_from_source.absolute_source_path, self.chapter_id)
        if parsed_chapter:
            return parsed_chapter.get('body', None)

        return None


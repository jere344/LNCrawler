from django.db import models
from ..utils import chapter_utils


class Volume(models.Model):
    """
    Represents a volume within a novel from a specific source
    """
    novel_from_source = models.ForeignKey('lncrawler_api.NovelFromSource', on_delete=models.CASCADE, related_name='volumes')
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
    novel_from_source = models.ForeignKey('lncrawler_api.NovelFromSource', on_delete=models.CASCADE, related_name='chapters')
    chapter_id = models.IntegerField()
    url = models.URLField(max_length=500)
    title = models.CharField(max_length=500)
    volume = models.IntegerField(default=0)
    volume_title = models.CharField(max_length=500, blank=True, null=True)
    images = models.JSONField(default=list)  # store only image filenames
    has_content = models.BooleanField(default=False)  # New field to track content availability
    
    class Meta:
        unique_together = ('novel_from_source', 'chapter_id')
        ordering = ['chapter_id']
    
    def __str__(self):
        return f"{self.title} - {self.novel_from_source.title}"
    
    @property
    def body(self):
        """Read the chapter body from the file"""
        parsed_chapter = chapter_utils.get_chapter(self.novel_from_source.absolute_source_path, self.chapter_id)
        if parsed_chapter:
            return parsed_chapter.get('body', None)

        return None
    
    def check_has_content(self, save=True):
        """Check if the chapter file exists and has content, and update the has_content field"""
        has_content = chapter_utils.check_chapter_has_content(self.novel_from_source.absolute_source_path, self.chapter_id)
        
        # Update the field if it's different
        if self.has_content != has_content:
            self.has_content = has_content
            if save:
                self.save(update_fields=['has_content'])
        
        return has_content
    
    def save(self, *args, **kwargs):
        # If we're not explicitly updating specific fields, check content
        if not kwargs.get('update_fields') or 'has_content' not in kwargs.get('update_fields', []):
            self.check_has_content(save=False)
        super().save(*args, **kwargs)

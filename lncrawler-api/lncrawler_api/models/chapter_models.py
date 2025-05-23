from django.db import models
import os
import json
from django.conf import settings
from ..utils.chapter_utils import check_chapter_path_has_content


class Volume(models.Model):
    """
    Represents a volume within a novel from a specific source
    """
    novel_from_source = models.ForeignKey('lncrawler_api.NovelFromSource', on_delete=models.CASCADE, related_name='volumes')
    volume_id = models.IntegerField()
    title = models.CharField(max_length=255)
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
    title = models.CharField(max_length=255)
    volume = models.IntegerField(default=0)
    volume_title = models.CharField(max_length=255, blank=True, null=True)
    chapter_path = models.CharField(max_length=500, null=True, blank=True)  # Path relative to settings.LNCRAWL_OUTPUT_PATH
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
        if self.chapter_path:
            try:
                full_path = os.path.join(settings.LNCRAWL_OUTPUT_PATH, self.chapter_path)
                if os.path.exists(full_path):
                    with open(full_path, 'r', encoding='utf-8') as f:
                        chapter_data = json.load(f)
                        return chapter_data.get('body')
            except Exception as e:
                print(f"Error reading chapter file {full_path}: {e}")
        
        return None
    
    def check_has_content(self, save=True):
        """Check if the chapter file exists and has content, and update the has_content field"""
        chapter_path = self.chapter_path
        # If no chapter_path is available, construct it from source_path and chapter_id
        if not chapter_path:
            try:
                source_path = self.novel_from_source.source_path
                if source_path:
                    chapter_path = os.path.join(source_path, 'json', f"{self.chapter_id:05d}.json")
            except Exception:
                chapter_path = None
        
        has_content = False
        if chapter_path:
            has_content = check_chapter_path_has_content(chapter_path)
        
        # Update the field if it's different
        if self.has_content != has_content:
            self.has_content = has_content
            if self.chapter_path != chapter_path:
                self.chapter_path = chapter_path
            
            if save:
                self.save(update_fields=['has_content'])
        
        return has_content
    
    def save(self, *args, **kwargs):
        # If we're not explicitly updating specific fields, check content
        if not kwargs.get('update_fields') or 'has_content' not in kwargs.get('update_fields', []):
            self.check_has_content(save=False)
        super().save(*args, **kwargs)

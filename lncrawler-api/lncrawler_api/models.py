from django.db import models

# Create your models here.

from django.db import models
from django.utils import timezone
import json
import uuid
import logging

logger = logging.getLogger("lncrawler_api")

class Job(models.Model):
    """Model to store the state of a downloader job"""
    
    # Job status choices
    STATUS_CREATED = 'created'
    STATUS_SEARCHING = 'searching'
    STATUS_SEARCH_COMPLETED = 'search_completed'
    STATUS_DOWNLOADING = 'downloading'
    STATUS_DOWNLOAD_COMPLETED = 'download_completed'
    STATUS_FAILED = 'failed'
    
    STATUS_CHOICES = [
        (STATUS_CREATED, 'Created'),
        (STATUS_SEARCHING, 'Searching'),
        (STATUS_SEARCH_COMPLETED, 'Search Completed'),
        (STATUS_DOWNLOADING, 'Downloading'),
        (STATUS_DOWNLOAD_COMPLETED, 'Download Completed'),
        (STATUS_FAILED, 'Failed'),
    ]
    
    # Primary fields
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CREATED)
    query = models.CharField(max_length=255, blank=True, null=True)
    
    # Process tracking
    job_pid = models.IntegerField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Tracking progress
    progress = models.IntegerField(default=0)
    total_items = models.IntegerField(default=0)
    
    # Storing results and state
    search_results = models.JSONField(default=dict, blank=True, null=True)
    selected_novel = models.JSONField(default=dict, blank=True, null=True)
    output_path = models.CharField(max_length=512, blank=True, null=True)
    output_files = models.JSONField(default=list, blank=True, null=True)
    
    # Error information
    error_message = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Job {self.id} - {self.get_status_display()}"
    
    def get_progress_percentage(self):
        """Calculate the progress percentage"""
        if self.total_items <= 0:
            return 0
        return min(100, int((self.progress / self.total_items) * 100))
    
    def update_search_results(self, results):
        """Update the search results JSON field"""
        self.search_results = results
        self.save(update_fields=['search_results', 'updated_at'])
    
    def update_status(self, status, error_message=None):
        """Update the job status and optionally set error message"""
        logger.info(f"Updating job {self.id} status to {status}")
        self.status = status
        if error_message:
            self.error_message = error_message
            
        self.save(update_fields=['status', 'error_message', 'updated_at'])
    
    def update_progress(self, progress, total_items=None):
        """Update the job progress"""
        self.progress = progress
        if total_items is not None:
            self.total_items = total_items
            
        self.save(update_fields=['progress', 'total_items', 'updated_at'])
    
    def update_download_results(self, output_path, output_files):
        """Update the download results"""
        self.output_path = output_path
        self.output_files = output_files
        self.save(update_fields=['output_path', 'output_files', 'updated_at'])
    
    def to_dict(self):
        """Convert job to dictionary with formatted fields"""
        return {
            'id': str(self.id),
            'status': self.status,
            'status_display': self.get_status_display(),
            'query': self.query,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'progress': self.progress,
            'total_items': self.total_items,
            'progress_percentage': self.get_progress_percentage(),
            'search_results': self.search_results,
            'selected_novel': self.selected_novel,
            'output_path': self.output_path,
            'output_files': self.output_files,
            'error_message': self.error_message,
        }
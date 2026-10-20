from django.db import models


class ExternalSource(models.Model):
    """
    Represents an external source (website) where novels are crawled from
    """
    STATUS_CHOICES = [
        ('alive', 'Alive'),
        ('dead', 'Dead'),
    ]
    
    source_name = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='alive')
    
    class Meta:
        ordering = ['source_name']
    
    def __str__(self):
        return f"{self.source_name} ({self.get_status_display()})"

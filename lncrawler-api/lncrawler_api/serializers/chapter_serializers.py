from rest_framework import serializers
from ..models import Chapter

class ChapterSerializer(serializers.ModelSerializer):
    """
    Serializes chapter information
    """
    class Meta:
        model = Chapter
        fields = ['id', 'chapter_id', 'title', 'url', 'volume', 'volume_title', 'has_content']

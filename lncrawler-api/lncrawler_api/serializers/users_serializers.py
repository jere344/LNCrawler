from rest_framework import serializers

from ..models import ReadingHistory, Chapter
from .chapter_serializers import ChapterSerializer

class ReadingHistorySerializer(serializers.ModelSerializer):
    """
    Serializes the ReadingHistory model
    """
    last_read_chapter = ChapterSerializer(read_only=True)
    
    class Meta:
        model = ReadingHistory
        fields = ['id', 'last_read_chapter', 'last_read_at']
        read_only_fields = ['id',  'last_read_at']

class DetailedReadingHistorySerializer(serializers.ModelSerializer):
    """
    Serializes the ReadingHistory model with additional details
    """
    last_read_chapter = ChapterSerializer(read_only=True)
    next_chapter = serializers.SerializerMethodField()
    novel_slug = serializers.SerializerMethodField()
    source_slug = serializers.SerializerMethodField()

    class Meta:
        model = ReadingHistory
        fields = ['id', 'novel_slug', 'source_slug', 'last_read_chapter', 'last_read_at', 'next_chapter']
        read_only_fields = ['id',  'last_read_at', 'next_chapter']
    
    def get_novel_slug(self, obj):
        return obj.novel.slug
    
    def get_source_slug(self, obj):
        return obj.source.source_slug

    def get_next_chapter(self, obj):
        try:
            next_chapter = Chapter.objects.get(
                novel_from_source=obj.source,
                chapter_id=obj.last_read_chapter.chapter_id + 1,
                has_content=True
            )
            return ChapterSerializer(next_chapter).data if next_chapter else None
        except Chapter.DoesNotExist:
            return None
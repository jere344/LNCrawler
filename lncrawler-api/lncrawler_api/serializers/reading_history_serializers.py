from rest_framework import serializers

from ..models import ReadingHistory, Chapter
from .chapter_serializers import ChapterSerializer
from .mixins import ProfileFieldsMixin


class ReadingHistorySerializer(ProfileFieldsMixin, serializers.ModelSerializer):
    """
    Serializes the ReadingHistory model.

    ``card`` is the plain history row (default); ``detail`` adds the novel /
    source slugs and the next / latest chapter.
    """
    last_read_chapter = ChapterSerializer(read_only=True)
    next_chapter = serializers.SerializerMethodField()
    novel_slug = serializers.SerializerMethodField()
    source_slug = serializers.SerializerMethodField()
    source_latest_chapter = serializers.SerializerMethodField()

    default_profile = 'card'
    field_profiles = {
        'card': ['id', 'last_read_chapter', 'last_read_at'],
        'detail': [
            'id', 'novel_slug', 'source_slug', 'last_read_chapter', 'last_read_at',
            'next_chapter', 'source_latest_chapter',
        ],
    }

    class Meta:
        model = ReadingHistory
        read_only_fields = ['id', 'last_read_at', 'next_chapter', 'source_latest_chapter']

    def get_novel_slug(self, obj):
        return obj.novel.slug

    def get_source_slug(self, obj):
        return obj.source.source_slug

    def get_next_chapter(self, obj):
        if not obj.last_read_chapter:
            return None
        next_chapter = Chapter.objects.filter(
            novel_from_source=obj.source,
            chapter_id__gt=obj.last_read_chapter.chapter_id,
            has_content=True
        ).order_by('chapter_id').first()
        return ChapterSerializer(next_chapter).data if next_chapter else None

    def get_source_latest_chapter(self, obj):
        latest_chapter = Chapter.objects.filter(
            novel_from_source=obj.source,
            has_content=True
        ).order_by('-chapter_id').first()
        return ChapterSerializer(latest_chapter).data if latest_chapter else None

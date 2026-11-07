from rest_framework import serializers

from ..models import ReadingHistory, Chapter
from .chapter_serializers import ChapterSerializer
from .mixins import ProfileFieldsMixin

# From this position on the user has finished the chapter, so Continue opens the next one.
FINISHED_POSITION = 0.95


class ReadingHistorySerializer(ProfileFieldsMixin, serializers.ModelSerializer):
    """
    Serializes the ReadingHistory model: where the user is in a novel.

    ``card`` is the pointer (default): the current chapter and the position in it. ``library`` is the progress
    a library item shows (source name and slug, unread count, latest chapter, and what Continue opens);
    ``detail`` adds the novel and source slugs.
    """
    current_chapter = ChapterSerializer(read_only=True)
    resume = serializers.SerializerMethodField()
    unread_chapters = serializers.SerializerMethodField()
    novel_slug = serializers.SerializerMethodField()
    source_slug = serializers.SerializerMethodField()
    source_name = serializers.SerializerMethodField()
    source_latest_chapter = serializers.SerializerMethodField()

    default_profile = 'card'
    field_profiles = {
        'card': ['id', 'current_chapter', 'position', 'last_read_at'],
        'library': [
            'source_slug', 'source_name', 'current_chapter', 'position', 'unread_chapters',
            'source_latest_chapter', 'resume',
        ],
        'detail': [
            'id', 'novel_slug', 'source_slug', 'source_name', 'current_chapter', 'position', 'last_read_at',
            'resume', 'unread_chapters', 'source_latest_chapter',
        ],
    }

    class Meta:
        model = ReadingHistory
        read_only_fields = ['id', 'last_read_at', 'resume', 'source_latest_chapter']

    def to_representation(self, instance):
        # The chapter cards label their title in the source's language: hand them the source the history row
        # already selected rather than letting each chapter fetch it.
        chapter = instance.current_chapter
        if chapter is not None:
            chapter.novel_from_source = instance.source
        return super().to_representation(instance)

    def get_novel_slug(self, obj):
        return obj.novel.slug

    def get_source_slug(self, obj):
        return obj.source.source_slug

    def get_source_name(self, obj):
        return obj.source.external_source.source_name

    def _card(self, obj, chapter):
        chapter.novel_from_source = obj.source
        return self._child(ChapterSerializer).to_representation(chapter)

    def _next_chapter(self, obj):
        """The content chapter after the current one, or None."""
        # Prefetched histories carry the next chapter's card columns (see annotate_reading_history);
        # an unsaved Chapter built from them serializes exactly like a fetched one (has_audio is False).
        if 'annotated_next_chapter' in obj.__dict__:
            annotated = obj.annotated_next_chapter
            if annotated is None:
                return None
            return Chapter(**annotated, novel_from_source=obj.source)
        return Chapter.objects.filter(
            novel_from_source=obj.source,
            chapter_id__gt=obj.current_chapter.chapter_id,
            has_content=True
        ).order_by('chapter_id').first()

    def get_resume(self, obj):
        """What Continue opens: the current chapter from ``position`` while the user is still in it, else the
        next chapter with content from its top. None without a current chapter, or when nothing follows."""
        if obj.current_chapter_id is None:
            return None
        if obj.position < FINISHED_POSITION:
            return {'chapter': self._card(obj, obj.current_chapter), 'progress': obj.position}
        next_chapter = self._next_chapter(obj)
        if next_chapter is None:
            return None
        return {'chapter': self._card(obj, next_chapter), 'progress': 0}

    def get_unread_chapters(self, obj):
        """How many available (has_content) chapters follow the current one.

        Counting ``latest - current`` ids would include gaps left by failed
        downloads, so the unread badge must count only chapters with content.
        Prefetched histories carry ``annotated_unread_chapters`` (one query for
        the whole page); the annotation vs a per-row COUNT is detected via
        ``__dict__`` like the other queryset-annotated fields.
        """
        if not obj.current_chapter_id:
            return None
        if 'annotated_unread_chapters' in obj.__dict__:
            return obj.annotated_unread_chapters or 0
        return Chapter.objects.filter(
            novel_from_source=obj.source_id,
            chapter_id__gt=obj.current_chapter.chapter_id,
            has_content=True,
        ).count()

    def get_source_latest_chapter(self, obj):
        # The source's stored latest chapter: history querysets select it with the source.
        latest_chapter = obj.source.latest_available_chapter
        if latest_chapter is None:
            return None
        latest_chapter.novel_from_source = obj.source
        return self._child(ChapterSerializer).to_representation(latest_chapter)

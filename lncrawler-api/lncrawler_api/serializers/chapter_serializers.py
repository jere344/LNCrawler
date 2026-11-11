from rest_framework import serializers
from django.db.models import Subquery
from ..models import Chapter
from ..models.comments_models import Comment
from ..services.audiobook_public import chapter_audio_hidden, chapter_audio_url, public_audio_chapters
from ..utils import build_media_url
from .mixins import ProfileFieldsMixin


class ChapterSerializer(ProfileFieldsMixin, serializers.ModelSerializer):
    """
    Serializes chapter information.

    ``card`` is the lightweight chapter row (default); ``content`` adds the
    chapter body, navigation and the comment summary of the chapter.
    """
    display_title = serializers.SerializerMethodField()
    body = serializers.SerializerMethodField()
    prev_chapter = serializers.SerializerMethodField()
    next_chapter = serializers.SerializerMethodField()
    prev_chapter_id = serializers.SerializerMethodField()
    next_chapter_id = serializers.SerializerMethodField()
    novel_title = serializers.SerializerMethodField()
    novel_id = serializers.SerializerMethodField()
    novel_slug = serializers.SerializerMethodField()
    source_id = serializers.SerializerMethodField()
    source_name = serializers.SerializerMethodField()
    source_slug = serializers.SerializerMethodField()
    images_path = serializers.SerializerMethodField()
    source_overview_image_url = serializers.SerializerMethodField()
    audio_url = serializers.SerializerMethodField()
    audio_duration_s = serializers.SerializerMethodField()
    language = serializers.SerializerMethodField()
    has_audio = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    top_comment = serializers.SerializerMethodField()

    default_profile = 'card'
    field_profiles = {
        'card': [
            'id', 'chapter_id', 'title', 'display_title', 'url', 'volume', 'volume_title', 'has_content', 'has_audio',
        ],
        'content': [
            'id', 'chapter_id', 'title', 'display_title', 'url', 'novel_title', 'novel_id', 'novel_slug',
            'source_id', 'source_name', 'source_slug', 'language', 'body', 'prev_chapter', 'next_chapter',
            'prev_chapter_id', 'next_chapter_id',
            'images_path', 'source_overview_image_url', 'audio_url', 'audio_duration_s',
            'comment_count', 'top_comment',
        ],
        'unavailable': [
            'chapter_id', 'title', 'display_title', 'novel_title', 'prev_chapter', 'next_chapter',
        ],
    }

    class Meta:
        model = Chapter

    def get_display_title(self, obj):
        return obj.display_title

    def get_body(self, obj):
        return obj.body

    def _neighbours(self, obj):
        # All four neighbour values come from one SELECT, memoized on the chapter
        # so the prev/next fields of a single response cost one query.
        cached = getattr(obj, '_neighbours', None)
        if cached is not None:
            return cached

        siblings = Chapter.objects.filter(novel_from_source_id=obj.novel_from_source_id)

        def first_id(qs):
            return Subquery(qs.values('chapter_id')[:1])

        row = Chapter.objects.filter(pk=obj.pk).values(
            prev_chapter=first_id(siblings.filter(
                chapter_id__lt=obj.chapter_id, has_content=True
            ).order_by('-chapter_id')),
            next_chapter=first_id(siblings.filter(
                chapter_id__gt=obj.chapter_id, has_content=True
            ).order_by('chapter_id')),
            # Immediate neighbour regardless of content, so the reader can detect a
            # gap between the current chapter and the next/prev *available* one.
            prev_chapter_id=first_id(siblings.filter(
                chapter_id__lt=obj.chapter_id
            ).order_by('-chapter_id')),
            next_chapter_id=first_id(siblings.filter(
                chapter_id__gt=obj.chapter_id
            ).order_by('chapter_id')),
        ).first()
        if row is None:
            row = {
                'prev_chapter': None,
                'next_chapter': None,
                'prev_chapter_id': None,
                'next_chapter_id': None,
            }
        obj._neighbours = row
        return row

    def get_prev_chapter(self, obj):
        return self._neighbours(obj)['prev_chapter']

    def get_next_chapter(self, obj):
        return self._neighbours(obj)['next_chapter']

    def get_prev_chapter_id(self, obj):
        return self._neighbours(obj)['prev_chapter_id']

    def get_next_chapter_id(self, obj):
        return self._neighbours(obj)['next_chapter_id']

    def get_novel_title(self, obj):
        return obj.novel_from_source.title

    def get_novel_id(self, obj):
        return str(obj.novel_from_source.novel.id)

    def get_novel_slug(self, obj):
        return obj.novel_from_source.novel.slug

    def get_source_id(self, obj):
        return str(obj.novel_from_source.id)

    def get_source_name(self, obj):
        return obj.novel_from_source.external_source.source_name

    def get_source_slug(self, obj):
        return obj.novel_from_source.source_slug

    def get_language(self, obj):
        return obj.novel_from_source.language

    def get_images_path(self, obj: Chapter):
        if obj.images:  # no need if no images
            return build_media_url(f"{obj.novel_from_source.source_path}/images")
        return None

    def get_source_overview_image_url(self, obj: Chapter):
        return build_media_url(obj.novel_from_source.overview_picture_path)

    def _public_audio(self, obj: Chapter):
        """The AudiobookChapter of the chapter when its audio is public, else None. One query, kept for both
        audio fields of the same chapter."""
        cache = self.__dict__.setdefault('_public_audio_cache', {})
        viewer = getattr(self.context.get('request'), 'user', None)
        if obj.pk not in cache:
            cache[obj.pk] = (
                None if chapter_audio_hidden(viewer, obj.novel_from_source)
                else public_audio_chapters().select_related('part').filter(chapter=obj).first()
            )
        return cache[obj.pk]

    def get_audio_url(self, obj: Chapter):
        audio = self._public_audio(obj)
        return chapter_audio_url(audio) if audio else None

    def get_audio_duration_s(self, obj: Chapter):
        audio = self._public_audio(obj)
        return audio.duration_s if audio else None

    def get_has_audio(self, obj: Chapter):
        # The chapter list view passes the ids of the chapters of its page that have public audio, in one query
        # (context ``audio_chapter_ids``); a serializer without it reports False.
        return obj.pk in self.context.get('audio_chapter_ids', ())

    def get_comment_count(self, obj: Chapter):
        # Every comment on this chapter number, across all sources, replies included.
        return Comment.objects.for_chapter_number(
            obj.novel_from_source.novel_id, obj.chapter_id
        ).count()

    def get_top_comment(self, obj: Chapter):
        # Highest vote score among the root comments, newest first on ties.
        top = (
            Comment.objects.for_chapter_number(obj.novel_from_source.novel_id, obj.chapter_id)
            .roots()
            .ranked('top')
            .first()
        )
        if top is None:
            return None
        return {
            'id': str(top.id),
            'author_name': top.author_name,
            # A spoiler's text stays hidden in the summary; the flag tells the reader why.
            'message': None if top.contains_spoiler else top.message[:160],
            'contains_spoiler': top.contains_spoiler,
            'vote_score': top.vote_score,
        }

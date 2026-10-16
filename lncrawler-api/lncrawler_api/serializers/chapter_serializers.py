from rest_framework import serializers
from django.db.models import Subquery
from ..models import Chapter
from ..utils import build_media_url
from .mixins import ProfileFieldsMixin


class ChapterSerializer(ProfileFieldsMixin, serializers.ModelSerializer):
    """
    Serializes chapter information.

    ``card`` is the lightweight chapter row (default); ``content`` adds the
    chapter body and navigation.
    """
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
    language = serializers.SerializerMethodField()

    default_profile = 'card'
    field_profiles = {
        'card': [
            'id', 'chapter_id', 'title', 'url', 'volume', 'volume_title', 'has_content',
        ],
        'content': [
            'id', 'chapter_id', 'title', 'novel_title', 'novel_id', 'novel_slug',
            'source_id', 'source_name', 'source_slug', 'language', 'body', 'prev_chapter', 'next_chapter',
            'prev_chapter_id', 'next_chapter_id',
            'images_path', 'source_overview_image_url',
        ],
        'unavailable': [
            'chapter_id', 'title', 'novel_title', 'prev_chapter', 'next_chapter',
        ],
    }

    class Meta:
        model = Chapter

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
        return obj.novel_from_source.novel.title

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

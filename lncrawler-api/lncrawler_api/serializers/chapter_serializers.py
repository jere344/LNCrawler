from urllib.parse import quote
from django.conf import settings
from rest_framework import serializers
from ..models import Chapter

class ChapterSerializer(serializers.ModelSerializer):
    """
    Serializes chapter information
    """
    class Meta:
        model = Chapter
        fields = ['id', 'chapter_id', 'title', 'url', 'volume', 'volume_title', 'has_content']


class ChapterContentSerializer(serializers.ModelSerializer):
    """
    Serializes chapter content with navigation
    """
    body = serializers.SerializerMethodField()
    prev_chapter = serializers.SerializerMethodField()
    next_chapter = serializers.SerializerMethodField()
    novel_title = serializers.SerializerMethodField()
    novel_id = serializers.SerializerMethodField()
    novel_slug = serializers.SerializerMethodField()
    source_id = serializers.SerializerMethodField()
    source_name = serializers.SerializerMethodField() 
    source_slug = serializers.SerializerMethodField()
    images_path = serializers.SerializerMethodField()
    source_overview_image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Chapter
        fields = [
            'id', 'chapter_id', 'title', 'novel_title', 'novel_id', 'novel_slug',
            'source_id', 'source_name', 'source_slug', 'body', 'prev_chapter', 'next_chapter',
            'images_path', 'source_overview_image_url',
        ]
    
    def get_body(self, obj):
        return obj.body
    
    def get_prev_chapter(self, obj):
        previous_chapter = obj.novel_from_source.chapters.filter(
            chapter_id__lt=obj.chapter_id
        ).order_by('-chapter_id').first()
        return previous_chapter.chapter_id if previous_chapter and previous_chapter.has_content else None
    
    def get_next_chapter(self, obj):
        next_chapter = obj.novel_from_source.chapters.filter(
            chapter_id__gt=obj.chapter_id
        ).order_by('chapter_id').first()
        return next_chapter.chapter_id if next_chapter and next_chapter.has_content else None
    
    def get_novel_title(self, obj):
        return obj.novel_from_source.novel.title
    
    def get_novel_id(self, obj):
        return str(obj.novel_from_source.novel.id)
    
    def get_novel_slug(self, obj):
        return obj.novel_from_source.novel.slug
    
    def get_source_id(self, obj):
        return str(obj.novel_from_source.id)
    
    def get_source_name(self, obj):
        return obj.novel_from_source.source_name
    
    def get_source_slug(self, obj):
        return obj.novel_from_source.source_slug
    
    def get_images_path(self, obj:Chapter):
        if obj.images: # no need if no images
            return quote(f"{settings.SITE_API_URL}/{settings.LNCRAWL_URL}{obj.novel_from_source.source_path}/images", safe=':/')
        return None
    
    def get_source_overview_image_url(self, obj:Chapter):
        if obj.novel_from_source.overview_picture_path:
            return quote(f"{settings.SITE_API_URL}/{settings.LNCRAWL_URL}{obj.novel_from_source.overview_picture_path}", safe=':/')
        return None
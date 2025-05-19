from rest_framework import serializers
from django.conf import settings
from ..models import (
    NovelFromSource, Chapter
)
from urllib.parse import quote
from ..utils import get_client_ip


class NovelSourceSerializer(serializers.ModelSerializer):
    """
    Serializes novel source information
    """
    authors = serializers.SerializerMethodField()
    genres = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    user_vote = serializers.SerializerMethodField()
    novel_id = serializers.SerializerMethodField()
    novel_slug = serializers.SerializerMethodField()
    novel_title = serializers.SerializerMethodField()
    vote_score = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    latest_available_chapter = serializers.SerializerMethodField()
    
    class Meta:
        model = NovelFromSource
        fields = [
            'id', 'title', 'source_url', 'source_name', 'source_slug', 'cover_path',
            'authors', 'genres', 'tags', 'language', 'status', 'synopsis',
            'chapters_count', 'volumes_count', 'last_chapter_update', 'upvotes', 'downvotes',
            'vote_score', 'user_vote', 'novel_id', 'novel_slug', 'novel_title', 'cover_url',
            'latest_available_chapter'
        ]

    def get_cover_url(self, obj):
        if obj.cover_path:
            return quote(f"{settings.SITE_API_URL}/{settings.LNCRAWL_URL}{obj.cover_path}", safe=':/')
        return None
    
    def get_authors(self, obj):
        return [author.name for author in obj.authors.all()]
    
    def get_genres(self, obj):
        return [genre.name for genre in obj.genres.all()]
    
    def get_tags(self, obj):
        return [tag.name for tag in obj.tags.all()]
    
    def get_user_vote(self, obj):
        request = self.context.get('request')
        if not request:
            return None
            
        client_ip = get_client_ip(request)
        if not client_ip:
            return None
            
        try:
            vote = obj.votes.filter(ip_address=client_ip).first()
            return vote.vote_type if vote else None
        except:
            return None

    def get_novel_id(self, obj):
        return str(obj.novel.id) if obj.novel else None

    def get_novel_slug(self, obj):
        return obj.novel.slug if obj.novel else None

    def get_novel_title(self, obj):
        return obj.novel.title if obj.novel else None

    def get_vote_score(self, obj):
        return obj.upvotes - obj.downvotes
    
    def get_latest_available_chapter(self, obj):
        """Return the latest available chapter with content"""
        latest_chapter = obj.chapters.filter(has_content=True).order_by('-chapter_id').first()
        if latest_chapter:
            return ChapterSerializer(latest_chapter).data
        return None


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
    
    class Meta:
        model = Chapter
        fields = [
            'id', 'chapter_id', 'title', 'novel_title', 'novel_id', 'novel_slug',
            'source_id', 'source_name', 'source_slug', 'body', 'prev_chapter', 'next_chapter'
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
